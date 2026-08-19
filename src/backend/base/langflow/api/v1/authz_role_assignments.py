"""CRUD API for production RBAC role assignments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from lfx.log.logger import logger
from lfx.services.authorization import (
    AuthorizationMutation,
    AuthorizationMutationKind,
    AuthorizationMutationRejected,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.api.v1.schemas.authz_role_assignments import (
    RoleAssignmentCreate,
    RoleAssignmentGrantSummary,
    RoleAssignmentRead,
)
from langflow.services.authorization.bootstrap import (
    ensure_authorization_bootstrap,
    is_managed_service_user,
    resolve_role_permissions,
)
from langflow.services.authorization.invalidation import safe_invalidate_user
from langflow.services.authorization.lifecycle import (
    acquire_identity_mutation_lock,
    safe_identity_mutation_committed,
    stage_identity_mutation,
    validate_identity_mutation,
)
from langflow.services.authorization.utils import audit_decision
from langflow.services.database.models.auth import AuthzRole, AuthzRoleAssignment, AuthzRoleAssignmentGrant
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_authorization_service

router = APIRouter(prefix="/authz/role-assignments", tags=["Authorization"])

_LIST_MAX_LIMIT = 200
_LIST_DEFAULT_LIMIT = 100
_ALLOWED_DOMAIN_TYPES = {"global", "organization", "org", "workspace", "project", "channel"}


def _domain_context(domain_type: str, domain_id: UUID | None) -> tuple[str, dict[str, UUID]]:
    if domain_type == "global" or domain_id is None:
        return "*", {}
    context_keys = {
        "organization": "organization_id",
        "org": "organization_id",
        "workspace": "workspace_id",
        "project": "project_id",
        "channel": "connection_id",
    }
    return f"{domain_type}:{domain_id}", {context_keys[domain_type]: domain_id}


async def _require_assignment_admin(
    *,
    current_user: User,
    role: AuthzRole,
    domain_type: str,
    domain_id: UUID | None,
    session: DbSession,
    action: str = "assign",
) -> None:
    """Allow superusers or least-privileged scoped RBAC administrators."""
    if current_user.is_active and current_user.is_superuser:
        return

    authz = get_authorization_service()
    if not await authz.is_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Scoped role administration requires RBAC enforcement to be enabled.",
        )

    domain, context = _domain_context(domain_type, domain_id)
    can_administer = await authz.enforce(
        user_id=current_user.id,
        domain=domain,
        obj="rbac:*",
        act=action,
        context=context,
    )
    if not can_administer:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    # A scoped administrator may only delegate permissions they already hold in
    # the same domain. This prevents channel admins from promoting themselves or
    # another user to organization/platform administrator.
    delegated_permissions = await resolve_role_permissions(session, {role.id})
    checks: list[tuple[str, str]] = []
    for permission in sorted(delegated_permissions):
        resource, separator, permission_action = permission.partition(":")
        if separator and resource and permission_action:
            checks.append((f"{resource}:*", permission_action))
    if checks:
        decisions = await authz.batch_enforce(
            user_id=current_user.id,
            domain=domain,
            requests=checks,
            context=context,
        )
        if not all(decisions):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A role cannot delegate permissions beyond the operator's effective scope.",
            )


async def _require_assignment_reader(
    *,
    current_user: User,
    domain_type: str | None,
    domain_id: UUID | None,
) -> None:
    if current_user.is_active and current_user.is_superuser:
        return
    if domain_type is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A scoped domain filter is required when reading another user's assignments.",
        )
    normalized = domain_type.strip().lower()
    if normalized not in _ALLOWED_DOMAIN_TYPES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown domain type")
    domain, context = _domain_context(normalized, domain_id)
    authz = get_authorization_service()
    if not await authz.is_enabled() or not await authz.enforce(
        user_id=current_user.id,
        domain=domain,
        obj="rbac:*",
        act="read",
        context=context,
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")


async def _assignment_reads(session, assignments: list[AuthzRoleAssignment]) -> list[RoleAssignmentRead]:
    """Serialize effective assignments with source summaries in two queries."""
    if not assignments:
        return []
    assignment_ids = [assignment.id for assignment in assignments]
    grants = (
        await session.exec(
            select(AuthzRoleAssignmentGrant)
            .where(AuthzRoleAssignmentGrant.assignment_id.in_(assignment_ids))
            .order_by(
                AuthzRoleAssignmentGrant.assignment_id,
                AuthzRoleAssignmentGrant.source_kind,
                AuthzRoleAssignmentGrant.provider_id,
                AuthzRoleAssignmentGrant.external_group,
            )
        )
    ).all()
    grants_by_assignment: dict[UUID, list[RoleAssignmentGrantSummary]] = {}
    for grant in grants:
        grants_by_assignment.setdefault(grant.assignment_id, []).append(
            RoleAssignmentGrantSummary.model_validate(grant)
        )
    return [
        RoleAssignmentRead.model_validate(assignment).model_copy(
            update={"grant_sources": grants_by_assignment.get(assignment.id, [])}
        )
        for assignment in assignments
    ]


def _assignment_match(payload: RoleAssignmentCreate, *, domain_type: str):
    domain_match = (
        AuthzRoleAssignment.domain_id.is_(None)
        if payload.domain_id is None
        else AuthzRoleAssignment.domain_id == payload.domain_id
    )
    return (
        AuthzRoleAssignment.user_id == payload.user_id,
        AuthzRoleAssignment.role_id == payload.role_id,
        AuthzRoleAssignment.domain_type == domain_type,
        domain_match,
    )


@router.get("", response_model=list[RoleAssignmentRead])
@router.get("/", response_model=list[RoleAssignmentRead])
async def list_assignments(
    session: DbSession,
    current_user: CurrentActiveUser,
    user_id: Annotated[UUID | None, Query(description="Filter by user")] = None,
    role_id: Annotated[UUID | None, Query(description="Filter by role")] = None,
    domain_type: Annotated[str | None, Query()] = None,
    domain_id: Annotated[UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_LIST_MAX_LIMIT)] = _LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RoleAssignmentRead]:
    await ensure_authorization_bootstrap(session)
    if user_id is None:
        user_id = current_user.id
    elif user_id != current_user.id:
        await _require_assignment_reader(
            current_user=current_user,
            domain_type=domain_type,
            domain_id=domain_id,
        )

    stmt = select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id)
    if role_id is not None:
        stmt = stmt.where(AuthzRoleAssignment.role_id == role_id)
    if domain_type is not None:
        stmt = stmt.where(AuthzRoleAssignment.domain_type == domain_type.strip().lower())
    if domain_id is not None:
        stmt = stmt.where(AuthzRoleAssignment.domain_id == domain_id)
    stmt = stmt.order_by(AuthzRoleAssignment.assigned_at.desc(), AuthzRoleAssignment.id).offset(offset).limit(limit)
    rows = (await session.exec(stmt)).all()
    return await _assignment_reads(session, list(rows))


@router.post("", response_model=RoleAssignmentRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=RoleAssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: RoleAssignmentCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> RoleAssignmentRead:
    """Assign one role after scope and delegation checks."""
    await ensure_authorization_bootstrap(session)
    authorization_service = get_authorization_service()
    # Let authorization plugins acquire their transaction-scoped policy-write
    # lock before the first canonical identity read or write. An external
    # compiler may need the same global lock later while staging derived policy.
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.ROLE_ASSIGNMENT_CREATED,
        affected_user_ids=(payload.user_id,),
    )

    user = await session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_id not found")
    if is_managed_service_user(user):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Managed channel service identities cannot receive RBAC roles",
        )
    role = await session.get(AuthzRole, payload.role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_id not found")

    domain_type = payload.domain_type.strip().lower()
    if domain_type not in _ALLOWED_DOMAIN_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"domain_type must be one of {sorted(_ALLOWED_DOMAIN_TYPES)}",
        )
    if domain_type == "global" and payload.domain_id is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="global role assignments must not include domain_id",
        )
    if domain_type != "global" and payload.domain_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{domain_type} role assignments require domain_id",
        )

    await _require_assignment_admin(
        current_user=current_user,
        role=role,
        domain_type=domain_type,
        domain_id=payload.domain_id,
        session=session,
    )

    candidate = AuthzRoleAssignment(
        user_id=payload.user_id,
        role_id=payload.role_id,
        domain_type=domain_type,
        domain_id=payload.domain_id,
        assigned_at=datetime.now(timezone.utc),
        assigned_by=current_user.id,
    )
    assignment = (
        await session.exec(select(AuthzRoleAssignment).where(*_assignment_match(payload, domain_type=domain_type)))
    ).first()
    effective_assignment_created = assignment is None
    if assignment is None:
        assignment = candidate
        session.add(assignment)
        await session.flush()
    else:
        existing_manual = (
            await session.exec(
                select(AuthzRoleAssignmentGrant).where(
                    AuthzRoleAssignmentGrant.assignment_id == assignment.id,
                    AuthzRoleAssignmentGrant.source_kind == "manual",
                )
            )
        ).first()
        if existing_manual is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Manual assignment already exists for this user/role/domain",
            )

    session.add(
        AuthzRoleAssignmentGrant(
            assignment_id=assignment.id,
            source_kind="manual",
            administrative_actor=current_user.id,
        )
    )
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.ROLE_ASSIGNMENT_CREATED,
        entity_id=assignment.id,
        actor_user_id=current_user.id,
        affected_user_ids=(payload.user_id,),
        role_id=payload.role_id,
        domain_type=domain_type,
        domain_id=payload.domain_id,
        policy_relevant_fields=("user_id", "role_id", "domain_type", "domain_id"),
    )
    try:
        await session.flush()
        if effective_assignment_created:
            await stage_identity_mutation(authorization_service, session, mutation)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assignment already exists for this user/role/domain",
        ) from exc
    if effective_assignment_created:
        await safe_identity_mutation_committed(authorization_service, mutation)
    await session.refresh(assignment)
    await safe_invalidate_user(get_authorization_service(), payload.user_id, op="role_assignment:create")
    await audit_decision(
        user_id=current_user.id,
        action="role_assignment:create",
        obj=f"user:{payload.user_id}",
        result="allow",
        details={
            "assignment_id": str(assignment.id),
            "role_id": str(payload.role_id),
            "role_name": role.name,
            "domain_type": domain_type,
            "domain_id": str(payload.domain_id) if payload.domain_id else None,
        },
    )
    logger.info(
        "Assigned role=%s to user=%s (domain=%s/%s)",
        role.name,
        payload.user_id,
        domain_type,
        payload.domain_id,
    )
    return (await _assignment_reads(session, [assignment]))[0]


@router.delete(
    "/{assignment_id}",
    response_model=RoleAssignmentRead,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_204_NO_CONTENT: {"description": "Manual assignment fully revoked."}},
)
async def delete_assignment(
    assignment_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> RoleAssignmentRead | Response:
    """Revoke a role assignment after the same delegation checks used on create."""
    await ensure_authorization_bootstrap(session)
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.ROLE_ASSIGNMENT_DELETED,
        entity_id=assignment_id,
    )
    assignment = await session.get(
        AuthzRoleAssignment,
        assignment_id,
        populate_existing=True,
        with_for_update=True,
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    # Superusers retain the official direct-revocation path and do not need a
    # second role lookup. Scoped administrators must still prove delegation
    # against the role currently bound to the assignment.
    if not (current_user.is_active and current_user.is_superuser):
        role = await session.get(AuthzRole, assignment.role_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
        await _require_assignment_admin(
            current_user=current_user,
            role=role,
            domain_type=assignment.domain_type,
            domain_id=assignment.domain_id,
            session=session,
        )
    grants = (
        await session.exec(
            select(AuthzRoleAssignmentGrant)
            .where(AuthzRoleAssignmentGrant.assignment_id == assignment_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).all()
    manual_grant = next((grant for grant in grants if grant.source_kind == "manual"), None)
    if grants and manual_grant is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="IdP-derived assignments cannot be deleted through the manual assignment API",
        )
    if manual_grant is not None and len(grants) > 1:
        surviving_grants = [grant for grant in grants if grant is not manual_grant]
        await session.delete(manual_grant)
        await session.commit()
        await audit_decision(
            user_id=current_user.id,
            action="role_assignment:delete_manual_source",
            obj=f"user:{assignment.user_id}",
            result="allow",
            details={
                "assignment_id": str(assignment_id),
                "role_id": str(assignment.role_id),
                "domain_type": assignment.domain_type,
                "domain_id": str(assignment.domain_id) if assignment.domain_id else None,
                "effective_assignment_preserved": True,
                "surviving_grant_sources": [
                    {
                        "source_kind": grant.source_kind,
                        "provider_id": grant.provider_id,
                        "external_group": grant.external_group,
                    }
                    for grant in surviving_grants
                ],
            },
        )
        return RoleAssignmentRead.model_validate(assignment).model_copy(
            update={"grant_sources": [RoleAssignmentGrantSummary.model_validate(grant) for grant in surviving_grants]}
        )

    user_id = assignment.user_id
    role_id = assignment.role_id
    domain_type = assignment.domain_type
    domain_id = assignment.domain_id
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.ROLE_ASSIGNMENT_DELETED,
        entity_id=assignment_id,
        actor_user_id=current_user.id,
        affected_user_ids=(user_id,),
        role_id=role_id,
        domain_type=domain_type,
        domain_id=domain_id,
        policy_relevant_fields=("user_id", "role_id", "domain_type", "domain_id"),
    )
    try:
        await validate_identity_mutation(authorization_service, session, mutation)
    except AuthorizationMutationRejected as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.public_detail) from exc

    await session.delete(assignment)
    await session.flush()
    await stage_identity_mutation(authorization_service, session, mutation)
    await session.commit()
    await safe_identity_mutation_committed(authorization_service, mutation)
    await safe_invalidate_user(get_authorization_service(), user_id, op="role_assignment:delete")
    await audit_decision(
        user_id=current_user.id,
        action="role_assignment:delete",
        obj=f"user:{user_id}",
        result="allow",
        details={
            "assignment_id": str(assignment_id),
            "role_id": str(role_id),
            "domain_type": domain_type,
            "domain_id": str(domain_id) if domain_id else None,
        },
    )
    logger.info("Revoked role assignment id=%s (user=%s)", assignment_id, user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
