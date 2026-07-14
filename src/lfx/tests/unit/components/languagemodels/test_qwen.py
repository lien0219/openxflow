from __future__ import annotations  # noqa: INP001

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
from lfx.components.qwen.qwen import QWEN_DEFAULT_BASE_URL, QWEN_DEFAULT_MODELS, QwenModelComponent


def test_qwen_component_uses_openai_compatible_defaults():
    component = QwenModelComponent()

    assert component.display_name == "Qwen"
    assert component.icon == "Qwen"
    assert component.model_name == "qwen-plus"
    assert component.base_url == QWEN_DEFAULT_BASE_URL


def test_qwen_model_refresh_falls_back_to_seed_models():
    component = QwenModelComponent()
    component.api_key = "test-key"  # pragma: allowlist secret
    with patch(
        "lfx.components.qwen.qwen.ssrf_safe_httpx_get",
        side_effect=httpx.RequestError("network unavailable"),
    ):
        assert component.get_models() == QWEN_DEFAULT_MODELS


def test_qwen_build_model_passes_all_runtime_inputs():
    component = QwenModelComponent()
    component.api_key = "test-key"  # pragma: allowlist secret
    component.model_name = "custom-qwen-model"
    component.max_tokens = 128
    component.temperature = 0.4
    component.model_kwargs = {"top_p": 0.8}
    component.stream = True
    component.json_mode = True
    chat_model = MagicMock()
    chat_openai = MagicMock(return_value=chat_model)

    with (
        patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=chat_openai)}),
        patch("lfx.components.qwen.qwen.ssrf_protected_openai_clients_for_url", return_value={}),
    ):
        assert component.build_model() is chat_model.bind.return_value

    chat_openai.assert_called_once_with(
        model="custom-qwen-model",
        temperature=0.4,
        max_tokens=128,
        model_kwargs={"top_p": 0.8},
        base_url=QWEN_DEFAULT_BASE_URL,
        api_key="test-key",  # pragma: allowlist secret
        streaming=True,
    )
    chat_model.bind.assert_called_once_with(response_format={"type": "json_object"})


def test_qwen_build_model_allows_node_base_url_override():
    component = QwenModelComponent()
    component.api_key = "test-key"  # pragma: allowlist secret
    component.base_url = "https://regional.example.com/compatible-mode/v1"
    chat_openai = MagicMock(return_value=MagicMock())

    with (
        patch.dict("sys.modules", {"langchain_openai": SimpleNamespace(ChatOpenAI=chat_openai)}),
        patch("lfx.components.qwen.qwen.ssrf_protected_openai_clients_for_url", return_value={}),
    ):
        component.build_model()

    assert chat_openai.call_args.kwargs["base_url"] == component.base_url
