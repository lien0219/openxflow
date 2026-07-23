"""Enterprise WeChat internal-application adapter."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, ClassVar
from urllib.parse import unquote
from uuid import UUID, uuid4

import httpx
from defusedxml import ElementTree as DefusedElementTree

from langflow.channels.adapters.base import ChannelAdapter
from langflow.channels.domain.models import (
    ChannelAttachment,
    ChannelConversation,
    ChannelEvent,
    ChannelEventType,
    ChannelIncomingMessage,
    ChannelMessage,
    ChannelMessageType,
    ChannelType,
    ChannelUser,
)
from langflow.channels.security.wecom_crypto import WeComCryptoError, WeComMessageCrypt
from langflow.channels.services.loop_lock import LoopLocalAsyncLock


class WeComAPIError(RuntimeError):
    """Raised when Enterprise WeChat returns a non-zero business code."""


class WeComChannelAdapter(ChannelAdapter):
    channel_type = ChannelType.WECOM
    _token_cache: ClassVar[dict[str, tuple[str, float]]] = {}
    _token_lock: ClassVar[LoopLocalAsyncLock] = LoopLocalAsyncLock()

    def __init__(
        self,
        connection_id: UUID,
        *,
        corp_id: str,
        corp_secret: str,
        agent_id: str | int,
        callback_token: str,
        encoding_aes_key: str,
        api_base_url: str = "https://qyapi.weixin.qq.com",
        timeout_seconds: float = 30.0,
    ) -> None:
        if not corp_id.strip() or not corp_secret.strip():
            raise ValueError("WeCom corp_id and corp_secret are required")
        try:
            parsed_agent_id = int(agent_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("WeCom agent_id must be an integer") from exc
        if parsed_agent_id <= 0:
            raise ValueError("WeCom agent_id must be positive")

        self.connection_id = connection_id
        self.corp_id = corp_id.strip()
        self.corp_secret = corp_secret.strip()
        self.agent_id = parsed_agent_id
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.crypt = WeComMessageCrypt(
            callback_token,
            encoding_aes_key,
            self.corp_id,
        )

    @property
    def _token_cache_key(self) -> str:
        secret_digest = hashlib.sha256(self.corp_secret.encode()).hexdigest()[:16]
        return f"{self.api_base_url}:{self.corp_id}:{secret_digest}"

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
                response = await client.get(
                    f"{self.api_base_url}/cgi-bin/gettoken",
                    params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
                )
            response.raise_for_status()
            body = response.json()
            self._raise_for_business_error(body)
            token = body.get("access_token")
            if not token:
                raise WeComAPIError("WeCom access token is missing")
            expires_in = max(60, int(body.get("expires_in", 7200)))
            self._token_cache[self._token_cache_key] = (
                str(token),
                time.monotonic() + max(30, expires_in - 60),
            )
            return str(token)

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        request_params = {"access_token": token, **(params or {})}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                params=request_params,
                json=payload,
            )
        response.raise_for_status()
        body = response.json() if response.content else {}
        if not isinstance(body, dict):
            raise WeComAPIError("Invalid WeCom API response")
        self._raise_for_business_error(body)
        return body

    @staticmethod
    def _raise_for_business_error(body: dict[str, Any]) -> None:
        error_code = body.get("errcode", 0)
        if error_code not in {0, "0", None, ""}:
            raise WeComAPIError(str(body.get("errmsg") or error_code))

    def verify_url(
        self,
        *,
        signature: str,
        timestamp: str,
        nonce: str,
        echo: str,
    ) -> str:
        encrypted = unquote(echo)
        if not self.crypt.verify_signature(signature, timestamp, nonce, encrypted):
            raise PermissionError("Invalid WeCom callback signature")
        return self.crypt.decrypt(encrypted)

    async def verify_event(self, headers: dict[str, str], payload: bytes) -> bool:
        try:
            outer = self._parse_xml(payload)
        except ValueError:
            return False
        encrypted = outer.get("Encrypt", "")
        signature = headers.get("x-wecom-msg-signature", "")
        timestamp = headers.get("x-wecom-timestamp", "")
        nonce = headers.get("x-wecom-nonce", "")
        return bool(
            encrypted
            and signature
            and timestamp
            and nonce
            and self.crypt.verify_signature(signature, timestamp, nonce, encrypted)
        )

    async def parse_event(self, headers: dict[str, str], payload: bytes) -> ChannelEvent:
        del headers
        outer = self._parse_xml(payload)
        encrypted = outer.get("Encrypt", "")
        if not encrypted:
            raise ValueError("WeCom encrypted callback is missing")
        try:
            plaintext = self.crypt.decrypt(encrypted)
        except WeComCryptoError as exc:
            raise ValueError("Unable to decrypt WeCom callback") from exc
        message = self._parse_xml(plaintext.encode())
        return self._normalize_message(message)

    def _normalize_message(self, message: dict[str, str]) -> ChannelEvent:
        user_id = message.get("FromUserName", "").strip()
        if not user_id:
            raise ValueError("WeCom sender ID is missing")
        msg_type = message.get("MsgType", "").strip().lower()
        create_time = message.get("CreateTime", "").strip()
        event_name = message.get("Event", "").strip().lower()
        event_key = message.get("EventKey", "").strip()
        msg_id = message.get("MsgId", "").strip()
        if not msg_id:
            identity = "|".join((user_id, create_time, msg_type, event_name, event_key))
            msg_id = f"event-{hashlib.sha256(identity.encode()).hexdigest()[:32]}"

        text, attachments, event_type = self._extract_content(
            message,
            msg_type=msg_type,
            event_name=event_name,
            event_key=event_key,
            message_id=msg_id,
        )
        timestamp = datetime.now(timezone.utc)
        if create_time:
            try:
                timestamp = datetime.fromtimestamp(int(create_time), tz=timezone.utc)
            except ValueError:
                pass

        metadata = {
            "wecom_msg_type": msg_type,
            "event": event_name or None,
            "event_key": event_key or None,
            "agent_id": message.get("AgentID"),
            "task_id": message.get("TaskId"),
            "card_type": message.get("CardType"),
            "response_code": message.get("ResponseCode"),
            "change_type": message.get("ChangeType"),
        }
        return ChannelEvent(
            event_id=msg_id,
            channel=self.channel_type,
            connection_id=self.connection_id,
            event_type=event_type,
            user=ChannelUser(
                external_user_id=user_id,
                tenant_id=message.get("ToUserName") or self.corp_id,
                metadata={"corp_id": message.get("ToUserName") or self.corp_id},
            ),
            conversation=ChannelConversation(
                external_conversation_id=f"user:{user_id}",
                conversation_type="private",
                metadata={"agent_id": message.get("AgentID")},
            ),
            message=ChannelIncomingMessage(
                external_message_id=msg_id,
                message_type=event_type,
                text=text,
                attachments=attachments,
                metadata={key: value for key, value in metadata.items() if value not in {None, ""}},
            ),
            timestamp=timestamp,
            raw_payload=message,
        )

    def _extract_content(
        self,
        message: dict[str, str],
        *,
        msg_type: str,
        event_name: str,
        event_key: str,
        message_id: str,
    ) -> tuple[str | None, list[ChannelAttachment], ChannelEventType]:
        if msg_type == "text":
            text = message.get("Content", "").strip()
            event_type = ChannelEventType.COMMAND if text.startswith("/") else ChannelEventType.TEXT
            return text or None, [], event_type

        if msg_type == "event":
            action_events = {
                "click",
                "view",
                "template_card_event",
                "template_card_menu_event",
                "location_select",
                "pic_sysphoto",
                "pic_photo_or_album",
                "pic_weixin",
                "scancode_push",
                "scancode_waitmsg",
            }
            if event_name in action_events:
                return event_key or event_name, [], ChannelEventType.ACTION
            return event_key or event_name or None, [], ChannelEventType.UNKNOWN

        media_id = message.get("MediaId", "").strip()
        if msg_type == "image" and media_id:
            attachment = self._attachment(media_id, f"wecom-{message_id}.jpg", "image")
            return None, [attachment], ChannelEventType.IMAGE
        if msg_type == "voice" and media_id:
            extension = (message.get("Format") or "amr").lower()
            attachment = self._attachment(media_id, f"wecom-{message_id}.{extension}", "audio")
            recognition = message.get("Recognition", "").strip()
            return recognition or None, [attachment], ChannelEventType.AUDIO
        if msg_type in {"video", "shortvideo"} and media_id:
            attachment = self._attachment(media_id, f"wecom-{message_id}.mp4", "file")
            return None, [attachment], ChannelEventType.FILE
        if msg_type == "file" and media_id:
            filename = message.get("FileName", "").strip() or f"wecom-{message_id}"
            attachment = self._attachment(media_id, filename, "file")
            return None, [attachment], ChannelEventType.FILE
        if msg_type == "location":
            label = message.get("Label", "").strip()
            coordinates = ", ".join(
                value
                for value in (message.get("Location_X", ""), message.get("Location_Y", ""))
                if value
            )
            text = label or coordinates
            return text or None, [], ChannelEventType.TEXT
        if msg_type == "link":
            parts = [message.get("Title", ""), message.get("Description", ""), message.get("Url", "")]
            text = "\n".join(part.strip() for part in parts if part and part.strip())
            return text or None, [], ChannelEventType.TEXT
        return None, [], ChannelEventType.UNKNOWN

    @staticmethod
    def _attachment(media_id: str, filename: str, kind: str) -> ChannelAttachment:
        return ChannelAttachment(
            external_file_id=f"wecom:{media_id}",
            filename=filename,
            metadata={"kind": kind, "media_id": media_id},
        )

    async def send_message(self, target_id: str, message: ChannelMessage) -> str:
        if target_id.startswith("group:"):
            raise NotImplementedError("WeCom internal applications cannot send to arbitrary group conversations")
        user_id = target_id.removeprefix("user:").strip()
        if not user_id:
            raise ValueError("WeCom target user ID is required")
        payload: dict[str, Any] = {
            "touser": user_id,
            "agentid": self.agent_id,
            "safe": 0,
            "enable_duplicate_check": 1,
            "duplicate_check_interval": 1800,
        }
        payload.update(self._render_message(message))
        body = await self._api_request("POST", "/cgi-bin/message/send", payload=payload)
        return str(body.get("msgid") or body.get("response_code") or "")

    async def send_response(self, event: ChannelEvent, message: ChannelMessage) -> str:
        return await self.send_message(event.conversation.external_conversation_id, message)

    def _render_message(self, message: ChannelMessage) -> dict[str, Any]:
        content = message.markdown or message.text or message.title or "OpenXFlow"
        if message.message_type is ChannelMessageType.CARD and message.actions:
            task_id = str(message.metadata.get("task_id") or f"openxflow_{uuid4().hex}")[:128]
            style_map = {"default": 1, "primary": 1, "danger": 2}
            return {
                "msgtype": "template_card",
                "template_card": {
                    "card_type": "button_interaction",
                    "main_title": {
                        "title": (message.title or "OpenXFlow")[:36],
                        "desc": content[:160],
                    },
                    "task_id": task_id,
                    "button_list": [
                        {
                            "text": action.label[:10],
                            "style": style_map.get(action.style, 1),
                            "key": (action.value or action.action_id)[:1024],
                        }
                        for action in message.actions[:6]
                    ],
                },
            }
        if message.message_type in {ChannelMessageType.MARKDOWN, ChannelMessageType.CARD} or message.markdown:
            return {"msgtype": "markdown", "markdown": {"content": content[:4096]}}
        return {"msgtype": "text", "text": {"content": content[:2048]}}

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        prefix, separator, media_id = external_file_id.partition(":")
        if prefix != "wecom" or not separator or not media_id:
            raise ValueError("Invalid WeCom media identifier")
        token = await self._access_token()
        async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
            response = await client.get(
                f"{self.api_base_url}/cgi-bin/media/get",
                params={"access_token": token, "media_id": media_id},
            )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type or response.content.lstrip().startswith(b"{"):
            body = response.json()
            self._raise_for_business_error(body)
            raise WeComAPIError("WeCom media response did not contain a file")
        return response.content, {
            "provider": "wecom",
            "content_type": content_type or None,
            "filename": self._response_filename(response.headers.get("content-disposition")),
        }

    async def healthcheck(self) -> dict[str, Any]:
        await self._access_token(force_refresh=True)
        agent = await self._api_request(
            "GET",
            "/cgi-bin/agent/get",
            params={"agentid": self.agent_id},
        )
        return {
            "ok": True,
            "channel": self.channel_type.value,
            "connection_id": str(self.connection_id),
            "corp_id": self.corp_id,
            "agent_id": self.agent_id,
            "display_name": agent.get("name"),
        }

    @staticmethod
    def _parse_xml(payload: bytes) -> dict[str, str]:
        try:
            root = DefusedElementTree.fromstring(payload)
        except Exception as exc:  # defusedxml and ElementTree expose several parse errors
            raise ValueError("Invalid WeCom XML payload") from exc
        return {child.tag: child.text or "" for child in root}

    @staticmethod
    def _response_filename(content_disposition: str | None) -> str | None:
        if not content_disposition:
            return None
        encoded_match = re.search(r"filename\*=UTF-8''([^;]+)", content_disposition, flags=re.IGNORECASE)
        if encoded_match:
            return unquote(encoded_match.group(1)).strip()
        basic_match = re.search(r'filename="?([^";]+)"?', content_disposition, flags=re.IGNORECASE)
        return basic_match.group(1).strip() if basic_match else None
