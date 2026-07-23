from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.security.credentials import encrypt_credentials


def test_factory_builds_resilient_encrypted_feishu_adapter() -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        channel_type="feishu",
        credentials_encrypted=encrypt_credentials(
            {
                "app_id": "cli-test",
                "app_secret": "secret",
                "verification_token": "verification-token",
                "encrypt_key": "encrypt-key",
            }
        ),
        settings_data={"api_base_url": "https://open.feishu.test/open-apis"},
    )

    adapter = build_channel_adapter(connection)

    assert isinstance(adapter, ResilientEncryptedFeishuChannelAdapter)
    assert isinstance(adapter, EncryptedFeishuChannelAdapter)
    assert isinstance(adapter, FeishuChannelAdapter)
    assert adapter.encrypt_key == "encrypt-key"


def test_factory_builds_resilient_dingtalk_adapter() -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        channel_type="dingtalk",
        credentials_encrypted=encrypt_credentials(
            {
                "client_id": "ding-client",
                "client_secret": "ding-secret",
                "robot_code": "robot-code",
            }
        ),
        settings_data={"api_base_url": "https://api.dingtalk.test"},
    )

    adapter = build_channel_adapter(connection)

    assert isinstance(adapter, ResilientDingTalkChannelAdapter)
    assert isinstance(adapter, DingTalkChannelAdapter)
    assert adapter.robot_code == "robot-code"
