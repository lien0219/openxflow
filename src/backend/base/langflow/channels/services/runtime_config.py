"""Environment-backed runtime configuration for channel webhooks."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

DEFAULT_WEBHOOK_MAX_CONCURRENCY = 16
DEFAULT_WEBHOOK_MAX_PENDING = 128
DEFAULT_WEBHOOK_MAX_PENDING_BYTES = 64 * 1024 * 1024
DEFAULT_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS = 300.0


def _positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _positive_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed > 0 else default


@dataclass(frozen=True)
class WebhookLimiterLimits:
    max_concurrency: int
    max_pending: int
    max_pending_bytes: int


def webhook_limiter_limits_from_env() -> WebhookLimiterLimits:
    """Return normalized process-local queue and execution limits."""
    max_concurrency = _positive_int_env(
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_CONCURRENCY",
        DEFAULT_WEBHOOK_MAX_CONCURRENCY,
    )
    configured_max_pending = _positive_int_env(
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING",
        DEFAULT_WEBHOOK_MAX_PENDING,
    )
    return WebhookLimiterLimits(
        max_concurrency=max_concurrency,
        max_pending=max(max_concurrency, configured_max_pending),
        max_pending_bytes=_positive_int_env(
            "LANGFLOW_CHANNEL_WEBHOOK_MAX_PENDING_BYTES",
            DEFAULT_WEBHOOK_MAX_PENDING_BYTES,
        ),
    )


def webhook_max_body_bytes() -> int:
    """Maximum accepted provider callback body size."""
    return _positive_int_env(
        "LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES",
        DEFAULT_WEBHOOK_MAX_BODY_BYTES,
    )


def webhook_task_timeout_seconds() -> float:
    """Maximum execution time after a callback obtains a concurrency slot."""
    return _positive_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS",
        DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS,
    )
