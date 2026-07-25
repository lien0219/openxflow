from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def replace_once(path: str, old: str, new: str, *, label: str) -> None:
    content = read(path)
    if new and new in content:
        return
    if old not in content:
        raise RuntimeError(f"Missing observability rollout target for {label}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate observability rollout block for {label}")
    write(path, content[:start_index] + replacement + content[end_index:])


# ---------------------------------------------------------------------------
# Model exports and router registration
# ---------------------------------------------------------------------------
CHANNEL_MODELS = "src/backend/base/langflow/services/database/models/channel/__init__.py"
replace_once(
    CHANNEL_MODELS,
    "from langflow.services.database.models.channel.binding_model import ChannelBindingCode\n",
    "from langflow.services.database.models.channel.audit_model import (\n"
    "    ChannelConfigurationAudit,\n"
    "    ChannelConfigurationAuditPage,\n"
    "    ChannelConfigurationAuditRead,\n"
    ")\n"
    "from langflow.services.database.models.channel.binding_model import ChannelBindingCode\n",
    label="channel audit model exports",
)
replace_once(
    CHANNEL_MODELS,
    "from langflow.services.database.models.channel.model import (\n",
    "from langflow.services.database.models.channel.message_model import (\n"
    "    ChannelMessageDirection,\n"
    "    ChannelMessageRecord,\n"
    "    ChannelMessageRecordKind,\n"
    "    ChannelMessageRecordPage,\n"
    "    ChannelMessageRecordRead,\n"
    "    ChannelMessageRecordStatus,\n"
    ")\n"
    "from langflow.services.database.models.channel.model import (\n",
    label="channel message model exports",
)
replace_once(
    CHANNEL_MODELS,
    '    "ChannelBindingCode",\n',
    '    "ChannelBindingCode",\n'
    '    "ChannelConfigurationAudit",\n'
    '    "ChannelConfigurationAuditPage",\n'
    '    "ChannelConfigurationAuditRead",\n',
    label="audit all exports",
)
replace_once(
    CHANNEL_MODELS,
    '    "ChannelIdentityStatus",\n',
    '    "ChannelIdentityStatus",\n'
    '    "ChannelMessageDirection",\n'
    '    "ChannelMessageRecord",\n'
    '    "ChannelMessageRecordKind",\n'
    '    "ChannelMessageRecordPage",\n'
    '    "ChannelMessageRecordRead",\n'
    '    "ChannelMessageRecordStatus",\n',
    label="message all exports",
)

TOP_MODELS = "src/backend/base/langflow/services/database/models/__init__.py"
replace_once(
    TOP_MODELS,
    "    ChannelConnection,\n",
    "    ChannelConfigurationAudit,\n    ChannelConnection,\n",
    label="top-level audit model",
)
replace_once(
    TOP_MODELS,
    "    ChannelIdentity,\n",
    "    ChannelIdentity,\n    ChannelMessageRecord,\n",
    label="top-level message model",
)
replace_once(
    TOP_MODELS,
    '    "ChannelConnection",\n',
    '    "ChannelConfigurationAudit",\n    "ChannelConnection",\n',
    label="top-level audit export",
)
replace_once(
    TOP_MODELS,
    '    "ChannelIdentity",\n',
    '    "ChannelIdentity",\n    "ChannelMessageRecord",\n',
    label="top-level message export",
)

V1_INIT = "src/backend/base/langflow/api/v1/__init__.py"
replace_once(
    V1_INIT,
    "from langflow.api.v1.channel_management import router as channel_management_router\n",
    "from langflow.api.v1.channel_management import router as channel_management_router\n"
    "from langflow.api.v1.channel_observability import router as channel_observability_router\n",
    label="observability router import",
)
replace_once(
    V1_INIT,
    '    "channel_management_router",\n',
    '    "channel_management_router",\n    "channel_observability_router",\n',
    label="observability router export",
)

API_ROUTER = "src/backend/base/langflow/api/router.py"
replace_once(
    API_ROUTER,
    "    channel_management_router,\n",
    "    channel_management_router,\n    channel_observability_router,\n",
    label="api observability router import",
)
replace_once(
    API_ROUTER,
    "router_v1.include_router(channel_management_router)\n",
    "router_v1.include_router(channel_management_router)\n"
    "router_v1.include_router(channel_observability_router)\n",
    label="mount observability router",
)

