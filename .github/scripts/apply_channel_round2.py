from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected source block not found in {path}: {old[:120]!r}")
    file_path.write_text(text.replace(old, new, 1), encoding="utf-8")


# 1. Load every supported locale synchronously so a persisted non-English
# language never renders the English fallback during the first paint.
i18n_path = "src/frontend/src/i18n.ts"
replace_once(
    i18n_path,
    'import { channelTranslations } from "./locales/channelTranslations";\nimport en from "./locales/en.json";\n',
    'import { channelTranslations } from "./locales/channelTranslations";\n'
    'import de from "./locales/de.json";\n'
    'import en from "./locales/en.json";\n'
    'import es from "./locales/es.json";\n'
    'import fr from "./locales/fr.json";\n'
    'import ja from "./locales/ja.json";\n'
    'import pt from "./locales/pt.json";\n'
    'import zhHans from "./locales/zh-Hans.json";\n',
)
replace_once(
    i18n_path,
    '  resources: {\n    en: { translation: { ...en, ...channelTranslations.en } },\n  },\n',
    '  resources: {\n'
    '    de: { translation: { ...de, ...(channelTranslations.de ?? {}) } },\n'
    '    en: { translation: { ...en, ...channelTranslations.en } },\n'
    '    es: { translation: { ...es, ...(channelTranslations.es ?? {}) } },\n'
    '    fr: { translation: { ...fr, ...(channelTranslations.fr ?? {}) } },\n'
    '    ja: { translation: { ...ja, ...(channelTranslations.ja ?? {}) } },\n'
    '    pt: { translation: { ...pt, ...(channelTranslations.pt ?? {}) } },\n'
    '    "zh-Hans": {\n'
    '      translation: { ...zhHans, ...(channelTranslations["zh-Hans"] ?? {}) },\n'
    '    },\n'
    '  },\n',
)

# 2. Prefer actual ChatOutput messages over component labels such as “聊天记录”.
workflow_path = "src/backend/base/langflow/channels/services/workflow.py"
replace_once(
    workflow_path,
    '    return []\n\n\ndef render_run_response(response: RunResponse) -> str:\n'
    '    payload = response.model_dump(exclude_none=True)\n'
    '    candidates = _collect_text_candidates(payload.get("outputs"))\n',
    '    return []\n\n\ndef _collect_chat_output_messages(value: Any) -> list[str]:\n'
    '    """Extract rendered assistant messages from RunOutputs before generic metadata."""\n'
    '    if not isinstance(value, (list, tuple)):\n'
    '        return []\n'
    '    candidates: list[str] = []\n'
    '    for run_output in value:\n'
    '        if hasattr(run_output, "model_dump"):\n'
    '            run_output = run_output.model_dump(exclude_none=True)\n'
    '        if not isinstance(run_output, dict):\n'
    '            continue\n'
    '        result_items = run_output.get("outputs")\n'
    '        if not isinstance(result_items, (list, tuple)):\n'
    '            continue\n'
    '        for result_item in result_items:\n'
    '            if hasattr(result_item, "model_dump"):\n'
    '                result_item = result_item.model_dump(exclude_none=True)\n'
    '            if not isinstance(result_item, dict):\n'
    '                continue\n'
    '            messages = result_item.get("messages")\n'
    '            if not isinstance(messages, (list, tuple)):\n'
    '                continue\n'
    '            for message in messages:\n'
    '                if hasattr(message, "model_dump"):\n'
    '                    message = message.model_dump(exclude_none=True)\n'
    '                if not isinstance(message, dict):\n'
    '                    continue\n'
    '                sender = str(message.get("sender") or "").strip().lower()\n'
    '                if sender and sender not in {"machine", "ai", "assistant"}:\n'
    '                    continue\n'
    '                candidates.extend(_collect_text_candidates(message.get("message"), depth=1))\n'
    '    return candidates\n\n\ndef render_run_response(response: RunResponse) -> str:\n'
    '    payload = response.model_dump(exclude_none=True)\n'
    '    outputs = payload.get("outputs")\n'
    '    candidates = _collect_chat_output_messages(outputs) or _collect_text_candidates(outputs)\n',
)

# 3. Make the Feishu processing card idempotent across durable retries.
delivery_model = "src/backend/base/langflow/services/database/models/channel/outbound_delivery_model.py"
replace_once(
    delivery_model,
    'class ChannelOutboundDeliveryKind(str, Enum):\n'
    '    ACKNOWLEDGEMENT = "acknowledgement"\n'
    '    RESPONSE = "response"\n',
    'class ChannelOutboundDeliveryKind(str, Enum):\n'
    '    ACKNOWLEDGEMENT = "acknowledgement"\n'
    '    PROCESSING = "processing"\n'
    '    RESPONSE = "response"\n',
)

