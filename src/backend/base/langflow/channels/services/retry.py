"""Retry policy for outbound channel provider operations."""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from lfx.log.logger import logger

_T = TypeVar("_T")
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, *range(500, 600)})


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
    return parsed if parsed > 0 else default


@dataclass(frozen=True)
class ChannelRetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter_ratio: float = 0.2

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_delay_seconds <= 0:
            raise ValueError("base_delay_seconds must be positive")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be greater than or equal to base_delay_seconds")
        if not 0 <= self.jitter_ratio <= 1:
            raise ValueError("jitter_ratio must be between 0 and 1")


def channel_retry_policy_from_env() -> ChannelRetryPolicy:
    return ChannelRetryPolicy(
        max_attempts=_positive_int_env("LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS", 3),
        base_delay_seconds=_positive_float_env("LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS", 0.5),
        max_delay_seconds=_positive_float_env("LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS", 8.0),
        jitter_ratio=min(
            1.0,
            max(0.0, _positive_float_env("LANGFLOW_CHANNEL_HTTP_JITTER_RATIO", 0.2)),
        ),
    )


async def retry_channel_operation(
    operation: Callable[[], Awaitable[_T]],
    *,
    operation_name: str,
    policy: ChannelRetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    random_value: Callable[[], float] = random.random,
) -> _T:
    """Retry transient provider failures without retrying validation or auth errors."""
    effective_policy = policy or channel_retry_policy_from_env()
    attempt = 1
    while True:
        try:
            return await operation()
        except Exception as exc:
            if attempt >= effective_policy.max_attempts or not is_retryable_channel_error(exc):
                raise
            delay = retry_delay_seconds(
                exc,
                attempt=attempt,
                policy=effective_policy,
                random_value=random_value,
            )
            await logger.awarning(
                "Retrying channel operation %s after attempt %s/%s in %.3fs: %s",
                operation_name,
                attempt,
                effective_policy.max_attempts,
                delay,
                type(exc).__name__,
            )
            await sleep(delay)
            attempt += 1


def is_retryable_channel_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    return isinstance(exc, httpx.RequestError)


def retry_delay_seconds(
    exc: Exception,
    *,
    attempt: int,
    policy: ChannelRetryPolicy,
    random_value: Callable[[], float] = random.random,
) -> float:
    retry_after = _retry_after_seconds(exc)
    if retry_after is not None:
        return min(policy.max_delay_seconds, max(0.0, retry_after))

    base_delay = min(
        policy.max_delay_seconds,
        policy.base_delay_seconds * (2 ** max(0, attempt - 1)),
    )
    jitter_multiplier = 1 + policy.jitter_ratio * (2 * random_value() - 1)
    return min(policy.max_delay_seconds, max(0.0, base_delay * jitter_multiplier))


def _retry_after_seconds(exc: Exception) -> float | None:
    if not isinstance(exc, httpx.HTTPStatusError):
        return None
    raw_value = exc.response.headers.get("Retry-After")
    if not raw_value:
        return None
    try:
        return float(raw_value)
    except ValueError:
        pass
    try:
        retry_at = parsedate_to_datetime(raw_value)
    except (TypeError, ValueError, OverflowError):
        return None
    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=timezone.utc)
    return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