# ---------------------------------------------------------------------------
# Message recording and delivery lifecycle
# ---------------------------------------------------------------------------
EXECUTION_LOGS = "src/backend/base/langflow/channels/services/execution_logs.py"
replace_once(
    EXECUTION_LOGS,
    "from sqlalchemy import func\n",
    "from lfx.log.logger import logger\nfrom sqlalchemy import func\n",
    label="execution delivery logger",
)
replace_once(
    EXECUTION_LOGS,
    "async def _fail_stale_channel_executions(session: AsyncSession, connection_id: UUID) -> None:\n",
    '''async def record_channel_delivery_outcome(
    *,
    connection_id: UUID,
    external_event_id: str,
    duration_ms: int,
    error: Exception | None = None,
) -> None:
    async with session_scope() as session:
        execution = (
            await session.exec(
                select(ChannelExecutionLog)
                .where(
                    ChannelExecutionLog.connection_id == connection_id,
                    ChannelExecutionLog.external_event_id == external_event_id,
                )
                .order_by(ChannelExecutionLog.created_at.desc())
                .limit(1)
            )
        ).first()
        if execution is None:
            return
        execution.delivery_duration_ms = max(0, duration_ms)
        if error is not None:
            execution.status = ChannelExecutionStatus.DELIVERY_FAILED.value
            execution.error_code = type(error).__name__[:128]
            execution.error_message = str(error)[:4000]
        session.add(execution)
        await session.commit()


async def safe_record_channel_delivery_outcome(
    *,
    connection_id: UUID,
    external_event_id: str,
    duration_ms: int,
    error: Exception | None = None,
) -> None:
    try:
        await record_channel_delivery_outcome(
            connection_id=connection_id,
            external_event_id=external_event_id,
            duration_ms=duration_ms,
            error=error,
        )
    except Exception:  # noqa: BLE001
        await logger.aexception("Unable to persist channel delivery outcome for %s", external_event_id)


async def _fail_stale_channel_executions(session: AsyncSession, connection_id: UUID) -> None:
''',
    label="delivery outcome persistence",
)
replace_once(
    EXECUTION_LOGS,
    "    trigger_type: str | None = None,\n) -> ChannelExecutionLogPage:\n",
    "    trigger_type: str | None = None,\n"
    "    query: str | None = None,\n"
    "    external_user_id: str | None = None,\n"
    "    session_id: str | None = None,\n"
    "    execution_identity_type: str | None = None,\n"
    "    flow_id: UUID | None = None,\n"
    "    error_code: str | None = None,\n"
    "    created_from: datetime | None = None,\n"
    "    created_to: datetime | None = None,\n"
    ") -> ChannelExecutionLogPage:\n",
    label="execution filters signature",
)
replace_once(
    EXECUTION_LOGS,
    "    if trigger_type:\n        filters.append(ChannelExecutionLog.trigger_type == trigger_type)\n\n",
    "    if trigger_type:\n"
    "        filters.append(ChannelExecutionLog.trigger_type == trigger_type)\n"
    "    if query and query.strip():\n"
    "        pattern = f\"%{query.strip()}%\"\n"
    "        filters.append(\n"
    "            sa.or_(\n"
    "                ChannelExecutionLog.external_event_id.ilike(pattern),\n"
    "                ChannelExecutionLog.external_user_id.ilike(pattern),\n"
    "                ChannelExecutionLog.session_id.ilike(pattern),\n"
    "                ChannelExecutionLog.command_name.ilike(pattern),\n"
    "                ChannelExecutionLog.error_code.ilike(pattern),\n"
    "                ChannelExecutionLog.error_message.ilike(pattern),\n"
    "            )\n"
    "        )\n"
    "    if external_user_id:\n"
    "        filters.append(ChannelExecutionLog.external_user_id == external_user_id)\n"
    "    if session_id:\n"
    "        filters.append(ChannelExecutionLog.session_id == session_id)\n"
    "    if execution_identity_type:\n"
    "        filters.append(ChannelExecutionLog.execution_identity_type == execution_identity_type)\n"
    "    if flow_id is not None:\n"
    "        filters.append(ChannelExecutionLog.flow_id == flow_id)\n"
    "    if error_code:\n"
    "        filters.append(ChannelExecutionLog.error_code == error_code)\n"
    "    if created_from is not None:\n"
    "        filters.append(ChannelExecutionLog.created_at >= created_from)\n"
    "    if created_to is not None:\n"
    "        filters.append(ChannelExecutionLog.created_at <= created_to)\n\n",
    label="execution filter predicates",
)
replace_once(
    EXECUTION_LOGS,
    "from sqlalchemy import func\n",
    "import sqlalchemy as sa\nfrom sqlalchemy import func\n",
    label="execution sqlalchemy alias",
)

