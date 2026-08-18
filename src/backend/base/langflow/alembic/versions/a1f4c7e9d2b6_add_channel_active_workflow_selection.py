"""add persistent channel workflow selections

Revision ID: a1f4c7e9d2b6
Revises: b5d8e1f3a6c9
Create Date: 2026-07-29 20:00:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration

revision: str = "a1f4c7e9d2b6"  # pragma: allowlist secret
down_revision: str | None = "b5d8e1f3a6c9"  # pragma: allowlist secret
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


def _recreate_mode(conn) -> str:
    return "always" if conn.dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    conn = op.get_bind()

    connection_columns = _columns("channel_connection", conn)
    if connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            if "user_flow_selection_enabled" not in connection_columns:
                batch_op.add_column(
                    sa.Column("user_flow_selection_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
                )
            if "flow_selection_ttl_hours" not in connection_columns:
                batch_op.add_column(
                    sa.Column("flow_selection_ttl_hours", sa.Integer(), nullable=False, server_default="24")
                )

    command_columns = _columns("channel_workflow_command", conn)
    if command_columns and "allow_persistent_selection" not in command_columns:
        with op.batch_alter_table("channel_workflow_command", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.add_column(
                sa.Column("allow_persistent_selection", sa.Boolean(), nullable=False, server_default=sa.false())
            )

    if not migration.table_exists("channel_active_workflow_selection", conn):
        op.create_table(
            "channel_active_workflow_selection",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_binding_id", sa.Uuid(), nullable=False),
            sa.Column("channel_identity_id", sa.Uuid(), nullable=False),
            sa.Column("conversation_scope_id", sa.String(length=255), nullable=False, server_default=""),
            sa.Column("workflow_command_id", sa.Uuid(), nullable=False),
            sa.Column("selected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["conversation_binding_id"], ["channel_conversation_binding.id"], ondelete="CASCADE"
            ),
            sa.ForeignKeyConstraint(["channel_identity_id"], ["channel_identity.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["workflow_command_id"], ["channel_workflow_command.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "conversation_binding_id",
                "channel_identity_id",
                "conversation_scope_id",
                name="uq_channel_active_flow_selection_scope",
            ),
        )
        for name, columns in (
            ("ix_channel_active_workflow_selection_connection_id", ["connection_id"]),
            ("ix_channel_active_workflow_selection_conversation_binding_id", ["conversation_binding_id"]),
            ("ix_channel_active_workflow_selection_channel_identity_id", ["channel_identity_id"]),
            ("ix_channel_active_workflow_selection_workflow_command_id", ["workflow_command_id"]),
            (
                "ix_channel_active_flow_selection_lookup",
                ["connection_id", "conversation_binding_id", "channel_identity_id", "conversation_scope_id"],
            ),
            ("ix_channel_active_flow_selection_connection_updated", ["connection_id", "updated_at"]),
            ("ix_channel_active_flow_selection_expires", ["expires_at"]),
        ):
            op.create_index(name, "channel_active_workflow_selection", columns, unique=False)

    execution_columns = _columns("channel_execution_log", conn)
    if execution_columns:
        with op.batch_alter_table("channel_execution_log", recreate=_recreate_mode(conn)) as batch_op:
            if "workflow_command_id" not in execution_columns:
                batch_op.add_column(sa.Column("workflow_command_id", sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_channel_execution_workflow_command",
                    "channel_workflow_command",
                    ["workflow_command_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "active_selection_id" not in execution_columns:
                batch_op.add_column(sa.Column("active_selection_id", sa.Uuid(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_channel_execution_active_selection",
                    "channel_active_workflow_selection",
                    ["active_selection_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "selection_scope" not in execution_columns:
                batch_op.add_column(sa.Column("selection_scope", sa.String(length=32), nullable=True))
        execution_indexes = _indexes("channel_execution_log", conn)
        if "ix_channel_execution_log_workflow_command_id" not in execution_indexes:
            op.create_index(
                "ix_channel_execution_log_workflow_command_id",
                "channel_execution_log",
                ["workflow_command_id"],
                unique=False,
            )
        if "ix_channel_execution_log_active_selection_id" not in execution_indexes:
            op.create_index(
                "ix_channel_execution_log_active_selection_id",
                "channel_execution_log",
                ["active_selection_id"],
                unique=False,
            )

    if migration.table_exists("channel_conversation_context_entry", conn):
        context_indexes = _indexes("channel_conversation_context_entry", conn)
        if "ix_channel_context_conversation_session_created" not in context_indexes:
            op.create_index(
                "ix_channel_context_conversation_session_created",
                "channel_conversation_context_entry",
                ["conversation_binding_id", "session_id", "created_at"],
                unique=False,
            )


def downgrade() -> None:
    conn = op.get_bind()

    if migration.table_exists("channel_conversation_context_entry", conn):
        if "ix_channel_context_conversation_session_created" in _indexes("channel_conversation_context_entry", conn):
            op.drop_index(
                "ix_channel_context_conversation_session_created",
                table_name="channel_conversation_context_entry",
            )

    execution_columns = _columns("channel_execution_log", conn)
    if execution_columns:
        for index_name in (
            "ix_channel_execution_log_active_selection_id",
            "ix_channel_execution_log_workflow_command_id",
        ):
            if index_name in _indexes("channel_execution_log", conn):
                op.drop_index(index_name, table_name="channel_execution_log")
        with op.batch_alter_table("channel_execution_log", recreate=_recreate_mode(conn)) as batch_op:
            if "selection_scope" in execution_columns:
                batch_op.drop_column("selection_scope")
            if "active_selection_id" in execution_columns:
                batch_op.drop_constraint("fk_channel_execution_active_selection", type_="foreignkey")
                batch_op.drop_column("active_selection_id")
            if "workflow_command_id" in execution_columns:
                batch_op.drop_constraint("fk_channel_execution_workflow_command", type_="foreignkey")
                batch_op.drop_column("workflow_command_id")

    if migration.table_exists("channel_active_workflow_selection", conn):
        op.drop_table("channel_active_workflow_selection")

    command_columns = _columns("channel_workflow_command", conn)
    if "allow_persistent_selection" in command_columns:
        with op.batch_alter_table("channel_workflow_command", recreate=_recreate_mode(conn)) as batch_op:
            batch_op.drop_column("allow_persistent_selection")

    connection_columns = _columns("channel_connection", conn)
    if connection_columns:
        with op.batch_alter_table("channel_connection", recreate=_recreate_mode(conn)) as batch_op:
            if "flow_selection_ttl_hours" in connection_columns:
                batch_op.drop_column("flow_selection_ttl_hours")
            if "user_flow_selection_enabled" in connection_columns:
                batch_op.drop_column("user_flow_selection_enabled")
