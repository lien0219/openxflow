"""Enterprise WeChat adapter with one-shot access-token recovery."""

from __future__ import annotations

import json
import time
from typing import Any, ClassVar

import httpx

from langflow.channels.adapters.wecom import WeComAPIError, WeComChannelAdapter
from langflow.channels.domain.models import ChannelEvent
from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.provider_http import (
    channel_download_limit_bytes,
    download_provider_file,
    provider_http_client,
)
from langflow.channels.services.token_cache import (
    InvalidProviderTokenResponseError,
    get_cached_provider_token,
    provider_token_cache_key,
    provider_token_lifetime_seconds,
    response_json_object,
)
from langflow.channels.services.token_refresh import (
    is_access_token_rejection,
    refresh_rejected_cached_token,
    request_with_token_refresh,
)

_WECOM_ACCESS_TOKEN_REJECTION_CODES = {"40014", "42001"}


class ResilientWeComChannelAdapter(WeComChannelAdapter):
    """Replay one API request after an explicit WeCom access-token rejection."""

    _token_lock_pool: ClassVar[LoopLocalKeyedLockPool] = LoopLocalKeyedLockPool()

    @property
    def _token_cache_key(self) -> str:
        return provider_token_cache_key(
            provider="wecom",
            api_base_url=self.api_base_url,
            public_id=self.corp_id,
            secret=self.corp_secret,
        )

    @property
    def _http_client(self) -> httpx.AsyncClient:
        return provider_http_client("wecom", self.api_base_url, self.timeout_seconds)

    async def _fetch_access_token_entry(self) -> tuple[str, float]:
        response = await self._http_client.get(
            f"{self.api_base_url}/cgi-bin/gettoken",
            params={"corpid": self.corp_id, "corpsecret": self.corp_secret},
        )
        response.raise_for_status()
        body = response_json_object(response)
        if body is None:
            raise WeComAPIError("Invalid WeCom access-token response")
        self._raise_for_business_error(body)
        token = body.get("access_token")
        if not token:
            raise WeComAPIError("WeCom access token is missing")
        try:
            expires_in = provider_token_lifetime_seconds(
                body,
                "expires_in",
                provider="WeCom",
            )
        except InvalidProviderTokenResponseError as exc:
            raise WeComAPIError(str(exc)) from exc
        return str(token), time.monotonic() + max(30, expires_in - 60)

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        return await get_cached_provider_token(
            provider="wecom",
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            force_refresh=force_refresh,
            lock_pool=self._token_lock_pool,
            fetch_new_token=self._fetch_access_token_entry,
        )

    async def _refresh_rejected_access_token(self, rejected_token: str) -> str:
        return await refresh_rejected_cached_token(
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            rejected_token=rejected_token,
            lock_pool=self._token_lock_pool,
            fetch_new_token=self._fetch_access_token_entry,
            provider="wecom",
        )

    @staticmethod
    def _is_token_rejection(result: tuple[httpx.Response, dict[str, Any] | None]) -> bool:
        response, body = result
        return is_access_token_rejection(
            response,
            body,
            known_codes=_WECOM_ACCESS_TOKEN_REJECTION_CODES,
            code_fields=("errcode", "code"),
            message_fields=("errmsg", "message", "msg"),
        )

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def send(token: str) -> tuple[httpx.Response, dict[str, Any] | None]:
            request_params = {"access_token": token, **(params or {})}
            response = await self._http_client.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                params=request_params,
                json=payload,
            )
            return response, response_json_object(response)

        response, body = await request_with_token_refresh(
            get_token=self._access_token,
            refresh_token=self._refresh_rejected_access_token,
            send=send,
            is_rejected=self._is_token_rejection,
            provider="wecom",
        )
        response.raise_for_status()
        if body is None:
            if response.content:
                raise WeComAPIError("Invalid WeCom API response")
            body = {}
        self._raise_for_business_error(body)
        return body

    def _normalize_message(self, message: dict[str, str]) -> ChannelEvent:
        callback_agent_id = message.get("AgentID", "").strip()
        if callback_agent_id:
            try:
                parsed_agent_id = int(callback_agent_id)
            except ValueError as exc:
                raise ValueError("WeCom callback AgentID must be an integer") from exc
            if parsed_agent_id != self.agent_id:
                raise ValueError("WeCom callback AgentID does not match this channel connection")
        return super()._normalize_message(message)

    @staticmethod
    def _download_error_body(content: bytes, content_type: str | None) -> dict[str, Any] | None:
        if not content or "json" not in str(content_type).lower():
            return None
        try:
            value = json.loads(content.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    async def _download_with_token(self, token: str, media_id: str):  # type: ignore[no-untyped-def]
        return await download_provider_file(
            self._http_client,
            f"{self.api_base_url}/cgi-bin/media/get",
            params={"access_token": token, "media_id": media_id},
            max_bytes=channel_download_limit_bytes(),
        )

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        prefix, separator, media_id = external_file_id.partition(":")
        if prefix != "wecom" or not separator or not media_id:
            raise ValueError("Invalid WeCom media identifier")

        token = await self._access_token()
        downloaded = await self._download_with_token(token, media_id)
        body = self._download_error_body(downloaded.content, downloaded.headers.get("content-type"))
        if body is not None and str(body.get("errcode")) in _WECOM_ACCESS_TOKEN_REJECTION_CODES:
            token = await self._refresh_rejected_access_token(token)
            downloaded = await self._download_with_token(token, media_id)
            body = self._download_error_body(downloaded.content, downloaded.headers.get("content-type"))
        if body is not None:
            self._raise_for_business_error(body)
            raise WeComAPIError("WeCom media response did not contain a file")
        return downloaded.content, {
            "provider": "wecom",
            "content_type": downloaded.headers.get("content-type"),
            "filename": self._response_filename(downloaded.headers.get("content-disposition")),
            "size_bytes": len(downloaded.content),
        }
