"""ModuRelay integration contracts, exercised through the extension and SDK boundaries."""

import importlib
import json
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest
from lfx.base.models import provider_registry
from lfx.base.models.unified_models import get_live_only_providers, get_model_providers
from lfx.extension import load_extension

ROOT = Path(__file__).resolve().parents[1] / "src" / "lfx_modurelay"


@pytest.fixture
def discovery():
    result = load_extension(ROOT)
    assert result.ok, (result.errors, result.warnings)
    try:
        yield importlib.import_module("lfx_modurelay.discovery")
    finally:
        provider_registry.unregister_provider("ModuRelay")


def _catalog_transport(monkeypatch, discovery, payload, *, status=200, variables=None):
    values = {"MODURELAY_API_KEY": "test-modurelay-key", **(variables or {})}  # pragma: allowlist secret
    monkeypatch.setattr(discovery, "get_provider_variable_value", lambda _user, key: values.get(key))
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(
        discovery,
        "provider_httpx_client_kwargs",
        lambda *_args, **_kwargs: (
            {"transport": httpx.MockTransport(handler)},
            {},
        ),
    )
    return captured


@pytest.mark.parametrize("base_url", [None, "https://ai.zhihengxiangyu.com", "https://ai.zhihengxiangyu.com/v1/"])
def test_discovery_uses_modurelay_endpoint_and_credentials(monkeypatch, discovery, base_url):
    requests = _catalog_transport(
        monkeypatch,
        discovery,
        {"data": [{"id": "new-vendor/custom-model-that-is-not-in-the-static-catalog"}]},
        variables={"MODURELAY_BASE_URL": base_url},
    )
    models = discovery.fetch_live_modurelay_models("user-a", "llm")
    assert [model["name"] for model in models] == ["new-vendor/custom-model-that-is-not-in-the-static-catalog"]
    assert str(requests[0].url) == "https://ai.zhihengxiangyu.com/v1/models"
    assert requests[0].headers["Authorization"] == "Bearer test-modurelay-key"
    assert models[0]["default"] is False
    assert models[0]["icon"] == "ModuRelay"


def test_provider_metadata_uses_the_modurelay_brand_icon():
    extension = json.loads((ROOT / "extension.json").read_text(encoding="utf-8"))

    assert extension["providers"][0]["metadata"]["icon"] == "ModuRelay"


def test_catalog_preserves_all_models_without_duplicating_chat_as_embeddings(monkeypatch, discovery):
    _catalog_transport(
        monkeypatch,
        discovery,
        {
            "data": [
                {"id": "custom-chat", "reasoning": True, "input_modalities": ["text", "image"]},
                {"id": "custom-vector", "supported_endpoints": ["/v1/embeddings"]},
                {"id": "custom-picture", "type": "image"},
                {"id": "custom-voice", "supported_endpoints": ["/audio/speech"]},
                {"id": "custom-film", "category": "video"},
                {"id": "custom-ranker", "type": "rerank"},
                {"id": "custom-chat"},
            ]
        },
    )
    all_models = discovery.fetch_live_modurelay_models("user-a", "all")
    assert {model["name"] for model in all_models} == {
        "custom-chat",
        "custom-vector",
        "custom-picture",
        "custom-voice",
        "custom-film",
        "custom-ranker",
    }
    assert len(all_models) == 6
    assert [m["name"] for m in discovery.fetch_live_modurelay_models("user-a", "llm")] == ["custom-chat"]
    assert [m["name"] for m in discovery.fetch_live_modurelay_models("user-a", "embeddings")] == ["custom-vector"]
    chat = next(model for model in all_models if model["name"] == "custom-chat")
    assert chat["reasoning"] is True
    assert chat["vision"] is True
    assert {m["name"] for m in all_models if m["model_type"] == "gateway"} == {
        "custom-picture",
        "custom-voice",
        "custom-film",
        "custom-ranker",
    }


