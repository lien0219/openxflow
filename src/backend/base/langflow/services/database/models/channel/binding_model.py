"""Single-use account binding challenge model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class ChannelBindingCode(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_binding_code"
    __table_args__ = (UniqueConstraint("code_hash", name="uq_channel_binding_code_hash"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    connection_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("channel_connection.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    external_user_id: str = Field(index=True, max_length=255)
    external_tenant_id: str = Field(default="", max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    profile_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )
    code_hash: str = Field(index=True, max_length=64)
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    used_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
