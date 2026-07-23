"""Encrypted Feishu adapter with one-shot tenant-token recovery."""

from __future__ import annotations

import time
from typing import Any

import httpx

from langflow.channels.adapters.feishu import FeishuAPIError
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
from langflow.channels.services.token_refresh import (
    is_access_token_rejection,
    refresh_rejected_cached_token,
    request_with_token_refresh,
    response_json_object,
)

_FEISHU_ACCESS_TOKEN_REJECTION_CODES = {
    "99991663",
    "99991664",
    "99991665",
    "99991668",
}


class ResilientEncryptedFeishuChannelAdapter(EncryptedFeishuChannelAdapter):
    """Replay one API request after an explicit Feishu token rejection."""

    async def _fetch_tenant_access_token_entry(self) -> tuple[str, float]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.api_base_url}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
        response.raise_for_status()
        body = response_json_object(response)
        if body is None:
            raise FeishuAPIError("Invalid Feishu tenant access-token response")
        if body.get("code", 0) != 0:
            raise FeishuAPIError(body.get("msg", "Unable to obtain Feishu tenant access token"))
        token = body.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("Feishu tenant access token is missing")
        expire_seconds = max(60, int(body.get("expire", 7200)))
        return str(token), time.monotonic() + max(30, expire_seconds - 60)

    async def _refresh_rejected_tenant_access_token(self, rejected_token: str) -> str:
        return await refresh_rejected_cached_token(
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            rejected_token=rejected_token,
            lock=self._token_lock,
            fetch_new_token=self._fetch_tenant_access_token_entry,
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        async def send(token: str) -> tuple[httpx.Response, dict[str, Any] | None]:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
                    method,
                    f"{self.api_base_url}/{path.lstrip('/')}",
                    params=params,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
            return response, response_json_object(response)

        def is_rejected(result: tuple[httpx.Response, dict[str, Any] | None]) -> bool:
            response, body = result
            return is_access_token_rejection(
                response,
                body,
                known_codes=_FEISHU_ACCESS_TOKEN_REJECTION_CODES,
                code_fields=("code", "errcode"),
                message_fields=("msg", "message", "errmsg"),
            )

        response, body = await request_with_token_refresh(
            get_token=self._tenant_access_token,
            refresh_token=self._refresh_rejected_tenant_access_token,
            send=send,
            is_rejected=is_rejected,
        )
        response.raise_for_status()
        if body is None:
            raise FeishuAPIError("Invalid Feishu API response")
        if body.get("code", 0) != 0:
            raise FeishuAPIError(body.get("msg", "Feishu API request failed"))
        return body.get("data")