outbound_path = "src/backend/base/langflow/channels/services/outbound_delivery.py"
replace_once(
    outbound_path,
    'class OutboundDeliveryDecision:\n'
    '    should_send: bool\n'
    '    delivery_id: UUID | None\n'
    '    delivery_kind: ChannelOutboundDeliveryKind\n',
    'class OutboundDeliveryDecision:\n'
    '    should_send: bool\n'
    '    delivery_id: UUID | None\n'
    '    delivery_kind: ChannelOutboundDeliveryKind\n'
    '    provider_message_id: str | None = None\n',
)
replace_once(
    outbound_path,
    '                return OutboundDeliveryDecision(False, existing.id, delivery_kind)\n',
    '                return OutboundDeliveryDecision(\n'
    '                    False,\n'
    '                    existing.id,\n'
    '                    delivery_kind,\n'
    '                    existing.provider_message_id,\n'
    '                )\n',
)
replace_once(
    outbound_path,
    'async def reserve_outbound_acknowledgement(\n'
    '    event: ChannelEvent,\n'
    ') -> OutboundDeliveryDecision:\n',
    'async def reserve_outbound_processing(\n'
    '    event: ChannelEvent,\n'
    '    message: ChannelMessage,\n'
    ') -> OutboundDeliveryDecision:\n'
    '    return await _reserve_outbound_delivery(\n'
    '        event,\n'
    '        delivery_kind=ChannelOutboundDeliveryKind.PROCESSING,\n'
    '        response_digest=channel_response_digest(message),\n'
    '    )\n\n\nasync def reserve_outbound_acknowledgement(\n'
    '    event: ChannelEvent,\n'
    ') -> OutboundDeliveryDecision:\n',
)
replace_once(
    outbound_path,
    'async def send_outbound_response_once(\n'
    '    event: ChannelEvent,\n'
    '    message: ChannelMessage,\n'
    '    sender: Callable[[], Awaitable[str]],\n'
    ') -> str | None:\n',
    'async def send_outbound_processing_once(\n'
    '    event: ChannelEvent,\n'
    '    message: ChannelMessage,\n'
    '    sender: Callable[[], Awaitable[str]],\n'
    ') -> str | None:\n'
    '    decision = await reserve_outbound_processing(event, message)\n'
    '    if not decision.should_send or decision.delivery_id is None:\n'
    '        return decision.provider_message_id\n'
    '    try:\n'
    '        provider_message_id = await sender()\n'
    '    except Exception as provider_error:\n'
    '        try:\n'
    '            await mark_outbound_delivery_failed(\n'
    '                decision.delivery_id,\n'
    '                decision.delivery_kind,\n'
    '                provider_error,\n'
    '            )\n'
    '        except Exception:\n'
    '            await logger.aexception(\n'
    '                "Unable to persist failed outbound processing message for event %s",\n'
    '                event.event_id,\n'
    '            )\n'
    '        raise\n'
    '    await mark_outbound_delivery_sent(\n'
    '        decision.delivery_id,\n'
    '        decision.delivery_kind,\n'
    '        provider_message_id,\n'
    '    )\n'
    '    return provider_message_id\n\n\nasync def send_outbound_response_once(\n'
    '    event: ChannelEvent,\n'
    '    message: ChannelMessage,\n'
    '    sender: Callable[[], Awaitable[str]],\n'
    ') -> str | None:\n',
)

