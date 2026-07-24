"""Administrative list and batch operations for channel connections."""

from __future__ import annotations

import math
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.channels.services.conversation_validation import validate_channel_routing_resources
from langflow.services.database.models.channel.crud import update_channel_conversation_binding
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
    ChannelConversationBindingRead,
    ChannelConversationBindingUpdate,
    ChannelConversationRouteMode,
    ChannelConversationStatus,
    ChannelIdentity,
    ChannelIdentityRead,
)

router = APIRouter(prefix="/channels", tags=["Channel Administration"])


class ChannelIdentityPage(BaseModel):
    items: list[ChannelIdentityRead]
    page: int
    page_size: int
    total: int
    total_pages: int


class ChannelConversationBatchRequest(BaseModel):
    conversation_ids: list[UUID] = Field(min_length=1, max_length=500)
    action: str
    default_flow_id: UUID | None = None


class ChannelConversationBatchResponse(BaseModel):
    updated: int
    items: list[ChannelConversationBindingRead]


async def _owned_connection_or_404(
    db: DbSession,
    current_user: CurrentActiveUser,
    connection_id: UUID,
) -> ChannelConnection:
    connection = await db.get(ChannelConnection, connection_id)
    if connection is None or (
        connection.user_id != current_user.id and not current_user.is_superuser
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    return connection


@router.get("/{connection_id}/identities/page", response_model=ChannelIdentityPage)
async def read_channel_identities_page(
    connection_id: UUID,
    db: DbSession,
    current_user: CurrentActiveUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status", max_length=32),
) -> ChannelIdentityPage:
    await _owned_connection_or_404(db, current_user, connection_id)
    filters: list = [ChannelIdentity.connection_id == connection_id]
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                ChannelIdentity.display_name.ilike(pattern),
                ChannelIdentity.external_user_id.ilike(pattern),
            )
        )
    if status_filter:
        filters.append(ChannelIdentity.status == status_filter)

    total_statement = select(func.count()).select_from(ChannelIdentity).where(*filters)
    total = int((await db.exec(total_statement)).one())
    statement = (
        select(ChannelIdentity)
        .where(*filters)
        .order_by(ChannelIdentity.updated_at.desc(), ChannelIdentity.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.exec(statement)).all()
    return ChannelIdentityPage(
        items=[ChannelIdentityRead.model_validate(row, from_attributes=True) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.post("/{connection_id}/conversations/batch", response_model=ChannelConversationBatchResponse)
async def batch_update_channel_conversations(
    connection_id: UUID,
    payload: ChannelConversationBatchRequest,
    db: DbSession,
    current_user: CurrentActiveUser,
) -> ChannelConversationBatchResponse:
    connection = await _owned_connection_or_404(db, current_user, connection_id)
    supported_actions = {"inherit", "override", "ignore", "restore", "disable", "enable"}
    if payload.action not in supported_actions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported conversation batch action",
        )
    if payload.action == "override" and payload.default_flow_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="default_flow_id is required for override action",
        )
    if payload.default_flow_id is not None:
        await validate_channel_routing_resources(
            db,
            current_user,
            flow_id=payload.default_flow_id,
            knowledge_base_id=None,
            allow_file_upload=False,
        )

    statement = select(ChannelConversationBinding).where(
        ChannelConversationBinding.connection_id == connection_id,
        ChannelConversationBinding.id.in_(payload.conversation_ids),
    )
    rows = (await db.exec(statement)).all()
    updated_items: list[ChannelConversationBindingRead] = []
    for row in rows:
        update = _batch_update_payload(payload)
        updated_items.append(
            await update_channel_conversation_binding(db, connection, row, update)
        )
    await db.commit()
    return ChannelConversationBatchResponse(updated=len(updated_items), items=updated_items)


def _batch_update_payload(payload: ChannelConversationBatchRequest) -> ChannelConversationBindingUpdate:
    if payload.action == "inherit":
        return ChannelConversationBindingUpdate(
            route_mode=ChannelConversationRouteMode.INHERIT.value,
            default_flow_id=None,
            status=ChannelConversationStatus.PENDING.value,
        )
    if payload.action == "override":
        return ChannelConversationBindingUpdate(
            route_mode=ChannelConversationRouteMode.OVERRIDE.value,
            default_flow_id=payload.default_flow_id,
            status=ChannelConversationStatus.OVERRIDDEN.value,
        )
    if payload.action == "ignore":
        return ChannelConversationBindingUpdate(status=ChannelConversationStatus.IGNORED.value)
    if payload.action == "restore":
        return ChannelConversationBindingUpdate(status=ChannelConversationStatus.PENDING.value)
    if payload.action == "disable":
        return ChannelConversationBindingUpdate(
            route_mode=ChannelConversationRouteMode.DISABLED.value,
            status=ChannelConversationStatus.DISABLED.value,
        )
    return ChannelConversationBindingUpdate(
        route_mode=ChannelConversationRouteMode.INHERIT.value,
        status=ChannelConversationStatus.PENDING.value,
    )
