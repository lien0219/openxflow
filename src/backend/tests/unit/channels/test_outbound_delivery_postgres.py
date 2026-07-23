from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
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

pytestmark = pytest.mark.skipif(
    not os.getenv("LANGFLOW_CHANNEL_TEST_POSTGRES_DSN"),
    reason="LANGFLOW_CHANNEL_TEST_POSTGRES_DSN is not configured",
)


def _event(connection_id) -> ChannelEvent:
    return ChannelEvent(
        event_id="postgres-race-event",
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


@pytest.mark.asyncio
async def test_postgres_serializes_outbound_delivery_reservation_races(monkeypatch) -> None:
    dsn = os.environ["LANGFLOW_CHANNEL_TEST_POSTGRES_DSN"]
    schema = f"channel_test_{uuid4().hex}"
    engine = create_async_engine(
        dsn,
        execution_options={"schema_translate_map": {None: schema}},
    )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def test_session_scope():
        async with factory() as session:
            yield session

    connection_id = uuid4()
    quoted_schema = '"' + schema.replace('"', '""') + '"'
    try:
        async with engine.begin() as connection:
            await connection.execute(sa.text(f"CREATE SCHEMA {quoted_schema}"))
            await connection.execute(
                sa.text(
                    f"""
                    CREATE TABLE {quoted_schema}.channel_connection (
                        id UUID PRIMARY KEY
                    )
                    """
                )
            )
            await connection.execute(
                sa.text(
                    f"""
                    CREATE TABLE {quoted_schema}.channel_outbound_delivery (
                        id UUID PRIMARY KEY,
                        connection_id UUID NOT NULL REFERENCES {quoted_schema}.channel_connection(id) ON DELETE CASCADE,
                        external_event_id VARCHAR(255) NOT NULL,
                        delivery_kind VARCHAR(32) NOT NULL,
                        response_digest VARCHAR(64) NOT NULL,
                        status VARCHAR(32) NOT NULL,
                        attempts INTEGER NOT NULL,
                        provider_message_id VARCHAR(255),
                        last_error TEXT,
                        created_at TIMESTAMPTZ NOT NULL,
                        updated_at TIMESTAMPTZ NOT NULL,
                        sent_at TIMESTAMPTZ,
                        CONSTRAINT uq_channel_outbound_delivery_event_kind
                            UNIQUE (connection_id, external_event_id, delivery_kind)
                    )
                    """
                )
            )
            await connection.execute(
                sa.text(
                    f"INSERT INTO {quoted_schema}.channel_connection (id) VALUES (:id)"
                ),
                {"id": connection_id},
            )

        monkeypatch.setattr(outbound_delivery, "session_scope", test_session_scope)
        event = _event(connection_id)
        message = ChannelMessage(text="world")

        first_race = await asyncio.gather(
            outbound_delivery.reserve_outbound_delivery(event, message),
            outbound_delivery.reserve_outbound_delivery(event, message),
        )
        assert sorted(decision.should_send for decision in first_race) == [False, True]

        winner = next(decision for decision in first_race if decision.should_send)
        await outbound_delivery.mark_outbound_delivery_failed(
            winner.delivery_id,
            winner.delivery_kind,
            RuntimeError("provider unavailable"),
        )

        retry_race = await asyncio.gather(
            outbound_delivery.reserve_outbound_delivery(event, message),
            outbound_delivery.reserve_outbound_delivery(event, message),
        )
        assert sorted(decision.should_send for decision in retry_race) == [False, True]
    finally:
        async with engine.begin() as connection:
            await connection.execute(sa.text(f"DROP SCHEMA IF EXISTS {quoted_schema} CASCADE"))
        await engine.dispose()
