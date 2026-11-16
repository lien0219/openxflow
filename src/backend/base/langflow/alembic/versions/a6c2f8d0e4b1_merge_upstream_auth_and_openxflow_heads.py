"""Merge upstream authentication and OpenXFlow migration heads.

Revision ID: a6c2f8d0e4b1
Revises: f5a7b9c2d4e6, f7c2e91a4b63
Create Date: 2026-11-15
Phase: EXPAND (no DDL - merge point only)

Join upstream OAuth and refresh-token migrations with the existing OpenXFlow
channel history without changing schema or data.
"""

from collections.abc import Sequence

revision: str = "a6c2f8d0e4b1"  # pragma: allowlist secret -- Alembic revision
down_revision: str | Sequence[str] | None = ("f5a7b9c2d4e6", "f7c2e91a4b63")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the migration histories without changing schema or data."""


def downgrade() -> None:
    """Restore the separate revision heads without changing schema or data."""
