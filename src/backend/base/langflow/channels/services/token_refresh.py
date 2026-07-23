"""Helpers for recovering from provider access-token rejection."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx

from langflow.channels.services.loop_lock import LoopLocalAsyncLock
from langflow.channels.services.metrics import (
    record_token_rejection,
    record_token_refresh_failure,
    record_token_refresh_success,
    record_token_replay,
)

_TResponse = TypeVar("_TResponse")
TokenCache = dict[str, tuple[str, float]]


def response_json_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return a JSON object response body without raising for binary or malformed bodies."""
    if not response.content:
        return None
    try:
        body = response.json()
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def is_access_token_rejection(
    response: httpx.Response,
    body: dict[str, Any] | None,
    *,
    known_codes: set[str],
    code_fields: tuple[str, ...] = ("code", "errcode"),
    message_fields: tuple[str, ...] = ("message", "msg", "errmsg"),
) -> bool:
    """Detect an explicit provider rejection of the supplied access token."""
    if response.status_code == 401:
        return True
    if body is None:
        return False

    for field in code_fields:
        value = body.get(field)
        if value is not None and str(value).strip().lower() in known_codes:
            return True

    message = " ".join(str(body.get(field) or "") for field in message_fields).strip().lower()
    if not message:
        return False
    mentions_token = any(term in message for term in ("access token", "access_token", "accesstoken", "tenant_access_token"))
    indicates_rejection = any(
        term in message
        for term in (
            "invalid",
            "expired",
            "expire",
            "unauthorized",
            "无效",
            "过期",
            "失效",
        )
    )
    return mentions_token and indicates_rejection


async def refresh_rejected_cached_token(
    *,
    cache: TokenCache,
    cache_key: str,
    rejected_token: str,
    lock: LoopLocalAsyncLock,
    fetch_new_token: Callable[[], Awaitable[tuple[str, float]]],
    provider: str = "unknown",
) -> str:
    """Refresh a rejected token once while allowing concurrent callers to reuse the winner."""
    async with lock:
        cached = cache.get(cache_key)
        if cached is not None and cached[0] != rejected_token and cached[1] > time.monotonic():
            return cached[0]

        try:
            token, expires_at = await fetch_new_token()
        except Exception:
            record_token_refresh_failure(provider)
            raise
        cache[cache_key] = (token, expires_at)
        record_token_refresh_success(provider)
        return token


async def request_with_token_refresh(
    *,
    get_token: Callable[[], Awaitable[str]],
    refresh_token: Callable[[str], Awaitable[str]],
    send: Callable[[str], Awaitable[_TResponse]],
    is_rejected: Callable[[_TResponse], bool],
    provider: str = "unknown",
) -> _TResponse:
    """Send once and replay at most once after an explicit access-token rejection."""
    token = await get_token()
    response = await send(token)
    if not is_rejected(response):
        return response
    record_token_rejection(provider)
    refreshed = await refresh_token(token)
    record_token_replay(provider)
    return await send(refreshed)
