"""Execute OpenXFlow workflows from normalized channel messages."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException, status

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from langflow.services.database.models.channel.model import ChannelContextMode
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from langflow.services.deps import session_scope

if TYPE_CHECKING:
    from langflow.api.v1.schemas import RunResponse

_TELEGRAM_SAFE_TEXT_LIMIT = 3900
_PREFERRED_OUTPUT_KEYS = ("text", "message", "content", "result", "results", "data")


def build_channel_session_id(event: ChannelEvent, context_mode: str = ChannelContextMode.ISOLATED.value) -> str:
    parts = [
        event.channel.value,
        str(event.connection_id),
        event.conversation.external_conversation_id,
        conversation_scope_id(event),
    ]
    if context_mode != ChannelContextMode.SHARED.value or event.conversation.conversation_type == "private":
        parts.append(event.user.external_user_id)
    raw = ":".join(parts)
    return f"channel-{hashlib.sha256(raw.encode()).hexdigest()[:32]}"


def _collect_text_candidates(value: Any, *, depth: int = 0) -> list[str]:
    if depth > 8 or value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True)
    if isinstance(value, dict):
        candidates: list[str] = []
        visited: set[str] = set()
        for key in _PREFERRED_OUTPUT_KEYS:
            if key in value:
                visited.add(key)
                candidates.extend(_collect_text_candidates(value[key], depth=depth + 1))
        for key, nested in value.items():
            if key not in visited:
                candidates.extend(_collect_text_candidates(nested, depth=depth + 1))
        return candidates
    if isinstance(value, (list, tuple)):
        candidates = []
        for nested in value:
            candidates.extend(_collect_text_candidates(nested, depth=depth + 1))
        return candidates
    return []


def _collect_chat_output_messages(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    candidates: list[str] = []
    for run_output in value:
        if hasattr(run_output, "model_dump"):
            run_output = run_output.model_dump(exclude_none=True)
        if not isinstance(run_output, dict):
            continue
        result_items = run_output.get("outputs")
        if not isinstance(result_items, (list, tuple)):
            continue
        for result_item in result_items:
            if hasattr(result_item, "model_dump"):
                result_item = result_item.model_dump(exclude_none=True)
            if not isinstance(result_item, dict):
                continue
            messages = result_item.get("messages")
            if not isinstance(messages, (list, tuple)):
                continue
            for message in messages:
                if hasattr(message, "model_dump"):
                    message = message.model_dump(exclude_none=True)
                if not isinstance(message, dict):
                    continue
                sender = str(message.get("sender") or "").strip().lower()
                if sender and sender not in {"machine", "ai", "assistant"}:
                    continue
                candidates.extend(_collect_text_candidates(message.get("message"), depth=1))
    return candidates


def render_run_response(response: RunResponse) -> str:
    payload = response.model_dump(exclude_none=True)
    outputs = payload.get("outputs")
    candidates = _collect_chat_output_messages(outputs) or _collect_text_candidates(outputs)
    deduplicated: list[str] = []
    for candidate in candidates:
        if candidate not in deduplicated:
            deduplicated.append(candidate)
    rendered = deduplicated[-1] if deduplicated else json.dumps(payload, ensure_ascii=False, default=str, indent=2)
    if len(rendered) > _TELEGRAM_SAFE_TEXT_LIMIT:
        rendered = f"{rendered[: _TELEGRAM_SAFE_TEXT_LIMIT - 24]}\n\n[结果已截断]"
    return rendered


class ChannelWorkflowExecutor:
    """Permission-aware bridge from a channel event to the existing workflow runtime."""

    async def execute(
        self,
        *,
        event: ChannelEvent,
        user: User,
        flow_identifier: str,
        input_value: str | None,
        session_id: str,
        execution_identity_type: str,
        channel_context: dict[str, Any] | None = None,
    ) -> ChannelMessage:
        from langflow.api.v1.endpoints import simple_run_flow
        from langflow.api.v1.schemas import SimplifiedAPIRequest

        if execution_identity_type == ChannelExecutionIdentityType.SERVICE.value:
            granted_flow_id = str((channel_context or {}).get("granted_flow_id") or "")
            if not granted_flow_id or granted_flow_id != flow_identifier:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="The channel service identity is not granted this workflow",
                )
            try:
                flow_id = UUID(granted_flow_id)
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Shared channel routes require an explicit workflow ID grant",
                ) from exc
            async with session_scope() as session:
                flow = await session.get(Flow, flow_id)
            if flow is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
        else:
            flow = await get_flow_by_id_or_endpoint_name(flow_identifier, user.id, widen_for_shares=True)
            await ensure_flow_permission(
                user,
                FlowAction.EXECUTE,
                flow_id=flow.id,
                flow_user_id=flow.user_id,
                workspace_id=getattr(flow, "workspace_id", None),
                folder_id=getattr(flow, "folder_id", None),
            )
        normalized_attachments = [attachment.model_dump(exclude_none=True) for attachment in event.message.attachments]
        context_payload: dict[str, Any] = {
            "type": event.channel.value,
            "connection_id": str(event.connection_id),
            "conversation_id": event.conversation.external_conversation_id,
            "conversation_type": event.conversation.conversation_type,
            "conversation_scope_id": conversation_scope_id(event),
            "message_id": event.message.external_message_id,
            "event_id": event.event_id,
            "external_user_id": event.user.external_user_id,
            "openxflow_user_id": str(user.id),
            "execution_identity_type": execution_identity_type,
            "attachments": normalized_attachments,
            "message_metadata": dict(event.message.metadata),
        }
        if channel_context:
            context_payload.update(channel_context)
        request = SimplifiedAPIRequest(
            input_value=input_value,
            input_type="chat",
            output_type="chat",
            session_id=session_id,
            user_id=f"{event.channel.value}:{event.user.external_user_id}",
        )
        response = await simple_run_flow(
            flow,
            request,
            api_key_user=user,
            context={"channel": context_payload},
        )
        return ChannelMessage(
            message_type=ChannelMessageType.MARKDOWN,
            title=flow.name,
            markdown=render_run_response(response),
            metadata={
                "flow_id": str(flow.id),
                "session_id": response.session_id,
                "execution_identity_type": execution_identity_type,
            },
        )
