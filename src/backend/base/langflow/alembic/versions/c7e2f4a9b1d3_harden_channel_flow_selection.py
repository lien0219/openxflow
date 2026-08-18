"""harden channel workflow selection lifecycle

Revision ID: c7e2f4a9b1d3
Revises: a1f4c7e9d2b6
Create Date: 2026-07-30 00:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from langflow.utils import migration

revision: str = "c7e2f4a9b1d3"  # pragma: allowlist secret
down_revision: str | None = "a1f4c7e9d2b6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _indexes(table_name: str, conn) -> set[str]:
    if not migration.table_exists(table_name, conn):
        return set()
    return {index["name"] for index in sa.inspect(conn).get_indexes(table_name)}


def upgrade() -> None:
    conn = op.get_bind()
    table_name = "channel_active_workflow_selection"
    if not migration.table_exists(table_name, conn):
        return
    existing = _indexes(table_name, conn)
    for name, columns in (
        ("ix_channel_active_flow_selection_connection_expires", ["connection_id", "expires_at"]),
        (
            "ix_channel_active_flow_selection_identity_updated",
            ["connection_id", "channel_identity_id", "updated_at"],
        ),
        ("ix_channel_active_flow_selection_command_updated", ["workflow_command_id", "updated_at"]),
    ):
        if name not in existing:
            op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    conn = op.get_bind()
    table_name = "channel_active_workflow_selection"
    if not migration.table_exists(table_name, conn):
        return
    existing = _indexes(table_name, conn)
    for name in (
        "ix_channel_active_flow_selection_command_updated",
        "ix_channel_active_flow_selection_identity_updated",
        "ix_channel_active_flow_selection_connection_expires",
    ):
        if name in existing:
            op.drop_index(name, table_name=table_name)
