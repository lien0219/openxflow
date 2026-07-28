"""CRUD API for production RBAC role assignments."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from lfx.log.logger import logger
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.api.v1.schemas.authz_role_assignments import (
    RoleAssignmentCreate,
    RoleAssignmentRead,
)
from langflow.services.authorization.invalidation import safe_invalidate_user
from langflow.services.authorization.utils import audit_decision
from langflow.services.database.models.auth import AuthzRole, AuthzRoleAssignment
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_authorization_service

router = APIRouter(prefix="/authz/role-assignments", tags=["Authorization"])

_LIST_MAX_LIMIT = 200
_LIST_DEFAULT_LIMIT = 100
_ALLOWED_DOMAIN_TYPES = {"global", "organization", "org", "workspace", "project", "channel"}


def _require_superuser(user: User) -> None:
    if not user.is_active or not user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser required to administer role assignments.",
        )


def _is_channel_service_identity(user: User) -> bool:
    optins = user.optins if isinstance(user.optins, dict) else {}
    return bool(optins.get("channel_service_identity"))


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
    if user_id is None:
        user_id = current_user.id
    elif user_id != current_user.id:
        _require_superuser(current_user)
    stmt = select(AuthzRoleAssignment).where(AuthzRoleAssignment.user_id == user_id)
    if role_id is not None:
        stmt = stmt.where(AuthzRoleAssignment.role_id == role_id)
    if domain_type is not None:
        stmt = stmt.where(AuthzRoleAssignment.domain_type == domain_type.strip().lower())
    if domain_id is not None:
        stmt = stmt.where(AuthzRoleAssignment.domain_id == domain_id)
    stmt = stmt.order_by(AuthzRoleAssignment.assigned_at.desc(), AuthzRoleAssignment.id).offset(offset).limit(limit)
    rows = (await session.exec(stmt)).all()
    return [RoleAssignmentRead.model_validate(row) for row in rows]


@router.post("", response_model=RoleAssignmentRead, status_code=status.HTTP_201_CREATED)
@router.post("/", response_model=RoleAssignmentRead, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    payload: RoleAssignmentCreate,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> RoleAssignmentRead:
    """Assign one role in a validated domain. Superuser-only."""
    _require_superuser(current_user)

    user = await session.get(User, payload.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user_id not found")
    if _is_channel_service_identity(user):
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

    assignment = AuthzRoleAssignment(
        user_id=payload.user_id,
        role_id=payload.role_id,
        domain_type=domain_type,
        domain_id=payload.domain_id,
        assigned_at=datetime.now(timezone.utc),
        assigned_by=current_user.id,
    )
    session.add(assignment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assignment already exists for this user/role/domain",
        ) from exc
    await session.refresh(assignment)
    await safe_invalidate_user(
        get_authorization_service(),
        payload.user_id,
        op="role_assignment:create",
    )
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
    return RoleAssignmentRead.model_validate(assignment)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assignment(
    assignment_id: UUID,
    current_user: CurrentActiveUser,
    session: DbSession,
) -> None:
    """Revoke a role assignment. Superuser-only."""
    _require_superuser(current_user)
    assignment = await session.get(AuthzRoleAssignment, assignment_id)
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    user_id = assignment.user_id
    role_id = assignment.role_id
    domain_type = assignment.domain_type
    domain_id = assignment.domain_id
    await session.delete(assignment)
    await session.commit()
    await safe_invalidate_user(
        get_authorization_service(),
        user_id,
        op="role_assignment:delete",
    )
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
