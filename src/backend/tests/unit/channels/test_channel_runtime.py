import pytest

from langflow.api.v1.channel_runtime import read_channel_runtime


@pytest.mark.asyncio
async def test_channel_runtime_returns_webhook_and_retry_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS", "5")
    result = await read_channel_runtime(object())

    assert result.webhook.max_concurrency > 0
    assert result.webhook.max_pending >= result.webhook.max_concurrency
    assert result.webhook.pending >= result.webhook.active
    assert result.webhook.queued == result.webhook.pending - result.webhook.active
    assert result.outbound_retry.max_attempts == 5
