from uuid import uuid4

from langflow.services.database.models.channel.context_model import (
    ChannelContextRole,
    ChannelConversationContextEntry,
)
from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionIdentityType,
    ChannelExecutionStatus,
)
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelConnectionCreate,
    ChannelContextMode,
    ChannelIdentityStatus,
)
from langflow.services.database.models.channel.webhook_job_model import ChannelWebhookJob


def test_production_channel_policy_defaults() -> None:
    payload = ChannelConnectionCreate(
        name="Production",
        channel_type="feishu",
        credentials={},
    )
    assert payload.access_policy == ChannelAccessPolicy.HYBRID.value
    assert payload.default_context_mode == ChannelContextMode.ISOLATED.value
    assert payload.max_concurrency == 10
    assert payload.per_user_concurrency == 1
    assert payload.per_user_queue_limit == 3
    assert payload.rate_limit_per_minute == 20
    assert payload.daily_quota == 0
    assert payload.task_timeout_seconds == 120
    assert payload.queue_timeout_seconds == 60
    assert payload.shared_context_window == 20
    assert payload.context_retention_days == 30


def test_channel_identity_and_execution_enums_cover_production_states() -> None:
    assert ChannelIdentityStatus.DISCOVERED.value == "discovered"
    assert ChannelExecutionIdentityType.SERVICE.value == "service"
    assert {status.value for status in ChannelExecutionStatus} >= {
        "queued",
        "running",
        "succeeded",
        "failed",
        "timeout",
        "cancelled",
        "delivery_failed",
    }


def test_webhook_jobs_store_stable_queue_scope() -> None:
    job = ChannelWebhookJob(
        connection_id=uuid4(),
        channel_type="feishu",
        external_event_id="evt-1",
        external_conversation_id="chat-1",
        external_user_id="user-1",
        conversation_type="group",
        queue_key="connection:chat:user",
        payload=b"{}",
    )
    assert job.queue_key == "connection:chat:user"


def test_context_entry_contract() -> None:
    entry = ChannelConversationContextEntry(
        connection_id=uuid4(),
        conversation_binding_id=uuid4(),
        external_event_id="evt-1",
        external_user_id="user-1",
        role=ChannelContextRole.USER.value,
        session_id="channel-session",
        text="hello",
    )
    assert entry.role == "user"
    assert entry.text == "hello"
