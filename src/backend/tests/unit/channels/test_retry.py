import math

import httpx
import pytest
from langflow.channels.services.metrics import outbound_metrics_snapshot, reset_outbound_metrics_for_testing
from langflow.channels.services.retry import (
    ChannelRetryPolicy,
    channel_retry_policy_from_env,
    is_retryable_channel_error,
    retry_channel_operation,
    retry_delay_seconds,
)


def setup_function() -> None:
    reset_outbound_metrics_for_testing()


def teardown_function() -> None:
    reset_outbound_metrics_for_testing()


def _status_error(status_code: int, *, retry_after: str | None = None) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://provider.example/messages")
    headers = {"Retry-After": retry_after} if retry_after is not None else None
    response = httpx.Response(status_code, request=request, headers=headers)
    return httpx.HTTPStatusError("provider failed", request=request, response=response)


@pytest.mark.asyncio
async def test_retry_channel_operation_recovers_from_transient_network_errors() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectError("connection failed", request=httpx.Request("GET", "https://provider.example"))
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = await retry_channel_operation(
        operation,
        operation_name="telegram.send_message",
        policy=ChannelRetryPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=4, jitter_ratio=0),
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [0.5, 1.0]
    metrics = outbound_metrics_snapshot()
    assert metrics.attempts[("telegram", "send_message")] == 3
    assert metrics.retries[("telegram", "send_message", "connecterror")] == 2
    assert metrics.succeeded[("telegram", "send_message")] == 1


@pytest.mark.asyncio
async def test_retry_channel_operation_honors_retry_after_header() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise _status_error(429, retry_after="3")
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = await retry_channel_operation(
        operation,
        operation_name="telegram.send_message",
        policy=ChannelRetryPolicy(max_attempts=2, base_delay_seconds=0.5, max_delay_seconds=8, jitter_ratio=0),
        sleep=sleep,
    )

    assert result == "ok"
    assert delays == [3.0]


@pytest.mark.asyncio
async def test_retry_channel_operation_does_not_retry_client_validation_errors() -> None:
    attempts = 0

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise _status_error(400)

    with pytest.raises(httpx.HTTPStatusError):
        await retry_channel_operation(
            operation,
            operation_name="feishu.send_response",
            policy=ChannelRetryPolicy(max_attempts=3, jitter_ratio=0),
        )

    assert attempts == 1
    metrics = outbound_metrics_snapshot()
    assert metrics.failed[("feishu", "send_response", "http_400")] == 1


def test_retryable_channel_error_statuses() -> None:
    assert is_retryable_channel_error(_status_error(408)) is True
    assert is_retryable_channel_error(_status_error(425)) is True
    assert is_retryable_channel_error(_status_error(429)) is True
    assert is_retryable_channel_error(_status_error(503)) is True
    assert is_retryable_channel_error(_status_error(401)) is False


def test_retry_policy_allows_disabling_jitter(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_JITTER_RATIO", "0")
    assert channel_retry_policy_from_env().jitter_ratio == 0


def test_retry_policy_rejects_non_finite_constructor_values() -> None:
    with pytest.raises(ValueError, match="base_delay_seconds"):
        ChannelRetryPolicy(base_delay_seconds=math.inf)
    with pytest.raises(ValueError, match="max_delay_seconds"):
        ChannelRetryPolicy(max_delay_seconds=math.nan)
    with pytest.raises(ValueError, match="jitter_ratio"):
        ChannelRetryPolicy(jitter_ratio=math.inf)


def test_retry_policy_falls_back_for_non_finite_environment_values(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_BASE_DELAY_SECONDS", "nan")
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_MAX_DELAY_SECONDS", "inf")
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_JITTER_RATIO", "nan")

    policy = channel_retry_policy_from_env()

    assert policy.base_delay_seconds == 0.5
    assert policy.max_delay_seconds == 8.0
    assert policy.jitter_ratio == 0.2


def test_retry_delay_clamps_out_of_range_random_values() -> None:
    policy = ChannelRetryPolicy(
        max_attempts=2,
        base_delay_seconds=1,
        max_delay_seconds=10,
        jitter_ratio=0.5,
    )
    error = httpx.ConnectError("connection failed", request=httpx.Request("GET", "https://provider.example"))

    assert retry_delay_seconds(error, attempt=1, policy=policy, random_value=lambda: -5) == 0.5
    assert retry_delay_seconds(error, attempt=1, policy=policy, random_value=lambda: 5) == 1.5
    assert retry_delay_seconds(error, attempt=1, policy=policy, random_value=lambda: math.nan) == 1.0


def test_non_finite_retry_after_header_falls_back_to_backoff() -> None:
    policy = ChannelRetryPolicy(
        max_attempts=2,
        base_delay_seconds=1,
        max_delay_seconds=10,
        jitter_ratio=0,
    )

    assert (
        retry_delay_seconds(
            _status_error(429, retry_after="nan"),
            attempt=1,
            policy=policy,
        )
        == 1.0
    )
