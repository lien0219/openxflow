from langchain_openai import OpenAIEmbeddings
from lfx.base.models.qwen_constants import QWEN_EMBEDDING_MODELS_DETAILED
from lfx.base.models.qwen_embedding_model import QwenEmbeddings
from lfx.base.models.unified_models import embedding_instantiation
from lfx.base.models.unified_models.class_registry import (
    EMBEDDING_PARAM_MAPPINGS,
    EMBEDDING_PROVIDER_CLASS_MAPPING,
)


def test_qwen_embedding_catalog_contains_text_embedding_v4() -> None:
    assert QWEN_EMBEDDING_MODELS_DETAILED == [
        {
            "provider": "Qwen",
            "name": "text-embedding-v4",
            "icon": "Qwen",
            "tool_calling": False,
            "reasoning": False,
            "search": False,
            "preview": False,
            "not_supported": False,
            "deprecated": False,
            "default": True,
            "model_type": "embeddings",
            "created": 0,
        }
    ]


def test_qwen_embedding_uses_dedicated_openai_compatible_class() -> None:
    assert EMBEDDING_PROVIDER_CLASS_MAPPING["Qwen"] == "QwenEmbeddings"
    assert EMBEDDING_PROVIDER_CLASS_MAPPING["OpenAI"] == "OpenAIEmbeddings"
    assert issubclass(QwenEmbeddings, OpenAIEmbeddings)
    assert EMBEDDING_PARAM_MAPPINGS["Qwen"]["model"] == "model"
    assert EMBEDDING_PARAM_MAPPINGS["Qwen"]["api_key"] == "api_key"
    assert EMBEDDING_PARAM_MAPPINGS["Qwen"]["api_base"] == "base_url"
    assert EMBEDDING_PARAM_MAPPINGS["Qwen"]["dimensions"] == "dimensions"


def test_qwen_embedding_disables_token_id_input_conversion() -> None:
    embeddings = QwenEmbeddings(
        model="text-embedding-v4",
        api_key="test-dashscope-key",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )

    assert embeddings.check_embedding_ctx_length is False


def test_qwen_embedding_resolves_configured_dashscope_base_url(monkeypatch) -> None:
    monkeypatch.setattr(
        embedding_instantiation,
        "_get_provider_variables",
        lambda _user_id, _provider: {
            "DASHSCOPE_BASE_URL": "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
        },
    )

    resolved = embedding_instantiation._resolve_openai_compatible_embedding_base_url("Qwen", "user-id")

    assert resolved == "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"


def test_qwen_embedding_passes_resolved_endpoint_to_delegate(monkeypatch) -> None:
    captured = {}

    def fake_delegate(model, user_id, api_key, **kwargs):
        captured.update(
            {
                "model": model,
                "user_id": user_id,
                "api_key": api_key,
                **kwargs,
            }
        )
        return "embedding-client"

    monkeypatch.setattr(
        embedding_instantiation,
        "_resolve_openai_compatible_embedding_base_url",
        lambda _provider, _user_id: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setattr(embedding_instantiation, "_delegate_get_embeddings", fake_delegate)

    selection = [
        {
            "name": "text-embedding-v4",
            "provider": "Qwen",
            "metadata": {"model_type": "embeddings"},
        }
    ]
    result = embedding_instantiation.get_embeddings(selection, "user-id", "dashscope-key", dimensions=1024)

    assert result == "embedding-client"
    assert captured["api_base"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert captured["dimensions"] == 1024
