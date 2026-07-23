"""Environment-backed runtime configuration for channel services."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

DEFAULT_CHANNEL_STREAMS_ENABLED = True
DEFAULT_WEBHOOK_MAX_CONCURRENCY = 16
DEFAULT_WEBHOOK_MAX_PENDING = 128
DEFAULT_WEBHOOK_MAX_PENDING_BYTES = 64 * 1024 * 1024
DEFAULT_WEBHOOK_MAX_BODY_BYTES = 1024 * 1024
DEFAULT_WEBHOOK_QUEUE_TIMEOUT_SECONDS = 0.0
DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS = 300.0
DEFAULT_WEBHOOK_DURABLE_ENABLED = True
DEFAULT_WEBHOOK_JOB_WORKERS = 4
DEFAULT_WEBHOOK_JOB_POLL_SECONDS = 0.5
DEFAULT_WEBHOOK_JOB_LEASE_SECONDS = 600.0
DEFAULT_WEBHOOK_JOB_MAX_ATTEMPTS = 5
DEFAULT_WEBHOOK_JOB_RETRY_BASE_SECONDS = 2.0
DEFAULT_WEBHOOK_JOB_RETRY_MAX_SECONDS = 300.0
DEFAULT_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS = 60.0
DEFAULT_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS = 7
DEFAULT_WEBHOOK_JOB_FAILED_RETENTION_DAYS = 30
DEFAULT_WEBHOOK_JOB_CLEANUP_BATCH_SIZE = 500
WEBHOOK_JOB_LEASE_SAFETY_SECONDS = 30.0

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}


def _boolean_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False
    return default


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


def _non_negative_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if math.isfinite(parsed) and parsed >= 0 else default


@dataclass(frozen=True)
class WebhookLimiterLimits:
    max_concurrency: int
    max_pending: int
    max_pending_bytes: int


@dataclass(frozen=True)
class DurableWebhookJobConfig:
    enabled: bool
    worker_count: int
    poll_seconds: float
    lease_seconds: float
    max_attempts: int
    retry_base_seconds: float
    retry_max_seconds: float
    cleanup_interval_seconds: float
    completed_retention_days: int
    failed_retention_days: int
    cleanup_batch_size: int


def channel_streams_enabled() -> bool:
    """Whether lifecycle-managed channel Stream clients should run in this process."""
    return _boolean_env("LANGFLOW_CHANNEL_STREAMS_ENABLED", DEFAULT_CHANNEL_STREAMS_ENABLED)


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


def webhook_queue_timeout_seconds() -> float:
    """Maximum queue wait before execution; zero disables queue timeout."""
    return _non_negative_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS",
        DEFAULT_WEBHOOK_QUEUE_TIMEOUT_SECONDS,
    )


def webhook_task_timeout_seconds() -> float:
    """Maximum execution time after a callback obtains a concurrency slot."""
    return _positive_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS",
        DEFAULT_WEBHOOK_TASK_TIMEOUT_SECONDS,
    )


def durable_webhook_job_config() -> DurableWebhookJobConfig:
    """Return normalized settings for database-backed provider webhook processing."""
    retry_base = _positive_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_BASE_SECONDS",
        DEFAULT_WEBHOOK_JOB_RETRY_BASE_SECONDS,
    )
    retry_max = _positive_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_RETRY_MAX_SECONDS",
        DEFAULT_WEBHOOK_JOB_RETRY_MAX_SECONDS,
    )
    configured_lease = _positive_float_env(
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_LEASE_SECONDS",
        DEFAULT_WEBHOOK_JOB_LEASE_SECONDS,
    )
    max_concurrency = webhook_limiter_limits_from_env().max_concurrency
    configured_workers = _positive_int_env(
        "LANGFLOW_CHANNEL_WEBHOOK_JOB_WORKERS",
        DEFAULT_WEBHOOK_JOB_WORKERS,
    )
    minimum_lease = webhook_task_timeout_seconds() + WEBHOOK_JOB_LEASE_SAFETY_SECONDS
    return DurableWebhookJobConfig(
        enabled=_boolean_env(
            "LANGFLOW_CHANNEL_WEBHOOK_DURABLE_ENABLED",
            DEFAULT_WEBHOOK_DURABLE_ENABLED,
        ),
        worker_count=min(configured_workers, max_concurrency),
        poll_seconds=_positive_float_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_POLL_SECONDS",
            DEFAULT_WEBHOOK_JOB_POLL_SECONDS,
        ),
        lease_seconds=max(configured_lease, minimum_lease),
        max_attempts=_positive_int_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_MAX_ATTEMPTS",
            DEFAULT_WEBHOOK_JOB_MAX_ATTEMPTS,
        ),
        retry_base_seconds=retry_base,
        retry_max_seconds=max(retry_base, retry_max),
        cleanup_interval_seconds=_positive_float_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS",
            DEFAULT_WEBHOOK_JOB_CLEANUP_INTERVAL_SECONDS,
        ),
        completed_retention_days=_positive_int_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS",
            DEFAULT_WEBHOOK_JOB_COMPLETED_RETENTION_DAYS,
        ),
        failed_retention_days=_positive_int_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_FAILED_RETENTION_DAYS",
            DEFAULT_WEBHOOK_JOB_FAILED_RETENTION_DAYS,
        ),
        cleanup_batch_size=_positive_int_env(
            "LANGFLOW_CHANNEL_WEBHOOK_JOB_CLEANUP_BATCH_SIZE",
            DEFAULT_WEBHOOK_JOB_CLEANUP_BATCH_SIZE,
        ),
    )