GATEWAY = "src/backend/base/langflow/channels/services/gateway.py"
replace_once(
    GATEWAY,
    "from collections.abc import Awaitable, Callable\n",
    "import time\nfrom collections.abc import Awaitable, Callable\n",
    label="gateway delivery timer",
)
replace_once(
    GATEWAY,
    "from langflow.channels.services.outbound_delivery import (\n",
    "from langflow.channels.services.execution_logs import safe_record_channel_delivery_outcome\n"
    "from langflow.channels.services.message_records import (\n"
    "    safe_mark_inbound_message,\n"
    "    safe_record_inbound_message,\n"
    "    safe_record_outbound_message,\n"
    ")\n"
    "from langflow.channels.services.outbound_delivery import (\n",
    label="gateway message observability imports",
)
replace_once(
    GATEWAY,
    "from langflow.channels.services.retry import retry_channel_operation\n",
    "from langflow.channels.services.retry import retry_channel_operation\n"
    "from langflow.services.database.models.channel.message_model import ChannelMessageRecordStatus\n",
    label="gateway message status import",
)
replace_between(
    GATEWAY,
    "        try:\n            if adapter.requires_event_acknowledgement(event):\n",
    "        return event\n",
    '''        await safe_record_inbound_message(event)
        try:
            if adapter.requires_event_acknowledgement(event):

                async def acknowledgement_sender() -> None:
                    await adapter.acknowledge_event(event)

                if guard_outbound:
                    await send_outbound_acknowledgement_once(event, acknowledgement_sender)
                else:
                    await acknowledgement_sender()

            response = await handler(event)
            if response is not None:

                async def response_sender() -> str:
                    return await retry_channel_operation(
                        lambda: adapter.send_response(event, response),
                        operation_name=f"{adapter.channel_type.value}.send_response",
                    )

                delivery_started = time.perf_counter()
                try:
                    if guard_outbound:
                        provider_message_id = await send_outbound_response_once(event, response, response_sender)
                    else:
                        provider_message_id = await response_sender()
                except Exception as delivery_error:
                    duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))
                    await safe_record_outbound_message(
                        event,
                        response,
                        status=ChannelMessageRecordStatus.FAILED.value,
                        error=delivery_error,
                    )
                    await safe_record_channel_delivery_outcome(
                        connection_id=event.connection_id,
                        external_event_id=event.event_id,
                        duration_ms=duration_ms,
                        error=delivery_error,
                    )
                    raise
                else:
                    duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))
                    await safe_record_outbound_message(
                        event,
                        response,
                        status=ChannelMessageRecordStatus.SENT.value,
                        provider_message_id=provider_message_id,
                    )
                    await safe_record_channel_delivery_outcome(
                        connection_id=event.connection_id,
                        external_event_id=event.event_id,
                        duration_ms=duration_ms,
                    )
        except Exception as exc:
            await safe_mark_inbound_message(
                event,
                status=ChannelMessageRecordStatus.FAILED.value,
                error=exc,
            )
            if deduplicator is not None and receipt is not None:
                await deduplicator.fail(receipt, exc)
            raise
        else:
            await safe_mark_inbound_message(
                event,
                status=ChannelMessageRecordStatus.PROCESSED.value,
            )
            if deduplicator is not None and receipt is not None:
                await deduplicator.complete(receipt)
''',
    label="gateway persistent message lifecycle",
)

