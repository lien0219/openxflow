from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    if new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing patch target in {path}: {old[:160]!r}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, new: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate block in {path}: {start!r} -> {end!r}")
    write(path, content[:start_index] + new + content[end_index:])


queueing = r'''"""Resolve durable FIFO queue scopes for normalized channel events."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.channels.domain.models import ChannelEvent
from langflow.channels.services.access_control import effective_context_mode
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
)

_SCOPE_METADATA_KEYS = (
    "conversation_scope_id",
    "thread_id",
    "message_thread_id",
    "topic_id",
    "message_thread_topic_id",
)


@dataclass(frozen=True)
class ChannelQueueDescriptor:
    queue_key: str
    external_conversation_id: str
    external_user_id: str
    conversation_type: str
    conversation_scope_id: str
    context_mode: str
    serialized_by_conversation: bool


def _conversation_scope_id(event: ChannelEvent) -> str:
    for key in _SCOPE_METADATA_KEYS:
        value = event.conversation.metadata.get(key)
        if value is None:
            value = event.message.metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _bounded_queue_key(connection_id: str, scope_type: str, components: tuple[str, ...]) -> str:
    canonical = "\x1f".join(components)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    return f"channel:{connection_id}:{scope_type}:{digest}"


async def resolve_channel_queue_descriptor(
    session: AsyncSession,
    connection: ChannelConnection,
    event: ChannelEvent,
) -> ChannelQueueDescriptor:
    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.connection_id == connection.id,
        ChannelConversationBinding.external_conversation_id == event.conversation.external_conversation_id,
    )
    binding = (await session.exec(statement)).first()
    context_mode = effective_context_mode(connection, binding)
    conversation_type = event.conversation.conversation_type
    scope_id = _conversation_scope_id(event)
    serialized_by_conversation = conversation_type != "private" and context_mode in {
        ChannelContextMode.SHARED.value,
        ChannelContextMode.HYBRID.value,
    }
    components = (
        str(connection.id),
        event.conversation.external_conversation_id,
        scope_id,
    )
    if serialized_by_conversation:
        scope_type = "conversation"
    else:
        scope_type = "member"
        components = (*components, event.user.external_user_id)
    return ChannelQueueDescriptor(
        queue_key=_bounded_queue_key(str(connection.id), scope_type, components),
        external_conversation_id=event.conversation.external_conversation_id,
        external_user_id=event.user.external_user_id,
        conversation_type=conversation_type,
        conversation_scope_id=scope_id,
        context_mode=context_mode,
        serialized_by_conversation=serialized_by_conversation,
    )
'''
write("src/backend/base/langflow/channels/services/queueing.py", queueing)

WEBHOOK_JOBS = "src/backend/base/langflow/channels/services/webhook_jobs.py"
replace_once(
    WEBHOOK_JOBS,
    "from datetime import timedelta\n",
    "from datetime import timedelta\n",
)
replace_once(
    WEBHOOK_JOBS,
    "    ChannelEventReceipt,\n    ChannelReceiptStatus,\n",
    "    ChannelConnection,\n    ChannelEventReceipt,\n    ChannelReceiptStatus,\n",
)

