from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if new in content:
        return
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected one match in {path}, found {count}: {old[:120]!r}")
    write(path, content.replace(old, new, 1))


MODEL = "src/backend/base/langflow/services/database/models/channel/model.py"
EXECUTION = "src/backend/base/langflow/services/database/models/channel/execution_model.py"
WEBHOOK_JOB = "src/backend/base/langflow/services/database/models/channel/webhook_job_model.py"
CHANNEL_INIT = "src/backend/base/langflow/services/database/models/channel/__init__.py"
MODELS_INIT = "src/backend/base/langflow/services/database/models/__init__.py"

replace_once(
    MODEL,
    """class ChannelIdentityStatus(str, Enum):
    PENDING = "pending"
    BOUND = "bound"
    DISABLED = "disabled"
""",
    """class ChannelIdentityStatus(str, Enum):
    DISCOVERED = "discovered"
    PENDING = "pending"
    BOUND = "bound"
    DISABLED = "disabled"
""",
)

replace_once(
    MODEL,
    """class ChannelUnconfiguredBehavior(str, Enum):
    USE_GLOBAL_DEFAULT = "use_global_default"
    NOTIFY_PENDING = "notify_pending"
    IGNORE = "ignore"


class ChannelConnectionBase(SQLModel):
""",
    """class ChannelUnconfiguredBehavior(str, Enum):
    USE_GLOBAL_DEFAULT = "use_global_default"
    NOTIFY_PENDING = "notify_pending"
    IGNORE = "ignore"


class ChannelAccessPolicy(str, Enum):
    SHARED = "shared"
    BOUND_ONLY = "bound_only"
    HYBRID = "hybrid"
    INHERIT = "inherit"


class ChannelContextMode(str, Enum):
    ISOLATED = "isolated"
    SHARED = "shared"
    HYBRID = "hybrid"
    INHERIT = "inherit"


class ChannelConnectionBase(SQLModel):
""",
)

replace_once(
    MODEL,
    """    default_response_mode: str = Field(default="mentions_only", max_length=32)
    default_allow_file_upload: bool = Field(default=True)
    settings_data: dict[str, Any] = Field(
""",
    """    default_response_mode: str = Field(default="mentions_only", max_length=32)
    default_allow_file_upload: bool = Field(default=True)
    access_policy: str = Field(default=ChannelAccessPolicy.HYBRID.value, max_length=32)
    default_context_mode: str = Field(default=ChannelContextMode.ISOLATED.value, max_length=32)
    max_concurrency: int = Field(default=10, ge=1, le=100)
    per_user_concurrency: int = Field(default=1, ge=1, le=10)
    per_user_queue_limit: int = Field(default=3, ge=1, le=100)
    rate_limit_per_minute: int = Field(default=20, ge=0, le=10000)
    daily_quota: int = Field(default=0, ge=0)
    task_timeout_seconds: int = Field(default=120, ge=10, le=3600)
    queue_timeout_seconds: int = Field(default=60, ge=5, le=3600)
    shared_context_window: int = Field(default=20, ge=0, le=100)
    context_retention_days: int = Field(default=30, ge=1, le=365)
    settings_data: dict[str, Any] = Field(
""",
)

replace_once(
    MODEL,
    """    default_flow_id: UUID | None = Field(
""",
    """    service_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    default_flow_id: UUID | None = Field(
""",
)

replace_once(
    MODEL,
    """class ChannelConnectionCreate(ChannelConnectionBase):
    credentials: dict[str, str] = Field(default_factory=dict)
    default_flow_id: UUID | None = None
""",
    """class ChannelConnectionCreate(ChannelConnectionBase):
    credentials: dict[str, str] = Field(default_factory=dict)
    service_user_id: UUID | None = None
    default_flow_id: UUID | None = None
""",
)

replace_once(
    MODEL,
    """    default_flow_id: UUID | None = None
    default_knowledge_base_id: UUID | None = None
    auto_discover_conversations: bool | None = None
""",
    """    service_user_id: UUID | None = None
    default_flow_id: UUID | None = None
    default_knowledge_base_id: UUID | None = None
    auto_discover_conversations: bool | None = None
""",
)

replace_once(
    MODEL,
    """    default_allow_file_upload: bool | None = None
    settings_data: dict[str, Any] | None = None
""",
    """    default_allow_file_upload: bool | None = None
    access_policy: str | None = Field(default=None, max_length=32)
    default_context_mode: str | None = Field(default=None, max_length=32)
    max_concurrency: int | None = Field(default=None, ge=1, le=100)
    per_user_concurrency: int | None = Field(default=None, ge=1, le=10)
    per_user_queue_limit: int | None = Field(default=None, ge=1, le=100)
    rate_limit_per_minute: int | None = Field(default=None, ge=0, le=10000)
    daily_quota: int | None = Field(default=None, ge=0)
    task_timeout_seconds: int | None = Field(default=None, ge=10, le=3600)
    queue_timeout_seconds: int | None = Field(default=None, ge=5, le=3600)
    shared_context_window: int | None = Field(default=None, ge=0, le=100)
    context_retention_days: int | None = Field(default=None, ge=1, le=365)
    settings_data: dict[str, Any] | None = None
""",
)

replace_once(
    MODEL,
    """class ChannelConnectionRead(ChannelConnectionBase):
    id: UUID
    user_id: UUID
    default_flow_id: UUID | None = None
""",
    """class ChannelConnectionRead(ChannelConnectionBase):
    id: UUID
    user_id: UUID
    service_user_id: UUID | None = None
    default_flow_id: UUID | None = None
""",
)

replace_once(
    MODEL,
    """    status: str = Field(default=ChannelIdentityStatus.BOUND.value, max_length=32)
""",
    """    status: str = Field(default=ChannelIdentityStatus.DISCOVERED.value, max_length=32)
""",
)

replace_once(
    MODEL,
    """    openxflow_user_id: UUID = Field(
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
""",
    """    openxflow_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            sa.Uuid(),
            ForeignKey("user.id", ondelete="SET NULL"),
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
    bound_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: datetime = Field(
""",
)

replace_once(
    MODEL,
    """class ChannelIdentityCreate(ChannelIdentityBase):
    openxflow_user_id: UUID


class ChannelIdentityRead(ChannelIdentityBase):
    id: UUID
    connection_id: UUID
    openxflow_user_id: UUID
    bound_at: datetime
    updated_at: datetime
""",
    """class ChannelIdentityCreate(ChannelIdentityBase):
    openxflow_user_id: UUID | None = None


class ChannelIdentityRead(ChannelIdentityBase):
    id: UUID
    connection_id: UUID
    openxflow_user_id: UUID | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    last_message_at: datetime
    bound_at: datetime | None = None
    updated_at: datetime
""",
)

replace_once(
    MODEL,
    """    source: str = Field(default=ChannelConversationSource.LEGACY_MANUAL.value, max_length=32)
    settings_data: dict[str, Any] = Field(
""",
    """    source: str = Field(default=ChannelConversationSource.LEGACY_MANUAL.value, max_length=32)
    access_policy: str = Field(default=ChannelAccessPolicy.INHERIT.value, max_length=32)
    context_mode: str = Field(default=ChannelContextMode.INHERIT.value, max_length=32)
    settings_data: dict[str, Any] = Field(
""",
)

replace_once(
    MODEL,
    """    status: str | None = Field(default=None, max_length=32)
    default_flow_id: UUID | None = None
""",
    """    status: str | None = Field(default=None, max_length=32)
    access_policy: str | None = Field(default=None, max_length=32)
    context_mode: str | None = Field(default=None, max_length=32)
    default_flow_id: UUID | None = None
""",
)

