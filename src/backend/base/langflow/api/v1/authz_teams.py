"""CRUD API for authz_team and authz_team_member rows.

Teams group users for bulk role assignment and share targeting. The
authorization plugin compiles team memberships into its own representation
during policy sync.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from lfx.log.logger import logger
from lfx.services.authorization import AuthorizationMutation, AuthorizationMutationKind
from lfx.utils.util_strings import escape_like_pattern
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.api.v1.schemas.authz_teams import (
    TeamCreate,
    TeamMemberCreate,
    TeamMemberRead,
    TeamRead,
    TeamRoleAssignmentCreate,
    TeamRoleAssignmentRead,
    TeamUpdate,
)
from langflow.services.authorization.audit import AUDIT_EVENT_ACCESS, AUDIT_EVENT_MUTATION
from langflow.services.authorization.bootstrap import is_managed_service_user
from langflow.services.authorization.invalidation import safe_invalidate_all
from langflow.services.authorization.lifecycle import (
    acquire_identity_mutation_lock,
    safe_identity_mutation_committed,
    stage_identity_mutation,
)
from langflow.services.authorization.team_roles import (
    TeamRoleGrant,
    create_team_role_grant,
    delete_all_team_role_grants,
    delete_team_role_grant,
    list_team_role_grants,
    remove_team_member_grants,
    sync_team_member_grants,
)
from langflow.services.authorization.utils import audit_decision
from langflow.services.database.models.auth import AuthzRole, AuthzTeam, AuthzTeamMember
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_authorization_service

router = APIRouter(prefix="/authz/teams", tags=["Authorization"], include_in_schema=False)

# See ``authz_roles._LIST_MAX_LIMIT`` — same bound, applied to teams + members.
_LIST_MAX_LIMIT = 200
_LIST_DEFAULT_LIMIT = 100


async def _audit_deny(*, user_id: UUID, action: str, obj: str, status_code: int, reason: str) -> None:
    await audit_decision(
        user_id=user_id,
        action=action,
        obj=obj,
        result="deny",
        details={"event": AUDIT_EVENT_ACCESS, "status_code": status_code, "reason": reason},
    )


async def _require_superuser(user, *, action: str, obj: str) -> None:
    if not getattr(user, "is_superuser", False):
        await _audit_deny(
            user_id=user.id,
            action=action,
            obj=obj,
            status_code=status.HTTP_403_FORBIDDEN,
            reason="superuser_required",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser required to administer teams.",
        )


async def _require_superuser_dependency(request: Request, current_user: CurrentActiveUser) -> None:
    """Run the superuser gate as a route dependency, i.e. before body validation.

    FastAPI solves a route's ``dependencies`` before validating that route's own
    body, so an unauthorised caller is refused whatever they post. Gated only in
    the endpoint body, they first receive the same 422 field names and enum
    values a superuser would, which lets them map the request contract of a
    route they cannot invoke.

    The in-body call is kept as well: it is the gate for anything that reaches
    the endpoint function without FastAPI resolving dependencies.
    """
    team_id = request.path_params.get("team_id", "*")
    is_member_route = "/members" in request.url.path
    is_role_route = "/roles" in request.url.path
    action = (
        "team_member:create"
        if is_member_route and request.method == "POST"
        else "team_member:delete"
        if is_member_route and request.method == "DELETE"
        else "team_role:create"
        if is_role_route and request.method == "POST"
        else "team_role:delete"
        if is_role_route and request.method == "DELETE"
        else "team_role:read"
        if is_role_route
        else {"POST": "team:create", "PATCH": "team:update", "DELETE": "team:delete"}.get(
            request.method,
            "team:access",
        )
    )
    await _require_superuser(current_user, action=action, obj=f"team:{team_id}")


SUPERUSER_ONLY = [Depends(_require_superuser_dependency)]


async def _require_team_reader(session: DbSession, *, team_id: UUID, current_user: User) -> None:
    if current_user.is_active and current_user.is_superuser:
        return
    membership = (
        await session.exec(
            select(AuthzTeamMember.id).where(
                AuthzTeamMember.team_id == team_id,
                AuthzTeamMember.user_id == current_user.id,
            )
        )
    ).first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")


def _team_role_read(grant: TeamRoleGrant) -> TeamRoleAssignmentRead:
    return TeamRoleAssignmentRead(
        id=grant.id,
        team_id=grant.team_id,
        role_id=grant.role_id,
        domain_type=grant.domain_type,
        domain_id=grant.domain_id,
        assigned_by=grant.assigned_by,
    )


# --- teams ---------------------------------------------------------------- #


@router.get("", response_model=list[TeamRead])
@router.get("/", response_model=list[TeamRead])
async def list_teams(
    session: DbSession,
    current_user: CurrentActiveUser,  # noqa: ARG001 — any authenticated user can list
    search: Annotated[str | None, Query(description="Substring match on team_name or adom_name")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_LIST_MAX_LIMIT)] = _LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TeamRead]:
    """List teams. Open to any authenticated user (for the share dialog's team picker).

    Paginated via ``limit`` / ``offset`` so a single call cannot enumerate every
    team. Stable order is ``(team_name, id)`` so ``offset`` is deterministic.
    """
    stmt = select(AuthzTeam)
    if search:
        like = f"%{escape_like_pattern(search)}%"
        stmt = stmt.where(
            (AuthzTeam.team_name.ilike(like, escape="\\")) | (AuthzTeam.adom_name.ilike(like, escape="\\"))
        )
    if is_active is not None:
        stmt = stmt.where(AuthzTeam.is_active == is_active)
    stmt = stmt.order_by(AuthzTeam.team_name, AuthzTeam.id).offset(offset).limit(limit)
    rows = (await session.exec(stmt)).all()
    return [TeamRead.model_validate(row) for row in rows]


@router.get("/{team_id}", response_model=TeamRead)
async def read_team(
    team_id: UUID,
    session: DbSession,
    current_user: CurrentActiveUser,  # noqa: ARG001
) -> TeamRead:
    team = await session.get(AuthzTeam, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return TeamRead.model_validate(team)


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED, dependencies=SUPERUSER_ONLY)
@router.post("/", response_model=TeamRead, status_code=status.HTTP_201_CREATED, dependencies=SUPERUSER_ONLY)
async def create_team(
    payload: TeamCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRead:
    await _require_superuser(current_user, action="team:create", obj="team:*")
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.TEAM_CREATED,
    )
    team = AuthzTeam(
        team_name=payload.team_name,
        adom_name=payload.adom_name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(team)
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.TEAM_CREATED,
        entity_id=team.id,
        actor_user_id=current_user.id,
        team_id=team.id,
        policy_relevant_fields=("adom_name", "is_active"),
    )
    try:
        await session.flush()
        await stage_identity_mutation(authorization_service, session, mutation)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        await _audit_deny(
            user_id=current_user.id,
            action="team:create",
            obj="team:*",
            status_code=status.HTTP_409_CONFLICT,
            reason="team_slug_conflict",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team with adom_name {payload.adom_name!r} already exists",
        ) from exc
    await safe_identity_mutation_committed(authorization_service, mutation)
    await session.refresh(team)
    await audit_decision(
        user_id=current_user.id,
        action="team:create",
        obj=f"team:{team.id}",
        result="allow",
        details={
            "event": AUDIT_EVENT_MUTATION,
            "team_name": team.team_name,
            "adom_name": team.adom_name,
        },
    )
    logger.info("Created team %s (id=%s)", team.team_name, team.id)
    return TeamRead.model_validate(team)


@router.patch("/{team_id}", response_model=TeamRead, dependencies=SUPERUSER_ONLY)
async def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRead:
    await _require_superuser(current_user, action="team:update", obj=f"team:{team_id}")
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.TEAM_UPDATED,
        entity_id=team_id,
    )
    team = await session.get(AuthzTeam, team_id)
    if team is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team:update",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    changed_fields: list[str] = []
    previous_adom_name = team.adom_name
    if payload.team_name is not None and team.team_name != payload.team_name:
        team.team_name = payload.team_name
        changed_fields.append("team_name")
    if payload.adom_name is not None and team.adom_name != payload.adom_name:
        team.adom_name = payload.adom_name
        changed_fields.append("adom_name")
    # description is nullable on the DB side, so use a presence check
    # (model_fields_set) instead of ``is not None`` — an explicit "description":
    # null in the body clears the field, while omitting it leaves the row alone.
    if "description" in payload.model_fields_set and team.description != payload.description:
        team.description = payload.description
        changed_fields.append("description")
    if payload.is_active is not None and team.is_active != payload.is_active:
        team.is_active = payload.is_active
        changed_fields.append("is_active")
    team.updated_at = datetime.now(timezone.utc)
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.TEAM_UPDATED,
        entity_id=team.id,
        actor_user_id=current_user.id,
        team_id=team.id,
        policy_relevant_fields=tuple(sorted(set(changed_fields) & {"adom_name", "is_active"})),
        previous_identifier=previous_adom_name if team.adom_name != previous_adom_name else None,
    )
    try:
        await session.flush()
        await stage_identity_mutation(authorization_service, session, mutation)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        await _audit_deny(
            user_id=current_user.id,
            action="team:update",
            obj=f"team:{team_id}",
            status_code=status.HTTP_409_CONFLICT,
            reason="team_slug_conflict",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="adom_name conflict — another team already uses this slug",
        ) from exc
    await safe_identity_mutation_committed(authorization_service, mutation)
    await session.refresh(team)
    await audit_decision(
        user_id=current_user.id,
        action="team:update",
        obj=f"team:{team.id}",
        result="allow",
        details={
            "event": AUDIT_EVENT_MUTATION,
            "team_name": team.team_name,
            "fields_changed": sorted(changed_fields),
        },
    )
    logger.info("Updated team %s (id=%s)", team.team_name, team.id)
    return TeamRead.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=SUPERUSER_ONLY)
async def delete_team(
    team_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    await _require_superuser(current_user, action="team:delete", obj=f"team:{team_id}")
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.TEAM_DELETED,
        entity_id=team_id,
    )
    team = await session.get(AuthzTeam, team_id)
    if team is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team:delete",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    team_name = team.team_name
    await delete_all_team_role_grants(session, team_id)
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.TEAM_DELETED,
        entity_id=team_id,
        actor_user_id=current_user.id,
        team_id=team_id,
        policy_relevant_fields=("adom_name", "is_active"),
        previous_identifier=team.adom_name,
    )
    # Cascade on team_members handles cleanup; share rows targeting this team
    # are left in place (caller may want to migrate them before deleting).
    await session.delete(team)
    await session.flush()
    await stage_identity_mutation(authorization_service, session, mutation)
    await session.commit()
    await safe_identity_mutation_committed(authorization_service, mutation)
    await audit_decision(
        user_id=current_user.id,
        action="team:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"event": AUDIT_EVENT_MUTATION, "team_name": team_name},
    )
    logger.info("Deleted team id=%s", team_id)


# --- persistent team roles ----------------------------------------------- #


@router.get("/{team_id}/roles", response_model=list[TeamRoleAssignmentRead])
async def list_team_roles(
    team_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> list[TeamRoleAssignmentRead]:
    if await session.get(AuthzTeam, team_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    await _require_team_reader(session, team_id=team_id, current_user=current_user)
    return [_team_role_read(grant) for grant in await list_team_role_grants(session, team_id)]


@router.post(
    "/{team_id}/roles",
    response_model=TeamRoleAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=SUPERUSER_ONLY,
)
async def add_team_role(
    team_id: UUID,
    payload: TeamRoleAssignmentCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRoleAssignmentRead:
    await _require_superuser(current_user, action="team_role:create", obj=f"team:{team_id}")
    team = await session.get(AuthzTeam, team_id, with_for_update=True)
    if team is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_role:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    role = await session.get(AuthzRole, payload.role_id)
    if role is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_role:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="role_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="role_id not found")
    grant = await create_team_role_grant(
        session,
        team_id=team_id,
        role_id=payload.role_id,
        domain_type=payload.domain_type,
        domain_id=payload.domain_id,
        assigned_by=current_user.id,
    )
    await session.commit()
    await safe_invalidate_all(get_authorization_service(), op="team_role:create")
    await audit_decision(
        user_id=current_user.id,
        action="team_role:create",
        obj=f"team:{team_id}",
        result="allow",
        details={
            "event": AUDIT_EVENT_MUTATION,
            "rule_id": grant.id,
            "role_id": str(payload.role_id),
            "role_name": role.name,
            "domain_type": payload.domain_type,
            "domain_id": str(payload.domain_id) if payload.domain_id else None,
        },
    )
    return _team_role_read(grant)


@router.delete(
    "/{team_id}/roles/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=SUPERUSER_ONLY,
)
async def remove_team_role(
    team_id: UUID,
    rule_id: int,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    await _require_superuser(current_user, action="team_role:delete", obj=f"team:{team_id}")
    if await session.get(AuthzTeam, team_id, with_for_update=True) is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_role:delete",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    existing_ids = {grant.id for grant in await list_team_role_grants(session, team_id)}
    if rule_id not in existing_ids:
        await _audit_deny(
            user_id=current_user.id,
            action="team_role:delete",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_role_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team role not found")
    await delete_team_role_grant(session, team_id=team_id, rule_id=rule_id)
    await session.commit()
    await safe_invalidate_all(get_authorization_service(), op="team_role:delete")
    await audit_decision(
        user_id=current_user.id,
        action="team_role:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"event": AUDIT_EVENT_MUTATION, "rule_id": rule_id},
    )


# --- team members --------------------------------------------------------- #


@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
async def list_members(
    team_id: UUID,
    session: DbSession,
    current_user: CurrentActiveUser,  # noqa: ARG001
    limit: Annotated[int, Query(ge=1, le=_LIST_MAX_LIMIT)] = _LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TeamMemberRead]:
    """List members of a team. Any authenticated user (so the UI can render team rosters).

    Paginated via ``limit`` / ``offset`` so a single call cannot enumerate a
    large team's full roster. Stable order is ``(created_at, user_id)``.
    """
    team = await session.get(AuthzTeam, team_id)
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    stmt = (
        select(AuthzTeamMember)
        .where(AuthzTeamMember.team_id == team_id)
        .order_by(AuthzTeamMember.created_at, AuthzTeamMember.user_id)
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.exec(stmt)).all()
    return [TeamMemberRead.model_validate(row) for row in rows]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=SUPERUSER_ONLY,
)
async def add_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamMemberRead:
    await _require_superuser(current_user, action="team_member:create", obj=f"team:{team_id}")
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.TEAM_MEMBER_ADDED,
        affected_user_ids=(payload.user_id,),
    )
    team = await session.get(AuthzTeam, team_id)
    if team is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_member:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="team_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    user = await session.get(User, payload.user_id)
    if user is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_member:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="user_not_found",
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_id not found")
    if is_managed_service_user(user):
        await _audit_deny(
            user_id=current_user.id,
            action="team_member:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            reason="managed_service_identity",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Managed channel service identities cannot join RBAC teams",
        )

    member = AuthzTeamMember(
        team_id=team_id,
        user_id=payload.user_id,
        source=payload.source,
    )
    session.add(member)
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.TEAM_MEMBER_ADDED,
        entity_id=member.id,
        actor_user_id=current_user.id,
        affected_user_ids=(payload.user_id,),
        team_id=team_id,
        policy_relevant_fields=("team_id", "user_id", "source"),
    )
    try:
        await session.flush()
        await sync_team_member_grants(
            session,
            team_id=team_id,
            user_id=payload.user_id,
            assigned_by=current_user.id,
        )
        await stage_identity_mutation(authorization_service, session, mutation)
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        await _audit_deny(
            user_id=current_user.id,
            action="team_member:create",
            obj=f"team:{team_id}",
            status_code=status.HTTP_409_CONFLICT,
            reason="membership_already_exists",
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this team",
        ) from exc
    await safe_identity_mutation_committed(authorization_service, mutation)
    await session.refresh(member)
    await audit_decision(
        user_id=current_user.id,
        action="team_member:create",
        obj=f"team:{team_id}",
        result="allow",
        details={
            "event": AUDIT_EVENT_MUTATION,
            "team_name": team.team_name,
            "user_id": str(payload.user_id),
            "source": payload.source,
        },
    )
    logger.info("Added user=%s to team=%s", payload.user_id, team_id)
    return TeamMemberRead.model_validate(member)


@router.delete(
    "/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=SUPERUSER_ONLY,
)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    await _require_superuser(current_user, action="team_member:delete", obj=f"team:{team_id}")
    authorization_service = get_authorization_service()
    await acquire_identity_mutation_lock(
        authorization_service,
        session,
        kind=AuthorizationMutationKind.TEAM_MEMBER_REMOVED,
        affected_user_ids=(user_id,),
    )
    member = (
        await session.exec(
            select(AuthzTeamMember).where(
                AuthzTeamMember.team_id == team_id,
                AuthzTeamMember.user_id == user_id,
            )
        )
    ).first()
    if member is None:
        await _audit_deny(
            user_id=current_user.id,
            action="team_member:delete",
            obj=f"team:{team_id}",
            status_code=status.HTTP_404_NOT_FOUND,
            reason="membership_not_found",
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Membership not found",
        )
    mutation = AuthorizationMutation(
        kind=AuthorizationMutationKind.TEAM_MEMBER_REMOVED,
        entity_id=member.id,
        actor_user_id=current_user.id,
        affected_user_ids=(user_id,),
        team_id=team_id,
        policy_relevant_fields=("team_id", "user_id", "source"),
    )
    await remove_team_member_grants(session, team_id=team_id, user_id=user_id)
    await session.delete(member)
    await session.flush()
    await stage_identity_mutation(authorization_service, session, mutation)
    await session.commit()
    await safe_identity_mutation_committed(authorization_service, mutation)
    await audit_decision(
        user_id=current_user.id,
        action="team_member:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"event": AUDIT_EVENT_MUTATION, "user_id": str(user_id)},
    )
    logger.info("Removed user=%s from team=%s", user_id, team_id)
