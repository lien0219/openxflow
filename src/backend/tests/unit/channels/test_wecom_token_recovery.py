import base64
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.wecom import WeComAPIError, WeComChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter
from langflow.channels.security.credentials import encrypt_credentials

_AES_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


def _adapter() -> ResilientWeComChannelAdapter:
    adapter = ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="ww-openxflow",
        corp_secret="corp-secret",
        agent_id="1000002",
        callback_token="callback-token",
        encoding_aes_key=_AES_KEY,
        api_base_url="https://wecom.example.test",
    )
    adapter._token_cache.clear()
    return adapter


def test_factory_builds_resilient_wecom_adapter() -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        channel_type="wecom",
        credentials_encrypted=encrypt_credentials(
            {
                "corp_id": "ww-openxflow",
                "corp_secret": "corp-secret",
                "agent_id": "1000002",
                "callback_token": "callback-token",
                "encoding_aes_key": _AES_KEY,
            }
        ),
        settings_data={"api_base_url": "https://wecom.example.test"},
    )

    adapter = build_channel_adapter(connection)

    assert isinstance(adapter, ResilientWeComChannelAdapter)
    assert isinstance(adapter, WeComChannelAdapter)


@pytest.mark.asyncio
@pytest.mark.parametrize("rejection_code", [40014, 42001])
async def test_wecom_rejected_token_is_refreshed_and_request_replayed_once(
    monkeypatch: pytest.MonkeyPatch,
    rejection_code: int,
) -> None:
    adapter = _adapter()
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 3600)
    requests: list[tuple[str, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.url.path, request.url.params.get("access_token")))
        if request.url.path == "/cgi-bin/gettoken":
            return httpx.Response(
                200,
                json={"errcode": 0, "access_token": "new-token", "expires_in": 7200},
            )
        if request.url.params.get("access_token") == "old-token":
            return httpx.Response(200, json={"errcode": rejection_code, "errmsg": "access token invalid"})
        return httpx.Response(200, json={"errcode": 0, "msgid": "message-1"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("langflow.channels.adapters.wecom_resilient.httpx.AsyncClient", client_factory)

    result = await adapter._api_request(
        "POST",
        "/cgi-bin/message/send",
        payload={"touser": "zhangsan"},
    )

    assert result["msgid"] == "message-1"
    assert requests == [
        ("/cgi-bin/message/send", "old-token"),
        ("/cgi-bin/gettoken", None),
        ("/cgi-bin/message/send", "new-token"),
    ]
    assert adapter._token_cache[adapter._token_cache_key][0] == "new-token"


@pytest.mark.asyncio
async def test_wecom_non_token_business_error_is_not_replayed(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    adapter._token_cache[adapter._token_cache_key] = ("current-token", time.monotonic() + 3600)
    request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(200, json={"errcode": 45009, "errmsg": "api frequency out of limit"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("langflow.channels.adapters.wecom_resilient.httpx.AsyncClient", client_factory)

    with pytest.raises(WeComAPIError, match="api frequency out of limit"):
        await adapter._api_request("POST", "/cgi-bin/message/send", payload={})

    assert request_count == 1
    assert adapter._token_cache[adapter._token_cache_key][0] == "current-token"


@pytest.mark.asyncio
async def test_wecom_second_token_rejection_is_not_replayed_again(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 3600)
    api_request_count = 0
    token_request_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal api_request_count, token_request_count
        if request.url.path == "/cgi-bin/gettoken":
            token_request_count += 1
            return httpx.Response(200, json={"errcode": 0, "access_token": "new-token", "expires_in": 7200})
        api_request_count += 1
        return httpx.Response(200, json={"errcode": 40014, "errmsg": "access token invalid"})

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr("langflow.channels.adapters.wecom_resilient.httpx.AsyncClient", client_factory)

    with pytest.raises(WeComAPIError, match="access token invalid"):
        await adapter._api_request("POST", "/cgi-bin/message/send", payload={})

    assert api_request_count == 2
    assert token_request_count == 1
