from uuid import uuid4

import pytest

from langflow.channels.adapters import dingtalk_resilient, feishu_resilient, wecom_resilient
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("module", "adapter", "method_name", "provider"),
    [
        (
            feishu_resilient,
            ResilientEncryptedFeishuChannelAdapter(
                uuid4(),
                app_id="feishu-app",
                app_secret="feishu-secret",
            ),
            "_tenant_access_token",
            "feishu",
        ),
        (
            dingtalk_resilient,
            ResilientDingTalkChannelAdapter(
                uuid4(),
                client_id="ding-app",
                client_secret="ding-secret",
            ),
            "_access_token",
            "dingtalk",
        ),
        (
            wecom_resilient,
            ResilientWeComChannelAdapter(
                uuid4(),
                corp_id="corp-id",
                corp_secret="corp-secret",
                agent_id=1,
                callback_token="callback-token",
                encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            ),
            "_access_token",
            "wecom",
        ),
    ],
)
async def test_resilient_adapters_delegate_token_cache_flow(
    monkeypatch: pytest.MonkeyPatch,
    module,
    adapter,
    method_name: str,
    provider: str,
) -> None:
    captured = {}

    async def cached_token(**kwargs) -> str:
        captured.update(kwargs)
        return "shared-token"

    monkeypatch.setattr(module, "get_cached_provider_token", cached_token)

    token = await getattr(adapter, method_name)(force_refresh=True)

    assert token == "shared-token"
    assert captured["provider"] == provider
    assert captured["cache"] is adapter._token_cache
    assert captured["cache_key"] == adapter._token_cache_key
    assert captured["force_refresh"] is True
    assert captured["lock_pool"] is adapter._token_lock_pool
    assert callable(captured["fetch_new_token"])
