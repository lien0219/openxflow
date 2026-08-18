"""normalize channel identity user foreign key

Revision ID: a4c7d0f3e5b9
Revises: f3a6c9e2b4d7
Create Date: 2026-07-26 18:00:00.000000

Phase: EXPAND
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from langflow.utils import migration

revision: str = "a4c7d0f3e5b9"  # pragma: allowlist secret
down_revision: str | None = "f3a6c9e2b4d7"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE_NAME = "channel_identity"
_COLUMN_NAME = "openxflow_user_id"
_REFERRED_TABLE = "user"
_FOREIGN_KEY_NAME = "fk_channel_identity_openxflow_user_id_user"
_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _matching_foreign_keys(conn: sa.Connection) -> list[dict]:
    if not migration.table_exists(_TABLE_NAME, conn) or not migration.column_exists(
        _TABLE_NAME, _COLUMN_NAME, conn
    ):
        return []

    return [
        foreign_key
        for foreign_key in sa.inspect(conn).get_foreign_keys(_TABLE_NAME)
        if foreign_key.get("constrained_columns") == [_COLUMN_NAME]
        and foreign_key.get("referred_table") == _REFERRED_TABLE
    ]


def _ondelete(foreign_key: dict) -> str:
    return str((foreign_key.get("options") or {}).get("ondelete") or "").upper()


def _column_is_nullable(conn: sa.Connection) -> bool:
    for column in sa.inspect(conn).get_columns(_TABLE_NAME):
        if column["name"] == _COLUMN_NAME:
            return bool(column.get("nullable"))
    return False


def _replace_foreign_key(conn: sa.Connection, *, ondelete: str) -> None:
    foreign_keys = _matching_foreign_keys(conn)
    normalized_ondelete = ondelete.upper()
    if (
        len(foreign_keys) == 1
        and _ondelete(foreign_keys[0]) == normalized_ondelete
        and _column_is_nullable(conn)
    ):
        return

    recreate = "always" if conn.dialect.name == "sqlite" else "auto"
    with op.batch_alter_table(
        _TABLE_NAME,
        recreate=recreate,
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        for foreign_key in foreign_keys:
            batch.drop_constraint(foreign_key.get("name") or _FOREIGN_KEY_NAME, type_="foreignkey")
        batch.alter_column(_COLUMN_NAME, existing_type=sa.Uuid(), nullable=True)
        batch.create_foreign_key(
            _FOREIGN_KEY_NAME,
            _REFERRED_TABLE,
            [_COLUMN_NAME],
            ["id"],
            ondelete=normalized_ondelete,
        )


def upgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(_TABLE_NAME, conn):
        return
    _replace_foreign_key(conn, ondelete="SET NULL")


def downgrade() -> None:
    conn = op.get_bind()
    if not migration.table_exists(_TABLE_NAME, conn):
        return
    _replace_foreign_key(conn, ondelete="CASCADE")
