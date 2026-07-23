"""Durable database job model for acknowledged provider webhooks."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, ForeignKey, Index, LargeBinary, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class ChannelWebhookJobStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChannelWebhookJob(SQLModel, table=True):  # type: ignore[call-arg]
    """Provider callback persisted before the provider receives a successful ACK."""

    __tablename__ = "channel_webhook_job"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_channel_webhook_job_external_event",
        ),
        Index("ix_channel_webhook_job_claim", "status", "next_attempt_at", "created_at"),
        Index("ix_channel_webhook_job_lease", "status", "lease_expires_at"),
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
    channel_type: str = Field(nullable=False, max_length=32)
    external_event_id: str = Field(nullable=False, max_length=255)
    headers_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )
    payload: bytes = Field(sa_column=Column(LargeBinary, nullable=False))
    status: str = Field(default=ChannelWebhookJobStatus.PENDING.value, nullable=False, max_length=32)
    attempts: int = Field(default=0, nullable=False)
    max_attempts: int = Field(default=5, nullable=False)
    lease_owner: UUID | None = Field(default=None, nullable=True)
    lease_expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    next_attempt_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    completed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
