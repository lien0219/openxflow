"""Pydantic schemas for /api/v1/authz/teams, members and bulk role grants."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

TeamRoleDomainType = Literal["global", "organization", "org", "workspace", "project", "channel"]


class TeamCreate(BaseModel):
    """Payload for creating an authz_team."""

    team_name: str = Field(..., min_length=1, max_length=255)
    adom_name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Administrative-domain slug, unique across all teams (often the SSO group name).",
    )
    description: str | None = None
    is_active: bool = True


class TeamUpdate(BaseModel):
    """Payload for updating an authz_team (PATCH semantics)."""

    team_name: str | None = Field(default=None, min_length=1, max_length=255)
    adom_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    is_active: bool | None = None


class TeamRead(BaseModel):
    """Serialized authz_team row returned by the API."""

    id: UUID
    team_name: str
    adom_name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TeamMemberCreate(BaseModel):
    """Payload for adding a user to a team."""

    user_id: UUID
    source: Literal["manual", "sso"] = "manual"


class TeamMemberRead(BaseModel):
    """Serialized authz_team_member row."""

    id: UUID
    team_id: UUID
    user_id: UUID
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}


class TeamRoleAssignmentCreate(BaseModel):
    """Persisted team role that materializes safe user assignments for members."""

    role_id: UUID
    domain_type: TeamRoleDomainType = "global"
    domain_id: UUID | None = None

    @model_validator(mode="after")
    def _validate_scope(self) -> TeamRoleAssignmentCreate:
        if self.domain_type == "global" and self.domain_id is not None:
            raise ValueError("domain_id must be null when domain_type='global'")
        if self.domain_type != "global" and self.domain_id is None:
            raise ValueError(f"domain_id is required when domain_type={self.domain_type!r}")
        return self


class TeamRoleAssignmentRead(BaseModel):
    """Serialized team role rule stored in the shared Casbin policy table."""

    id: int
    team_id: UUID
    role_id: UUID
    domain_type: str
    domain_id: UUID | None
    assigned_by: UUID | None
