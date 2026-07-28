"""Server-side pagination for the Settings > Messages data grid."""

from __future__ import annotations

import math
from typing import Annotated
from urllib.parse import unquote
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.schema.message import MessageResponse
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.authorization.fetch import authorized_or_owner_scoped
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.message.model import MessageTable

router = APIRouter(prefix="/monitor/messages", tags=["Monitor"])


class MessagePage(BaseModel):
    items: list[MessageResponse]
    page: int
    page_size: int
    total: int
    total_pages: int


@router.get("/page", response_model=MessagePage)
async def get_messages_page(
    session: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    flow_id: Annotated[UUID | None, Query()] = None,
    session_id: Annotated[str | None, Query()] = None,
    sender: Annotated[str | None, Query()] = None,
    sender_name: Annotated[str | None, Query()] = None,
    query: Annotated[str | None, Query(max_length=500)] = None,
    order_by: Annotated[str, Query()] = "-timestamp",
) -> MessagePage:
    """Return one owner/RBAC-scoped page instead of loading the full message table."""
    filters = [~col(MessageTable.session_id).startswith("agentic_")]

    if flow_id is not None:
        flow = await authorized_or_owner_scoped(
            session,
            Flow,
            id_column=Flow.id,
            resource_id=flow_id,
            owner_column=Flow.user_id,
            owner_id=current_user.id,
        )
        if flow is None:
            return MessagePage(items=[], page=page, page_size=page_size, total=0, total_pages=0)
        await ensure_flow_permission(
            current_user,
            FlowAction.READ,
            flow_id=flow.id,
            flow_user_id=flow.user_id,
            workspace_id=getattr(flow, "workspace_id", None),
            folder_id=getattr(flow, "folder_id", None),
        )
        filters.append(MessageTable.flow_id == flow_id)
    else:
        # The global settings page is intentionally tenant-scoped. Shared-flow
        # messages are available by selecting that flow explicitly.
        filters.append(Flow.user_id == current_user.id)

    if session_id:
        filters.append(MessageTable.session_id == unquote(session_id))
    if sender:
        filters.append(MessageTable.sender == sender)
    if sender_name:
        filters.append(MessageTable.sender_name == sender_name)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            (MessageTable.text.ilike(pattern))
            | (MessageTable.sender_name.ilike(pattern))
            | (MessageTable.session_id.ilike(pattern))
        )

    base_stmt = select(MessageTable).join(Flow, MessageTable.flow_id == Flow.id).where(*filters)
    count_stmt = (
        select(func.count()).select_from(MessageTable).join(Flow, MessageTable.flow_id == Flow.id).where(*filters)
    )
    total = int((await session.exec(count_stmt)).one())

    descending = order_by.startswith("-")
    field_name = order_by.removeprefix("-")
    sort_columns = {
        "timestamp": MessageTable.timestamp,
        "sender": MessageTable.sender,
        "sender_name": MessageTable.sender_name,
        "session_id": MessageTable.session_id,
    }
    sort_column = sort_columns.get(field_name, MessageTable.timestamp)
    ordering = sort_column.desc() if descending else sort_column.asc()
    statement = base_stmt.order_by(ordering, MessageTable.id.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await session.exec(statement)).all()
    return MessagePage(
        items=[MessageResponse.model_validate(row, from_attributes=True) for row in rows],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )
