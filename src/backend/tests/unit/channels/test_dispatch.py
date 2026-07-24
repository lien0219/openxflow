from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.domain.models import (
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelMessageType,
    ChannelType,
    ChannelUser,
)
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.workflow import build_channel_session_id
from langflow.services.database.models.channel.model import ChannelConversationBinding


class FeishuMockAdapter(MockChannelAdapter):
    channel_type = ChannelType.FEISHU


class FakeWorkflowExecutor:
    async def execute(self, **kwargs) -> ChannelMessage:
        del kwargs
        return ChannelMessage(title="Workflow", markdown="final answer")


def _event(
    *,
    text: str,
    conversation_type: str = "private",
    channel: ChannelType = ChannelType.TELEGRAM,
) -> ChannelEvent:
    return ChannelEvent(
        event_id="1",
        channel=channel,
        connection_id=uuid4(),
        event_type=ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT,
        user=ChannelUser(external_user_id="42"),
        conversation=ChannelConversation(
            external_conversation_id="100",
            conversation_type=conversation_type,
        ),
        message=ChannelIncomingMessage(
            external_message_id="2",
            message_type=ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT,
            text=text,
        ),
    )


def _dispatch_service(adapter: MockChannelAdapter) -> ChannelDispatchService:
    service = object.__new__(ChannelDispatchService)
    service.session = None
    service.connection = SimpleNamespace(
        id=adapter.connection_id,
        channel_type=adapter.channel_type.value,
        default_knowledge_base_id=None,
    )
    service.adapter = adapter
    service.workflow_executor = FakeWorkflowExecutor()
    return service


def test_command_parser_strips_telegram_bot_suffix() -> None:
    command, argument = ChannelDispatchService._parse_command("/flow@openxflow_bot abc hello")
    assert command == "/flow"
    assert argument == "abc hello"


def test_channel_session_id_is_stable_per_user_conversation() -> None:
    event = _event(text="hello")
    assert build_channel_session_id(event) == build_channel_session_id(event)
    assert build_channel_session_id(event).startswith("channel-")


def test_plain_group_message_without_mention_is_ignored_by_default() -> None:
    event = _event(text="hello", conversation_type="group")
    assert ChannelDispatchService._should_ignore_group_event(event) is True


def test_group_command_is_never_filtered() -> None:
    event = _event(text="/help", conversation_type="group")
    command, _ = ChannelDispatchService._parse_command(event.message.text)
    assert ChannelDispatchService._should_ignore_group_event(event, command=command) is False


def test_all_messages_binding_accepts_plain_group_text() -> None:
    event = _event(text="hello", conversation_type="group")
    binding = ChannelConversationBinding(
        connection_id=event.connection_id,
        external_conversation_id=event.conversation.external_conversation_id,
        conversation_type="group",
        response_mode="all_messages",
    )
    assert ChannelDispatchService._should_ignore_group_event(event, binding=binding) is False


def test_mentions_only_binding_filters_plain_group_text() -> None:
    event = _event(text="hello", conversation_type="group")
    binding = ChannelConversationBinding(
        connection_id=event.connection_id,
        external_conversation_id=event.conversation.external_conversation_id,
        conversation_type="group",
        response_mode="mentions_only",
    )
    assert ChannelDispatchService._should_ignore_group_event(event, binding=binding) is True


async def test_feishu_workflow_replaces_processing_message_with_final_result() -> None:
    event = _event(text="hello", channel=ChannelType.FEISHU)
    adapter = FeishuMockAdapter(event.connection_id)
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
    assert adapter.sent_messages == [
        {
            "external_message_id": "mock-1",
            "target_id": "100",
            "message": ChannelMessage(
                message_type=ChannelMessageType.CARD,
                text="⏳ 正在处理中，请稍候…",
                metadata={"feishu_update_multi": True},
            ),
        }
    ]
    assert adapter.updated_messages == [
        {
            "external_message_id": "mock-1",
            "message": ChannelMessage(title="Workflow", markdown="final answer"),
        }
    ]


async def test_non_feishu_workflow_returns_final_result_without_processing_message() -> None:
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


def test_help_message_exposes_interactive_actions() -> None:
    message = ChannelDispatchService._help_message(bound=True)

    assert message.message_type == ChannelMessageType.CARD
    assert [action.value for action in message.actions] == ["/bind", "/commands"]
