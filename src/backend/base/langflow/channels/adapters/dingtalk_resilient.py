"""DingTalk adapter with one-shot access-token recovery."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from langflow.channels.adapters.dingtalk import DingTalkAPIError, DingTalkChannelAdapter
from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.provider_http import (
    channel_download_limit_bytes,
    download_provider_file,
    provider_http_client,
    provider_http_client_for_url,
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

_DINGTALK_ACCESS_TOKEN_REJECTION_CODES = {
    "invalidaccesstoken",
    "accesstokenexpired",
    "40014",
    "42001",
}


class ResilientDingTalkChannelAdapter(DingTalkChannelAdapter):
    """Replay one API request after an explicit DingTalk token rejection."""

    _token_lock_pool: ClassVar[LoopLocalKeyedLockPool] = LoopLocalKeyedLockPool()

    @property
    def _token_cache_key(self) -> str:
        return provider_token_cache_key(
            provider="dingtalk",
            api_base_url=self.api_base_url,
            public_id=self.client_id,
            secret=self.client_secret,
        )

    @property
    def _http_client(self) -> httpx.AsyncClient:
        return provider_http_client("dingtalk", self.api_base_url, self.timeout_seconds)

    async def _fetch_access_token_entry(self) -> tuple[str, float]:
        response = await self._http_client.post(
            f"{self.api_base_url}/v1.0/oauth2/accessToken",
            json={"clientId": self.client_id, "clientSecret": self.client_secret},
        )
        response.raise_for_status()
        body = response_json_object(response)
        if body is None:
            raise DingTalkAPIError("Invalid DingTalk access-token response")
        token = body.get("accessToken")
        if not token:
            raise DingTalkAPIError(str(body.get("message") or body.get("msg") or "DingTalk access token missing"))
        try:
            expire_seconds = provider_token_lifetime_seconds(
                body,
                "expireIn",
                provider="DingTalk",
            )
        except InvalidProviderTokenResponseError as exc:
            raise DingTalkAPIError(str(exc)) from exc
        return str(token), time.monotonic() + max(30, expire_seconds - 60)

    async def _access_token(self, *, force_refresh: bool = False) -> str:
        return await get_cached_provider_token(
            provider="dingtalk",
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
            provider="dingtalk",
        )

    async def _api_request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        async def send(token: str) -> tuple[httpx.Response, dict[str, Any] | None]:
            response = await self._http_client.request(
                method,
                f"{self.api_base_url}/{path.lstrip('/')}",
                json=payload,
                headers={"x-acs-dingtalk-access-token": token},
            )
            return response, response_json_object(response)

        def is_rejected(result: tuple[httpx.Response, dict[str, Any] | None]) -> bool:
            response, body = result
            return is_access_token_rejection(
                response,
                body,
                known_codes=_DINGTALK_ACCESS_TOKEN_REJECTION_CODES,
                code_fields=("code", "errcode"),
                message_fields=("message", "msg", "errmsg"),
            )

        response, body = await request_with_token_refresh(
            get_token=self._access_token,
            refresh_token=self._refresh_rejected_access_token,
            send=send,
            is_rejected=is_rejected,
            provider="dingtalk",
        )
        response.raise_for_status()
        if not response.content:
            return {}
        if body is None:
            raise DingTalkAPIError("Invalid DingTalk API response")
        if body.get("code") not in {None, "", 0, "0"}:
            raise DingTalkAPIError(str(body.get("message") or body.get("msg") or body["code"]))
        return body

    async def _post_session_webhook(self, webhook_url: str, payload: dict[str, Any]) -> None:
        self._validate_session_webhook(webhook_url)
        client = provider_http_client_for_url("dingtalk-session", webhook_url, self.timeout_seconds)
        response = await client.post(webhook_url, json=payload)
        response.raise_for_status()
        body = response_json_object(response)
        if body is not None and body.get("errcode") not in {None, 0, "0"}:
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
        client = provider_http_client_for_url(
            "dingtalk-download",
            download_url,
            self.timeout_seconds,
            follow_redirects=False,
        )
        downloaded = await download_provider_file(
            client,
            download_url,
            max_bytes=channel_download_limit_bytes(),
        )
        return downloaded.content, {
            "content_type": downloaded.headers.get("content-type"),
            "provider": "dingtalk",
            "filename": identifier.get("filename"),
            "size_bytes": len(downloaded.content),
        }
