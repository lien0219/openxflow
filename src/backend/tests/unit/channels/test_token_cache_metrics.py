import asyncio
import time

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import get_cached_provider_token, prune_provider_token_cache
from langflow.channels.services.token_cache_metrics import (
    TokenCacheMetricsCollector,
    record_token_cache_eviction,
    reset_token_cache_metrics_for_testing,
    token_cache_metrics_snapshot,
)


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_token_cache_metrics_for_testing()


@pytest.mark.asyncio
async def test_token_cache_metrics_record_hit_refresh_and_failure() -> None:
    cache = {"feishu-key": ("cached", time.monotonic() + 60)}
    pool = LoopLocalKeyedLockPool()

    async def successful_fetch() -> tuple[str, float]:
        return "fresh", time.monotonic() + 60

    async def failed_fetch() -> tuple[str, float]:
        raise RuntimeError("provider unavailable")

    assert (
        await get_cached_provider_token(
            provider="feishu",
            cache=cache,
            cache_key="feishu-key",
            force_refresh=False,
            lock_pool=pool,
            fetch_new_token=successful_fetch,
        )
        == "cached"
    )
    assert (
        await get_cached_provider_token(
            provider="feishu",
            cache=cache,
            cache_key="feishu-key",
            force_refresh=True,
            lock_pool=pool,
            fetch_new_token=successful_fetch,
        )
        == "fresh"
    )

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await get_cached_provider_token(
            provider="dingtalk",
            cache={},
            cache_key="dingtalk-key",
            force_refresh=False,
            lock_pool=pool,
            fetch_new_token=failed_fetch,
        )

    snapshot = token_cache_metrics_snapshot()
    assert snapshot.hits == {"feishu": 1}
    assert snapshot.misses == {"dingtalk": 1}
    assert snapshot.forced_refreshes == {"feishu": 1}
    assert snapshot.refresh_succeeded == {"feishu": 1}
    assert snapshot.refresh_failed == {"dingtalk": 1}


@pytest.mark.asyncio
async def test_token_cache_metrics_count_concurrent_refresh_coalescing() -> None:
    cache: dict[str, tuple[str, float]] = {}
    pool = LoopLocalKeyedLockPool()
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()

    async def fetch() -> tuple[str, float]:
        fetch_started.set()
        await release_fetch.wait()
        return "shared-token", time.monotonic() + 60

    tasks = [
        asyncio.create_task(
            get_cached_provider_token(
                provider="wecom",
                cache=cache,
                cache_key="wecom-key",
                force_refresh=False,
                lock_pool=pool,
                fetch_new_token=fetch,
            )
        )
        for _ in range(8)
    ]
    await fetch_started.wait()
    await asyncio.sleep(0)
    release_fetch.set()

    assert await asyncio.gather(*tasks) == ["shared-token"] * 8
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.misses == {"wecom": 8}
    assert snapshot.coalesced_refreshes == {"wecom": 7}
    assert snapshot.refresh_succeeded == {"wecom": 1}
    assert snapshot.refresh_failed == {}


def test_token_cache_metrics_count_expired_and_capacity_evictions() -> None:
    cache = {
        "protected": ("current", 200.0),
        "expired": ("old", 50.0),
        "early": ("early", 120.0),
        "late": ("late", 300.0),
    }

    prune_provider_token_cache(
        provider="feishu",
        cache=cache,
        protected_key="protected",
        now=100.0,
        max_entries=2,
    )

    snapshot = token_cache_metrics_snapshot()
    assert snapshot.evictions == {
        ("feishu", "expired"): 1,
        ("feishu", "capacity"): 1,
    }


def test_token_cache_metrics_reject_negative_eviction_count() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        record_token_cache_eviction("wecom", "expired", -1)


def test_token_cache_metrics_collector_uses_only_bounded_labels() -> None:
    record_token_cache_eviction("feishu", "expired", 2)
    record_token_cache_eviction("dingtalk", "capacity", 1)

    registry = CollectorRegistry(auto_describe=True)
    registry.register(TokenCacheMetricsCollector())
    body = generate_latest(registry)

    assert b"openxflow_channel_token_cache_hits_total" in body
    assert b"openxflow_channel_token_cache_misses_total" in body
    assert b"openxflow_channel_token_cache_forced_refreshes_total" in body
    assert b"openxflow_channel_token_cache_coalesced_refreshes_total" in body
    assert b"openxflow_channel_token_cache_refresh_succeeded_total" in body
    assert b"openxflow_channel_token_cache_refresh_failed_total" in body
    assert b"openxflow_channel_token_cache_evictions_total" in body
    assert b'provider="feishu",reason="expired"' in body
    assert b'provider="dingtalk",reason="capacity"' in body
    assert b"connection_id" not in body
    assert b"cache_key" not in body
    assert b"secret" not in body
