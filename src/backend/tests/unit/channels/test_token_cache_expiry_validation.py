import math
import time

import pytest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import (
    DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES,
    InvalidProviderTokenResponseError,
    get_cached_provider_token,
)
from langflow.channels.services.token_cache_metrics import (
    reset_token_cache_metrics_for_testing,
    token_cache_metrics_snapshot,
)


def test_provider_token_cache_default_capacity_is_bounded() -> None:
    assert DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES == 512


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expires_at",
    [math.nan, math.inf, -math.inf, 0.0],
)
async def test_cached_provider_token_rejects_invalid_absolute_expiry(expires_at: float) -> None:
    reset_token_cache_metrics_for_testing()
    previous_expiry = time.monotonic() - 1
    cache = {"credential": ("previous-token", previous_expiry)}

    async def fetch() -> tuple[str, float]:
        return "invalid-token", expires_at

    with pytest.raises(InvalidProviderTokenResponseError, match="absolute expiry"):
        await get_cached_provider_token(
            provider="feishu",
            cache=cache,
            cache_key="credential",
            force_refresh=False,
            lock_pool=LoopLocalKeyedLockPool(),
            fetch_new_token=fetch,
        )

    assert cache == {"credential": ("previous-token", previous_expiry)}
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.refresh_failed == {"feishu": 1}
    assert snapshot.refresh_succeeded == {}


@pytest.mark.asyncio
async def test_cached_provider_token_rejects_expiry_that_elapsed_during_fetch() -> None:
    reset_token_cache_metrics_for_testing()
    cache: dict[str, tuple[str, float]] = {}

    async def fetch() -> tuple[str, float]:
        return "already-expired", time.monotonic() - 0.001

    with pytest.raises(InvalidProviderTokenResponseError, match="absolute expiry"):
        await get_cached_provider_token(
            provider="dingtalk",
            cache=cache,
            cache_key="credential",
            force_refresh=False,
            lock_pool=LoopLocalKeyedLockPool(),
            fetch_new_token=fetch,
        )

    assert cache == {}
    snapshot = token_cache_metrics_snapshot()
    assert snapshot.refresh_failed == {"dingtalk": 1}
    assert snapshot.refresh_succeeded == {}
