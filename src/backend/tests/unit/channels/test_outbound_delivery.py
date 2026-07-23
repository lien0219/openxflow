from uuid import uuid4

import pytest

from langflow.channels.domain.models import (
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelType,
    ChannelUser,
)
from langflow.channels.services import outbound_delivery
from langflow.channels.services.outbound_delivery import (
    OutboundDeliveryDecision,
    channel_response_digest,
    send_outbound_response_once,
)


def _event() -> ChannelEvent:
    connection_id = uuid4()
    return ChannelEvent(
        event_id="event-1",
        channel=ChannelType.TELEGRAM,
        connection_id=connection_id,
        event_type=ChannelEventType.TEXT,
        user=ChannelUser(external_user_id="user-1"),
        conversation=ChannelConversation(external_conversation_id="chat-1"),
        message=ChannelIncomingMessage(
            external_message_id="message-1",
            message_type=ChannelEventType.TEXT,
            text="hello",
        ),
    )


def test_channel_response_digest_is_stable_and_content_sensitive() -> None:
    first = ChannelMessage(title="Result", text="hello", metadata={"b": 2, "a": 1})
    same = ChannelMessage(metadata={"a": 1, "b": 2}, text="hello", title="Result")
    changed = ChannelMessage(title="Result", text="different", metadata={"a": 1, "b": 2})

    assert channel_response_digest(first) == channel_response_digest(same)
    assert channel_response_digest(first) != channel_response_digest(changed)
    assert len(channel_response_digest(first)) == 64


@pytest.mark.asyncio
async def test_send_outbound_response_once_marks_success(monkeypatch) -> None:
    delivery_id = uuid4()
    sent = []
    marked = []

    async def reserve(_event, _message):
        return OutboundDeliveryDecision(should_send=True, delivery_id=delivery_id)

    async def sender() -> str:
        sent.append(True)
        return "provider-message-1"

    async def mark_sent(actual_delivery_id, provider_message_id):
        marked.append((actual_delivery_id, provider_message_id))

    monkeypatch.setattr(outbound_delivery, "reserve_outbound_delivery", reserve)
    monkeypatch.setattr(outbound_delivery, "mark_outbound_delivery_sent", mark_sent)

    result = await send_outbound_response_once(_event(), ChannelMessage(text="world"), sender)

    assert result == "provider-message-1"
    assert sent == [True]
    assert marked == [(delivery_id, "provider-message-1")]


@pytest.mark.asyncio
async def test_send_outbound_response_once_skips_existing_reservation(monkeypatch) -> None:
    called = False

    async def reserve(_event, _message):
        return OutboundDeliveryDecision(should_send=False, delivery_id=uuid4())

    async def sender() -> str:
        nonlocal called
        called = True
        return "unexpected"

    monkeypatch.setattr(outbound_delivery, "reserve_outbound_delivery", reserve)

    result = await send_outbound_response_once(_event(), ChannelMessage(text="world"), sender)

    assert result is None
    assert called is False


@pytest.mark.asyncio
async def test_send_outbound_response_once_marks_known_failure(monkeypatch) -> None:
    delivery_id = uuid4()
    failures = []

    async def reserve(_event, _message):
        return OutboundDeliveryDecision(should_send=True, delivery_id=delivery_id)

    async def sender() -> str:
        raise RuntimeError("provider unavailable")

    async def mark_failed(actual_delivery_id, error):
        failures.append((actual_delivery_id, str(error)))

    monkeypatch.setattr(outbound_delivery, "reserve_outbound_delivery", reserve)
    monkeypatch.setattr(outbound_delivery, "mark_outbound_delivery_failed", mark_failed)

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await send_outbound_response_once(_event(), ChannelMessage(text="world"), sender)

    assert failures == [(delivery_id, "provider unavailable")]
