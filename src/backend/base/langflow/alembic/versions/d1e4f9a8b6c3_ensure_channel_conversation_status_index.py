"""ensure channel conversation status index exists

Revision ID: d1e4f9a8b6c3
Revises: c0a3e8f7d5b2
Create Date: 2026-07-25 01:10:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "d1e4f9a8b6c3"  # pragma: allowlist secret
down_revision: str | None = "c0a3e8f7d5b2"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "channel_conversation_binding"
_INDEX_NAME = "ix_channel_conversation_binding_status"


def _index_exists(conn) -> bool:
    return _INDEX_NAME in {index["name"] for index in sa.inspect(conn).get_indexes(_TABLE_NAME)}


def upgrade() -> None:
    """Repair databases that applied the routing migration before this index was added."""
    conn = op.get_bind()
    if not migration.table_exists(_TABLE_NAME, conn) or _index_exists(conn):
        return

    op.create_index(_INDEX_NAME, _TABLE_NAME, ["status"], unique=False)


def downgrade() -> None:
    """Keep the index because it is part of the schema expected by the prior revision."""