# 4. Commit the receipt before Feishu side effects and finalize logs independently.
dispatch_path = "src/backend/base/langflow/channels/services/dispatch.py"
replace_once(
    dispatch_path,
    'from __future__ import annotations\n\nfrom datetime import datetime, timezone\n',
    'from __future__ import annotations\n\nimport asyncio\nfrom datetime import datetime, timezone\n',
)
replace_once(
    dispatch_path,
    'from langflow.channels.services.execution_logs import finish_channel_execution, start_channel_execution\n',
    'from langflow.channels.services.execution_logs import finalize_channel_execution, start_channel_execution\n',
)
replace_once(
    dispatch_path,
    'from langflow.channels.services.retry import retry_channel_operation\n',
    'from langflow.channels.services.outbound_delivery import send_outbound_processing_once\n'
    'from langflow.channels.services.retry import retry_channel_operation\n',
)
replace_once(
    dispatch_path,
    '        processing_message_id = await self._send_processing_message(event)\n'
    '        succeeded = False\n'
    '        error_message: str | None = None\n'
    '        try:\n'
    '            channel_context = await self._build_bound_context(binding)\n'
    '            if command_name:\n'
    '                channel_context["command_name"] = command_name\n'
    '            # The workflow job service persists through its own database session. Commit\n'
    '            # conversation discovery and the running audit row first so SQLite does not\n'
    '            # keep a write lock while that session creates the workflow job.\n'
    '            if self.session is not None:\n'
    '                await self.session.commit()\n'
    '            response = await self.workflow_executor.execute(\n',
    '        # Persist the event receipt, discovered conversation, and running audit row\n'
    '        # before any provider side effect. This prevents a Feishu retry from racing\n'
    '        # the first delivery and creating a second processing/final card.\n'
    '        if self.session is not None:\n'
    '            await self.session.commit()\n'
    '        processing_message_id = await self._send_processing_message(event)\n'
    '        succeeded = False\n'
    '        error_message: str | None = None\n'
    '        try:\n'
    '            channel_context = await self._build_bound_context(binding)\n'
    '            if command_name:\n'
    '                channel_context["command_name"] = command_name\n'
    '            response = await self.workflow_executor.execute(\n',
)
replace_once(
    dispatch_path,
    '        except Exception as exc:  # noqa: BLE001\n'
    '            error_message = str(exc)\n'
    '            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)\n'
    '            response = ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")\n'
    '        finally:\n'
    '            if execution is not None:\n'
    '                try:\n'
    '                    await finish_channel_execution(\n'
    '                        self.session,\n'
    '                        execution,\n'
    '                        succeeded=succeeded,\n'
    '                        error_message=error_message,\n'
    '                    )\n'
    '                    await self.session.commit()\n'
    '                except Exception:  # noqa: BLE001\n'
    '                    await logger.aexception("Unable to finish channel execution log %s", execution.id)\n',
    '        except asyncio.CancelledError:\n'
    '            error_message = "Channel workflow execution was cancelled or timed out"\n'
    '            raise\n'
    '        except Exception as exc:  # noqa: BLE001\n'
    '            error_message = str(exc)\n'
    '            await logger.aexception("Channel workflow execution failed for flow %s", flow_identifier)\n'
    '            response = ChannelMessage(text="工作流执行失败，请在 OpenXFlow 运行记录中查看错误详情。")\n'
    '        finally:\n'
    '            if execution is not None:\n'
    '                try:\n'
    '                    await finalize_channel_execution(\n'
    '                        execution.id,\n'
    '                        succeeded=succeeded,\n'
    '                        error_message=error_message,\n'
    '                    )\n'
    '                except asyncio.CancelledError:\n'
    '                    raise\n'
    '                except Exception:  # noqa: BLE001\n'
    '                    await logger.aexception("Unable to finish channel execution log %s", execution.id)\n',
)
replace_once(
    dispatch_path,
    '        try:\n'
    '            return await retry_channel_operation(\n'
    '                lambda: self.adapter.send_response(event, processing_message),\n'
    '                operation_name="feishu.send_processing_message",\n'
    '            )\n'
    '        except Exception:  # noqa: BLE001\n',
    '        async def sender() -> str:\n'
    '            return await retry_channel_operation(\n'
    '                lambda: self.adapter.send_response(event, processing_message),\n'
    '                operation_name="feishu.send_processing_message",\n'
    '            )\n\n'
    '        try:\n'
    '            if self.session is None:\n'
    '                return await sender()\n'
    '            return await send_outbound_processing_once(event, processing_message, sender)\n'
    '        except Exception:  # noqa: BLE001\n',
)

# 5. Finalize execution rows on cancellation and repair stale running rows.
execution_path = "src/backend/base/langflow/channels/services/execution_logs.py"
replace_once(
    execution_path,
    'from __future__ import annotations\n\nimport math\nfrom datetime import datetime, timezone\n',
    'from __future__ import annotations\n\nimport asyncio\nimport math\nfrom datetime import datetime, timedelta, timezone\n',
)
replace_once(
    execution_path,
    'from langflow.services.database.models.channel.execution_model import (\n',
    'from langflow.channels.services.runtime_config import webhook_task_timeout_seconds\n'
    'from langflow.services.database.models.channel.execution_model import (\n',
)
replace_once(
    execution_path,
    '    ChannelExecutionStatus,\n)\n',
    '    ChannelExecutionStatus,\n)\nfrom langflow.services.deps import session_scope\n',
)
replace_once(
    execution_path,
    'async def list_channel_executions(\n',
    'async def finalize_channel_execution(\n'
    '    execution_id: UUID,\n'
    '    *,\n'
    '    succeeded: bool,\n'
    '    error_message: str | None = None,\n'
    ') -> None:\n'
    '    """Finish an audit row in an isolated session that survives caller cancellation."""\n'
    '    async def persist() -> None:\n'
    '        async with session_scope() as session:\n'
    '            execution = await session.get(ChannelExecutionLog, execution_id)\n'
    '            if execution is None:\n'
    '                return\n'
    '            await finish_channel_execution(\n'
    '                session,\n'
    '                execution,\n'
    '                succeeded=succeeded,\n'
    '                error_message=error_message,\n'
    '            )\n'
    '            await session.commit()\n\n'
    '    task = asyncio.create_task(persist())\n'
    '    await asyncio.shield(task)\n\n\nasync def _fail_stale_channel_executions(\n'
    '    session: AsyncSession,\n'
    '    connection_id: UUID,\n'
    ') -> None:\n'
    '    cutoff = _utc_now() - timedelta(seconds=webhook_task_timeout_seconds() + 60)\n'
    '    statement = select(ChannelExecutionLog).where(\n'
    '        ChannelExecutionLog.connection_id == connection_id,\n'
    '        ChannelExecutionLog.status == ChannelExecutionStatus.RUNNING.value,\n'
    '        ChannelExecutionLog.created_at <= cutoff,\n'
    '    )\n'
    '    stale_rows = (await session.exec(statement)).all()\n'
    '    for execution in stale_rows:\n'
    '        await finish_channel_execution(\n'
    '            session,\n'
    '            execution,\n'
    '            succeeded=False,\n'
    '            error_message="Channel workflow execution was interrupted or timed out",\n'
    '        )\n'
    '    if stale_rows:\n'
    '        await session.commit()\n\n\nasync def list_channel_executions(\n',
)
replace_once(
    execution_path,
    ') -> ChannelExecutionLogPage:\n'
    '    normalized_page = max(1, page)\n',
    ') -> ChannelExecutionLogPage:\n'
    '    await _fail_stale_channel_executions(session, connection_id)\n'
    '    normalized_page = max(1, page)\n',
)

