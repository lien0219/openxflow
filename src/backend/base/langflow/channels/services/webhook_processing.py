"""Background processing for provider webhooks after a fast acknowledgement."""

from __future__ import annotations

from uuid import UUID

from lfx.log.logger import logger

from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.services.deduplication import ChannelEventDeduplicator
from langflow.channels.services.dispatch import ChannelDispatchService
from langflow.channels.services.gateway import ChannelGateway
from langflow.services.database.models.channel.model import ChannelConnection
from langflow.services.deps import session_scope


async def process_provider_webhook(
    *,
    connection_id: UUID,
    expected_channel_type: str,
    headers: dict[str, str],
    payload: bytes,
) -> None:
    """Process one already-validated provider callback in an isolated DB session."""
    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)
        if connection is None or connection.channel_type != expected_channel_type or not connection.enabled:
            await logger.awarning(
                "Skipping channel webhook for missing or disabled connection %s",
                connection_id,
            )
            return

        adapter = build_channel_adapter(connection)
        gateway = ChannelGateway()
        gateway.register_adapter(connection_id, adapter)
        deduplicator = ChannelEventDeduplicator(session)
        dispatcher = ChannelDispatchService(session, connection, adapter)

        try:
            await gateway.receive(
                connection_id,
                headers,
                payload,
                dispatcher.handle,
                deduplicator=deduplicator,
            )
        except DuplicateChannelEventError:
            await session.rollback()
            await logger.adebug(
                "Ignored duplicate %s channel webhook for connection %s",
                expected_channel_type,
                connection_id,
            )
            return
        except Exception:  # noqa: BLE001
            await session.rollback()
            await logger.aexception(
                "Background %s channel webhook processing failed for connection %s",
                expected_channel_type,
                connection_id,
            )
            return

        await session.commit()
