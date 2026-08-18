from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.services.service_identity import (
    is_managed_channel_service_user,
    managed_service_username,
)


def test_managed_service_username_is_deterministic_and_isolated() -> None:
    first = uuid4()
    second = uuid4()
    assert managed_service_username(first) == managed_service_username(first)
    assert managed_service_username(first) != managed_service_username(second)
    assert managed_service_username(first).endswith("@openxflow.internal")


def test_service_identity_marker_is_connection_scoped() -> None:
    connection_id = uuid4()
    user = SimpleNamespace(
        optins={
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        }
    )
    assert is_managed_channel_service_user(user, connection_id)
    assert not is_managed_channel_service_user(user, uuid4())
    assert not is_managed_channel_service_user(SimpleNamespace(optins=None), connection_id)
