"""Encrypted Feishu adapter with one-shot tenant-token recovery."""

from __future__ import annotations

import time
from typing import Any, ClassVar

import httpx

from langflow.channels.adapters.feishu import FeishuAPIError
from langflow.channels.adapters.feishu_encrypted import EncryptedFeishuChannelAdapter
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

_FEISHU_ACCESS_TOKEN_REJECTION_CODES = {
    "99991663",
    "99991664",
    "99991665",
    "99991668",
}


class ResilientEncryptedFeishuChannelAdapter(EncryptedFeishuChannelAdapter):
    """Replay one API request after an explicit Feishu token rejection."""

    _token_lock_pool: ClassVar[LoopLocalKeyedLockPool] = LoopLocalKeyedLockPool()

    @property
    def _token_cache_key(self) -> str:
        return provider_token_cache_key(
            provider="feishu",
            api_base_url=self.api_base_url,
            public_id=self.app_id,
            secret=self.app_secret,
        )

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
        try:
            expire_seconds = provider_token_lifetime_seconds(
                body,
                "expire",
                provider="Feishu",
            )
        except InvalidProviderTokenResponseError as exc:
            raise FeishuAPIError(str(exc)) from exc
        return str(token), time.monotonic() + max(30, expire_seconds - 60)

    async def _tenant_access_token(self, *, force_refresh: bool = False) -> str:
        return await get_cached_provider_token(
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            force_refresh=force_refresh,
            lock_pool=self._token_lock_pool,
            fetch_new_token=self._fetch_tenant_access_token_entry,
        )

    async def _refresh_rejected_tenant_access_token(self, rejected_token: str) -> str:
        return await refresh_rejected_cached_token(
            cache=self._token_cache,
            cache_key=self._token_cache_key,
            rejected_token=rejected_token,
            lock_pool=self._token_lock_pool,
            fetch_new_token=self._fetch_tenant_access_token_entry,
            provider="feishu",
        )

    @staticmethod
    def _is_token_rejection(result: tuple[httpx.Response, dict[str, Any] | None]) -> bool:
        response, body = result
        return is_access_token_rejection(
            response,
            body,
            known_codes=_FEISHU_ACCESS_TOKEN_REJECTION_CODES,
            code_fields=("code", "errcode"),
            message_fields=("msg", "message", "errmsg"),
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

        response, body = await request_with_token_refresh(
            get_token=self._tenant_access_token,
            refresh_token=self._refresh_rejected_tenant_access_token,
            send=send,
            is_rejected=self._is_token_rejection,
            provider="feishu",
        )
        response.raise_for_status()
        if body is None:
            raise FeishuAPIError("Invalid Feishu API response")
        if body.get("code", 0) != 0:
            raise FeishuAPIError(body.get("msg", "Feishu API request failed"))
        return body.get("data")

    async def download_file(self, external_file_id: str) -> tuple[bytes, dict[str, Any]]:
        parts = external_file_id.split(":", 2)
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError("Invalid Feishu file identifier")
        message_id, file_key = parts[0], parts[1]
        resource_type = parts[2] if len(parts) == 3 else "file"

        async def send(token: str) -> tuple[httpx.Response, dict[str, Any] | None]:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.get(
                    f"{self.api_base_url}/im/v1/messages/{message_id}/resources/{file_key}",
                    params={"type": resource_type},
                    headers={"Authorization": f"Bearer {token}"},
                )
            return response, response_json_object(response)

        response, body = await request_with_token_refresh(
            get_token=self._tenant_access_token,
            refresh_token=self._refresh_rejected_tenant_access_token,
            send=send,
            is_rejected=self._is_token_rejection,
            provider="feishu",
        )
        response.raise_for_status()
        if body is not None and body.get("code", 0) != 0:
            raise FeishuAPIError(body.get("msg", "Feishu resource download failed"))
        return response.content, {
            "content_type": response.headers.get("content-type"),
            "provider": "feishu",
            "resource_type": resource_type,
        }
