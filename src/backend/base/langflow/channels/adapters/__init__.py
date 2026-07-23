from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.adapters.dingtalk import DingTalkAPIError, DingTalkChannelAdapter
from langflow.channels.adapters.factory import build_channel_adapter
from langflow.channels.adapters.feishu import FeishuAPIError, FeishuChannelAdapter
from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.adapters.telegram import TelegramAPIError, TelegramChannelAdapter
from langflow.channels.adapters.wecom import WeComAPIError, WeComChannelAdapter
from langflow.channels.services.loop_lock import LoopLocalAsyncLock

# Token caches are shared at class scope. Use loop-local synchronization so
# reloaders and test clients cannot bind the shared lock to a stale event loop.
FeishuChannelAdapter._token_lock = LoopLocalAsyncLock()
WeComChannelAdapter._token_lock = LoopLocalAsyncLock()

__all__ = [
    "ChannelAdapter",
    "DingTalkAPIError",
    "DingTalkChannelAdapter",
    "FeishuAPIError",
    "FeishuChannelAdapter",
    "MockChannelAdapter",
    "TelegramAPIError",
    "TelegramChannelAdapter",
    "WeComAPIError",
    "WeComChannelAdapter",
    "build_channel_adapter",
]
