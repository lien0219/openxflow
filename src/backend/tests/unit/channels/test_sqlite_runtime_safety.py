import asyncio
import sqlite3
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import sqlalchemy as sa
from langflow.channels.domain.models import ChannelMessage
from langflow.channels.services import deduplication, webhook_processing
from langflow.services.database.models.user import crud as user_crud
from lfx.services import deps
from lfx.services.settings.groups.database import DatabaseSettings
from lfx.services.sqlite_runtime import (
    SQLiteNestedWriteError,
    SQLiteWriteCoordinator,
    release_sqlite_process_safety,
    validate_sqlite_worker_count,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession


_BOOM_ERROR = "boom"
_DISPATCH_ERROR = "dispatch failed"


def test_sqlite_settings_keep_small_read_pool(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", f"sqlite:///{tmp_path / 'openxflow.db'}")

    settings = DatabaseSettings(
        db_connection_settings={
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 5,
            "pool_pre_ping": True,
        }
    )

    assert settings.db_connection_settings == {
        "pool_size": 5,
        "max_overflow": 0,
        "pool_timeout": 30,
        "pool_pre_ping": True,
    }


def test_sqlite_default_pool_keeps_concurrent_read_capacity(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", f"sqlite:///{tmp_path / 'openxflow.db'}")

    settings = DatabaseSettings()

    assert settings.db_connection_settings is not None
    assert settings.db_connection_settings["pool_size"] == 5
    assert settings.db_connection_settings["max_overflow"] == 0
    assert settings.db_connection_settings["pool_timeout"] == 30


def test_sqlite_memory_database_remains_single_connection(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", "sqlite:///:memory:")

    settings = DatabaseSettings()

    assert settings.db_connection_settings is not None
    assert settings.db_connection_settings["pool_size"] == 1
    assert settings.db_connection_settings["max_overflow"] == 0


def test_postgres_settings_keep_configured_pool(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", "postgresql://user:password@localhost/openxflow")
    configured = {
        "pool_size": 8,
        "max_overflow": 12,
        "pool_timeout": 15,
        "pool_pre_ping": True,
    }

    settings = DatabaseSettings(db_connection_settings=configured)

    assert settings.db_connection_settings == configured


def test_sqlite_rejects_multiple_workers(monkeypatch, tmp_path) -> None:
    database_url = f"sqlite:///{tmp_path / 'openxflow.db'}"

    with pytest.raises(ValueError, match="LANGFLOW_WORKERS=1"):
        validate_sqlite_worker_count(database_url, 2)

    monkeypatch.setenv("LANGFLOW_DATABASE_URL", database_url)
    monkeypatch.setenv("LANGFLOW_WORKERS", "2")
    with pytest.raises(ValueError, match="LANGFLOW_WORKERS=1"):
        DatabaseSettings()


class _FailedSession:
    is_active = False

    def __init__(self) -> None:
        self.rollback_calls = 0

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _FakeDBService:
    def __init__(self, session) -> None:
        self.session = session

    @asynccontextmanager
    async def _with_session(self):
        yield self.session


@pytest.mark.asyncio
async def test_session_scope_rolls_back_inactive_failed_session(monkeypatch) -> None:
    session = _FailedSession()
    monkeypatch.setattr(deps, "get_db_service", lambda: _FakeDBService(session))
    monkeypatch.setattr(deps.logger, "aexception", AsyncMock())

    with pytest.raises(RuntimeError, match=_BOOM_ERROR):
        async with deps.session_scope():
            raise RuntimeError(_BOOM_ERROR)

    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_last_login_sqlite_lock_rolls_back_request_session(monkeypatch) -> None:
    session = _FailedSession()
    lock_error = OperationalError(
        "UPDATE user SET last_login_at = ?",
        {},
        sqlite3.OperationalError("database is locked"),
    )
    monkeypatch.setattr(user_crud, "get_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(user_crud, "update_user", AsyncMock(side_effect=lock_error))
    monkeypatch.setattr(user_crud.logger, "awarning", AsyncMock())
    monkeypatch.setattr(user_crud.logger, "aerror", AsyncMock())

    result = await user_crud.update_user_last_login_at(uuid4(), session)

    assert result is None
    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_last_login_does_not_hide_non_lock_failures(monkeypatch) -> None:
    session = _FailedSession()
    monkeypatch.setattr(user_crud, "get_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(user_crud, "update_user", AsyncMock(side_effect=RuntimeError("schema mismatch")))

    with pytest.raises(RuntimeError, match="schema mismatch"):
        await user_crud.update_user_last_login_at(uuid4(), session)

    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_last_login_does_not_hide_non_lock_operational_errors(monkeypatch) -> None:
    session = _FailedSession()
    disk_error = OperationalError(
        "UPDATE user SET last_login_at = ?",
        {},
        sqlite3.OperationalError("disk I/O error"),
    )
    monkeypatch.setattr(user_crud, "get_user_by_id", AsyncMock(return_value=object()))
    monkeypatch.setattr(user_crud, "update_user", AsyncMock(side_effect=disk_error))

    with pytest.raises(OperationalError, match="disk I/O error"):
        await user_crud.update_user_last_login_at(uuid4(), session)

    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_sqlite_write_coordinator_rejects_nested_write_sessions() -> None:
    coordinator = SQLiteWriteCoordinator(wait_seconds=0.1)
    first_owner = object()
    second_owner = object()

    await coordinator.acquire(first_owner)
    try:
        with pytest.raises(SQLiteNestedWriteError, match="Nested SQLite write sessions"):
            await coordinator.acquire(second_owner)
    finally:
        coordinator.release(first_owner)


class _Result:
    def __init__(self, value) -> None:
        self.value = value

    def first(self):
        return self.value


class _DedupSession:
    def __init__(self) -> None:
        self.commit_calls = 0

    async def exec(self, _statement):
        return _Result(None)

    async def commit(self) -> None:
        self.commit_calls += 1


@pytest.mark.asyncio
async def test_deduplication_claim_commits_before_follow_up_writes(monkeypatch) -> None:
    session = _DedupSession()
    receipt = SimpleNamespace(id=uuid4())
    claim = AsyncMock(return_value=receipt)
    monkeypatch.setattr(deduplication, "claim_channel_event", claim)
    event = SimpleNamespace(
        connection_id=uuid4(),
        event_id="event-1",
        event_type=SimpleNamespace(value="text"),
    )

    result = await deduplication.ChannelEventDeduplicator(session).claim(event, b"payload")
    assert sù∑ı»ZÆÀk∫wµÁ