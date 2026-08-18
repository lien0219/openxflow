"""Pydantic schemas for /api/v1/authz/role-assignments."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

# ``global`` is unscoped. Every other domain is tied to one concrete UUID.
DomainType = Literal["global", "organization", "org", "workspace", "project", "channel"]


class RoleAssignmentCreate(BaseModel):
    """Payload for assigning a role to a user."""

    user_id: UUID
    role_id: UUID
    domain_type: DomainType = Field(
        default="global",
        description=(
            "Domain scope of the assignment. ``global`` is unscoped; organization, org, "
            "workspace, project and channel assignments require a matching ``domain_id``."
        ),
    )
    domain_id: UUID | None = Field(
        default=None,
        description="Required for every non-global assignment; must be null for global assignments.",
    )

    @model_validator(mode="after")
    def _check_domain_id_consistency(self) -> RoleAssignmentCreate:
        if self.domain_type == "global" and self.domain_id is not None:
            msg = "domain_id must be null when domain_type='global'"
            raise ValueError(msg)
        if self.domain_type != "global" and self.domain_id is None:
            msg = f"domain_id is required when domain_type={self.domain_type!r}"
            raise ValueError(msg)
        return self


class RoleAssignmentRead(BaseModel):
    """Serialized authz_role_assignment row returned by the API."""

    id: UUID
    user_id: UUID
    role_id: UUID
    domain_type: str
    domain_id: UUID | None
    assigned_at: datetime
    assigned_by: UUID | None

    model_config = {"from_attributes": True}
