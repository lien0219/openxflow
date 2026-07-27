import httpx
import pytest
from langflow.channels.services.provider_http import (
    ChannelDownloadTooLargeError,
    download_provider_file,
    provider_http_client,
    provider_http_client_count_for_testing,
    reset_provider_http_clients_for_testing,
)

_ORIGINAL_ASYNC_CLIENT = httpx.AsyncClient


class _ClientFactory:
    def __init__(self, handler):
        self._transport = httpx.MockTransport(handler)
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        kwargs["transport"] = self._transport
        return _ORIGINAL_ASYNC_CLIENT(*args, **kwargs)


@pytest.mark.asyncio
async def test_provider_http_client_reuses_one_origin_pool(monkeypatch) -> None:
    factory = _ClientFactory(lambda request: httpx.Response(200, json={"ok": True}))
    monkeypatch.setattr(httpx, "AsyncClient", factory)

    first = provider_http_client("telegram", "https://api.telegram.test/bot", 5)
    second = provider_http_client("telegram", "https://api.telegram.test/file", 5)

    assert first is second
    assert factory.calls == 1
    assert provider_http_client_count_for_testing() == 1
    await reset_provider_http_clients_for_testing()


@pytest.mark.asyncio
async def test_provider_download_rejects_declared_oversize(monkeypatch) -> None:
    factory = _ClientFactory(
        lambda request: httpx.Response(
            200,
            headers={"content-length": "11", "content-type": "application/octet-stream"},
            content=b"hello world",
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    client = provider_http_client("telegram", "https://api.telegram.test", 5)

    with pytest.raises(ChannelDownloadTooLargeError, match="10-byte"):
        await download_provider_file(client, "https://api.telegram.test/file", max_bytes=10)

    await reset_provider_http_clients_for_testing()


@pytest.mark.asyncio
async def test_provider_download_returns_bounded_content(monkeypatch) -> None:
    factory = _ClientFactory(
        lambda request: httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"hello",
        )
    )
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    client = provider_http_client("feishu", "https://open.feishu.test/open-apis", 5)

    downloaded = await download_provider_file(client, "https://open.feishu.test/file", max_bytes=10)

    assert downloaded.content == b"hello"
    assert downloaded.headers["content-type"] == "text/plain"
    await reset_provider_http_clients_for_testing()
