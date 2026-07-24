"""Persistent at-most-once guard for durable channel event deliveries."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now


class ChannelOutboundDeliveryKind(str, Enum):
    ACKNOWLEDGEMENT = "acknowledgement"
    RESPONSE = "response"


class ChannelOutboundDeliveryStatus(str, Enum):
    RESERVED = "reserved"
    SENT = "sent"
    FAILED = "failed"


class ChannelOutboundDelivery(SQLModel, table=True):  # type: ignore[call-arg]
    """One provider delivery slot for one inbound event and delivery kind."""

    __tablename__ = "channel_outbound_delivery"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            "delivery_kind",
            name="uq_channel_outbound_delivery_event_kind",
        ),
        Index("ix_channel_outbound_delivery_status_updated", "status", "updated_at"),
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
    external_event_id: str = Field(nullable=False, max_length=255)
    delivery_kind: str = Field(nullable=False, max_length=32)
    response_digest: str = Field(nullable=False, max_length=64)
    status: str = Field(default=ChannelOutboundDeliveryStatus.RESERVED.value, nullable=False, max_length=32)
    attempts: int = Field(default=1, nullable=False)
    provider_message_id: str | None = Field(default=None, nullable=True, max_length=255)
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
