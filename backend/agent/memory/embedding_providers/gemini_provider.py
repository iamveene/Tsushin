"""Gemini embedding provider — adapter over the ``google-genai`` SDK.

Used by the Trigger Case Memory subsystem when a tenant configures a
``VectorStoreInstance`` with ``extra_config.embedding_provider="gemini"``.

The adapter is intentionally narrow:
  - One model: ``gemini-embedding-001`` (override-able via constructor).
  - One of three valid output dimensionalities: ``{768, 1536, 3072}``.
  - ``task_type`` passed at call-time so the same client instance can
    serve both write-side (``RETRIEVAL_DOCUMENT``) and query-side
    (``RETRIEVAL_QUERY``) embeddings.
  - Tenacity-backed retry with exponential backoff (4 attempts, 2s→30s).

Singleton caching is handled by
``agent.memory.embedding_service.get_shared_embedding_service``; the
cache key is ``(api_key_fingerprint, model, dims)``.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import List

from google import genai
from google.genai import types as genai_types
from tenacity import retry, stop_after_attempt, wait_exponential

from agent.memory.embedding_service import EmbeddingProvider

_VALID_DIMS = {768, 1536, 3072}
_DEFAULT_MODEL = "gemini-embedding-001"
_DEFAULT_DIMS = 1536

logger = logging.getLogger(__name__)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """``EmbeddingProvider`` backed by Google Gemini embedding models."""

    def __init__(
        self,
        api_key: str,
        model: str = _DEFAULT_MODEL,
        output_dimensionality: int = _DEFAULT_DIMS,
    ):
        if not api_key:
            raise ValueError("Gemini API key is required")
        if output_dimensionality not in _VALID_DIMS:
            raise ValueError(
                f"output_dimensionality must be one of {_VALID_DIMS}, "
                f"got {output_dimensionality}"
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._dims = int(output_dimensionality)
        self._logger = logger

    # --- Introspection ---------------------------------------------------

    def get_embedding_dimension(self) -> int:
        return self._dims

    @property
    def model(self) -> str:
        return self._model

    # --- Core call -------------------------------------------------------

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_api(self, texts: List[str], task_type: str) -> List[List[float]]:
        """Single API call with tenacity-backed retry.

        Returns a list of embedding vectors, one per input text. The
        google-genai SDK packs them into ``response.embeddings[i].values``.
        """
        response = self._client.models.embed_content(
            model=self._model,
            contents=texts,
            config=genai_types.EmbedContentConfig(
                task_type=task_type,
                output_dimensionality=self._dims,
            ),
        )
        return [list(e.values) for e in response.embeddings]

    # --- Single-text APIs ------------------------------------------------

    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        text = text or " "
        return self._call_api([text], task_type)[0]

    async def embed_text_async(
        self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[float]:
        return await asyncio.to_thread(self.embed_text, text, task_type)

    # --- Batch APIs ------------------------------------------------------

    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        """Embed ``texts`` in chunks, swallowing per-batch failures.

        On a per-batch exception the failing batch yields empty vectors
        (``[]``) for each text in that slice so the caller still sees
        positional alignment with the input list. This mirrors the
        local provider's "return partial results" contract used in
        ``index_case``'s dimension validator.
        """
        if not texts:
            return []
        results: List[List[float]] = []
        for i in range(0, len(texts), batch_size):
            batch = [t if t else " " for t in texts[i : i + batch_size]]
            try:
                results.extend(self._call_api(batch, task_type))
            except Exception:  # noqa: BLE001 — graceful per-batch fallback
                self._logger.exception(
                    "GeminiEmbeddingProvider: batch %d failed (size=%d)",
                    i // batch_size,
                    len(batch),
                )
                results.extend([[] for _ in batch])
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


def fingerprint_api_key(api_key: str) -> str:
    """Stable, non-reversible identifier for an API key.

    Used as a cache-key component so the singleton cache can distinguish
    different keys without ever holding the key itself in cleartext.
    """
    return hashlib.sha256((api_key or "").encode("utf-8")).hexdigest()[:16]
