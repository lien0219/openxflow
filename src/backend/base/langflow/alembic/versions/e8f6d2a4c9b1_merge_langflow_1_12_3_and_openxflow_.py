"""merge Langflow 1.12.3 and OpenXFlow channel heads

Revision ID: e8f6d2a4c9b1
Revises: 386662af02e9, d3b7e1f5a9c2
Create Date: 2026-09-29 19:07:46.295991

Phase: EXPAND

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e8f6d2a4c9b1"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = ("386662af02e9", "d3b7e1f5a9c2")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
