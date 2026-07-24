"""add channel workflow commands and execution logs

Revision ID: c0a3e8f7d5b2
Revises: b9f2d7e6c4a1
Create Date: 2026-07-24 19:10:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from langflow.utils import migration

revision: str = "c0a3e8f7d5b2"  # pragma: allowlist secret
down_revision: str | None = "b9f2d7e6c4a1"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    conn = op.get_bind()

    if not migration.table_exists("channel_workflow_command", conn):
        op.create_table(
            "channel_workflow_command",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=True),
            sa.Column("owner_user_id", sa.Uuid(), nullable=True),
            sa.Column("created_by", sa.Uuid(), nullable=False),
            sa.Column("flow_id", sa.Uuid(), nullable=False),
            sa.Column("command", sa.String(length=33), nullable=False),
            sa.Column("normalized_command", sa.String(length=33), nullable=False),
            sa.Column("aliases", JsonVariant, server_default=sa.text("'[]'"), nullable=False),
            sa.Column("description", sa.String(length=500), nullable=True),
            sa.Column("scope_type", sa.String(length=32), nullable=False),
            sa.Column("scope_key", sa.String(length=255), nullable=False),
            sa.Column("prompt_template", sa.String(length=8000), nullable=True),
            sa.Column("input_required", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("allow_attachments", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("require_mention", sa.Boolean(), server_default=sa.false(), nullable=False),
            sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("settings_data", JsonVariant, server_default=sa.text("'{}'"), nullable=False),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"],
                ["channel_conversation_binding.id"],
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(["owner_user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["flow_id"], ["flow.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "scope_key",
                "normalized_command",
                name="uq_channel_workflow_command_scope_command",
            ),
        )
        op.create_index(
            "ix_channel_workflow_command_connection_id",
            "channel_workflow_command",
            ["connection_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_conversation_binding_id",
            "channel_workflow_command",
            ["conversation_binding_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_owner_user_id",
            "channel_workflow_command",
            ["owner_user_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_created_by",
            "channel_workflow_command",
            ["created_by"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_normalized_command",
            "channel_workflow_command",
            ["normalized_command"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_connection_scope",
            "channel_workflow_command",
            ["connection_id", "scope_type", "enabled"],
            unique=False,
        )
        op.create_index(
            "ix_channel_workflow_command_flow_id",
            "channel_workflow_command",
            ["flow_id"],
            unique=False,
        )

    if not migration.table_exists("channel_execution_log", conn):
        op.create_table(
            "channel_execution_log",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=True),
            sa.Column("openxflow_user_id", sa.Uuid(), nullable=True),
            sa.Column("flow_id", sa.Uuid(), nullable=True),
            sa.Column("external_event_id", sa.String(length=255), nullable=False),
            sa.Column("trigger_type", sa.String(length=32), nullable=False),
            sa.Column("command_name", sa.String(length=33), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"],
                ["channel_conversation_binding.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(["openxflow_user_id"], ["user.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["flow_id"], ["flow.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_channel_execution_log_connection_id",
            "channel_execution_log",
            ["connection_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_log_conversation_binding_id",
            "channel_execution_log",
            ["conversation_binding_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_log_openxflow_user_id",
            "channel_execution_log",
            ["openxflow_user_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_log_flow_id",
            "channel_execution_log",
            ["flow_id"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_log_status",
            "channel_execution_log",
            ["status"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_connection_created",
            "channel_execution_log",
            ["connection_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_conversation_created",
            "channel_execution_log",
            ["conversation_binding_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_user_created",
            "channel_execution_log",
            ["openxflow_user_id", "created_at"],
            unique=False,
        )
        op.create_index(
            "ix_channel_execution_status_created",
            "channel_execution_log",
            ["status", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_execution_log", conn):
        op.drop_table("channel_execution_log")
    if migration.table_exists("channel_workflow_command", conn):
        op.drop_table("channel_workflow_command")
