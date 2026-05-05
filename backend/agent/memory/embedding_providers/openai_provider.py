"""OpenAI embedding provider adapter."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.memory.embedding_service import EmbeddingProvider

logger = logging.getLogger(__name__)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """``EmbeddingProvider`` backed by OpenAI's embeddings endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimensions: int,
        base_url: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAI API key is required for embeddings")
        if not model:
            raise ValueError("OpenAI embedding model is required")
        if not dimensions:
            raise ValueError("OpenAI embedding dimensions are required")

        try:
            from openai import OpenAI
        except ImportError as exc:  # pragma: no cover - environment diagnostic
            raise ValueError("openai package is required for OpenAI embeddings") from exc

        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model
        self._dims = int(dimensions)

    @property
    def provider(self) -> str:
        return "openai"

    @property
    def model(self) -> str:
        return self._model

    def get_embedding_dimension(self) -> int:
        return self._dims

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=20),
        reraise=True,
    )
    def _call_api(self, texts: List[str]) -> List[List[float]]:
        response = self._client.embeddings.create(
            model=self._model,
            input=[text or " " for text in texts],
            dimensions=self._dims,
        )
        data = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in data]

    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        return self._call_api([text])[0]

    async def embed_text_async(
        self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[float]:
        return await asyncio.to_thread(self.embed_text, text, task_type)

    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        if not texts:
            return []
        results: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            results.extend(self._call_api(batch))
        return results

    async def embed_batch_chunked_async(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        return await asyncio.to_thread(
            self.embed_batch_chunked, texts, batch_size, force_gc, task_type
        )


def fingerprint_openai_config(api_key: str, base_url: Optional[str] = None) -> str:
    payload = f"{api_key or ''}|{base_url or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
