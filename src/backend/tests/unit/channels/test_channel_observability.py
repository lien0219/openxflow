from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from langflow.channels.services.configuration_audit import (
    channel_resource_changes,
    record_channel_configuration_audit,
    sanitize_channel_audit_value,
)
from langflow.channels.services.message_records import list_channel_messages
from langflow.channels.services.observability import _percentile, retry_failed_outbound_delivery
from langflow.services.database.models.channel.audit_model import ChannelConfigurationAudit
from langflow.services.database.models.channel.message_model import (
    ChannelMessageDirection,
    ChannelMessageRecord,
    ChannelMessageRecordKind,
    ChannelMessageRecordStatus,
)
from langflow.services.database.models.channel.model import (
    ChannelEventReceipt,
    ChannelReceiptStatus,
    utc_now,
)
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)
from langflow.services.database.models.channel.webhook_job_model import (
    ChannelWebhookJob,
    ChannelWebhookJobStatus,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession


async def _database(tmp_path):  # type: ignore[no-untyped-def]
    database_path = tmp_path / "channel-observability.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        for table in (
            ChannelMessageRecord.__table__,
            ChannelConfigurationAudit.__table__,
            ChannelEventReceipt.__table__,
            ChannelWebhookJob.__table__,
            ChannelOutboundDelivery.__table__,
        ):
            await connection.run_sync(lambda sync_connection, target=table: target.create(sync_connection))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


def test_configuration_audit_redacts_nested_credentials_without_hiding_ids() -> None:
    sanitized = sanitize_channel_audit_value(
        {
            "knowledge_base_id": "kb-1",
            "settings_data": {
                "bot_token": "secret-value",
                "nested": {"client_secret": "another-secret", "region": "cn"},
            },
        }
    )

    assert sanitized["knowledge_base_id"] == "kb-1"
    assert sanitized["settings_data"]["bot_token"] == "[REDACTED]"
    assert sanitized["settings_data"]["nested"]["client_secret"] == "[REDACTED]"
    assert sanitized["settings_data"]["nested"]["region"] == "cn"


def test_configuration_audit_changes_only_contains_mutated_fields() -> None:
    changes = channel_resource_changes(
        {"enabled": True, "name": "old", "unchanged": 1},
        {"enabled": False, "name": "new", "unchanged": 1},
    )

    assert changes == {
        "enabled": {"before": True, "after": False},
        "name": {"before": "old", "after": "new"},
    }


def test_percentile_is_nearest_rank_and_bounded() -> None:
    assert _percentile([], 0.95) is None
    assert _percentile([10], 0.95) == 10
    assert _percentile([10, 20, 30, 40], 0.95) == 40
    assert _percentile([40, 10, 30, 20], 0.5) == 20


async def test_message_center_filters_by_direction_status_and_query(tmp_path) -> None:
    engine, factory = await _database(tmp_path)
    connection_id = uuid4()
    try:
        async with factory() as session:
            session.add_all(
                [
                    ChannelMessageRecord(
                        connection_id=connection_id,
                        external_event_id="event-1",
                        external_message_id="message-1",
                        external_conversation_id="chat-1",
                        external_user_id="user-1",
                        sender_name="Alice",
                        direction=ChannelMessageDirection.INBOUND.value,
                        message_kind=ChannelMessageRecordKind.INBOUND.value,
                        message_type="message.text",
                        status=ChannelMessageRecordStatus.PROCESSED.value,
                        text="production incident",
                    ),
                    ChannelMessageRecord(
                        connection_id=connection_id,
                        external_event_id="event-1",
                        external_conversation_id="chat-1",
                        external_user_id="user-1",
                        sender_name="OpenXFlow",
                        direction=ChannelMessageDirection.OUTBOUND.value,
                        message_kind=ChannelMessageRecordKind.RESPONSE.value,
                        message_type="text",
                        status=ChannelMessageRecordStatus.SENT.value,
                        text="incident resolved",
                    ),
                    ChannelMessageRecord(
                        connection_id=connection_id,
                        external_event_id="event-2",
                        external_conversation_id="chat-2",
                        external_user_id="user-2",
                        sender_name="Bob",
                        direction=ChannelMessageDirection.INBOUND.value,
                        message_kind=ChannelMessageRecordKind.INBOUND.value,
                        message_type="message.text",
                        status=ChannelMessageRecordStatus.FAILED.value,
                        text="unrelated",
                    ),
                ]
            )
            await session.commit()

        async with factory() as session:
            page = await list_channel_messages(
                session,
                connection_id,
                direction=ChannelMessageDirection.OUTBOUND.value,
                status=ChannelMessageRecordStatus.SENT.value,
                query="resolved",
            )
        assert page.total == 1
        assert page.items[0].direction == ChannelMessageDirection.OUTBOUND.value
        assert page.items[0].text == "incident resolved"
    finally:
        await engine.dispose()


