"""SQLite runtime coordination for async OpenXFlow sessions.

SQLite permits concurrent readers in WAL mode but only one writer. This module
keeps a small read-capable connection pool while serializing write transactions
inside one process, rejects unsafe multi-worker use, and prevents two OpenXFlow
backend processes from opening the same database file at the same time.
"""

from __future__ import annotations

import asyncio
import atexit
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote
from weakref import WeakKeyDictionary

from filelock import FileLock
from filelock import Timeout as FileLockTimeout
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.sql.elements import TextClause

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_SQLITE_LOCK_MESSAGES = (
    "database is locked",
    "database table is locked",
    "database schema is locked",
)
_SQLITE_WRITE_PREFIXES = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "INSERT",
    "PRAGMA",
    "REINDEX",
    "REPLACE",
    "UPDATE",
    "VACUUM",
}
_DEFAULT_WRITE_WAIT_SECONDS = 10.0
_DEFAULT_PROCESS_LOCK_WAIT_SECONDS = 10.0
_SQLITE_GUARD_INSTALLED_KEY = "openxflow_sqlite_guard_installed"


class SQLiteNestedWriteError(RuntimeError):
    """Raised when one task starts a second write session before finishing the first."""

    def __init__(self) -> None:
        super().__init__(
            "Nested SQLite write sessions were detected in the same task. "
            "Commit or roll back the outer session before opening an independent write session."
        )


class SQLiteWriteTimeoutError(TimeoutError):
    """Raised when a SQLite write cannot enter the application writer queue."""

    def __init__(self, wait_seconds: float) -> None:
        super().__init__(
            f"SQLite write queue wait exceeded {wait_seconds:g} seconds. "
            "A transaction is likely being held open across network or workflow work."
        )


class SQLiteConcurrentSessionUseError(RuntimeError):
    """Raised when one guarded session is written from multiple asyncio tasks."""

    def __init__(self) -> None:
        super().__init__(
            "A SQLite AsyncSession was used for writes by multiple asyncio tasks. "
            "Create one session per task and commit each transaction before sharing results."
        )


def is_sqlite_url(database_url: str | None) -> bool:
    """Return whether a database URL uses SQLite."""
    return bool(database_url and database_url.startswith("sqlite"))


def sqlite_database_path(database_url: str | None) -> Path | None:
    """Return a file-backed SQLite path, excluding in-memory databases."""
    if not is_sqlite_url(database_url):
        return None
    try:
        database = make_url(str(database_url)).database
    except Exception:  # noqa: BLE001 - malformed URLs are validated by settings
        return None
    if not database or database == ":memory:":
        return None
    return Path(unquote(database))


def is_sqlite_lock_error(error: BaseException) -> bool:
    """Return whether an exception chain represents SQLite lock contention."""
    current: BaseException | None = error
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        message = str(current).lower()
        if any(fragment in message for fragment in _SQLITE_LOCK_MESSAGES):
            return True
        if isinstance(current, OperationalError):
            original = getattr(current, "orig", None)
            if isinstance(original, BaseException) and original is not current:
                current = original
                continue
        current = current.__cause__ or current.__context__
    return False


def validate_sqlite_worker_count(database_url: str | None, workers: int) -> None:
    """Reject multiple application workers for one SQLite database."""
    if is_sqlite_url(database_url) and workers != 1:
        msg = (
            "SQLite requires LANGFLOW_WORKERS=1. Multiple OpenXFlow workers cannot safely share "
            "one SQLite file; use one worker locally or PostgreSQL for multi-worker deployments."
        )
        raise ValueError(msg)


def _statement_is_write(statement: Any) -> bool:
    if bool(getattr(statement, "is_dml", False) or getattr(statement, "is_ddl", False)):
        return True
    if not isinstance(statement, TextClause):
        return False
    text = statement.text.lstrip()
    if not text:
        return False
    prefix = text.split(None, 1)[0].upper()
    if prefix in _SQLITE_WRITE_PREFIXES:
        return True
    if prefix == "WITH":
        normalized = f" {' '.join(text.upper().split())} "
        return any(f" {keyword} " in normalized for keyword in ("INSERT", "UPDATE", "DELETE", "REPLACE"))
    return prefix == "BEGIN" and "IMMEDIATE" in text.upper()


