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
        raise RuntimeError(f"Missing capability rollout target for {label}")
    write(path, content.replace(old, new, 1))


def replace_between(path: str, start: str, end: str, replacement: str, *, label: str) -> None:
    content = read(path)
    start_index = content.find(start)
    end_index = content.find(end, start_index)
    if start_index < 0 or end_index < 0:
        raise RuntimeError(f"Unable to locate capability rollout block for {label}")
    write(path, content[:start_index] + replacement + content[end_index:])


conversation_scope = '''"""Provider-neutral conversation thread and topic scope helpers."""

from __future__ import annotations

from langflow.channels.domain.models import ChannelEvent

_SCOPE_METADATA_KEYS = (
    "conversation_scope_id",
    "thread_id",
    "message_thread_id",
    "topic_id",
    "message_thread_topic_id",
)


def conversation_scope_id(event: ChannelEvent) -> str:
    """Return a stable thread/topic identifier without knowing the provider."""
    for key in _SCOPE_METADATA_KEYS:
        value = event.conversation.metadata.get(key)
        if value is None:
            value = event.message.metadata.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""
'''
write("src/backend/base/langflow/channels/services/conversation_scope.py", conversation_scope)

response_policy = '''"""Provider-neutral channel response mode policy."""

from __future__ import annotations

from enum import Enum

from langflow.channels.domain.models import ChannelEvent, ChannelEventType


class ChannelResponseMode(str, Enum):
    MENTION_ONLY = "mention_only"
    ALL_MESSAGES = "all_messages"
    COMMANDS_ONLY = "commands_only"
    DISABLED = "disabled"


_LEGACY_ALIASES = {
    "mentions_only": ChannelResponseMode.MENTION_ONLY.value,
    "mention": ChannelResponseMode.MENTION_ONLY.value,
}


def normalize_response_mode(value: str | None) -> str:
    normalized = (value or ChannelResponseMode.MENTION_ONLY.value).strip().lower()
    normalized = _LEGACY_ALIASES.get(normalized, normalized)
    allowed = {mode.value for mode in ChannelResponseMode}
    return normalized if normalized in allowed else ChannelResponseMode.MENTION_ONLY.value


def should_process_channel_event(
    event: ChannelEvent,
    *,
    command: str | None,
    response_mode: str | None,
) -> bool:
    """Apply group response policy consistently to text, files and actions."""
    if event.conversation.conversation_type == "private":
        return True

    mode = normalize_response_mode(response_mode)
    if mode == ChannelResponseMode.DISABLED.value:
        return False
    if event.event_type == ChannelEventType.ACTION:
        return True
    if command is not None:
        return True
    if mode == ChannelResponseMode.ALL_MESSAGES.value:
        return True
    if mode == ChannelResponseMode.COMMANDS_ONLY.value:
        return False
    return bool(event.message.mentions)
'''
write("src/backend/base/langflow/channels/services/response_policy.py", response_policy)

capabilities = '''"""Provider capability metadata shared by runtime and channel-management UI."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChannelProviderCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    conversation_types: tuple[str, ...]
    supports_private_chat: bool = True
    supports_group_chat: bool = False
    supports_channel_chat: bool = False
    supports_mentions: bool = False
    supports_reply_reference: bool = False
    supports_message_update: bool = False
    supports_processing_indicator: bool = False
    supports_processing_message: bool = False
    supports_interactive_card: bool = False
    supports_file_upload: bool = False
    supports_threads: bool = False
    supports_streaming_connection: bool = False
    processing_message_type: str = "text"
    processing_message_metadata: dict[str, Any] = Field(default_factory=dict)


PROVIDER_CAPABILITIES: dict[str, ChannelProviderCapabilities] = {
    "telegram": ChannelProviderCapabilities(
        conversation_types=("private", "group", "supergroup", "channel"),
        supports_group_chat=True,
        supports_channel_chat=True,
        supports_mentions=True,
        supports_reply_reference=True,
        supports_message_update=True,
        supports_processing_message=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        supports_threads=True,
    ),
    "feishu": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_message_update=True,
        supports_processing_message=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        processing_message_type="card",
        processing_message_metadata={"feishu_update_multi": True},
    ),
    "dingtalk": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_interactive_card=True,
        supports_file_upload=True,
        supports_streaming_connection=True,
    ),
    "wecom": ChannelProviderCapabilities(
        conversation_types=("private",),
        supports_file_upload=True,
        supports_interactive_card=True,
    ),
    "mock": ChannelProviderCapabilities(
        conversation_types=("private", "group"),
        supports_group_chat=True,
        supports_mentions=True,
        supports_file_upload=True,
    ),
}


def get_provider_capabilities() -> dict[str, ChannelProviderCapabilities]:
    return PROVIDER_CAPABILITIES.copy()


def get_provider_capability(channel_type: str) -> ChannelProviderCapabilities | None:
    return PROVIDER_CAPABILITIES.get(channel_type.strip().lower())


def validate_provider_conversation_type(channel_type: str, conversation_type: str) -> bool:
    capabilities = get_provider_capability(channel_type)
    return capabilities is not None and conversation_type in capabilities.conversation_types
'''
write("src/backend/base/langflow/channels/services/capabilities.py", capabilities)

