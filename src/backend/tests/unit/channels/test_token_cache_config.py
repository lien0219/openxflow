import time

import pytest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import (
    DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES,
    TOKEN_CACHE_MAX_ENTRIES_ENV,
    get_cached_provider_token,
    provider_token_cache_max_entries,
)


def test_provider_token_cache_capacity_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(TOKEN_CACHE_MAX_ENTRIES_ENV, raising=False)

    assert provider_token_cache_max_entries() == DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES


@pytest.mark.parametrize("value", ["1", "64", "2048"])
def test_provider_token_cache_capacity_accepts_positive_integer(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, value)

    assert provider_token_cache_max_entries() == int(value)


@pytest.mark.parametrize("value", ["", "invalid", "0", "-1", "1.5"])
def test_provider_token_cache_capacity_invalid_values_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, value)

    assert provider_token_cache_max_entries() == DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES


@pytest.mark.asyncio
async def test_explicit_cache_capacity_overrides_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, "1")
    now = time.monotonic()
    cache = {
        "early": ("early-token", now + 10),
        "late": ("late-token", now + 20),
    }

    async def fetch() -> tuple[str, float]:
        return "current-token", time.monotonic() + 30

    await get_cached_provider_token(
        provider="feishu",
        cache=cache,
        cache_key="current",
        force_refresh=False,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
        max_entries=2,
    )

    assert set(cache) == {"late", "current"}


@pytest.mark.asyncio
async def test_environment_capacity_is_applied_on_cache_hit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, "2")
    now = time.monotonic()
    cache = {
        "current": ("current-token", now + 30),
        "early": ("early-token", now + 10),
        "late": ("late-token", now + 20),
    }
    fetch_calls = 0

    async def fetch() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        return "unexpected", time.monotonic() + 60

    token = await get_cached_provider_token(
        provider="dingtalk",
        cache=cache,
        cache_key="current",
        force_refresh=False,
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch,
    )

    assert token == "current-token"
    assert fetch_calls == 0
    assert set(cache) == {"current", "late"}
