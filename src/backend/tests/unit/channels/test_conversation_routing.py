from __future__ import annotations

from uuid import uuid4

from langflow.services.database.models.channel.crud import _derive_conversation_status
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelConversationRouteMode,
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
        _derive_conversation_status(_connection(default_flow=False), binding)
        == ChannelConversationStatus.PENDING.value
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
        _derive_conversation_status(_connection(default_flow=True), ignored)
        == ChannelConversationStatus.IGNORED.value
    )