replace_once(
    EXECUTION,
    """class ChannelExecutionStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
""",
    """class ChannelExecutionStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    DELIVERY_FAILED = "delivery_failed"


class ChannelExecutionIdentityType(str, Enum):
    SERVICE = "service"
    BOUND_USER = "bound_user"
""",
)

replace_once(
    EXECUTION,
    """        sa.Index("ix_channel_execution_status_created", "status", "created_at"),
""",
    """        sa.Index("ix_channel_execution_status_created", "status", "created_at"),
        sa.Index("ix_channel_execution_external_user_created", "connection_id", "external_user_id", "created_at"),
""",
)

replace_once(
    EXECUTION,
    """    flow_id: UUID | None = Field(
""",
    """    external_user_id: str | None = Field(default=None, max_length=255, index=True)
    session_id: str | None = Field(default=None, max_length=255, index=True)
    execution_identity_type: str = Field(
        default=ChannelExecutionIdentityType.BOUND_USER.value,
        max_length=32,
    )
    flow_id: UUID | None = Field(
""",
)

replace_once(
    EXECUTION,
    """    duration_ms: int | None = None
    error_message: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    created_at: datetime = Field(
""",
    """    queue_wait_ms: int | None = None
    duration_ms: int | None = None
    delivery_duration_ms: int | None = None
    retry_count: int = Field(default=0, ge=0)
    error_code: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, sa_column=Column(Text(), nullable=True))
    created_at: datetime = Field(
""",
)

replace_once(
    EXECUTION,
    """    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
""",
    """    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
    completed_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True), nullable=True))
""",
)

replace_once(
    EXECUTION,
    """    openxflow_user_id: UUID | None = None
    flow_id: UUID | None = None
""",
    """    openxflow_user_id: UUID | None = None
    external_user_id: str | None = None
    session_id: str | None = None
    execution_identity_type: str
    flow_id: UUID | None = None
""",
)

replace_once(
    EXECUTION,
    """    status: str
    duration_ms: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
""",
    """    status: str
    queue_wait_ms: int | None = None
    duration_ms: int | None = None
    delivery_duration_ms: int | None = None
    retry_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
""",
)

replace_once(
    WEBHOOK_JOB,
    """class ChannelWebhookJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
""",
    """class ChannelWebhookJobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
""",
)

replace_once(
    WEBHOOK_JOB,
    """        Index("ix_channel_webhook_job_lease", "status", "lease_expires_at"),
""",
    """        Index("ix_channel_webhook_job_lease", "status", "lease_expires_at"),
        Index("ix_channel_webhook_job_queue", "queue_key", "status", "created_at"),
        Index("ix_channel_webhook_job_connection_status", "connection_id", "status", "created_at"),
        Index("ix_channel_webhook_job_user_created", "connection_id", "external_user_id", "created_at"),
""",
)

replace_once(
    WEBHOOK_JOB,
    """    channel_type: str = Field(nullable=False, max_length=32)
    external_event_id: str = Field(nullable=False, max_length=255)
""",
    """    channel_type: str = Field(nullable=False, max_length=32)
    external_event_id: str = Field(nullable=False, max_length=255)
    external_conversation_id: str = Field(default="", nullable=False, max_length=255)
    external_user_id: str = Field(default="", nullable=False, max_length=255)
    conversation_type: str = Field(default="private", nullable=False, max_length=32)
    queue_key: str = Field(default="", nullable=False, max_length=768)
""",
)

context_model = '''"""Bounded public conversation context used by shared and hybrid channel modes."""

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
'''
write("src/backend/base/langflow/services/database/models/channel/context_model.py", context_model)

