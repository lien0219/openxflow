from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from langflow.channels.services.authorization import authorize_channel_connection
from langflow.services.authorization import ChannelAction
from langflow.services.database.models.channel.model import ChannelConnection


@pytest.mark.asyncio
async def test_channel_owner_is_allowed_without_rbac() -> None:
    connection_id = uuid4()
    user_id = uuid4()
    connection = SimpleNamespace(id=connection_id, user_id=user_id)
    user = SimpleNamespace(id=user_id, is_active=True, is_superuser=False, optins={})
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=lambda model, record_id: (
            connection if model is ChannelConnection and record_id == connection_id else None
        )
    )

    result = await authorize_channel_connection(
        session,
        user,
        connection_id,
        ChannelAction.WRITE,
    )

    assert result is connection


@pytest.mark.asyncio
async def test_non_owner_is_hidden_when_rbac_is_disabled() -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(id=connection_id, user_id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, optins={})
    session = MagicMock()
    session.get = AsyncMock(return_value=connection)

    with (
        patch(
            "langflow.channels.services.authorization.get_settings_service",
            return_value=SimpleNamespace(auth_settings=SimpleNamespace(AUTHZ_ENABLED=False)),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await authorize_channel_connection(
            session,
            user,
            connection_id,
            ChannelAction.READ,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_non_owner_is_allowed_by_scoped_channel_rbac() -> None:
    connection_id = uuid4()
    connection = SimpleNamespace(id=connection_id, user_id=uuid4())
    user = SimpleNamespace(id=uuid4(), is_active=True, is_superuser=False, optins={})
    session = MagicMock()
    session.get = AsyncMock(return_value=connection)

    with (
        patch(
            "langflow.channels.services.authorization.get_settings_service",
            return_value=SimpleNamespace(auth_settings=SimpleNamespace(AUTHZ_ENABLED=True)),
        ),
        patch(
            "langflow.channels.services.authorization.ensure_permission",
            new=AsyncMock(return_value=None),
        ) as ensure_permission,
    ):
        result = await authorize_channel_connection(
            session,
            user,
            connection_id,
            ChannelAction.AUDIT,
        )

    assert result is connection
    ensure_permission.assert_awaited_once()
    assert ensure_permission.await_args.kwargs["domain"] == f"channel:{connection_id}"
    assert ensure_permission.await_args.kwargs["act"] == "audit"
