"""Qwen embeddings adapter for DashScope's OpenAI-compatible endpoint."""

from langchain_openai import OpenAIEmbeddings


class QwenEmbeddings(OpenAIEmbeddings):
    """Preserve raw string inputs because DashScope rejects token-id arrays."""

    check_embedding_ctx_length: bool = False
