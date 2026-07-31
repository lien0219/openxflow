"""Regression coverage for Feishu card actions preserving their source conversation."""

import json
from uuid import uuid4

import pytest
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.domain.models import (
    ChannelAction,
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelMessageType,
    ChannelType,
    ChannelUser,
)


def _adapter() -> FeishuChannelAdapter:
    return FeishuChannelAdapter(
        uuid4(),
        app_id="cli_test",
        app_secret="secret",
        verification_token="verify-token",
    )


def _event(*, chat_id: str, conversation_type: str) -> ChannelEvent:
    return ChannelEvent(
        event_id=f"event-{chat_id}",
        channel=ChannelType.FEISHU,
        connection_id=uuid4(),
        event_type=ChannelEventType.COMMAND,
        user=ChannelUser(external_user_id="ou_user"),
        conversation=ChannelConversation(
            external_conversation_id=chat_id,
            conversation_type=conversation_type,
        ),
        message=ChannelIncomingMessage(
            external_message_id=f"message-{chat_id}",
            message_type=ChannelEventType.COMMAND,
            text="/commands",
        ),
    )


async def _render_response_action_value(
    adapter: FeishuChannelAdapter,
    event: ChannelEvent,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    captured: dict = {}

    async def fake_request(method, path, *, params=None, payload=None):
        captured.update({"method": method, "path": path, "params": params, "payload": payload})
        return {"message_id": "sent-message"}

    monkeypatch.setattr(adapter, "_request", fake_request)
    await adapter.send_response(
        event,
        ChannelMessage(
            message_type=ChannelMessageType.CARD,
            title="Commands",
            text="Available",
            actions=[
                ChannelAction(
                    action_id="use-flow:deepseek",
                    label="切换 /deepseek",
                    value="/use-flow /deepseek",
                )
            ],
        ),
    )

    content = json.loads(captured["payload"]["content"])
    return content["elements"][1]["actions"][0]["value"]


@pytest.mark.asyncio
async def test_feishu_card_buttons_embed_private_and_group_context(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _adapter()

    private_value = await _render_response_action_value(
        adapter,
        _event(chat_id="oc_private", conversation_type="private"),
        monkeypatch,
    )
    group_value = await _render_response_action_value(
        adapter,
        _event(chat_id="oc_group", conversation_type="group"),
        monkeypatch,
    )

    assert private_value["value"] == "/use-flow /deepseek"
    assert private_value["__openxflow_chat_id"] == "oc_private"
    assert private_value["__openxflow_conversation_type"] == "private"
    assert group_value["__openxflow_chat_id"] == "oc_group"
    assert group_value["__openxflow_conversation_type"] == "group"


@pytest.mark.asyncio
async def test_feishu_card_callback_restores_embedded_origin_context() -> None:
    adapter = _adapter()
    payload = json.dumps(
        {
            "schema": "2.0",
            "header": {
                "event_id": "card-event",
                "event_type": "card.action.trigger",
                "tenant_key": "tenant-1",
                "token": "verify-token",
            },
            "event": {
                "operator": {"open_id": "ou_user"},
                "context": {
                    "open_chat_id": "oc_callback_context",
                    "open_message_id": "om_card",
                },
                "action": {
                    "tag": "button",
                    "value": {
                        "action_id": "use-flow:deepseek",
                        "value": "/use-flow /deepseek",
                        "__openxflow_chat_id": "oc_private",
                        "__openxflow_conversation_type": "private",
                    },
                },
            },
        }
    ).encode()

    event = await adapter.parse_event({}, payload)

    assert event.event_type == ChannelEventType.ACTION
    assert event.message.text == "/use-flow /deepseek"
    assert event.conversation.external_conversation_id == "oc_private"
    assert event.conversation.conversation_type == "private"
    assert event.conversation.metadata["callback_open_chat_id"] == "oc_callback_context"


@pytest.mark.asyncio
async def test_feishu_legacy_card_callback_keeps_provider_context() -> None:
    adapter = _adapter()
    payload = json.dumps(
        {
            "schema": "2.0",
            "header": {
                "event_id": "legacy-card-event",
                "event_type": "card.action.trigger",
                "tenant_key": "tenant-1",
                "token": "verify-token",
            },
            "event": {
                "operator": {"open_id": "ou_user"},
                "context": {
                    "open_chat_id": "oc_group",
                    "open_message_id": "om_legacy_card",
                },
                "action": {
                    "tag": "button",
                    "value": {
                        "action_id": "use-flow:deepseek",
                        "value": "/use-flow /deepseek",
                    },
                },
            },
        }
    ).encode()

    event = await adapter.parse_event({}, payload)

    assert event.conversation.external_conversation_id == "oc_group"
    assert event.conversation.conversation_type == "group"
