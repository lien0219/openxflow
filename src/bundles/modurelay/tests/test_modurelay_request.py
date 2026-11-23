"""Exercise gateway JSON, multipart and binary operations through real HTTP serialization."""

import base64
import importlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from lfx.schema.data import Data


@pytest.fixture
def gateway(monkeypatch):
    module = importlib.import_module("lfx_modurelay.components.modurelay.request")
    monkeypatch.setattr(module, "get_api_key_for_provider", lambda *_args, **_kwargs: "test-gateway-key")
    monkeypatch.setattr(module, "get_all_variables_for_provider", lambda *_args: {})

    def forbidden(*_args, **_kwargs):
        pytest.fail("Tests must install an HTTP test transport before sending a request")

    monkeypatch.setattr(module, "provider_httpx_client_kwargs", forbidden)
    return module


def _transport(monkeypatch, gateway, handler):
    monkeypatch.setattr(
        gateway,
        "provider_httpx_client_kwargs",
        lambda *_args, **_kwargs: (
            {},
            {"transport": httpx.MockTransport(handler), "follow_redirects": False},
        ),
    )


def test_request_component_uses_the_modurelay_brand_icon(gateway):
    assert gateway.ModuRelayRequestComponent.icon == "ModuRelay"


@pytest.mark.parametrize("endpoint", ["/images/generations", "/videos", "/rerank", "/responses", "/custom/new-api"])
async def test_arbitrary_gateway_model_ids_and_parameters_reach_the_selected_api(monkeypatch, gateway, endpoint):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"id": "job-or-result", "data": [{"url": "https://cdn.example/result"}]})

    _transport(monkeypatch, gateway, handler)
    component = gateway.ModuRelayRequestComponent().set(
        model_name="vendor/my-custom-alias",
        endpoint=endpoint,
        prompt="hello",
        body_json='{"size":"1024x1024","model":"wrong-model"}',
    )
    result = await component.request()
    assert result.data["result"]["id"] == "job-or-result"
    assert captured[0].url.path == f"/v1{endpoint}"
    assert captured[0].headers["Authorization"] == "Bearer test-gateway-key"
    assert json.loads(captured[0].content)["model"] == "vendor/my-custom-alias"
    assert json.loads(captured[0].content)["size"] == "1024x1024"


async def test_multipart_audio_preserves_uploaded_bytes_and_model(monkeypatch, gateway):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"text": "transcribed"})

    _transport(monkeypatch, gateway, handler)
    component = gateway.ModuRelayRequestComponent().set(
        model_name="custom-transcriber",
        endpoint="/audio/transcriptions",
        multipart_files=Data(
            data={"file": {"filename": "clip.wav", "content_base64": "aGVsbG8=", "content_type": "audio/wav"}}
        ),
    )
    assert (await component.request()).data["result"] == {"text": "transcribed"}
    assert "multipart/form-data" in captured[0].headers["Content-Type"]
    assert b'filename="clip.wav"' in captured[0].content
    assert b"hello" in captured[0].content
    assert b"custom-transcriber" in captured[0].content


async def test_native_gemini_uses_its_versioned_path_and_selected_model(monkeypatch, gateway):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"candidates": []})

    _transport(monkeypatch, gateway, handler)
    component = gateway.ModuRelayRequestComponent().set(
        model_name="models/custom-gemini",
        endpoint="/v1beta/models/{model}:generateContent",
        prompt="hello",
        body_json='{"generationConfig":{"temperature":0.2}}',
    )
    await component.request()
    assert captured[0].url.path == "/v1beta/models/custom-gemini:generateContent"
    body = json.loads(captured[0].content)
    assert "model" not in body
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hello"}]}]
    assert body["generationConfig"]["temperature"] == 0.2


@pytest.mark.parametrize("prefix", ["/", "", "///"])
async def test_native_endpoint_cannot_select_a_different_model(gateway, prefix):
    component = gateway.ModuRelayRequestComponent().set(
        model_name="allowed-model",
        endpoint=f"{prefix}v1beta/models/different-model:generateContent",
    )
    with pytest.raises(ValueError, match="selected model"):
        await component.request()


@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        ("/v1beta/models/{model}:embedContent", {"content": {"parts": [{"text": "hello"}]}}),
        ("/v1/models/{model}:predict", {"instances": [{"prompt": "hello"}]}),
    ],
)
async def test_native_model_actions_preserve_explicit_payload(monkeypatch, gateway, endpoint, payload):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"result": []})

    _transport(monkeypatch, gateway, handler)
    component = gateway.ModuRelayRequestComponent().set(
        model_name="custom-native-model",
        endpoint=endpoint,
        body_json=json.dumps(payload),
    )
    await component.request()
    assert captured[0].url.path == endpoint.replace("{model}", "custom-native-model")
    assert json.loads(captured[0].content) == payload


