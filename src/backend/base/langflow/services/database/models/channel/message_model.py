"""Provider-neutral message records for the channel management center."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class ChannelMessageDirection(str, Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class ChannelMessageRecordStatus(str, Enum):
    RECEIVED = "received"
    PROCESSED = "processed"
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"


class ChannelMessageRecordKind(str, Enum):
    INBOUND = "inbound"
    RESPONSE = "response"
    PROCESSING = "processing"
    SYSTEM = "system"


class ChannelMessageRecord(SQLModel, table=True):  # type: ignore[call-arg]
    """Sanitized inbound or outbound message metadata retained for operations."""

    __tablename__ = "channel_message_record"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            "direction",
            "message_kind",
            name="uq_channel_message_event_direction_kind",
        ),
        sa.Index("ix_channel_message_connection_created", "connection_id", "created_at"),
        sa.Index("ix_channel_message_conversation_created", "connection_id", "external_conversation_id", "created_at"),
        sa.Index("ix_channel_message_user_created", "connection_id", "external_user_id", "created_at"),
        sa.Index("ix_channel_message_status_created", "connection_id", "status", "created_at"),
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
            ForeignKey("channel_conversation_binding.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    execution_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_execution_log.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    external_event_id: str = Field(max_length=255)
    external_message_id: str | None = Field(default=None, max_length=1024)
    provider_message_id: str | None = Field(default=None, max_length=1024)
    external_conversation_id: str = Field(max_length=255, index=True)
    conversation_scope_id: str = Field(default="", max_length=255)
    external_user_id: str | None = Field(default=None, max_length=255, index=True)
    sender_name: str | None = Field(default=None, max_length=255)
    direction: str = Field(max_length=16, index=True)
    message_kind: str = Field(max_length=32)
    message_type: str = Field(default="text", max_length=64)
    status: str = Field(default=ChannelMessageRecordStatus.RECEIVED.value, max_length=32, index=True)
    text: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    has_attachments: bool = Field(default=False)
    attachment_count: int = Field(default=0, ge=0)
    reply_to_message_id: str | None = Field(default=None, max_length=1024)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    metadata_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    delivered_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ChannelMessageRecordRead(SQLModel):
    id: UUID
    connection_id: UUID
    conversation_binding_id: UUID | None = None
    execution_id: UUID | None = None
    external_event_id: str
    external_message_id: str | None = None
    provider_message_id: str | None = None
    external_conversation_id: str
    conversation_scope_id: str
    external_user_id: str | None = None
    sender_name: str | None = None
    direction: str
    message_kind: str
    message_type: str
    status: str
    text: str | None = None
    has_attachments: bool
    attachment_count: int
    reply_to_message_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata_data: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    delivered_at: datetime | None = None


class ChannelMessageRecordPage(SQLModel):
    items: list[ChannelMessageRecordRead]
    page: int
    page_size: int
    total: int
    total_pages: int
