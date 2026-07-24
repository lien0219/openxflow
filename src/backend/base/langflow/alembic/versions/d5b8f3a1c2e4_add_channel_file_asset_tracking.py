"""add channel file asset tracking

Revision ID: d5b8f3a1c2e4
Revises: c4a9e2d7f1b0
Create Date: 2026-07-22 23:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from langflow.utils import migration

revision: str = "d5b8f3a1c2e4"  # pragma: allowlist secret
down_revision: str | None = "c4a9e2d7f1b0"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _create_index(name: str, table: str, columns: list[str]) -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if name not in {index["name"] for index in inspector.get_indexes(table)}:
        op.create_index(name, table, columns)


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_file_asset", conn):
        op.create_table(
            "channel_file_asset",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("connection_id", sa.Uuid(), nullable=False),
            sa.Column("openxflow_user_id", sa.Uuid(), nullable=False),
            sa.Column("external_conversation_id", sa.String(length=255), nullable=False),
            sa.Column("external_message_id", sa.String(length=255), nullable=False),
            sa.Column("external_file_id", sa.String(length=255), nullable=False),
            sa.Column("user_file_id", sa.Uuid(), nullable=True),
            sa.Column("knowledge_base_id", sa.Uuid(), nullable=True),
            sa.Column("ingestion_job_id", sa.Uuid(), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=False),
            sa.Column("mime_type", sa.String(length=255), nullable=True),
            sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error_message", sa.String(), nullable=True),
            sa.Column("metadata_data", _JSON, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["openxflow_user_id"], ["user.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_file_id"], ["file.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["knowledge_base_id"], ["knowledge_base.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["ingestion_job_id"], ["job.job_id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "connection_id",
                "external_message_id",
                "external_file_id",
                name="uq_channel_file_asset_external_file",
            ),
        )

    _create_index("ix_channel_file_asset_connection_id", "channel_file_asset", ["connection_id"])
    _create_index("ix_channel_file_asset_openxflow_user_id", "channel_file_asset", ["openxflow_user_id"])
    _create_index(
        "ix_channel_file_asset_external_conversation_id",
        "channel_file_asset",
        ["external_conversation_id"],
    )
    _create_index("ix_channel_file_asset_user_file_id", "channel_file_asset", ["user_file_id"])
    _create_index("ix_channel_file_asset_knowledge_base_id", "channel_file_asset", ["knowledge_base_id"])
    _create_index("ix_channel_file_asset_ingestion_job_id", "channel_file_asset", ["ingestion_job_id"])
    _create_index("ix_channel_file_asset_status", "channel_file_asset", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_file_asset", conn):
        op.drop_table("channel_file_asset")
