"""Lightweight paginated resource options for channel routing editors."""

from __future__ import annotations

import math
from typing import Annotated, Any
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.initial_setup.constants import STARTER_FOLDER_NAME
from langflow.services.authorization import FlowAction, KnowledgeBaseAction
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.folder.model import Folder
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.deps import get_authorization_service, get_settings_service

router = APIRouter(prefix="/channels/resources", tags=["Channel Resources"])


class ChannelFlowOption(BaseModel):
    id: UUID
    name: str
    endpoint_name: str | None = None
    description: str | None = None
    folder_id: UUID | None = None
    project_name: str | None = None


class ChannelFlowOptionPage(BaseModel):
    items: list[ChannelFlowOption]
    selected_item: ChannelFlowOption | None = None
    page: int
    page_size: int
    total: int
    total_pages: int


class ChannelKnowledgeBaseOption(BaseModel):
    id: UUID
    name: str
    status: str
    chunks: int


class ChannelKnowledgeBaseOptionPage(BaseModel):
    items: list[ChannelKnowledgeBaseOption]
    page: int
    page_size: int
    total: int
    total_pages: int


def _flow_option(flow: Flow, project_name: str | None) -> ChannelFlowOption:
    return ChannelFlowOption(
        id=flow.id,
        name=flow.name,
        endpoint_name=flow.endpoint_name,
        description=flow.description,
        folder_id=flow.folder_id,
        project_name=project_name,
    )


async def _visible_resource_filter(
    current_user: CurrentActiveUser,
    *,
    resource_type: str,
    action: str,
    id_column,
    owner_column,
):
    """Return a SQL predicate for owner plus RBAC/share-visible resources."""
    if current_user.is_superuser:
        return None
    settings = get_settings_service()
    if not settings.auth_settings.AUTHZ_ENABLED:
        return owner_column == current_user.id

    visible_ids = await get_authorization_service().list_visible_resource_ids(
        user_id=current_user.id,
        resource_type=resource_type,
        act=action,
        context={"is_superuser": current_user.is_superuser},
    )
    if visible_ids is None:
        return None
    if not visible_ids:
        return owner_column == current_user.id
    return sa.or_(owner_column == current_user.id, id_column.in_(visible_ids))


@router.get("/flows", response_model=ChannelFlowOptionPage)
async def read_channel_flow_options(
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: Annotated[str | None, Query(max_length=255)] = None,
    selected_id: Annotated[UUID | None, Query()] = None,
) -> ChannelFlowOptionPage:
    # The project workspace hides starter templates from normal project lists. Keep
    # the channel picker aligned with that UI instead of exposing every seeded flow.
    base_filters: list[Any] = [
        sa.or_(Flow.is_component.is_(False), Flow.is_component.is_(None)),
        sa.or_(
            Flow.folder_id.is_(None),
            Folder.id.is_(None),
            Folder.name != STARTER_FOLDER_NAME,
        ),
    ]
    visibility = await _visible_resource_filter(
        current_user,
        resource_type="flow",
        action=FlowAction.READ.value,
        id_column=Flow.id,
        owner_column=Flow.user_id,
    )
    if visibility is not None:
        base_filters.append(visibility)

    filters = list(base_filters)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                Flow.name.ilike(pattern),
                Flow.endpoint_name.ilike(pattern),
                Flow.description.ilike(pattern),
                Folder.name.ilike(pattern),
            )
        )

    total_statement = (
        select(func.count()).select_from(Flow).outerjoin(Folder, Folder.id == Flow.folder_id).where(*filters)
    )
    total = int((await db.exec(total_statement)).one())
    statement = (
        select(Flow, Folder.name.label("project_name"))
        .select_from(Flow)
        .outerjoin(Folder, Folder.id == Flow.folder_id)
        .where(*filters)
        .order_by(Flow.updated_at.desc(), Folder.name, Flow.name, Flow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.exec(statement)).all()

    selected_item: ChannelFlowOption | None = None
    if selected_id is not None:
        selected_statement = (
            select(Flow, Folder.name.label("project_name"))
            .select_from(Flow)
            .outerjoin(Folder, Folder.id == Flow.folder_id)
            .where(*base_filters, Flow.id == selected_id)
            .limit(1)
        )
        selected_row = (await db.exec(selected_statement)).first()
        if selected_row is not None:
            selected_flow, selected_project_name = selected_row
            selected_item = _flow_option(selected_flow, selected_project_name)

    return ChannelFlowOptionPage(
        items=[_flow_option(flow, project_name) for flow, project_name in rows],
        selected_item=selected_item,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/knowledge-bases", response_model=ChannelKnowledgeBaseOptionPage)
async def read_channel_knowledge_base_options(
    db: DbSession,
    current_user: CurrentActiveUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    query: Annotated[str | None, Query(max_length=255)] = None,
) -> ChannelKnowledgeBaseOptionPage:
    filters: list[Any] = []
    visibility = await _visible_resource_filter(
        current_user,
        resource_type="knowledge_base",
        action=KnowledgeBaseAction.READ.value,
        id_column=KnowledgeBaseRecord.id,
        owner_column=KnowledgeBaseRecord.user_id,
    )
    if visibility is not None:
        filters.append(visibility)
    if query and query.strip():
        filters.append(KnowledgeBaseRecord.name.ilike(f"%{query.strip()}%"))

    total_statement = select(func.count()).select_from(KnowledgeBaseRecord).where(*filters)
    total = int((await db.exec(total_statement)).one())
    statement = (
        select(KnowledgeBaseRecord)
        .where(*filters)
        .order_by(KnowledgeBaseRecord.updated_at.desc(), KnowledgeBaseRecord.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.exec(statement)).all()
    return ChannelKnowledgeBaseOptionPage(
        items=[
            ChannelKnowledgeBaseOption(
                id=row.id,
                name=row.name,
                status=row.status,
                chunks=row.chunks,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )
