from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.services.loop_lock import LoopLocalAsyncLock


def test_provider_token_locks_are_declared_as_loop_local() -> None:
    assert isinstance(FeishuChannelAdapter._token_lock, LoopLocalAsyncLock)
    assert isinstance(WeComChannelAdapter._token_lock, LoopLocalAsyncLock)


def test_provider_token_locks_are_not_shared_between_adapters() -> None:
    assert FeishuChannelAdapter._token_lock is not WeComChannelAdapter._token_lock
