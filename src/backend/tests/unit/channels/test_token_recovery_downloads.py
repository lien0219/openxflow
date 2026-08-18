import base64
import time
from uuid import uuid4

import httpx
import pytest
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


class _ClientFactory:
    def __init__(self, handler):
        self._transport = httpx.MockTransport(handler)

    def __call__(self, *args, **kwargs):
        kwargs["transport"] = self._transport
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)


@pytest.mark.asyncio
async def test_feishu_file_download_replays_after_token_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret",
        api_base_url="https://open.feishu.test/open-apis",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/auth/v3/tenant_access_token/internal"):
            return httpx.Response(200, json={"code": 0, "tenant_access_token": "new-token", "expire": 7200})
        if request.headers.get("authorization") == "Bearer old-token":
            return httpx.Response(200, json={"code": 99991663, "msg": "tenant_access_token invalid"})
        return httpx.Response(200, content=b"file-bytes", headers={"content-type": "application/pdf"})

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    content, metadata = await adapter.download_file("message-1:file-key:file")

    assert content == b"file-bytes"
    assert metadata["content_type"] == "application/pdf"
    assert calls == [
        "/open-apis/im/v1/messages/message-1/resources/file-key",
        "/open-apis/auth/v3/tenant_access_token/internal",
        "/open-apis/im/v1/messages/message-1/resources/file-key",
    ]


@pytest.mark.asyncio
async def test_wecom_media_download_replays_after_token_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    encoding_key = base64.b64encode(bytes(range(32))).decode().rstrip("=")
    adapter = ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="ww-openxflow",
        corp_secret="corp-secret",
        agent_id=1000002,
        callback_token="callback-token",
        encoding_aes_key=encoding_key,
        api_base_url="https://qyapi.weixin.test",
    )
    adapter._token_cache[adapter._token_cache_key] = ("old-token", time.monotonic() + 600)
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/cgi-bin/gettoken"):
            return httpx.Response(200, json={"errcode": 0, "access_token": "new-token", "expires_in": 7200})
        token = request.url.params.get("access_token", "")
        tokens.append(token)
        if token == "old-token":
            return httpx.Response(200, json={"errcode": 42001, "errmsg": "access token expired"})
        return httpx.Response(
            200,
            content=b"image-bytes",
            headers={
                "content-type": "image/jpeg",
                "content-disposition": 'attachment; filename="photo.jpg"',
            },
        )

    monkeypatch.setattr(httpx, "AsyncClient", _ClientFactory(handler))
    content, metadata = await adapter.download_file("wecom:media-1")

    assert content == b"image-bytes"
    assert metadata["content_type"] == "image/jpeg"
    assert metadata["filename"] == "photo.jpg"
    assert tokens == ["old-token", "new-token"]
