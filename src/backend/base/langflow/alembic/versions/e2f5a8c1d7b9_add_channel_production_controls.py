"""add production channel access, context, and queue controls

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
