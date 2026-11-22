"""Use arbitrary ModuRelay model APIs from a workflow."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
from typing import Any
from urllib.parse import quote, unquote, urlsplit

import httpx
from lfx.base.models.provider_ssrf import ensure_credential_endpoint_allowed, provider_httpx_client_kwargs
from lfx.base.models.unified_models import get_all_variables_for_provider, get_api_key_for_provider
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, IntInput, MessageTextInput, MultilineInput, Output, SecretStrInput
from lfx.schema.data import Data
from lfx.services.model_provider_policy import ModelProviderPolicyPurpose, resolve_model_provider_policy

from lfx_modurelay.discovery import DEFAULT_API_BASE, model_operation, normalize_base_url, read_catalog


class ModuRelayRequestComponent(Component):
    display_name = "ModuRelay Request"
    description = "Use ModuRelay models for images, audio, video, reranking and custom API requests."
    icon = "ModuRelay"
    name = "ModuRelayRequest"
    model_provider_id = "modurelay"

    inputs = [
        DropdownInput(
            name="model_name",
            display_name="Model",
            options=[],
            combobox=True,
            refresh_button=True,
            info="Refresh models from ModuRelay, or enter a model ID or alias.",
        ),
        MessageTextInput(name="prompt", display_name="Prompt", tool_mode=True),
        DropdownInput(
            name="endpoint",
            display_name="Endpoint",
            value="Auto",
            combobox=True,
            options=[
                "Auto",
                "/chat/completions",
                "/responses",
                "/messages",
                "/v1beta/models/{model}:generateContent",
                "/embeddings",
                "/images/generations",
                "/images/edits",
                "/audio/speech",
                "/audio/transcriptions",
                "/videos",
                "/rerank",
            ],
            info="Auto uses model capabilities. Enter another gateway API path for custom operations or job results.",
        ),
        MultilineInput(
            name="body_json",
            display_name="JSON Body",
            value="{}",
            info="Additional API parameters. The selected model ID takes precedence.",
            tool_mode=True,
        ),
        DataInput(
            name="payload",
            display_name="Request Data",
            advanced=True,
            info="Optional JSON object from another component, used instead of JSON Body.",
        ),
        DataInput(
            name="multipart_files",
            display_name="Multipart Files",
            advanced=True,
            info=(
                "Data keyed by form field: filename, content_base64 and optional content_type. "
                "Accepts lists for repeated fields."
            ),
        ),
        DropdownInput(
            name="method",
            display_name="Method",
            options=["POST", "GET"],
            value="POST",
            advanced=True,
            info="Use GET with a job or content endpoint to retrieve asynchronous generation results.",
        ),
        SecretStrInput(
            name="api_key",
            display_name="ModuRelay API Key",
            advanced=True,
            info="Uses the API key saved in Model Providers when left empty.",
        ),
        MessageTextInput(
            name="base_url",
            display_name="Base URL",
            advanced=True,
            info="Uses the configured ModuRelay URL or https://ai.zhihengxiangyu.com.",
        ),
        IntInput(name="timeout", display_name="Timeout", value=120, advanced=True),
    ]
    outputs = [Output(name="response", display_name="Response", method="request")]

    def _model_provider_policy_id(self) -> str:
        return "modurelay"

    def _standalone_model_policy_selection(self, parameters=None):
        model_names, _ = super()._standalone_model_policy_selection(parameters)
        return model_names, None

    def _require_policy(self, purpose: ModelProviderPolicyPurpose, model_name: str | None = None) -> None:
        policy = resolve_model_provider_policy(user_id=self.user_id, providers=("ModuRelay",), purpose=purpose)
        policy.require("ModuRelay")
        if model_name:
            # A custom endpoint must not evade a block on the same model under
            # another typed identity. Untyped checks match every blocked type.
            policy.require_model("ModuRelay", model_name)

    def _connection(self) -> tuple[str, str]:
        api_key = get_api_key_for_provider(self.user_id, "ModuRelay", self.api_key)
        if not api_key:
            msg = "ModuRelay API key is required. Configure it in Model Providers or in this component."
            raise ValueError(msg)
        variables = get_all_variables_for_provider(self.user_id, "ModuRelay")
        api_base = normalize_base_url(self.base_url or variables.get("MODURELAY_BASE_URL"))
        ensure_credential_endpoint_allowed(api_key, api_base, default_url=DEFAULT_API_BASE)
        return api_base, api_key

    def update_build_config(self, build_config: dict, field_value: Any, field_name: str | None = None):  # noqa: ARG002
        if field_name in {"model_name", "api_key", "base_url"}:
            self._require_policy(ModelProviderPolicyPurpose.CONFIGURE)
            api_base, api_key = self._connection()
            build_config["model_name"]["options"] = [model["id"] for model in read_catalog(api_base, api_key)]
        return build_config

    @staticmethod
    def _endpoint_url(api_base: str, endpoint: str, model_name: str = "") -> str:
        endpoint = endpoint.replace("{model}", quote(model_name.removeprefix("models/"), safe=""))
        parsed = urlsplit(endpoint)
        decoded = unquote(parsed.path)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or "\\" in decoded
            or any(part in {".", ".."} for part in decoded.split("/"))
        ):
            msg = "ModuRelay endpoint must be an API path within the configured gateway."
            raise ValueError(msg)
        native_model = re.match(r"^/?(?:v1beta|v1)/models/(.+):[^/]+$", decoded)
        if native_model and native_model[1] != model_name.removeprefix("models/"):
            msg = "ModuRelay endpoint model must match the selected model. Use {model} in the endpoint."
            raise ValueError(msg)
        path = parsed.path.lstrip("/")
        if not path:
            msg = "ModuRelay endpoint must contain an API path."
            raise ValueError(msg)
        # Explicit API versions are relative to the gateway root, including
        # gateways installed below a path prefix such as /relay/v1.
        root = api_base.removesuffix("/v1") if re.match(r"^(?:api/)?v\d", path) else api_base
        return f"{root}/{path}" + (f"?{parsed.query}" if parsed.query else "")

    def _payload(self, endpoint: str, model_name: str) -> dict:
        supplied = self.payload.data if isinstance(self.payload, Data) else self.payload
        try:
            body = dict(supplied) if supplied else json.loads(self.body_json or "{}")
        except (ValueError, TypeError) as exc:
            msg = "ModuRelay JSON Body must be a JSON object."
            raise ValueError(msg) from exc
        if not isinstance(body, dict):
            msg = "ModuRelay JSON Body must be a JSON object."
            raise TypeError(msg)
        body["model"] = model_name
        path = urlsplit(endpoint).path
        is_gemini = ":generateContent" in path or ":streamGenerateContent" in path
        if is_gemini or re.match(r"^/?(?:v1beta|v1)/models/.+:[^/]+$", path):
            body.pop("model")
        prompt = self.prompt
        if prompt:
            if is_gemini:
                body.setdefault("contents", [{"role": "user", "parts": [{"text": prompt}]}])
            elif path.endswith("/chat/completions"):
                body.setdefault("messages", [{"role": "user", "content": prompt}])
            elif path.endswith(("/embeddings", "/audio/speech", "/responses")):
                body.setdefault("input", prompt)
            elif path.endswith("/rerank"):
                body.setdefault("query", prompt)
            elif path.endswith("/messages"):
                body.setdefault("messages", [{"role": "user", "content": prompt}])
                body.setdefault("max_tokens", 1024)
            else:
                body.setdefault("prompt", prompt)
        return body

    def _files(self) -> list[tuple[str, tuple[str, bytes, str]]]:
        files = self.multipart_files.data if isinstance(self.multipart_files, Data) else self.multipart_files
        if not files:
            return []
        if not isinstance(files, dict):
            msg = "ModuRelay Multipart Files must be an object keyed by form field."
            raise TypeError(msg)
        result = []
        try:
            for field, values in files.items():
                for file in values if isinstance(values, list) else [values]:
                    content = base64.b64decode(file["content_base64"], validate=True)
                    result.append(
                        (field, (file["filename"], content, file.get("content_type", "application/octet-stream")))
                    )
        except (KeyError, TypeError, ValueError, binascii.Error) as exc:
            msg = "ModuRelay Multipart Files require filename and valid content_base64 for each file."
            raise ValueError(msg) from exc
        return result

    async def request(self) -> Data:
        model_name = (self.model_name or "").strip()
        self._require_policy(ModelProviderPolicyPurpose.USE, model_name)
        api_base, api_key = self._connection()
        endpoint = self.endpoint or "Auto"
        method = self.method or "POST"
        if method not in {"GET", "POST"}:
            msg = "ModuRelay method must be GET or POST."
            raise ValueError(msg)
        if method == "POST" and not model_name:
            msg = "Select a ModuRelay model before making a request."
            raise ValueError(msg)
        if endpoint == "Auto":
            if method == "GET":
                msg = "Enter a ModuRelay endpoint to retrieve a job or its content."
                raise ValueError(msg)
            catalog = await asyncio.to_thread(read_catalog, api_base, api_key)
            model = next((model for model in catalog if model["id"] == model_name), {"id": model_name})
            _, endpoint = model_operation(model)
        url = self._endpoint_url(api_base, endpoint, model_name)
        options: dict[str, Any] = {
            "headers": {"Authorization": f"Bearer {api_key}"},
            "timeout": self.timeout,
            "follow_redirects": False,
        }
        if urlsplit(url).path.endswith("/messages"):
            options["headers"]["anthropic-version"] = "2023-06-01"
        try:
            if method == "POST":
                body = self._payload(endpoint, model_name)
                files = self._files()
                if files:
                    options["files"] = files
                    options["data"] = {
                        key: value if isinstance(value, str) else json.dumps(value) for key, value in body.items()
                    }
                else:
                    options["json"] = body
            _, client_kwargs = provider_httpx_client_kwargs(api_base, default_url=DEFAULT_API_BASE)
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.request(method, url, **options)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            msg = f"ModuRelay returned HTTP {exc.response.status_code}. Check the model, endpoint and API parameters."
            raise ValueError(msg) from exc
        except httpx.RequestError as exc:
            msg = "The ModuRelay request failed. Check gateway availability and the timeout."
            raise ValueError(msg) from exc
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        if "json" in content_type:
            result = Data(data={"status_code": response.status_code, "result": response.json()})
        else:
            result = Data(
                data={
                    "status_code": response.status_code,
                    "content_type": content_type,
                    "content_base64": base64.b64encode(response.content).decode("ascii"),
                }
            )
        self.status = result
        return result