replace_once(
    CHANNEL_INIT,
    """from langflow.services.database.models.channel.execution_model import (
""",
    """from langflow.services.database.models.channel.context_model import (
    ChannelContextRole,
    ChannelConversationContextEntry,
)
from langflow.services.database.models.channel.execution_model import (
""",
)
replace_once(
    CHANNEL_INIT,
    """    ChannelExecutionLogRead,
    ChannelExecutionStatus,
""",
    """    ChannelExecutionIdentityType,
    ChannelExecutionLogRead,
    ChannelExecutionStatus,
""",
)
replace_once(
    CHANNEL_INIT,
    """    ChannelConnection,
""",
    """    ChannelAccessPolicy,
    ChannelConnection,
""",
)
replace_once(
    CHANNEL_INIT,
    """    ChannelConversationStatus,
""",
    """    ChannelContextMode,
    ChannelConversationStatus,
""",
)
replace_once(
    CHANNEL_INIT,
    """    "ChannelBindingCode",
""",
    """    "ChannelAccessPolicy",
    "ChannelBindingCode",
""",
)
replace_once(
    CHANNEL_INIT,
    """    "ChannelConversationBindingUpsert",
""",
    """    "ChannelConversationBindingUpsert",
    "ChannelConversationContextEntry",
    "ChannelContextMode",
    "ChannelContextRole",
""",
)
replace_once(
    CHANNEL_INIT,
    """    "ChannelExecutionLogRead",
""",
    """    "ChannelExecutionIdentityType",
    "ChannelExecutionLogRead",
""",
)

replace_once(
    MODELS_INIT,
    """    ChannelConversationBinding,
""",
    """    ChannelConversationBinding,
    ChannelConversationContextEntry,
""",
)
replace_once(
    MODELS_INIT,
    """    "ChannelConversationBinding",
""",
    """    "ChannelConversationBinding",
    "ChannelConversationContextEntry",
""",
)

