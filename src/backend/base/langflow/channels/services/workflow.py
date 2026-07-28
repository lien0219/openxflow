"""Execute OpenXFlow workflows from normalized channel messages."""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException, status
from lfx.log.logger import logger

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from langflow.services.database.models.channel.model import ChannelContextMode
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.user.model import User
from langflow.services.deps import get_variable_service, session_scope

if TYPE_CHECKING:
    from langflow.api.v1.schemas import RunResponse

_TELEGRAM_SAFE_TEXT_LIMIT = 3900
_PREFERRED_OUTPUT_KEYS = ("text", "message", "content", "result", "results", "data")
_TABLE_LOAD_FROM_DB_FIELDS = "__load_from_db_fields"


async def apply_global_variable_defaults(graph_data: dict[str, Any], user_id: UUID) -> dict[str, Any]:
    """Load the API helper lazily so channel service imports cannot form a router cycle."""
    from langflow.api.v1.global_variable_defaults import apply_global_variable_defaults as apply_defaults

    return await apply_defaults(graph_data, user_id)


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


def _table_cell_loads_from_db(metadata: Any, column_name: str) -> bool:
    if isinstance(metadata, dict) and column_name in metadata:
        return bool(metadata[column_name])
    if isinstance(metadata, list):
        return column_name in metadata
    return True


def _collect_delegated_variable_names(graph_data: dict[str, Any]) -> set[str]:
    """Return only global-variable names explicitly referenced by the workflow."""
    names: set[str] = set()
    nodes = graph_data.get("nodes")
    if not isinstance(nodes, list):
        return names

    for node in nodes:
        if not isinstance(node, dict):
            continue
        template = (node.get("data") or {}).get("node", {}).get("template")
        if not isinstance(template, dict):
            continue

        for field in template.values():
            if not isinstance(field, dict):
                continue

            if field.get("load_from_db") is True:
                variable_name = field.get("value")
                if isinstance(variable_name, str) and variable_name.strip():
                    names.add(variable_name.strip())

            if field.get("type") != "table":
                continue
            table_schema = field.get("table_schema")
            table_data = field.get("value")
            if not isinstance(table_schema, list) or not isinstance(table_data, list):
                continue

            load_columns = {
                column.get("name")
                for column in table_schema
                if isinstance(column, dict) and column.get("load_from_db") and isinstance(column.get("name"), str)
            }
            for row in table_data:
                if not isinstance(row, dict):
                    continue
                metadata = row.get(_TABLE_LOAD_FROM_DB_FIELDS)
                for column_name in load_columns:
                    if not _table_cell_loads_from_db(metadata, column_name):
                        continue
                    variable_name = row.get(column_name)
                    if isinstance(variable_name, str) and variable_name.strip():
                        names.add(variable_name.strip())

    return names


async def _load_delegated_request_variables(
    graph_data: dict[str, Any],
    *,
    owner_user_id: UUID,
) -> dict[str, Any]:
    """Load the flow owner's referenced variables without changing the execution identity."""
    variable_names = _collect_delegated_variable_names(graph_data)
    if not variable_names:
        return {}

    variable_service = get_variable_service()
    resolved: dict[str, Any] = {}
    async with session_scope() as session:
        for variable_name in sorted(variable_names):
            try:
                resolved[variable_name] = await variable_service.get_variable(
                    user_id=owner_user_id,
                    name=variable_name,
                    field="channel_service",
                    session=session,
                )
            except (TypeError, ValueError) as exc:
                await logger.adebug(
                    "Channel service identity could not resolve delegated variable %s for flow owner %s: %s",
                    variable_name,
                    owner_user_id,
                    exc,
                )
    return resolved


async def _prepare_service_flow_credentials(flow: Flow) -> tuple[Flow, dict[str, Any]]:
    """Prepare a service-run copy of the flow with least-privilege credential delegation."""
    if not isinstance(flow.data, dict):
        return flow, {}

    graph_data = await apply_global_variable_defaults(flow.data, flow.user_id)
    request_variables = await _load_delegated_request_variables(
        graph_data,
        owner_user_id=flow.user_id,
    )
    return flow.model_copy(update={"data": graph_data}), request_variables


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

        delegated_request_variables: dict[str, Any] = {}
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
            flow, delegated_request_variables = await _prepare_service_flow_credentials(flow)
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
        run_context: dict[str, Any] = {"channel": context_payload}
        if delegated_request_variables:
            run_context["request_variables"] = delegated_request_variables
        response = await simple_run_flow(
            flow,
            request,
            api_key_user=user,
            context=run_context,
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
