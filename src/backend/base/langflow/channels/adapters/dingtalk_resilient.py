"""DingTalk adapter with one-shot access-token recovery."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from langflow.channels.adapters.dingtalk import DingTalkAPIError, DingTalkChannelAdapter
from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
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

    async def _fetch_access_token_entry(self) -> tuple[str, float]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.api_base_url}/v1.0/oauth2/accessToken",
                json={"clientId": self.client_id, "clientSecret": self.client_secret},
            )
        response.raise_for_status()
        body = response_json_object(response)
        if body is None:
            raise DingTalkAPIError("Invalid DingTalk access-token response")
        token = body.get("accessToken")
        if not token:
            raise DingTalkAPIError(
                str(body.get("message") or body.get("msg") or "DingTalk access token missing")
            )
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
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
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
            raise DingTalkAPIError(
                str(body.get("message") or body.get("msg") or body["code"])
            )
        return body