DISPATCH = "src/backend/base/langflow/channels/services/dispatch.py"
replace_once(
    DISPATCH,
    "import inspect\n",
    "import inspect\nimport time\n",
    label="dispatch delivery timer",
)
replace_once(
    DISPATCH,
    "from langflow.channels.services.execution_logs import finalize_channel_execution, start_channel_execution\n",
    "from langflow.channels.services.execution_logs import (\n"
    "    finalize_channel_execution,\n"
    "    safe_record_channel_delivery_outcome,\n"
    "    start_channel_execution,\n"
    ")\n",
    label="dispatch delivery outcome import",
)
replace_once(
    DISPATCH,
    "from langflow.channels.services.outbound_delivery import send_outbound_processing_once\n",
    "from langflow.channels.services.message_records import safe_record_outbound_message\n"
    "from langflow.channels.services.outbound_delivery import send_outbound_processing_once\n",
    label="dispatch outbound message import",
)
replace_once(
    DISPATCH,
    "from langflow.services.database.models.channel.model import (\n",
    "from langflow.services.database.models.channel.message_model import ChannelMessageRecordStatus\n"
    "from langflow.services.database.models.channel.model import (\n",
    label="dispatch message status import",
)
replace_once(
    DISPATCH,
    "        if processing_message_id is not None:\n            try:\n                await retry_channel_operation(\n",
    "        if processing_message_id is not None:\n"
    "            delivery_started = time.perf_counter()\n"
    "            try:\n"
    "                await retry_channel_operation(\n",
    label="dispatch final update timing",
)
replace_once(
    DISPATCH,
    "                )\n                return None\n            except Exception:  # noqa: BLE001\n",
    "                )\n"
    "                duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))\n"
    "                await safe_record_outbound_message(\n"
    "                    event,\n"
    "                    response,\n"
    "                    status=ChannelMessageRecordStatus.SENT.value,\n"
    "                    provider_message_id=processing_message_id,\n"
    "                )\n"
    "                await safe_record_channel_delivery_outcome(\n"
    "                    connection_id=event.connection_id,\n"
    "                    external_event_id=event.event_id,\n"
    "                    duration_ms=duration_ms,\n"
    "                )\n"
    "                return None\n"
    "            except Exception:  # noqa: BLE001\n",
    label="record updated processing response",
)

MESSAGE_RECORDS = "src/backend/base/langflow/channels/services/message_records.py"
replace_once(
    MESSAGE_RECORDS,
    "        if existing is None:\n            session.add(\n",
    "        if existing is not None and provider_message_id is None:\n"
    "            values.pop(\"provider_message_id\", None)\n"
    "        if existing is None:\n"
    "            session.add(\n",
    label="preserve provider message id",
)

AUDIT_SERVICE = "src/backend/base/langflow/channels/services/configuration_audit.py"
replace_once(
    AUDIT_SERVICE,
    "from pydantic import BaseModel\n",
    "import sqlalchemy as sa\nfrom pydantic import BaseModel\n",
    label="audit sqlalchemy import",
)
replace_once(
    AUDIT_SERVICE,
    '                select(__import__("sqlalchemy").func.count())\n',
    "                select(sa.func.count())\n",
    label="audit portable count",
)

