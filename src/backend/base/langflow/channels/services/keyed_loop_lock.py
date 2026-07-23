"""Bounded keyed asyncio locks isolated by event loop."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from threading import Lock
from weakref import WeakKeyDictionary


class LoopLocalKeyedLockPool:
    """Provide one lock per key and event loop with bounded idle retention."""

    def __init__(self, *, max_keys_per_loop: int = 256) -> None:
        if max_keys_per_loop <= 0:
            raise ValueError("max_keys_per_loop must be positive")
        self._max_keys_per_loop = max_keys_per_loop
        self._registry_guard = Lock()
        self._locks: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            OrderedDict[str, asyncio.Lock],
        ] = WeakKeyDictionary()

    @asynccontextmanager
    async def hold(self, key: str):  # type: ignore[no-untyped-def]
        """Acquire the loop-local lock for one stable provider cache key."""
        if not key:
            raise ValueError("key must not be empty")
        lock = self._lock_for_key(key)
        await lock.acquire()
        try:
            yield
        finally:
            lock.release()
            self._prune_idle_locks()

    def _lock_for_key(self, key: str) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._registry_guard:
            locks = self._locks.get(loop)
            if locks is None:
                locks = OrderedDict()
                self._locks[loop] = locks
            lock = locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                locks[key] = lock
            else:
                locks.move_to_end(key)
            return lock

    def _prune_idle_locks(self) -> None:
        loop = asyncio.get_running_loop()
        with self._registry_guard:
            locks = self._locks.get(loop)
            if locks is None:
                return
            while len(locks) > self._max_keys_per_loop:
                idle_key = next(
                    (candidate for candidate, lock in locks.items() if not lock.locked()),
                    None,
                )
                if idle_key is None:
                    return
                locks.pop(idle_key, None)
