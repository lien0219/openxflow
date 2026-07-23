import pytest

from langflow.channels.services.retry import (
    ChannelRetryPolicy,
    channel_error_reason,
    is_retryable_channel_error,
    retry_channel_operation,
)


class TelegramAPIError(RuntimeError):
    pass


class FeishuAPIError(RuntimeError):
    pass


@pytest.mark.asyncio
async def test_provider_rate_limit_error_uses_retry_after_from_message() -> None:
    attempts = 0
    delays: list[float] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TelegramAPIError("Too Many Requests: retry after 2")
        return "ok"

    async def sleep(delay: float) -> None:
        delays.append(delay)

    result = await retry_channel_operation(
        operation,
        operation_name="telegram.send_message",
        policy=ChannelRetryPolicy(
            max_attempts=2,
            base_delay_seconds=0.5,
            max_delay_seconds=8,
            jitter_ratio=0,
        ),
        sleep=sleep,
    )

    assert result == "ok"
    assert attempts == 2
    assert delays == [2.0]


def test_provider_busy_error_is_retryable() -> None:
    error = FeishuAPIError("system busy, try again later")

    assert is_retryable_channel_error(error) is True
    assert channel_error_reason(error) == "provider_busy"


def test_provider_validation_error_is_not_retryable() -> None:
    error = FeishuAPIError("invalid receive_id")

    assert is_retryable_channel_error(error) is False
    assert channel_error_reason(error) == "feishuapierror"