QUEUEING = "src/backend/base/langflow/channels/services/queueing.py"
replace_once(
    QUEUEING,
    "from langflow.channels.services.access_control import effective_context_mode\n",
    "from langflow.channels.services.access_control import effective_context_mode\nfrom langflow.channels.services.conversation_scope import conversation_scope_id\n",
    label="queue scope import",
)
replace_between(
    QUEUEING,
    "_SCOPE_METADATA_KEYS = (\n",
    "def _bounded_queue_key",
    "",
    label="remove duplicate scope helper",
)
replace_once(
    QUEUEING,
    "    scope_id = _conversation_scope_id(event)\n",
    "    scope_id = conversation_scope_id(event)\n",
    label="shared queue scope helper",
)

WORKFLOW = "src/backend/base/langflow/channels/services/workflow.py"
replace_once(
    WORKFLOW,
    "from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType\n",
    "from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType\nfrom langflow.channels.services.conversation_scope import conversation_scope_id\n",
    label="workflow scope import",
)
replace_between(
    WORKFLOW,
    "def build_channel_session_id(\n",
    "def _collect_text_candidates",
    """def build_channel_session_id(event: ChannelEvent, context_mode: str = ChannelContextMode.ISOLATED.value) -> str:
    parts = [
        event.channel.value,
        str(event.connection_id),
        event.conversation.external_conversation_id,
        conversation_scope_id(event),
    ]
    if context_mode != ChannelContextMode.SHARED.value or event.conversation.conversation_type == "private":
        parts.append(event.user.external_user_id)
    raw = ":".join(parts)
    return f"channel-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


""",
    label="thread-aware session identity",
)
replace_once(
    WORKFLOW,
    """            "conversation_type": event.conversation.conversation_type,
            "message_id": event.message.external_message_id,
""",
    """            "conversation_type": event.conversation.conversation_type,
            "conversation_scope_id": conversation_scope_id(event),
            "message_id": event.message.external_message_id,
""",
    label="workflow scope context",
)

DISPATCH = "src/backend/base/langflow/channels/services/dispatch.py"
replace_once(
    DISPATCH,
    "from langflow.channels.services.binding import discover_channel_identity, issue_channel_binding_code\n",
    "from langflow.channels.services.binding import discover_channel_identity, issue_channel_binding_code\nfrom langflow.channels.services.capabilities import get_provider_capability\n",
    label="dispatch capability import",
)
replace_once(
    DISPATCH,
    "from langflow.channels.services.retry import retry_channel_operation\n",
    "from langflow.channels.services.response_policy import normalize_response_mode, should_process_channel_event\nfrom langflow.channels.services.retry import retry_channel_operation\n",
    label="dispatch response policy import",
)
replace_once(
    DISPATCH,
    "        if self._should_ignore_group_event(event, binding=binding, command=command):\n",
    """        response_mode = binding.response_mode if binding is not None else self.connection.default_response_mode
        if self._should_ignore_group_event(event, command=command, response_mode=response_mode):
""",
    label="effective response mode",
)
replace_between(
    DISPATCH,
    "    async def _send_processing_message(self, event: ChannelEvent) -> str | None:\n",
    "    async def _binding_required_message",
    """    async def _send_processing_message(self, event: ChannelEvent) -> str | None:
        capabilities = get_provider_capability(event.channel.value)
        if (
            capabilities is None
            or not capabilities.supports_processing_message
            or not capabilities.supports_message_update
        ):
            return None
        processing_message = ChannelMessage(
            message_type=ChannelMessageType(capabilities.processing_message_type),
            text="⏳ 正在处理中，请稍候…",
            metadata=dict(capabilities.processing_message_metadata),
        )

        async def sender() -> str:
            return await retry_channel_operation(
                lambda: self.adapter.send_response(event, processing_message),
                operation_name=f"{event.channel.value}.send_processing_message",
            )

        try:
            if self.session is None:
                return await sender()
            return await send_outbound_processing_once(event, processing_message, sender)
        except Exception:  # noqa: BLE001
            await logger.aexception(
                "Unable to send %s processing message; continuing without it",
                event.channel.value,
            )
            return None

""",
    label="capability-driven processing message",
)
replace_between(
    DISPATCH,
    "    @staticmethod\n    def _should_ignore_group_event(\n",
    "    @staticmethod\n    def _help_message",
    """    @staticmethod
    def _should_ignore_group_event(
        event: ChannelEvent,
        *,
        command: str | None = None,
        response_mode: str | None = None,
        binding: ChannelConversationBinding | None = None,
    ) -> bool:
        effective_mode = response_mode
        if effective_mode is None and binding is not None:
            effective_mode = binding.response_mode
        return not should_process_channel_event(
            event,
            command=command,
            response_mode=effective_mode,
        )

""",
    label="uniform group response policy",
)
replace_once(
    DISPATCH,
    """                    "response_mode": binding.response_mode,
""",
    """                    "response_mode": normalize_response_mode(binding.response_mode),
""",
    label="normalized response context",
)

