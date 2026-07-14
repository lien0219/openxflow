"""Regression tests for unified DeepSeek and Qwen providers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.parametrize(
    ("provider", "api_key_variable", "base_url_variable", "base_url"),
    [
        ("DeepSeek", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        ("Qwen", "DASHSCOPE_API_KEY", "DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ],
)
def test_openai_compatible_provider_metadata_and_catalog(provider, api_key_variable, base_url_variable, base_url):
    from lfx.base.models.model_metadata import MODEL_PROVIDER_METADATA, get_provider_param_mapping
    from lfx.base.models.unified_models import get_model_provider_variable_mapping, get_unified_models_detailed

    metadata = MODEL_PROVIDER_METADATA[provider]
    assert metadata["icon"] == provider
    assert metadata["base_url"] == base_url
    assert get_provider_param_mapping(provider)["model_class"] == "ChatOpenAI"
    assert get_model_provider_variable_mapping()[provider] == api_key_variable
    assert {variable["variable_key"] for variable in metadata["variables"]} == {
        api_key_variable,
        base_url_variable,
    }

    catalog = get_unified_models_detailed(providers=[provider])
    assert catalog[0]["provider"] == provider
    assert catalog[0]["models"]
    assert all(model["metadata"]["tool_calling"] for model in catalog[0]["models"])


def test_deepseek_v4_catalog_preserves_legacy_aliases():
    from lfx.base.models.deepseek_constants import DEEPSEEK_MODELS_DETAILED
    from lfx.base.models.unified_models import get_unified_models_detailed

    by_name = {model["name"]: model for model in DEEPSEEK_MODELS_DETAILED}
    assert by_name["deepseek-v4-flash"]["default"] is True
    assert by_name["deepseek-v4-flash"]["tool_calling"] is True
    assert by_name["deepseek-v4-flash"]["reasoning"] is True
    assert by_name["deepseek-v4-pro"]["tool_calling"] is True
    assert by_name["deepseek-v4-pro"]["reasoning"] is True
    assert by_name["deepseek-chat"]["deprecated"] is True
    assert by_name["deepseek-reasoner"]["deprecated"] is True
    assert by_name["deepseek-reasoner"]["reasoning"] is True

    catalog = get_unified_models_detailed(providers=["DeepSeek"], include_deprecated=True)
    assert {model["model_name"] for model in catalog[0]["models"]} == set(by_name)


def test_get_llm_supports_legacy_deepseek_chat_selection():
    from lfx.base.models import unified_models as unified_models_module
    from lfx.base.models.unified_models.instantiation import get_llm

    captured_kwargs = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    with (
        patch.object(unified_models_module, "get_api_key_for_provider", return_value="provider-key"),
        patch.object(unified_models_module, "get_model_class", return_value=FakeChatOpenAI),
        patch.object(unified_models_module, "get_all_variables_for_provider", return_value={}),
        patch(
            "lfx.utils.ssrf_httpx.ssrf_protected_openai_clients_for_url",
            return_value={"http_client": MagicMock(), "http_async_client": MagicMock()},
        ),
    ):
        get_llm([{"name": "deepseek-chat", "provider": "DeepSeek", "metadata": {}}], user_id="test-user")

    assert captured_kwargs["model"] == "deepseek-chat"


@pytest.mark.parametrize(
    ("provider", "api_key_variable", "base_url_variable", "configured_url", "local_url"),
    [
        (
            "DeepSeek",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "https://configured.deepseek.example/v1",
            "https://local.deepseek.example/v1",
        ),
        (
            "Qwen",
            "DASHSCOPE_API_KEY",
            "DASHSCOPE_BASE_URL",
            "https://configured.qwen.example/v1",
            "https://local.qwen.example/v1",
        ),
    ],
)
def test_get_llm_uses_provider_key_and_local_base_url(
    provider, api_key_variable, base_url_variable, configured_url, local_url
):
    from lfx.base.models import unified_models as unified_models_module
    from lfx.base.models.unified_models.instantiation import get_llm

    captured_kwargs = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured_kwargs.update(kwargs)

    model = [{"name": "example-model", "provider": provider, "metadata": {}}]
    with (
        patch.object(unified_models_module, "get_api_key_for_provider", return_value="provider-key"),
        patch.object(unified_models_module, "get_model_class", return_value=FakeChatOpenAI),
        patch.object(
            unified_models_module,
            "get_all_variables_for_provider",
            return_value={
                api_key_variable: "provider-key",  # pragma: allowlist secret
                base_url_variable: configured_url,
            },
        ),
        patch(
            "lfx.utils.ssrf_httpx.ssrf_protected_openai_clients_for_url",
            return_value={"http_client": MagicMock(), "http_async_client": MagicMock()},
        ),
    ):
        get_llm(
            model,
            user_id="test-user",
            temperature=0.4,
            stream=True,
            max_tokens=42,
            openai_compatible_base_url=local_url,
        )

    assert captured_kwargs["model"] == "example-model"
    assert captured_kwargs["api_key"] == "provider-key"  # pragma: allowlist secret
    assert captured_kwargs["base_url"] == local_url
    assert captured_kwargs["streaming"] is True
    assert captured_kwargs["temperature"] == 0.4
    assert captured_kwargs["max_tokens"] == 42


@pytest.mark.parametrize(
    ("provider", "variable_name"),
    [("DeepSeek", "DEEPSEEK_API_KEY"), ("Qwen", "DASHSCOPE_API_KEY")],
)
def test_get_llm_missing_provider_key_names_correct_variable(provider, variable_name):
    from lfx.base.models import unified_models as unified_models_module
    from lfx.base.models.unified_models.instantiation import get_llm

    with (
        patch.object(unified_models_module, "get_api_key_for_provider", return_value=None),
        pytest.raises(ValueError, match=variable_name),
    ):
        get_llm([{"name": "example-model", "provider": provider, "metadata": {}}], user_id="test-user")


@pytest.mark.parametrize(
    ("provider", "api_key_variable"),
    [("DeepSeek", "DEEPSEEK_API_KEY"), ("Qwen", "DASHSCOPE_API_KEY")],
)
def test_validate_openai_compatible_provider_success(provider, api_key_variable):
    from lfx.base.models.unified_models import validate_model_provider_key

    calls = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def invoke(self, _message):
            return "ok"

    with (
        patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=FakeChatOpenAI)}),
        patch(
            "lfx.utils.ssrf_httpx.ssrf_protected_openai_clients_for_url",
            return_value={"http_client": MagicMock(), "http_async_client": MagicMock()},
        ),
    ):
        validate_model_provider_key(provider, {api_key_variable: "test-key"})  # pragma: allowlist secret

    assert calls[0]["api_key"] == "test-key"  # pragma: allowlist secret
    assert calls[0]["max_tokens"] == 1
    if provider == "DeepSeek":
        assert calls[0]["model"] == "deepseek-v4-flash"


@pytest.mark.parametrize(
    ("provider", "api_key_variable"),
    [("DeepSeek", "DEEPSEEK_API_KEY"), ("Qwen", "DASHSCOPE_API_KEY")],
)
def test_validate_openai_compatible_provider_hides_key_on_auth_error(provider, api_key_variable):
    from lfx.base.models.unified_models import validate_model_provider_key

    class FakeChatOpenAI:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _message):
            message = "401 unauthorized"
            raise RuntimeError(message)

    with (
        patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=FakeChatOpenAI)}),
        patch(
            "lfx.utils.ssrf_httpx.ssrf_protected_openai_clients_for_url",
            return_value={"http_client": MagicMock(), "http_async_client": MagicMock()},
        ),
        pytest.raises(ValueError, match=f"Invalid API key for {provider}") as error,
    ):
        validate_model_provider_key(provider, {api_key_variable: "super-secret-key"})  # pragma: allowlist secret

    assert "super-secret-key" not in str(error.value)


@pytest.mark.parametrize(
    ("provider", "api_key_variable"),
    [("DeepSeek", "DEEPSEEK_API_KEY"), ("Qwen", "DASHSCOPE_API_KEY")],
)
def test_validate_openai_compatible_provider_network_error_is_readable(provider, api_key_variable):
    from lfx.base.models.unified_models import validate_model_provider_key

    class FakeChatOpenAI:
        def __init__(self, **_kwargs):
            pass

        def invoke(self, _message):
            message = "connection refused"
            raise RuntimeError(message)

    with (
        patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=FakeChatOpenAI)}),
        patch(
            "lfx.utils.ssrf_httpx.ssrf_protected_openai_clients_for_url",
            return_value={"http_client": MagicMock(), "http_async_client": MagicMock()},
        ),
        pytest.raises(ValueError, match=f"Could not reach {provider} API endpoint") as error,
    ):
        validate_model_provider_key(provider, {api_key_variable: "super-secret-key"})  # pragma: allowlist secret

    assert "super-secret-key" not in str(error.value)
