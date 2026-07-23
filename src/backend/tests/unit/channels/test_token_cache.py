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
    prune_provider_token_cache,
)
from langflow.channels.services.token_cache_metrics import (
    reset_token_cache_metrics_for_testing,
    token_cache_metrics_snapshot,
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


def test_prune_provider_token_cache_removes_expired_before_capacity() -> None:
    reset_token_cache_metrics_for_testing()
    cache = {
        "protected": ("current", 200.0),
        "expired-one": ("old-one", 50.0),
        "expired-two": ("old-two", 99.0),
        "valid-early": ("early", 150.0),
        "valid-late": ("late", 300.0),
    }

    expired, capacity = prune_provider_token_cache(
        provider="feishu",
        cache=cache,
        protected_key="protected",
        now=100.0,
        max_entries=3,
    )

    assert expired == 2
    assert capacity == 0
    assert set(cache) == {"protected", "valid-early", "valid-late"}
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.evictions == {("feishu", "expired"): 2}


def test_prune_provider_token_cache_evicts_earliest_expiry_and_protects_current() -> None:
    reset_token_cache_metrics_for_testing()
    cache = {
        "protected": ("current", 110.0),
        "first": ("one", 120.0),
        "second": ("two", 130.0),
        "third": ("three", 140.0),
    }

    expired, capacity = prune_provider_token_cache(
        provider="dingtalk",
        cache=cache,
        protected_key="protected",
        now=100.0,
        max_entries=2,
    )

    assert expired == 0
    assert capacity == 2
    assert set(cache) == {"protected", "third"}
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.evictions == {("dingtalk", "capacity"): 2}


def test_prune_provider_token_cache_rejects_invalid_capacity() -> None:
    with pytest.raises(ValueError, match="positive"):
        prune_provider_token_cache(
            provider="wecom",
            cache={},
            protected_key="current",
            max_entries=0,
        )


@pytest.mark.asyncio
async def test_cached_provider_token_reuses_valid_entry() -> None:
    cache = {"credential": ("cached-token", time.monotonic() + 60)}
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        return "new-token", time.monotonic() + 60

    token = await get_cached_provider_token(
        provider="feishu",
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
        provider="feishu",
        cache=cache,
        cache_key="credential",
        force_refresh=True,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
    )

    assert token == "new-token"
    assert cache["credential"][0] == "new-token"


@pytest.mark.asyncio
async def test_cached_provider_token_prunes_cache_after_refresh() -> None:
    now = time.monotonic()
    cache = {
        "expired": ("old", now - 1),
        "early": ("early", now + 10),
        "late": ("late", now + 20),
    }

    async def fetch() -> tuple[str, float]:
        return "current", time.monotonic() + 30

    token = await get_cached_provider_token(
        provider="wecom",
        cache=cache,
        cache_key="current",
        force_refresh=False,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
        max_entries=2,
    )

    assert token == "current"
    assert set(cache) == {"late", "current"}


@pytest.mark.asyncio
async def test_cached_provider_token_rejects_invalid_capacity_before_fetch() -> None:
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        return "token", time.monotonic() + 60

    with pytest.raises(ValueError, match="positive"):
        await get_cached_provider_token(
            provider="feishu",
            cache={},
            cache_key="credential",
            force_refresh=False,
            lock_pool=LoopLocalKeyedLockPool(),
            fetch_new_token=fetch,
            max_entries=0,
        )

    assert fetch_calls == 0


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
                provider="feishu",
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
                provider="feishu",
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
        provider="feishu",
        cache=cache,
        cache_key="credential",
        force_refresh=True,
        lock_pool=lock_pool,
        fetch_new_token=fetch,
    )

    assert next_token == "refreshed-2"
    assert fetch_calls == 2