migration = '''"""add production channel access, context, and queue controls

Revision ID: e2f5a8c1d7b9
Revises: d1e4f9a8b6c3
Create Date: 2026-07-25 10:00:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "e2f5a8c1d7b9"  # pragma: allowlist secret
down_revision: str | None = "d1e4f9a8b6c3"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _columns(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {column["name"] for column in sa.inspect(conn).get_columns(table_name)}


def _indexes(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def _add_column(table_name: str, column: sa.Column, conn) -> None:
    if column.name not in _columns(table_name, conn):
        op.add_column(table_name, column)


def _create_index(name: str, table_name: str, columns: list[str], conn) -> None:
    if name not in _indexes(table_name, conn):
        op.create_index(name, table_name, columns, unique=False)


def upgrade() -> None:
    conn = op.get_bind()

    for column in (
        sa.Column("service_user_id", sa.Uuid(), nullable=True),
        sa.Column("access_policy", sa.String(length=32), nullable=False, server_default="hybrid"),
        sa.Column("default_context_mode", sa.String(length=32), nullable=False, server_default="isolated"),
        sa.Column("max_concurrency", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("per_user_concurrency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("per_user_queue_limit", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("daily_quota", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("task_timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("queue_timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("shared_context_window", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("context_retention_days", sa.Integer(), nullable=False, server_default="30"),
    ):
        _add_column("channel_connection", column, conn)
    conn.execute(sa.text("UPDATE channel_connection SET service_user_id = user_id WHERE service_user_id IS NULL"))
    _create_index("ix_channel_connection_service_user_id", "channel_connection", ["service_user_id"], conn)

    for column in (
        sa.Column("access_policy", sa.String(length=32), nullable=False, server_default="inherit"),
        sa.Column("context_mode", sa.String(length=32), nullable=False, server_default="inherit"),
    ):
        _add_column("channel_conversation_binding", column, conn)

    identity_columns = _columns("channel_identity", conn)
    for column in (
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    ):
        _add_column("channel_identity", column, conn)
    conn.execute(
        sa.text(
            "UPDATE channel_identity SET first_seen_at = COALESCE(first_seen_at, bound_at, updated_at), "
            "last_seen_at = COALESCE(last_seen_at, updated_at, bound_at), "
            "last_message_at = COALESCE(last_message_at, updated_at, bound_at)"
        )
    )
    with op.batch_alter_table("channel_identity") as batch:
        if "openxflow_user_id" in identity_columns:
            batch.alter_column("openxflow_user_id", existing_type=sa.Uuid(), nullable=True)
        if "bound_at" in identity_columns:
            batch.alter_column("bound_at", existing_type=sa.DateTime(timezone=True), nullable=True)
        batch.alter_column("first_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("last_seen_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch.alter_column("last_message_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    for column in (
        sa.Column("external_user_id", sa.String(length=255), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("execution_identity_type", sa.String(length=32), nullable=False, server_default="bound_user"),
        sa.Column("queue_wait_ms", sa.Integer(), nullable=True),
        sa.Column("delivery_duration_ms", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    ):
        _add_column("channel_execution_log", column, conn)
    _create_index("ix_channel_execution_external_user_id", "channel_execution_log", ["external_user_id"], conn)
    _create_index("ix_channel_execution_session_id", "channel_execution_log", ["session_id"], conn)
    _create_index(
        "ix_channel_execution_external_user_created",
        "channel_execution_log",
        ["connection_id", "external_user_id", "created_at"],
        conn,
    )

    for column in (
        sa.Column("external_conversation_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("external_user_id", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("conversation_type", sa.String(length=32), nullable=False, server_default="private"),
        sa.Column("queue_key", sa.String(length=768), nullable=False, server_default=""),
    ):
        _add_column("channel_webhook_job", column, conn)
    conn.execute(
        sa.text(
            "UPDATE channel_webhook_job SET queue_key = CAST(connection_id AS VARCHAR) || ':legacy:' || external_event_id "
            "WHERE queue_key = ''"
        )
    )
    _create_index(
        "ix_channel_webhook_job_queue",
        "channel_webhook_job",
        ["queue_key", "status", "created_at"],
        conn,
    )
    _create_index(
        "ix_channel_webhook_job_connection_status",
        "channel_webhook_job",
        ["connection_id", "status", "created_at"],
        conn,
    )
    _create_index(
        "ix_channel_webhook_job_user_created",
        "channel_webhook_job",
        ["connection_id", "external_user_id", "created_at"],
        conn,
    )

    if not migration.table_exists("channel_conversation_context_entry", conn):
        op.create_table(
            "channel_conversation_context_entry",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=False),
            sa.Column("external_event_id", sa.String(length=255), nullable=False),
            sa.Column("external_user_id", sa.String(length=255), nullable=False),
            sa.Column("sender_name", sa.String(length=255), nullable=True),
            sa.Column("role", sa.String(length=32), nullable=False),
            sa.Column("session_id", sa.String(length=255), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"],
                ["channel_conversation_binding.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_event_id",
                "role",
                name="uq_channel_context_event_role",
            ),
        )
        op.create_index(
            "ix_channel_context_conversation_created",
            "channel_conversation_context_entry",
            ["conversation_binding_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_channel_context_connection_created",
            "channel_conversation_context_entry",
            ["connection_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_channel_conversation_context_entry_connection_id",
            "channel_conversation_context_entry",
            ["connection_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_conversation_context_entry_conversation_binding_id",
            "channel_conversation_context_entry",
            ["conversation_binding_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_conversation_context_entry_external_user_id",
            "channel_conversation_context_entry",
            ["external_user_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_conversation_context_entry_session_id",
            "channel_conversation_context_entry",
            ["session_id"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_conversation_context_entry", conn):
        op.drop_table("channel_conversation_context_entry")

    for table_name, columns in (
        (
            "channel_webhook_job",
            ["queue_key", "conversation_type", "external_user_id", "external_conversation_id"],
        ),
        (
            "channel_execution_log",
            [
                "started_at",
                "error_code",
                "retry_count",
                "delivery_duration_ms",
                "queue_wait_ms",
                "execution_identity_type",
                "session_id",
                "external_user_id",
            ],
        ),
        ("channel_conversation_binding", ["context_mode", "access_policy"]),
        (
            "channel_connection",
            [
                "context_retention_days",
                "shared_context_window",
                "queue_timeout_seconds",
                "task_timeout_seconds",
                "daily_quota",
                "rate_limit_per_minute",
                "per_user_queue_limit",
                "per_user_concurrency",
                "max_concurrency",
                "default_context_mode",
                "access_policy",
                "service_user_id",
            ],
        ),
    ):
        existing = _columns(table_name, conn)
        with op.batch_alter_table(table_name) as batch:
            for column in columns:
                if column in existing:
                    batch.drop_column(column)

    if migration.table_exists("channel_identity", conn):
        conn.execute(sa.text("DELETE FROM channel_identity WHERE openxflow_user_id IS NULL"))
        with op.batch_alter_table("channel_identity") as batch:
            batch.alter_column("openxflow_user_id", existing_type=sa.Uuid(), nullable=False)
            batch.alter_column("bound_at", existing_type=sa.DateTime(timezone=True), nullable=False)
            for column in ("last_message_at", "last_seen_at", "first_seen_at"):
                if column in _columns("channel_identity", conn):
                    batch.drop_column(column)
'''
write(
    "src/backend/base/langflow/alembic/versions/e2f5a8c1d7b9_add_channel_production_controls.py",
    migration,
)

