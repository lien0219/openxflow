"""Idempotent bootstrap helpers for OpenXFlow's built-in RBAC catalog."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.services.database.models.auth import AuthzRole, AuthzRoleAssignment
from langflow.services.database.models.user.model import User

if TYPE_CHECKING:
    from uuid import UUID

    from sqlmodel.ext.asyncio.session import AsyncSession


@dataclass(frozen=True, slots=True)
class SystemRoleDefinition:
    name: str
    description: str
    permissions: tuple[str, ...]


SYSTEM_ROLE_DEFINITIONS: tuple[SystemRoleDefinition, ...] = (
    SystemRoleDefinition(
        name="platform_admin",
        description="Platform-wide administrator with full resource and RBAC management access.",
        permissions=(
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:*",
            "channel:*",
            "audit:*",
            "rbac:*",
            "team:*",
            "user:*",
        ),
    ),
    SystemRoleDefinition(
        name="organization_admin",
        description="Administrator for an organization or workspace scope.",
        permissions=(
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:*",
            "channel:*",
            "audit:read",
            "rbac:read",
            "rbac:assign",
            "team:*",
            "user:read",
        ),
    ),
    SystemRoleDefinition(
        name="channel_admin",
        description="Administrator for one channel connection and its conversations.",
        permissions=(
            "channel:*",
            "audit:read",
            "flow:read",
            "flow:execute",
            "knowledge_base:read",
            "rbac:read",
            "rbac:assign",
            "user:read",
        ),
    ),
    SystemRoleDefinition(
        name="resource_editor",
        description="Create and maintain workflows, projects, files and knowledge bases.",
        permissions=(
            "flow:*",
            "deployment:*",
            "project:*",
            "knowledge_base:*",
            "variable:*",
            "file:*",
            "share:read",
            "share:create",
            "share:update",
        ),
    ),
    SystemRoleDefinition(
        name="viewer",
        description="Read and execute shared resources without editing them.",
        permissions=(
            "flow:read",
            "flow:execute",
            "deployment:read",
            "project:read",
            "knowledge_base:read",
            "variable:read",
            "file:read",
            "share:read",
            "channel:read",
        ),
    ),
    SystemRoleDefinition(
        name="auditor",
        description="Read-only access to resource metadata, channel activity and audit records.",
        permissions=(
            "audit:read",
            "channel:read",
            "channel:audit",
            "flow:read",
            "deployment:read",
            "project:read",
        ),
    ),
    SystemRoleDefinition(
        name="member",
        description="Default authenticated member. Access is granted through ownership or explicit sharing.",
        permissions=(),
    ),
)

_SYSTEM_ROLE_BY_NAME = {role.name: role for role in SYSTEM_ROLE_DEFINITIONS}
_BOOTSTRAP_LOCK = asyncio.Lock()
_MAX_INHERITANCE_DEPTH = 32
_MAX_ROLE_GRAPH_SIZE = 1024


def is_managed_service_user(user: User) -> bool:
    optins = user.optins if isinstance(user.optins, dict) else {}
    return bool(optins.get("channel_service_identity"))


async def ensure_builtin_roles(session: AsyncSession) -> dict[str, AuthzRole]:
    """Create or reconcile immutable system roles and return them by name."""
    async with _BOOTSTRAP_LOCK:
        existing = (await session.exec(select(AuthzRole))).all()
        by_name = {role.name.strip().lower(): role for role in existing}
        changed = False

        for definition in SYSTEM_ROLE_DEFINITIONS:
            role = by_name.get(definition.name)
            permissions = list(definition.permissions)
            if role is None:
                role = AuthzRole(
                    name=definition.name,
                    description=definition.description,
                    is_system=True,
                    permissions=permissions,
                )
                session.add(role)
                by_name[definition.name] = role
                changed = True
                continue

            if not role.is_system:
                # Names in the built-in catalog are reserved. A legacy bootstrap
                # row has no creator and may be safely upgraded; a user-created
                # collision must fail closed rather than silently gaining system
                # role semantics.
                if role.created_by is not None:
                    message = f"Custom role {role.name!r} conflicts with a reserved system role name"
                    raise RuntimeError(message)
                role.is_system = True
                changed = True
            if role.description != definition.description:
                role.description = definition.description
                changed = True
            if list(role.permissions or []) != permissions:
                role.permissions = permissions
                changed = True

        if changed:
            try:
                await session.commit()
            except IntegrityError:
                # A second worker may have inserted the same deterministic catalog.
                await session.rollback()
                existing = (await session.exec(select(AuthzRole))).all()
                by_name = {role.name.strip().lower(): role for role in existing}
            else:
                existing = (await session.exec(select(AuthzRole))).all()
                by_name = {role.name.strip().lower(): role for role in existing}

        missing = set(_SYSTEM_ROLE_BY_NAME) - set(by_name)
        if missing:
            message = f"RBAC system role bootstrap incomplete: {sorted(missing)}"
            raise RuntimeError(message)
        return {name: by_name[name] for name in _SYSTEM_ROLE_BY_NAME}


async def ensure_user_default_role(
    session: AsyncSession,
    user: User,
    *,
    roles: dict[str, AuthzRole] | None = None,
    commit: bool = True,
) -> AuthzRoleAssignment | None:
    """Reconcile safe bootstrap assignments for one human user.

    Bootstrap-created assignments use ``assigned_by=None``. This lets a later
    superuser demotion remove only the automatic platform-admin grant while
    preserving explicit administrator assignments created by another operator.
    """
    if not user.is_active or is_managed_service_user(user):
        return None

    roles = roles or await ensure_builtin_roles(session)
    platform_role = roles["platform_admin"]
    member_role = roles["member"]
    existing_assignments = (
        await session.exec(select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user.id))
    ).all()

    automatic_platform = next(
        (
            assignment
            for assignment in existing_assignments
            if assignment.role_id == platform_role.id
            and assignment.domain_type == "global"
            and assignment.domain_id is None
            and assignment.assigned_by is None
        ),
        None,
    )
    automatic_member = next(
        (
            assignment
            for assignment in existing_assignments
            if assignment.role_id == member_role.id
            and assignment.domain_type == "global"
            and assignment.domain_id is None
            and assignment.assigned_by is None
        ),
        None,
    )

    changed = False
    result: AuthzRoleAssignment | None
    if user.is_superuser:
        result = automatic_platform
        if result is None:
            result = AuthzRoleAssignment(
                user_id=user.id,
                role_id=platform_role.id,
                domain_type="global",
                domain_id=None,
                assigned_by=None,
            )
            session.add(result)
            changed = True
        if automatic_member is not None:
            await session.delete(automatic_member)
            changed = True
    else:
        if automatic_platform is not None:
            await session.delete(automatic_platform)
            changed = True
        result = automatic_member
        if result is None:
            result = AuthzRoleAssignment(
                user_id=user.id,
                role_id=member_role.id,
                domain_type="global",
                domain_id=None,
                assigned_by=None,
            )
            session.add(result)
            changed = True

    if changed and commit:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            desired_role_id = platform_role.id if user.is_superuser else member_role.id
            result = (
                await session.exec(
                    select(AuthzRoleAssignment).where(
                        AuthzRoleAssignment.user_id == user.id,
                        AuthzRoleAssignment.role_id == desired_role_id,
                        AuthzRoleAssignment.domain_type == "global",
                        AuthzRoleAssignment.domain_id.is_(None),
                    )
                )
            ).first()
        else:
            if result is not None:
                await session.refresh(result)
    return result


async def ensure_authorization_bootstrap(session: AsyncSession) -> dict[str, AuthzRole]:
    """Reconcile the catalog and default assignments in one bounded transaction."""
    roles = await ensure_builtin_roles(session)
    users = (await session.exec(select(User).where(User.is_active.is_(True)))).all()
    for user in users:
        await ensure_user_default_role(session, user, roles=roles, commit=False)
    try:
        await session.commit()
    except IntegrityError:
        # Concurrent workers can race on a previously missing default grant.
        # Roll back and let the next idempotent call observe the winning rows.
        await session.rollback()
    logger.debug("RBAC bootstrap reconciled %d system roles and %d active users", len(roles), len(users))
    return roles


async def resolve_role_permissions(session: AsyncSession, role_ids: set[UUID]) -> set[str]:
    """Return direct and inherited permissions for a role set."""
    if not role_ids:
        return set()
    roles = (await session.exec(select(AuthzRole).where(AuthzRole.id.in_(role_ids)))).all()
    by_id = {role.id: role for role in roles}

    pending = {
        role.parent_role_id for role in roles if role.parent_role_id is not None and role.parent_role_id not in by_id
    }
    while pending and len(by_id) < _MAX_ROLE_GRAPH_SIZE:
        parents = (await session.exec(select(AuthzRole).where(AuthzRole.id.in_(pending)))).all()
        if not parents:
            break
        by_id.update({role.id: role for role in parents})
        pending = {
            role.parent_role_id
            for role in parents
            if role.parent_role_id is not None and role.parent_role_id not in by_id
        }

    permissions: set[str] = set()
    visited: set[UUID] = set()

    def collect(role: AuthzRole | None, depth: int = 0) -> None:
        if role is None or depth > _MAX_INHERITANCE_DEPTH or role.id in visited:
            return
        visited.add(role.id)
        permissions.update(str(item).strip().lower() for item in (role.permissions or []) if item)
        collect(by_id.get(role.parent_role_id), depth + 1)

    for role_id in role_ids:
        collect(by_id.get(role_id))
    return permissions


__all__ = [
    "SYSTEM_ROLE_DEFINITIONS",
    "ensure_authorization_bootstrap",
    "ensure_builtin_roles",
    "ensure_user_default_role",
    "is_managed_service_user",
    "resolve_role_permissions",
]
