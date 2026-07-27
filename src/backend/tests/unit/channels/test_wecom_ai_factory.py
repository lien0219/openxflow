import base64
from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.wecom_ai import WeComAIBotChannelAdapter

_KEY = base64.b64encode(bytes(range(32))).decode().rstrip("=")


def test_factory_builds_wecom_ai_bot_adapter(monkeypatch) -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        channel_type="wecom",
        connection_mode="ai_bot",
        credentials_encrypted="encrypted",
        settings_data={"timeout_seconds": 15},
    )
    monkeypatch.setattr(
        "langflow.channels.adapters.factory.decrypt_credentials",
        lambda _value: {
            "token": "callback-token",
            "encoding_aes_key": _KEY,
            "bot_name": "OpenXFlow",
        },
    )

    adapter = build_channel_adapter(connection)

    assert isinstance(adapter, WeComAIBotChannelAdapter)
    assert adapter.connection_id == connection.id
    assert adapter.bot_name == "OpenXFlow"
    assert adapter.timeout_seconds == 15
