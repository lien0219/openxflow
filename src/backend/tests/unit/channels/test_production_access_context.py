from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    effective_access_policy,
    effective_context_mode,
)
from langflow.channels.services.workflow import build_channel_session_id
from langflow.services.database.models.channel.model import (
    ChannelAccessPolicy,
    ChannelContextMode,
)


def _event(*, user_id: str = "user-1", conversation_type: str = "group"):
    return SimpleNamespace(
        channel=SimpleNamespace(value="feishu"),
        connection_id=uuid4(),
        conversation=SimpleNamespace(
            external_conversation_id="chat-1",
            conversation_type=conversation_type,
        ),
        user=SimpleNamespace(external_user_id=user_id),
    )


def test_effective_policy_and_context_inherit_from_connection() -> None:
    connection = SimpleNamespace(
        access_policy=ChannelAccessPolicy.HYBRID.value,
        default_context_mode=ChannelContextMode.ISOLATED.value,
    )
    binding = SimpleNamespace(
        access_policy=ChannelAccessPolicy.INHERIT.value,
        context_mode=ChannelContextMode.INHERIT.value,
    )
    assert effective_access_policy(connection, binding) == "hybrid"
    assert effective_context_mode(connection, binding) == "isolated"


def test_shared_group_session_is_common_but_isolated_session_is_per_user() -> None:
    first = _event(user_id="user-1")
    second = SimpleNamespace(**first.__dict__)
    second.user = SimpleNamespace(external_user_id="user-2")
    assert build_channel_session_id(first, "shared") == build_channel_session_id(second, "shared")
    assert build_channel_session_id(first, "isolated") != build_channel_session_id(second, "isolated")


def test_private_sessions_remain_user_scoped_in_shared_mode() -> None:
    first = _event(user_id="user-1", conversation_type="private")
    second = _event(user_id="user-2", conversation_type="private")
    second.connection_id = first.connection_id
    assert build_channel_session_id(first, "shared") != build_channel_session_id(second, "shared")


def test_binding_required_error_is_permission_error() -> None:
    assert issubclass(ChannelBindingRequiredError, PermissionError)
