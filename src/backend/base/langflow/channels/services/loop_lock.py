"""Async synchronization primitives that are safe across application event loops."""

from __future__ import annotations

import asyncio
from threading import Lock
from weakref import WeakKeyDictionary


class LoopLocalAsyncLock(asyncio.Lock):
    """Present one lock interface while keeping independent locks per event loop.

    Application tests, reloaders, and some server lifecycles may reuse adapter
    classes across multiple event loops. A plain module-level ``asyncio.Lock``
    can become bound to an earlier loop after contention. This wrapper delegates
    each operation to a lock owned by the currently running loop.
    """

    def __init__(self) -> None:
        super().__init__()
        self._registry_guard = Lock()
        self._locks: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Lock] = WeakKeyDictionary()

    async def acquire(self) -> bool:
        return await self._current_lock().acquire()

    def release(self) -> None:
        self._current_lock().release()

    def locked(self) -> bool:
        try:
            return self._current_lock().locked()
        except RuntimeError:
            return False

    def _current_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        with self._registry_guard:
            lock = self._locks.get(loop)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[loop] = lock
            return lock
