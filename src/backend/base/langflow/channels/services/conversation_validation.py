"""Validation for workflow and knowledge-base resources attached to channel routing."""

from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import (
    FlowAction,
    KnowledgeBaseAction,
    ensure_flow_permission,
    ensure_knowledge_base_permission,
)
from langflow.services.database.models.channel.model import (
    ChannelConnectionCreate,
    ChannelConnectionUpdate,
    ChannelConversationBindingUpdate,
    ChannelConversationBindingUpsert,
)
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.database.models.user.model import User


async def validate_channel_routing_resources(
    session: AsyncSession,
    user: User,
    *,
    flow_id: UUID | None,
    knowledge_base_id: UUID | None,
    allow_file_upload: bool,
) -> None:
    """Reject resource IDs that the connection owner cannot safely use."""
    if flow_id is not None:
        flow = await get_flow_by_id_or_endpoint_name(
            str(flow_id),
            user.id,
            widen_for_shares=True,
        )
        if flow.id != flow_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )
        await ensure_flow_permission(
            user,
            FlowAction.EXECUTE,
            flow_id=flow.id,
            flow_user_id=flow.user_id,
            workspace_id=getattr(flow, "workspace_id", None),
            folder_id=getattr(flow, "folder_id", None),
        )

    if knowledge_base_id is None:
        return

    knowledge_base = await session.get(KnowledgeBaseRecord, knowledge_base_id)
    if knowledge_base is None or knowledge_base.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge base not found",
        )

    await ensure_knowledge_base_permission(
        user,
        KnowledgeBaseAction.READ,
        kb_id=knowledge_base.id,
        kb_user_id=knowledge_base.user_id,
        kb_name=knowledge_base.name,
    )
    if allow_file_upload:
        await ensure_knowledge_base_permission(
            user,
            KnowledgeBaseAction.INGEST,
            kb_id=knowledge_base.id,
            kb_user_id=knowledge_base.user_id,
            kb_name=knowledge_base.name,
        )


async def validate_connection_routing_resources(
    session: AsyncSession,
    user: User,
    payload: ChannelConnectionCreate | ChannelConnectionUpdate,
    *,
    current_allow_file_upload: bool = True,
) -> None:
    changes = payload.model_dump(exclude_unset=True)
    await validate_channel_routing_resources(
        session,
        user,
        flow_id=changes.get("default_flow_id"),
        knowledge_base_id=changes.get("default_knowledge_base_id"),
        allow_file_upload=changes.get("default_allow_file_upload", current_allow_file_upload),
    )


async def validate_conversation_binding_resources(
    session: AsyncSession,
    user: User,
    payload: ChannelConversationBindingUpsert | ChannelConversationBindingUpdate,
    *,
    current_allow_file_upload: bool = True,
) -> None:
    changes = payload.model_dump(exclude_unset=True)
    await validate_channel_routing_resources(
        session,
        user,
        flow_id=changes.get("default_flow_id"),
        knowledge_base_id=changes.get("knowledge_base_id"),
        allow_file_upload=changes.get("allow_file_upload", current_allow_file_upload),
    )
