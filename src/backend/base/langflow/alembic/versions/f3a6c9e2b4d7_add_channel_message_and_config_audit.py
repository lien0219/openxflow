"""add channel message center and configuration audit

Revision ID: f3a6c9e2b4d7
Revises: e2f5a8c1d7b9
Create Date: 2026-07-26 20:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from langflow.utils import migration

revision: str = "f3a6c9e2b4d7"  # pragma: allowlist secret
down_revision: str | None = "e2f5a8c1d7b9"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    json_type = sa.JSON().with_variant(JSONB(), "postgresql")

    if not migration.table_exists("channel_message_record", conn):
        op.create_table(
            "channel_message_record",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=True),
            sa.Column("execution_id", sa.Uuid(), nullable=True),
            sa.Column("external_event_id", sa.String(length=255), nullable=False),
            sa.Column("external_message_id", sa.String(length=1024), nullable=True),
            sa.Column("provider_message_id", sa.String(length=1024), nullable=True),
            sa.Column("external_conversation_id", sa.String(length=255), nullable=False),
            sa.Column("conversation_scope_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("external_user_id", sa.String(length=255), nullable=True),
            sa.Column("sender_name", sa.String(length=255), nullable=True),
            sa.Column("direction", sa.String(length=16), nullable=False),
            sa.Column("message_kind", sa.String(length=32), nullable=False),
            sa.Column("message_type", sa.String(length=64), nullable=False, server_default="text"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="received"),
            sa.Column("text", sa.Text(), nullable=True),
            sa.Column("has_attachments", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("attachment_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reply_to_message_id", sa.String(length=1024), nullable=True),
            sa.Column("error_code", sa.String(length=128), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("metadata_data", json_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"],
                ["channel_conversation_binding.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["execution_id"], ["channel_execution_log.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_event_id",
                "direction",
                "message_kind",
                name="uq_channel_message_event_direction_kind",
            ),
        )
        for name, columns in (
            ("ix_channel_message_record_connection_id", ["connection_id"]),
            ("ix_channel_message_record_conversation_binding_id", ["conversation_binding_id"]),
            ("ix_channel_message_record_execution_id", ["execution_id"]),
            ("ix_channel_message_record_external_conversation_id", ["external_conversation_id"]),
            ("ix_channel_message_record_external_user_id", ["external_user_id"]),
            ("ix_channel_message_record_direction", ["direction"]),
            ("ix_channel_message_record_status", ["status"]),
            ("ix_channel_message_connection_created", ["connection_id", "created_at"]),
            (
                "ix_channel_message_conversation_created",
                ["connection_id", "external_conversation_id", "created_at"],
            ),
            ("ix_channel_message_user_created", ["connection_id", "external_user_id", "created_at"]),
            ("ix_channel_message_status_created", ["connection_id", "status", "created_at"]),
        ):
            op.create_index(name, "channel_message_record", columns, unique=False)

    if not migration.table_exists("channel_configuration_audit", conn):
        op.create_table(
            "channel_configuration_audit",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=True),
            sa.Column("connection_reference", sa.Uuid(), nullable=False),
            sa.Column("actor_user_id", sa.Uuid(), nullable=True),
            sa.Column("action", sa.String(length=64), nullable=False),
            sa.Column("resource_type", sa.String(length=64), nullable=False),
            sa.Column("resource_id", sa.String(length=255), nullable=True),
            sa.Column("before_data", json_type, nullable=False),
            sa.Column("after_data", json_type, nullable=False),
            sa.Column("changes_data", json_type, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, columns in (
            ("ix_channel_configuration_audit_connection_id", ["connection_id"]),
            ("ix_channel_configuration_audit_connection_reference", ["connection_reference"]),
            ("ix_channel_configuration_audit_actor_user_id", ["actor_user_id"]),
            ("ix_channel_configuration_audit_action", ["action"]),
            ("ix_channel_configuration_audit_resource_type", ["resource_type"]),
            ("ix_channel_configuration_audit_resource_id", ["resource_id"]),
            ("ix_channel_audit_connection_created", ["connection_reference", "created_at"]),
            ("ix_channel_audit_actor_created", ["actor_user_id", "created_at"]),
            ("ix_channel_audit_resource_created", ["resource_type", "resource_id", "created_at"]),
        ):
            op.create_index(name, "channel_configuration_audit", columns, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_configuration_audit", conn):
        op.drop_table("channel_configuration_audit")
    if migration.table_exists("channel_message_record", conn):
        op.drop_table("channel_message_record")
