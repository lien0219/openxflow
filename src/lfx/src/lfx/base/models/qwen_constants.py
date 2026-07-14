"""Qwen models available through DashScope's OpenAI-compatible API."""

from .model_metadata import create_model_metadata

QWEN_MODELS_DETAILED = [
    create_model_metadata(
        provider="Qwen",
        name="qwen-plus",
        icon="Qwen",
        tool_calling=True,
        default=True,
    ),
    create_model_metadata(
        provider="Qwen",
        name="qwen-max",
        icon="Qwen",
        tool_calling=True,
    ),
    create_model_metadata(
        provider="Qwen",
        name="qwen-turbo",
        icon="Qwen",
        tool_calling=True,
    ),
]