# ---------------------------------------------------------------------------
# Management API audits and richer execution filters
# ---------------------------------------------------------------------------
CHANNELS_API = "src/backend/base/langflow/api/v1/channels.py"
replace_once(
    CHANNELS_API,
    "from langflow.channels.services.conversation_validation import (\n",
    "from langflow.channels.services.configuration_audit import (\n"
    "    channel_resource_snapshot,\n"
    "    record_channel_configuration_audit,\n"
    ")\n"
    "from langflow.channels.services.conversation_validation import (\n",
    label="channels api audit imports",
)
replace_once(
    CHANNELS_API,
    "    else:\n        await db.commit()\n        return result\n\n\n@router.patch(\"/{connection_id}\"",
    "    else:\n"
    "        await record_channel_configuration_audit(\n"
    "            db,\n"
    "            connection_id=result.id,\n"
    "            actor_user_id=current_user.id,\n"
    "            action=\"create\",\n"
    "            resource_type=\"connection\",\n"
    "            resource_id=result.id,\n"
    "            after=result,\n"
    "        )\n"
    "        await db.commit()\n"
    "        return result\n\n\n"
    "@router.patch(\"/{connection_id}\"",
    label="connection create audit",
)
replace_once(
    CHANNELS_API,
    "    connection = await _owned_connection_or_404(db, current_user.id, connection_id)\n"
    "    if payload.service_user_id is not None:\n",
    "    connection = await _owned_connection_or_404(db, current_user.id, connection_id)\n"
    "    before = channel_resource_snapshot(connection)\n"
    "    if payload.service_user_id is not None:\n",
    label="connection update snapshot",
)
replace_once(
    CHANNELS_API,
    "    else:\n        await db.commit()\n        return result\n\n\n@router.delete(\"/{connection_id}\"",
    "    else:\n"
    "        await record_channel_configuration_audit(\n"
    "            db,\n"
    "            connection_id=connection.id,\n"
    "            actor_user_id=current_user.id,\n"
    "            action=\"update\",\n"
    "            resource_type=\"connection\",\n"
    "            resource_id=connection.id,\n"
    "            before=before,\n"
    "            after=result,\n"
    "        )\n"
    "        await db.commit()\n"
    "        return result\n\n\n"
    "@router.delete(\"/{connection_id}\"",
    label="connection update audit",
)
replace_once(
    CHANNELS_API,
    "    connection = await _owned_connection_or_404(db, current_user.id, connection_id)\n"
    "    await delete_channel_connection(db, connection)\n",
    "    connection = await _owned_connection_or_404(db, current_user.id, connection_id)\n"
    "    before = channel_resource_snapshot(connection)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection.id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"delete\",\n"
    "        resource_type=\"connection\",\n"
    "        resource_id=connection.id,\n"
    "        before=before,\n"
    "    )\n"
    "    await delete_channel_connection(db, connection)\n",
    label="connection delete audit",
)
replace_once(
    CHANNELS_API,
    "    result = await upsert_channel_identity(db, connection_id, payload)\n"
    "    await db.commit()\n",
    "    result = await upsert_channel_identity(db, connection_id, payload)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"upsert\",\n"
    "        resource_type=\"identity\",\n"
    "        resource_id=result.id,\n"
    "        after=result,\n"
    "    )\n"
    "    await db.commit()\n",
    label="identity upsert audit",
)
replace_once(
    CHANNELS_API,
    "    if not await delete_channel_identity(db, connection_id, identity_id):\n"
    "        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel identity not found\")\n"
    "    await db.commit()\n",
    "    if not await delete_channel_identity(db, connection_id, identity_id):\n"
    "        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel identity not found\")\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"delete\",\n"
    "        resource_type=\"identity\",\n"
    "        resource_id=identity_id,\n"
    "        before={\"id\": identity_id},\n"
    "    )\n"
    "    await db.commit()\n",
    label="identity delete audit",
)
replace_once(
    CHANNELS_API,
    "    result = await upsert_channel_conversation_binding(db, connection_id, payload)\n"
    "    await db.commit()\n",
    "    result = await upsert_channel_conversation_binding(db, connection_id, payload)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"upsert\",\n"
    "        resource_type=\"conversation\",\n"
    "        resource_id=result.id,\n"
    "        after=result,\n"
    "    )\n"
    "    await db.commit()\n",
    label="conversation upsert audit",
)
replace_once(
    CHANNELS_API,
    "    if binding is None:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel conversation not found\")\n"
    "    await validate_conversation_binding_resources(\n",
    "    if binding is None:\n"
    "        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel conversation not found\")\n"
    "    before = channel_resource_snapshot(binding)\n"
    "    await validate_conversation_binding_resources(\n",
    label="conversation update snapshot",
)
replace_once(
    CHANNELS_API,
    "    result = await update_channel_conversation_binding(db, connection, binding, payload)\n"
    "    await db.commit()\n",
    "    result = await update_channel_conversation_binding(db, connection, binding, payload)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"update\",\n"
    "        resource_type=\"conversation\",\n"
    "        resource_id=binding.id,\n"
    "        before=before,\n"
    "        after=result,\n"
    "    )\n"
    "    await db.commit()\n",
    label="conversation update audit",
)
replace_once(
    CHANNELS_API,
    "    await delete_legacy_channel_conversation_binding(db, connection_id, binding_id)\n"
    "    await db.commit()\n",
    "    before = channel_resource_snapshot(binding)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"delete\",\n"
    "        resource_type=\"conversation\",\n"
    "        resource_id=binding.id,\n"
    "        before=before,\n"
    "    )\n"
    "    await delete_legacy_channel_conversation_binding(db, connection_id, binding_id)\n"
    "    await db.commit()\n",
    label="conversation delete audit",
)

