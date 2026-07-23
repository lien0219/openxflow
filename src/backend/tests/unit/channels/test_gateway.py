import json
from uuid import uuid4

import pytest
from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.domain.models import ChannelMessage
from langflow.channels.services import gateway as gateway_module
from langflow.channels.services.gateway import ChannelGateway


class AckRequiredMockAdapter(MockChannelAdapter):
    def __init__(self, *args, order=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order if order is not None else []

    def requires_event_acknowledgement(self, event) -> bool:
        del event
        return True

    async def acknowledge_event(self, event) -> None:
        self.order.append(("provider_ack", event.event_id))


class FakeDeduplicator:
    def __init__(self, *, duplicate: bool = False) -> None:
        self.duplicate = duplicate
        self.completed = False
        self.failed = False
        self.receipt = object()

    async def claim(self, event, payload):
        del event, payload
        return None if self.duplicate else self.receipt

    async def complete(self, receipt):
        assert receipt is self.receipt
        self.completed = True

    async def fail(self, receipt, error):
        assert receipt is self.receipt
        assert isinstance(error, RuntimeError)
        self.failed = True


async def test_gateway_receives_normalized_event_and_replies():
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)
    deduplicator = FakeDeduplicator()

    async def handler(event):
        assert event.message.text == "hello"
        return ChannelMessage(text="world")

    payload = json.dumps({"event_id": "event-1", "text": "hello"}).encode()
    event = await gateway.receive(
        connection_id,
        {"x-openxflow-mock-token": "secret"},
        payload,
        handler,
        deduplicator=deduplicator,
    )

    assert event.event_id == "event-1"
    assert deduplicator.completed is True
    assert adapter.sent_messages[0]["message"].text == "world"


async def test_gateway_rejects_invalid_signature():
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)

    async def handler(event):
        del event

    with pytest.raises(PermissionError):
        await gateway.receive(connection_id, {}, b"{}", handler)


async def test_preverified_normal_message_skips_acknowledgement_guard(monkeypatch):
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)
    guarded = False

    async def guard_ack(event, sender):
        del event, sender
        nonlocal guarded
        guarded = True
        return True

    async def handler(event):
        del event

    monkeypatch.setattr(gateway_module, "send_outbound_acknowledgement_once", guard_ack)
    event = await gateway.receive_verified(
        connection_id,
        b'{"event_id":"event-preverified","text":"hello"}',
        handler,
    )

    assert event.event_id == "event-preverified"
    assert guarded is False


async def test_preverified_gateway_guards_required_acknowledgement_before_response(monkeypatch):
    connection_id = uuid4()
    order = []
    adapter = AckRequiredMockAdapter(
        connection_id,
        verification_token="secret",
        order=order,
    )
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)

    async def guard_ack(event, sender):
        order.append(("ack_guard", event.event_id))
        await sender()
        return True

    async def guard_response(event, message, sender):
        order.append(("response_guard", event.event_id, message.text))
        return await sender()

    async def handler(event):
        order.append(("handler", event.event_id))
        return ChannelMessage(text="guarded response")

    monkeypatch.setattr(gateway_module, "send_outbound_acknowledgement_once", guard_ack)
    monkeypatch.setattr(gateway_module, "send_outbound_response_once", guard_response)

    await gateway.receive_verified(
        connection_id,
        b'{"event_id":"event-guarded","text":"hello"}',
        handler,
    )

    assert order == [
        ("ack_guard", "event-guarded"),
        ("provider_ack", "event-guarded"),
        ("handler", "event-guarded"),
        ("response_guard", "event-guarded", "guarded response"),
    ]
    assert len(adapter.sent_messages) == 1


@pytest.mark.parametrize("extra_header", [None, "authorization", "cookie", "x-forwarded-for"])
async def test_gateway_never_trusts_preverified_marker_on_normal_receive(extra_header: str | None):
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)

    async def handler(event):
        del event

    headers = {"x-openxflow-preverified": "1"}
    if extra_header is not None:
        headers[extra_header] = "sensitive"
    with pytest.raises(PermissionError):
        await gateway.receive(
            connection_id,
            headers,
            b'{"event_id":"event-preverified"}',
            handler,
        )


async def test_gateway_rejects_duplicate_event():
    connection_id = uuid4()
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, MockChannelAdapter(connection_id))

    async def handler(event):
        del event

    with pytest.raises(DuplicateChannelEventError):
        await gateway.receive(
            connection_id,
            {},
            b'{"event_id":"event-1"}',
            handler,
            deduplicator=FakeDeduplicator(duplicate=True),
        )


async def test_gateway_marks_failed_event():
    connection_id = uuid4()
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, MockChannelAdapter(connection_id))
    deduplicator = FakeDeduplicator()

    async def handler(event):
        del event
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await gateway.receive(
            connection_id,
            {},
            b'{"event_id":"event-1"}',
            handler,
            deduplicator=deduplicator,
        )

    assert deduplicator.failed is True