class SQLiteWriteCoordinator:
    """Serialize SQLite writers while allowing independent read sessions."""

    def __init__(self, wait_seconds: float = _DEFAULT_WRITE_WAIT_SECONDS) -> None:
        self.wait_seconds = max(0.1, wait_seconds)
        self._lock = asyncio.Lock()
        self._owner: object | None = None
        self._owner_task: asyncio.Task[Any] | None = None

    async def acquire(self, owner: object) -> None:
        current_task = asyncio.current_task()
        if self._owner is owner:
            if current_task is not None and self._owner_task is not current_task:
                raise SQLiteConcurrentSessionUseError
            return
        if current_task is not None and self._owner_task is current_task:
            raise SQLiteNestedWriteError
        try:
            await asyncio.wait_for(self._lock.acquire(), timeout=self.wait_seconds)
        except TimeoutError as exc:
            raise SQLiteWriteTimeoutError(self.wait_seconds) from exc
        self._owner = owner
        self._owner_task = current_task

    def release(self, owner: object) -> None:
        if self._owner is not owner:
            return
        self._owner = None
        self._owner_task = None
        if self._lock.locked():
            self._lock.release()


@dataclass
class _ProcessLockEntry:
    file_lock: FileLock
    references: int = 1


_PROCESS_LOCK_GUARD = threading.Lock()
_PROCESS_LOCKS: dict[Path, _ProcessLockEntry] = {}


def _release_all_process_locks() -> None:
    with _PROCESS_LOCK_GUARD:
        entries = list(_PROCESS_LOCKS.values())
        _PROCESS_LOCKS.clear()
    for entry in entries:
        if entry.file_lock.is_locked:
            entry.file_lock.release(force=True)


atexit.register(_release_all_process_locks)


class SQLiteProcessLock:
    """Cross-process guard preventing two OpenXFlow processes from sharing one SQLite file."""

    def __init__(self, database_path: Path, file_lock: FileLock) -> None:
        self.database_path = database_path.resolve()
        self._file_lock = file_lock
        self._closed = False

    @classmethod
    def acquire(
        cls,
        database_path: Path,
        *,
        wait_seconds: float = _DEFAULT_PROCESS_LOCK_WAIT_SECONDS,
    ) -> SQLiteProcessLock:
        """Acquire a process lock, allowing a short reload-worker handover window."""
        resolved = database_path.resolve()
        with _PROCESS_LOCK_GUARD:
            existing = _PROCESS_LOCKS.get(resolved)
            if existing is not None:
                existing.references += 1
                return cls(resolved, existing.file_lock)

            lock_path = Path(f"{resolved}.openxflow.lock")
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            file_lock = FileLock(str(lock_path), timeout=max(0.0, wait_seconds), thread_local=False)
            try:
                file_lock.acquire()
            except FileLockTimeout as exc:
                msg = (
                    f"SQLite database '{resolved}' is already used by another OpenXFlow process. "
                    "Stop the other backend process before starting this one."
                )
                raise RuntimeError(msg) from exc
            _PROCESS_LOCKS[resolved] = _ProcessLockEntry(file_lock=file_lock)
            return cls(resolved, file_lock)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with _PROCESS_LOCK_GUARD:
            entry = _PROCESS_LOCKS.get(self.database_path)
            if entry is None or entry.file_lock is not self._file_lock:
                return
            entry.references -= 1
            if entry.references > 0:
                return
            _PROCESS_LOCKS.pop(self.database_path, None)
            if self._file_lock.is_locked:
                self._file_lock.release(force=True)


_COORDINATOR_GUARD = threading.Lock()
_COORDINATORS: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, SQLiteWriteCoordinator]] = WeakKeyDictionary()


def _database_runtime_key(database_url: str) -> str:
    path = sqlite_database_path(database_url)
    return str(path.resolve()) if path is not None else database_url


def _coordinator_for_current_loop(database_url: str, wait_seconds: float) -> SQLiteWriteCoordinator:
    loop = asyncio.get_running_loop()
    database_key = _database_runtime_key(database_url)
    with _COORDINATOR_GUARD:
        loop_coordinators = _COORDINATORS.setdefault(loop, {})
        coordinator = loop_coordinators.get(database_key)
        if coordinator is None:
            coordinator = SQLiteWriteCoordinator(wait_seconds)
            loop_coordinators[database_key] = coordinator
        return coordinator


def _pending_writes(session: AsyncSession) -> bool:
    return bool(session.new or session.dirty or session.deleted)


