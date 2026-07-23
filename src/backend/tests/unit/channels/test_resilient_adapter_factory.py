from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter
from langflow.channels.security.credentials import encrypt_credentials

_REPOSITORY_ROOT = Path(__file__).parents[5]
_FACTORY_SOURCE = _REPOSITORY_ROOT / "src/backend/base/langflow/channels/adapters/factory.py"
_STREAM_SOURCE = _REPOSITORY_ROOT / "src/backend/base/langflow/channels/services/dingtalk_stream.py"


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


def test_factory_builds_resilient_wecom_adapter() -> None:
    connection = SimpleNamespace(
        id=uuid4(),
        channel_type="wecom",
        credentials_encrypted=encrypt_credentials(
            {
                "corp_id": "corp-id",
                "corp_secret": "corp-secret",
                "agent_id": "1000002",
                "callback_token": "callback-token",
                "encoding_aes_key": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            }
        ),
        settings_data={"api_base_url": "https://qyapi.weixin.test"},
    )

    adapter = build_channel_adapter(connection)

    assert isinstance(adapter, ResilientWeComChannelAdapter)
    assert isinstance(adapter, WeComChannelAdapter)
    assert adapter.agent_id == 1000002


def test_production_entrypoints_only_construct_resilient_enterprise_adapters() -> None:
    factory_source = _FACTORY_SOURCE.read_text(encoding="utf-8")
    stream_source = _STREAM_SOURCE.read_text(encoding="utf-8")

    assert "return ResilientEncryptedFeishuChannelAdapter(" in factory_source
    assert "return ResilientDingTalkChannelAdapter(" in factory_source
    assert "return ResilientWeComChannelAdapter(" in factory_source
    assert "return FeishuChannelAdapter(" not in factory_source
    assert "return DingTalkChannelAdapter(" not in factory_source
    assert "return WeComChannelAdapter(" not in factory_source
    assert "from langflow.channels.adapters.dingtalk_resilient import" in stream_source
    assert "adapter = ResilientDingTalkChannelAdapter(" in stream_source