async def test_manual_delivery_retry_requeues_durable_job_and_receipt(tmp_path) -> None:
    engine, factory = await _database(tmp_path)
    connection_id = uuid4()
    event_id = "event-retry"
    now = utc_now()
    try:
        async with factory() as session:
            delivery = ChannelOutboundDelivery(
                connection_id=connection_id,
                external_event_id=event_id,
                delivery_kind=ChannelOutboundDeliveryKind.RESPONSE.value,
                response_digest="0" * 64,
                status=ChannelOutboundDeliveryStatus.FAILED.value,
                last_error="provider unavailable",
            )
            job = ChannelWebhookJob(
                connection_id=connection_id,
                channel_type="telegram",
                external_event_id=event_id,
                payload=b"{}",
                status=ChannelWebhookJobStatus.FAILED.value,
                attempts=5,
                max_attempts=5,
                next_attempt_at=now + timedelta(days=1),
                last_error="exhausted",
            )
            receipt = ChannelEventReceipt(
                connection_id=connection_id,
                external_event_id=event_id,
                status=ChannelReceiptStatus.PROCESSED.value,
            )
            session.add_all([delivery, job, receipt])
            await session.commit()
            delivery_id = delivery.id
            job_id = job.id

        async with factory() as session:
            result = await retry_failed_outbound_delivery(
                session,
                connection_id=connection_id,
                delivery_id=delivery_id,
            )
            await session.commit()

        assert result.webhook_job_id == job_id
        assert result.status == ChannelWebhookJobStatus.PENDING.value
        assert result.already_queued is False

        async with factory() as session:
            stored_job = await session.get(ChannelWebhookJob, job_id)
            stored_receipt = (
                await session.exec(
                    select(ChannelEventReceipt).where(
                        ChannelEventReceipt.connection_id == connection_id,
                        ChannelEventReceipt.external_event_id == event_id,
                    )
                )
            ).one()
        assert stored_job is not None
        assert stored_job.status == ChannelWebhookJobStatus.PENDING.value
        assert stored_job.attempts == 0
        assert stored_job.lease_owner is None
        assert stored_receipt.status == ChannelReceiptStatus.FAILED.value
    finally:
        await engine.dispose()


async def test_configuration_audit_persists_redacted_snapshots(tmp_path) -> None:
    engine, factory = await _database(tmp_path)
    connection_id = uuid4()
    actor_id = uuid4()
    try:
        async with factory() as session:
            audit = await record_channel_configuration_audit(
                session,
                connection_id=connection_id,
                actor_user_id=actor_id,
                action="update",
                resource_type="connection",
                resource_id=connection_id,
                before={"name": "before", "settings_data": {"app_secret": "one"}},
                after={"name": "after", "settings_data": {"app_secret": "two"}},
            )
            await session.commit()
            audit_id = audit.id

        async with factory() as session:
            stored = await session.get(ChannelConfigurationAudit, audit_id)
        assert stored is not None
        assert stored.before_data["settings_data"]["app_secret"] == "[REDACTED]"
        assert stored.after_data["settings_data"]["app_secret"] == "[REDACTED]"
        assert stored.changes_data["name"] == {"before": "before", "after": "after"}
        assert "settings_data" not in stored.changes_data
    finally:
        await engine.dispose()
