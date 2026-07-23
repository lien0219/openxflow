"""Authenticated runtime diagnostics for the unified channel gateway."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from pydantic import BaseModel

from langflow.api.utils import CurrentActiveUser
from langflow.api.v1.channel_webhooks import webhook_max_body_bytes
from langflow.channels.services.metrics import ChannelMetricsCollector
from langflow.channels.services.retry import channel_retry_policy_from_env
from langflow.channels.services.webhook_processing import (
    webhook_limiter_snapshot,
    webhook_task_timeout_seconds,
)

router = APIRouter(prefix="/channel-runtime", tags=["Channels"])


class ChannelWebhookRuntimeRead(BaseModel):
    pending: int
    active: int
    queued: int
    pending_bytes: int
    max_pending: int
    max_pending_bytes: int
    max_concurrency: int
    max_body_bytes: int
    task_timeout_seconds: float
    accepted_total: int
    rejected_total: int
    succeeded_total: int
    failed_total: int


class ChannelOutboundRetryRuntimeRead(BaseModel):
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float


class ChannelRuntimeRead(BaseModel):
    webhook: ChannelWebhookRuntimeRead
    outbound_retry: ChannelOutboundRetryRuntimeRead


@router.get("/", response_model=ChannelRuntimeRead)
async def read_channel_runtime(current_user: CurrentActiveUser) -> ChannelRuntimeRead:
    del current_user
    webhook = webhook_limiter_snapshot()
    retry_policy = channel_retry_policy_from_env()
    return ChannelRuntimeRead(
        webhook=ChannelWebhookRuntimeRead(
            **asdict(webhook),
            max_body_bytes=webhook_max_body_bytes(),
            task_timeout_seconds=webhook_task_timeout_seconds(),
        ),
        outbound_retry=ChannelOutboundRetryRuntimeRead(
            max_attempts=retry_policy.max_attempts,
            base_delay_seconds=retry_policy.base_delay_seconds,
            max_delay_seconds=retry_policy.max_delay_seconds,
            jitter_ratio=retry_policy.jitter_ratio,
        ),
    )


@router.get("/metrics", response_class=Response)
async def read_channel_prometheus_metrics(current_user: CurrentActiveUser) -> Response:
    """Return authenticated Prometheus exposition for channel-specific metrics."""
    del current_user
    registry = CollectorRegistry(auto_describe=True)
    registry.register(ChannelMetricsCollector())
    return Response(
        content=generate_latest(registry),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