MODEL = "src/backend/base/langflow/services/database/models/channel/model.py"
replace_once(
    MODEL,
    '    default_response_mode: str = Field(default="mentions_only", max_length=32)\n',
    '    default_response_mode: str = Field(default="mention_only", max_length=32)\n',
    label="connection response default",
)
replace_once(
    MODEL,
    '    response_mode: str = Field(default="mentions_only", max_length=32)\n',
    '    response_mode: str = Field(default="mention_only", max_length=32)\n',
    label="conversation response default",
)

TEST_DISPATCH = "src/backend/tests/unit/channels/test_dispatch.py"
replace_once(
    TEST_DISPATCH,
    """def _event(
    *,
    text: str,
    conversation_type: str = "private",
    channel: ChannelType = ChannelType.TELEGRAM,
) -> ChannelEvent:
""",
    """def _event(
    *,
    text: str,
    conversation_type: str = "private",
    channel: ChannelType = ChannelType.TELEGRAM,
    event_type: ChannelEventType | None = None,
    mentions: list[str] | None = None,
    scope_id: str | None = None,
) -> ChannelEvent:
""",
    label="dispatch event test options",
)
replace_once(
    TEST_DISPATCH,
    """        event_type=ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT,
""",
    """        event_type=event_type or (ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT),
""",
    label="dispatch event type override",
)
replace_once(
    TEST_DISPATCH,
    """            conversation_type=conversation_type,
        ),
""",
    """            conversation_type=conversation_type,
            metadata={"message_thread_id": scope_id} if scope_id else {},
        ),
""",
    label="dispatch scope metadata",
)
replace_once(
    TEST_DISPATCH,
    """            text=text,
        ),
""",
    """            text=text,
            mentions=mentions or [],
        ),
""",
    label="dispatch mentions fixture",
)
replace_once(
    TEST_DISPATCH,
    """def test_channel_session_id_is_stable_per_user_conversation() -> None:
    event = _event(text="hello")
    assert build_channel_session_id(event) == build_channel_session_id(event)
    assert build_channel_session_id(event).startswith("channel-")
""",
    """def test_channel_session_id_is_stable_per_user_conversation() -> None:
    event = _event(text="hello")
    assert build_channel_session_id(event) == build_channel_session_id(event)
    assert build_channel_session_id(event).startswith("channel-")


def test_channel_session_id_isolated_by_thread_scope() -> None:
    first = _event(text="hello", conversation_type="supergroup", scope_id="topic-1")
    second = _event(text="hello", conversation_type="supergroup", scope_id="topic-2")
    second.connection_id = first.connection_id
    assert build_channel_session_id(first) != build_channel_session_id(second)
""",
    label="thread session regression",
)
replace_once(
    TEST_DISPATCH,
    """def test_mentions_only_binding_filters_plain_group_text() -> None:
""",
    """def test_group_file_without_mention_is_filtered_by_default() -> None:
    event = _event(text="file", conversation_type="group", event_type=ChannelEventType.FILE)
    assert ChannelDispatchService._should_ignore_group_event(event, response_mode="mention_only") is True


def test_commands_only_ignores_mentions_but_all_messages_accepts_files() -> None:
    mentioned = _event(text="hello", conversation_type="group", mentions=["bot"])
    uploaded = _event(text="file", conversation_type="group", event_type=ChannelEventType.FILE)
    assert ChannelDispatchService._should_ignore_group_event(mentioned, response_mode="commands_only") is True
    assert ChannelDispatchService._should_ignore_group_event(uploaded, response_mode="all_messages") is False


def test_disabled_mode_ignores_group_actions_and_commands() -> None:
    action = _event(text="approve", conversation_type="group", event_type=ChannelEventType.ACTION)
    command = _event(text="/help", conversation_type="group")
    assert ChannelDispatchService._should_ignore_group_event(action, response_mode="disabled") is True
    assert ChannelDispatchService._should_ignore_group_event(command, command="/help", response_mode="disabled") is True


def test_mentions_only_binding_filters_plain_group_text() -> None:
""",
    label="group response mode regressions",
)
replace_once(
    TEST_DISPATCH,
    """async def test_non_feishu_workflow_returns_final_result_without_processing_message() -> None:
    event = _event(text="hello", channel=ChannelType.TELEGRAM)
    adapter = MockChannelAdapter(event.connection_id)
    service = _dispatch_service(adapter)

    response = await service._execute_workflow(
        event,
        SimpleNamespace(id=uuid4()),
        "flow-id",
        "hello",
        binding=None,
        trigger_type="default",
    )

    assert response == ChannelMessage(title="Workflow", markdown="final answer")
    assert adapter.sent_messages == []
    assert adapter.updated_messages == []
""",
    """async def test_telegram_workflow_updates_processing_placeholder() -> None:
    event = _event(text="hello", channel=ChannelType.TELEGRAM)

    class TelegramMockAdapter(MockChannelAdapter):
        channel_type = ChannelType.TELEGRAM

    adapter = TelegramMockAdapter(event.connection_id)
    service = _dispatch_service(adapter)

    response = await service._execute_workflow(
        event,
        SimpleNamespace(id=uuid4()),
        "flow-id",
        "hello",
        binding=None,
        trigger_type="default",
    )

    assert response is None
    assert adapter.sent_messages[0]["message"] == ChannelMessage(text="⏳ 正在处理中，请稍候…")
    assert adapter.updated_messages[0]["message"] == ChannelMessage(title="Workflow", markdown="final answer")
""",
    label="Telegram processing lifecycle",
)

