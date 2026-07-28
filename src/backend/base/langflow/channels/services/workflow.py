"""Execute OpenXFlow workflows from normalized channel messages."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from uuid import UUID

from fastapi import HTTPException, status
from lfx.log.logger import logger

from langflow.channels.domain.models import ChannelEvent, ChannelMessage, ChannelMessageType
from langflow.channels.services.conversation_scope import conversation_scope_id
from langflow.helpers.flow import get_flow_by_id_or_endpoint_name
from langflow.services.authorization import FlowAction, ensure_flow_permission
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelContextMode,
    ChannelConversationBinding,
)
from langflow.services.database.models.flow.model import Flow
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord
from langflow.services.deps import get_variable_service, session_scope

if TYPE_CHECKING:
    from langflow.api.v1.schemas import RunResponse
    from langflow.services.database.models.user.model import User

_TELEGRAM_SAFE_TEXT_LIMIT = 3900
_PREFERRED_OUTPUT_KEYS = ("text", "message", "content", "result", "results", "data")
_TABLE_LOAD_FROM_DB_FIELDS = "__load_from_db_fields"
_MAX_TEXT_CANDIDATE_DEPTH = 8


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
    if depth > _MAX_TEXT_CANDIDATE_DEPTH or value is None:
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
        candidates: list[str] = []
        for nested in value:
            candidates.extend(_collect_text_candidates(nested, depth=depth + 1))
        return candidates
    return []


def _collect_chat_output_messages(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    candidates: list[str] = []
    for raw_run_output in value:
        run_output = (
            raw_run_output.model_dump(exclude_none=True)
            if hasattr(raw_run_output, "model_dump")
            else raw_run_output
        )
        if not isinstance(run_output, dict):
            continue
        result_items = run_output.get("outputs")
        if not isinstance(result_items, (list, tuple)):
            continue
        for raw_result_item in result_items:
            result_item = (
                raw_result_item.model_dump(exclude_none=True)
                if hasattr(raw_result_item, "model_dump")
                else raw_result_item
            )
            if not isinstance(result_item, dict):
                continue
            messages = result_item.get("messages")
            if not isinstance(messages, (list, tuple)):
                continue
            for raw_message in messages:
                message = (
                    raw_message.model_dump(exclude_none=True)
                    if hasattr(raw_message, "model_dump")
                    else raw_message
                )
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


async def _build_service_model_provider_access(
    *,
    channel_context: dict[str, Any] | None,
    service_user_id: UUID,
    flow: Flow,
) -> dict[str, str]:
    """Validate the explicit shared-flow grant used for model-provider delegation."""
    context = channel_context or {}
    try:
        connection_id = UUID(str(context.get("connection_id") or ""))
        granted_flow_id = UUID(str(context.get("granted_flow_id") or ""))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid channel model-provider grant context",
        ) from exc

    if granted_flow_id != flow.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The channel route is not granted this workflow",
        )

    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)

    if connection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel connection not found")
    if connection.service_user_id != service_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The channel service identity is not granted this connection",
        )
    if connection.user_id != flow.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared workflows can only use the connection owner's model providers",
        )

    return {
        "connection_id": str(connection.id),
        "flow_id": str(flow.id),
        "resource_owner_user_id": str(flow.user_id),
        "service_user_id": str(service_user_id),
    }


async def _build_service_knowledge_base_access(
    *,
    channel_context: dict[str, Any] | None,
    service_user_id: UUID,
    flow_owner_user_id: UUID,
) -> dict[str, str] | None:
    """Validate and return one explicitly granted KB owner delegation."""
    context = channel_context or {}
    raw_knowledge_base_id = context.get("knowledge_base_id")
    if not raw_knowledge_base_id:
        return None

    try:
        connection_id = UUID(str(context.get("connection_id") or ""))
        knowledge_base_id = UUID(str(raw_knowledge_base_id))
        raw_binding_id = context.get("conversation_binding_id")
        binding_id = UUID(str(raw_binding_id)) if raw_binding_id else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid channel knowledge-base grant context",
        ) from exc

    async with session_scope() as session:
        connection = await session.get(ChannelConnection, connection_id)
        knowledge_base = await session.get(KnowledgeBaseRecord, knowledge_base_id)
        binding = await session.get(ChannelConversationBinding, binding_id) if binding_id is not None else None

    if connection is None or knowledge_base is None or (binding_id is not None and binding is None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge base grant not found")
    if connection.service_user_id != service_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The channel service identity is not granted this knowledge base",
        )
    if connection.user_id != flow_owner_user_id or knowledge_base.user_id != flow_owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shared workflows can only use the connection owner's knowledge base",
        )
    if binding is not None and binding.connection_id != connection.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The conversation knowledge-base grant belongs to another connection",
        )

    expected_knowledge_base_id = (
        binding.knowledge_base_id
        if binding is not None and binding.knowledge_base_id is not None
        else connection.default_knowledge_base_id
    )
    if expected_knowledge_base_id != knowledge_base.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The knowledge base is not explicitly granted to this channel route",
        )

    configured_name = str(context.get("knowledge_base_name") or "").strip()
    if configured_name and configured_name != knowledge_base.name:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The channel knowledge-base grant does not match the selected resource",
        )

    return {
        "connection_id": str(connection.id),
        "knowledge_base_id": str(knowledge_base.id),
        "knowledge_base_name": knowledge_base.name,
        "resource_owner_user_id": str(knowledge_base.user_id),
        "service_user_id": str(service_user_id),
    }


_CHANNEL_KB_USER_SCOPE_MARKER = "# OpenXFlow channel knowledge-base owner scope"
_CHANNEL_KB_USER_SCOPE_PROPERTY = """
    # OpenXFlow channel knowledge-base owner scope
    @property
    def user_id(self):
        current_user_id = super().user_id
        try:
            channel_context = self.graph.context.get("channel") or {}
            access = channel_context.get("knowledge_base_access") or {}
        except (AttributeError, TypeError):
            return current_user_id
        if channel_context.get("execution_identity_type") != "service":
            return current_user_id
        if str(access.get("service_user_id") or "") != str(current_user_id):
            return current_user_id
        if str(access.get("connection_id") or "") != str(channel_context.get("connection_id") or ""):
            return current_user_id
        if str(access.get("knowledge_base_id") or "") != str(channel_context.get("knowledge_base_id") or ""):
            return current_user_id
        selected_knowledge_base = str(getattr(self, "knowledge_base", "") or "")
        if str(access.get("knowledge_base_name") or "") != selected_knowledge_base:
            return current_user_id
        owner_user_id = access.get("resource_owner_user_id")
        if not owner_user_id:
            return current_user_id
        try:
            return type(current_user_id)(str(owner_user_id))
        except (TypeError, ValueError):
            return str(owner_user_id)
