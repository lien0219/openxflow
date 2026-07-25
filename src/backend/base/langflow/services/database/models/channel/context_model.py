"""Bounded public conversation context used by shared and hybrid channel modes."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel

from langflow.services.database.models.channel.model import utc_now


class ChannelContextRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChannelConversationContextEntry(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_conversation_context_entry"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            "role",
            name="uq_channel_context_event_role",
        ),
        sa.Index(
            "ix_channel_context_conversation_created",
            "conversation_binding_id",
            "created_at",
        ),
        sa.Index(
            "ix_channel_context_connection_created",
            "connection_id",
            "created_at",
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
    external_event_id: str = Field(max_length=255)
    external_user_id: str = Field(max_length=255, index=True)
    sender_name: str | None = Field(default=None, max_length=255)
    role: str = Field(max_length=32)
    session_id: str = Field(max_length=255, index=True)
    text: str = Field(sa_column=Column(Text(), nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
