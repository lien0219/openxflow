"""Per-user effective-permissions endpoint used by frontend permission gates."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from langflow.api.utils import CurrentActiveUser
from langflow.services.deps import get_authorization_service

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


class EffectivePermissionsRequest(BaseModel):
    """Body for :func:`get_effective_permissions`."""

    resource_type: ResourceTypeLiteral
    resource_ids: list[UUID] = Field(
        ...,
        description="Resource IDs to evaluate. Capped at 500 per request.",
    )
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
