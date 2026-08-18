"""Team, membership and persistent team-role administration APIs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from lfx.log.logger import logger
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
from langflow.services.authorization.bootstrap import is_managed_service_user
from langflow.services.authorization.invalidation import safe_invalidate_all, safe_invalidate_user
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

router = APIRouter(prefix="/authz/teams", tags=["Authorization"])

_LIST_MAX_LIMIT = 200
_LIST_DEFAULT_LIMIT = 100


def _require_superuser(user: User) -> None:
    if not user.is_active or not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser required to administer teams.",
        )


async def _get_team(
    session: DbSession,
    team_id: UUID,
    *,
    for_update: bool = False,
) -> AuthzTeam:
    statement = select(AuthzTeam).where(AuthzTeam.id == team_id)
    if for_update:
        # PostgreSQL serializes all membership/role writes for one team. SQLite
        # ignores FOR UPDATE but its single-writer transaction still protects
        # local development from duplicate grant materialization.
        statement = statement.with_for_update()
    team = (await session.exec(statement)).first()
    if team is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")
    return team


async def _require_team_reader(
    session: DbSession,
    *,
    team_id: UUID,
    current_user: User,
) -> None:
    """Hide team rosters and role grants from unrelated authenticated users."""
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
        # 404 avoids turning sequential UUID probes into a team-directory oracle.
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
    current_user: CurrentActiveUser,  # noqa: ARG001 — authenticated share picker
    search: Annotated[str | None, Query(description="Substring match on team_name or adom_name")] = None,
    is_active: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_LIST_MAX_LIMIT)] = _LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TeamRead]:
    # Team name/slug metadata is available to authenticated users because the
    # resource-share dialog needs an audience picker. Rosters and grants remain
    # protected by ``_require_team_reader`` below.
    statement = select(AuthzTeam)
    if search:
        like = f"%{search}%"
        statement = statement.where((AuthzTeam.team_name.ilike(like)) | (AuthzTeam.adom_name.ilike(like)))
    if is_active is not None:
        statement = statement.where(AuthzTeam.is_active == is_active)
    statement = statement.order_by(AuthzTeam.team_name, AuthzTeam.id).offset(offset).limit(limit)
    rows = (await session.exec(statement)).all()
    return [TeamRead.model_validate(row) for row in rows]


@router.get("/{team_id}", response_model=TeamRead)
async def read_team(
    team_id: UUID,
    session: DbSession,
    current_user: CurrentActiveUser,
) -> TeamRead:
    team = await _get_team(session, team_id)
    await _require_team_reader(session, team_id=team_id, current_user=current_user)
    return TeamRead.model_validate(team)


@router.post("", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=TeamRead, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRead:
    _require_superuser(current_user)
    team = AuthzTeam(
        team_name=payload.team_name,
        adom_name=payload.adom_name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(team)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Team with adom_name {payload.adom_name!r} already exists",
        ) from exc
    await session.refresh(team)
    await audit_decision(
        user_id=current_user.id,
        action="team:create",
        obj=f"team:{team.id}",
        result="allow",
        details={"team_name": team.team_name, "adom_name": team.adom_name},
    )
    logger.info("Created team %s (id=%s)", team.team_name, team.id)
    return TeamRead.model_validate(team)


@router.patch("/{team_id}", response_model=TeamRead)
async def update_team(
    team_id: UUID,
    payload: TeamUpdate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRead:
    _require_superuser(current_user)
    team = await _get_team(session, team_id, for_update=True)

    policy_relevant_changed = False
    changed_fields: list[str] = []
    if payload.team_name is not None and team.team_name != payload.team_name:
        team.team_name = payload.team_name
        changed_fields.append("team_name")
    if payload.adom_name is not None and team.adom_name != payload.adom_name:
        team.adom_name = payload.adom_name
        changed_fields.append("adom_name")
        policy_relevant_changed = True
    if "description" in payload.model_fields_set and team.description != payload.description:
        team.description = payload.description
        changed_fields.append("description")
    if payload.is_active is not None and team.is_active != payload.is_active:
        team.is_active = payload.is_active
        changed_fields.append("is_active")
        policy_relevant_changed = True
    team.updated_at = datetime.now(timezone.utc)

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="adom_name conflict — another team already uses this slug",
        ) from exc
    await session.refresh(team)
    if policy_relevant_changed:
        await safe_invalidate_all(get_authorization_service(), op="team:update")
    await audit_decision(
        user_id=current_user.id,
        action="team:update",
        obj=f"team:{team.id}",
        result="allow",
        details={"team_name": team.team_name, "fields_changed": sorted(changed_fields)},
    )
    logger.info("Updated team %s (id=%s)", team.team_name, team.id)
    return TeamRead.model_validate(team)


@router.delete("/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    _require_superuser(current_user)
    team = await _get_team(session, team_id, for_update=True)
    team_name = team.team_name
    await delete_all_team_role_grants(session, team_id)
    await session.delete(team)
    await session.commit()
    await safe_invalidate_all(get_authorization_service(), op="team:delete")
    await audit_decision(
        user_id=current_user.id,
        action="team:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"team_name": team_name},
    )
    logger.info("Deleted team id=%s", team_id)


# --- persistent team roles ------------------------------------------------ #


@router.get("/{team_id}/roles", response_model=list[TeamRoleAssignmentRead])
async def list_team_roles(
    team_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> list[TeamRoleAssignmentRead]:
    await _get_team(session, team_id)
    await _require_team_reader(session, team_id=team_id, current_user=current_user)
    return [_team_role_read(grant) for grant in await list_team_role_grants(session, team_id)]


@router.post(
    "/{team_id}/roles",
    response_model=TeamRoleAssignmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_team_role(
    team_id: UUID,
    payload: TeamRoleAssignmentCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamRoleAssignmentRead:
    _require_superuser(current_user)
    await _get_team(session, team_id, for_update=True)
    role = await session.get(AuthzRole, payload.role_id)
    if role is None:
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
            "rule_id": grant.id,
            "role_id": str(payload.role_id),
            "role_name": role.name,
            "domain_type": payload.domain_type,
            "domain_id": str(payload.domain_id) if payload.domain_id else None,
        },
    )
    return _team_role_read(grant)


@router.delete("/{team_id}/roles/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_role(
    team_id: UUID,
    rule_id: int,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    _require_superuser(current_user)
    await _get_team(session, team_id, for_update=True)
    existing_ids = {grant.id for grant in await list_team_role_grants(session, team_id)}
    if rule_id not in existing_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team role not found")
    await delete_team_role_grant(session, team_id=team_id, rule_id=rule_id)
    await session.commit()
    await safe_invalidate_all(get_authorization_service(), op="team_role:delete")
    await audit_decision(
        user_id=current_user.id,
        action="team_role:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"rule_id": rule_id},
    )


# --- team members --------------------------------------------------------- #


@router.get("/{team_id}/members", response_model=list[TeamMemberRead])
async def list_members(
    team_id: UUID,
    session: DbSession,
    current_user: CurrentActiveUser,
    limit: Annotated[int, Query(ge=1, le=_LIST_MAX_LIMIT)] = _LIST_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TeamMemberRead]:
    await _get_team(session, team_id)
    await _require_team_reader(session, team_id=team_id, current_user=current_user)
    statement = (
        select(AuthzTeamMember)
        .where(AuthzTeamMember.team_id == team_id)
        .order_by(AuthzTeamMember.created_at, AuthzTeamMember.user_id)
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.exec(statement)).all()
    return [TeamMemberRead.model_validate(row) for row in rows]


@router.post(
    "/{team_id}/members",
    response_model=TeamMemberRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_member(
    team_id: UUID,
    payload: TeamMemberCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> TeamMemberRead:
    _require_superuser(current_user)
    team = await _get_team(session, team_id, for_update=True)
    user = await session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_id not found")
    if is_managed_service_user(user):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Managed channel service identities cannot join RBAC teams",
        )

    member = AuthzTeamMember(team_id=team_id, user_id=payload.user_id, source=payload.source)
    session.add(member)
    try:
        await session.flush()
        await sync_team_member_grants(
            session,
            team_id=team_id,
            user_id=payload.user_id,
            assigned_by=current_user.id,
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a member of this team",
        ) from exc
    await session.refresh(member)
    await safe_invalidate_user(get_authorization_service(), payload.user_id, op="team_member:create")
    await audit_decision(
        user_id=current_user.id,
        action="team_member:create",
        obj=f"team:{team_id}",
        result="allow",
        details={
            "team_name": team.team_name,
            "user_id": str(payload.user_id),
            "source": payload.source,
        },
    )
    logger.info("Added user=%s to team=%s", payload.user_id, team_id)
    return TeamMemberRead.model_validate(member)


@router.delete("/{team_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    team_id: UUID,
    user_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    _require_superuser(current_user)
    await _get_team(session, team_id, for_update=True)
    member = (
        await session.exec(
            select(AuthzTeamMember).where(
                AuthzTeamMember.team_id == team_id,
                AuthzTeamMember.user_id == user_id,
            )
        )
    ).first()
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    await remove_team_member_grants(session, team_id=team_id, user_id=user_id)
    await session.delete(member)
    await session.commit()
    await safe_invalidate_user(get_authorization_service(), user_id, op="team_member:delete")
    await audit_decision(
        user_id=current_user.id,
        action="team_member:delete",
        obj=f"team:{team_id}",
        result="allow",
        details={"user_id": str(user_id)},
    )
    logger.info("Removed user=%s from team=%s", user_id, team_id)
