"""Execute OpenXFlow workflows from normalized channel messages."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.database.models.user.model import User

if TYPE_CHECKING:
    from langflow.api.v1.schemas import RunResponse

_TELEGRAM_SAFE_TEXT_LIMIT = 3900
_PREFERRED_OUTPUT_KEYS = ("text", "message", "content", "result", "results", "data")


def build_channel_session_id(event: ChannelEvent) -> str:
    raw = ":".join(
        (
            event.channel.value,
            str(event.connection_id),
            event.conversation.external_conversation_id,
            event.user.external_user_id,
        )
    )
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


def render_run_response(response: RunResponse) -> str:
    payload = response.model_dump(exclude_none=True)
    candidates = _collect_text_candidates(payload.get("outputs"))
    deduplicated: list[str] = []
    for candidate in candidates:
        if candidate not in deduplicated:
            deduplicated.append(candidate)
    if deduplicated:
        rendered = deduplicated[-1]
    else:
        rendered = json.dumps(payload, ensure_ascii=False, default=str, indent=2)
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
        channel_context: dict[str, Any] | None = None,
    ) -> ChannelMessage:
        # Lazy import avoids a router -> channel webhook -> workflow -> endpoints
        # cycle while FastAPI is still constructing the v1 router.
        from langflow.api.v1.endpoints import simple_run_flow
        from langflow.api.v1.schemas import SimplifiedAPIRequest

        flow = await get_flow_by_id_or_endpoint_name(
            flow_identifier,
            user.id,
            widen_for_shares=True,
        )
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
            "message_id": event.message.external_message_id,
            "event_id": event.event_id,
            "external_user_id": event.user.external_user_id,
            "openxflow_user_id": str(user.id),
            "attachments": normalized_attachments,
            "message_metadata": dict(event.message.metadata),
        }
        if channel_context:
            context_payload.update(channel_context)
        context = {"channel": context_payload}
        request = SimplifiedAPIRequest(
            input_value=input_value,
            input_type="chat",
            output_type="chat",
            session_id=build_channel_session_id(event),
            user_id=f"{event.channel.value}:{event.user.external_user_id}",
        )
        response = await simple_run_flow(
            flow,
            request,
            api_key_user=user,
            context=context,
        )
        return ChannelMessage(
            message_type=ChannelMessageType.MARKDOWN,
            title=flow.name,
            markdown=render_run_response(response),
            metadata={
                "flow_id": str(flow.id),
                "session_id": response.session_id,
            },
        )
