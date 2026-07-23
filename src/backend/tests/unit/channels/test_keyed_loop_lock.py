import asyncio

import pytest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool


@pytest.mark.asyncio
async def test_keyed_lock_serializes_same_key() -> None:
    pool = LoopLocalKeyedLockPool()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()

    async def first() -> None:
        async with pool.hold("same"):
            first_entered.set()
            await release_first.wait()

    async def second() -> None:
        await first_entered.wait()
        async with pool.hold("same"):
            second_entered.set()

    first_task = asyncio.create_task(first())
    second_task = asyncio.create_task(second())
    await first_entered.wait()
    await asyncio.sleep(0)
    assert second_entered.is_set() is False

    release_first.set()
    await asyncio.gather(first_task, second_task)
    assert second_entered.is_set() is True


@pytest.mark.asyncio
async def test_keyed_lock_allows_different_keys_concurrently() -> None:
    pool = LoopLocalKeyedLockPool()
    both_entered = asyncio.Event()
    entered = 0
    release = asyncio.Event()

    async def worker(key: str) -> None:
        nonlocal entered
        async with pool.hold(key):
            entered += 1
            if entered == 2:
                both_entered.set()
            await release.wait()

    first_task = asyncio.create_task(worker("first"))
    second_task = asyncio.create_task(worker("second"))
    await asyncio.wait_for(both_entered.wait(), timeout=1)
    release.set()
    await asyncio.gather(first_task, second_task)


@pytest.mark.asyncio
async def test_keyed_lock_prunes_idle_entries() -> None:
    pool = LoopLocalKeyedLockPool(max_keys_per_loop=2)

    for key in ("one", "two", "three"):
        async with pool.hold(key):
            pass

    assert pool.retained_key_count_for_testing() <= 2


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_leak_key_usage() -> None:
    pool = LoopLocalKeyedLockPool(max_keys_per_loop=1)
    holder_entered = asyncio.Event()
    release_holder = asyncio.Event()

    async def holder() -> None:
        async with pool.hold("shared"):
            holder_entered.set()
            await release_holder.wait()

    holder_task = asyncio.create_task(holder())
    await holder_entered.wait()

    waiter_task = asyncio.create_task(pool.hold("shared").__aenter__())
    await asyncio.sleep(0)
    waiter_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiter_task

    release_holder.set()
    await holder_task
    async with pool.hold("replacement"):
        pass

    assert pool.retained_key_count_for_testing() <= 1


def test_keyed_lock_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="positive"):
        LoopLocalKeyedLockPool(max_keys_per_loop=0)
