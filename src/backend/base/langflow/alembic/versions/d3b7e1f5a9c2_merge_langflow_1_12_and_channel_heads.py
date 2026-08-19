"""merge Langflow 1.12 and OpenXFlow channel heads

Revision ID: d3b7e1f5a9c2
Revises: a3f8b1c9d7e2, c7e2f4a9b1d3
Create Date: 2026-08-19 15:00:00.000000

Phase: EXPAND

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "d3b7e1f5a9c2"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = ("a3f8b1c9d7e2", "c7e2f4a9b1d3")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