"""
_CHANNEL_KB_CLASS_MARKERS = (
    "class KnowledgeComponent(Component):\n",
    "class KnowledgeBaseComponent(Component):\n",
    "class KnowledgeBaseComponent(KnowledgeComponent):\n",
    "class KnowledgeIngestionComponent(Component):\n",
    "class KnowledgeIngestionComponent(KnowledgeComponent):\n",
)


def _apply_service_knowledge_base_scope(flow: Flow, access: dict[str, str] | None) -> Flow:
    """Patch only selected Knowledge nodes in the in-memory service-run flow copy."""
    if access is None or not isinstance(flow.data, dict):
        return flow

    selected_name = access.get("knowledge_base_name")
    if not selected_name:
        return flow

    graph_data = deepcopy(flow.data)
    nodes = graph_data.get("nodes")
    if not isinstance(nodes, list):
        return flow

    patched_nodes = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_data = (node.get("data") or {}).get("node")
        if not isinstance(node_data, dict):
            continue
        template = node_data.get("template")
        if not isinstance(template, dict):
            continue
        knowledge_base_field = template.get("knowledge_base")
        if not isinstance(knowledge_base_field, dict) or knowledge_base_field.get("value") != selected_name:
            continue
        code_field = template.get("code")
        if not isinstance(code_field, dict):
            continue
        code = code_field.get("value")
        if not isinstance(code, str) or _CHANNEL_KB_USER_SCOPE_MARKER in code:
            continue
        class_marker = next((candidate for candidate in _CHANNEL_KB_CLASS_MARKERS if candidate in code), None)
        if class_marker is None:
            continue
        code_field["value"] = code.replace(
            class_marker,
            f"{class_marker}{_CHANNEL_KB_USER_SCOPE_PROPERTY}",
            1,
        )
        patched_nodes += 1

    if patched_nodes == 0:
        return flow
    return flow.model_copy(update={"data": graph_data})


_CHANNEL_MODEL_USER_SCOPE_MARKER = "# OpenXFlow channel model-provider owner scope"
_CHANNEL_MODEL_USER_SCOPE_PROPERTY = """
    # OpenXFlow channel model-provider owner scope
    @property
    def user_id(self):
        current_user_id = super().user_id
        try:
            channel_context = self.graph.context.get("channel") or {}
            access = channel_context.get("model_provider_access") or {}
        except (AttributeError, TypeError):
            return current_user_id
        if channel_context.get("execution_identity_type") != "service":
            return current_user_id
        if str(access.get("service_user_id") or "") != str(current_user_id):
            return current_user_id
        if str(access.get("connection_id") or "") != str(channel_context.get("connection_id") or ""):
            return current_user_id
        if str(access.get("flow_id") or "") != str(channel_context.get("granted_flow_id") or ""):
            return current_user_id
        owner_user_id = access.get("resource_owner_user_id")
        if not owner_user_id:
            return current_user_id
        try:
            return type(current_user_id)(str(owner_user_id))
        except (TypeError, ValueError):
            return str(owner_user_id)
