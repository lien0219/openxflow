"""Effective-permission, status and identity summary endpoints for RBAC clients."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.authorization.bootstrap import (
    SYSTEM_ROLE_DEFINITIONS,
    ensure_authorization_bootstrap,
    resolve_role_permissions,
)
from langflow.services.database.models.auth import AuthzRole, AuthzRoleAssignment, AuthzTeam, AuthzTeamMember
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_authorization_service, get_settings_service

router = APIRouter(prefix="/authz/me", tags=["Authorization"])

ResourceTypeLiteral = Literal[
    "flow",
    "deployment",
    "project",
    "knowledge_base",
    "variable",
    "file",
    "component",
    "channel",
]

_DEFAULT_ACTIONS: tuple[str, ...] = ("read", "write", "execute", "delete", "create")
_MAX_RESOURCE_IDS = 500
_MAX_ACTIONS = 10
_ALLOWED_SUMMARY_DOMAINS = {"global", "organization", "org", "workspace", "project", "channel"}


def _summary_domain_context(domain_type: str, domain_id: UUID | None) -> tuple[str, dict[str, UUID]]:
    normalized = domain_type.strip().lower()
    if normalized not in _ALLOWED_SUMMARY_DOMAINS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown domain type")
    if normalized == "global":
        if domain_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="global summaries must not include domain_id",
            )
        return "*", {}
    if domain_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{normalized} summaries require domain_id",
        )
    context_keys = {
        "organization": "organization_id",
        "org": "organization_id",
        "workspace": "workspace_id",
        "project": "project_id",
        "channel": "connection_id",
    }
    return f"{normalized}:{domain_id}", {context_keys[normalized]: domain_id}


class EffectivePermissionsRequest(BaseModel):
    """Body for :func:`get_effective_permissions`."""

    resource_type: ResourceTypeLiteral
    resource_ids: list[UUID] = Field(..., description="Resource IDs to evaluate. Capped at 500 per request.")
    actions: list[str] | None = Field(
        default=None,
        description=f"Actions to check. Normalized and capped at {_MAX_ACTIONS}.",
    )
    domain: str = Field(
        default="*",
        description="Authorization domain, for example project:<id>, workspace:<id>, or channel:<id>.",
    )

    @field_validator("actions")
    @classmethod
    def _normalize_actions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        seen: set[str] = set()
        normalized: list[str] = []
        for raw in value:
            cleaned = raw.strip().lower()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            normalized.append(cleaned)
        if len(normalized) > _MAX_ACTIONS:
            message = f"actions capped at {_MAX_ACTIONS} unique entries"
            raise ValueError(message)
        return normalized or None


class EffectivePermissionsResponse(BaseModel):
    """Response mapping each resource ID to allowed actions."""

    resource_type: ResourceTypeLiteral
    permissions: dict[UUID, list[str]]


class RbacStatusResponse(BaseModel):
    authz_enabled: bool
    audit_enabled: bool
    superuser_bypass: bool
    auto_login: bool
    is_superuser: bool
    production_ready: bool
    warnings: list[str]


class AssignmentSummary(BaseModel):
    id: UUID
    role_id: UUID
    role_name: str
    domain_type: str
    domain_id: UUID | None
    assigned_at: str
    assigned_by: UUID | None


class TeamSummary(BaseModel):
    id: UUID
    team_name: str
    adom_name: str
    source: str


class RbacIdentitySummaryResponse(BaseModel):
    user_id: UUID
    username: str
    is_active: bool
    is_superuser: bool
    assignments: list[AssignmentSummary]
    teams: list[TeamSummary]
    effective_permissions: list[str]
    permission_catalog: list[str]


@router.get("/status", response_model=RbacStatusResponse)
async def get_rbac_status(
    current_user: CurrentActiveUser,
    session: DbSession,
) -> RbacStatusResponse:
    await ensure_authorization_bootstrap(session)
    auth_settings = get_settings_service().auth_settings
    warnings: list[str] = []
    if auth_settings.AUTO_LOGIN:
        warnings.append("AUTO_LOGIN is enabled; disable it before using multi-user RBAC in production.")
    if not auth_settings.AUTHZ_ENABLED:
        warnings.append("RBAC enforcement is disabled; role decisions are not currently blocking requests.")
    if not auth_settings.AUTHZ_AUDIT_ENABLED:
        warnings.append("Authorization audit logging is disabled.")
    return RbacStatusResponse(
        authz_enabled=bool(auth_settings.AUTHZ_ENABLED),
        audit_enabled=bool(auth_settings.AUTHZ_AUDIT_ENABLED),
        superuser_bypass=bool(auth_settings.AUTHZ_SUPERUSER_BYPASS),
        auto_login=bool(auth_settings.AUTO_LOGIN),
        is_superuser=bool(current_user.is_superuser),
        production_ready=bool(
            not auth_settings.AUTO_LOGIN and auth_settings.AUTHZ_ENABLED and auth_settings.AUTHZ_AUDIT_ENABLED
        ),
        warnings=warnings,
    )


@router.get("/summary", response_model=RbacIdentitySummaryResponse)
async def get_rbac_identity_summary(
    current_user: CurrentActiveUser,
    session: DbSession,
    user_id: UUID | None = Query(default=None),
    domain_type: str | None = Query(default=None),
    domain_id: UUID | None = Query(default=None),
) -> RbacIdentitySummaryResponse:
    await ensure_authorization_bootstrap(session)
    target_user_id = user_id or current_user.id
    cross_user_scoped = target_user_id != current_user.id and not current_user.is_superuser

    normalized_domain_type: str | None = None
    if cross_user_scoped:
        if domain_type is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A scoped domain is required to inspect another user's permissions.",
            )
        normalized_domain_type = domain_type.strip().lower()
        domain, context = _summary_domain_context(normalized_domain_type, domain_id)
        authz = get_authorization_service()
        if not await authz.is_enabled() or not await authz.enforce(
            user_id=current_user.id,
            domain=domain,
            obj="rbac:*",
            act="read",
            context=context,
        ):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")

    target_user = await session.get(User, target_user_id)
    if target_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    assignment_stmt = select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == target_user_id)
    if cross_user_scoped and normalized_domain_type is not None:
        assignment_stmt = assignment_stmt.where(AuthzRoleAssignment.domain_type == normalized_domain_type)
        if normalized_domain_type == "global":
            assignment_stmt = assignment_stmt.where(AuthzRoleAssignment.domain_id.is_(None))
        else:
            assignment_stmt = assignment_stmt.where(AuthzRoleAssignment.domain_id == domain_id)
    assignments = (
        await session.exec(assignment_stmt.order_by(AuthzRoleAssignment.assigned_at.desc(), AuthzRoleAssignment.id))
    ).all()

    role_ids = {assignment.role_id for assignment in assignments}
    roles = (await session.exec(select(AuthzRole).where(AuthzRole.id.in_(role_ids)))).all() if role_ids else []
    roles_by_id = {role.id: role for role in roles}

    memberships = []
    if not cross_user_scoped:
        memberships = (
            await session.exec(
                select(AuthzTeamMember, AuthzTeam)
                .join(AuthzTeam, AuthzTeam.id == AuthzTeamMember.team_id)
                .where(AuthzTeamMember.user_id == target_user_id, AuthzTeam.is_active.is_(True))
                .order_by(AuthzTeam.team_name, AuthzTeam.id)
            )
        ).all()

    effective_permissions = await resolve_role_permissions(session, role_ids)
    permission_catalog = sorted(
        {permission for definition in SYSTEM_ROLE_DEFINITIONS for permission in definition.permissions}
        | effective_permissions
    )
    return RbacIdentitySummaryResponse(
        user_id=target_user.id,
        username=target_user.username,
        is_active=target_user.is_active,
        is_superuser=target_user.is_superuser,
        assignments=[
            AssignmentSummary(
                id=assignment.id,
                role_id=assignment.role_id,
                role_name=roles_by_id.get(assignment.role_id).name
                if roles_by_id.get(assignment.role_id)
                else "unknown",
                domain_type=assignment.domain_type,
                domain_id=assignment.domain_id,
                assigned_at=assignment.assigned_at.isoformat(),
                assigned_by=assignment.assigned_by,
            )
            for assignment in assignments
        ],
        teams=[
            TeamSummary(
                id=team.id,
                team_name=team.team_name,
                adom_name=team.adom_name,
                source=membership.source,
            )
            for membership, team in memberships
        ],
        effective_permissions=sorted(effective_permissions),
        permission_catalog=permission_catalog,
    )


@router.post("/permissions", response_model=EffectivePermissionsResponse)
async def get_effective_permissions(
    body: EffectivePermissionsRequest,
    current_user: CurrentActiveUser,
) -> EffectivePermissionsResponse:
    if not body.resource_ids:
        return EffectivePermissionsResponse(resource_type=body.resource_type, permissions={})
    if len(body.resource_ids) > _MAX_RESOURCE_IDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"resource_ids capped at {_MAX_RESOURCE_IDS}",
        )

    authz = get_authorization_service()
    actions = tuple(body.actions) if body.actions else _DEFAULT_ACTIONS
    permissions = await authz.get_effective_permissions(
        user_id=current_user.id,
        resource_type=body.resource_type,
        resource_ids=body.resource_ids,
        actions=actions,
        domain=body.domain,
        context={"is_superuser": getattr(current_user, "is_superuser", False)},
    )
    return EffectivePermissionsResponse(
        resource_type=body.resource_type,
        permissions=permissions,
    )
