from uuid import uuid4

import httpx
import pytest
from langflow.channels.adapters.dingtalk import DingTalkAPIError
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.feishu import FeishuAPIError
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComAPIError
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


class _ClientFactory:
    def __init__(self, handler):
        self._transport = httpx.MockTransport(handler)

    def __call__(self, *args, **kwargs):
        kwargs["transport"] = self._transport
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("expire", [None, True, "invalid", "nan", "inf", 0, -1])
async def test_feishu_invalid_token_lifetime_raises_provider_error(monkeypatch, expire) -> None:
    adapter = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret",
        api_base_url="https://open.feishu.test/open-apis",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"code": 0, "tenant_access_token": "token", "expire": expire},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(FeishuAPIError, match="lifetime"):
        await adapter._fetch_tenant_access_token_entry()


@pytest.mark.asyncio
@pytest.mark.parametrize("expire", [None, True, "invalid", "nan", "inf", 0, -1])
async def test_dingtalk_invalid_token_lifetime_raises_provider_error(monkeypatch, expire) -> None:
    adapter = ResilientDingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="secret",
        api_base_url="https://api.dingtalk.test",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"accessToken": "token", "expireIn": expire})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(DingTalkAPIError, match="lifetime"):
        await adapter._fetch_access_token_entry()


@pytest.mark.asyncio
@pytest.mark.parametrize("expire", [None, True, "invalid", "nan", "inf", 0, -1])
async def test_wecom_invalid_token_lifetime_raises_provider_error(monkeypatch, expire) -> None:
    adapter = ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="corp-id",
        corp_secret="secret",
        agent_id=1,
        callback_token="callback-token",
        encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        api_base_url="https://qyapi.weixin.test",
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"errcode": 0, "access_token": "token", "expires_in": expire},
        )

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(WeComAPIError, match="lifetime"):
        await adapter._fetch_access_token_entry()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter", "method", "error_type"),
    [
        (
            ResilientEncryptedFeishuChannelAdapter(
                uuid4(),
                app_id="cli-test",
                app_secret="secret",
                api_base_url="https://open.feishu.test/open-apis",
            ),
            "_fetch_tenant_access_token_entry",
            FeishuAPIError,
        ),
        (
            ResilientDingTalkChannelAdapter(
                uuid4(),
                client_id="ding-client",
                client_secret="secret",
                api_base_url="https://api.dingtalk.test",
            ),
            "_fetch_access_token_entry",
            DingTalkAPIError,
        ),
        (
            ResilientWeComChannelAdapter(
                uuid4(),
                corp_id="corp-id",
                corp_secret="secret",
                agent_id=1,
                callback_token="callback-token",
                encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
                api_base_url="https://qyapi.weixin.test",
            ),
            "_fetch_access_token_entry",
            WeComAPIError,
        ),
    ],
)
async def test_provider_token_endpoint_requires_json_object(
    monkeypatch,
    adapter,
    method,
    error_type,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    with pytest.raises(error_type, match="Invalid"):
        await getattr(adapter, method)()
