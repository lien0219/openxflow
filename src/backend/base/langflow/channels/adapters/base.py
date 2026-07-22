from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelType


class ChannelAdapter(ABC):
    """Provider-neutral contract implemented by each chat platform."""

    channel_type: ChannelType

    @abstractmethod
    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        """Verify that an inbound event was sent by the configured provider."""

    @abstractmethod
    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        """Convert a provider payload into the unified channel event model."""

    @abstractmethod
    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        """Send a message and return the provider message identifier."""

    async def acknowledge_event(self, event: ChannelEvent) -> None:
        """Acknowledge provider-specific interactive events when required."""

    async def update_message(self, external_message_id: str, message: ChannelMessage) -> None:
        raise NotImplementedError(f"{self.channel_type} does not support message updates")

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        raise NotImplementedError(f"{self.channel_type} does not support file downloads")

    async def healthcheck(self) -> dict[str, Any]:
        return {"ok": True, "channel": self.channel_type.value}
