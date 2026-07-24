import inspect

import pytest
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter


@pytest.mark.parametrize(
    "adapter_class",
    [
        ResilientEncryptedFeishuChannelAdapter,
        ResilientDingTalkChannelAdapter,
        ResilientWeComChannelAdapter,
    ],
)
def test_resilient_token_implementations_use_shared_safe_contract(adapter_class) -> None:
    source = inspect.getsource(adapter_class)

    assert "get_cached_provider_token(" in source
    assert "provider_token_cache_key(" in source
    assert "response_json_object(" in source
    assert "provider_token_lifetime_seconds(" in source
    assert "response.json()" not in source
    assert "_token_lock:" not in source
    assert 'f"{self.api_base_url}:{' not in source
