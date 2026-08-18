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


def _event(event_type: ChannelEventType) -> ChannelEvent:
    return ChannelEvent(
        event_id="event-1",
        channel=ChannelType.FEISHU,
        connection_id=uuid4(),
        event_type=event_type,
        user=ChannelUser(external_user_id="ou_user"),
        conversation=ChannelConversation(
            external_conversation_id="oc_chat",
            conversation_type="group",
        ),
        message=ChannelIncomingMessage(
            external_message_id="om_card",
            message_type=event_type,
            text="/use-flow /deepseek" if event_type == ChannelEventType.ACTION else "hello",
        ),
    )


def test_interactive_action_is_explicitly_targeted_to_the_bot() -> None:
    event = _event(ChannelEventType.ACTION)
    command, _ = ChannelDispatchService._parse_command(event.message.text)
    targeted = ChannelDispatchService._command_targets_bot(event)

    assert event.message.mentions == ["__openxflow_interactive_action__"]
    assert targeted is True
    assert (
        ChannelDispatchService._should_ignore_group_event(
            event,
            command=command,
            response_mode="mention_only",
            require_command_mention=True,
            command_targeted=targeted,
        )
        is False
    )


def test_plain_text_event_does_not_gain_a_synthetic_mention() -> None:
    event = _event(ChannelEventType.TEXT)

    assert event.message.mentions == []
