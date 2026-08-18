"""Qwen embeddings adapter for DashScope's OpenAI-compatible endpoint."""

from typing import Any

from langchain_openai import OpenAIEmbeddings

DASHSCOPE_MAX_EMBEDDING_BATCH_SIZE = 10


class QwenEmbeddings(OpenAIEmbeddings):
    """Preserve raw strings and enforce DashScope's embedding batch limit."""

    check_embedding_ctx_length: bool = False
    chunk_size: int = DASHSCOPE_MAX_EMBEDDING_BATCH_SIZE

    def __init__(self, **kwargs: Any) -> None:
        """Cap explicitly configured batch sizes without affecting other providers."""
        requested_chunk_size = kwargs.get("chunk_size")
        if requested_chunk_size is not None:
            kwargs["chunk_size"] = max(
                1,
                min(int(requested_chunk_size), DASHSCOPE_MAX_EMBEDDING_BATCH_SIZE),
            )
        super().__init__(**kwargs)
