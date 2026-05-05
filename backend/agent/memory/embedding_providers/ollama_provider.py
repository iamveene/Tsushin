"""Ollama embedding provider adapter."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import List, Optional

from tenacity import retry, stop_after_attempt, wait_exponential

from agent.memory.embedding_service import EmbeddingProvider

logger = logging.getLogger(__name__)


class OllamaEmbeddingProvider(EmbeddingProvider):
    """``EmbeddingProvider`` backed by Ollama's ``/api/embed`` endpoint."""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        dimensions: Optional[int] = None,
        timeout_seconds: int = 60,
    ) -> None:
        if not base_url:
            raise ValueError("Ollama base URL is required for embeddings")
        if not model:
            raise ValueError("Ollama embedding model is required")

        self._base_url = base_url.rstrip("/")
        self._model = model
        self._dims = int(dimensions) if dimensions else None
        self._timeout_seconds = timeout_seconds

    @property
    def provider(self) -> str:
        return "ollama"

    @property
    def model(self) -> str:
        return self._model

    def get_embedding_dimension(self) -> int:
        return int(self._dims or 0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    def _call_api(self, texts: List[str]) -> List[List[float]]:
        try:
            import httpx
        except ImportError as exc:  # pragma: no cover - environment diagnostic
            raise ValueError("httpx package is required for Ollama embeddings") from exc

        payload = {
            "model": self._model,
            "input": [text or " " for text in texts],
        }
        if self._dims:
            payload["dimensions"] = self._dims

        with httpx.Client(timeout=self._timeout_seconds) as client:
            response = client.post(f"{self._base_url}/api/embed", json=payload)
            response.raise_for_status()
            data = response.json()

        embeddings = data.get("embeddings")
        if embeddings is None and "embedding" in data:
            embeddings = [data["embedding"]]
        if embeddings is None:
            raise ValueError("Ollama embed response did not include embeddings")

        vectors = [list(vector) for vector in embeddings]
        if vectors and self._dims is None:
            self._dims = len(vectors[0])
        return vectors

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


def fingerprint_ollama_config(base_url: str, model: str) -> str:
    payload = f"{base_url or ''}|{model or ''}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
