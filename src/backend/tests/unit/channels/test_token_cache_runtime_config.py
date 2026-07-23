import pytest

from langflow.api.v1.channel_runtime import read_channel_runtime
from langflow.channels.services.token_cache import TOKEN_CACHE_MAX_ENTRIES_ENV


@pytest.mark.asyncio
async def test_channel_runtime_exposes_token_cache_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, "2048")

    result = await read_channel_runtime(object())

    assert result.token_cache.max_entries == 2048


@pytest.mark.asyncio
async def test_channel_runtime_normalizes_invalid_token_cache_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(TOKEN_CACHE_MAX_ENTRIES_ENV, "invalid")

    result = await read_channel_runtime(object())

    assert result.token_cache.max_entries == 512