TEST_QUEUE = "src/backend/tests/unit/channels/test_channel_queueing.py"
replace_once(
    TEST_QUEUE,
    """def _event(*, user_id: str, conversation_id: str = "chat-1", conversation_type: str = "group"):
""",
    """def _event(
    *,
    user_id: str,
    conversation_id: str = "chat-1",
    conversation_type: str = "group",
    scope_id: str | None = None,
):
""",
    label="queue scope fixture",
)
replace_once(
    TEST_QUEUE,
    """            metadata={},
        ),
""",
    """            metadata={"message_thread_id": scope_id} if scope_id else {},
        ),
""",
    label="queue topic metadata",
)
queue_scope_test = """

async def test_shared_group_topics_receive_distinct_fifo_keys() -> None:
    connection = SimpleNamespace(id=uuid4(), default_context_mode="shared")
    first = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="a", scope_id="1"))
    second = await resolve_channel_queue_descriptor(FakeSession(), connection, _event(user_id="b", scope_id="2"))
    assert first.queue_key != second.queue_key
    assert first.conversation_scope_id == "1"
    assert second.conversation_scope_id == "2"
"""
if "test_shared_group_topics_receive_distinct_fifo_keys" not in read(TEST_QUEUE):
    write(TEST_QUEUE, read(TEST_QUEUE) + queue_scope_test)

capability_tests = """from langflow.channels.services.capabilities import get_provider_capability, validate_provider_conversation_type
from langflow.channels.services.response_policy import normalize_response_mode


def test_provider_capability_matrix_matches_implemented_transports() -> None:
    telegram = get_provider_capability("telegram")
    dingtalk = get_provider_capability("dingtalk")
    wecom = get_provider_capability("wecom")
    assert telegram is not None and telegram.supports_message_update and telegram.supports_threads
    assert dingtalk is not None and dingtalk.supports_streaming_connection
    assert wecom is not None and wecom.conversation_types == ("private",)
    assert validate_provider_conversation_type("wecom", "group") is False


def test_legacy_mentions_only_normalizes_without_database_migration() -> None:
    assert normalize_response_mode("mentions_only") == "mention_only"
    assert normalize_response_mode("mention_only") == "mention_only"
    assert normalize_response_mode("invalid") == "mention_only"
"""
write("src/backend/tests/unit/channels/test_channel_capabilities_policy.py", capability_tests)

print("Applied provider capabilities, response modes, and conversation scopes")
