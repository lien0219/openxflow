import asyncio
import math
import time

import pytest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import (
    InvalidProviderTokenResponseError,
    get_cached_provider_token,
    provider_token_cache_key,
    provider_token_lifetime_seconds,
)


def test_provider_token_cache_key_fingerprints_secret() -> None:
    first = provider_token_cache_key(
        provider="Feishu",
        api_base_url="https://open.feishu.test/open-apis/",
        public_id=" cli-test ",
        secret="secret-one",
    )
    same = provider_token_cache_key(
        provider="feishu",
        api_base_url="https://open.feishu.test/open-apis",
        public_id="cli-test",
        secret="secret-one",
    )
    rotated = provider_token_cache_key(
        provider="feishu",
        api_base_url="https://open.feishu.test/open-apis",
        public_id="cli-test",
        secret="secret-two",
    )

    assert first == same
    assert first != rotated
    assert "secret-one" not in first
    assert "secret-two" not in rotated
    assert len(first.rsplit(":", 1)[-1]) == 64


def test_provider_token_lifetime_accepts_numeric_values() -> None:
    assert provider_token_lifetime_seconds({"expire": 7200}, "expire", provider="Feishu") == 7200
    assert provider_token_lifetime_seconds({"expire": "120"}, "expire", provider="Feishu") == 120
    assert provider_token_lifetime_seconds({"expire": 1}, "expire", provider="Feishu") == 60
    assert provider_token_lifetime_seconds({}, "expire", provider="Feishu") == 7200


@pytest.mark.parametrize(
    "value",
    [None, True, False, "invalid", "nan", "inf", "-inf", 0, -1, math.nan, math.inf],
)
def test_provider_token_lifetime_rejects_invalid_values(value) -> None:
    with pytest.raises(InvalidProviderTokenResponseError, match="Feishu"):
        provider_token_lifetime_seconds({"expire": value}, "expire", provider="Feishu")


@pytest.mark.asyncio
async def test_cached_provider_token_reuses_valid_entry() -> None:
    cache = {"credential": ("cached-token", time.monotonic() + 60)}
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        return "new-token", time.monotonic() + 60

    token = await get_cached_provider_token(
        cache=cache,
        cache_key="credential",
        force_refresh=False,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
    )

    assert token == "cached-token"
    assert fetch_calls == 0


@pytest.mark.asyncio
async def test_cached_provider_token_force_refresh_replaces_valid_entry() -> None:
    cache = {"credential": ("cached-token", time.monotonic() + 60)}

    async def fetch() -> tuple[str, float]:
        return "new-token", time.monotonic() + 60

    token = await get_cached_provider_token(
        cache=cache,
        cache_key="credential",
        force_refresh=True,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
    )

    assert token == "new-token"
    assert cache["credential"][0] == "new-token"


@pytest.mark.asyncio
async def test_cached_provider_token_concurrent_miss_fetches_once() -> None:
    cache: dict[str, tuple[str, float]] = {}
    lock_pool = LoopLocalKeyedLockPool()
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        fetch_started.set()
        await release_fetch.wait()
        return "shared-token", time.monotonic() + 60

    tasks = [
        asyncio.create_task(
            get_cached_provider_token(
                cache=cache,
                cache_key="credential",
                force_refresh=False,
                lock_pool=lock_pool,
                fetch_new_token=fetch,
            )
        )
        for _ in range(8)
    ]
    await fetch_started.wait()
    await asyncio.sleep(0)
    release_fetch.set()

    assert await asyncio.gather(*tasks) == ["shared-token"] * 8
    assert fetch_calls == 1


@pytest.mark.asyncio
async def test_cached_provider_token_concurrent_force_refresh_fetches_once() -> None:
    cache = {"credential": ("old-token", time.monotonic() + 60)}
    lock_pool = LoopLocalKeyedLockPool()
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        fetch_started.set()
        await release_fetch.wait()
        return f"refreshed-{fetch_calls}", time.monotonic() + 60

    tasks = [
        asyncio.create_task(
            get_cached_provider_token(
                cache=cache,
                cache_key="credential",
                force_refresh=True,
                lock_pool=lock_pool,
                fetch_new_token=fetch,
            )
        )
        for _ in range(6)
    ]
    await fetch_started.wait()
    await asyncio.sleep(0)
    release_fetch.set()

    assert await asyncio.gather(*tasks) == ["refreshed-1"] * 6
    assert fetch_calls == 1

    next_token = await get_cached_provider_token(
        cache=cache,
        cache_key="credential",
        force_refresh=True,
        lock_pool=lock_pool,
        fetch_new_token=fetch,
    )

    assert next_token == "refreshed-2"
    assert fetch_calls == 2
