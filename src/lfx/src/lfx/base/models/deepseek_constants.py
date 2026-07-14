"""DeepSeek models available through its OpenAI-compatible API."""

from .model_metadata import create_model_metadata

DEEPSEEK_MODELS_DETAILED = [
    create_model_metadata(
        provider="DeepSeek",
        name="deepseek-v4-flash",
        icon="DeepSeek",
        tool_calling=True,
        default=True,
        reasoning=True,
    ),
    create_model_metadata(
        provider="DeepSeek",
        name="deepseek-v4-pro",
        icon="DeepSeek",
        tool_calling=True,
        reasoning=True,
    ),
    # Legacy API aliases are retained so imported flows continue to load.
    create_model_metadata(
        provider="DeepSeek",
        name="deepseek-chat",
        icon="DeepSeek",
        tool_calling=True,
        deprecated=True,
    ),
    create_model_metadata(
        provider="DeepSeek",
        name="deepseek-reasoner",
        icon="DeepSeek",
        tool_calling=True,
        reasoning=True,
        deprecated=True,
    ),
]
