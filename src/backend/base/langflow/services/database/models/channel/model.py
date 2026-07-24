"""Database models for provider-neutral chat channel integrations."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa
from pydantic import field_validator
from sqlalchemy import JSON, Column, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

JsonVariant = JSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChannelConnectionStatus(StrEnum):
    CONFIGURING = "configuring"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class ChannelIdentityStatus(StrEnum):
    PENDING = "pending"
    BOUND = "bound"
    DISABLED = "disabled"


class ChannelReceiptStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class ChannelConversationStatus(StrEnum):
    PENDING = "pending"
    INHERITED = "inherited"
    OVERRIDDEN = "overridden"
    IGNORED = "ignored"
    DISABLED = "disabled"
    UNAVAILABLE = "unavailable"


class ChannelConversationRouteMode(StrEnum):
    INHERIT = "inherit"
    OVERRIDE = "override"
    DISABLED = "disabled"


class ChannelConversationSource(StrEnum):
    AUTO_DISCOVERED = "auto_discovered"
    LEGACY_MANUAL = "legacy_manual"


class ChannelUnconfiguredBehavior(StrEnum):
    USE_GLOBAL_DEFAULT = "use_global_default"
    NOTIFY_PENDING = "notify_pending"
    IGNORE = "ignore"


class ChannelConnectionBase(SQLModel):
    name: str = Field(min_length=1, max_length=128)
    channel_type: str = Field(index=True, max_length=32)
    enabled: bool = Field(default=True)

    @field_validator("channel_type")
    @classmethod
    def validate_channel_type(cls, value: str) -> str:
        allowed = {"telegram", "feishu", "dingtalk", "wecom", "mock"}
        normalized = value.strip().lower()
        if normalized not in allowed:
            msg = f"Unsupported channel type: {value}"
            raise ValueError(msg)
        return normalized

    connection_mode: str = Field(default="webhook", max_length=32)
    auto_discover_conversations: bool = Field(default=True)
    unconfigured_behavior: str = Field(default=ChannelUnconfiguredBehavior.NOTIFY_PENDING.value, max_length=32)
    pending_notice_enabled: bool = Field(default=True)
    personal_commands_enabled: bool = Field(default=True)
    default_response_mode: str = Field(default="mentions_only", max_length=32)
    default_allow_file_upload: bool = Field(default=True)
    settings_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )


class ChannelConnection(ChannelConnectionBase, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_connection"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_channel_connection_user_name"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    default_flow_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("flow.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    default_knowledge_base_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("knowledge_base.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    credentials_encrypted: str = Field(nullable=False)
    status: str = Field(default=ChannelConnectionStatus.CONFIGURING.value, index=True, max_length=32)
    last_connected_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelConnectionCreate(ChannelConnectionBase):
    credentials: dict[str, str] = Field(default_factory=dict)
    default_flow_id: UUID | None = None
    default_knowledge_base_id: UUID | None = None

    @field_validator("credentials")
    @classmethod
    def validate_credentials(cls, value: dict[str, str]) -> dict[str, str]:
        if any(not isinstance(item, str) for item in value.values()):
            msg = "Channel credential values must be strings"
            raise ValueError(msg)
        return value


class ChannelConnectionUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    enabled: bool | None = None
    connection_mode: str | None = Field(default=None, max_length=32)
    default_flow_id: UUID | None = None
    default_knowledge_base_id: UUID | None = None
    auto_discover_conversations: bool | None = None
    unconfigured_behavior: str | None = Field(default=None, max_length=32)
    pending_notice_enabled: bool | None = None
    personal_commands_enabled: bool | None = None
    default_response_mode: str | None = Field(default=None, max_length=32)
    default_allow_file_upload: bool | None = None
    settings_data: dict[str, Any] | None = None
    credentials: dict[str, str] | None = None


class ChannelConnectionRead(ChannelConnectionBase):
    id: UUID
    user_id: UUID
    default_flow_id: UUID | None = None
    default_knowledge_base_id: UUID | None = None
    status: str
    configured_credential_keys: list[str] = Field(default_factory=list)
    last_connected_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime


class ChannelIdentityBase(SQLModel):
    external_user_id: str = Field(min_length=1, max_length=255)
    external_tenant_id: str = Field(default="", max_length=255)
    external_union_id: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=255)
    status: str = Field(default=ChannelIdentityStatus.BOUND.value, max_length=32)
    profile_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )


class ChannelIdentity(ChannelIdentityBase, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_identity"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_tenant_id",
            "external_user_id",
            name="uq_channel_identity_external_user",
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
    bound_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelIdentityCreate(ChannelIdentityBase):
    openxflow_user_id: UUID


class ChannelIdentityRead(ChannelIdentityBase):
    id: UUID
    connection_id: UUID
    openxflow_user_id: UUID
    bound_at: datetime
    updated_at: datetime


class ChannelConversationBindingBase(SQLModel):
    external_conversation_id: str = Field(min_length=1, max_length=255)
    conversation_type: str = Field(default="private", max_length=32)
    display_name: str | None = Field(default=None, max_length=255)
    response_mode: str = Field(default="mentions_only", max_length=32)
    allow_file_upload: bool = Field(default=True)
    route_mode: str = Field(default=ChannelConversationRouteMode.INHERIT.value, max_length=32)
    status: str = Field(default=ChannelConversationStatus.PENDING.value, max_length=32, index=True)
    source: str = Field(default=ChannelConversationSource.LEGACY_MANUAL.value, max_length=32)
    settings_data: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )
    provider_metadata: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JsonVariant, nullable=False),
    )


class ChannelConversationBinding(ChannelConversationBindingBase, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_conversation_binding"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_conversation_id",
            name="uq_channel_conversation_external_id",
        ),
        sa.Index("ix_channel_conversation_connection_last_message", "connection_id", "last_message_at"),
        sa.Index("ix_channel_conversation_connection_status", "connection_id", "status", "last_message_at"),
        sa.Index(
            "ix_channel_conversation_connection_type",
            "connection_id",
            "conversation_type",
            "last_message_at",
        ),
        sa.Index("ix_channel_conversation_connection_route", "connection_id", "route_mode", "last_message_at"),
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
    default_flow_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("flow.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
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
    first_seen_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_seen_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    last_message_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    pending_notice_sent_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    ignored_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    disabled_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


class ChannelConversationBindingUpsert(ChannelConversationBindingBase):
    default_flow_id: UUID | None = None
    knowledge_base_id: UUID | None = None


class ChannelConversationBindingUpdate(SQLModel):
    display_name: str | None = Field(default=None, max_length=255)
    response_mode: str | None = Field(default=None, max_length=32)
    allow_file_upload: bool | None = None
    route_mode: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    default_flow_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    settings_data: dict[str, Any] | None = None


class ChannelConversationBindingRead(ChannelConversationBindingBase):
    id: UUID
    connection_id: UUID
    default_flow_id: UUID | None = None
    knowledge_base_id: UUID | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_message_at: datetime
    pending_notice_sent_at: datetime | None = None
    ignored_at: datetime | None = None
    disabled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ChannelConversationBindingPage(SQLModel):
    items: list[ChannelConversationBindingRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class ChannelEventReceipt(SQLModel, table=True):  # type: ignore[call-arg]
    __tablename__ = "channel_event_receipt"
    __table_args__ = (
        UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_channel_event_receipt_external_event",
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
    external_event_id: str = Field(nullable=False, max_length=255)
    event_type: str = Field(default="unknown", max_length=64)
    status: str = Field(default=ChannelReceiptStatus.RECEIVED.value, index=True, max_length=32)
    trace_id: UUID = Field(default_factory=uuid4, index=True)
    payload_digest: str | None = Field(default=None, max_length=64)
    error_message: str | None = Field(default=None, nullable=True)
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    processed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
