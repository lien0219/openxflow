"""DingTalk enterprise robot adapter for Stream and signed webhook callbacks."""

from __future__ import annotations

import base64
import hashlib
import hmac
import importlib.util
import json
import time
from datetime import datetime, timezone
from typing import Any, ClassVar
from urllib.parse import unquote_plus, urlparse
from uuid import UUID

import httpx

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAttachment,
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelType,
    ChannelUser,
)
from langflow.channels.services.loop_lock import LoopLocalAsyncLock

_DINGTALK_SIGNATURE_MAX_AGE_MS = 60 * 60 * 1000
_DINGTALK_DOWNLOAD_HOST_SUFFIXES = (".aliyuncs.com", ".dingtalk.com")


class DingTalkAPIError(RuntimeError):
    """Raised when DingTalk returns an HTTP or business-level error."""


class DingTalkChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.DINGTALK
    _token_cache: ClassVar[dict[str, tuple[str, float]]] = {}
    _token_lock: ClassVar[LoopLocalAsyncLock] = LoopLocalAsyncLock()

    def __init__(
        self,
        connection_id: UUID,
        *,
        client_id: str,
        client_secret: str,
        robot_code: str | None = None,
        api_base_url: str = "https://api.dingtalk.com",
        timeout_seconds: float = 30.0,
        stream_authenticated: bool = False,
    ) -> None:
        if not client_id.strip() or not client_secret.strip():
            raise ValueError("DingTalk client_id and client_secret are required")
        self.connection_id = connection_id
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.robot_code = (robot_code or client_id).strip()
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.stream_authenticated = stream_authenticated

    @property
    def _token_cache_key(self) -> str:
        return f"{self.api_base_url}:{self.client_id}"

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        now = time.monotonic()
        cached = self._token_cache.get(self._token_cache_key)
        if not force_refresh and cached is not None and cached[1] > now:
            return cached[0]

        async with self._token_lock:
            now = time.monotonic()
            cached = self._token_cache.get(self._token_cache_key)
            if not force_refresh and cached is not None and cached[1] > now:
                return cached[0]

            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    f"{self.api_base_url}/v1.0/oauth2/accessToken",
                    json={"clientId": self.client_id, "clientSecret": self.client_secret},
                )
            response.raise_for_status()
            body = response.json()
            token = body.get("accessToken")
            if not token:
                raise DingTalkAPIError(str(body.get("message") or body.get("msg") or "DingTalk access token missing"))
            expire_seconds = max(60, int(body.get("expireIn", 7200)))
            self._token_cache[self._token_cache_key] = (
                str(token),
                time.monotonic() + max(30, expire_seconds - 60),
            )
            return str(token)

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                json=payload,
                headers={"x-acs-dingtalk-access-token": token},
            )
        response.raise_for_status()
        if not response.content:
            return {}
        body = response.json()
        if isinstance(body, dict) and body.get("code") not in {None, "", 0, "0"}:
            raise DingTalkAPIError(str(body.get("message") or body.get("msg") or body["code"]))
        return body if isinstance(body, dict) else {}

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        del payload
        if self.stream_authenticated:
            return True
        timestamp = headers.get("timestamp") or headers.get("x-dingtalk-timestamp") or ""
        provided_sign = headers.get("sign") or headers.get("x-dingtalk-signature") or ""
        if not timestamp or not provided_sign:
            return False
        try:
            timestamp_value = int(timestamp)
        except ValueError:
            return False
        if abs(int(time.time() * 1000) - timestamp_value) > _DINGTALK_SIGNATURE_MAX_AGE_MS:
            return False
        string_to_sign = f"{timestamp}\n{self.client_secret}"
        digest = hmac.new(
            self.client_secret.encode(),
            string_to_sign.encode(),
            hashlib.sha256,
        ).digest()
        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(unquote_plus(provided_sign), expected)

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        try:
            body = json.loads(payload.decode("utf-8"))
            if isinstance(body.get("data"), str):
                body = json.loads(body["data"])
            elif isinstance(body.get("data"), dict):
                body = body["data"]
            if not isinstance(body, dict):
                raise TypeError("DingTalk payload must be an object")
            return self._parse_message(body)
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError("Invalid DingTalk robot payload") from exc

    def _parse_message(self, body: dict[str, Any]) -> ChannelEvent:
        message_id = str(body.get("msgId") or body.get("messageId") or "").strip()
        if not message_id:
            raise ValueError("DingTalk message ID is missing")
        sender_id = str(body.get("senderStaffId") or body.get("senderId") or "").strip()
        if not sender_id:
            raise ValueError("DingTalk sender ID is missing")

        conversation_type_value = str(body.get("conversationType") or "1")
        is_group = conversation_type_value == "2"
        raw_conversation_id = str(body.get("conversationId") or "").strip()
        external_conversation_id = (
            f"group:{raw_conversation_id}" if is_group else f"user:{sender_id}"
        )
        if is_group and not raw_conversation_id:
            raise ValueError("DingTalk group conversation ID is missing")

        msg_type = str(body.get("msgtype") or "text")
        text, attachments = self._extract_content(body, msg_type, message_id)
        event_type = self._event_type(msg_type, text, attachments)
        mentions = []
        if bool(body.get("isInAtList")):
            mentions.append(str(body.get("chatbotUserId") or body.get("robotCode") or "__bot__"))
        mentions.extend(
            str(item.get("staffId") or item.get("dingtalkId") or "")
            for item in body.get("atUsers") or []
            if isinstance(item, dict)
        )

        create_at = body.get("createAt")
        timestamp = datetime.now(timezone.utc)
        if isinstance(create_at, (int, float)):
            timestamp = datetime.fromtimestamp(float(create_at) / 1000, tz=timezone.utc)

        session_webhook = str(body.get("sessionWebhook") or "")
        session_expired = body.get("sessionWebhookExpiredTime")
        return ChannelEvent(
            event_id=message_id,
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=event_type,
            user=ChannelUser(
                external_user_id=sender_id,
                display_name=str(body.get("senderNick") or "") or None,
                tenant_id=str(body.get("senderCorpId") or body.get("chatbotCorpId") or "") or None,
                metadata={
                    "sender_id": body.get("senderId"),
                    "sender_staff_id": body.get("senderStaffId"),
                    "is_admin": body.get("isAdmin"),
                },
            ),
            conversation=ChannelConversation(
                external_conversation_id=external_conversation_id,
                conversation_type="group" if is_group else "private",
                title=str(body.get("conversationTitle") or "") or None,
                metadata={
                    "conversation_id": raw_conversation_id,
                    "conversation_type": conversation_type_value,
                },
            ),
            message=ChannelIncomingMessage(
                external_message_id=message_id,
                message_type=event_type,
                text=text,
                mentions=[item for item in mentions if item],
                attachments=attachments,
                metadata={
                    "dingtalk_msg_type": msg_type,
                    "session_webhook": session_webhook,
                    "session_webhook_expired_time": session_expired,
                    "robot_code": str(body.get("robotCode") or self.robot_code),
                },
            ),
            timestamp=timestamp,
            raw_payload=body,
        )

    def _extract_content(
        self,
        body: dict[str, Any],
        msg_type: str,
        message_id: str,
    ) -> tuple[str | None, list[ChannelAttachment]]:
        if msg_type == "text":
            text_block = body.get("text") or {}
            text = str(text_block.get("content") or "").strip()
            return text or None, []

        content = body.get("content") or {}
        if not isinstance(content, dict):
            content = {}
        robot_code = str(body.get("robotCode") or self.robot_code)

        if msg_type == "richText":
            fragments: list[str] = []
            attachments: list[ChannelAttachment] = []
            for index, item in enumerate(content.get("richText") or []):
                if not isinstance(item, dict):
                    continue
                value = item.get("text")
                if isinstance(value, str) and value.strip():
                    fragments.append(value.strip())
                download_code = item.get("downloadCode") or item.get("pictureDownloadCode")
                if download_code:
                    filename = str(item.get("fileName") or f"dingtalk-rich-{message_id}-{index}.png")
                    attachments.append(
                        self._attachment(
                            str(download_code),
                            robot_code,
                            filename,
                            "image" if not item.get("fileName") else "file",
                        )
                    )
            return "\n".join(fragments) or None, attachments

        download_code = content.get("downloadCode") or content.get("pictureDownloadCode")
        if not download_code:
            return None, []
        default_names = {
            "picture": f"dingtalk-{message_id}.png",
            "audio": f"dingtalk-{message_id}.amr",
            "video": f"dingtalk-{message_id}.mp4",
        }
        filename = str(content.get("fileName") or default_names.get(msg_type) or f"dingtalk-{message_id}")
        kind = "image" if msg_type == "picture" else "audio" if msg_type == "audio" else "file"
        return None, [self._attachment(str(download_code), robot_code, filename, kind)]

    @staticmethod
    def _event_type(
        msg_type: str,
        text: str | None,
        attachments: list[ChannelAttachment],
    ) -> ChannelEventType:
        if text is not None:
            return ChannelEventType.COMMAND if text.lstrip().startswith("/") else ChannelEventType.TEXT
        if attachments:
            kind = attachments[0].metadata.get("kind")
            if kind == "image":
                return ChannelEventType.IMAGE
            if kind == "audio":
                return ChannelEventType.AUDIO
            return ChannelEventType.FILE
        return ChannelEventType.UNKNOWN

    @classmethod
    def _attachment(
        cls,
        download_code: str,
        robot_code: str,
        filename: str,
        kind: str,
    ) -> ChannelAttachment:
        identifier = cls._encode_file_identifier(
            {"download_code": download_code, "robot_code": robot_code, "filename": filename}
        )
        return ChannelAttachment(
            external_file_id=identifier,
            filename=filename,
            metadata={"kind": kind, "download_code": download_code, "robot_code": robot_code},
        )

    @staticmethod
    def _encode_file_identifier(value: dict[str, str]) -> str:
        encoded = base64.urlsafe_b64encode(json.dumps(value, ensure_ascii=False).encode()).decode().rstrip("=")
        return f"dingtalk:{encoded}"

    @staticmethod
    def _decode_file_identifier(value: str) -> dict[str, str]:
        prefix, separator, encoded = value.partition(":")
        if prefix != "dingtalk" or not separator or not encoded:
            raise ValueError("Invalid DingTalk file identifier")
        padded = encoded + "=" * (-len(encoded) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(data, dict) or not data.get("download_code"):
            raise ValueError("Invalid DingTalk file identifier")
        return {str(key): str(item) for key, item in data.items()}

    async def send_response(self, event: ChannelEvent, message: ChannelMessage) -> str:
        session_webhook = str(event.message.metadata.get("session_webhook") or "")
        expired_at = event.message.metadata.get("session_webhook_expired_time")
        if session_webhook and not self._is_session_webhook_expired(expired_at):
            await self._post_session_webhook(session_webhook, self._render_webhook_message(message))
            return event.message.external_message_id
        return await self.send_message(event.conversation.external_conversation_id, message)

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        msg_param = self._render_openapi_message(message)
        if target_id.startswith("user:"):
            user_id = target_id.removeprefix("user:")
            body = await self._api_request(
                "POST",
                "/v1.0/robot/oToMessages/batchSend",
                payload={
                    "robotCode": self.robot_code,
                    "userIds": [user_id],
                    "msgKey": "sampleMarkdown",
                    "msgParam": json.dumps(msg_param, ensure_ascii=False),
                },
            )
        else:
            conversation_id = target_id.removeprefix("group:")
            body = await self._api_request(
                "POST",
                "/v1.0/robot/groupMessages/send",
                payload={
                    "robotCode": self.robot_code,
                    "openConversationId": conversation_id,
                    "msgKey": "sampleMarkdown",
                    "msgParam": json.dumps(msg_param, ensure_ascii=False),
                },
            )
        return str(body.get("processQueryKey") or body.get("messageId") or "")

    async def _post_session_webhook(self, webhook_url: str, payload: dict[str, Any]) -> None:
        self._validate_session_webhook(webhook_url)
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        if response.content:
            body = response.json()
            if isinstance(body, dict) and body.get("errcode") not in {None, 0, "0"}:
                raise DingTalkAPIError(str(body.get("errmsg") or body["errcode"]))

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        identifier = self._decode_file_identifier(external_file_id)
        response = await self._api_request(
            "POST",
            "/v1.0/robot/messageFiles/download",
            payload={
                "robotCode": identifier.get("robot_code") or self.robot_code,
                "downloadCode": identifier["download_code"],
            },
        )
        download_url = str(response.get("downloadUrl") or "")
        if not download_url:
            raise DingTalkAPIError("DingTalk download URL is missing")
        self._validate_download_url(download_url)
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            file_response = await client.get(download_url)
        file_response.raise_for_status()
        return file_response.content, {
            "content_type": file_response.headers.get("content-type"),
            "provider": "dingtalk",
            "filename": identifier.get("filename"),
        }

    async def healthcheck(self) -> dict[str, Any]:
        await self._access_token(force_refresh=True)
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "client_id": self.client_id,
            "robot_code": self.robot_code,
            "stream_sdk_available": importlib.util.find_spec("dingtalk_stream") is not None,
        }

    @staticmethod
    def _is_session_webhook_expired(value: Any) -> bool:
        if value in {None, ""}:
            return False
        try:
            return int(value) <= int(time.time() * 1000)
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _render_openapi_message(message: ChannelMessage) -> dict[str, str]:
        body = message.markdown or message.text or ""
        if message.actions:
            action_lines = [
                f"- **{action.label}**：`{action.value or action.action_id}`"
                for action in message.actions
            ]
            body = f"{body}\n\n" + "\n".join(action_lines)
        return {"title": message.title or "OpenXFlow", "text": body or message.title or "OpenXFlow"}

    @classmethod
    def _render_webhook_message(cls, message: ChannelMessage) -> dict[str, Any]:
        rendered = cls._render_openapi_message(message)
        return {
            "msgtype": "markdown",
            "markdown": rendered,
            "at": {"atUserIds": [], "isAtAll": False},
        }

    @staticmethod
    def _validate_session_webhook(raw_url: str) -> None:
        parsed = urlparse(raw_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not hostname.endswith(".dingtalk.com"):
            raise ValueError("Invalid DingTalk session webhook URL")

    @staticmethod
    def _validate_download_url(raw_url: str) -> None:
        parsed = urlparse(raw_url)
        hostname = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not any(
            hostname.endswith(suffix) for suffix in _DINGTALK_DOWNLOAD_HOST_SUFFIXES
        ):
            raise ValueError("Invalid DingTalk download URL")
