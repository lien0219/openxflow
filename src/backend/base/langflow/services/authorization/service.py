"""Built-in production RBAC authorization service for OpenXFlow."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from lfx.log.logger import logger
from lfx.services.authorization.base import BaseAuthorizationService
from lfx.services.schema import ServiceType
from sqlmodel import select

from langflow.services.database.models.auth import (
    AuthzRole,
    AuthzRoleAssignment,
    AuthzShare,
    AuthzTeam,
    AuthzTeamMember,
    SharePermissionLevel,
    ShareScope,
)
from langflow.services.database.models.user.model import User

if TYPE_CHECKING:
    from collections.abc import Sequence

    from lfx.services.settings.auth import AuthSettings
    from lfx.services.settings.service import SettingsService
    from sqlmodel.ext.asyncio.session import AsyncSession


_BUILTIN_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "platform_admin": frozenset(
        {
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:*",
            "channel:*",
            "audit:*",
        }
    ),
    "organization_admin": frozenset(
        {
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:*",
            "channel:*",
            "audit:read",
        }
    ),
    "channel_admin": frozenset(
        {
            "channel:*",
            "audit:read",
            "flow:read",
            "flow:execute",
            "knowledge_base:read",
        }
    ),
    "resource_editor": frozenset(
        {
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:read",
            "share:create",
            "share:update",
        }
    ),
    "editor": frozenset(
        {
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:read",
            "share:create",
            "share:update",
        }
    ),
    "viewer": frozenset(
        {
            "flow:read",
            "flow:execute",
            "deployment:read",
            "project:read",
            "knowledge_base:read",
            "variable:read",
            "file:read",
            "share:read",
            "channel:read",
        }
    ),
    "auditor": frozenset(
        {
            "audit:read",
            "channel:read",
            "channel:audit",
            "flow:read",
            "deployment:read",
            "project:read",
        }
    ),
    "member": frozenset(),
}

_MAX_ROLE_GRAPH_SIZE = 1024
_MAX_ROLE_INHERITANCE_DEPTH = 32


_SHARE_LEVEL_ACTIONS: dict[str, frozenset[str]] = {
    SharePermissionLevel.READ.value: frozenset({"read"}),
    SharePermissionLevel.EXECUTE.value: frozenset({"read", "execute"}),
    SharePermissionLevel.WRITE.value: frozenset({"read", "write", "create", "ingest", "execute"}),
    SharePermissionLevel.ADMIN.value: frozenset({"*"}),
}


class LangflowAuthorizationService(BaseAuthorizationService):
    """Database-backed RBAC for roles, scoped assignments, teams and shares.

    Resource-owner shortcuts remain in the route guards. This service evaluates
    non-owner access. With ``AUTHZ_ENABLED=false`` it preserves legacy behaviour;
    with enforcement enabled it fails closed unless a role/share grants access.
    """

    SUPPORTS_CROSS_USER_FETCH: ClassVar[bool] = True

    def __init__(self, settings_service: SettingsService) -> None:
        super().__init__()
        self.settings_service = settings_service
        self.set_ready()
        logger.debug("OpenXFlow built-in RBAC authorization service initialized")

    @property
    def name(self) -> str:
        return ServiceType.AUTHORIZATION_SERVICE.value

    def _authz_settings(self) -> AuthSettings:
        return self.settings_service.auth_settings

    async def is_enabled(self) -> bool:
        return bool(self._authz_settings().AUTHZ_ENABLED)

    def _superuser_bypass_enabled(self) -> bool:
        return bool(self._authz_settings().AUTHZ_SUPERUSER_BYPASS)

    @staticmethod
    def _domain_matches(
        assignment: AuthzRoleAssignment,
        *,
        domain: str,
        context: dict[str, Any],
    ) -> bool:
        domain_type = str(assignment.domain_type or "global").strip().lower()
        if domain_type == "global":
            return True
        if assignment.domain_id is None:
            return False
        assignment_id = str(assignment.domain_id)
        if domain == f"{domain_type}:{assignment_id}":
            return True

        aliases: dict[str, tuple[str, ...]] = {
            "workspace": ("workspace_id",),
            "project": ("project_id", "folder_id"),
            "channel": ("channel_connection_id", "connection_id"),
            "organization": ("organization_id", "org_id"),
            "org": ("organization_id", "org_id"),
        }
        return any(
            context.get(key) is not None and str(context.get(key)) == assignment_id
            for key in aliases.get(domain_type, ())
        )

    @staticmethod
    async def _role_permissions(
        session: AsyncSession,
        assignments: Sequence[AuthzRoleAssignment],
    ) -> set[str]:
        role_ids = {assignment.role_id for assignment in assignments}
        if not role_ids:
            return set()
        roles = (await session.exec(select(AuthzRole).where(AuthzRole.id.in_(role_ids)))).all()
        by_id = {role.id: role for role in roles}

        pending_parent_ids = {
            role.parent_role_id
            for role in roles
            if role.parent_role_id is not None and role.parent_role_id not in by_id
        }
        while pending_parent_ids and len(by_id) < _MAX_ROLE_GRAPH_SIZE:
            parents = (await session.exec(select(AuthzRole).where(AuthzRole.id.in_(pending_parent_ids)))).all()
            if not parents:
                break
            by_id.update({role.id: role for role in parents})
            pending_parent_ids = {
                role.parent_role_id
                for role in parents
                if role.parent_role_id is not None and role.parent_role_id not in by_id
            }

        permissions: set[str] = set()
        visited: set[UUID] = set()

        def collect(role: AuthzRole | None, *, depth: int = 0) -> None:
            if role is None or depth > _MAX_ROLE_INHERITANCE_DEPTH or role.id in visited:
                return
            visited.add(role.id)
            permissions.update(str(item).strip().lower() for item in (role.permissions or []) if item)
            permissions.update(_BUILTIN_ROLE_PERMISSIONS.get(role.name.strip().lower(), frozenset()))
            collect(by_id.get(role.parent_role_id), depth=depth + 1)

        for assignment in assignments:
            collect(by_id.get(assignment.role_id))
        return permissions

    @staticmethod
    def _permission_matches(permissions: set[str], *, resource_type: str, act: str) -> bool:
        normalized_action = act.strip().lower()
        return f"{resource_type}:{normalized_action}" in permissions or f"{resource_type}:*" in permissions

    @staticmethod
    async def _team_ids(session: AsyncSession, user_id: UUID) -> set[UUID]:
        rows = (
            await session.exec(
                select(AuthzTeamMember.team_id)
                .join(AuthzTeam, AuthzTeam.id == AuthzTeamMember.team_id)
                .where(AuthzTeamMember.user_id == user_id, AuthzTeam.is_active.is_(True))
            )
        ).all()
        return set(rows)

    @staticmethod
    def _share_targets_user(share: AuthzShare, *, user_id: UUID, team_ids: set[UUID]) -> bool:
        return (
            share.scope == ShareScope.PUBLIC.value
            or (share.scope == ShareScope.USER.value and share.target_id == user_id)
            or (share.scope == ShareScope.TEAM.value and share.target_id in team_ids)
        )

    @staticmethod
    def _share_level_allows(permission_level: str, act: str) -> bool:
        allowed_actions = _SHARE_LEVEL_ACTIONS.get(permission_level, frozenset())
        normalized_action = act.strip().lower()
        return "*" in allowed_actions or normalized_action in allowed_actions

    async def _load_principal_permissions(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        domain: str,
        context: dict[str, Any],
    ) -> tuple[User | None, set[str], set[UUID]]:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            return user, set(), set()
        assignments = (
            await session.exec(select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id))
        ).all()
        matching = [
            assignment for assignment in assignments if self._domain_matches(assignment, domain=domain, context=context)
        ]
        permissions = await self._role_permissions(session, matching)
        team_ids = await self._team_ids(session, user_id)
        return user, permissions, team_ids

    async def _share_allows(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        team_ids: set[UUID],
        resource_type: str,
        resource_id: UUID | None,
        act: str,
        prefetched: dict[tuple[str, UUID], list[AuthzShare]] | None = None,
    ) -> bool:
        if resource_id is None:
            return False
        if prefetched is None:
            shares = (
                await session.exec(
                    select(AuthzShare).where(
                        AuthzShare.resource_type == resource_type,
                        AuthzShare.resource_id == resource_id,
                    )
                )
            ).all()
        else:
            shares = prefetched.get((resource_type, resource_id), [])
        return any(
            self._share_targets_user(share, user_id=user_id, team_ids=team_ids)
            and self._share_level_allows(share.permission_level, act)
            for share in shares
        )

    @staticmethod
    async def _prefetch_shares(
        session: AsyncSession,
        requests: Sequence[tuple[str, str]],
    ) -> dict[tuple[str, UUID], list[AuthzShare]]:
        resources: dict[str, set[UUID]] = {}
        for obj, _ in requests:
            resource_type, separator, raw_resource_id = obj.partition(":")
            resource_type = resource_type.strip().lower()
            if not separator or not resource_type or not raw_resource_id or raw_resource_id == "*":
                continue
            try:
                resource_id = UUID(raw_resource_id)
            except ValueError:
                continue
            resources.setdefault(resource_type, set()).add(resource_id)

        prefetched: dict[tuple[str, UUID], list[AuthzShare]] = {}
        for resource_type, resource_ids in resources.items():
            rows = (
                await session.exec(
                    select(AuthzShare).where(
                        AuthzShare.resource_type == resource_type,
                        AuthzShare.resource_id.in_(resource_ids),
                    )
                )
            ).all()
            for row in rows:
                prefetched.setdefault((resource_type, row.resource_id), []).append(row)
        return prefetched

    async def _enforce_with_principal(
        self,
        session: AsyncSession,
        *,
        user: User | None,
        user_id: UUID,
        permissions: set[str],
        team_ids: set[UUID],
        obj: str,
        act: str,
        context: dict[str, Any],
        prefetched_shares: dict[tuple[str, UUID], list[AuthzShare]] | None = None,
    ) -> bool:
        if user is None or not user.is_active:
            return False
        if self._superuser_bypass_enabled() and (user.is_superuser or bool(context.get("is_superuser"))):
            return True

        resource_type, separator, raw_resource_id = obj.partition(":")
        resource_type = resource_type.strip().lower()
        if not separator or not resource_type:
            return False
        try:
            resource_id = UUID(raw_resource_id) if raw_resource_id and raw_resource_id != "*" else None
        except ValueError:
            resource_id = None

        if self._permission_matches(permissions, resource_type=resource_type, act=act):
            return True
        return await self._share_allows(
            session,
            user_id=user_id,
            team_ids=team_ids,
            resource_type=resource_type,
            resource_id=resource_id,
            act=act,
            prefetched=prefetched_shares,
        )

    async def enforce(
        self,
        *,
        user_id: UUID,
        domain: str,
        obj: str,
        act: str,
        context: dict[str, Any] | None = None,
    ) -> bool:
        if not await self.is_enabled():
            return True
        from langflow.services.deps import session_scope

        request_context = dict(context or {})
        async with session_scope() as session:
            user, permissions, team_ids = await self._load_principal_permissions(
                session,
                user_id=user_id,
                domain=domain,
                context=request_context,
            )
            return await self._enforce_with_principal(
                session,
                user=user,
                user_id=user_id,
                permissions=permissions,
                team_ids=team_ids,
                obj=obj,
                act=act,
                context=request_context,
            )

    async def batch_enforce(
        self,
        *,
        user_id: UUID,
        domain: str,
        requests: Sequence[tuple[str, str]],
        context: dict[str, Any] | None = None,
    ) -> list[bool]:
        if not requests:
            return []
        if not await self.is_enabled():
            return [True] * len(requests)
        from langflow.services.deps import session_scope

        request_context = dict(context or {})
        async with session_scope() as session:
            user, permissions, team_ids = await self._load_principal_permissions(
                session,
                user_id=user_id,
                domain=domain,
                context=request_context,
            )
            prefetched_shares = await self._prefetch_shares(session, requests)
            return [
                await self._enforce_with_principal(
                    session,
                    user=user,
                    user_id=user_id,
                    permissions=permissions,
                    team_ids=team_ids,
                    obj=obj,
                    act=act,
                    context=request_context,
                    prefetched_shares=prefetched_shares,
                )
                for obj, act in requests
            ]

    async def list_visible_resource_ids(
        self,
        *,
        user_id: UUID,
        resource_type: str,
        domain: str = "*",
        act: str = "read",
        context: dict[str, Any] | None = None,
    ) -> list[UUID] | None:
        """Return shared IDs, or ``None`` when a role grants the whole resource type."""
        if not await self.is_enabled():
            return None
        from langflow.services.deps import session_scope

        request_context = dict(context or {})
        async with session_scope() as session:
            user, permissions, team_ids = await self._load_principal_permissions(
                session,
                user_id=user_id,
                domain=domain,
                context=request_context,
            )
            if user is None or not user.is_active:
                return []
            if self._superuser_bypass_enabled() and user.is_superuser:
                return None
            normalized_resource = resource_type.strip().lower()
            if self._permission_matches(permissions, resource_type=normalized_resource, act=act):
                return None

            shares = (
                await session.exec(select(AuthzShare).where(AuthzShare.resource_type == normalized_resource))
            ).all()
            return list(
                {
                    share.resource_id
                    for share in shares
                    if self._share_targets_user(share, user_id=user_id, team_ids=team_ids)
                    and self._share_level_allows(share.permission_level, act)
                }
            )
