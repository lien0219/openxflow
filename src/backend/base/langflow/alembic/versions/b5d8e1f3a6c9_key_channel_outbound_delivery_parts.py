"""key channel outbound delivery parts

Revision ID: b5d8e1f3a6c9
Revises: a4c7d0f3e5b9
Create Date: 2026-07-27 18:30:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "b5d8e1f3a6c9"  # pragma: allowlist secret
down_revision: str | None = "a4c7d0f3e5b9"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "channel_outbound_delivery"
_OLD_CONSTRAINT = "uq_channel_outbound_delivery_event_kind"
_NEW_CONSTRAINT = "uq_channel_outbound_delivery_event_kind_key"


def _recreate_mode(conn) -> str:
    return "always" if conn.dialect.name == "sqlite" else "auto"


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(_TABLE, conn):
        return

    columns = {column["name"] for column in sa.inspect(conn).get_columns(_TABLE)}
    if "delivery_key" in columns:
        return

    with op.batch_alter_table(_TABLE, recreate=_recreate_mode(conn)) as batch_op:
        batch_op.add_column(
            sa.Column(
                "delivery_key",
                sa.String(length=64),
                nullable=False,
                server_default="default",
            )
        )
        batch_op.drop_constraint(_OLD_CONSTRAINT, type_="unique")
        batch_op.create_unique_constraint(
            _NEW_CONSTRAINT,
            ["connection_id", "external_event_id", "delivery_kind", "delivery_key"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(_TABLE, conn):
        return

    columns = {column["name"] for column in sa.inspect(conn).get_columns(_TABLE)}
    if "delivery_key" not in columns:
        return

    with op.batch_alter_table(_TABLE, recreate=_recreate_mode(conn)) as batch_op:
        batch_op.drop_constraint(_NEW_CONSTRAINT, type_="unique")
        batch_op.create_unique_constraint(
            _OLD_CONSTRAINT,
            ["connection_id", "external_event_id", "delivery_kind"],
        )
        batch_op.drop_column("delivery_key")
