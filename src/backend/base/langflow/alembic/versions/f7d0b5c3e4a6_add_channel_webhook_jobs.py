"""add durable channel webhook jobs

Revision ID: f7d0b5c3e4a6
Revises: e6c9a4b2d3f5
Create Date: 2026-07-23 18:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from langflow.utils import migration

revision: str = "f7d0b5c3e4a6"  # pragma: allowlist secret
down_revision: str | None = "e6c9a4b2d3f5"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_webhook_job", conn):
        return

    json_type = sa.JSON().with_variant(JSONB(), "postgresql")
    op.create_table(
        "channel_webhook_job",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("headers_data", json_type, nullable=False),
        sa.Column("payload", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.Uuid(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_channel_webhook_job_external_event",
        ),
    )
    op.create_index(
        "ix_channel_webhook_job_connection_id",
        "channel_webhook_job",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_channel_webhook_job_claim",
        "channel_webhook_job",
        ["status", "next_attempt_at", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_channel_webhook_job_lease",
        "channel_webhook_job",
        ["status", "lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_webhook_job", conn):
        return
    op.drop_index("ix_channel_webhook_job_lease", table_name="channel_webhook_job")
    op.drop_index("ix_channel_webhook_job_claim", table_name="channel_webhook_job")
    op.drop_index("ix_channel_webhook_job_connection_id", table_name="channel_webhook_job")
    op.drop_table("channel_webhook_job")
