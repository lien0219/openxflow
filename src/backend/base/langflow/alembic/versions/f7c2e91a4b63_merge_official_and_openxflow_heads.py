"""Merge official Langflow and OpenXFlow migration heads.

Revision ID: f7c2e91a4b63
Revises: e5a7c9b1d3f2, e8f6d2a4c9b1
Create Date: 2026-10-18
Phase: EXPAND (no DDL - merge point only)

Join the official flow-version history with OpenXFlow's existing channel
history without changing schema or data.
"""

from collections.abc import Sequence

revision: str = "f7c2e91a4b63"  # pragma: allowlist secret -- Alembic revision
down_revision: str | Sequence[str] | None = ("e5a7c9b1d3f2", "e8f6d2a4c9b1")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the migration histories without changing schema or data."""


def downgrade() -> None:
    """Restore the separate revision heads without changing schema or data."""
