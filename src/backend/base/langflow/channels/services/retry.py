"""Retry policy for outbound channel provider operations."""

from __future__ import annotations

import asyncio
import os
import random
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from lfx.log.logger import logger

from langflow.channels.services.metrics import (
    record_outbound_attempt,
    record_outbound_failure,
    record_outbound_retry,
    record_outbound_success,
)

_T = TypeVar("_T")
_RETRYABLE_STATUS_CODES = frozenset({408, 425, 429, *range(500, 600)})
_PROVIDER_RATE_LIMIT_HINTS = (
    "too many requests",
    "rate limit",
    "frequency limit",
    "retry after",
    "限流",
    "频率限制",
    "请求过于频繁",
)
_PROVIDER_BUSY_HINTS = (
    "system busy",
    "service unavailable",
    "temporarily unavailable",
    "temporary failure",
    "try again later",
    "系统繁忙",
    "服务不可用",
    "稍后重试",
)
_PROVIDER_TIMEOUT_HINTS = ("timeout", "timed out", "超时")
_RETRY_AFTER_PATTERN = re.compile(
    r"(?:retry[\s_-]*after|after)\D{0,16}(\d+(?:\.\d+)?)",
    re.IGNORECASE,
)


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


def _non_negative_float_env(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError:
        return default
    return parsed if parsed >= 0 else default


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
            _non_negative_float_env("LANGFLOW_CHANNEL_HTTP_JITTER_RATIO", 0.2),
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
        record_outbound_attempt(operation_name)
        try:
            result = await operation()
        except Exception as exc:
            reason = channel_error_reason(exc)
            if attempt >= effective_policy.max_attempts or not is_retryable_channel_error(exc):
                record_outbound_failure(operation_name, reason)
                raise
            record_outbound_retry(operation_name, reason)
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
        else:
            record_outbound_success(operation_name)
            return result


def is_retryable_channel_error(exc: Exception) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRYABLE_STATUS_CODES
    if isinstance(exc, httpx.RequestError):
        return True
    return _is_retryable_provider_api_error(exc)


def channel_error_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http_{exc.response.status_code}"
    if isinstance(exc, httpx.RequestError):
        return type(exc).__name__.lower()
    if _is_provider_api_error(exc):
        normalized = str(exc).casefold()
        if _contains_any(normalized, _PROVIDER_RATE_LIMIT_HINTS):
            return "provider_rate_limit"
        if _contains_any(normalized, _PROVIDER_BUSY_HINTS):
            return "provider_busy"
        if _contains_any(normalized, _PROVIDER_TIMEOUT_HINTS):
            return "provider_timeout"
    return type(exc).__name__.lower()


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


def _is_provider_api_error(exc: Exception) -> bool:
    return type(exc).__name__.endswith("APIError")


def _is_retryable_provider_api_error(exc: Exception) -> bool:
    if not _is_provider_api_error(exc):
        return False
    normalized = str(exc).casefold()
    return _contains_any(
        normalized,
        (*_PROVIDER_RATE_LIMIT_HINTS, *_PROVIDER_BUSY_HINTS, *_PROVIDER_TIMEOUT_HINTS),
    )


def _contains_any(value: str, hints: tuple[str, ...]) -> bool:
    return any(hint in value for hint in hints)


def _retry_after_seconds(exc: Exception) -> float | None:
    attribute_value = getattr(exc, "retry_after", None)
    if isinstance(attribute_value, (int, float)):
        return float(attribute_value)

    if isinstance(exc, httpx.HTTPStatusError):
        raw_value = exc.response.headers.get("Retry-After")
        if raw_value:
            parsed_header = _parse_retry_after_header(raw_value)
            if parsed_header is not None:
                return parsed_header

    if _is_provider_api_error(exc):
        match = _RETRY_AFTER_PATTERN.search(str(exc))
        if match is not None:
            return float(match.group(1))
    return None


def _parse_retry_after_header(raw_value: str) -> float | None:
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
