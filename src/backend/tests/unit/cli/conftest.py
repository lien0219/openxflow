"""Failure fixtures shared by the CLI's database checks."""

import pytest
import sqlalchemy as sa


@pytest.fixture(autouse=True)
def disable_data_subject_erase_worker(monkeypatch):
    """CLI tests replace database services and do not exercise the app worker."""
    # CLI fixtures can switch the global database service to a temporary source
    # without keeping application-owned database workers alive against it.
    monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", "false")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED", "false")

    async def no_worker(_self) -> None:
        return None

    monkeypatch.setattr("langflow.services.data_subjects.worker.DataSubjectEraseWorker.start", no_worker)


@pytest.fixture
def deny_revision_read(client, monkeypatch):  # noqa: ARG001
    """Reproduce PostgreSQL's query-time permission failure on the local test engine."""

    async def deny(_session):
        statement = "SELECT version_num FROM alembic_version"
        message = "permission denied for table alembic_version"
        raise sa.exc.ProgrammingError(
            statement,
            {},
            RuntimeError(message),
        )

    from langflow.cli import integrity
    from langflow.cli import migration_preflight as preflight

    monkeypatch.setattr(integrity, "recorded_revisions", deny)
    monkeypatch.setattr(preflight, "recorded_revisions", deny)
