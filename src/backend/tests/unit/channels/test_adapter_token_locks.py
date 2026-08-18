from uuid import uuid4

from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.dingtalk_resilient import ResilientDingTalkChannelAdapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.feishu_resilient import ResilientEncryptedFeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.adapters.wecom_resilient import ResilientWeComChannelAdapter
from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.loop_lock import LoopLocalAsyncLock


def test_provider_compatibility_locks_are_loop_local() -> None:
    assert isinstance(DingTalkChannelAdapter._token_lock, LoopLocalAsyncLock)
    assert isinstance(FeishuChannelAdapter._token_lock, LoopLocalAsyncLock)
    assert isinstance(WeComChannelAdapter._token_lock, LoopLocalAsyncLock)


def test_resilient_provider_token_lock_pools_are_independent() -> None:
    pools = (
        ResilientDingTalkChannelAdapter._token_lock_pool,
        ResilientEncryptedFeishuChannelAdapter._token_lock_pool,
        ResilientWeComChannelAdapter._token_lock_pool,
    )

    assert all(isinstance(pool, LoopLocalKeyedLockPool) for pool in pools)
    assert len({id(pool) for pool in pools}) == 3


def test_feishu_cache_key_changes_after_secret_rotation() -> None:
    first = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret-one",
        api_base_url="https://open.feishu.test/open-apis",
    )
    same = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret-one",
        api_base_url="https://open.feishu.test/open-apis/",
    )
    rotated = ResilientEncryptedFeishuChannelAdapter(
        uuid4(),
        app_id="cli-test",
        app_secret="secret-two",
        api_base_url="https://open.feishu.test/open-apis",
    )

    assert first._token_cache_key == same._token_cache_key
    assert first._token_cache_key != rotated._token_cache_key
    assert "secret-one" not in first._token_cache_key


def test_dingtalk_cache_key_changes_after_secret_rotation() -> None:
    first = ResilientDingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="secret-one",
        api_base_url="https://api.dingtalk.test",
    )
    rotated = ResilientDingTalkChannelAdapter(
        uuid4(),
        client_id="ding-client",
        client_secret="secret-two",
        api_base_url="https://api.dingtalk.test",
    )

    assert first._token_cache_key != rotated._token_cache_key
    assert "secret-one" not in first._token_cache_key


def test_wecom_cache_key_changes_after_secret_rotation() -> None:
    first = ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="corp-id",
        corp_secret="secret-one",
        agent_id=1,
        callback_token="callback-token",
        encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        api_base_url="https://qyapi.weixin.test",
    )
    rotated = ResilientWeComChannelAdapter(
        uuid4(),
        corp_id="corp-id",
        corp_secret="secret-two",
        agent_id=1,
        callback_token="callback-token",
        encoding_aes_key="abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        api_base_url="https://qyapi.weixin.test",
    )

    assert first._token_cache_key != rotated._token_cache_key
    assert "secret-one" not in first._token_cache_key
