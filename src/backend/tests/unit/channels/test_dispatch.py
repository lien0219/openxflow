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


def test_plain_group_message_without_mention_is_ignored() -> None:
    event = _event(text="hello", conversation_type="group")
    assert ChannelDispatchService._should_ignore_group_event(event) is True
