"""Execution audit records for channel-triggered workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Text, func
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelExecutionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ChannelExecutionTrigger(str, Enum):
    DEFAULT = "default"
    COMMAND = "command"
    ADMIN_FLOW = "admin_flow"
    FILE = "file"


class ChannelExecutionLog(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_execution_log"
    __table_args__ = (
        sa.Index("ix_channel_execution_connection_created", "connection_id", "created_at"),
        sa.Index("ix_channel_execution_conversation_created", "conversation_binding_id", "created_at"),
        sa.Index("ix_channel_execution_user_created", "openxflow_user_id", "created_at"),
        sa.Index("ix_channel_execution_status_created", "status", "created_at"),
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
    openxflow_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    flow_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("flow.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    external_event_id: str = Field(max_length=255)
    trigger_type: str = Field(default=ChannelExecutionTrigger.DEFAULT.value, max_length=32)
    command_name: str | None = Field(default=None, max_length=33)
    status: str = Field(default=ChannelExecutionStatus.RUNNING.value, max_length=32, index=True)
    duration_ms: int | None = None
    error_message: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))


class ChannelExecutionLogRead(SQLModel):
    id: UUID
    connection_id: UUID
    conversation_binding_id: UUID | None = None
    openxflow_user_id: UUID | None = None
    flow_id: UUID | None = None
    external_event_id: str
    trigger_type: str
    command_name: str | None = None
    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class ChannelExecutionLogPage(SQLModel):
    items: list[ChannelExecutionLogRead]
    page: int
    page_size: int
    total: int
    total_pages: int
