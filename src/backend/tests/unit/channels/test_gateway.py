import json
from uuid import uuid4

import pytest

from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.domain.models import ChannelMessage
from langflow.channels.services.gateway import ChannelGateway


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
        return None

    with pytest.raises(PermissionError):
        await gateway.receive(connection_id, {}, b"{}", handler)


async def test_gateway_accepts_minimal_internal_preverified_headers():
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)

    async def handler(event):
        return None

    event = await gateway.receive(
        connection_id,
        {
            "x-openxflow-preverified": "1",
            "content-type": "application/json",
        },
        b'{"event_id":"event-preverified","text":"hello"}',
        handler,
    )

    assert event.event_id == "event-preverified"


@pytest.mark.parametrize("extra_header", ["authorization", "cookie", "x-forwarded-for"])
async def test_gateway_rejects_preverified_marker_with_unapproved_headers(extra_header: str):
    connection_id = uuid4()
    adapter = MockChannelAdapter(connection_id, verification_token="secret")
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, adapter)

    async def handler(event):
        del event
        return None

    with pytest.raises(PermissionError):
        await gateway.receive(
            connection_id,
            {
                "x-openxflow-preverified": "1",
                extra_header: "sensitive",
            },
            b'{"event_id":"event-preverified"}',
            handler,
        )


async def test_gateway_rejects_duplicate_event():
    connection_id = uuid4()
    gateway = ChannelGateway()
    gateway.register_adapter(connection_id, MockChannelAdapter(connection_id))

    async def handler(event):
        del event
        return None

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
