"""Embedding instantiation adapter for OpenAI-compatible providers."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from lfx.base.models.model_utils import _to_str
from lfx.services.variable.request_scope import is_env_fallback_disabled

from .class_registry import EMBEDDING_PROVIDER_CLASS_MAPPING
from .instantiation import get_embeddings as _delegate_get_embeddings
from .provider_queries import model_provider_metadata

if TYPE_CHECKING:
    from uuid import UUID


_OPENAI_COMPATIBLE_EMBEDDING_CLASSES = {"OpenAIEmbeddings", "QwenEmbeddings"}


def _env_if_allowed(key: str | None) -> str | None:
    """Return an environment variable unless request isolation disables fallback."""
    if not key or is_env_fallback_disabled():
        return None
    return os.environ.get(key)


def _get_provider_variables(user_id: UUID | str | None, provider: str) -> dict[str, Any]:
    """Load encrypted provider variables without importing the package during module init."""
    from lfx.base.models import unified_models as unified_models_module

    return unified_models_module.get_all_variables_for_provider(user_id, provider) or {}


def _resolve_openai_compatible_embedding_base_url(
    provider: str,
    user_id: UUID | str | None,
) -> str | None:
    """Resolve a provider endpoint using DB, environment, then provider defaults."""
    provider_meta = model_provider_metadata.get(provider, {})
    base_url_variable = next(
        (
            variable.get("variable_key")
            for variable in provider_meta.get("variables", [])
            if variable.get("langchain_param") == "base_url"
        ),
        None,
    )
    provider_vars = _get_provider_variables(user_id, provider)
    configured_base_url = provider_vars.get(base_url_variable) if base_url_variable else None
    env_base_url = _env_if_allowed(base_url_variable)
    default_base_url = provider_meta.get("base_url")
    return _to_str(configured_base_url) or _to_str(env_base_url) or _to_str(default_base_url)


def get_embeddings(
    model,
    user_id: UUID | str | None = None,
    api_key=None,
    *,
    api_base=None,
    dimensions=None,
    chunk_size=None,
    request_timeout=None,
    max_retries=None,
    show_progress_bar=None,
    model_kwargs=None,
    watsonx_url=None,
    watsonx_project_id=None,
    watsonx_truncate_input_tokens=None,
    watsonx_input_text=None,
    ollama_base_url=None,
) -> Any:
    """Instantiate embeddings and inject configured endpoints for compatible providers."""
    provider = None
    if isinstance(model, list) and model and isinstance(model[0], dict):
        provider = model[0].get("provider")

    resolved_api_base = _to_str(api_base)
    if (
        not resolved_api_base
        and provider
        and provider != "OpenAI"
        and EMBEDDING_PROVIDER_CLASS_MAPPING.get(provider) in _OPENAI_COMPATIBLE_EMBEDDING_CLASSES
    ):
        resolved_api_base = _resolve_openai_compatible_embedding_base_url(provider, user_id)

    return _delegate_get_embeddings(
        model,
        user_id,
        api_key,
        api_base=resolved_api_base,
        dimensions=dimensions,
        chunk_size=chunk_size,
        request_timeout=request_timeout,
        max_retries=max_retries,
        show_progress_bar=show_progress_bar,
        model_kwargs=model_kwargs,
        watsonx_url=watsonx_url,
        watsonx_project_id=watsonx_project_id,
        watsonx_truncate_input_tokens=watsonx_truncate_input_tokens,
        watsonx_input_text=watsonx_input_text,
        ollama_base_url=ollama_base_url,
    )