@pytest.mark.parametrize(
    ("name", "model_type"),
    [
        ("gpt-6-astra", "llm"),
        ("text-embedding-v4", "embeddings"),
        ("gpt-image-2", "gateway"),
        ("whisper-1", "gateway"),
        ("tts-1", "gateway"),
        ("sora-2", "gateway"),
        ("bge-reranker-v2", "gateway"),
    ],
)
def test_unannotated_models_use_capability_hints_without_a_name_whitelist(monkeypatch, discovery, name, model_type):
    _catalog_transport(monkeypatch, discovery, {"data": [{"id": name}]})
    assert discovery.fetch_live_modurelay_models("user-a", "all")[0]["model_type"] == model_type


def test_missing_key_does_not_send_an_unauthenticated_discovery_request(monkeypatch, discovery):
    requests = _catalog_transport(monkeypatch, discovery, {"data": []}, variables={"MODURELAY_API_KEY": None})
    assert discovery.fetch_live_modurelay_models("user-a", "all") == []
    assert requests == []


@pytest.mark.parametrize("status", [401, 403, 500])
def test_validation_reports_gateway_failures_without_generating_a_completion(monkeypatch, discovery, status):
    requests = _catalog_transport(monkeypatch, discovery, {"error": {"message": "upstream rejected"}}, status=status)
    with pytest.raises(ValueError, match="ModuRelay"):
        discovery.validate_modurelay_credentials(
            "ModuRelay",
            {"MODURELAY_API_KEY": "test-modurelay-key"},  # pragma: allowlist secret
        )
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/v1/models"


@pytest.mark.parametrize("payload", [{"data": []}, {"data": [{"id": "anything"}]}])
def test_validation_accepts_valid_empty_or_dynamic_model_lists(monkeypatch, discovery, payload):
    _catalog_transport(monkeypatch, discovery, payload)
    discovery.validate_modurelay_credentials(
        "ModuRelay",
        {"MODURELAY_API_KEY": "test-modurelay-key"},  # pragma: allowlist secret
    )


def test_environment_credentials_cannot_be_redirected_to_another_gateway(monkeypatch, discovery):
    monkeypatch.setenv("MODURELAY_API_KEY", "test-modurelay-environment-key")
    monkeypatch.setenv("LANGFLOW_PROVIDER_CREDENTIAL_ALLOWED_HOSTS", "")
    with pytest.raises(ValueError, match="non-default endpoint"):
        discovery.validate_modurelay_credentials(
            "ModuRelay",
            {
                "MODURELAY_BASE_URL": "https://unapproved.example",
                "MODURELAY_API_KEY": "test-modurelay-environment-key",  # pragma: allowlist secret
            },
        )


def test_openai_credentials_are_not_a_modurelay_fallback(monkeypatch, discovery):  # noqa: ARG001
    from lfx.base.models.unified_models import get_llm

    monkeypatch.setenv("OPENAI_API_KEY", "test-unrelated-key")
    monkeypatch.delenv("MODURELAY_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ModuRelay API key is required"):
        get_llm([{"name": "arbitrary", "provider": "ModuRelay", "metadata": {}}], user_id=None)


@pytest.mark.parametrize("include_metadata", [True, False])
def test_settings_catalog_fetches_all_types_once(monkeypatch, discovery, include_metadata):
    from lfx.base.models import model_utils
    from lfx.base.models.unified_models import get_model_provider_metadata

    requests = _catalog_transport(monkeypatch, discovery, {"data": [{"id": "gpt-image-new"}]})
    result = model_utils.replace_with_live_models(
        [], "user-a", {"ModuRelay"}, provider_metadata=get_model_provider_metadata() if include_metadata else None
    )
    assert result[0]["models"][0]["metadata"]["model_type"] == "gateway"
    assert len(requests) == 1


@pytest.mark.parametrize("payload", [{"success": True}, {"data": "not a list"}, {"data": [None]}])
def test_validation_does_not_accept_non_catalog_json(monkeypatch, discovery, payload):
    _catalog_transport(monkeypatch, discovery, payload)
    with pytest.raises(ValueError, match="catalog"):
        discovery.validate_modurelay_credentials(
            "ModuRelay",
            {"MODURELAY_API_KEY": "test-modurelay-key"},  # pragma: allowlist secret
        )


