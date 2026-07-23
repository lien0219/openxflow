import time
from uuid import uuid4

import httpx
import pytest

from langflow.channels.adapters.dingtalk import DingTalkAPIError
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.feishu import FeishuAPIError
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


class _ClientFactory:
    def __init__(self, handler):
        self._transport = httpx.MockTransport(handler)

    def __call__(self, *args, **kwargs):
        kwargs["transport"] = self._transport
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)


@pytest.mark.asyncio
async def test_feishu_replays_once_after_rejected_token(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret",
        api_base_url="https://open.feishu.test/open-apis",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("authorization", "")
        calls.append((request.url.path, token))
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "new-token", "expire": 7200})
        if token == "Bearer old-token":
            return httpx.Response(200, json={"code": 99991663, "msg": "tenant_access_token invalid"})
        return httpx.Response(200, json={"code": 0, "data": {"message_id": "msg-1"}})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    result = await adapter._request("POST", "/im/v1/messages", payload={"text": "hello"})

    assert result == {"message_id": "msg-1"}
    assert calls == [
        ("/open-apis/im/v1/messages", "Bearer old-token"),
        ("/open-apis/auth/v3/tenant_access_token/internal", ""),
        ("/open-apis/im/v1/messages", "Bearer new-token"),
    ]


@pytest.mark.asyncio
async def test_feishu_second_rejection_is_not_replayed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret",
        api_base_url="https://open.feishu.test/open-apis",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    api_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_calls
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "new-token", "expire": 7200})
        api_calls += 1
        return httpx.Response(200, json={"code": 99991663, "msg": "tenant_access_token invalid"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(FeishuAPIError, match="invalid"):
        await adapter._request("POST", "/im/v1/messages", payload={})
    assert api_calls == 2


@pytest.mark.asyncio
async def test_dingtalk_replays_once_after_rejected_token(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ResilientDingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="ding-secret",
        api_base_url="https://api.dingtalk.test",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        token = request.headers.get("x-acs-dingtalk-access-token", "")
        calls.append((request.url.path, token))
        if request.url.path.endswith("/v1.0/oauth2/accessToken"):
            return httpx.Response(200, json={"accessToken": "new-token", "expireIn": 7200})
        if token == "old-token":
            return httpx.Response(401, json={"code": "InvalidAccessToken", "message": "access token invalid"})
        return httpx.Response(200, json={"processQueryKey": "query-1"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    result = await adapter._api_request("POST", "/v1.0/robot/groupMessages/send", payload={})

    assert result["processQueryKey"] == "query-1"
    assert calls == [
        ("/v1.0/robot/groupMessages/send", "old-token"),
        ("/v1.0/oauth2/accessToken", ""),
        ("/v1.0/robot/groupMessages/send", "new-token"),
    ]


@pytest.mark.asyncio
async def test_dingtalk_business_error_does_not_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ResilientDingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="ding-secret",
        api_base_url="https://api.dingtalk.test",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": "InvalidParameter", "message": "robot code invalid"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(DingTalkAPIError, match="robot code invalid"):
        await adapter._api_request("POST", "/v1.0/robot/groupMessages/send", payload={})
    assert calls == 1