model_test = """from uuid import uuid4

from langflow.services.database.models.channel.context_model import (
    ChannelContextRole,
    ChannelConversationContextEntry,
)
from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionIdentityType,
    ChannelExecutionStatus,
)
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelConnectionCreate,
    ChannelContextMode,
    ChannelIdentityStatus,
)
from langflow.services.database.models.channel.webhook_job_model import ChannelWebhookJob


def test_production_channel_policy_defaults() -> None:
    payload = ChannelConnectionCreate(
        name="Production",
        channel_type="feishu",
        credentials={},
    )
    assert payload.access_policy == ChannelAccessPolicy.HYBRID.value
    assert payload.default_context_mode == ChannelContextMode.ISOLATED.value
    assert payload.max_concurrency == 10
    assert payload.per_user_concurrency == 1
    assert payload.per_user_queue_limit == 3
    assert payload.rate_limit_per_minute == 20
    assert payload.daily_quota == 0
    assert payload.task_timeout_seconds == 120
    assert payload.queue_timeout_seconds == 60
    assert payload.shared_context_window == 20
    assert payload.context_retention_days == 30


def test_channel_identity_and_execution_enums_cover_production_states() -> None:
    assert ChannelIdentityStatus.DISCOVERED.value == "discovered"
    assert ChannelExecutionIdentityType.SERVICE.value == "service"
    assert {status.value for status in ChannelExecutionStatus} >= {
        "queued",
        "running",
        "succeeded",
        "failed",
        "timeout",
        "cancelled",
        "delivery_failed",
    }


def test_webhook_jobs_store_stable_queue_scope() -> None:
    job = ChannelWebhookJob(
        connection_id=uuid4(),
        channel_type="feishu",
        external_event_id="evt-1",
        external_conversation_id="chat-1",
        external_user_id="user-1",
        conversation_type="group",
        queue_key="connection:chat:user",
        payload=b"{}",
    )
    assert job.queue_key == "connection:chat:user"


def test_context_entry_contract() -> None:
    entry = ChannelConversationContextEntry(
        connection_id=uuid4(),
        conversation_binding_id=uuid4(),
        external_event_id="evt-1",
        external_user_id="user-1",
        role=ChannelContextRole.USER.value,
        session_id="channel-session",
        text="hello",
    )
    assert entry.role == "user"
    assert entry.text == "hello"
"""
write("src/backend/tests/unit/channels/test_production_policy_models.py", model_test)

print("Applied production channel phase 1 model and migration changes")
