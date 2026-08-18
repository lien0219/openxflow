from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from langflow.channels.services.workflow import (
    _apply_service_model_provider_scope,
    _build_service_model_provider_access,
)
from langflow.services.database.models.channel.model import ChannelConnection


def _session_context(session: MagicMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=None)
    return context


@pytest.mark.asyncio
async def test_service_model_provider_access_requires_owner_granted_flow() -> None:
    connection_id = uuid4()
    flow_id = uuid4()
    owner_user_id = uuid4()
    service_user_id = uuid4()
    connection = SimpleNamespace(
        id=connection_id,
        user_id=owner_user_id,
        service_user_id=service_user_id,
    )
    flow = SimpleNamespace(id=flow_id, user_id=owner_user_id)
    session = MagicMock()
    session.get = AsyncMock(
        side_effect=lambda model, record_id: (
            connection if model is ChannelConnection and record_id == connection_id else None
        )
    )

    with patch(
        "langflow.channels.services.workflow.session_scope",
        return_value=_session_context(session),
    ):
        access = await _build_service_model_provider_access(
            channel_context={
                "connection_id": str(connection_id),
                "granted_flow_id": str(flow_id),
            },
            service_user_id=service_user_id,
            flow=flow,
        )

    assert access == {
        "connection_id": str(connection_id),
        "flow_id": str(flow_id),
        "resource_owner_user_id": str(owner_user_id),
        "service_user_id": str(service_user_id),
    }


def test_service_model_scope_is_injected_only_into_model_nodes() -> None:
    owner_user_id = uuid4()
    service_user_id = uuid4()
    connection_id = uuid4()
    flow_id = uuid4()
    model_code = '''
class LCModelComponent:
    @property
    def user_id(self):
        return self.graph.user_id

class LanguageModelComponent(LCModelComponent):
    """Language model."""
'''
    other_code = '''
class Component:
    @property
    def user_id(self):
        return self.graph.user_id

class PromptComponent(Component):
    """Prompt."""
'''
    graph_data = {
        "nodes": [
            {
                "data": {
                    "node": {
                        "template": {
                            "model": {"value": {"provider": "OpenAI", "name": "gpt-5.5"}},
                            "code": {"value": model_code},
                        }
                    }
                }
            },
            {
                "data": {
                    "node": {
                        "template": {
                            "prompt": {"value": "hello"},
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
        "flow_id": str(flow_id),
        "resource_owner_user_id": str(owner_user_id),
        "service_user_id": str(service_user_id),
    }

    result = _apply_service_model_provider_scope(flow, access)

    assert result is patched_flow
    patched_data = flow.model_copy.call_args.kwargs["update"]["data"]
    patched_code = patched_data["nodes"][0]["data"]["node"]["template"]["code"]["value"]
    unchanged_code = patched_data["nodes"][1]["data"]["node"]["template"]["code"]["value"]
    assert "OpenXFlow channel model-provider owner scope" in patched_code
    assert unchanged_code == other_code
    assert graph_data["nodes"][0]["data"]["node"]["template"]["code"]["value"] == model_code

    namespace: dict[str, object] = {}
    exec(patched_code, namespace)  # noqa: S102
    component_class = namespace["LanguageModelComponent"]
    component = component_class()
    component.graph = SimpleNamespace(
        user_id=service_user_id,
        context={
            "channel": {
                "execution_identity_type": "service",
                "connection_id": str(connection_id),
                "granted_flow_id": str(flow_id),
                "model_provider_access": access,
            }
        },
    )

    assert component.user_id == owner_user_id
    assert isinstance(component.user_id, UUID)
