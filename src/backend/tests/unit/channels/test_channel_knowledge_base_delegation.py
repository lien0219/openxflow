from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from langflow.channels.services.workflow import (
    _apply_service_knowledge_base_scope,
    _build_service_knowledge_base_access,
)
from langflow.services.database.models.channel.model import (
    ChannelConnection,
    ChannelConversationBinding,
)
from langflow.services.database.models.knowledge_base.model import KnowledgeBaseRecord


def _session_context(session: MagicMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


@pytest.mark.asyncio
async def test_service_knowledge_base_access_accepts_explicit_conversation_grant() -> None:
    connection_id = uuid4()
    binding_id = uuid4()
    knowledge_base_id = uuid4()
    owner_user_id = uuid4()
    service_user_id = uuid4()

    connection = SimpleNamespace(
        id=connection_id,
        user_id=owner_user_id,
        service_user_id=service_user_id,
        default_knowledge_base_id=None,
    )
    binding = SimpleNamespace(
        id=binding_id,
        connection_id=connection_id,
        knowledge_base_id=knowledge_base_id,
    )
    knowledge_base = SimpleNamespace(
        id=knowledge_base_id,
        user_id=owner_user_id,
        name="openxflow-v5",
    )

    async def get_record(model, record_id):
        records = {
            (ChannelConnection, connection_id): connection,
            (ChannelConversationBinding, binding_id): binding,
            (KnowledgeBaseRecord, knowledge_base_id): knowledge_base,
        }
        return records.get((model, record_id))

    session = MagicMock()
    session.get = AsyncMock(side_effect=get_record)

    with patch(
        "langflow.channels.services.workflow.session_scope",
        return_value=_session_context(session),
    ):
        access = await _build_service_knowledge_base_access(
            channel_context={
                "connection_id": str(connection_id),
                "conversation_binding_id": str(binding_id),
                "knowledge_base_id": str(knowledge_base_id),
                "knowledge_base_name": "openxflow-v5",
            },
            service_user_id=service_user_id,
            flow_owner_user_id=owner_user_id,
        )

    assert access == {
        "connection_id": str(connection_id),
        "knowledge_base_id": str(knowledge_base_id),
        "knowledge_base_name": "openxflow-v5",
        "resource_owner_user_id": str(owner_user_id),
        "service_user_id": str(service_user_id),
    }


@pytest.mark.asyncio
async def test_service_knowledge_base_access_rejects_ungranted_knowledge_base() -> None:
    connection_id = uuid4()
    binding_id = uuid4()
    knowledge_base_id = uuid4()
    owner_user_id = uuid4()
    service_user_id = uuid4()

    connection = SimpleNamespace(
        id=connection_id,
        user_id=owner_user_id,
        service_user_id=service_user_id,
        default_knowledge_base_id=None,
    )
    binding = SimpleNamespace(
        id=binding_id,
        connection_id=connection_id,
        knowledge_base_id=uuid4(),
    )
    knowledge_base = SimpleNamespace(
        id=knowledge_base_id,
        user_id=owner_user_id,
        name="private-kb",
    )

    async def get_record(model, record_id):
        records = {
            (ChannelConnection, connection_id): connection,
            (ChannelConversationBinding, binding_id): binding,
            (KnowledgeBaseRecord, knowledge_base_id): knowledge_base,
        }
        return records.get((model, record_id))

    session = MagicMock()
    session.get = AsyncMock(side_effect=get_record)

    with (
        patch(
            "langflow.channels.services.workflow.session_scope",
            return_value=_session_context(session),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await _build_service_knowledge_base_access(
            channel_context={
                "connection_id": str(connection_id),
                "conversation_binding_id": str(binding_id),
                "knowledge_base_id": str(knowledge_base_id),
                "knowledge_base_name": "private-kb",
            },
            service_user_id=service_user_id,
            flow_owner_user_id=owner_user_id,
        )

    assert exc_info.value.status_code == 403


def test_service_scope_is_injected_only_into_the_selected_knowledge_node() -> None:
    owner_user_id = uuid4()
    service_user_id = uuid4()
    connection_id = uuid4()
    knowledge_base_id = uuid4()
    knowledge_code = '''
class Component:
    @property
    def user_id(self):
        return self.graph.user_id

class KnowledgeComponent(Component):
    """Knowledge component."""
'''
    other_code = knowledge_code
    graph_data = {
        "nodes": [
            {
                "data": {
                    "node": {
                        "template": {
                            "knowledge_base": {"value": "openxflow-v5"},
                            "code": {"value": knowledge_code},
                        }
                    }
                }
            },
            {
                "data": {
                    "node": {
                        "template": {
                            "knowledge_base": {"value": "other-kb"},
                            "code": {"value": other_code},
                        }
                    }
                }
            },
        ]
    }
    patched_flow = MagicMock()
    flow = MagicMock()
    flow.data = graph_data
    flow.model_copy.return_value = patched_flow
    access = {
        "connection_id": str(connection_id),
        "knowledge_base_id": str(knowledge_base_id),
        "knowledge_base_name": "openxflow-v5",
        "resource_owner_user_id": str(owner_user_id),
        "service_user_id": str(service_user_id),
    }

    result = _apply_service_knowledge_base_scope(flow, access)

    assert result is patched_flow
    patched_data = flow.model_copy.call_args.kwargs["update"]["data"]
    patched_code = patched_data["nodes"][0]["data"]["node"]["template"]["code"]["value"]
    unchanged_code = patched_data["nodes"][1]["data"]["node"]["template"]["code"]["value"]
    assert "OpenXFlow channel knowledge-base owner scope" in patched_code
    assert unchanged_code == other_code
    assert graph_data["nodes"][0]["data"]["node"]["template"]["code"]["value"] == knowledge_code

    namespace: dict[str, object] = {}
    exec(patched_code, namespace)
    component_class = namespace["KnowledgeComponent"]
    component = component_class()
    component.knowledge_base = "openxflow-v5"
    component.graph = SimpleNamespace(
        user_id=service_user_id,
        context={
            "channel": {
                "execution_identity_type": "service",
                "connection_id": str(connection_id),
                "knowledge_base_id": str(knowledge_base_id),
                "knowledge_base_access": access,
            }
        },
    )

    assert component.user_id == owner_user_id
    assert isinstance(component.user_id, UUID)
