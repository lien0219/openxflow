from types import SimpleNamespace
from uuid import uuid4

import pytest
from langflow.channels.services.access_control import (
    ChannelBindingRequiredError,
    ChannelServiceIdentityUnavailableError,
    resolve_execution_principal,
)
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType


class FakeSession:
    def __init__(self, users):
        self.users = users

    async def get(self, _model, user_id):
        return self.users.get(user_id)


def _user(user_id, *, active=True, connection_id=None):
    optins = {}
    if connection_id is not None:
        optins = {
            "channel_service_identity": True,
            "channel_connection_id": str(connection_id),
        }
    return SimpleNamespace(id=user_id, is_active=active, optins=optins)


def _identity(user_id=None):
    return SimpleNamespace(
        status="bound" if user_id else "discovered",
        openxflow_user_id=user_id,
    )


async def test_shared_route_requires_explicit_service_identity() -> None:
    owner_id = uuid4()
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=owner_id,
        service_user_id=None,
        access_policy="hybrid",
    )
    with pytest.raises(ChannelServiceIdentityUnavailableError):
        await resolve_execution_principal(FakeSession({owner_id: _user(owner_id)}), connection, None, None)


async def test_bound_only_gates_member_but_shared_route_uses_service_identity() -> None:
    service_id = uuid4()
    member_id = uuid4()
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="bound_only",
    )
    users = {service_id: _user(service_id, connection_id=connection.id), member_id: _user(member_id)}
    principal = await resolve_execution_principal(
        FakeSession(users),
        connection,
        None,
        _identity(member_id),
    )
    assert principal.user.id == service_id
    assert principal.identity_type == ChannelExecutionIdentityType.SERVICE.value


async def test_bound_only_rejects_unbound_member_before_shared_execution() -> None:
    service_id = uuid4()
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="bound_only",
    )
    with pytest.raises(ChannelBindingRequiredError):
        await resolve_execution_principal(
            FakeSession({service_id: _user(service_id)}),
            connection,
            None,
            _identity(),
        )


async def test_hybrid_personal_route_uses_bound_member_identity() -> None:
    service_id = uuid4()
    member_id = uuid4()
    connection = SimpleNamespace(
        id=uuid4(),
        user_id=uuid4(),
        service_user_id=service_id,
        access_policy="hybrid",
    )
    users = {service_id: _user(service_id), member_id: _user(member_id)}
    principal = await resolve_execution_principal(
        FakeSession(users),
        connection,
        None,
        _identity(member_id),
        requires_personal=True,
    )
    assert principal.user.id == member_id
    assert principal.identity_type == ChannelExecutionIdentityType.BOUND_USER.value
