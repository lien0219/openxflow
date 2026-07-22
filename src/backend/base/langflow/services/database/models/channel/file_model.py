"""Persistence for files received through external communication channels."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import JSON, BigInteger, Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


class ChannelFileStatus(StrEnum):
    RECEIVED = "received"
    STORED = "stored"
    INGESTING = "ingesting"
    READY = "ready"
    FAILED = "failed"


class ChannelFileAsset(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_file_asset"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_message_id",
            "external_file_id",
            name="uq_channel_file_asset_external_file",
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
    openxflow_user_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    external_conversation_id: str = Field(max_length=255, index=True)
    external_message_id: str = Field(max_length=255)
    external_file_id: str = Field(max_length=255)
    user_file_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.Uuid(), ForeignKey("file.id", ondelete="SET NULL"), nullable=True, index=True),
    )
    knowledge_base_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("knowledge_base.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    ingestion_job_id: UUID | None = Field(
        default=None,
        sa_column=Column(sa.Uuid(), ForeignKey("job.job_id", ondelete="SET NULL"), nullable=True, index=True),
    )
    filename: str = Field(max_length=255)
    mime_type: str | None = Field(default=None, max_length=255)
    size_bytes: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False, server_default="0"),
    )
    status: str = Field(default=ChannelFileStatus.RECEIVED.value, max_length=32, index=True)
    error_message: str | None = Field(default=None, nullable=True)
    metadata_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelFileAssetRead(SQLModel):
    id: UUID
    connection_id: UUID
    openxflow_user_id: UUID
    external_conversation_id: str
    external_message_id: str
    external_file_id: str
    user_file_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    ingestion_job_id: UUID | None = None
    filename: str
    mime_type: str | None = None
    size_bytes: int
    status: str
    error_message: str | None = None
    metadata_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
