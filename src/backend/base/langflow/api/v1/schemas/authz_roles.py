"""Pydantic schemas for /api/v1/authz/roles."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from langflow.services.authorization.actions import (
    AuditAction,
    ChannelAction,
    DeploymentAction,
    FileAction,
    FlowAction,
    KnowledgeBaseAction,
    ProjectAction,
    ShareAction,
    VariableAction,
)

_RESOURCE_ACTIONS: dict[str, frozenset[str]] = {
    "flow": frozenset({a.value for a in FlowAction}) | {"*"},
    "deployment": frozenset({a.value for a in DeploymentAction}) | {"*"},
    "project": frozenset({a.value for a in ProjectAction}) | {"*"},
    "knowledge_base": frozenset({a.value for a in KnowledgeBaseAction}) | {"*"},
    "variable": frozenset({a.value for a in VariableAction}) | {"*"},
    "file": frozenset({a.value for a in FileAction}) | {"*"},
    "share": frozenset({a.value for a in ShareAction}) | {"*"},
    "channel": frozenset({a.value for a in ChannelAction}) | {"*"},
    "audit": frozenset({a.value for a in AuditAction}) | {"*"},
}

_PERMISSION_SLUG_RE = re.compile(r"^[a-z_]+:[a-z_*]+$")


def _validate_permission_slug(slug: str) -> str:
    normalized = slug.strip().lower()
    if not _PERMISSION_SLUG_RE.fullmatch(normalized):
        msg = (
            f"permission {slug!r} is not in the canonical "
            "'<resource>:<action>' form (e.g. 'flow:read', 'channel:write')"
        )
        raise ValueError(msg)
    resource, action = normalized.split(":", 1)
    allowed = _RESOURCE_ACTIONS.get(resource)
    if allowed is None:
        msg = f"permission {slug!r} has unknown resource {resource!r}; expected one of {sorted(_RESOURCE_ACTIONS)}"
        raise ValueError(msg)
    if action not in allowed:
        msg = (
            f"permission {slug!r} has unknown action {action!r} for resource {resource!r}; "
            f"expected one of {sorted(allowed)}"
        )
        raise ValueError(msg)
    return normalized


class RoleCreate(BaseModel):
    """Payload for creating an authz_role row."""

    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = Field(default=None)
    permissions: list[str] = Field(
        default_factory=list,
        description=(
            "Canonical ``<resource>:<action>`` permissions. Supported resources are "
            "flow, deployment, project, knowledge_base, variable, file, share, channel and audit."
        ),
    )
    parent_role_id: UUID | None = Field(default=None)

    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(_validate_permission_slug(item) for item in value))


class RoleUpdate(BaseModel):
    """Payload for updating an authz_role row (PATCH semantics — only set fields apply)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    permissions: list[str] | None = None
    parent_role_id: UUID | None = None

    @field_validator("permissions")
    @classmethod
    def _validate_permissions(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        return list(dict.fromkeys(_validate_permission_slug(item) for item in value))


class RoleRead(BaseModel):
    """Serialized authz_role row returned by the API."""

    id: UUID
    name: str
    description: str | None
    is_system: bool
    permissions: list[str]
    parent_role_id: UUID | None
    workspace_id: UUID | None
    created_at: datetime
    updated_at: datetime
    created_by: UUID | None

    model_config = {"from_attributes": True}