@contextmanager
def _runtime(monkeypatch, handler, variables):
    from lfx.base.models import unified_models
    from lfx.base.models.unified_models import instantiation

    monkeypatch.setattr(unified_models, "get_api_key_for_provider", lambda *_args, **_kwargs: "test-modurelay-key")
    monkeypatch.setattr(unified_models, "get_all_variables_for_provider", lambda *_args, **_kwargs: variables)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(
            instantiation, "ssrf_protected_openai_clients_for_url", lambda _url: {"http_client": client}
        )
        yield unified_models


@pytest.mark.parametrize("base_url", [None, "https://ai.zhihengxiangyu.com/", "https://ai.zhihengxiangyu.com/v1/"])
def test_runtime_chat_sends_dynamic_model_id_tools_and_isolated_key(monkeypatch, discovery, base_url):  # noqa: ARG001
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chat-test",
                "object": "chat.completion",
                "created": 0,
                "model": "brand-new-chat",
                "choices": [
                    {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "worked"}}
                ],
            },
        )

    with _runtime(monkeypatch, handler, {"MODURELAY_BASE_URL": base_url}) as models:
        chat = models.get_llm([{"name": "brand-new-chat", "provider": "ModuRelay", "metadata": {}}], user_id=None)
        result = chat.bind_tools(
            [{"type": "function", "function": {"name": "lookup", "parameters": {"type": "object"}}}]
        ).invoke("hello")
    assert result.content == "worked"
    assert str(captured[0].url) == "https://ai.zhihengxiangyu.com/v1/chat/completions"
    assert captured[0].headers["Authorization"] == "Bearer test-modurelay-key"
    assert json.loads(captured[0].content)["model"] == "brand-new-chat"
    assert json.loads(captured[0].content)["tools"][0]["function"]["name"] == "lookup"


def test_runtime_chat_streams_text_without_changing_the_dynamic_model_id(monkeypatch, discovery):  # noqa: ARG001
    captured = []

    def handler(request):
        captured.append(request)
        events = [
            {
                "id": "chat-stream",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "stream-alias",
                "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
            }
            for text in ["hello ", "world"]
        ]
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text="".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n",
        )

    with _runtime(monkeypatch, handler, {}) as models:
        chat = models.get_llm(
            [{"name": "stream-alias", "provider": "ModuRelay", "metadata": {}}],
            user_id=None,
            stream=True,
        )
        assert "".join(chunk.content for chunk in chat.stream("hello")) == "hello world"
    assert str(captured[0].url) == "https://ai.zhihengxiangyu.com/v1/chat/completions"
    assert json.loads(captured[0].content)["stream"] is True
    assert json.loads(captured[0].content)["model"] == "stream-alias"


def test_runtime_embeddings_use_dynamic_names_and_plain_strings(monkeypatch, discovery):  # noqa: ARG001
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1, 0.2], "index": 0}],
                "model": "custom-vector",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
            },
        )

    with _runtime(monkeypatch, handler, {}) as models:
        embedding = models.get_embeddings([{"name": "custom-vector", "provider": "ModuRelay", "metadata": {}}])
        assert embedding.embed_query("hello world") == [0.1, 0.2]
    assert str(captured[0].url) == "https://ai.zhihengxiangyu.com/v1/embeddings"
    assert json.loads(captured[0].content)["input"] == ["hello world"]


def test_modurelay_is_available_before_credentials_are_configured():
    try:
        result = load_extension(ROOT)
        assert result.ok, (result.errors, result.warnings)
        assert "ModuRelay" in get_model_providers()
        assert "ModuRelay" in get_live_only_providers()
        assert not provider_registry.is_api_key_optional("ModuRelay")
        assert provider_registry.live_discovery_for("ModuRelay") is not None
        assert provider_registry.validator_for("ModuRelay") is not None
    finally:
        provider_registry.unregister_provider("ModuRelay")
