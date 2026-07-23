import asyncio

import pytest

from langflow.channels.services.loop_lock import LoopLocalAsyncLock


def test_loop_local_lock_can_be_reused_across_event_loops() -> None:
    lock = LoopLocalAsyncLock()

    async def use_lock() -> None:
        async with lock:
            assert lock.locked() is True
        assert lock.locked() is False

    asyncio.run(use_lock())
    asyncio.run(use_lock())


@pytest.mark.asyncio
async def test_loop_local_lock_serializes_tasks_in_same_loop() -> None:
    lock = LoopLocalAsyncLock()
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_started = asyncio.Event()

    async def first() -> None:
        async with lock:
            first_started.set()
            await release_first.wait()

    async def second() -> None:
        async with lock:
            second_started.set()

    first_task = asyncio.create_task(first())
    await first_started.wait()
    second_task = asyncio.create_task(second())
    await asyncio.sleep(0)

    assert second_started.is_set() is False
    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_started.is_set() is True
