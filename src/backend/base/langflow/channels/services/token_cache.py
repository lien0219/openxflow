"""Provider access-token cache key, parsing, and synchronization helpers."""

from __future__ import annotations

import hashlib
import math
import os
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache_metrics import (
    record_token_cache_coalesced_refresh,
    record_token_cache_entries,
    record_token_cache_eviction,
    record_token_cache_forced_refresh,
    record_token_cache_hit,
    record_token_cache_miss,
    record_token_cache_refresh_failure,
    record_token_cache_refresh_success,
)

TokenCache = dict[str, tuple[str, float]]
DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES = 512
TOKEN_CACHE_MAX_ENTRIES_ENV = "LANGFLOW_CHANNEL_TOKEN_CACHE_MAX_ENTRIES"


class InvalidProviderTokenResponseError(RuntimeError):
    """Raised when a provider token endpoint returns an invalid response shape."""


def provider_token_cache_max_entries() -> int:
    """Return the normalized per-provider process cache capacity."""
    raw_value = os.getenv(TOKEN_CACHE_MAX_ENTRIES_ENV)
    if raw_value is None:
        return DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES
    try:
        parsed = int(raw_value)
    except ValueError:
        return DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES
    return parsed if parsed > 0 else DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES


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


def prune_provider_token_cache(
    *,
    provider: str,
    cache: TokenCache,
    protected_key: str,
    now: float | None = None,
    max_entries: int = DEFAULT_PROVIDER_TOKEN_CACHE_MAX_ENTRIES,
) -> tuple[int, int]:
    """Remove expired entries, then earliest-expiring entries above the capacity limit."""
    if max_entries <= 0:
        raise ValueError("max_entries must be positive")
    current_time = time.monotonic() if now is None else now

    expired_evictions = 0
    expired_keys = [
        key
        for key, (_token, expires_at) in cache.items()
        if key != protected_key and expires_at <= current_time
    ]
    for key in expired_keys:
        if cache.pop(key, None) is not None:
            expired_evictions += 1

    capacity_evictions = 0
    if len(cache) > max_entries:
        candidates = sorted(
            (
                (expires_at, key)
                for key, (_token, expires_at) in cache.items()
                if key != protected_key
            ),
        )
        for _expires_at, key in candidates:
            if len(cache) <= max_entries:
                break
            if cache.pop(key, None) is not None:
                capacity_evictions += 1

    if expired_evictions:
        record_token_cache_eviction(provider, "expired", expired_evictions)
    if capacity_evictions:
        record_token_cache_eviction(provider, "capacity", capacity_evictions)
    record_token_cache_entries(provider, len(cache))
    return expired_evictions, capacity_evictions


async def get_cached_provider_token(
    *,
    provider: str,
    cache: TokenCache,
    cache_key: str,
    force_refresh: bool,
    lock_pool: LoopLocalKeyedLockPool,
    fetch_new_token: Callable[[], Awaitable[tuple[str, float]]],
    max_entries: int | None = None,
) -> str:
    """Return one cached token while serializing refreshes only for the same credential key."""
    normalized_max_entries = provider_token_cache_max_entries() if max_entries is None else max_entries
    if normalized_max_entries <= 0:
        raise ValueError("max_entries must be positive")
    now = time.monotonic()
    observed = cache.get(cache_key)
    if not force_refresh and observed is not None and observed[1] > now:
        record_token_cache_hit(provider)
        record_token_cache_entries(provider, len(cache))
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
                record_token_cache_entries(provider, len(cache))
                return cached[0]
        try:
            token, expires_at = await fetch_new_token()
            refreshed_at = time.monotonic()
            if not math.isfinite(expires_at) or expires_at <= refreshed_at:
                raise InvalidProviderTokenResponseError(
                    f"Invalid {provider} access-token absolute expiry"
                )
        except Exception:
            record_token_cache_refresh_failure(provider)
            raise
        cache[cache_key] = (token, expires_at)
        prune_provider_token_cache(
            provider=provider,
            cache=cache,
            protected_key=cache_key,
            now=refreshed_at,
            max_entries=normalized_max_entries,
        )
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
