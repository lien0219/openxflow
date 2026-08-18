"""Sanitized configuration audit records for channel administration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class ChannelConfigurationAudit(SQLModel, table=True):  # type: ignore[call-arg]
    """Immutable, credential-free record of a channel configuration mutation."""

    __tablename__ = "channel_configuration_audit"
    __table_args__ = (
        sa.Index("ix_channel_audit_connection_created", "connection_reference", "created_at"),
        sa.Index("ix_channel_audit_actor_created", "actor_user_id", "created_at"),
        sa.Index("ix_channel_audit_resource_created", "resource_type", "resource_id", "created_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_connection.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    connection_reference: UUID = Field(index=True)
    actor_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    action: str = Field(max_length=64, index=True)
    resource_type: str = Field(max_length=64, index=True)
    resource_id: str | None = Field(default=None, max_length=255, index=True)
    before_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JsonVariant, nullable=False))
    after_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JsonVariant, nullable=False))
    changes_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JsonVariant, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelConfigurationAuditRead(SQLModel):
    id: UUID
    connection_id: UUID | None = None
    connection_reference: UUID
    actor_user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    before_data: dict[str, Any]
    after_data: dict[str, Any]
    changes_data: dict[str, Any]
    created_at: datetime


class ChannelConfigurationAuditPage(SQLModel):
    items: list[ChannelConfigurationAuditRead]
    page: int
    page_size: int
    total: int
    total_pages: int
