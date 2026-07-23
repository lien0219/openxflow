"""Enterprise WeChat adapter with one-shot access-token recovery."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from langflow.channels.adapters.wecom import WeComAPIError, WeComChannelAdapter
from langflow.channels.services.keyed_loop_lock import LoopLocalKeyedLockPool
from langflow.channels.services.token_cache import (
    InvalidProviderTokenResponseError,
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

    async def _fetch_access_token_entry(self) -> tuple[str, float]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(
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
        cache_key = self._token_cache_key
        now = time.monotonic()
        cached = self._token_cache.get(cache_key)
        if not force_refresh and cached is not None and cached[1] > now:
            return cached[0]

        async with self._token_lock_pool.hold(cache_key):
            now = time.monotonic()
            cached = self._token_cache.get(cache_key)
            if not force_refresh and cached is not None and cached[1] > now:
                return cached[0]
            token, expires_at = await self._fetch_access_token_entry()
            self._token_cache[cache_key] = (token, expires_at)
            return token

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
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
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

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        prefix, separator, media_id = external_file_id.partition(":")
        if prefix != "wecom" or not separator or not media_id:
            raise ValueError("Invalid WeCom media identifier")

        async def send(token: str) -> tuple[httpx.Response, dict[str, Any] | None]:
            async with httpx.AsyncClient(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = await client.get(
                    f"{self.api_base_url}/cgi-bin/media/get",
                    params={"access_token": token, "media_id": media_id},
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
        content_type = response.headers.get("content-type", "")
        if body is not None:
            self._raise_for_business_error(body)
            raise WeComAPIError("WeCom media response did not contain a file")
        return response.content, {
            "provider": "wecom",
            "content_type": content_type or None,
            "filename": self._response_filename(response.headers.get("content-disposition")),
        }
