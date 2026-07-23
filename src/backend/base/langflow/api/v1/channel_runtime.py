"""Authenticated runtime diagnostics for the unified channel gateway."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from pydantic import BaseModel

from langflow.api.utils import CurrentActiveUser
from langflow.channels.services.dingtalk_stream import dingtalk_stream_runtime_snapshot
from langflow.channels.services.metrics import ChannelMetricsCollector
from langflow.channels.services.retry import channel_retry_policy_from_env
from langflow.channels.services.runtime_config import (
    channel_streams_enabled,
    durable_webhook_job_config,
    webhook_max_body_bytes,
    webhook_queue_timeout_seconds,
    webhook_task_timeout_seconds,
)
from langflow.channels.services.timing_metrics import ChannelTimingMetricsCollector
from langflow.channels.services.webhook_job_metrics import (
    DurableWebhookJobMetricsCollector,
    durable_webhook_job_metrics_snapshot,
)
from langflow.channels.services.webhook_processing import webhook_limiter_snapshot

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
    queue_timeout_seconds: float
    task_timeout_seconds: float
    accepted_total: int
    rejected_total: int
    rejected_pending_total: int
    rejected_bytes_total: int
    rejected_both_total: int
    succeeded_total: int
    failed_total: int
    queue_timed_out_total: int
    cancelled_total: int
    client_disconnected_total: int


class ChannelStreamRuntimeRead(BaseModel):
    running_managers: int
    leader_managers: int
    managed_clients: int
    sync_errors_total: int
    connection_errors_total: int
    reconnect_attempts_total: int
    successful_sync_total: int
    last_successful_sync_timestamp_seconds: float


class DurableWebhookJobRuntimeRead(BaseModel):
    enabled: bool
    worker_count: int
    poll_seconds: float
    lease_seconds: float
    max_attempts: int
    retry_base_seconds: float
    retry_max_seconds: float
    running_managers: int
    consumer_tasks: int
    claimed_total: int
    completed_total: int
    retried_total: int
    failed_total: int
    claim_errors_total: int


class ChannelOutboundRetryRuntimeRead(BaseModel):
    max_attempts: int
    base_delay_seconds: float
    max_delay_seconds: float
    jitter_ratio: float


class ChannelRuntimeRead(BaseModel):
    streams_enabled: bool
    stream_runtime: ChannelStreamRuntimeRead
    webhook: ChannelWebhookRuntimeRead
    durable_webhook_jobs: DurableWebhookJobRuntimeRead
    outbound_retry: ChannelOutboundRetryRuntimeRead


@router.get("/", response_model=ChannelRuntimeRead)
async def read_channel_runtime(current_user: CurrentActiveUser) -> ChannelRuntimeRead:
    del current_user
    stream_runtime = dingtalk_stream_runtime_snapshot()
    webhook = webhook_limiter_snapshot()
    durable_config = durable_webhook_job_config()
    durable_runtime = durable_webhook_job_metrics_snapshot()
    retry_policy = channel_retry_policy_from_env()
    return ChannelRuntimeRead(
        streams_enabled=channel_streams_enabled(),
        stream_runtime=ChannelStreamRuntimeRead(**asdict(stream_runtime)),
        webhook=ChannelWebhookRuntimeRead(
            **asdict(webhook),
            max_body_bytes=webhook_max_body_bytes(),
            queue_timeout_seconds=webhook_queue_timeout_seconds(),
            task_timeout_seconds=webhook_task_timeout_seconds(),
        ),
        durable_webhook_jobs=DurableWebhookJobRuntimeRead(
            **asdict(durable_config),
            **asdict(durable_runtime),
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
    registry.register(ChannelTimingMetricsCollector())
    registry.register(DurableWebhookJobMetricsCollector())
    return Response(
        content=generate_latest(registry),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
