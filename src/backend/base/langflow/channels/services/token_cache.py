"""Provider access-token cache key, parsing, and synchronization helpers."""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache_metrics import (
    record_token_cache_coalesced_refresh,
    record_token_cache_forced_refresh,
    record_token_cache_hit,
    record_token_cache_miss,
    record_token_cache_refresh_failure,
    record_token_cache_refresh_success,
)

TokenCache = dict[str, tuple[str, float]]


class InvalidProviderTokenResponseError(RuntimeError):
    """Raised when a provider token endpoint returns an invalid response shape."""


def provider_token_cache_key(
    *,
    provider: str,
    api_base_url: str,
    public_id: str,
    secret: str,
) -> str:
    """Build a stable cache key without retaining the raw credential secret."""
    normalized_provider = provider.strip().lower()
    normalized_base_url = api_base_url.rstrip("/")
    normalized_public_id = public_id.strip()
    secret_digest = hashlib.sha256(secret.encode()).hexdigest()
    return ":".join(
        (
            normalized_provider,
            normalized_base_url,
            normalized_public_id,
            secret_digest,
        )
    )


async def get_cached_provider_token(
    *,
    provider: str,
    cache: TokenCache,
    cache_key: str,
    force_refresh: bool,
    lock_pool: LoopLocalKeyedLockPool,
    fetch_new_token: Callable[[], Awaitable[tuple[str, float]]],
) -> str:
    """Return one cached token while serializing refreshes only for the same credential key."""
    now = time.monotonic()
    observed = cache.get(cache_key)
    if not force_refresh and observed is not None and observed[1] > now:
        record_token_cache_hit(provider)
        return observed[0]

    if force_refresh:
        record_token_cache_forced_refresh(provider)
    else:
        record_token_cache_miss(provider)

    async with lock_pool.hold(cache_key):
        now = time.monotonic()
        cached = cache.get(cache_key)
        if cached is not None and cached[1] > now:
            if not force_refresh or cached is not observed:
                record_token_cache_coalesced_refresh(provider)
                return cached[0]
        try:
            token, expires_at = await fetch_new_token()
        except Exception:
            record_token_cache_refresh_failure(provider)
            raise
        cache[cache_key] = (token, expires_at)
        record_token_cache_refresh_success(provider)
        return token


def response_json_object(response: httpx.Response) -> dict[str, Any] | None:
    """Return a JSON object response body without raising for malformed bodies."""
    if not response.content:
        return None
    try:
        body = response.json()
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


def provider_token_lifetime_seconds(
    body: dict[str, Any],
    field: str,
    *,
    provider: str,
    default: int = 7200,
    minimum: int = 60,
) -> int:
    """Parse a positive finite token lifetime with a provider-safe error type."""
    raw_value = body.get(field, default)
    if isinstance(raw_value, bool):
        raise InvalidProviderTokenResponseError(
            f"Invalid {provider} access-token lifetime field '{field}'"
        )
    try:
        parsed = float(raw_value)
    except (TypeError, ValueError) as exc:
        raise InvalidProviderTokenResponseError(
            f"Invalid {provider} access-token lifetime field '{field}'"
        ) from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise InvalidProviderTokenResponseError(
            f"Invalid {provider} access-token lifetime field '{field}'"
        )
    return max(minimum, int(parsed))
