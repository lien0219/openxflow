import pytest

from langflow.api.v1.channel_runtime import (
    read_channel_prometheus_metrics,
    read_channel_runtime,
)


@pytest.mark.asyncio
async def test_channel_runtime_returns_webhook_and_retry_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES", "2048")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "12.5")
    result = await read_channel_runtime(object())

    assert result.webhook.max_concurrency > 0
    assert result.webhook.max_pending >= result.webhook.max_concurrency
    assert result.webhook.pending >= result.webhook.active
    assert result.webhook.queued == result.webhook.pending - result.webhook.active
    assert result.webhook.max_body_bytes == 2048
    assert result.webhook.task_timeout_seconds == 12.5
    assert result.outbound_retry.max_attempts == 5


@pytest.mark.asyncio
async def test_channel_prometheus_endpoint_uses_standard_content_type() -> None:
    response = await read_channel_prometheus_metrics(object())

    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert b"openxflow_channel_webhook_pending" in response.body
    assert b"openxflow_channel_outbound_attempts" in response.body