# Regression tests.
Path("src/backend/tests/unit/channels/test_workflow_response.py").write_text(
    '''from langflow.channels.services.workflow import render_run_response\n\n\nclass FakeRunResponse:\n    def __init__(self, payload: dict) -> None:\n        self.payload = payload\n\n    def model_dump(self, *, exclude_none: bool = True) -> dict:\n        del exclude_none\n        return self.payload\n\n\ndef test_render_run_response_prefers_chat_message_over_component_label() -> None:\n    response = FakeRunResponse(\n        {\n            "outputs": [\n                {\n                    "outputs": [\n                        {\n                            "messages": [\n                                {\n                                    "message": "我是 Qwen，由阿里云开发。",\n                                    "sender": "Machine",\n                                    "sender_name": "AI",\n                                    "type": "text",\n                                }\n                            ],\n                            "component_display_name": "聊天记录",\n                        }\n                    ]\n                }\n            ],\n            "session_id": "channel-test",\n        }\n    )\n\n    assert render_run_response(response) == "我是 Qwen，由阿里云开发。"\n\n\ndef test_render_run_response_keeps_generic_fallback() -> None:\n    response = FakeRunResponse({"outputs": [{"outputs": [{"results": {"text": "fallback"}}]}]})\n\n    assert render_run_response(response) == "fallback"\n''',
    encoding="utf-8",
)

outbound_test = "src/backend/tests/unit/channels/test_outbound_delivery.py"
test_text = Path(outbound_test).read_text(encoding="utf-8")
test_text = test_text.replace(
    '    send_outbound_acknowledgement_once,\n    send_outbound_response_once,\n',
    '    send_outbound_acknowledgement_once,\n    send_outbound_processing_once,\n    send_outbound_response_once,\n',
    1,
)
test_text += '''\n\n@pytest.mark.asyncio\nasync def test_processing_delivery_reuses_existing_provider_message(monkeypatch) -> None:\n    called = False\n\n    async def reserve(_event, _message):\n        return OutboundDeliveryDecision(\n            False,\n            uuid4(),\n            ChannelOutboundDeliveryKind.PROCESSING,\n            "provider-processing-1",\n        )\n\n    async def sender() -> str:\n        nonlocal called\n        called = True\n        return "unexpected"\n\n    monkeypatch.setattr(outbound_delivery, "reserve_outbound_processing", reserve)\n\n    result = await send_outbound_processing_once(_event(), ChannelMessage(text="working"), sender)\n\n    assert result == "provider-processing-1"\n    assert called is False\n'''
Path(outbound_test).write_text(test_text, encoding="utf-8")

Path("src/frontend/src/pages/SettingsPage/pages/ChannelsPage/__tests__/i18n.test.ts").write_text(
    '''import i18n from "@/i18n";\n\ndescribe("channel locale initialization", () => {\n  it("loads the persisted Chinese bundle before the first render", () => {\n    expect(i18n.hasResourceBundle("zh-Hans", "translation")).toBe(true);\n    expect(i18n.getFixedT("zh-Hans")("channels.title")).toBe("渠道中心");\n  });\n});\n''',
    encoding="utf-8",
)

# Remove one-shot patch resources from the resulting branch.
Path(".github/workflows/channel-acceptance-round2-fixes.yml").unlink()
Path(".github/scripts/apply_channel_round2.py").unlink()
