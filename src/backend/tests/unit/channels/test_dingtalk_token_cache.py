import asyncio
from uuid import uuid4

import pytest

from langflow.channels.adapters import dingtalk as dingtalk_module
from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter


class _FakeResponse:
    content = b'{"accessToken":"token-1","expireIn":7200}'

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"accessToken": "token-1", "expireIn": 7200}


@pytest.mark.asyncio
async def test_concurrent_dingtalk_token_requests_share_single_refresh(monkeypatch) -> None:
    adapter = DingTalkChannelAdapter(
        uuid4(),
        client_id="concurrent-client",
        client_secret="concurrent-secret",
    )
    DingTalkChannelAdapter._token_cache.pop(adapter._token_cache_key, None)
    request_count = 0

    class _FakeAsyncClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            return None

        async def post(self, _url, *, json):
            nonlocal request_count
            assert json == {
                "clientId": "concurrent-client",
                "clientSecret": "concurrent-secret",
            }
            request_count += 1
            await asyncio.sleep(0.01)
            return _FakeResponse()

    monkeypatch.setattr(dingtalk_module.httpx, "AsyncClient", _FakeAsyncClient)

    tokens = await asyncio.gather(*(adapter._access_token() for _ in range(10)))

    assert tokens == ["token-1"] * 10
    assert request_count == 1


@pytest.mark.asyncio
async def test_dingtalk_force_refresh_remains_serialized(monkeypatch) -> None:
    adapter = DingTalkChannelAdapter(
        uuid4(),
        client_id="force-refresh-client",
        client_secret="force-refresh-secret",
    )
    DingTalkChannelAdapter._token_cache.pop(adapter._token_cache_key, None)
    request_count = 0

    class _FakeAsyncClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, _exc_type, _exc, _tb) -> None:
            return None

        async def post(self, _url, *, json):
            nonlocal request_count
            del json
            request_count += 1
            await asyncio.sleep(0)
            return _FakeResponse()

    monkeypatch.setattr(dingtalk_module.httpx, "AsyncClient", _FakeAsyncClient)

    await asyncio.gather(
        adapter._access_token(force_refresh=True),
        adapter._access_token(force_refresh=True),
    )

    assert request_count == 2