MANAGEMENT_API = "src/backend/base/langflow/api/v1/channel_management.py"
replace_once(
    MANAGEMENT_API,
    "from typing import Annotated\n",
    "from datetime import datetime\nfrom typing import Annotated\n",
    label="execution datetime filters",
)
replace_once(
    MANAGEMENT_API,
    "from langflow.channels.services.commands import (\n",
    "from langflow.channels.services.configuration_audit import (\n"
    "    channel_resource_snapshot,\n"
    "    record_channel_configuration_audit,\n"
    ")\n"
    "from langflow.channels.services.commands import (\n",
    label="management audit imports",
)
replace_once(
    MANAGEMENT_API,
    "    else:\n        await db.commit()\n        return result\n\n\n@router.patch(\"/{connection_id}/commands/{command_id}\"",
    "    else:\n"
    "        await record_channel_configuration_audit(\n"
    "            db,\n"
    "            connection_id=connection_id,\n"
    "            actor_user_id=current_user.id,\n"
    "            action=\"create\",\n"
    "            resource_type=\"command\",\n"
    "            resource_id=result.id,\n"
    "            after=result,\n"
    "        )\n"
    "        await db.commit()\n"
    "        return result\n\n\n"
    "@router.patch(\"/{connection_id}/commands/{command_id}\"",
    label="command create audit",
)
replace_once(
    MANAGEMENT_API,
    "    if command is None:\n        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel command not found\")\n"
    "    if payload.flow_id is not None:\n",
    "    if command is None:\n"
    "        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=\"Channel command not found\")\n"
    "    before = channel_resource_snapshot(command)\n"
    "    if payload.flow_id is not None:\n",
    label="command update snapshot",
)
replace_once(
    MANAGEMENT_API,
    "    else:\n        await db.commit()\n        return result\n\n\n@router.delete(\"/{connection_id}/commands/{command_id}\"",
    "    else:\n"
    "        await record_channel_configuration_audit(\n"
    "            db,\n"
    "            connection_id=connection_id,\n"
    "            actor_user_id=current_user.id,\n"
    "            action=\"update\",\n"
    "            resource_type=\"command\",\n"
    "            resource_id=command.id,\n"
    "            before=before,\n"
    "            after=result,\n"
    "        )\n"
    "        await db.commit()\n"
    "        return result\n\n\n"
    "@router.delete(\"/{connection_id}/commands/{command_id}\"",
    label="command update audit",
)
replace_once(
    MANAGEMENT_API,
    "    await delete_workflow_command(db, connection, current_user, command)\n"
    "    await db.commit()\n",
    "    before = channel_resource_snapshot(command)\n"
    "    await delete_workflow_command(db, connection, current_user, command)\n"
    "    await record_channel_configuration_audit(\n"
    "        db,\n"
    "        connection_id=connection_id,\n"
    "        actor_user_id=current_user.id,\n"
    "        action=\"delete\",\n"
    "        resource_type=\"command\",\n"
    "        resource_id=command.id,\n"
    "        before=before,\n"
    "    )\n"
    "    await db.commit()\n",
    label="command delete audit",
)
replace_once(
    MANAGEMENT_API,
    "    trigger_type: Annotated[str | None, Query(max_length=32)] = None,\n) -> ChannelExecutionLogPage:\n",
    "    trigger_type: Annotated[str | None, Query(max_length=32)] = None,\n"
    "    query: Annotated[str | None, Query(max_length=255)] = None,\n"
    "    external_user_id: Annotated[str | None, Query(max_length=255)] = None,\n"
    "    session_id: Annotated[str | None, Query(max_length=255)] = None,\n"
    "    execution_identity_type: Annotated[str | None, Query(max_length=32)] = None,\n"
    "    flow_id: Annotated[UUID | None, Query()] = None,\n"
    "    error_code: Annotated[str | None, Query(max_length=128)] = None,\n"
    "    created_from: Annotated[datetime | None, Query()] = None,\n"
    "    created_to: Annotated[datetime | None, Query()] = None,\n"
    ") -> ChannelExecutionLogPage:\n",
    label="execution API filters",
)
replace_once(
    MANAGEMENT_API,
    "        status=status_filter,\n        trigger_type=trigger_type,\n",
    "        status=status_filter,\n"
    "        trigger_type=trigger_type,\n"
    "        query=query,\n"
    "        external_user_id=external_user_id,\n"
    "        session_id=session_id,\n"
    "        execution_identity_type=execution_identity_type,\n"
    "        flow_id=flow_id,\n"
    "        error_code=error_code,\n"
    "        created_from=created_from,\n"
    "        created_to=created_to,\n",
    label="execution API filter forwarding",
)

