import asyncio
import sqlite3
import threading
import time
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
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession as SQLModelAsyncSession


def test_sqlite_settings_use_loop_neutral_null_pool(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", f"sqlite:///{tmp_path / 'openxflow.db'}")

    settings = DatabaseSettings(
        db_connection_settings={
            "pool_size": 20,
            "max_overflow": 30,
            "pool_timeout": 5,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
        }
    )

    assert settings.db_connection_settings == {
        "pool_pre_ping": True,
        "poolclass": "NullPool",
    }


def test_sqlite_default_pool_is_loop_neutral(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", f"sqlite:///{tmp_path / 'openxflow.db'}")

    settings = DatabaseSettings()

    assert settings.db_connection_settings is not None
    assert settings.db_connection_settings["poolclass"] == "NullPool"
    assert "pool_size" not in settings.db_connection_settings
    assert "max_overflow" not in settings.db_connection_settings
    assert "pool_timeout" not in settings.db_connection_settings
    assert "pool_recycle" not in settings.db_connection_settings


def test_sqlite_memory_database_uses_static_pool(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_DATABASE_URL", "sqlite:///:memory:")

    settings = DatabaseSettings()

    assert settings.db_connection_settings is not None
    assert settings.db_connection_settings["poolclass"] == "StaticPool"
    assert "pool_size" not in settings.db_connection_settings
    assert "max_overflow" not in settings.db_connection_settings


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

    with pytest.raises(RuntimeError, match="boom"):
        async with deps.session_scope():
            raise RuntimeError("boom")

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
    assert result is receipt
    assert session.commit_calls == 1


class _WebhookSession:
    def __init__(self, connection) -> None:
        self.connection = connection
        self.commit_calls = 0
        self.rollback_calls = 0
        self.failure_marker = False
        self.committed_failure_marker = False

    async def get(self, _model, connection_id):
        return self.connection if self.connection.id == connection_id else None

    async def commit(self) -> None:
        self.commit_calls += 1
        if self.failure_marker:
            self.committed_failure_marker = True

    async def rollback(self) -> None:
        self.rollback_calls += 1


class _DispatchService:
    def __init__(self, _session, _connection, _adapter) -> None:
        pass

    async def handle(self, _event):
        return ChannelMessage(text="ok")


class _FailingDispatchService(_DispatchService):
    async def handle(self, _event):
        raise RuntimeError("dispatch failed")


def _connection(connection_id):
    return SimpleNamespace(
        id=connection_id,
        channel_type="telegram",
        enabled=True,
        queue_timeout_seconds=30,
        task_timeout_seconds=30,
    )


def _event():
    return SimpleNamespace(message=SimpleNamespace(metadata={}))


@pytest.mark.asyncio
async def test_webhook_dispatch_commits_before_gateway_delivery(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    session = _WebhookSession(connection)
    observed = {}

    @asynccontextmanager
    async def fake_session_scope():
        yield session

    class _Gateway:
        def register_adapter(self, _connection_id, _adapter) -> None:
            return None

        async def receive(self, _connection_id, _headers, _payload, handler, *, deduplicator):
            del deduplicator
            observed["response"] = await handler(_event())
            observed["commit_calls_after_handler"] = session.commit_calls

    monkeypatch.setattr(webhook_processing, "session_scope", fake_session_scope)
    monkeypatch.setattr(webhook_processing, "build_channel_adapter", lambda _connection: object())
    monkeypatch.setattr(webhook_processing, "ChannelGateway", _Gateway)
    monkeypatch.setattr(webhook_processing, "ChannelEventDeduplicator", lambda _session: object())
    monkeypatch.setattr(webhook_processing, "ChannelDispatchService", _DispatchService)

    result = await webhook_processing.process_provider_webhook(
        connection_id=connection_id,
        expected_channel_type="telegram",
        headers={},
        payload=b"{}",
    )

    assert result is True
    assert observed["response"].text == "ok"
    assert observed["commit_calls_after_handler"] == 1
    assert session.commit_calls == 2
    assert session.rollback_calls == 0


@pytest.mark.asyncio
async def test_webhook_failure_commits_receipt_failure_marker(monkeypatch) -> None:
    connection_id = uuid4()
    connection = _connection(connection_id)
    session = _WebhookSession(connection)

    @asynccontextmanager
    async def fake_session_scope():
        yield session

    class _Gateway:
        def register_adapter(self, _connection_id, _adapter) -> None:
            return None

        async def receive(self, _connection_id, _headers, _payload, handler, *, deduplicator):
            del deduplicator
            try:
                await handler(_event())
            except RuntimeError:
                session.failure_marker = True
                raise

    monkeypatch.setattr(webhook_processing, "session_scope", fake_session_scope)
    monkeypatch.setattr(webhook_processing, "build_channel_adapter", lambda _connection: object())
    monkeypatch.setattr(webhook_processing, "ChannelGateway", _Gateway)
    monkeypatch.setattr(webhook_processing, "ChannelEventDeduplicator", lambda _session: object())
    monkeypatch.setattr(webhook_processing, "ChannelDispatchService", _FailingDispatchService)
    monkeypatch.setattr(webhook_processing.logger, "aexception", AsyncMock())

    result = await webhook_processing.process_provider_webhook(
        connection_id=connection_id,
        expected_channel_type="telegram",
        headers={},
        payload=b"{}",
    )

    assert result is False
    assert session.rollback_calls == 1
    assert session.commit_calls == 1
    assert session.committed_failure_marker is True


def test_sqlite_null_pool_engine_is_reusable_across_event_loops(tmp_path) -> None:
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'cross-loop.db'}"
    engine = create_async_engine(database_url, poolclass=NullPool)

    async def initialize() -> None:
        async with engine.begin() as connection:
            await connection.execute(sa.text("CREATE TABLE sample (value INTEGER NOT NULL)"))
            await connection.execute(sa.text("INSERT INTO sample (value) VALUES (1)"))

    async def read_value() -> int:
        async with engine.connect() as connection:
            return int((await connection.execute(sa.text("SELECT value FROM sample"))).scalar_one())

    asyncio.run(initialize())
    assert asyncio.run(read_value()) == 1
    asyncio.run(engine.dispose())


def test_sqlite_writer_coordinator_serializes_different_event_loops() -> None:
    coordinator = SQLiteWriteCoordinator(wait_seconds=2)
    first_acquired = threading.Event()
    release_first = threading.Event()
    elapsed: list[float] = []
    errors: list[BaseException] = []

    def first_writer() -> None:
        async def run() -> None:
            owner = object()
            await coordinator.acquire(owner)
            first_acquired.set()
            await asyncio.to_thread(release_first.wait, 1)
            coordinator.release(owner)

        try:
            asyncio.run(run())
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    def second_writer() -> None:
        first_acquired.wait(1)

        async def run() -> None:
            owner = object()
            started = time.monotonic()
            await coordinator.acquire(owner)
            elapsed.append(time.monotonic() - started)
            coordinator.release(owner)

        try:
            asyncio.run(run())
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    first_thread = threading.Thread(target=first_writer)
    second_thread = threading.Thread(target=second_writer)
    first_thread.start()
    second_thread.start()
    assert first_acquired.wait(1)
    time.sleep(0.15)
    release_first.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert not errors
    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert elapsed
    assert elapsed[0] >= 0.1


class _RealDBService:
    def __init__(self, database_url, session_maker) -> None:
        self.database_url = database_url
        self.session_maker = session_maker
        self.settings_service = SimpleNamespace(
            settings=SimpleNamespace(
                workers=1,
                db_connect_timeout=5,
            )
        )

    @asynccontextmanager
    async def _with_session(self):
        async with self.session_maker() as session:
            yield session


@pytest.mark.asyncio
async def test_real_sqlite_writes_serialize_while_reads_remain_concurrent(monkeypatch, tmp_path) -> None:
    database_path = tmp_path / "runtime.db"
    database_url = f"sqlite+aiosqlite:///{database_path}"
    engine = create_async_engine(
        database_url,
        poolclass=NullPool,
        connect_args={"check_same_thread": False, "timeout": 1},
    )

    def set_pragmas(dbapi_connection, _record) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=1000")
        finally:
            cursor.close()

    sa.event.listen(engine.sync_engine, "connect", set_pragmas)
    session_maker = async_sessionmaker(
        engine,
        class_=SQLModelAsyncSession,
        expire_on_commit=False,
    )
    service = _RealDBService(database_url, session_maker)
    monkeypatch.setattr(deps, "get_db_service", lambda: service)

    try:
        async with engine.begin() as connection:
            await connection.execute(
                sa.text(
                    "CREATE TABLE runtime_item (id INTEGER PRIMARY KEY AUTOINCREMENT, value INTEGER NOT NULL UNIQUE)"
                )
            )

        async def write_value(value: int) -> None:
            async with deps.session_scope() as session:
                await session.execute(
                    sa.text("INSERT INTO runtime_item(value) VALUES (:value)"),
                    {"value": value},
                )
                await asyncio.sleep(0.01)

        await asyncio.wait_for(
            asyncio.gather(*(write_value(value) for value in range(10))),
            timeout=5,
        )

        writer_started = asyncio.Event()
        release_writer = asyncio.Event()

        async def held_writer() -> None:
            async with deps.session_scope() as session:
                await session.execute(
                    sa.text("INSERT INTO runtime_item(value) VALUES (:value)"),
                    {"value": 100},
                )
                writer_started.set()
                await release_writer.wait()

        writer_task = asyncio.create_task(held_writer())
        await asyncio.wait_for(writer_started.wait(), timeout=3)
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        async with deps.session_scope_readonly() as session:
            count_before_commit = int(
                (await session.execute(sa.text("SELECT COUNT(*) FROM runtime_item"))).scalar_one()
            )
        read_elapsed = loop.time() - started_at
        release_writer.set()
        await asyncio.wait_for(writer_task, timeout=3)

        async with deps.session_scope_readonly() as session:
            final_count = int((await session.execute(sa.text("SELECT COUNT(*) FROM runtime_item"))).scalar_one())

        assert count_before_commit == 10
        assert final_count == 11
        assert read_elapsed < 1.0
    finally:
        sa.event.remove(engine.sync_engine, "connect", set_pragmas)
        await engine.dispose()
        release_sqlite_process_safety(database_url)
