import time

import pytest
from prometheus_client import CollectorRegistry, generate_latest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import get_cached_provider_token
from langflow.channels.services.token_cache_metrics import (
    TokenCacheMetricsCollector,
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


def test_token_cache_metrics_collector_uses_only_provider_label() -> None:
    registry = CollectorRegistry(auto_describe=True)
    registry.register(TokenCacheMetricsCollector())
    body = generate_latest(registry)

    assert b"openxflow_channel_token_cache_hits_total" in body
    assert b"openxflow_channel_token_cache_misses_total" in body
    assert b"openxflow_channel_token_cache_forced_refreshes_total" in body
    assert b"openxflow_channel_token_cache_coalesced_refreshes_total" in body
    assert b"openxflow_channel_token_cache_refresh_succeeded_total" in body
    assert b"openxflow_channel_token_cache_refresh_failed_total" in body
    assert b"connection_id" not in body
    assert b"cache_key" not in body
    assert b"secret" not in body
