"""Command routing and execution-history APIs for communication channels."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.services.commands import (
    create_workflow_command,
    delete_workflow_command,
    get_workflow_command,
    list_workflow_commands,
    update_workflow_command,
)
from langflow.channels.services.configuration_audit import (
    channel_resource_snapshot,
    record_channel_configuration_audit,
)
from langflow.channels.services.conversation_validation import (
    validate_channel_routing_resources,
)
from langflow.channels.services.execution_logs import list_channel_executions
from langflow.services.database.models.channel.command_model import (
    ChannelWorkflowCommandCreate,
    ChannelWorkflowCommandPage,
    ChannelWorkflowCommandRead,
    ChannelWorkflowCommandUpdate,
)
from langflow.services.database.models.channel.execution_model import (
    ChannelExecutionLogPage,
)
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelIdentity,
    ChannelIdentityStatus,
)

router = APIRouter(prefix="/channels", tags=["Channel Management"])


async def _accessible_connection_or_404(
    db: DbSession,
    current_user: CurrentActiveUser,
    connection_id: UUID,
) -> ChannelConnection:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    if current_user.is_superuser or connection.user_id == current_user.id:
        return connection
    identity_statement = select(ChannelIdentity.id).where(
        ChannelIdentity.connection_id == connection_id,
        ChannelIdentity.openxflow_user_id == current_user.id,
        ChannelIdentity.status == ChannelIdentityStatus.BOUND.value,
    )
    if (await db.exec(identity_statement)).first() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    return connection


async def _owned_connection_or_404(
    db: DbSession,
    current_user: CurrentActiveUser,
    connection_id: UUID,
) -> ChannelConnection:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or (connection.user_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    return connection


@router.get("/{connection_id}/commands", response_model=ChannelWorkflowCommandPage)
async def read_channel_commands(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: Annotated[str | None, Query(max_length=255)] = None,
    scope_type: Annotated[str | None, Query(max_length=32)] = None,
    enabled: Annotated[bool | None, Query()] = None,
) -> ChannelWorkflowCommandPage:
    connection = await _accessible_connection_or_404(db, current_user, connection_id)
    return await list_workflow_commands(
        db,
        connection,
        current_user,
        page=page,
        page_size=page_size,
        query=query,
        scope_type=scope_type,
        enabled=enabled,
    )


@router.post(
    "/{connection_id}/commands",
    response_model=ChannelWorkflowCommandRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_channel_command(
    connection_id: UUID,
    payload: ChannelWorkflowCommandCreate,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelWorkflowCommandRead:
    connection = await _accessible_connection_or_404(db, current_user, connection_id)
    await validate_channel_routing_resources(
        db,
        current_user,
        flow_id=payload.flow_id,
        knowledge_base_id=None,
        allow_file_upload=False,
    )
    try:
        result = await create_workflow_command(db, connection, current_user, payload)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A command with this name already exists in the selected scope",
        ) from exc
    else:
        await record_channel_configuration_audit(
            db,
            connection_id=connection_id,
            actor_user_id=current_user.id,
            action="create",
            resource_type="command",
            resource_id=result.id,
            after=result,
        )
        await db.commit()
        return result


@router.patch("/{connection_id}/commands/{command_id}", response_model=ChannelWorkflowCommandRead)
async def patch_channel_command(
    connection_id: UUID,
    command_id: UUID,
    payload: ChannelWorkflowCommandUpdate,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelWorkflowCommandRead:
    connection = await _accessible_connection_or_404(db, current_user, connection_id)
    command = await get_workflow_command(db, connection_id, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel command not found")
    before = channel_resource_snapshot(command)
    if payload.flow_id is not None:
        await validate_channel_routing_resources(
            db,
            current_user,
            flow_id=payload.flow_id,
            knowledge_base_id=None,
            allow_file_upload=False,
        )
    try:
        result = await update_workflow_command(db, connection, current_user, command, payload)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A command with this name already exists in the selected scope",
        ) from exc
    else:
        await record_channel_configuration_audit(
            db,
            connection_id=connection_id,
            actor_user_id=current_user.id,
            action="update",
            resource_type="command",
            resource_id=command.id,
            before=before,
            after=result,
        )
        await db.commit()
        return result


@router.delete("/{connection_id}/commands/{command_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_channel_command(
    connection_id: UUID,
    command_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> Response:
    connection = await _accessible_connection_or_404(db, current_user, connection_id)
    command = await get_workflow_command(db, connection_id, command_id)
    if command is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel command not found")
    before = channel_resource_snapshot(command)
    await delete_workflow_command(db, connection, current_user, command)
    await record_channel_configuration_audit(
        db,
        connection_id=connection_id,
        actor_user_id=current_user.id,
        action="delete",
        resource_type="command",
        resource_id=command.id,
        before=before,
    )
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{connection_id}/executions", response_model=ChannelExecutionLogPage)
async def read_channel_executions(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    conversation_binding_id: Annotated[UUID | None, Query()] = None,
    openxflow_user_id: Annotated[UUID | None, Query()] = None,
    status_filter: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    trigger_type: Annotated[str | None, Query(max_length=32)] = None,
    query: Annotated[str | None, Query(max_length=255)] = None,
    external_user_id: Annotated[str | None, Query(max_length=255)] = None,
    session_id: Annotated[str | None, Query(max_length=255)] = None,
    execution_identity_type: Annotated[str | None, Query(max_length=32)] = None,
    flow_id: Annotated[UUID | None, Query()] = None,
    error_code: Annotated[str | None, Query(max_length=128)] = None,
    created_from: Annotated[datetime | None, Query()] = None,
    created_to: Annotated[datetime | None, Query()] = None,
) -> ChannelExecutionLogPage:
    await _owned_connection_or_404(db, current_user, connection_id)
    return await list_channel_executions(
        db,
        connection_id,
        page=page,
        page_size=page_size,
        conversation_binding_id=conversation_binding_id,
        openxflow_user_id=openxflow_user_id,
        status=status_filter,
        trigger_type=trigger_type,
        query=query,
        external_user_id=external_user_id,
        session_id=session_id,
        execution_identity_type=execution_identity_type,
        flow_id=flow_id,
        error_code=error_code,
        created_from=created_from,
        created_to=created_to,
    )
