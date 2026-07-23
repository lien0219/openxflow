"""Bounded keyed asyncio locks isolated by event loop."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass
from threading import Lock
from weakref import WeakKeyDictionary


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class LoopLocalKeyedLockPool:
    """Provide one lock per key and event loop with bounded idle retention."""

    def __init__(self, *, max_keys_per_loop: int = 256) -> None:
        if max_keys_per_loop <= 0:
            raise ValueError("max_keys_per_loop must be positive")
        self._max_keys_per_loop = max_keys_per_loop
        self._registry_guard = Lock()
        self._locks: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            OrderedDict[str, _LockEntry],
        ] = WeakKeyDictionary()

    @asynccontextmanager
    async def hold(self, key: str):  # type: ignore[no-untyped-def]
        """Acquire the loop-local lock for one stable provider cache key."""
        if not key:
            raise ValueError("key must not be empty")
        loop = asyncio.get_running_loop()
        entry = self._entry_for_key(loop, key)
        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            self._release_entry(loop, key, entry)

    def retained_key_count_for_testing(self) -> int:
        """Return the current loop's retained key count for deterministic tests."""
        loop = asyncio.get_running_loop()
        with self._registry_guard:
            locks = self._locks.get(loop)
            return len(locks) if locks is not None else 0

    def _entry_for_key(self, loop: asyncio.AbstractEventLoop, key: str) -> _LockEntry:
        with self._registry_guard:
            locks = self._locks.get(loop)
            if locks is None:
                locks = OrderedDict()
                self._locks[loop] = locks
            entry = locks.get(key)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock())
                locks[key] = entry
            else:
                locks.move_to_end(key)
            entry.users += 1
            return entry

    def _release_entry(
        self,
        loop: asyncio.AbstractEventLoop,
        key: str,
        entry: _LockEntry,
    ) -> None:
        with self._registry_guard:
            locks = self._locks.get(loop)
            if locks is None:
                return
            current = locks.get(key)
            if current is not entry:
                return
            entry.users -= 1
            if entry.users < 0:
                raise RuntimeError("Keyed lock user count became negative")
            self._prune_idle_locks_locked(locks)

    def _prune_idle_locks_locked(self, locks: OrderedDict[str, _LockEntry]) -> None:
        while len(locks) > self._max_keys_per_loop:
            idle_key = next(
                (
                    candidate
                    for candidate, entry in locks.items()
                    if entry.users == 0 and not entry.lock.locked()
                ),
                None,
            )
            if idle_key is None:
                return
            locks.pop(idle_key, None)
