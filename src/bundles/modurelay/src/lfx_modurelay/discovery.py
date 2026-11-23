"""Read the user's ModuRelay catalog without generating billable requests."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from lfx.base.models.model_metadata import create_model_metadata
from lfx.base.models.model_utils import get_provider_variable_value
from lfx.base.models.provider_ssrf import ensure_credential_endpoint_allowed, provider_httpx_client_kwargs
from lfx.log.logger import logger

if TYPE_CHECKING:
    from uuid import UUID

DEFAULT_BASE_URL = "https://ai.zhihengxiangyu.com"
DEFAULT_API_BASE = f"{DEFAULT_BASE_URL}/v1"


def normalize_base_url(base_url: str | None) -> str:
    """Accept a gateway root or API root, with identical discovery/runtime URLs."""
    parsed = urlsplit((base_url or DEFAULT_BASE_URL).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        msg = "Invalid ModuRelay base URL. Use an http(s) gateway URL without credentials."
        raise ValueError(msg)
    if parsed.query or parsed.fragment:
        msg = "Invalid ModuRelay base URL. Remove query parameters and fragments."
        raise ValueError(msg)
    path = parsed.path.rstrip("/")
    if not path.endswith("/v1"):
        path += "/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def parse_catalog(payload: Any) -> list[dict]:
    """Preserve arbitrary gateway IDs and metadata; reject non-catalog JSON."""
    entries = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        msg = "Invalid ModuRelay model catalog: expected a data array."
        raise TypeError(msg)
    models: dict[str, dict] = {}
    for raw_entry in entries:
        entry = {"id": raw_entry} if isinstance(raw_entry, str) else raw_entry
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"].strip():
            msg = "Invalid ModuRelay model catalog entry: expected a non-empty model ID."
            raise ValueError(msg)
        models.setdefault(entry["id"], entry)
    return [models[name] for name in sorted(models)]


def model_operation(model: dict) -> tuple[str, str]:
    """Return selector type and suggested endpoint, preferring gateway annotations.

    Name hints are a fallback for the standard ID-only OpenAI catalog, never a
    whitelist. Unknown IDs remain available as language models and can use an
    explicit endpoint in ModuRelay Request.
    """
    details = {**(model.get("metadata") if isinstance(model.get("metadata"), dict) else {}), **model}
    endpoints = details.get("supported_endpoints", [])
    if isinstance(endpoints, str):
        endpoints = [endpoints]
    if isinstance(endpoints, list):
        for raw_endpoint in endpoints:
            if not isinstance(raw_endpoint, str):
                continue
            endpoint = raw_endpoint.removeprefix("/v1/").lstrip("/")
            if endpoint == "embeddings":
                return "embeddings", "/embeddings"
            if endpoint in {"chat/completions", "responses", "messages"}:
                return "llm", f"/{endpoint}"
            if endpoint.startswith(("images/", "audio/", "videos", "rerank")):
                return "gateway", f"/{endpoint}"
    kind = str(details.get("model_type") or details.get("type") or details.get("category") or "").lower()
    if kind in {"llm", "chat", "language", "text", "reasoning"}:
        return "llm", "/chat/completions"
    if kind in {"embedding", "embeddings"}:
        return "embeddings", "/embeddings"
    if kind in {"image", "image_generation"}:
        return "gateway", "/images/generations"
    if kind in {"video", "video_generation"}:
        return "gateway", "/videos"
    if kind in {"audio", "speech", "tts"}:
        return "gateway", "/audio/speech"
    if kind in {"transcription", "stt"}:
        return "gateway", "/audio/transcriptions"
    if kind in {"rerank", "reranking"}:
        return "gateway", "/rerank"

    name = model["id"].lower()
    if re.search(r"rerank", name):
        return "gateway", "/rerank"
    if re.search(r"embed|(?:^|[/:-])(?:bge|e5)(?:[-/:]|$)", name):
        return "embeddings", "/embeddings"
    if re.search(r"image|dall-e|flux|seedream|stable-diffusion", name):
        return "gateway", "/images/generations"
    if re.search(r"whisper|transcri", name):
        return "gateway", "/audio/transcriptions"
    if re.search(r"tts|speech|audio", name):
        return "gateway", "/audio/speech"
    if re.search(r"sora|veo|video|(?:^|[/:-])wan[-\d]", name):
        return "gateway", "/videos"
    return "llm", "/chat/completions"


def read_catalog(base_url: str | None, api_key: str) -> list[dict]:
    """Read one authenticated, SSRF-protected catalog; do not follow redirects."""
    if not api_key:
        msg = "ModuRelay API key is required. Configure MODURELAY_API_KEY."
        raise ValueError(msg)
    api_base = normalize_base_url(base_url)
    ensure_credential_endpoint_allowed(api_key, api_base, default_url=DEFAULT_API_BASE)
    try:
        client_kwargs, _ = provider_httpx_client_kwargs(api_base, default_url=DEFAULT_API_BASE)
        with httpx.Client(**client_kwargs) as client:
            response = client.get(
                f"{api_base}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
                follow_redirects=False,
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        message = (
            "ModuRelay authentication failed. Check the API key and its group permissions."
            if status in {401, 403}
            else f"ModuRelay model discovery returned HTTP {status}. Check the gateway base URL and availability."
        )
        raise ValueError(message) from exc
    except httpx.RequestError as exc:
        msg = "Could not connect to ModuRelay. Check the base URL and network connection."
        raise ValueError(msg) from exc
    try:
        return parse_catalog(response.json())
    except (ValueError, TypeError) as exc:
        msg = "Invalid ModuRelay model catalog. Check that the base URL points to the API gateway."
        raise ValueError(msg) from exc


def fetch_live_modurelay_models(user_id: UUID | str | None, model_type: str = "llm") -> list[dict]:
    """Discover all IDs once for settings, or only models for a specific picker."""
    try:
        api_key = get_provider_variable_value(user_id, "MODURELAY_API_KEY")
        if not api_key:
            return []
        catalog = read_catalog(get_provider_variable_value(user_id, "MODURELAY_BASE_URL"), api_key)
        models = []
        for model in catalog:
            kind, endpoint = model_operation(model)
            if model_type not in {"all", kind}:
                continue
            details = {**(model.get("metadata") if isinstance(model.get("metadata"), dict) else {}), **model}
            metadata = create_model_metadata(
                provider="ModuRelay",
                name=model["id"],
                icon="ModuRelay",
                model_type=kind,
                tool_calling=kind == "llm" and details.get("tool_calling", True) is not False,
                reasoning=details.get("reasoning") is True,
                default=False,
                created=model.get("created") if isinstance(model.get("created"), int) else 0,
            )
            metadata["vision"] = "image" in (details.get("input_modalities") or [])
            metadata["endpoint"] = endpoint
            models.append(metadata)
    except Exception:  # noqa: BLE001 - an unavailable gateway must not break other providers
        logger.debug("Could not fetch the ModuRelay model catalog")
        return []
    return models


def validate_modurelay_credentials(
    provider: str,  # noqa: ARG001 - registry validator contract
    variables: dict[str, str],
    model_name: str | None = None,  # noqa: ARG001
) -> None:
    """Validate connectivity and credentials using a read-only models request."""
    read_catalog(variables.get("MODURELAY_BASE_URL"), variables.get("MODURELAY_API_KEY", ""))
