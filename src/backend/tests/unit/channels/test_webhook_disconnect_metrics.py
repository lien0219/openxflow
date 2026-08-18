import pytest
from fastapi import HTTPException
from langflow.api.v1 import channel_webhooks
from langflow.channels.services import webhook_processing
from langflow.channels.services.webhook_processing import WebhookProcessingLimiter
from starlette.requests import ClientDisconnect


class _DisconnectingRequest:
    headers = {"content-type": "application/json"}

    async def stream(self):
        yield b"partial"
        raise ClientDisconnect


@pytest.mark.asyncio
async def test_disconnected_upload_increments_counter_without_reserving_capacity(monkeypatch) -> None:
    limiter = WebhookProcessingLimiter(max_concurrency=1, max_pending=1, max_pending_bytes=1024)
    monkeypatch.setattr(webhook_processing, "_webhook_limiter", limiter)
    monkeypatch.setattr(channel_webhooks, "webhook_max_body_bytes", lambda: 1024)

    with pytest.raises(HTTPException) as exc_info:
        await channel_webhooks._read_limited_body(_DisconnectingRequest())  # type: ignore[arg-type]

    snapshot = limiter.snapshot()
    assert exc_info.value.status_code == 400
    assert snapshot.client_disconnected_total == 1
    assert snapshot.pending == 0
    assert snapshot.pending_bytes == 0
    assert snapshot.accepted_total == 0
    assert snapshot.rejected_total == 0
