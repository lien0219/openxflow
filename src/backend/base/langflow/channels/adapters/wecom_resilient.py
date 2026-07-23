"""Enterprise WeChat adapter with one-shot access-token recovery."""

from __future__ import annotations

import time
from typing import Any

import httpx

from langflow.channels.adapters.wecom import WeComAPIError, WeComChannelAdapter
from langflow.channels.services.token_refresh import (
    is_access_token_rejection,
    refresh_rejected_cached_token,
    request_with_token_refresh,
    response_json_object,
)

_WECOM_ACCESS_TOKEN_REJECTION_CODES = {"40014", "42001"}


class ResilientWeComChannelAdapter(WeComChannelAdapter):
    """Replay one API request after an explicit WeCom access-token rejection."""

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
        expires_in = max(60, int(body.get("expires_in", 7200)))
        return str(token), time.monotonic() + max(30, expires_in - 60)

    async def _refresh_rejected_access_token(self, rejected_token: str) -> str:
        return await refresh_rejected_cached_token(
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            rejected_token=rejected_token,
            lock=self._token_lock,
            fetch_new_token=self._fetch_access_token_entry,
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

        def is_rejected(result: tuple[httpx.Response, dict[str, Any] | None]) -> bool:
            response, body = result
            return is_access_token_rejection(
                response,
                body,
                known_codes=_WECOM_ACCESS_TOKEN_REJECTION_CODES,
                code_fields=("errcode", "code"),
                message_fields=("errmsg", "message", "msg"),
            )

        response, body = await request_with_token_refresh(
            get_token=self._access_token,
            refresh_token=self._refresh_rejected_access_token,
            send=send,
            is_rejected=is_rejected,
        )
        response.raise_for_status()
        if body is None:
            if response.content:
                raise WeComAPIError("Invalid WeCom API response")
            body = {}
        self._raise_for_business_error(body)
        return body
