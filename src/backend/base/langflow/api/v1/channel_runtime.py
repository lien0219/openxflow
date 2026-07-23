"""Authenticated runtime diagnostics for the unified channel gateway."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from langflow.api.utils import CurrentActiveUser
from langflow.channels.services.retry import channel_retry_policy_from_env
from langflow.channels.services.webhook_processing import webhook_limiter_snapshot

router = APIRouter(prefix="/channel-runtime", tags=["Channels"])


class ChannelWebhookRuntimeRead(BaseModel):
    pending: int
    active: int
    queued: int
    max_pending: int
    max_concurrency: int
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
        webhook=ChannelWebhookRuntimeRead(**webhook.__dict__),
        outbound_retry=ChannelOutboundRetryRuntimeRead(
            max_attempts=retry_policy.max_attempts,
            base_delay_seconds=retry_policy.base_delay_seconds,
            max_delay_seconds=retry_policy.max_delay_seconds,
            jitter_ratio=retry_policy.jitter_ratio,
        ),
    )
