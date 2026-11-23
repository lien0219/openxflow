"""Merge the user-session and OpenXFlow migration heads.

Revision ID: b8d4e6f2a1c9
Revises: a6b8c0d2e4f7, a6c2f8d0e4b1
Phase: EXPAND (no DDL - merge point only)
Create Date: 2026-11-22

Join the upstream session-version migration with the existing OpenXFlow
authentication and channel history without changing schema or data.
"""

from collections.abc import Sequence

revision: str = "b8d4e6f2a1c9"  # pragma: allowlist secret -- Alembic revision
down_revision: str | Sequence[str] | None = ("a6b8c0d2e4f7", "a6c2f8d0e4b1")  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the migration histories without changing schema or data."""


def downgrade() -> None:
    """Restore the separate revision heads without changing schema or data."""
