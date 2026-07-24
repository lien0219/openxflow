"""add channel gateway schema

Revision ID: c4a9e2d7f1b0
Revises: e1705947c729
Create Date: 2026-07-22 21:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from langflow.utils import migration

revision: str = "c4a9e2d7f1b0"  # pragma: allowlist secret
down_revision: str | None = "e1705947c729"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _create_index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if name not in {index["name"] for index in inspector.get_indexes(table)}:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    conn = op.get_bind()

    if not migration.table_exists("channel_connection", conn):
        op.create_table(
            "channel_connection",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False),
            sa.Column("connection_mode", sa.String(length=32), nullable=False),
            sa.Column("settings_data", _JSON, nullable=False),
            sa.Column("credentials_encrypted", sa.String(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "name", name="uq_channel_connection_user_name"),
        )
    _create_index("ix_channel_connection_user_id", "channel_connection", ["user_id"])
    _create_index("ix_channel_connection_channel_type", "channel_connection", ["channel_type"])
    _create_index("ix_channel_connection_status", "channel_connection", ["status"])

    if not migration.table_exists("channel_identity", conn):
        op.create_table(
            "channel_identity",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("openxflow_user_id", sa.Uuid(), nullable=False),
            sa.Column("external_user_id", sa.String(length=255), nullable=False),
            sa.Column("external_tenant_id", sa.String(length=255), nullable=False),
            sa.Column("external_union_id", sa.String(length=255), nullable=True),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("profile_data", _JSON, nullable=False),
            sa.Column("bound_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["openxflow_user_id"], ["user.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_tenant_id",
                "external_user_id",
                name="uq_channel_identity_external_user",
            ),
        )
    _create_index("ix_channel_identity_connection_id", "channel_identity", ["connection_id"])
    _create_index("ix_channel_identity_openxflow_user_id", "channel_identity", ["openxflow_user_id"])

    if not migration.table_exists("channel_conversation_binding", conn):
        op.create_table(
            "channel_conversation_binding",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("external_conversation_id", sa.String(length=255), nullable=False),
            sa.Column("conversation_type", sa.String(length=32), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("response_mode", sa.String(length=32), nullable=False),
            sa.Column("allow_file_upload", sa.Boolean(), nullable=False),
            sa.Column("settings_data", _JSON, nullable=False),
            sa.Column("default_flow_id", sa.Uuid(), nullable=True),
            sa.Column("knowledge_base_id", sa.Uuid(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["default_flow_id"], ["flow.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_base.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_conversation_id",
                name="uq_channel_conversation_external_id",
            ),
        )
    _create_index("ix_channel_conversation_binding_connection_id", "channel_conversation_binding", ["connection_id"])
    _create_index(
        "ix_channel_conversation_binding_default_flow_id",
        "channel_conversation_binding",
        ["default_flow_id"],
    )
    _create_index(
        "ix_channel_conversation_binding_knowledge_base_id",
        "channel_conversation_binding",
        ["knowledge_base_id"],
    )

    if not migration.table_exists("channel_event_receipt", conn):
        op.create_table(
            "channel_event_receipt",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("external_event_id", sa.String(length=255), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("trace_id", sa.Uuid(), nullable=False),
            sa.Column("payload_digest", sa.String(length=64), nullable=True),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_event_id",
                name="uq_channel_event_receipt_external_event",
            ),
        )
    _create_index("ix_channel_event_receipt_connection_id", "channel_event_receipt", ["connection_id"])
    _create_index("ix_channel_event_receipt_status", "channel_event_receipt", ["status"])
    _create_index("ix_channel_event_receipt_trace_id", "channel_event_receipt", ["trace_id"])

    if not migration.table_exists("channel_binding_code", conn):
        op.create_table(
            "channel_binding_code",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("external_user_id", sa.String(length=255), nullable=False),
            sa.Column("external_tenant_id", sa.String(length=255), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("profile_data", _JSON, nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("code_hash", name="uq_channel_binding_code_hash"),
        )
    _create_index("ix_channel_binding_code_connection_id", "channel_binding_code", ["connection_id"])
    _create_index("ix_channel_binding_code_external_user_id", "channel_binding_code", ["external_user_id"])
    _create_index("ix_channel_binding_code_code_hash", "channel_binding_code", ["code_hash"])
    _create_index("ix_channel_binding_code_expires_at", "channel_binding_code", ["expires_at"])


def downgrade() -> None:
    conn = op.get_bind()
    for table in (
        "channel_binding_code",
        "channel_event_receipt",
        "channel_conversation_binding",
        "channel_identity",
        "channel_connection",
    ):
        if migration.table_exists(table, conn):
            op.drop_table(table)
