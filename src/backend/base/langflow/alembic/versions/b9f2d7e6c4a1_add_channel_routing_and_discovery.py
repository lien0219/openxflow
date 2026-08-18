"""add channel routing and conversation discovery fields

Revision ID: b9f2d7e6c4a1
Revises: a8e1c6d4f5b7
Create Date: 2026-07-24 18:05:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from langflow.utils import migration

revision: str = "b9f2d7e6c4a1"  # pragma: allowlist secret
down_revision: str | None = "a8e1c6d4f5b7"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _index_exists(table_name: str, index_name: str, conn) -> bool:
    return index_name in {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def _add_column(table_name: str, column: sa.Column, conn) -> None:
    if migration.column_exists(table_name, column.name, conn):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


def _drop_column(table_name: str, column_name: str, conn) -> None:
    if not migration.column_exists(table_name, column_name, conn):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_column(column_name)


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_connection", conn):
        return

    _add_column("channel_connection", sa.Column("default_flow_id", sa.Uuid(), nullable=True), conn)
    _add_column("channel_connection", sa.Column("default_knowledge_base_id", sa.Uuid(), nullable=True), conn)
    _add_column(
        "channel_connection",
        sa.Column("auto_discover_conversations", sa.Boolean(), server_default=sa.true(), nullable=False),
        conn,
    )
    _add_column(
        "channel_connection",
        sa.Column(
            "unconfigured_behavior",
            sa.String(length=32),
            server_default="notify_pending",
            nullable=False,
        ),
        conn,
    )
    _add_column(
        "channel_connection",
        sa.Column("pending_notice_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        conn,
    )
    _add_column(
        "channel_connection",
        sa.Column("personal_commands_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        conn,
    )
    _add_column(
        "channel_connection",
        sa.Column("default_response_mode", sa.String(length=32), server_default="mentions_only", nullable=False),
        conn,
    )
    _add_column(
        "channel_connection",
        sa.Column("default_allow_file_upload", sa.Boolean(), server_default=sa.true(), nullable=False),
        conn,
    )

    if not migration.foreign_key_exists("channel_connection", "fk_channel_connection_default_flow_id", conn):
        with op.batch_alter_table("channel_connection") as batch_op:
            batch_op.create_foreign_key(
                "fk_channel_connection_default_flow_id",
                "flow",
                ["default_flow_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if not migration.foreign_key_exists(
        "channel_connection", "fk_channel_connection_default_knowledge_base_id", conn
    ):
        with op.batch_alter_table("channel_connection") as batch_op:
            batch_op.create_foreign_key(
                "fk_channel_connection_default_knowledge_base_id",
                "knowledge_base",
                ["default_knowledge_base_id"],
                ["id"],
                ondelete="SET NULL",
            )

    if not _index_exists("channel_connection", "ix_channel_connection_default_flow_id", conn):
        op.create_index(
            "ix_channel_connection_default_flow_id",
            "channel_connection",
            ["default_flow_id"],
            unique=False,
        )
    if not _index_exists("channel_connection", "ix_channel_connection_default_knowledge_base_id", conn):
        op.create_index(
            "ix_channel_connection_default_knowledge_base_id",
            "channel_connection",
            ["default_knowledge_base_id"],
            unique=False,
        )

    if not migration.table_exists("channel_conversation_binding", conn):
        return

    _add_column(
        "channel_conversation_binding",
        sa.Column("route_mode", sa.String(length=32), server_default="inherit", nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("status", sa.String(length=32), server_default="pending", nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("source", sa.String(length=32), server_default="legacy_manual", nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("provider_metadata", JsonVariant, server_default=sa.text("'{}'"), nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("pending_notice_sent_at", sa.DateTime(timezone=True), nullable=True),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("ignored_at", sa.DateTime(timezone=True), nullable=True),
        conn,
    )
    _add_column(
        "channel_conversation_binding",
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        conn,
    )

    op.execute(
        sa.text(
            "UPDATE channel_conversation_binding "
            "SET route_mode = 'override', status = 'overridden' "
            "WHERE default_flow_id IS NOT NULL"
        )
    )

    indexes = {
        "ix_channel_conversation_binding_status": ["status"],
        "ix_channel_conversation_connection_last_message": ["connection_id", "last_message_at"],
        "ix_channel_conversation_connection_status": ["connection_id", "status", "last_message_at"],
        "ix_channel_conversation_connection_type": ["connection_id", "conversation_type", "last_message_at"],
        "ix_channel_conversation_connection_route": ["connection_id", "route_mode", "last_message_at"],
    }
    for index_name, columns in indexes.items():
        if not _index_exists("channel_conversation_binding", index_name, conn):
            op.create_index(index_name, "channel_conversation_binding", columns, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_conversation_binding", conn):
        for index_name in (
            "ix_channel_conversation_binding_status",
            "ix_channel_conversation_connection_route",
            "ix_channel_conversation_connection_type",
            "ix_channel_conversation_connection_status",
            "ix_channel_conversation_connection_last_message",
        ):
            if _index_exists("channel_conversation_binding", index_name, conn):
                op.drop_index(index_name, table_name="channel_conversation_binding")
        for column_name in (
            "disabled_at",
            "ignored_at",
            "pending_notice_sent_at",
            "last_message_at",
            "last_seen_at",
            "first_seen_at",
            "provider_metadata",
            "source",
            "status",
            "route_mode",
        ):
            _drop_column("channel_conversation_binding", column_name, conn)

    if migration.table_exists("channel_connection", conn):
        if _index_exists("channel_connection", "ix_channel_connection_default_knowledge_base_id", conn):
            op.drop_index("ix_channel_connection_default_knowledge_base_id", table_name="channel_connection")
        if _index_exists("channel_connection", "ix_channel_connection_default_flow_id", conn):
            op.drop_index("ix_channel_connection_default_flow_id", table_name="channel_connection")
        for column_name in (
            "default_allow_file_upload",
            "default_response_mode",
            "personal_commands_enabled",
            "pending_notice_enabled",
            "unconfigured_behavior",
            "auto_discover_conversations",
            "default_knowledge_base_id",
            "default_flow_id",
        ):
            _drop_column("channel_connection", column_name, conn)
