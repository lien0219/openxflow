"""Validation for workflow and knowledge-base resources attached to channel conversations."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlmodel.ext.asyncio.session import AsyncSession

from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import (
    FlowAction,
    KnowledgeBaseAction,
    ensure_flow_permission,
    ensure_knowledge_base_permission,
)
from langflow.services.database.models.channel.model import ChannelConversationBindingUpsert
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.database.models.user.model import User


async def validate_conversation_binding_resources(
    session: AsyncSession,
    user: User,
    payload: ChannelConversationBindingUpsert,
) -> None:
    """Reject resource IDs that the connection owner cannot safely use."""
    if payload.default_flow_id is not None:
        flow = await get_flow_by_id_or_endpoint_name(
            str(payload.default_flow_id),
            user.id,
            widen_for_shares=True,
        )
        if flow.id != payload.default_flow_id:
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

    if payload.knowledge_base_id is None:
        return

    knowledge_base = await session.get(KnowledgeBaseRecord, payload.knowledge_base_id)
    # Knowledge bases are currently user-scoped and do not have the shared-resource
    # lookup path that flows have. Returning 404 avoids leaking another user's UUID.
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
    if payload.allow_file_upload:
        await ensure_knowledge_base_permission(
            user,
            KnowledgeBaseAction.INGEST,
            kb_id=knowledge_base.id,
            kb_user_id=knowledge_base.user_id,
            kb_name=knowledge_base.name,
        )
