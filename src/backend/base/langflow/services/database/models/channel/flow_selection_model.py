"""Durable per-member active workflow selections for communication channels."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now


class UTCDateTime(sa.TypeDecorator):
    """Persist UTC timestamps while restoring timezone information on SQLite reads."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        if value is None:
            return None
        normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        if dialect.name == "sqlite":
            return normalized.replace(tzinfo=None)
        return normalized

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:  # type: ignore[no-untyped-def]
        del dialect
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class ChannelActiveWorkflowSelection(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_active_workflow_selection"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "conversation_binding_id",
            "channel_identity_id",
            "conversation_scope_id",
            name="uq_channel_active_flow_selection_scope",
        ),
        sa.Index(
            "ix_channel_active_flow_selection_lookup",
            "connection_id",
            "conversation_binding_id",
            "channel_identity_id",
            "conversation_scope_id",
        ),
        sa.Index("ix_channel_active_flow_selection_connection_updated", "connection_id", "updated_at"),
        sa.Index("ix_channel_active_flow_selection_expires", "expires_at"),
        sa.Index("ix_channel_active_flow_selection_connection_expires", "connection_id", "expires_at"),
        sa.Index(
            "ix_channel_active_flow_selection_identity_updated",
            "connection_id",
            "channel_identity_id",
            "updated_at",
        ),
        sa.Index(
            "ix_channel_active_flow_selection_command_updated",
            "workflow_command_id",
            "updated_at",
        ),
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
    conversation_binding_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_conversation_binding.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    channel_identity_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_identity.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    conversation_scope_id: str = Field(default="", max_length=255)
    workflow_command_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_workflow_command.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    selected_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_used_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(timezone=True), nullable=True))
    expires_at: datetime | None = Field(default=None, sa_column=Column(UTCDateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(UTCDateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelActiveWorkflowSelectionRead(SQLModel):
    id: UUID
    connection_id: UUID
    conversation_binding_id: UUID
    channel_identity_id: UUID
    conversation_scope_id: str
    workflow_command_id: UUID
    selected_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    identity_display_name: str | None = None
    external_user_id: str | None = None
    conversation_display_name: str | None = None
    external_conversation_id: str | None = None
    conversation_type: str | None = None
    command: str | None = None
    flow_id: UUID | None = None
    flow_name: str | None = None
    flow_endpoint_name: str | None = None
    execution_identity_type: str | None = None


class ChannelActiveWorkflowSelectionPage(SQLModel):
    items: list[ChannelActiveWorkflowSelectionRead]
    page: int
    page_size: int
    total: int
    total_pages: int
