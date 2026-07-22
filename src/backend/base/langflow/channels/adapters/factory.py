"""Construct provider adapters from persisted channel connections."""

from __future__ import annotations

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.domain.models import ChannelType
from langflow.channels.security.credentials import decrypt_credentials
from langflow.services.database.models.channel.model import ChannelConnection


def build_channel_adapter(connection: ChannelConnection) -> ChannelAdapter:
    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)

    if channel_type is ChannelType.MOCK:
        return MockChannelAdapter(
            connection.id,
            verification_token=credentials.get("verification_token"),
        )

    msg = f"Channel adapter '{channel_type.value}' has not been implemented yet"
    raise NotImplementedError(msg)
