from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.services.loop_lock import LoopLocalAsyncLock


def test_provider_token_locks_are_declared_as_loop_local() -> None:
    assert isinstance(DingTalkChannelAdapter._token_lock, LoopLocalAsyncLock)
    assert isinstance(FeishuChannelAdapter._token_lock, LoopLocalAsyncLock)
    assert isinstance(WeComChannelAdapter._token_lock, LoopLocalAsyncLock)


def test_provider_token_locks_are_not_shared_between_adapters() -> None:
    locks = {
        id(DingTalkChannelAdapter._token_lock),
        id(FeishuChannelAdapter._token_lock),
        id(WeComChannelAdapter._token_lock),
    }
    assert len(locks) == 3
