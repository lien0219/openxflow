"""Lightweight paginated resource options for channel routing editors."""

from __future__ import annotations

import math
from uuid import UUID

import sqlalchemy as sa
from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import select

from langflow.api.utils import CurrentActiveUser, DbSession
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord

router = APIRouter(prefix="/channels/resources", tags=["Channel Resources"])


class ChannelFlowOption(BaseModel):
    id: UUID
    name: str
    endpoint_name: str | None = None
    description: str | None = None
    folder_id: UUID | None = None


class ChannelFlowOptionPage(BaseModel):
    items: list[ChannelFlowOption]
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


@router.get("/flows", response_model=ChannelFlowOptionPage)
async def read_channel_flow_options(
    db: DbSession,
    current_user: CurrentActiveUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str | None = Query(default=None, max_length=255),
) -> ChannelFlowOptionPage:
    filters: list = [
        Flow.user_id == current_user.id,
        sa.or_(Flow.is_component.is_(False), Flow.is_component.is_(None)),
    ]
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        filters.append(
            sa.or_(
                Flow.name.ilike(pattern),
                Flow.endpoint_name.ilike(pattern),
                Flow.description.ilike(pattern),
            )
        )

    total_statement = select(func.count()).select_from(Flow).where(*filters)
    total = int((await db.exec(total_statement)).one())
    statement = (
        select(Flow)
        .where(*filters)
        .order_by(Flow.updated_at.desc(), Flow.name, Flow.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.exec(statement)).all()
    return ChannelFlowOptionPage(
        items=[
            ChannelFlowOption(
                id=row.id,
                name=row.name,
                endpoint_name=row.endpoint_name,
                description=row.description,
                folder_id=row.folder_id,
            )
            for row in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        total_pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/knowledge-bases", response_model=ChannelKnowledgeBaseOptionPage)
async def read_channel_knowledge_base_options(
    db: DbSession,
    current_user: CurrentActiveUser,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query: str | None = Query(default=None, max_length=255),
) -> ChannelKnowledgeBaseOptionPage:
    filters: list = [KnowledgeBaseRecord.user_id == current_user.id]
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