enqueue_block = r'''async def enqueue_provider_webhook_job(
    session: AsyncSession,
    *,
    connection_id: UUID,
    channel_type: str,
    external_event_id: str,
    headers: dict[str, str],
    payload: bytes,
    connection: ChannelConnection | None = None,
    external_conversation_id: str = "",
    external_user_id: str = "",
    conversation_type: str = "private",
    queue_key: str = "",
) -> bool:
    """Persist a validated callback and commit it before returning a successful provider ACK.

    Queue pressure is represented by a durable rejection job instead of dropping
    an already verified callback. The worker later sends the user-facing rejection
    through the same idempotent outbound path as a normal response.
    """
    config = durable_webhook_job_config()
    now = utc_now()
    normalized_queue_key = queue_key or f"{connection_id}:legacy:{external_event_id}"
    persisted_headers = dict(headers)
    rejection_reason: str | None = None
    queue_position = 0

    if connection is not None and queue_key:
        active_statuses = (
            ChannelWebhookJobStatus.PENDING.value,
            ChannelWebhookJobStatus.PROCESSING.value,
        )
        queue_position = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == connection_id,
                        ChannelWebhookJob.queue_key == queue_key,
                        ChannelWebhookJob.status.in_(active_statuses),
                    )
                )
            ).one()
        )
        pending_count = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == connection_id,
                        ChannelWebhookJob.queue_key == queue_key,
                        ChannelWebhookJob.status == ChannelWebhookJobStatus.PENDING.value,
                    )
                )
            ).one()
        )
        if pending_count >= connection.per_user_queue_limit:
            rejection_reason = "queue_limit"

        if rejection_reason is None and connection.rate_limit_per_minute > 0:
            rate_filters = [
                ChannelWebhookJob.connection_id == connection_id,
                ChannelWebhookJob.created_at >= now - timedelta(minutes=1),
            ]
            if external_user_id:
                rate_filters.append(ChannelWebhookJob.external_user_id == external_user_id)
            recent_count = int(
                (
                    await session.exec(
                        select(sa.func.count(ChannelWebhookJob.id)).where(*rate_filters)
                    )
                ).one()
            )
            if recent_count >= connection.rate_limit_per_minute:
                rejection_reason = "rate_limit"

        if rejection_reason is None and connection.daily_quota > 0:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_count = int(
                (
                    await session.exec(
                        select(sa.func.count(ChannelWebhookJob.id)).where(
                            ChannelWebhookJob.connection_id == connection_id,
                            ChannelWebhookJob.created_at >= day_start,
                        )
                    )
                ).one()
            )
            if daily_count >= connection.daily_quota:
                rejection_reason = "daily_quota"

    persisted_headers["x-openxflow-queue-position"] = str(queue_position)
    if rejection_reason is not None:
        persisted_headers["x-openxflow-queue-rejection"] = rejection_reason
        normalized_queue_key = f"{connection_id}:rejected:{external_event_id}"

    job = ChannelWebhookJob(
        connection_id=connection_id,
        channel_type=channel_type,
        external_event_id=external_event_id,
        external_conversation_id=external_conversation_id,
        external_user_id=external_user_id,
        conversation_type=conversation_type,
        queue_key=normalized_queue_key,
        headers_data=persisted_headers,
        payload=payload,
        max_attempts=config.max_attempts,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        duplicate = (
            await session.exec(
                select(ChannelWebhookJob.id).where(
                    ChannelWebhookJob.connection_id == connection_id,
                    ChannelWebhookJob.external_event_id == external_event_id,
                )
            )
        ).first()
        if duplicate is not None:
            return False
        raise
    return True


'''
replace_between(WEBHOOK_JOBS, "async def enqueue_provider_webhook_job(\n", "def _claimable", enqueue_block)

claim_block = r'''async def claim_provider_webhook_job(
    session: AsyncSession,
    *,
    worker_id: UUID,
) -> ChannelWebhookJob | None:
    """Claim one ready job while preserving per-queue FIFO and connection limits.

    Claimers serialize on the connection row. PostgreSQL therefore cannot race
    past max_concurrency or claim two jobs for the same queue; SQLite retains its
    normal single-writer behavior for development and tests.
    """
    config = durable_webhook_job_config()
    now = utc_now()
    candidate_ids = list(
        (
            await session.exec(
                select(ChannelWebhookJob.id)
                .where(_claimable(now))
                .order_by(ChannelWebhookJob.next_attempt_at, ChannelWebhookJob.created_at, ChannelWebhookJob.id)
                .limit(32)
            )
        ).all()
    )
    active_processing = sa.and_(
        ChannelWebhookJob.status == ChannelWebhookJobStatus.PROCESSING.value,
        ChannelWebhookJob.lease_expires_at.is_not(None),
        ChannelWebhookJob.lease_expires_at > now,
    )

    for candidate_id in candidate_ids:
        candidate = await session.get(ChannelWebhookJob, candidate_id)
        if candidate is None:
            await session.rollback()
            continue

        limits = (
            await session.exec(
                select(
                    ChannelConnection.max_concurrency,
                    ChannelConnection.per_user_concurrency,
                )
                .where(ChannelConnection.id == candidate.connection_id)
                .with_for_update()
            )
        ).first()
        max_concurrency = int(limits[0]) if limits is not None else max(1, config.worker_count)
        per_queue_concurrency = int(limits[1]) if limits is not None else 1

        connection_active = int(
            (
                await session.exec(
                    select(sa.func.count(ChannelWebhookJob.id)).where(
                        ChannelWebhookJob.connection_id == candidate.connection_id,
                        active_processing,
                    )
                )
            ).one()
        )
        if connection_active >= max_concurrency:
            await session.rollback()
            continue

        rejection_job = "x-openxflow-queue-rejection" in candidate.headers_data
        if not rejection_job:
            head_id = (
                await session.exec(
                    select(ChannelWebhookJob.id)
                    .where(
                        ChannelWebhookJob.queue_key == candidate.queue_key,
                        ChannelWebhookJob.status == ChannelWebhookJobStatus.PENDING.value,
                    )
                    .order_by(ChannelWebhookJob.created_at, ChannelWebhookJob.id)
                    .limit(1)
                )
            ).first()
            if candidate.status == ChannelWebhookJobStatus.PENDING.value and head_id != candidate.id:
                await session.rollback()
                continue

            queue_active = int(
                (
                    await session.exec(
                        select(sa.func.count(ChannelWebhookJob.id)).where(
                            ChannelWebhookJob.queue_key == candidate.queue_key,
                            active_processing,
                        )
                    )
                ).one()
            )
            serialized_queue = ":conversation:" in candidate.queue_key
            queue_limit = 1 if serialized_queue else max(1, per_queue_concurrency)
            if queue_active >= queue_limit:
                await session.rollback()
                continue

        result = await session.exec(
            sa.update(ChannelWebhookJob)
            .where(ChannelWebhookJob.id == candidate_id, _claimable(now))
            .values(
                status=ChannelWebhookJobStatus.PROCESSING.value,
                attempts=ChannelWebhookJob.attempts + 1,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=config.lease_seconds),
                updated_at=now,
                last_error=None,
            )
        )
        if result.rowcount != 1:
            await session.rollback()
            continue
        await session.commit()
        return await session.get(ChannelWebhookJob, candidate_id)
    await session.rollback()
    return None


'''
replace_between(WEBHOOK_JOBS, "async def claim_provider_webhook_job(\n", "async def complete_provider_webhook_job(\n", claim_block)

execute_block = r'''    async def _execute(self, job: ChannelWebhookJob) -> bool:
        async with session_scope() as session:
            await recover_stale_event_receipt(session, job)
        created_at = job.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=utc_now().tzinfo)
        queue_wait_ms = max(0, int((utc_now() - created_at).total_seconds() * 1000))
        raw_position = job.headers_data.get("x-openxflow-queue-position", "0")
        try:
            queue_position = max(0, int(str(raw_position)))
        except ValueError:
            queue_position = 0
        rejection_reason = job.headers_data.get("x-openxflow-queue-rejection")
        return await process_provider_webhook(
            connection_id=job.connection_id,
            expected_channel_type=job.channel_type,
            headers={str(key): str(value) for key, value in job.headers_data.items()},
            payload=job.payload,
            preverified=True,
            queue_wait_ms=queue_wait_ms,
            queue_position=queue_position,
            queue_rejection_reason=str(rejection_reason) if rejection_reason else None,
        )

'''
replace_between(WEBHOOK_JOBS, "    async def _execute(self, job: ChannelWebhookJob) -> bool:\n", "    async def _process", execute_block)

WEBHOOK_PROCESSING = "src/backend/base/langflow/channels/services/webhook_processing.py"
replace_once(
    WEBHOOK_PROCESSING,
    "from langflow.channels.domain.exceptions import DuplicateChannelEventError\n",
    "from langflow.channels.domain.exceptions import DuplicateChannelEventError\nfrom langflow.channels.domain.models import ChannelMessage\n",
)
replace_once(
    WEBHOOK_PROCESSING,
    '''    preverified: bool = False,
) -> bool:
''',
    '''    preverified: bool = False,
    queue_wait_ms: int = 0,
    queue_position: int = 0,
    queue_rejection_reason: str | None = None,
) -> bool:
''',
)
replace_once(
    WEBHOOK_PROCESSING,
    '''        dispatcher = ChannelDispatchService(session, connection, adapter)

        try:
''',
    '''        dispatcher = ChannelDispatchService(session, connection, adapter)

        async def queued_handler(event):  # type: ignore[no-untyped-def]
            event.message.metadata["queue_wait_ms"] = max(0, queue_wait_ms)
            event.message.metadata["queue_position"] = max(0, queue_position)
            if queue_rejection_reason == "queue_limit":
                return ChannelMessage(text="你已有多个任务正在处理，请等待当前任务完成后再试。")
            if queue_rejection_reason == "rate_limit":
                return ChannelMessage(text="当前请求过于频繁，请稍后再试。")
            if queue_rejection_reason == "daily_quota":
                return ChannelMessage(text="当前渠道今日调用额度已用完，请联系管理员。")
            if queue_wait_ms > connection.queue_timeout_seconds * 1000:
                return ChannelMessage(text="当前请求排队时间过长，任务已取消，请稍后重试。")
            return await dispatcher.handle(event)

        try:
''',
)
replace_once(
    WEBHOOK_PROCESSING,
    "                    dispatcher.handle,\n                    deduplicator=deduplicator,\n",
    "                    queued_handler,\n                    deduplicator=deduplicator,\n",
)
# Both verified and non-verified gateway calls contain the same handler block.
content = read(WEBHOOK_PROCESSING)
if "                    dispatcher.handle,\n                    deduplicator=deduplicator,\n" in content:
    write(
        WEBHOOK_PROCESSING,
        content.replace(
            "                    dispatcher.handle,\n                    deduplicator=deduplicator,\n",
            "                    queued_handler,\n                    deduplicator=deduplicator,\n",
            1,
        ),
    )

