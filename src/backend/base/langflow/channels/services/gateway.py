from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING
from uuid import UUID

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.exceptions import DuplicateChannelEventError
from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelType
from langflow.channels.services.execution_logs import safe_record_channel_delivery_outcome
from langflow.channels.services.message_planning import plan_channel_messages
from langflow.channels.services.message_records import (
    safe_mark_inbound_message,
    safe_record_inbound_message,
    safe_record_outbound_message,
)
from langflow.channels.services.outbound_delivery import (
    send_outbound_acknowledgement_once,
    send_outbound_response_once,
)
from langflow.channels.services.retry import retry_channel_operation
from langflow.services.database.models.channel.message_model import ChannelMessageRecordStatus

if TYPE_CHECKING:
    from langflow.channels.services.deduplication import ChannelEventDeduplicator

ChannelHandler = Callable[[ChannelEvent], Awaitable[ChannelMessage | None]]


class ChannelGateway:
    """Coordinates provider adapters and dispatches normalized events."""

    def __init__(self) -> None:
        self._adapters: dict[UUID, ChannelAdapter] = {}

    def register_adapter(self, connection_id: UUID, adapter: ChannelAdapter) -> None:
        self._adapters[connection_id] = adapter

    def unregister_adapter(self, connection_id: UUID) -> None:
        self._adapters.pop(connection_id, None)

    def get_adapter(self, connection_id: UUID) -> ChannelAdapter:
        try:
            return self._adapters[connection_id]
        except KeyError as exc:
            raise LookupError(f"Channel connection '{connection_id}' is not registered") from exc

    def list_connections(self) -> list[dict[str, str]]:
        return [
            {"connection_id": str(connection_id), "channel": adapter.channel_type.value}
            for connection_id, adapter in self._adapters.items()
        ]

    async def receive(
        self,
        connection_id: UUID,
        headers: dict[str, str],
        payload: bytes,
        handler: ChannelHandler,
        *,
        deduplicator: ChannelEventDeduplicator | None = None,
    ) -> ChannelEvent:
        adapter = self.get_adapter(connection_id)
        if not await adapter.verify_event(headers, payload):
            raise PermissionError("Channel event signature verification failed")
        return await self._receive_parsed(
            connection_id,
            headers,
            payload,
            handler,
            deduplicator=deduplicator,
            guard_outbound=False,
        )

    async def receive_verified(
        self,
        connection_id: UUID,
        payload: bytes,
        handler: ChannelHandler,
        *,
        deduplicator: ChannelEventDeduplicator | None = None,
    ) -> ChannelEvent:
        """Process a callback verified before durable persistence with guarded deliveries."""
        return await self._receive_parsed(
            connection_id,
            {},
            payload,
            handler,
            deduplicator=deduplicator,
            guard_outbound=True,
        )

    async def _receive_parsed(
        self,
        connection_id: UUID,
        headers: dict[str, str],
        payload: bytes,
        handler: ChannelHandler,
        *,
        deduplicator: ChannelEventDeduplicator | None,
        guard_outbound: bool,
    ) -> ChannelEvent:
        adapter = self.get_adapter(connection_id)
        event = await adapter.parse_event(headers, payload)
        if event.connection_id != connection_id:
            raise ValueError("Parsed channel event belongs to another connection")
        if event.channel != adapter.channel_type:
            raise ValueError("Parsed channel event has an unexpected channel type")

        receipt = None
        if deduplicator is not None:
            receipt = await deduplicator.claim(event, payload)
            if receipt is None:
                raise DuplicateChannelEventError(event.event_id)

        await safe_record_inbound_message(event)
        try:
            if adapter.requires_event_acknowledgement(event):

                async def acknowledgement_sender() -> None:
                    await adapter.acknowledge_event(event)

                if guard_outbound:
                    await send_outbound_acknowledgement_once(event, acknowledgement_sender)
                else:
                    await acknowledgement_sender()

            response = await handler(event)
            if response is not None:
                delivery_started = time.perf_counter()
                try:
                    provider_message_id = await self._send_planned_response(
                        adapter,
                        event,
                        response,
                        guard_outbound=guard_outbound,
                    )
                except Exception as delivery_error:
                    duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))
                    await safe_record_outbound_message(
                        event,
                        response,
                        status=ChannelMessageRecordStatus.FAILED.value,
                        error=delivery_error,
                    )
                    await safe_record_channel_delivery_outcome(
                        connection_id=event.connection_id,
                        external_event_id=event.event_id,
                        duration_ms=duration_ms,
                        error=delivery_error,
                    )
                    raise
                else:
                    duration_ms = max(0, int((time.perf_counter() - delivery_started) * 1000))
                    await safe_record_outbound_message(
                        event,
                        response,
                        status=ChannelMessageRecordStatus.SENT.value,
                        provider_message_id=provider_message_id,
                    )
                    await safe_record_channel_delivery_outcome(
                        connection_id=event.connection_id,
                        external_event_id=event.event_id,
                        duration_ms=duration_ms,
                    )
        except Exception as exc:
            await safe_mark_inbound_message(
                event,
                status=ChannelMessageRecordStatus.FAILED.value,
                error=exc,
            )
            if deduplicator is not None and receipt is not None:
                await deduplicator.fail(receipt, exc)
            raise
        else:
            await safe_mark_inbound_message(
                event,
                status=ChannelMessageRecordStatus.PROCESSED.value,
            )
            if deduplicator is not None and receipt is not None:
                await deduplicator.complete(receipt)
        return event

    @staticmethod
    async def _send_planned_response(
        adapter: ChannelAdapter,
        event: ChannelEvent,
        message: ChannelMessage,
        *,
        guard_outbound: bool = False,
    ) -> str:
        planned = plan_channel_messages(adapter.channel_type.value, message)
        provider_message_id = ""
        total = len(planned)
        for index, part in enumerate(planned, start=1):

            async def send_part(part: ChannelMessage = part, index: int = index) -> str:
                return await retry_channel_operation(
                    lambda: adapter.send_response(event, part),
                    operation_name=f"{adapter.channel_type.value}.send_response.part_{index}",
                )

            if guard_outbound:
                result = await send_outbound_response_once(
                    event,
                    part,
                    send_part,
                    delivery_key=f"part:{index}:{total}",
                )
                if result:
                    provider_message_id = result
            else:
                provider_message_id = await send_part()
        return provider_message_id

    @staticmethod
    async def _send_planned_message(
        adapter: ChannelAdapter,
        target_id: str,
        message: ChannelMessage,
    ) -> str:
        planned = plan_channel_messages(adapter.channel_type.value, message)
        provider_message_id = ""
        for index, part in enumerate(planned, start=1):
            provider_message_id = await retry_channel_operation(
                lambda part=part: adapter.send_message(target_id, part),
                operation_name=f"{adapter.channel_type.value}.send_message.part_{index}",
            )
        return provider_message_id

    async def send(self, connection_id: UUID, target_id: str, message: ChannelMessage) -> str:
        adapter = self.get_adapter(connection_id)
        return await self._send_planned_message(adapter, target_id, message)

    async def healthcheck(self, connection_id: UUID) -> dict:
        adapter = self.get_adapter(connection_id)
        return await retry_channel_operation(
            adapter.healthcheck,
            operation_name=f"{adapter.channel_type.value}.healthcheck",
        )

    def has_channel_type(self, channel_type: ChannelType) -> bool:
        return any(adapter.channel_type == channel_type for adapter in self._adapters.values())
