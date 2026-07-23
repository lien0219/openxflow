from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

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
from langflow.services.database.models.channel.outbound_delivery_model import (
    ChannelOutboundDelivery,
    ChannelOutboundDeliveryKind,
    ChannelOutboundDeliveryStatus,
)

_CREATE_TABLE = """
CREATE TABLE channel_outbound_delivery (
    id CHAR(32) NOT NULL PRIMARY KEY,
    connection_id CHAR(32) NOT NULL,
    external_event_id VARCHAR(255) NOT NULL,
    delivery_kind VARCHAR(32) NOT NULL,
    response_digest VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL,
    provider_message_id VARCHAR(255),
    last_error TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    sent_at DATETIME,
    CONSTRAINT uq_channel_outbound_delivery_event_kind
        UNIQUE (connection_id, external_event_id, delivery_kind)
)
"""


def _event(connection_id) -> ChannelEvent:
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


async def test_outbound_delivery_receipts_separate_acknowledgement_and_response(
    monkeypatch,
    tmp_path,
) -> None:
    database_path = tmp_path / "outbound-delivery.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.execute(sa.text(_CREATE_TABLE))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def test_session_scope():
        async with factory() as session:
            yield session

    monkeypatch.setattr(outbound_delivery, "session_scope", test_session_scope)
    connection_id = uuid4()
    event = _event(connection_id)
    message = ChannelMessage(text="world")

    try:
        acknowledgement = await outbound_delivery.reserve_outbound_acknowledgement(event)
        response = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert acknowledgement.should_send is True
        assert response.should_send is True
        assert acknowledgement.delivery_id != response.delivery_id

        duplicate_ack = await outbound_delivery.reserve_outbound_acknowledgement(event)
        duplicate_response = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert duplicate_ack.should_send is False
        assert duplicate_response.should_send is False

        await outbound_delivery.mark_outbound_delivery_sent(acknowledgement.delivery_id, None)
        await outbound_delivery.mark_outbound_delivery_failed(
            response.delivery_id,
            RuntimeError("provider unavailable"),
        )
        retry = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert retry.should_send is True
        assert retry.delivery_id == response.delivery_id
        await outbound_delivery.mark_outbound_delivery_sent(retry.delivery_id, "provider-message-1")

        async with factory() as session:
            receipts = list((await session.exec(select(ChannelOutboundDelivery))).all())
        assert len(receipts) == 2
        by_kind = {receipt.delivery_kind: receipt for receipt in receipts}

        ack_receipt = by_kind[ChannelOutboundDeliveryKind.ACKNOWLEDGEMENT.value]
        assert ack_receipt.status == ChannelOutboundDeliveryStatus.SENT.value
        assert ack_receipt.attempts == 1
        assert ack_receipt.provider_message_id is None

        response_receipt = by_kind[ChannelOutboundDeliveryKind.RESPONSE.value]
        assert response_receipt.status == ChannelOutboundDeliveryStatus.SENT.value
        assert response_receipt.attempts == 2
        assert response_receipt.provider_message_id == "provider-message-1"
        assert response_receipt.sent_at is not None
        assert response_receipt.last_error is None
    finally:
        await engine.dispose()
