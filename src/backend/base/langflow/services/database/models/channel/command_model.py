"""Workflow command routing models for communication channels."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelCommandScope(StrEnum):
    CONNECTION_SHARED = "connection_shared"
    CONVERSATION_SHARED = "conversation_shared"
    IDENTITY_CONNECTION = "identity_connection"
    IDENTITY_CONVERSATION = "identity_conversation"


class ChannelWorkflowCommandBase(SQLModel):
    command: str = Field(min_length=2, max_length=33)
    aliases: list[str] = Field(default_factory=list, sa_column=Column(JsonVariant, nullable=False))
    description: str | None = Field(default=None, max_length=500)
    scope_type: str = Field(default=ChannelCommandScope.CONNECTION_SHARED.value, max_length=32)
    prompt_template: str | None = Field(default=None, max_length=8000)
    input_required: bool = Field(default=False)
    allow_attachments: bool = Field(default=True)
    require_mention: bool = Field(default=False)
    enabled: bool = Field(default=True)
    settings_data: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JsonVariant, nullable=False))


class ChannelWorkflowCommand(ChannelWorkflowCommandBase, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_workflow_command"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "scope_key",
            "normalized_command",
            name="uq_channel_workflow_command_scope_command",
        ),
        sa.Index("ix_channel_workflow_command_connection_scope", "connection_id", "scope_type", "enabled"),
        sa.Index("ix_channel_workflow_command_flow_id", "flow_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_connection.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    conversation_binding_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_conversation_binding.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    owner_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=True,
            index=True,
        ),
    )
    created_by: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    flow_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("flow.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    scope_key: str = Field(max_length=255)
    normalized_command: str = Field(max_length=33, index=True)
    last_used_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelWorkflowCommandCreate(ChannelWorkflowCommandBase):
    flow_id: UUID
    conversation_binding_id: UUID | None = None


class ChannelWorkflowCommandUpdate(SQLModel):
    command: str | None = Field(default=None, min_length=2, max_length=33)
    aliases: list[str] | None = None
    description: str | None = Field(default=None, max_length=500)
    flow_id: UUID | None = None
    prompt_template: str | None = Field(default=None, max_length=8000)
    input_required: bool | None = None
    allow_attachments: bool | None = None
    require_mention: bool | None = None
    enabled: bool | None = None
    settings_data: dict[str, Any] | None = None


class ChannelWorkflowCommandRead(ChannelWorkflowCommandBase):
    id: UUID
    connection_id: UUID
    conversation_binding_id: UUID | None = None
    owner_user_id: UUID | None = None
    created_by: UUID
    flow_id: UUID
    scope_key: str
    normalized_command: str
    last_used_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChannelWorkflowCommandPage(SQLModel):
    items: list[ChannelWorkflowCommandRead]
    page: int
    page_size: int
    total: int
    total_pages: int