ADMIN_API = "src/backend/base/langflow/api/v1/channel_admin.py"
replace_once(
    ADMIN_API,
    "from langflow.channels.services.conversation_validation import validate_channel_routing_resources\n",
    "from langflow.channels.services.configuration_audit import (\n"
    "    channel_resource_snapshot,\n"
    "    record_channel_configuration_audit,\n"
    ")\n"
    "from langflow.channels.services.conversation_validation import validate_channel_routing_resources\n",
    label="batch audit imports",
)
replace_once(
    ADMIN_API,
    "    for row in rows:\n"
    "        update = _batch_update_payload(payload)\n"
    "        updated_items.append(await update_channel_conversation_binding(db, connection, row, update))\n",
    "    for row in rows:\n"
    "        before = channel_resource_snapshot(row)\n"
    "        update = _batch_update_payload(payload)\n"
    "        updated = await update_channel_conversation_binding(db, connection, row, update)\n"
    "        updated_items.append(updated)\n"
    "        await record_channel_configuration_audit(\n"
    "            db,\n"
    "            connection_id=connection_id,\n"
    "            actor_user_id=current_user.id,\n"
    "            action=f\"batch_{payload.action}\",\n"
    "            resource_type=\"conversation\",\n"
    "            resource_id=row.id,\n"
    "            before=before,\n"
    "            after=updated,\n"
    "        )\n",
    label="batch conversation audits",
)

# ---------------------------------------------------------------------------
# Migration regression chain
# ---------------------------------------------------------------------------
MIGRATION_TEST = "src/backend/tests/unit/channels/test_channel_migrations_sqlite.py"
replace_once(
    MIGRATION_TEST,
    "from langflow.alembic.versions import (\n    f7d0b5c3e4a6_add_channel_webhook_jobs as webhook_job_migration,\n)\n",
    "from langflow.alembic.versions import (\n"
    "    e2f5a8c1d7b9_add_channel_production_controls as production_controls_migration,\n"
    ")\n"
    "from langflow.alembic.versions import (\n"
    "    f3a6c9e2b4d7_add_channel_message_and_config_audit as observability_migration,\n"
    ")\n"
    "from langflow.alembic.versions import (\n"
    "    f7d0b5c3e4a6_add_channel_webhook_jobs as webhook_job_migration,\n"
    ")\n",
    label="observability migration imports",
)
replace_once(
    MIGRATION_TEST,
    "    status_index_repair_migration,\n)\n",
    "    status_index_repair_migration,\n"
    "    production_controls_migration,\n"
    "    observability_migration,\n"
    ")\n",
    label="observability migration order",
)
replace_once(
    MIGRATION_TEST,
    '        "d1e4f9a8b6c3",\n    ]\n',
    '        "d1e4f9a8b6c3",\n'
    '        "e2f5a8c1d7b9",\n'
    '        "f3a6c9e2b4d7",\n'
    "    ]\n",
    label="observability revision assertions",
)
replace_once(
    MIGRATION_TEST,
    '        "c0a3e8f7d5b2",\n    ]\n',
    '        "c0a3e8f7d5b2",\n'
    '        "d1e4f9a8b6c3",\n'
    '        "e2f5a8c1d7b9",\n'
    "    ]\n",
    label="observability down revision assertions",
)
replace_once(
    MIGRATION_TEST,
    '            "channel_execution_log",\n        }\n',
    '            "channel_execution_log",\n'
    '            "channel_conversation_context_entry",\n'
    '            "channel_message_record",\n'
    '            "channel_configuration_audit",\n'
    "        }\n",
    label="observability expected tables",
)