async def test_anthropic_messages_include_the_protocol_version(monkeypatch, gateway):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": "hello"}]})

    _transport(monkeypatch, gateway, handler)
    await (
        gateway.ModuRelayRequestComponent()
        .set(
            model_name="custom-claude",
            endpoint="/messages",
            prompt="hello",
        )
        .request()
    )
    assert captured[0].headers["anthropic-version"] == "2023-06-01"
    assert json.loads(captured[0].content)["max_tokens"] == 1024


async def test_other_versioned_apis_preserve_the_gateway_route(monkeypatch, gateway):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, json={"id": "video-task"})

    _transport(monkeypatch, gateway, handler)
    await (
        gateway.ModuRelayRequestComponent()
        .set(
            model_name="custom-video",
            endpoint="/api/v3/contents/generations/tasks",
            body_json='{"content":[{"type":"text","text":"a scene"}]}',
        )
        .request()
    )
    assert captured[0].url.path == "/api/v3/contents/generations/tasks"


async def test_audio_binary_and_video_job_downloads_are_returned_without_decoding_loss(monkeypatch, gateway):
    captured = []

    def handler(request):
        captured.append(request)
        return httpx.Response(200, content=b"\x00\xff\x80audio", headers={"Content-Type": "audio/mpeg"})

    _transport(monkeypatch, gateway, handler)
    component = gateway.ModuRelayRequestComponent().set(method="GET", endpoint="/videos/job-123/content")
    result = await component.request()
    assert str(captured[0].url) == "https://ai.zhihengxiangyu.com/v1/videos/job-123/content"
    assert base64.b64decode(result.data["content_base64"]) == b"\x00\xff\x80audio"
    assert result.data["content_type"] == "audio/mpeg"


@pytest.mark.parametrize("endpoint", ["https://attacker.example/", "//attacker.example/", "/../admin", "/%2e%2e/admin"])
async def test_custom_endpoint_cannot_escape_the_configured_gateway(gateway, endpoint):
    component = gateway.ModuRelayRequestComponent().set(model_name="custom", endpoint=endpoint)
    with pytest.raises(ValueError, match="endpoint"):
        await component.request()


async def test_upstream_errors_do_not_become_successful_workflow_outputs(monkeypatch, gateway):
    _transport(monkeypatch, gateway, lambda _request: httpx.Response(429, json={"error": {"message": "rate limited"}}))
    component = gateway.ModuRelayRequestComponent().set(model_name="anything", endpoint="/images/generations")
    with pytest.raises(ValueError, match="429"):
        await component.request()


@pytest.mark.parametrize(
    "blocked_keys",
    [
        frozenset(),
        frozenset({"modurelay::gateway::blocked-model"}),
        frozenset({"modurelay::llm::blocked-model"}),
        frozenset({"modurelay::embeddings::blocked-model"}),
    ],
)
async def test_policy_denial_happens_before_credentials_or_network(monkeypatch, gateway, blocked_keys):
    from lfx.services.model_provider_policy import (
        ModelProviderPolicyContext,
        ModelProviderPolicyError,
        ModelProviderPolicyPurpose,
        ModelProviderPolicySnapshot,
    )

    policy = ModelProviderPolicySnapshot(
        context=ModelProviderPolicyContext(),
        candidate_provider_ids=frozenset({"modurelay"}),
        allowed_provider_ids=frozenset({"modurelay"}) if blocked_keys else frozenset(),
        blocked_model_keys=blocked_keys,
        purpose=ModelProviderPolicyPurpose.USE,
    )
    monkeypatch.setattr(gateway, "resolve_model_provider_policy", lambda **_kwargs: policy)

    def forbidden(*_args, **_kwargs):
        pytest.fail("Denied models must not resolve credentials or send requests")

    monkeypatch.setattr(gateway, "get_api_key_for_provider", forbidden)
    monkeypatch.setattr(gateway, "provider_httpx_client_kwargs", forbidden)
    component = gateway.ModuRelayRequestComponent().set(model_name="blocked-model", endpoint="/custom")
    with pytest.raises(ModelProviderPolicyError):
        await component.request()
    monkeypatch.setattr(
        "lfx.services.model_provider_policy.aresolve_model_provider_policy",
        AsyncMock(return_value=policy),
    )
    # Graph execution checks raw parameters before resolving secret inputs.
    with pytest.raises(ModelProviderPolicyError):
        await component.arequire_model_provider_policy(
            ModelProviderPolicyPurpose.USE,
            parameters={"model_name": "blocked-model"},
        )