CHANNEL_WEBHOOKS = "src/backend/base/langflow/api/v1/channel_webhooks.py"
replace_once(
    CHANNEL_WEBHOOKS,
    "from langflow.channels.services.runtime_config import durable_webhook_job_config, webhook_max_body_bytes\n",
    "from langflow.channels.services.queueing import resolve_channel_queue_descriptor\nfrom langflow.channels.services.runtime_config import durable_webhook_job_config, webhook_max_body_bytes\n",
)
replace_once(
    CHANNEL_WEBHOOKS,
    '''    if durable_webhook_job_config().enabled:
        await enqueue_provider_webhook_job(
''',
    '''    if durable_webhook_job_config().enabled:
        queue = await resolve_channel_queue_descriptor(db, connection, event)
        await enqueue_provider_webhook_job(
''',
)
replace_once(
    CHANNEL_WEBHOOKS,
    '''            payload=payload,
        )
''',
    '''            payload=payload,
            connection=connection,
            external_conversation_id=queue.external_conversation_id,
            external_user_id=queue.external_user_id,
            conversation_type=queue.conversation_type,
            queue_key=queue.queue_key,
        )
''',
)

FACTORY = "src/backend/base/langflow/channels/adapters/factory.py"
replace_once(
    FACTORY,
    '''            robot_code=credentials.get("robot_code"),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://api.dingtalk.com")),
''',
    '''            robot_code=credentials.get("robot_code"),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://api.dingtalk.com")),
            stream_authenticated=connection.connection_mode == "stream",
''',
)

DINGTALK_STREAM = "src/backend/base/langflow/channels/services/dingtalk_stream.py"
replace_once(
    DINGTALK_STREAM,
    "from langflow.channels.services.gateway import ChannelGateway\n",
    "from langflow.channels.services.gateway import ChannelGateway\nfrom langflow.channels.services.queueing import resolve_channel_queue_descriptor\nfrom langflow.channels.services.runtime_config import durable_webhook_job_config\nfrom langflow.channels.services.webhook_jobs import enqueue_provider_webhook_job\n",
)
replace_once(
    DINGTALK_STREAM,
    '''        gateway = ChannelGateway()
        gateway.register_adapter(connection.id, adapter)
''',
    '''        if durable_webhook_job_config().enabled:
            event = await adapter.parse_event({}, payload)
            queue = await resolve_channel_queue_descriptor(session, connection, event)
            await enqueue_provider_webhook_job(
                session,
                connection_id=connection.id,
                channel_type="dingtalk",
                external_event_id=event.event_id,
                headers={},
                payload=payload,
                connection=connection,
                external_conversation_id=queue.external_conversation_id,
                external_user_id=queue.external_user_id,
                conversation_type=queue.conversation_type,
                queue_key=queue.queue_key,
            )
            return

        gateway = ChannelGateway()
        gateway.register_adapter(connection.id, adapter)
''',
)

