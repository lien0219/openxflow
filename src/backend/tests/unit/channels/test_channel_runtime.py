import pytest

from langflow.api.v1.channel_runtime import (
    read_channel_prometheus_metrics,
    read_channel_runtime,
)


@pytest.mark.asyncio
async def test_channel_runtime_returns_stream_webhook_and_retry_configuration(monkeypatch) -> None:
    monkeypatch.setenv("LANGFLOW_CHANNEL_STREAMS_ENABLED", "false")
    monkeypatch.setenv("LANGFLOW_CHANNEL_HTTP_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_MAX_BODY_BYTES", "2048")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_QUEUE_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("LANGFLOW_CHANNEL_WEBHOOK_TASK_TIMEOUT_SECONDS", "12.5")
    result = await read_channel_runtime(object())

    assert result.streams_enabled is False
    assert result.stream_runtime.running_managers >= 0
    assert result.stream_runtime.leader_managers >= 0
    assert result.stream_runtime.managed_clients >= 0
    assert result.stream_runtime.leader_managers <= result.stream_runtime.running_managers
    assert result.stream_runtime.connection_errors_total >= 0
    assert result.stream_runtime.reconnect_attempts_total >= 0
    assert result.stream_runtime.successful_sync_total >= 0
    assert result.stream_runtime.last_successful_sync_timestamp_seconds >= 0
    assert result.webhook.max_concurrency > 0
    assert result.webhook.max_pending >= result.webhook.max_concurrency
    assert result.webhook.pending >= result.webhook.active
    assert result.webhook.queued == result.webhook.pending - result.webhook.active
    assert result.webhook.pending_bytes >= 0
    assert result.webhook.max_pending_bytes > 0
    assert result.webhook.pending_bytes <= result.webhook.max_pending_bytes
    assert result.webhook.max_body_bytes == 2048
    assert result.webhook.queue_timeout_seconds == 3.5
    assert result.webhook.task_timeout_seconds == 12.5
    assert (
        result.webhook.rejected_pending_total
        + result.webhook.rejected_bytes_total
        + result.webhook.rejected_both_total
        == result.webhook.rejected_total
    )
    assert result.webhook.queue_timed_out_total >= 0
    assert result.webhook.cancelled_total >= 0
    assert result.webhook.client_disconnected_total >= 0
    assert result.outbound_retry.max_attempts == 5


@pytest.mark.asyncio
async def test_channel_prometheus_endpoint_uses_standard_content_type() -> None:
    response = await read_channel_prometheus_metrics(object())

    assert response.headers["content-type"] == "text/plain; version=0.0.4; charset=utf-8"
    assert b"openxflow_channel_stream_running_managers" in response.body
    assert b"openxflow_channel_stream_leader_managers" in response.body
    assert b"openxflow_channel_stream_managed_clients" in response.body
    assert b"openxflow_channel_stream_connection_errors" in response.body
    assert b"openxflow_channel_stream_reconnect_attempts" in response.body
    assert b"openxflow_channel_stream_successful_syncs" in response.body
    assert b"openxflow_channel_stream_last_successful_sync_timestamp_seconds" in response.body
    assert b"openxflow_channel_webhook_pending" in response.body
    assert b"openxflow_channel_webhook_pending_bytes" in response.body
    assert b"openxflow_channel_webhook_max_pending_bytes" in response.body
    assert b"openxflow_channel_webhook_rejected_pending" in response.body
    assert b"openxflow_channel_webhook_rejected_bytes" in response.body
    assert b"openxflow_channel_webhook_rejected_both" in response.body
    assert b"openxflow_channel_webhook_queue_timed_out" in response.body
    assert b"openxflow_channel_webhook_cancelled" in response.body
    assert b"openxflow_channel_webhook_client_disconnected" in response.body
    assert b"openxflow_channel_outbound_attempts" in response.body
    assert b"openxflow_channel_token_rejections" in response.body
    assert b"openxflow_channel_token_refresh_succeeded" in response.body
    assert b"openxflow_channel_token_refresh_failed" in response.body
    assert b"openxflow_channel_token_replays" in response.body
