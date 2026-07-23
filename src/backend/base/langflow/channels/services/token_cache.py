"""Provider access-token cache key and response parsing helpers."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import httpx


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
