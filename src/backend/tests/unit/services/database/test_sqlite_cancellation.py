"""SQLite checkout must finish releasing its worker before cancellation escapes."""

import asyncio
import sqlite3
import threading
from contextlib import suppress

import aiosqlite
import pytest
import sqlalchemy as sa
from langflow.services.database.service import DatabaseService
from langflow.services.deps import get_settings_service
from lfx.services import deps
from lfx.services.settings.service import SettingsService
from lfx.services.sqlite_runtime import release_sqlite_process_safety


@pytest.fixture(params=["file", "memory"])
async def sqlite_service(tmp_path, request):
    base_settings = get_settings_service()
    settings = base_settings.settings.model_copy(
        update={
            "database_url": (
                "sqlite+aiosqlite:///:memory:"
                if request.param == "memory"
                else f"sqlite+aiosqlite:///{tmp_path / 'cancellation.db'}"
            ),
            "database_connection_retry": False,
            "sqlite_pragmas": {"busy_timeout": 1000},
            "db_driver_connection_settings": {"check_same_thread": False, "timeout": 1},
            "use_noop_database": False,
        }
    )
    service = DatabaseService(SettingsService(settings, base_settings.auth_settings))
    try:
        yield service
    finally:
        service._remove_connection_listener(service.engine)
        await service.engine.dispose()
        release_sqlite_process_safety(service.database_url, owner=service)


