from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from langflow.channels.services.flow_selection import (
    clear_active_workflow_selection,
    resolve_active_workflow_selection,
    set_active_workflow_selection,
)
from langflow.services.database.models.channel.command_model import (
    ChannelCommandScope,
    ChannelWorkflowCommand,
)
from langflow.services.database.models.channel.flow_selection_model import ChannelActiveWorkflowSelection
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelIdentity,
)
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def selection_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    tables = [
        ChannelConnection.__table__,
        ChannelConversationBinding.__table__,
        ChannelIdentity.__table__,
        ChannelWorkflowCommand.__table__,
        ChannelActiveWorkflowSelection.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync_connection: SQLModel.metadata.create_all(sync_connection, tables=tables))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed(selection_session):
    connection = ChannelConnection(
        id=uuid4(),
        user_id=uuid4(),
        name="Feishu",
        channel_type="feishu",
        credentials_encrypted="encrypted",
        user_flow_selection_enabled=True,
        flow_selection_ttl_hours=24,
    )
    binding = ChannelConversationBinding(
        id=uuid4(),
        connection_id=connection.id,
        external_conversation_id="chat-1",
        conversation_type="group",
    )
    identity = ChannelIdentity(
        id=uuid4(),
        connection_id=connection.id,
        external_user_id="ou-user-1",
    )
    command = ChannelWorkflowCommand(
        id=uuid4(),
        connection_id=connection.id,
        created_by=connection.user_id,
        flow_id=uuid4(),
        command="/summary",
        normalized_command="/summary",
        scope_type=ChannelCommandScope.CONNECTION_SHARED.value,
        scope_key="connection",
        allow_persistent_selection=True,
    )
    selection_session.add_all([connection, binding, identity, command])
    await selection_session.flush()
    return connection, binding, identity, command


@pytest.mark.asyncio
async def test_selection_persists_and_resolves_for_unbound_shared_member(selection_session) -> None:
    connection, binding, identity, command = await _seed(selection_session)

    selection, selected_command = await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-1",
        user_id=None,
        command_name="/summary",
    )
    assert selected_command.id == command.id
    assert selection.workflow_command_id == command.id
    assert selection.expires_at is not None

    resolution = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-1",
        user_id=None,
    )
    assert resolution.command.id == command.id
    assert resolution.selection.last_used_at is not None


@pytest.mark.asyncio
async def test_selection_isolated_by_member_and_thread(selection_session) -> None:
    connection, binding, identity, _ = await _seed(selection_session)
    await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-a",
        user_id=None,
        command_name="/summary",
    )

    other_thread = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="thread-b",
        user_id=None,
    )
    assert other_thread.command is None

    other_identity = ChannelIdentity(
        id=uuid4(),
        connection_id=connection.id,
        external_user_id="ou-user-2",
    )
    selection_session.add(other_identity)
    await selection_session.flush()
    other_member = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=other_identity,
        conversation_scope_id="thread-a",
        user_id=None,
    )
    assert other_member.command is None


@pytest.mark.asyncio
async def test_expired_or_disabled_selection_is_removed(selection_session) -> None:
    connection, binding, identity, _ = await _seed(selection_session)
    selection, _ = await set_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="",
        user_id=None,
        command_name="/summary",
    )
    selection.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    selection_session.add(selection)
    await selection_session.flush()

    resolution = await resolve_active_workflow_selection(
        selection_session,
        connection=connection,
        binding=binding,
        identity=identity,
        conversation_scope_id="",
        user_id=None,
    )
    assert resolution.command is None
    assert resolution.invalid_reason == "selection_expired"

    assert not await clear_active_workflow_selection(
        selection_session,
        connection_id=connection.id,
        conversation_binding_id=binding.id,
        channel_identity_id=identity.id,
        conversation_scope_id="",
    )
