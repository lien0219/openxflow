import httpx
import pytest

from langflow.channels.services.retry import (
    ChannelRetryPolicy,
    is_retryable_channel_error,
    retry_channel_operation,
)


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
        operation_name="test.send",
        policy=ChannelRetryPolicy(max_attempts=3, base_delay_seconds=0.5, max_delay_seconds=4, jitter_ratio=0),
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 3
    assert delays == [0.5, 1.0]


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
        operation_name="test.rate_limit",
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
            operation_name="test.validation",
            policy=ChannelRetryPolicy(max_attempts=3, jitter_ratio=0),
        )

    assert attempts == 1


def test_retryable_channel_error_statuses() -> None:
    assert is_retryable_channel_error(_status_error(408)) is True
    assert is_retryable_channel_error(_status_error(425)) is True
    assert is_retryable_channel_error(_status_error(429)) is True
    assert is_retryable_channel_error(_status_error(503)) is True
    assert is_retryable_channel_error(_status_error(401)) is False
