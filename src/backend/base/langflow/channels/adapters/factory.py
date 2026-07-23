"""Construct provider adapters from persisted channel connections."""

from __future__ import annotations

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.adapters.dingtalk import DingTalkChannelAdapter
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
from langflow.channels.adapters.mock import MockChannelAdapter
from langflow.channels.adapters.telegram import TelegramChannelAdapter
from langflow.channels.adapters.wecom import WeComChannelAdapter
from langflow.channels.domain.models import ChannelType
from langflow.channels.security.credentials import decrypt_credentials
from langflow.services.database.models.channel.model import ChannelConnection


def build_channel_adapter(connection: ChannelConnection) -> ChannelAdapter:
    channel_type = ChannelType(connection.channel_type)
    credentials = decrypt_credentials(connection.credentials_encrypted)

    if channel_type is ChannelType.MOCK:
        return MockChannelAdapter(
            connection.id,
            verification_token=credentials.get("verification_token"),
        )
    if channel_type is ChannelType.TELEGRAM:
        return TelegramChannelAdapter(
            connection.id,
            bot_token=credentials.get("bot_token", ""),
            webhook_secret=credentials.get("webhook_secret"),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://api.telegram.org")),
        )
    if channel_type is ChannelType.FEISHU:
        return EncryptedFeishuChannelAdapter(
            connection.id,
            app_id=credentials.get("app_id", ""),
            app_secret=credentials.get("app_secret", ""),
            verification_token=credentials.get("verification_token"),
            encrypt_key=credentials.get("encrypt_key"),
            api_base_url=str(
                connection.settings_data.get(
                    "api_base_url",
                    "https://open.feishu.cn/open-apis",
                )
            ),
        )
    if channel_type is ChannelType.DINGTALK:
        return DingTalkChannelAdapter(
            connection.id,
            client_id=credentials.get("client_id", ""),
            client_secret=credentials.get("client_secret", ""),
            robot_code=credentials.get("robot_code"),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://api.dingtalk.com")),
        )
    if channel_type is ChannelType.WECOM:
        return WeComChannelAdapter(
            connection.id,
            corp_id=credentials.get("corp_id", ""),
            corp_secret=credentials.get("corp_secret", ""),
            agent_id=credentials.get("agent_id", ""),
            callback_token=credentials.get("callback_token", ""),
            encoding_aes_key=credentials.get("encoding_aes_key", ""),
            api_base_url=str(connection.settings_data.get("api_base_url", "https://qyapi.weixin.qq.com")),
        )

    msg = f"Channel adapter '{channel_type.value}' has not been implemented yet"
    raise NotImplementedError(msg)
