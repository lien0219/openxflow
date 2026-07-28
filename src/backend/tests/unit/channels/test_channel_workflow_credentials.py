from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langflow.channels.services.workflow import (
    ChannelWorkflowExecutor,
    _collect_delegated_variable_names,
)
from langflow.services.database.models.channel.execution_model import ChannelExecutionIdentityType
from pydantic import SecretStr


class FakeRunResponse:
    session_id = "channel-session"

    def model_dump(self, *, exclude_none: bool = True) -> dict:
        del exclude_none
        return {
            "outputs": [
                {
                    "outputs": [
                        {
                            "messages": [
                                {
                                    "message": "飞书渠道凭据委托成功",
                                    "sender": "Machine",
                                }
                            ]
                        }
                    ]
                }
            ],
            "session_id": self.session_id,
        }


def _channel_event() -> SimpleNamespace:
    return SimpleNamespace(
        channel=SimpleNamespace(value="feishu"),
        connection_id=uuid4(),
        conversation=SimpleNamespace(
            external_conversation_id="oc_test",
            conversation_type="private",
            metadata={},
        ),
        user=SimpleNamespace(external_user_id="ou_test"),
        message=SimpleNamespace(
            attachments=[],
            external_message_id="om_test",
            metadata={},
        ),
        event_id="evt_test",
    )


def test_collect_delegated_variable_names_limits_scope_to_referenced_fields() -> None:
    graph_data = {
        "nodes": [
            {
                "data": {
                    "node": {
                        "template": {
                            "api_key": {
                                "type": "str",
                                "value": "DASHSCOPE_API_KEY",
                                "load_from_db": True,
                            },
                            "literal": {
                                "type": "str",
                                "value": "DO_NOT_DELEGATE",
                                "load_from_db": False,
                            },
                            "headers": {
                                "type": "table",
                                "value": [
                                    {
                                        "name": "Authorization",
                                        "value": "DASHSCOPE_HEADER",
                                        "__load_from_db_fields": ["value"],
                                    },
                                    {
                                        "name": "Literal",
                                        "value": "DO_NOT_DELEGATE_TABLE",
                                        "__load_from_db_fields": {"value": False},
                                    },
                                ],
                                "table_schema": [
                                    {"name": "name", "load_from_db": False},
                                    {"name": "value", "load_from_db": True},
                                ],
                            },
                        }
                    }
                }
            }
        ]
    }

    assert _collect_delegated_variable_names(graph_data) == {
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_HEADER",
    }


@pytest.mark.asyncio
async def test_service_identity_executes_with_owner_variables_but_keeps_service_user() -> None:
    flow_id = uuid4()
    owner_user_id = uuid4()
    service_user_id = uuid4()
    graph_data = {
        "nodes": [
            {
                "data": {
                    "node": {
                        "template": {
                            "api_key": {
                                "type": "str",
                                "value": "DASHSCOPE_API_KEY",
                                "load_from_db": True,
                            }
                        }
                    }
                }
            }
        ]
    }

    flow = MagicMock()
    flow.id = flow_id
    flow.user_id = owner_user_id
    flow.name = "千问AI"
    flow.data = graph_data

    prepared_flow = MagicMock()
    prepared_flow.id = flow_id
    prepared_flow.user_id = owner_user_id
    prepared_flow.name = flow.name
    prepared_flow.data = graph_data
    flow.model_copy.return_value = prepared_flow

    session = MagicMock()
    session.get = AsyncMock(return_value=flow)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=session)
    session_cm.__aexit__ = AsyncMock(return_value=None)

    variable_service = MagicMock()
    variable_service.get_variable = AsyncMock(return_value=SecretStr("sk-owner-qwen"))

    simple_run_flow = AsyncMock(return_value=FakeRunResponse())
    service_user = SimpleNamespace(id=service_user_id)

    with (
        patch(
            "langflow.channels.services.workflow.session_scope",
            return_value=session_cm,
        ),
        patch(
            "langflow.channels.services.workflow.get_variable_service",
            return_value=variable_service,
        ),
        patch(
            "langflow.channels.services.workflow.apply_global_variable_defaults",
            new=AsyncMock(return_value=graph_data),
        ),
        patch(
            "langflow.api.v1.endpoints.simple_run_flow",
            new=simple_run_flow,
        ),
    ):
        result = await ChannelWorkflowExecutor().execute(
            event=_channel_event(),
            user=service_user,
            flow_identifier=str(flow_id),
            input_value="你好",
            session_id="channel-session",
            execution_identity_type=ChannelExecutionIdentityType.SERVICE.value,
            channel_context={"granted_flow_id": str(flow_id)},
        )

    flow.model_copy.assert_called_once_with(update={"data": graph_data})
    variable_service.get_variable.assert_awaited_once_with(
        user_id=owner_user_id,
        name="DASHSCOPE_API_KEY",
        field="channel_service",
        session=session,
    )

    call = simple_run_flow.await_args
    assert call.args[0] is prepared_flow
    assert call.kwargs["api_key_user"] is service_user

    context = call.kwargs["context"]
    delegated_secret = context["request_variables"]["DASHSCOPE_API_KEY"]
    assert isinstance(delegated_secret, SecretStr)
    assert delegated_secret.get_secret_value() == "sk-owner-qwen"
    assert context["channel"]["openxflow_user_id"] == str(service_user_id)
    assert result.markdown == "飞书渠道凭据委托成功"