SQLITE_TEST = "src/backend/tests/unit/channels/test_durable_webhook_jobs_sqlite.py"
replace_once(
    SQLITE_TEST,
    '''_CREATE_JOB_TABLE = """
CREATE TABLE channel_webhook_job (
''',
    '''_CREATE_CONNECTION_TABLE = """
CREATE TABLE channel_connection (
    id CHAR(32) NOT NULL PRIMARY KEY,
    max_concurrency INTEGER NOT NULL DEFAULT 10,
    per_user_concurrency INTEGER NOT NULL DEFAULT 1
)
"""

_CREATE_JOB_TABLE = """
CREATE TABLE channel_webhook_job (
''',
)
replace_once(
    SQLITE_TEST,
    '''    external_event_id VARCHAR(255) NOT NULL,
    headers_data JSON NOT NULL,
''',
    '''    external_event_id VARCHAR(255) NOT NULL,
    external_conversation_id VARCHAR(255) NOT NULL DEFAULT '',
    external_user_id VARCHAR(255) NOT NULL DEFAULT '',
    conversation_type VARCHAR(32) NOT NULL DEFAULT 'private',
    queue_key VARCHAR(768) NOT NULL DEFAULT '',
    headers_data JSON NOT NULL,
''',
)
replace_once(
    SQLITE_TEST,
    '''    async with engine.begin() as connection:
        await connection.execute(sa.text(_CREATE_JOB_TABLE))
''',
    '''    async with engine.begin() as connection:
        await connection.execute(sa.text(_CREATE_CONNECTION_TABLE))
        await connection.execute(sa.text(_CREATE_JOB_TABLE))
''',
)

fifo_test = r'''

async def test_durable_webhook_jobs_preserve_queue_fifo_and_allow_other_sessions() -> None:
    engine, factory = await _session_factory()
    connection_id = uuid4()
    first_worker = uuid4()
    second_worker = uuid4()

    try:
        async with factory() as session:
            await session.exec(
                sa.text(
                    "INSERT INTO channel_connection (id, max_concurrency, per_user_concurrency) "
                    "VALUES (:id, 10, 1)"
                ),
                params={"id": connection_id.hex},
            )
            await session.commit()
            for event_id, queue_key, conversation_id in (
                ("event-a1", "queue-a", "chat-a"),
                ("event-a2", "queue-a", "chat-a"),
                ("event-b1", "queue-b", "chat-b"),
            ):
                await enqueue_provider_webhook_job(
                    session,
                    connection_id=connection_id,
                    channel_type="telegram",
                    external_event_id=event_id,
                    external_conversation_id=conversation_id,
                    external_user_id="same-user",
                    queue_key=queue_key,
                    headers={},
                    payload=b"{}",
                )

        async with factory() as session:
            first = await claim_provider_webhook_job(session, worker_id=first_worker)
        assert first is not None
        assert first.external_event_id == "event-a1"

        async with factory() as session:
            parallel = await claim_provider_webhook_job(session, worker_id=second_worker)
        assert parallel is not None
        assert parallel.external_event_id == "event-b1"

        async with factory() as session:
            assert await complete_provider_webhook_job(
                session,
                job_id=first.id,
                worker_id=first_worker,
            )

        async with factory() as session:
            next_in_fifo = await claim_provider_webhook_job(session, worker_id=uuid4())
        assert next_in_fifo is not None
        assert next_in_fifo.external_event_id == "event-a2"
    finally:
        await engine.dispose()
'''
content = read(SQLITE_TEST)
if "test_durable_webhook_jobs_preserve_queue_fifo" not in content:
    write(SQLITE_TEST, content + fifo_test)

queueing_test = r'''from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.services.queueing import resolve_channel_queue_descriptor


class FakeResult:
    def first(self):
        return None


class FakeSession:
    async def exec(self, _statement):
        return FakeResult()


def _event(*, user_id: str, conversation_id: str = "chat-1", conversation_type: str = "group"):
    return SimpleNamespace(
        conversation=SimpleNamespace(
            external_conversation_id=conversation_id,
            conversation_type=conversation_type,
            metadata={},
        ),
        message=SimpleNamespace(metadata={}),
        user=SimpleNamespace(external_user_id=user_id),
    )


async def test_isolated_group_queue_is_member_scoped() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="isolated")
    first = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="a"))
    second = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="b"))
    assert first.queue_key != second.queue_key
    assert first.serialized_by_conversation is False


async def test_shared_group_queue_is_conversation_scoped() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="shared")
    first = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="a"))
    second = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="b"))
    assert first.queue_key == second.queue_key
    assert first.serialized_by_conversation is True


async def test_private_queue_remains_member_scoped_in_shared_default() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="shared")
    first = await resolve_channel_queue_descriptor(
        FakeSession(),
        connection,
        _event(user_id="a", conversation_type="private"),
    )
    second = await resolve_channel_queue_descriptor(
        FakeSession(),
        connection,
        _event(user_id="b", conversation_type="private"),
    )
    assert first.queue_key != second.queue_key
'''
write("src/backend/tests/unit/channels/test_channel_queueing.py", queueing_test)

print("Applied durable per-session channel FIFO queue")
