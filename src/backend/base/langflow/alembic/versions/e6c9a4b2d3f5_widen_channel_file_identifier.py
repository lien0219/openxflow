"""widen channel provider file identifiers

Revision ID: e6c9a4b2d3f5
Revises: d5b8f3a1c2e4
Create Date: 2026-07-23 10:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "e6c9a4b2d3f5"  # pragma: allowlist secret
down_revision: str | None = "d5b8f3a1c2e4"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_file_asset", conn):
        return
    with op.batch_alter_table("channel_file_asset") as batch_op:
        batch_op.alter_column(
            "external_file_id",
            existing_type=sa.String(length=255),
            type_=sa.String(length=1024),
            existing_nullable=False,
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists("channel_file_asset", conn):
        return
    with op.batch_alter_table("channel_file_asset") as batch_op:
        batch_op.alter_column(
            "external_file_id",
            existing_type=sa.String(length=1024),
            type_=sa.String(length=255),
            existing_nullable=False,
        )
