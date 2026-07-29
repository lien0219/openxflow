"""Persistent team-role grants backed by the existing Casbin policy table.

Team grants are materialized into ordinary ``AuthzRoleAssignment`` rows so the
hot authorization path remains unchanged. Auxiliary policy rows track which
materialized assignments were created by the team subsystem, allowing safe
reference-counted cleanup when multiple teams grant the same role/scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.services.database.models.auth import (
    AuthzRoleAssignment,
    AuthzTeamMember,
    CasbinRule,
)

TEAM_ROLE_PTYPE = "g_team_role"
TEAM_ROLE_MEMBER_PTYPE = "g_team_role_member"
TEAM_ROLE_ORIGIN_PTYPE = "g_team_role_origin"
_ORIGIN_MANAGED = "managed"
_ORIGIN_EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class TeamRoleGrant:
    id: int
    team_id: UUID
    role_id: UUID
    domain_type: str
    domain_id: UUID | None
    assigned_by: UUID | None


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except (TypeError, ValueError):
        return None


def _parse_team_role(rule: CasbinRule) -> TeamRoleGrant | None:
    if rule.id is None:
        return None
    team_id = _uuid_or_none(rule.v0)
    role_id = _uuid_or_none(rule.v1)
    if team_id is None or role_id is None or not rule.v2:
        return None
    return TeamRoleGrant(
        id=rule.id,
        team_id=team_id,
        role_id=role_id,
        domain_type=rule.v2,
        domain_id=_uuid_or_none(rule.v3),
        assigned_by=_uuid_or_none(rule.v4),
    )


async def list_team_role_grants(session: AsyncSession, team_id: UUID) -> list[TeamRoleGrant]:
    rows = (
        await session.exec(
            select(CasbinRule)
            .where(CasbinRule.ptype == TEAM_ROLE_PTYPE, CasbinRule.v0 == str(team_id))
            .order_by(CasbinRule.id)
        )
    ).all()
    return [grant for row in rows if (grant := _parse_team_role(row)) is not None]


async def _find_assignment(
    session: AsyncSession,
    *,
    user_id: UUID,
    role_id: UUID,
    domain_type: str,
    domain_id: UUID | None,
) -> AuthzRoleAssignment | None:
    stmt = select(AuthzRoleAssignment).where(
        AuthzRoleAssignment.user_id == user_id,
        AuthzRoleAssignment.role_id == role_id,
        AuthzRoleAssignment.domain_type == domain_type,
    )
    stmt = (
        stmt.where(AuthzRoleAssignment.domain_id.is_(None))
        if domain_id is None
        else stmt.where(AuthzRoleAssignment.domain_id == domain_id)
    )
    return (await session.exec(stmt)).first()


async def _ensure_origin(
    session: AsyncSession,
    *,
    assignment_id: UUID,
    managed: bool,
) -> CasbinRule:
    origin = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_ORIGIN_PTYPE,
                CasbinRule.v0 == str(assignment_id),
            )
        )
    ).first()
    if origin is not None:
        return origin
    origin = CasbinRule(
        ptype=TEAM_ROLE_ORIGIN_PTYPE,
        v0=str(assignment_id),
        v1=_ORIGIN_MANAGED if managed else _ORIGIN_EXTERNAL,
    )
    try:
        async with session.begin_nested():
            session.add(origin)
            await session.flush()
    except IntegrityError:
        origin = (
            await session.exec(
                select(CasbinRule).where(
                    CasbinRule.ptype == TEAM_ROLE_ORIGIN_PTYPE,
                    CasbinRule.v0 == str(assignment_id),
                )
            )
        ).first()
        if origin is None:
            raise
    return origin


async def _cleanup_assignment_if_unreferenced(
    session: AsyncSession,
    assignment_id: UUID,
) -> None:
    remaining_mapping = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_MEMBER_PTYPE,
                CasbinRule.v2 == str(assignment_id),
            )
        )
    ).first()
    if remaining_mapping is not None:
        return

    origin = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_ORIGIN_PTYPE,
                CasbinRule.v0 == str(assignment_id),
            )
        )
    ).first()
    if origin is not None and origin.v1 == _ORIGIN_MANAGED:
        assignment = await session.get(AuthzRoleAssignment, assignment_id)
        if assignment is not None:
            await session.delete(assignment)
    if origin is not None:
        await session.delete(origin)


async def _sync_grant_for_user(
    session: AsyncSession,
    *,
    grant: TeamRoleGrant,
    user_id: UUID,
    assigned_by: UUID | None,
) -> UUID:
    existing_mapping = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_MEMBER_PTYPE,
                CasbinRule.v0 == str(grant.id),
                CasbinRule.v1 == str(user_id),
            )
        )
    ).first()
    if existing_mapping is not None:
        assignment_id = _uuid_or_none(existing_mapping.v2)
        if assignment_id is not None and await session.get(AuthzRoleAssignment, assignment_id) is not None:
            return assignment_id
        await session.delete(existing_mapping)
        await session.flush()
        if assignment_id is not None:
            await _cleanup_assignment_if_unreferenced(session, assignment_id)

    assignment = await _find_assignment(
        session,
        user_id=user_id,
        role_id=grant.role_id,
        domain_type=grant.domain_type,
        domain_id=grant.domain_id,
    )
    managed = assignment is None
    if assignment is None:
        assignment = AuthzRoleAssignment(
            user_id=user_id,
            role_id=grant.role_id,
            domain_type=grant.domain_type,
            domain_id=grant.domain_id,
            assigned_by=assigned_by,
        )
        try:
            async with session.begin_nested():
                session.add(assignment)
                await session.flush()
        except IntegrityError:
            assignment = await _find_assignment(
                session,
                user_id=user_id,
                role_id=grant.role_id,
                domain_type=grant.domain_type,
                domain_id=grant.domain_id,
            )
            if assignment is None:
                raise
            managed = False

    await _ensure_origin(session, assignment_id=assignment.id, managed=managed)
    mapping = CasbinRule(
        ptype=TEAM_ROLE_MEMBER_PTYPE,
        v0=str(grant.id),
        v1=str(user_id),
        v2=str(assignment.id),
    )
    try:
        async with session.begin_nested():
            session.add(mapping)
            await session.flush()
    except IntegrityError:
        # The Casbin table has no composite unique constraint in older schemas;
        # an explicit pre-check above makes duplicates unlikely. A concurrent
        # duplicate is harmless because cleanup is reference-counted by rows.
        pass
    return assignment.id


async def create_team_role_grant(
    session: AsyncSession,
    *,
    team_id: UUID,
    role_id: UUID,
    domain_type: str,
    domain_id: UUID | None,
    assigned_by: UUID | None,
) -> TeamRoleGrant:
    normalized_domain = domain_type.strip().lower()
    domain_value = str(domain_id) if domain_id else ""
    duplicate = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_PTYPE,
                CasbinRule.v0 == str(team_id),
                CasbinRule.v1 == str(role_id),
                CasbinRule.v2 == normalized_domain,
                CasbinRule.v3 == domain_value,
            )
        )
    ).first()
    if duplicate is not None:
        grant = _parse_team_role(duplicate)
        if grant is None:
            raise RuntimeError("Existing team role rule is malformed")
        return grant

    rule = CasbinRule(
        ptype=TEAM_ROLE_PTYPE,
        v0=str(team_id),
        v1=str(role_id),
        v2=normalized_domain,
        v3=domain_value,
        v4=str(assigned_by) if assigned_by else "",
    )
    session.add(rule)
    await session.flush()
    grant = _parse_team_role(rule)
    if grant is None:
        raise RuntimeError("Unable to persist team role rule")

    members = (
        await session.exec(select(AuthzTeamMember).where(AuthzTeamMember.team_id == team_id))
    ).all()
    for member in members:
        await _sync_grant_for_user(
            session,
            grant=grant,
            user_id=member.user_id,
            assigned_by=assigned_by,
        )
    return grant


async def sync_team_member_grants(
    session: AsyncSession,
    *,
    team_id: UUID,
    user_id: UUID,
    assigned_by: UUID | None,
) -> list[UUID]:
    assignment_ids: list[UUID] = []
    for grant in await list_team_role_grants(session, team_id):
        assignment_ids.append(
            await _sync_grant_for_user(
                session,
                grant=grant,
                user_id=user_id,
                assigned_by=assigned_by,
            )
        )
    return assignment_ids


async def remove_team_member_grants(
    session: AsyncSession,
    *,
    team_id: UUID,
    user_id: UUID,
) -> set[UUID]:
    grants = await list_team_role_grants(session, team_id)
    grant_ids = {str(grant.id) for grant in grants}
    if not grant_ids:
        return set()
    mappings = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_MEMBER_PTYPE,
                CasbinRule.v0.in_(grant_ids),
                CasbinRule.v1 == str(user_id),
            )
        )
    ).all()
    assignment_ids = {_uuid_or_none(mapping.v2) for mapping in mappings}
    assignment_ids.discard(None)
    for mapping in mappings:
        await session.delete(mapping)
    await session.flush()
    for assignment_id in assignment_ids:
        await _cleanup_assignment_if_unreferenced(session, assignment_id)
    return assignment_ids


async def delete_team_role_grant(
    session: AsyncSession,
    *,
    team_id: UUID,
    rule_id: int,
) -> set[UUID]:
    rule = await session.get(CasbinRule, rule_id)
    if rule is None or rule.ptype != TEAM_ROLE_PTYPE or rule.v0 != str(team_id):
        return set()
    mappings = (
        await session.exec(
            select(CasbinRule).where(
                CasbinRule.ptype == TEAM_ROLE_MEMBER_PTYPE,
                CasbinRule.v0 == str(rule_id),
            )
        )
    ).all()
    assignment_ids = {_uuid_or_none(mapping.v2) for mapping in mappings}
    assignment_ids.discard(None)
    for mapping in mappings:
        await session.delete(mapping)
    await session.delete(rule)
    await session.flush()
    for assignment_id in assignment_ids:
        await _cleanup_assignment_if_unreferenced(session, assignment_id)
    return assignment_ids


async def delete_all_team_role_grants(session: AsyncSession, team_id: UUID) -> set[UUID]:
    affected: set[UUID] = set()
    for grant in await list_team_role_grants(session, team_id):
        affected.update(
            await delete_team_role_grant(session, team_id=team_id, rule_id=grant.id)
        )
    return affected


__all__ = [
    "TeamRoleGrant",
    "create_team_role_grant",
    "delete_all_team_role_grants",
    "delete_team_role_grant",
    "list_team_role_grants",
    "remove_team_member_grants",
    "sync_team_member_grants",
]