def install_sqlite_session_guard(
    session: AsyncSession,
    *,
    database_url: str,
    workers: int,
    write_wait_seconds: float = _DEFAULT_WRITE_WAIT_SECONDS,
) -> None:
    """Install lazy write serialization on a SQLAlchemy async session.

    Reads remain concurrent. The first DML statement, pending autoflush, or
    commit with pending ORM changes acquires the process-local writer queue and
    retains it until commit, rollback, or close.
    """
    if not is_sqlite_url(database_url):
        return
    validate_sqlite_worker_count(database_url, workers)
    if session.info.get(_SQLITE_GUARD_INSTALLED_KEY, False):
        return

    coordinator = _coordinator_for_current_loop(database_url, write_wait_seconds)
    owner = object()
    guard_held = False

    original_exec = getattr(session, "exec", None)
    original_execute = session.execute
    original_flush = session.flush
    original_commit = session.commit
    original_rollback = session.rollback
    original_close = session.close
    original_refresh = session.refresh

    async def ensure_guard() -> None:
        nonlocal guard_held
        if guard_held:
            return
        await coordinator.acquire(owner)
        guard_held = True

    def release_guard() -> None:
        nonlocal guard_held
        if not guard_held:
            return
        coordinator.release(owner)
        guard_held = False

    async def recover_failed_write() -> None:
        try:
            await original_rollback()
        finally:
            release_guard()

    async def guarded_execute(statement: Any, *args: Any, **kwargs: Any) -> Any:
        needs_guard = _pending_writes(session) or _statement_is_write(statement)
        if needs_guard:
            await ensure_guard()
        try:
            return await original_execute(statement, *args, **kwargs)
        except Exception:
            if needs_guard or guard_held:
                await recover_failed_write()
            raise

    async def guarded_exec(statement: Any, *args: Any, **kwargs: Any) -> Any:
        needs_guard = _pending_writes(session) or _statement_is_write(statement)
        if needs_guard:
            await ensure_guard()
        try:
            return await original_exec(statement, *args, **kwargs)
        except Exception:
            if needs_guard or guard_held:
                await recover_failed_write()
            raise

    async def guarded_flush(*args: Any, **kwargs: Any) -> Any:
        needs_guard = _pending_writes(session) or bool(args) or bool(kwargs.get("objects"))
        if needs_guard:
            await ensure_guard()
        try:
            return await original_flush(*args, **kwargs)
        except Exception:
            if needs_guard or guard_held:
                await recover_failed_write()
            raise

    async def guarded_refresh(*args: Any, **kwargs: Any) -> Any:
        if _pending_writes(session):
            await ensure_guard()
        try:
            return await original_refresh(*args, **kwargs)
        except Exception:
            if guard_held:
                await recover_failed_write()
            raise

    async def guarded_commit() -> None:
        if _pending_writes(session) or guard_held:
            await ensure_guard()
        try:
            await original_commit()
        except Exception:
            await recover_failed_write()
            raise
        else:
            release_guard()

    async def guarded_rollback() -> None:
        try:
            await original_rollback()
        finally:
            release_guard()

    async def guarded_close() -> None:
        try:
            await original_close()
        finally:
            release_guard()

    if original_exec is not None:
        session.exec = guarded_exec  # type: ignore[method-assign]
    session.execute = guarded_execute  # type: ignore[method-assign]
    session.flush = guarded_flush  # type: ignore[method-assign]
    session.refresh = guarded_refresh  # type: ignore[method-assign]
    session.commit = guarded_commit  # type: ignore[method-assign]
    session.rollback = guarded_rollback  # type: ignore[method-assign]
    session.close = guarded_close  # type: ignore[method-assign]
    session.info[_SQLITE_GUARD_INSTALLED_KEY] = True


_RUNTIME_LOCK_GUARD = threading.Lock()
_RUNTIME_PROCESS_LOCKS: dict[Path, SQLiteProcessLock] = {}


def ensure_sqlite_process_safety(database_url: str | None, workers: int) -> SQLiteProcessLock | None:
    """Validate worker count and acquire one process-lifetime lock per database."""
    validate_sqlite_worker_count(database_url, workers)
    path = sqlite_database_path(database_url)
    if path is None:
        return None
    resolved = path.resolve()
    with _RUNTIME_LOCK_GUARD:
        existing = _RUNTIME_PROCESS_LOCKS.get(resolved)
        if existing is not None:
            return existing
        process_lock = SQLiteProcessLock.acquire(resolved)
        _RUNTIME_PROCESS_LOCKS[resolved] = process_lock
        return process_lock


def release_sqlite_process_safety(database_url: str | None) -> None:
    """Release a cached process lock, primarily for orderly teardown and tests."""
    path = sqlite_database_path(database_url)
    if path is None:
        return
    resolved = path.resolve()
    with _RUNTIME_LOCK_GUARD:
        process_lock = _RUNTIME_PROCESS_LOCKS.pop(resolved, None)
    if process_lock is not None:
        process_lock.close()
