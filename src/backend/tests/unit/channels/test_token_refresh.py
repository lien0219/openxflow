import asyncio
import time

import httpx
import pytest

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_refresh import (
    is_access_token_rejection,
    refresh_rejected_cached_token,
    request_with_token_refresh,
    response_json_object,
)


def _response(status_code: int, body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.example/api")
    if body is None:
        return httpx.Response(status_code, request=request)
    return httpx.Response(status_code, request=request, json=body)


def test_response_json_object_handles_object_and_non_json_bodies() -> None:
    assert response_json_object(_response(200, {"code": 0})) == {"code": 0}

    request = httpx.Request("GET", "https://provider.example/file")
    binary = httpx.Response(200, request=request, content=b"\xff\x00")
    assert response_json_object(binary) is None


def test_access_token_rejection_requires_explicit_authentication_signal() -> None:
    assert is_access_token_rejection(_response(401), None, known_codes=set()) is True
    assert (
        is_access_token_rejection(
            _response(200, {"errcode": 40014, "errmsg": "invalid access_token"}),
            {"errcode": 40014, "errmsg": "invalid access_token"},
            known_codes={"40014", "42001"},
        )
        is True
    )
    assert (
        is_access_token_rejection(
            _response(200, {"code": "rate_limited", "message": "system busy"}),
            {"code": "rate_limited", "message": "system busy"},
            known_codes={"invalid_token"},
        )
        is False
    )


@pytest.mark.asyncio
async def test_request_success_does_not_refresh_token() -> None:
    refresh_calls = 0
    sent_tokens: list[str] = []

    async def get_token() -> str:
        return "cached-token"

    async def refresh_token(_rejected: str) -> str:
        nonlocal refresh_calls
        refresh_calls += 1
        return "new-token"

    async def send(token: str) -> httpx.Response:
        sent_tokens.append(token)
        return _response(200, {"code": 0})

    response = await request_with_token_refresh(
        get_token=get_token,
        refresh_token=refresh_token,
        send=send,
        is_rejected=lambda value: value.status_code == 401,
    )

    assert response.status_code == 200
    assert sent_tokens == ["cached-token"]
    assert refresh_calls == 0


@pytest.mark.asyncio
async def test_request_replays_at_most_once_after_token_rejection() -> None:
    sent_tokens: list[str] = []

    async def get_token() -> str:
        return "cached-token"

    async def refresh_token(rejected: str) -> str:
        assert rejected == "cached-token"
        return "new-token"

    async def send(token: str) -> httpx.Response:
        sent_tokens.append(token)
        return _response(401, {"code": "invalid_token"})

    response = await request_with_token_refresh(
        get_token=get_token,
        refresh_token=refresh_token,
        send=send,
        is_rejected=lambda value: value.status_code == 401,
    )

    assert response.status_code == 401
    assert sent_tokens == ["cached-token", "new-token"]


@pytest.mark.asyncio
async def test_concurrent_rejected_tokens_share_one_refresh() -> None:
    cache = {"connection": ("rejected-token", time.monotonic() + 3600)}
    lock_pool = LoopLocalKeyedLockPool()
    fetch_calls = 0

    async def fetch_new_token() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        await asyncio.sleep(0)
        return "replacement-token", time.monotonic() + 3600

    tokens = await asyncio.gather(
        *(
            refresh_rejected_cached_token(
                cache=cache,
                cache_key="connection",
                rejected_token="rejected-token",
                lock_pool=lock_pool,
                fetch_new_token=fetch_new_token,
            )
            for _ in range(10)
        )
    )

    assert tokens == ["replacement-token"] * 10
    assert fetch_calls == 1


@pytest.mark.asyncio
async def test_different_cache_keys_refresh_concurrently() -> None:
    now = time.monotonic() + 3600
    cache = {
        "first": ("rejected-first", now),
        "second": ("rejected-second", now),
    }
    lock_pool = LoopLocalKeyedLockPool()
    entered: set[str] = set()
    both_entered = asyncio.Event()
    release = asyncio.Event()

    async def refresh(key: str, rejected: str) -> str:
        async def fetch_new_token() -> tuple[str, float]:
            entered.add(key)
            if len(entered) == 2:
                both_entered.set()
            await release.wait()
            return f"new-{key}", time.monotonic() + 3600

        return await refresh_rejected_cached_token(
            cache=cache,
            cache_key=key,
            rejected_token=rejected,
            lock_pool=lock_pool,
            fetch_new_token=fetch_new_token,
        )

    first = asyncio.create_task(refresh("first", "rejected-first"))
    second = asyncio.create_task(refresh("second", "rejected-second"))
    await asyncio.wait_for(both_entered.wait(), timeout=1)
    release.set()

    assert await asyncio.gather(first, second) == ["new-first", "new-second"]


@pytest.mark.asyncio
async def test_newer_cached_token_is_not_overwritten_by_late_rejection() -> None:
    cache = {"connection": ("newer-token", time.monotonic() + 3600)}
    fetch_calls = 0

    async def fetch_new_token() -> tuple[str, float]:
        nonlocal fetch_calls
        fetch_calls += 1
        return "unexpected-token", time.monotonic() + 3600

    token = await refresh_rejected_cached_token(
        cache=cache,
        cache_key="connection",
        rejected_token="older-rejected-token",
        lock_pool=LoopLocalKeyedLockPool(),
        fetch_new_token=fetch_new_token,
    )

    assert token == "newer-token"
    assert fetch_calls == 0
