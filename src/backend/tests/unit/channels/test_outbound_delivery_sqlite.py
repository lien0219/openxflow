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
    ChannelOutboundDeliveryStatus,
)

_CREATE_TABLE = """
CREATE TABLE channel_outbound_delivery (
    id CHAR(32) NOT NULL PRIMARY KEY,
    connection_id CHAR(32) NOT NULL,
    external_event_id VARCHAR(255) NOT NULL,
    response_digest VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempts INTEGER NOT NULL,
    provider_message_id VARCHAR(255),
    last_error TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    sent_at DATETIME,
    CONSTRAINT uq_channel_outbound_delivery_event UNIQUE (connection_id, external_event_id)
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


async def test_outbound_delivery_receipt_prevents_duplicate_send_and_allows_known_failure_retry(
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
        first = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert first.should_send is True
        assert first.delivery_id is not None

        duplicate_reserved = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert duplicate_reserved.should_send is False
        assert duplicate_reserved.delivery_id == first.delivery_id

        await outbound_delivery.mark_outbound_delivery_failed(
            first.delivery_id,
            RuntimeError("provider unavailable"),
        )
        retry = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert retry.should_send is True
        assert retry.delivery_id == first.delivery_id

        await outbound_delivery.mark_outbound_delivery_sent(retry.delivery_id, "provider-message-1")
        duplicate_sent = await outbound_delivery.reserve_outbound_delivery(event, message)
        assert duplicate_sent.should_send is False

        async with factory() as session:
            receipt = (await session.exec(select(ChannelOutboundDelivery))).one()
        assert receipt.status == ChannelOutboundDeliveryStatus.SENT.value
        assert receipt.attempts == 2
        assert receipt.provider_message_id == "provider-message-1"
        assert receipt.sent_at is not None
        assert receipt.last_error is None
    finally:
        await engine.dispose()
