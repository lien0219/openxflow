"""Paginated authorization audit queries for superusers and scoped auditors."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import col, select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.database.models.auth import AuthzAuditLog
from langflow.services.deps import get_authorization_service

router = APIRouter(prefix="/authz/audit", tags=["Authorization"])

_MAX_PAGE_SIZE = 200
_ALLOWED_DOMAINS = {"global", "organization", "org", "workspace", "project", "channel"}


class AuthzAuditLogRead(BaseModel):
    """Read-only projection of an ``AuthzAuditLog`` row."""

    id: UUID
    user_id: UUID | None
    action: str
    resource_type: str | None
    resource_id: UUID | None
    result: str
    details: dict | None
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuthzAuditPage(BaseModel):
    """Paginated audit-log response."""

    items: list[AuthzAuditLogRead]
    total: int
    page: int
    size: int
    pages: int


def _audit_domain_context(domain_type: str, domain_id: UUID | None) -> tuple[str, dict[str, UUID]]:
    normalized = domain_type.strip().lower()
    if normalized not in _ALLOWED_DOMAINS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown domain type")
    if normalized == "global":
        if domain_id is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="global audit queries must not include domain_id",
            )
        return "*", {}
    if domain_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"{normalized} audit queries require domain_id",
        )
    context_keys = {
        "organization": "organization_id",
        "org": "organization_id",
        "workspace": "workspace_id",
        "project": "project_id",
        "channel": "connection_id",
    }
    return f"{normalized}:{domain_id}", {context_keys[normalized]: domain_id}


@router.get("", response_model=AuthzAuditPage)
@router.get("/", response_model=AuthzAuditPage)
async def list_audit_log(
    session: DbSession,
    current_user: CurrentActiveUser,
    user_id: Annotated[UUID | None, Query(description="Filter by acting user id.")] = None,
    resource_type: Annotated[
        str | None,
        Query(description="Filter by resource type slug, e.g. ``flow`` or ``deployment``."),
    ] = None,
    resource_id: Annotated[UUID | None, Query(description="Filter by resource UUID.")] = None,
    action: Annotated[
        str | None,
        Query(description="Filter by action string, e.g. ``flow:read`` or ``share:create``."),
    ] = None,
    result: Annotated[
        str | None,
        Query(description="Filter by decision result (``allow`` / ``deny`` / ``owner_override``)."),
    ] = None,
    since: Annotated[datetime | None, Query(description="Inclusive lower bound on ``timestamp``.")] = None,
    until: Annotated[datetime | None, Query(description="Exclusive upper bound on ``timestamp``.")] = None,
    domain_type: Annotated[str | None, Query(description="RBAC domain for non-superuser auditors.")] = None,
    domain_id: Annotated[UUID | None, Query(description="Concrete domain resource ID.")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=_MAX_PAGE_SIZE)] = 50,
) -> AuthzAuditPage:
    """Return an audited, paginated slice without leaking records across scopes."""
    if since is not None and until is not None and since >= until:
        raise HTTPException(status_code=400, detail="`since` must be strictly less than `until`")

    forced_resource_type: str | None = None
    forced_resource_id: UUID | None = None
    if not current_user.is_superuser:
        if domain_type is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A scoped domain is required for non-superuser audit access.",
            )
        normalized_domain = domain_type.strip().lower()
        domain, context = _audit_domain_context(normalized_domain, domain_id)
        authz = get_authorization_service()
        allowed = await authz.is_enabled() and await authz.enforce(
            user_id=current_user.id,
            domain=domain,
            obj="audit:*",
            act="read",
            context=context,
        )
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        if normalized_domain != "global":
            forced_resource_type = "organization" if normalized_domain == "org" else normalized_domain
            forced_resource_id = domain_id

    base = select(AuthzAuditLog)
    if user_id is not None:
        base = base.where(AuthzAuditLog.user_id == user_id)
    if forced_resource_type is not None:
        base = base.where(AuthzAuditLog.resource_type == forced_resource_type)
    elif resource_type is not None:
        base = base.where(AuthzAuditLog.resource_type == resource_type)
    if forced_resource_id is not None:
        base = base.where(AuthzAuditLog.resource_id == forced_resource_id)
    elif resource_id is not None:
        base = base.where(AuthzAuditLog.resource_id == resource_id)
    if action is not None:
        base = base.where(AuthzAuditLog.action == action)
    if result is not None:
        base = base.where(AuthzAuditLog.result == result)
    if since is not None:
        base = base.where(AuthzAuditLog.timestamp >= since)
    if until is not None:
        base = base.where(AuthzAuditLog.timestamp < until)

    from sqlalchemy import func

    total_stmt = select(func.count()).select_from(base.subquery())
    total = int((await session.exec(total_stmt)).first() or 0)

    page_stmt = base.order_by(col(AuthzAuditLog.timestamp).desc()).offset((page - 1) * size).limit(size)
    rows = list(await session.exec(page_stmt))

    items = [AuthzAuditLogRead.model_validate(row, from_attributes=True) for row in rows]
    pages = (total + size - 1) // size if total > 0 else 0
    return AuthzAuditPage(items=items, total=total, page=page, size=size, pages=pages)


__all__ = ["AuthzAuditLogRead", "AuthzAuditPage", "router"]