"""
_CHANNEL_MODEL_CLASS_MARKERS = (
    "class LanguageModelComponent(LCModelComponent):\n",
    "class AgentComponent(ToolsAgentComponent):\n",
    "class AgentComponent(Component):\n",
)


def _apply_service_model_provider_scope(flow: Flow, access: dict[str, str] | None) -> Flow:
    """Delegate provider settings only to model-bearing nodes in the granted flow copy."""
    if access is None or not isinstance(flow.data, dict):
        return flow

    graph_data = deepcopy(flow.data)
    nodes = graph_data.get("nodes")
    if not isinstance(nodes, list):
        return flow

    patched_nodes = 0
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_data = (node.get("data") or {}).get("node")
        if not isinstance(node_data, dict):
            continue
        template = node_data.get("template")
        if not isinstance(template, dict) or not any(key in template for key in ("model", "language_model")):
            continue
        code_field = template.get("code")
        if not isinstance(code_field, dict):
            continue
        code = code_field.get("value")
        if not isinstance(code, str) or _CHANNEL_MODEL_USER_SCOPE_MARKER in code:
            continue
        class_marker = next((candidate for candidate in _CHANNEL_MODEL_CLASS_MARKERS if candidate in code), None)
        if class_marker is None:
            continue
        code_field["value"] = code.replace(
            class_marker,
            f"{class_marker}{_CHANNEL_MODEL_USER_SCOPE_PROPERTY}",
            1,
        )
        patched_nodes += 1

    if patched_nodes == 0:
        return flow
    return flow.model_copy(update={"data": graph_data})


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
        delegated_knowledge_base_access: dict[str, str] | None = None
        delegated_model_provider_access: dict[str, str] | None = None
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
            delegated_model_provider_access = await _build_service_model_provider_access(
                channel_context=channel_context,
                service_user_id=user.id,
                flow=flow,
            )
            delegated_knowledge_base_access = await _build_service_knowledge_base_access(
                channel_context=channel_context,
                service_user_id=user.id,
                flow_owner_user_id=flow.user_id,
            )
            flow, delegated_request_variables = await _prepare_service_flow_credentials(flow)
            flow = _apply_service_knowledge_base_scope(flow, delegated_knowledge_base_access)
            flow = _apply_service_model_provider_scope(flow, delegated_model_provider_access)
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
        context_payload.pop("knowledge_base_access", None)
        context_payload.pop("model_provider_access", None)
        if delegated_knowledge_base_access is not None:
            context_payload["knowledge_base_access"] = delegated_knowledge_base_access
        if delegated_model_provider_access is not None:
            context_payload["model_provider_access"] = delegated_model_provider_access
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
