from uuid import uuid4

import pytest
from pydantic import ValidationError

from langflow.services.database.models.channel.model import (
    ChannelConnectionCreate,
    ChannelConversationBindingUpsert,
)


def test_channel_connection_create_normalizes_provider():
    payload = ChannelConnectionCreate(
        name="Phone bot",
        channel_type=" TELEGRAM ",
        credentials={"bot_token": "secret"},
    )

    assert payload.channel_type == "telegram"


def test_channel_connection_create_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        ChannelConnectionCreate(name="Unknown", channel_type="unknown")


def test_conversation_binding_accepts_flow_and_knowledge_base():
    flow_id = uuid4()
    knowledge_base_id = uuid4()

    binding = ChannelConversationBindingUpsert(
        external_conversation_id="chat-1",
        default_flow_id=flow_id,
        knowledge_base_id=knowledge_base_id,
    )

    assert binding.default_flow_id == flow_id
    assert binding.knowledge_base_id == knowledge_base_id