@pytest.mark.parametrize("stage", ["connect", "create_function", "pragma"])
@pytest.mark.parametrize("access", ["engine", "session"])
@pytest.mark.parametrize("cancel_count", [1, 2])
async def test_cancel_during_sqlite_checkout_closes_connection(
    sqlite_service, monkeypatch, stage, access, cancel_count
):
    """Cancel at real driver boundaries, before the session owns the connection."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    resume = threading.Event()
    raw_connections = []
    async_connections = []
    worker_threads = []

    def pause(at_stage):
        if at_stage == stage:
            loop.call_soon_threadsafe(started.set)
            if not resume.wait(timeout=10):
                msg = "Test did not release SQLite worker"
                raise TimeoutError(msg)

    class TrackedCursor(sqlite3.Cursor):
        def execute(self, sql, parameters=()):
            if sql == "PRAGMA busy_timeout = 1000":
                pause("pragma")
            return super().execute(sql, parameters)

    class TrackedConnection(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            raw_connections.append(self)
            worker_threads.append(threading.current_thread())
            pause("connect")

        def create_function(self, name, *args, **kwargs):
            if name == "regexp":
                pause("create_function")
            return super().create_function(name, *args, **kwargs)

        def cursor(self, *args, **kwargs):
            return super().cursor(*args, factory=TrackedCursor, **kwargs)

    original_connect = aiosqlite.connect

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, factory=TrackedConnection, **kwargs)
        async_connections.append(connection)
        return connection

    monkeypatch.setattr(aiosqlite, "connect", tracked_connect)

    async def query():
        if access == "engine":
            async with sqlite_service.engine.connect() as connection:
                await connection.execute(sa.text("SELECT 1"))
        else:
            async with deps.session_scope(sqlite_service) as session:
                await session.exec(sa.text("SELECT 1"))

    task = asyncio.create_task(query())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        for _ in range(cancel_count):
            task.cancel()
            # Give cancellation a turn at the blocked driver operation.
            await asyncio.sleep(0)
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        await sqlite_service.engine.dispose()

        assert raw_connections
        for connection in raw_connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
                connection.execute("SELECT 1")
        for worker in worker_threads:
            await asyncio.to_thread(worker.join, 1)
            assert not worker.is_alive()
    finally:
        resume.set()
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        # Even a failing regression must not leave workers behind in pytest.
        for connection in async_connections:
            await connection.close()
        for connection in raw_connections:
            connection.close()
        for worker in worker_threads:
            await asyncio.to_thread(worker.join, 1)


async def test_cancelled_sqlite_transaction_rolls_back_and_releases_writer(sqlite_service):
    async with sqlite_service.engine.begin() as connection:
        await connection.execute(sa.text("CREATE TABLE sample (value INTEGER NOT NULL)"))

    inserted = asyncio.Event()

    async def write_then_wait():
        async with deps.session_scope(sqlite_service) as session:
            await session.execute(sa.text("INSERT INTO sample VALUES (1)"))
            inserted.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(write_then_wait())
    try:
        await asyncio.wait_for(inserted.wait(), timeout=5)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    async with deps.session_scope(sqlite_service) as session:
        assert (await session.execute(sa.text("SELECT COUNT(*) FROM sample"))).scalar_one() == 0
        await session.execute(sa.text("INSERT INTO sample VALUES (2)"))
        await session.commit()
        # Committing releases the connection. The next transaction must still
        # work, including when StaticPool keeps an in-memory database alive.
        await session.execute(sa.text("INSERT INTO sample VALUES (3)"))
        await session.rollback()

    async with sqlite_service.engine.connect() as connection:
        assert (await connection.execute(sa.text("SELECT value FROM sample"))).scalars().all() == [2]


async def test_sqlite_checkout_error_is_propagated(sqlite_service):
    def fail_connect(_connection, _record):
        msg = "connection initialization failed"
        raise sqlite3.OperationalError(msg)

    # A real connect listener can fail even when the driver opened successfully.
    # Keep this connection reachable so this test can explicitly clean it up.
    connections = []

    def capture_connection(connection, _record):
        connections.append(connection.driver_connection)

    sa.event.listen(sqlite_service.engine.sync_engine, "connect", capture_connection, insert=True)
    sa.event.listen(sqlite_service.engine.sync_engine, "connect", fail_connect)
    try:
        with pytest.raises(sa.exc.OperationalError, match="connection initialization failed"):
            async with sqlite_service.engine.connect():
                pytest.fail("checkout unexpectedly succeeded")
    finally:
        sa.event.remove(sqlite_service.engine.sync_engine, "connect", fail_connect)
        sa.event.remove(sqlite_service.engine.sync_engine, "connect", capture_connection)
        for connection in connections:
            await connection.close()


@pytest.mark.parametrize("sqlite_service", ["file"], indirect=True)
@pytest.mark.parametrize("stage", ["rollback", "close"])
@pytest.mark.parametrize("cancel_count", [1, 2])
async def test_cancel_during_session_exit_waits_for_sqlite_cleanup(sqlite_service, monkeypatch, stage, cancel_count):
    """A session owner must not exit while its shielded close still uses SQLite."""
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    resume = threading.Event()
    exiting = threading.Event()
    workers = []
    connections = []

    def pause(at_stage):
        if exiting.is_set() and at_stage == stage:
            loop.call_soon_threadsafe(started.set)
            if not resume.wait(timeout=10):
                msg = "Test did not release SQLite cleanup"
                raise TimeoutError(msg)

    class TrackedConnection(sqlite3.Connection):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            connections.append(self)
            workers.append(threading.current_thread())

        def rollback(self):
            pause("rollback")
            return super().rollback()

        def close(self):
            pause("close")
            return super().close()

    original_connect = aiosqlite.connect
    cleanup_done = asyncio.Event()

    def tracked_connect(*args, **kwargs):
        connection = original_connect(*args, factory=TrackedConnection, **kwargs)
        original_close = connection.close

        async def close():
            try:
                await original_close()
            finally:
                cleanup_done.set()

        connection.close = close
        return connection

    monkeypatch.setattr(aiosqlite, "connect", tracked_connect)

    async def query():
        async with sqlite_service._with_session() as session:
            await session.execute(sa.text("SELECT 1"))
            exiting.set()

    task = asyncio.create_task(query())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        for _ in range(cancel_count):
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done(), "session owner exited before SQLite cleanup finished"
        resume.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)
        assert cleanup_done.is_set()
        for connection in connections:
            with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
                connection.execute("SELECT 1")
    finally:
        resume.set()
        with suppress(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cleanup_done.wait(), timeout=5)
        for worker in workers:
            await asyncio.to_thread(worker.join, 1)
            assert not worker.is_alive()
