import httpx
from pydantic.v1 import SecretStr
from typing_extensions import override

from lfx.base.models.model import LCModelComponent
from lfx.field_typing import LanguageModel
from lfx.field_typing.range_spec import RangeSpec
from lfx.inputs.inputs import BoolInput, DictInput, DropdownInput, IntInput, SecretStrInput, SliderInput, StrInput
from lfx.utils.ssrf_httpx import ssrf_protected_openai_clients_for_url, ssrf_safe_httpx_get
from lfx.utils.ssrf_protection import SSRFProtectionError

QWEN_DEFAULT_MODELS = ["qwen-plus", "qwen-max", "qwen-turbo"]
QWEN_DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class QwenModelComponent(LCModelComponent):
    """Generate text with Qwen via DashScope's OpenAI-compatible API."""

    display_name = "Qwen"
    description = "Generate text using Qwen models through DashScope."
    icon = "Qwen"

    inputs = [
        *LCModelComponent.get_base_inputs(),
        IntInput(
            name="max_tokens",
            display_name="Max Tokens",
            advanced=True,
            info="Maximum number of tokens to generate. Set to 0 for unlimited.",
            range_spec=RangeSpec(min=0, max=128000),
        ),
        DictInput(
            name="model_kwargs",
            display_name="Model Kwargs",
            advanced=True,
            info="Additional keyword arguments to pass to the model.",
        ),
        BoolInput(
            name="json_mode",
            display_name="JSON Mode",
            advanced=True,
            info="If True, request JSON object output.",
        ),
        DropdownInput(
            name="model_name",
            display_name="Model Name",
            info="Qwen model to use",
            options=QWEN_DEFAULT_MODELS,
            value=QWEN_DEFAULT_MODELS[0],
            refresh_button=True,
            combobox=True,
        ),
        StrInput(
            name="base_url",
            display_name="DashScope API Base",
            advanced=True,
            info=f"Base URL for API requests. Defaults to {QWEN_DEFAULT_BASE_URL}",
            value=QWEN_DEFAULT_BASE_URL,
        ),
        SecretStrInput(
            name="api_key",
            display_name="DashScope API Key",
            info="The DashScope API key.",
            advanced=False,
            value="DASHSCOPE_API_KEY",
            required=True,
        ),
        SliderInput(
            name="temperature",
            display_name="Temperature",
            info="Controls randomness in responses.",
            value=0.7,
            range_spec=RangeSpec(min=0, max=2, step=0.01),
            advanced=True,
        ),
    ]

    def get_models(self) -> list[str]:
        """Fetch models, degrading to stable seeds for unsupported endpoints."""
        if not self.api_key:
            return QWEN_DEFAULT_MODELS

        url = f"{(self.base_url or QWEN_DEFAULT_BASE_URL).rstrip('/')}/models"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        try:
            response = ssrf_safe_httpx_get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            models = [model["id"] for model in data.get("data", []) if model.get("id")]
        except SSRFProtectionError as exc:
            self.status = f"SSRF Protection: {exc}"
        except httpx.HTTPError as exc:
            self.status = f"Error fetching models: {exc}"
        else:
            return models or QWEN_DEFAULT_MODELS
        return QWEN_DEFAULT_MODELS

    @override
    def update_build_config(self, build_config: dict, field_value: str, field_name: str | None = None):
        if field_name in {"api_key", "base_url", "model_name"}:
            build_config["model_name"]["options"] = self.get_models()
        return build_config

    def build_model(self) -> LanguageModel:
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            msg = "langchain-openai not installed. Please install with `pip install langchain-openai`"
            raise ImportError(msg) from exc

        base_url = self.base_url or QWEN_DEFAULT_BASE_URL
        api_key = SecretStr(self.api_key).get_secret_value() if self.api_key else None
        output = ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature if self.temperature is not None else 0.7,
            max_tokens=self.max_tokens or None,
            model_kwargs=self.model_kwargs or {},
            base_url=base_url,
            api_key=api_key,
            streaming=self.stream if hasattr(self, "stream") else False,
            **ssrf_protected_openai_clients_for_url(base_url),
        )
        if self.json_mode:
            output = output.bind(response_format={"type": "json_object"})
        return output
