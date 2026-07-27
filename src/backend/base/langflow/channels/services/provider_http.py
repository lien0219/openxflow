"""Shared HTTP clients and bounded provider downloads for channel adapters."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from threading import Lock
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary

import httpx

_DEFAULT_DOWNLOAD_LIMIT_BYTES = 50 * 1024 * 1024
_DEFAULT_MAX_CONNECTIONS = 32
_DEFAULT_MAX_KEEPALIVE_CONNECTIONS = 16
_DEFAULT_KEEPALIVE_EXPIRY_SECONDS = 30.0


class ChannelDownloadTooLargeError(ValueError):
    """Raised before or during a provider download that exceeds the configured limit."""

    def __init__(self, *, limit_bytes: int, actual_bytes: int | None = None) -> None:
        self.limit_bytes = limit_bytes
        self.actual_bytes = actual_bytes
        actual = f" ({actual_bytes} bytes)" if actual_bytes is not None else ""
        super().__init__(f"Channel file exceeds the {limit_bytes}-byte download limit{actual}")


@dataclass(frozen=True)
class DownloadedProviderFile:
    content: bytes
    headers: dict[str, str]
    final_url: str
    status_code: int


def channel_download_limit_bytes() -> int:
    """Return the operator-configured maximum provider download size."""
    raw = os.getenv("LANGFLOW_CHANNEL_MAX_DOWNLOAD_BYTES")
    if raw is None:
        return _DEFAULT_DOWNLOAD_LIMIT_BYTES
    try:
        parsed = int(raw)
    except ValueError:
        return _DEFAULT_DOWNLOAD_LIMIT_BYTES
    return parsed if parsed > 0 else _DEFAULT_DOWNLOAD_LIMIT_BYTES


def _origin(raw_url: str) -> str:
    parsed = urlsplit(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provider URL must use http or https")
    return f"{parsed.scheme}://{parsed.netloc}"


class _LoopLocalProviderClientPool:
    """Retain bounded HTTP connection pools per event loop and provider origin."""

    def __init__(self) -> None:
        self._guard = Lock()
        self._clients: WeakKeyDictionary[
            asyncio.AbstractEventLoop,
            dict[str, httpx.AsyncClient],
        ] = WeakKeyDictionary()

    def get(
        self,
        *,
        provider: str,
        base_url: str,
        timeout_seconds: float,
        follow_redirects: bool,
    ) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        origin = _origin(base_url)
        normalized_timeout = max(0.1, float(timeout_seconds))
        client_factory_id = id(httpx.AsyncClient)
        key = (
            f"{provider.strip().lower()}|{origin}|{normalized_timeout:g}|"
            f"{int(follow_redirects)}|{client_factory_id}"
        )
        with self._guard:
            clients = self._clients.get(loop)
            if clients is None:
                clients = {}
                self._clients[loop] = clients
            client = clients.get(key)
            if client is None or client.is_closed:
                client = httpx.AsyncClient(
                    timeout=httpx.Timeout(normalized_timeout),
                    limits=httpx.Limits(
                        max_connections=_DEFAULT_MAX_CONNECTIONS,
                        max_keepalive_connections=_DEFAULT_MAX_KEEPALIVE_CONNECTIONS,
                        keepalive_expiry=_DEFAULT_KEEPALIVE_EXPIRY_SECONDS,
                    ),
                    follow_redirects=follow_redirects,
                    headers={"User-Agent": "OpenXFlow-Channel-Gateway/1"},
                )
                clients[key] = client
            return client

    async def close_current_loop(self) -> None:
        loop = asyncio.get_running_loop()
        with self._guard:
            clients = tuple((self._clients.pop(loop, None) or {}).values())
        if clients:
            await asyncio.gather(*(client.aclose() for client in clients), return_exceptions=True)

    def current_loop_client_count_for_testing(self) -> int:
        loop = asyncio.get_running_loop()
        with self._guard:
            clients = self._clients.get(loop)
            return len(clients) if clients is not None else 0


_CLIENT_POOL = _LoopLocalProviderClientPool()


def provider_http_client(
    provider: str,
    base_url: str,
    timeout_seconds: float,
    *,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """Return a reusable loop-local client for one provider origin."""
    return _CLIENT_POOL.get(
        provider=provider,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        follow_redirects=follow_redirects,
    )


def provider_http_client_for_url(
    provider: str,
    url: str,
    timeout_seconds: float,
    *,
    follow_redirects: bool = False,
) -> httpx.AsyncClient:
    """Return a reusable client keyed by the origin of a dynamic provider URL."""
    return provider_http_client(
        provider,
        _origin(url),
        timeout_seconds,
        follow_redirects=follow_redirects,
    )


async def close_provider_http_clients() -> None:
    """Close all provider clients bound to the current event loop."""
    await _CLIENT_POOL.close_current_loop()


async def reset_provider_http_clients_for_testing() -> None:
    """Close current-loop clients so tests do not retain mocked transports."""
    await close_provider_http_clients()


def provider_http_client_count_for_testing() -> int:
    """Return current-loop client count for deterministic tests."""
    return _CLIENT_POOL.current_loop_client_count_for_testing()


async def download_provider_file(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    max_bytes: int | None = None,
) -> DownloadedProviderFile:
    """Stream one provider file into a bounded buffer and fail immediately on overflow."""
    limit = max_bytes or channel_download_limit_bytes()
    if limit <= 0:
        raise ValueError("max_bytes must be positive")

    async with client.stream("GET", url, params=params, headers=headers) as response:
        response.raise_for_status()
        declared_size = response.headers.get("content-length")
        if declared_size:
            try:
                parsed_size = int(declared_size)
            except ValueError:
                parsed_size = None
            if parsed_size is not None and parsed_size > limit:
                raise ChannelDownloadTooLargeError(limit_bytes=limit, actual_bytes=parsed_size)

        chunks: list[bytes] = []
        received = 0
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            received += len(chunk)
            if received > limit:
                raise ChannelDownloadTooLargeError(limit_bytes=limit, actual_bytes=received)
            chunks.append(chunk)

        return DownloadedProviderFile(
            content=b"".join(chunks),
            headers={str(key): str(value) for key, value in response.headers.items()},
            final_url=str(response.url),
            status_code=response.status_code,
        )
