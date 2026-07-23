"""add channel outbound delivery receipts

Revision ID: g8e1c6d4f5b7
Revises: f7d0b5c3e4a6
Create Date: 2026-07-23 20:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "g8e1c6d4f5b7"  # pragma: allowlist secret
down_revision: str | None = "f7d0b5c3e4a6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if migration.table_exists("channel_outbound_delivery", conn):
        return

    op.create_table(
        "channel_outbound_delivery",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("response_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["connection_id"], ["channel_connection.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_channel_outbound_delivery_event",
        ),
    )
    op.create_index(
        "ix_channel_outbound_delivery_connection_id",
        "channel_outbound_delivery",
        ["connection_id"],
        unique=False,
    )
    op.create_index(
        "ix_channel_outbound_delivery_status_updated",
        "channel_outbound_delivery",
        ["status", "updated_at"],
        unique=False,
    )


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_outbound_delivery", conn):
        return
    op.drop_index("ix_channel_outbound_delivery_status_updated", table_name="channel_outbound_delivery")
    op.drop_index("ix_channel_outbound_delivery_connection_id", table_name="channel_outbound_delivery")
    op.drop_table("channel_outbound_delivery")
