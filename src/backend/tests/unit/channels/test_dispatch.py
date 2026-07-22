from uuid import uuid4

from langflow.channels.domain.models import (
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelType,
    ChannelUser,
)
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.workflow import build_channel_session_id
from langflow.services.database.models.channel.model import ChannelConversationBinding


def _event(*, text: str, conversation_type: str = "private") -> ChannelEvent:
    return ChannelEvent(
        event_id="1",
        channel=ChannelType.TELEGRAM,
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
