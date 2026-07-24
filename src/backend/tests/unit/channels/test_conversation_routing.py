from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from langflow.services.database.models.channel.crud import (
    _derive_conversation_status,
    delete_legacy_channel_conversation_binding,
)
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelConversationRouteMode,
    ChannelConversationSource,
    ChannelConversationStatus,
)


def _connection(*, default_flow: bool) -> ChannelConnection:
    return ChannelConnection(
        user_id=uuid4(),
        name="test",
        channel_type="feishu",
        credentials_encrypted="encrypted",
        default_flow_id=uuid4() if default_flow else None,
    )


def _binding(*, route_mode: str, default_flow: bool = False) -> ChannelConversationBinding:
    return ChannelConversationBinding(
        connection_id=uuid4(),
        external_conversation_id="conversation",
        conversation_type="private",
        route_mode=route_mode,
        default_flow_id=uuid4() if default_flow else None,
    )


def test_inherited_conversation_uses_connection_default_state() -> None:
    binding = _binding(route_mode=ChannelConversationRouteMode.INHERIT.value)

    assert (
        _derive_conversation_status(_connection(default_flow=True), binding)
        == ChannelConversationStatus.INHERITED.value
    )
    assert (
        _derive_conversation_status(_connection(default_flow=False), binding) == ChannelConversationStatus.PENDING.value
    )


def test_overridden_conversation_requires_own_workflow() -> None:
    binding = _binding(
        route_mode=ChannelConversationRouteMode.OVERRIDE.value,
        default_flow=True,
    )

    assert (
        _derive_conversation_status(_connection(default_flow=False), binding)
        == ChannelConversationStatus.OVERRIDDEN.value
    )


def test_disabled_and_ignored_states_take_precedence() -> None:
    disabled = _binding(route_mode=ChannelConversationRouteMode.DISABLED.value)
    ignored = _binding(route_mode=ChannelConversationRouteMode.INHERIT.value)
    ignored.status = ChannelConversationStatus.IGNORED.value

    assert (
        _derive_conversation_status(_connection(default_flow=True), disabled)
        == ChannelConversationStatus.DISABLED.value
    )
    assert (
        _derive_conversation_status(_connection(default_flow=True), ignored) == ChannelConversationStatus.IGNORED.value
    )

@pytest.mark.asyncio
async def test_legacy_manual_conversation_can_be_deleted() -> None:
    binding = _binding(route_mode=ChannelConversationRouteMode.OVERRIDE.value)
    binding.source = ChannelConversationSource.LEGACY_MANUAL.value
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = binding
    session.exec.return_value = result

    deleted = await delete_legacy_channel_conversation_binding(session, binding.connection_id, binding.id)

    assert deleted is True
    session.delete.assert_awaited_once_with(binding)
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_discovered_conversation_cannot_be_deleted() -> None:
    binding = _binding(route_mode=ChannelConversationRouteMode.INHERIT.value)
    binding.source = ChannelConversationSource.AUTO_DISCOVERED.value
    session = AsyncMock()
    result = MagicMock()
    result.first.return_value = binding
    session.exec.return_value = result

    with pytest.raises(ValueError, match="Only legacy manual"):
        await delete_legacy_channel_conversation_binding(session, binding.connection_id, binding.id)

    session.delete.assert_not_awaited()
