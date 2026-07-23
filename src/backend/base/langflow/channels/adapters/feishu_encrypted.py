"""Feishu adapter variant that transparently unwraps Encrypt Key events."""

from __future__ import annotations

import hmac
import json
from typing import Any
from uuid import UUID

from langflow.channels.adapters.feishu import FeishuChannelAdapter
from langflow.channels.domain.models import ChannelEvent
from langflow.channels.security.feishu_crypto import (
    FeishuCryptoError,
    unwrap_feishu_event_payload,
)


class EncryptedFeishuChannelAdapter(FeishuChannelAdapter):
    """Support both plaintext and Encrypt Key protected Feishu callbacks."""

    def __init__(
        self,
        connection_id: UUID,
        *,
        app_id: str,
        app_secret: str,
        verification_token: str | None = None,
        encrypt_key: str | None = None,
        api_base_url: str = "https://open.feishu.cn/open-apis",
        timeout_seconds: float = 30.0,
    ) -> None:
        super().__init__(
            connection_id,
            app_id=app_id,
            app_secret=app_secret,
            verification_token=verification_token,
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
        )
        self.encrypt_key = encrypt_key.strip() if encrypt_key else None

    def unwrap_payload(self, payload: bytes) -> bytes:
        return unwrap_feishu_event_payload(payload, self.encrypt_key)

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del headers
        try:
            plaintext = self.unwrap_payload(payload)
            body = json.loads(plaintext.decode("utf-8"))
        except (FeishuCryptoError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        if self.verification_token is None:
            return True
        provided = str(body.get("token") or (body.get("header") or {}).get("token") or "")
        return hmac.compare_digest(provided, self.verification_token)

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        plaintext = self.unwrap_payload(payload)
        return await super().parse_event(headers, plaintext)

    def is_url_verification(self, payload: bytes) -> bool:
        try:
            body = json.loads(self.unwrap_payload(payload).decode("utf-8"))
        except (FeishuCryptoError, UnicodeDecodeError, json.JSONDecodeError):
            return False
        return body.get("type") == "url_verification" and bool(body.get("challenge"))

    def get_url_verification_challenge(self, payload: bytes) -> str:
        body: dict[str, Any] = json.loads(self.unwrap_payload(payload).decode("utf-8"))
        return str(body["challenge"])
