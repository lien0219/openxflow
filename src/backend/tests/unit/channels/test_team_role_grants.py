from __future__ import annotations

from uuid import uuid4

import pytest
from langflow.services.authorization.team_roles import (
    create_team_role_grant,
    delete_team_role_grant,
)
from langflow.services.database.models.auth import (
    AuthzRole,
    AuthzRoleAssignment,
    AuthzTeam,
    AuthzTeamMember,
    CasbinRule,
)
from langflow.services.database.models.user.model import User  # noqa: F401 - registers FK table
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession


async def _session() -> tuple[AsyncSession, object]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    return AsyncSession(engine, expire_on_commit=False), engine


async def _seed_team_role(session: AsyncSession):
    user_id = uuid4()
    role = AuthzRole(name=f"viewer-{uuid4()}", permissions=["flow:read"])
    first_team = AuthzTeam(team_name="Team A", adom_name=f"team-a-{uuid4()}")
    second_team = AuthzTeam(team_name="Team B", adom_name=f"team-b-{uuid4()}")
    session.add(role)
    session.add(first_team)
    session.add(second_team)
    await session.flush()
    session.add(AuthzTeamMember(team_id=first_team.id, user_id=user_id))
    session.add(AuthzTeamMember(team_id=second_team.id, user_id=user_id))
    await session.commit()
    return user_id, role, first_team, second_team


@pytest.mark.asyncio
async def test_team_role_materializes_and_removes_managed_assignment() -> None:
    session, engine = await _session()
    try:
        user_id, role, first_team, _ = await _seed_team_role(session)
        grant = await create_team_role_grant(
            session,
            team_id=first_team.id,
            role_id=role.id,
            domain_type="channel",
            domain_id=uuid4(),
            assigned_by=uuid4(),
        )
        await session.commit()

        assignments = (
            await session.exec(select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id))
        ).all()
        assert len(assignments) == 1
        assert assignments[0].role_id == role.id
        assert assignments[0].domain_type == "channel"

        await delete_team_role_grant(session, team_id=first_team.id, rule_id=grant.id)
        await session.commit()
        assert (
            await session.exec(select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id))
        ).first() is None
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_teams_reference_count_the_same_materialized_assignment() -> None:
    session, engine = await _session()
    try:
        user_id, role, first_team, second_team = await _seed_team_role(session)
        domain_id = uuid4()
        first_grant = await create_team_role_grant(
            session,
            team_id=first_team.id,
            role_id=role.id,
            domain_type="project",
            domain_id=domain_id,
            assigned_by=uuid4(),
        )
        second_grant = await create_team_role_grant(
            session,
            team_id=second_team.id,
            role_id=role.id,
            domain_type="project",
            domain_id=domain_id,
            assigned_by=uuid4(),
        )
        await session.commit()

        assignments = (
            await session.exec(select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id))
        ).all()
        assert len(assignments) == 1

        await delete_team_role_grant(session, team_id=first_team.id, rule_id=first_grant.id)
        await session.commit()
        assert await session.get(AuthzRoleAssignment, assignments[0].id) is not None

        await delete_team_role_grant(session, team_id=second_team.id, rule_id=second_grant.id)
        await session.commit()
        assert await session.get(AuthzRoleAssignment, assignments[0].id) is None
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_team_role_never_deletes_an_existing_manual_assignment() -> None:
    session, engine = await _session()
    try:
        user_id, role, first_team, _ = await _seed_team_role(session)
        domain_id = uuid4()
        manual_assignment = AuthzRoleAssignment(
            user_id=user_id,
            role_id=role.id,
            domain_type="workspace",
            domain_id=domain_id,
            assigned_by=uuid4(),
        )
        session.add(manual_assignment)
        await session.commit()

        grant = await create_team_role_grant(
            session,
            team_id=first_team.id,
            role_id=role.id,
            domain_type="workspace",
            domain_id=domain_id,
            assigned_by=uuid4(),
        )
        await session.commit()
        await delete_team_role_grant(session, team_id=first_team.id, rule_id=grant.id)
        await session.commit()

        assert await session.get(AuthzRoleAssignment, manual_assignment.id) is not None
        orphan_policy_rows = (
            await session.exec(select(CasbinRule).where(CasbinRule.v0 == str(manual_assignment.id)))
        ).all()
        assert orphan_policy_rows == []
    finally:
        await session.close()
        await engine.dispose()
