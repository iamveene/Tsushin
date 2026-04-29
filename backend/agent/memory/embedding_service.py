"""
Embedding Service - Generate text embeddings for semantic search

Uses sentence-transformers library with all-MiniLM-L6-v2 model by default.
This model produces 384-dimensional embeddings optimized for semantic similarity.

BUG-001 Fix: Added singleton pattern and batched processing to prevent OOM crashes
on large document uploads.

v0.7.x Wave 1-B: Added ``EmbeddingProvider`` ABC and dispatcher to support
multiple embedding back-ends (local SentenceTransformer at 384 dims and
Gemini at 768/1536/3072 dims). The dispatcher in
``get_shared_embedding_service`` accepts an optional
``EmbeddingContract`` and routes to the right provider, while keeping the
zero-arg / ``model_name``-only callers working unchanged.
"""

import abc
import logging
import gc
import threading
from typing import List, Optional
import numpy as np
from sentence_transformers import SentenceTransformer

# Singleton caches:
#   _model_cache:  legacy local SentenceTransformer cache (model_name -> EmbeddingService)
#   _provider_cache: provider-aware cache used when a contract is supplied
_model_cache: dict = {}
_provider_cache: dict = {}
_model_lock = threading.Lock()


class EmbeddingProvider(abc.ABC):
    """Abstract interface for embedding providers.

    Concrete implementations are:
      - ``LocalSentenceTransformerProvider`` — wraps the existing local
        ``EmbeddingService`` (default).
      - ``GeminiEmbeddingProvider`` — wraps Google Gemini via the
        ``google-genai`` SDK.

    The ``task_type`` argument is a hint used by Gemini-style providers
    (``RETRIEVAL_DOCUMENT`` for write-side, ``RETRIEVAL_QUERY`` for the
    query-side). Local providers ignore it.
    """

    @abc.abstractmethod
    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        ...

    @abc.abstractmethod
    async def embed_text_async(
        self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[float]:
        ...

    @abc.abstractmethod
    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        ...

    @abc.abstractmethod
    async def embed_batch_chunked_async(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        ...

    @abc.abstractmethod
    def get_embedding_dimension(self) -> int:
        ...


class LocalSentenceTransformerProvider(EmbeddingProvider):
    """Adapter wrapping the existing local ``EmbeddingService``.

    The ``task_type`` arg is accepted (for interface parity) but ignored —
    SentenceTransformer models do not use a task hint.
    """

    def __init__(self, inner: "EmbeddingService") -> None:
        self._inner = inner

    @property
    def inner(self) -> "EmbeddingService":  # exposed for legacy code-paths
        return self._inner

    # Compatibility shims so consumers that previously held an
    # ``EmbeddingService`` reference and accessed ``.model`` / ``.model_name``
    # continue to work.
    @property
    def model(self):  # type: ignore[override]
        return getattr(self._inner, "model", None)

    @property
    def model_name(self) -> str:
        return getattr(self._inner, "model_name", "all-MiniLM-L6-v2")

    def embed_text(self, text: str, task_type: str = "RETRIEVAL_DOCUMENT") -> List[float]:
        return self._inner.embed_text(text)

    async def embed_text_async(
        self, text: str, task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[float]:
        return await self._inner.embed_text_async(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        # Legacy passthrough — used by callers that pre-date the chunked variant.
        return self._inner.embed_batch(texts)

    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        return self._inner.embed_batch_chunked(texts, batch_size=batch_size, force_gc=force_gc)

    async def embed_batch_chunked_async(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True,
        task_type: str = "RETRIEVAL_DOCUMENT",
    ) -> List[List[float]]:
        return await self._inner.embed_batch_chunked_async(
            texts, batch_size=batch_size, force_gc=force_gc
        )

    def get_embedding_dimension(self) -> int:
        return self._inner.get_embedding_dimension()


def get_shared_embedding_service(
    model_name: str = "all-MiniLM-L6-v2",
    contract: Optional[object] = None,
    credentials: Optional[dict] = None,
) -> "EmbeddingProvider":
    """Get a shared embedding provider (singleton-cached).

    Backward-compatible:
      - Zero-arg calls return the local default
        (``LocalSentenceTransformerProvider`` wrapping
        ``EmbeddingService('all-MiniLM-L6-v2')``).
      - ``model_name``-only calls behave as before.

    Contract-aware:
      - ``contract.provider == "local"`` → local provider (model from
        ``contract.model`` if set, else the function arg).
      - ``contract.provider == "gemini"`` → ``GeminiEmbeddingProvider``,
        cached by ``(api_key_fingerprint, model, dims)``.

    Failure semantics:
      - If a Gemini provider is requested but ``credentials.api_key`` is
        missing, ``ValueError`` is raised. The case-memory indexer
        catches this and marks the row failed without retrying.
    """

    provider_name = None
    contract_model = None
    contract_dims = None
    if contract is not None:
        provider_name = (getattr(contract, "provider", None) or "").lower() or None
        contract_model = getattr(contract, "model", None)
        contract_dims = getattr(contract, "dimensions", None)

    if provider_name in (None, "local"):
        # Local SentenceTransformer path. Use contract.model when present
        # and non-default to allow tenants to switch local model variants.
        effective_model = contract_model or model_name

        global _model_cache
        if effective_model in _model_cache:
            return _model_cache[effective_model]

        with _model_lock:
            if effective_model not in _model_cache:
                inner = EmbeddingService(effective_model)
                _model_cache[effective_model] = LocalSentenceTransformerProvider(inner)
                logging.getLogger(__name__).info(
                    "Created shared local embedding provider: %s", effective_model
                )

        return _model_cache[effective_model]

    if provider_name == "gemini":
        from agent.memory.embedding_providers.gemini_provider import (
            GeminiEmbeddingProvider,
            fingerprint_api_key,
        )

        api_key = (credentials or {}).get("api_key") if credentials else None
        if not api_key:
            # Some tenants store the key under different field names.
            for alt in ("apiKey", "GEMINI_API_KEY", "google_api_key"):
                if credentials and credentials.get(alt):
                    api_key = credentials[alt]
                    break
        if not api_key:
            raise ValueError(
                "Gemini embedding provider requested but no api_key found "
                "in credentials. Set the API key on the VectorStoreInstance."
            )

        gemini_model = contract_model or "gemini-embedding-001"
        gemini_dims = int(contract_dims) if contract_dims is not None else 1536
        cache_key = (fingerprint_api_key(api_key), gemini_model, gemini_dims)

        if cache_key in _provider_cache:
            return _provider_cache[cache_key]

        with _model_lock:
            if cache_key not in _provider_cache:
                _provider_cache[cache_key] = GeminiEmbeddingProvider(
                    api_key=api_key,
                    model=gemini_model,
                    output_dimensionality=gemini_dims,
                )
                logging.getLogger(__name__).info(
                    "Created shared Gemini embedding provider: model=%s dims=%d",
                    gemini_model,
                    gemini_dims,
                )

        return _provider_cache[cache_key]

    raise ValueError(f"Unknown embedding provider: {provider_name!r}")


def _reset_provider_cache_for_tests() -> None:
    """Test helper — clears both caches so tests don't leak singletons."""
    global _model_cache, _provider_cache
    with _model_lock:
        _model_cache.clear()
        _provider_cache.clear()


class EmbeddingService:
    """
    Service for generating text embeddings using sentence-transformers.

    Attributes:
        model_name: Name of the sentence-transformers model
        model: Loaded SentenceTransformer model
        logger: Logger instance
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        """
        Initialize the embedding service.

        Args:
            model_name: Name of the sentence-transformers model to use.
                       Default is 'all-MiniLM-L6-v2' (384 dimensions, fast, good quality)
        """
        self.model_name = model_name
        self.logger = logging.getLogger(__name__)

        self.logger.info(f"Loading embedding model: {model_name}")
        try:
            self.model = SentenceTransformer(model_name)
            self.logger.info(f"Model loaded successfully. Embedding dimension: {self.model.get_sentence_embedding_dimension()}")
        except Exception as e:
            # BUG-400 graceful fallback: if the model fails to load (e.g. OOM
            # during first-time download on constrained containers), set model
            # to None so callers get empty embeddings instead of a crash.
            self.model = None
            self.logger.error(
                f"Failed to load embedding model '{model_name}': {e}. "
                "Embedding requests will return empty vectors until the model "
                "is available. Pre-download the model in the Docker image to "
                "avoid this."
            )

    def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text (sync version).

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector (384 dimensions for MiniLM)
        """
        return self._embed_text_sync(text)

    def _embed_text_sync(self, text: str) -> List[float]:
        """Synchronous embedding — use embed_text_async in async contexts."""
        if self.model is None:
            self.logger.warning(
                "Embedding model not loaded — returning empty vector. "
                "KB search quality will be degraded until the model is available."
            )
            return []
        try:
            if not text:
                text = " "
            embedding = self.model.encode(text, convert_to_numpy=True)
            return embedding.tolist()
        except Exception as e:
            self.logger.error(f"Error generating embedding: {e}")
            raise

    async def embed_text_async(self, text: str) -> List[float]:
        """
        Async-safe embedding — runs the CPU-bound encode in a thread pool
        to avoid blocking the event loop.
        """
        import asyncio
        return await asyncio.to_thread(self._embed_text_sync, text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts (more efficient than calling embed_text repeatedly).

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        if self.model is None:
            self.logger.warning(
                "Embedding model not loaded — returning empty vectors for batch of %d texts.",
                len(texts),
            )
            return [[] for _ in texts]

        try:
            # Handle empty strings in batch
            processed_texts = [text if text else " " for text in texts]

            # Generate embeddings in batch (more efficient)
            embeddings = self.model.encode(processed_texts, convert_to_numpy=True, show_progress_bar=False)

            # Convert to list of lists
            return [emb.tolist() for emb in embeddings]

        except Exception as e:
            self.logger.error(f"Error generating batch embeddings: {e}")
            raise

    def embed_batch_chunked(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in smaller batches to prevent OOM.

        BUG-001 Fix: Process chunks in smaller batches to prevent memory spikes
        when embedding large documents.

        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process at once (default 50)
            force_gc: Whether to force garbage collection between batches

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        if self.model is None:
            self.logger.warning(
                "Embedding model not loaded — returning empty vectors for %d chunks. "
                "KB document will complete but without semantic embeddings.",
                len(texts),
            )
            return [[] for _ in texts]

        all_embeddings = []
        total_texts = len(texts)

        self.logger.info(f"Embedding {total_texts} chunks in batches of {batch_size}")

        for i in range(0, total_texts, batch_size):
            batch = texts[i:i + batch_size]

            try:
                # Handle empty strings in batch
                processed_batch = [text if text else " " for text in batch]

                # Generate embeddings for this batch
                batch_embeddings = self.model.encode(
                    processed_batch,
                    convert_to_numpy=True,
                    show_progress_bar=False
                )

                # Convert to list and extend results
                all_embeddings.extend([emb.tolist() for emb in batch_embeddings])

                # Force garbage collection to free memory
                if force_gc and i + batch_size < total_texts:
                    del batch_embeddings
                    gc.collect()

            except Exception as e:
                self.logger.error(f"Error embedding batch {i//batch_size + 1}: {e}")
                # Return partial results rather than failing completely
                break

        self.logger.info(f"Successfully embedded {len(all_embeddings)}/{total_texts} chunks")
        return all_embeddings

    async def embed_batch_chunked_async(
        self,
        texts: List[str],
        batch_size: int = 50,
        force_gc: bool = True
    ) -> List[List[float]]:
        """Async-safe batched embedding — runs in a thread pool."""
        import asyncio
        return await asyncio.to_thread(self.embed_batch_chunked, texts, batch_size, force_gc)

    @staticmethod
    def cosine_similarity(embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Cosine similarity ranges from -1 (opposite) to 1 (identical).
        Values closer to 1 indicate higher semantic similarity.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score between -1 and 1
        """
        try:
            # Convert to numpy arrays
            emb1 = np.array(embedding1)
            emb2 = np.array(embedding2)

            # Calculate cosine similarity
            dot_product = np.dot(emb1, emb2)
            norm1 = float(np.linalg.norm(emb1))
            norm2 = float(np.linalg.norm(emb2))

            if norm1 == 0 or norm2 == 0:
                return 0.0

            similarity = dot_product / (norm1 * norm2)

            # Ensure result is in valid range (due to floating point errors)
            return float(np.clip(similarity, -1.0, 1.0))

        except Exception as e:
            logging.error(f"Error calculating cosine similarity: {e}")
            raise

    def get_embedding_dimension(self) -> int:
        """
        Get the dimension of embeddings produced by this model.

        Returns:
            Embedding dimension (384 for all-MiniLM-L6-v2)
        """
        if self.model is None:
            return 384  # Default dimension for all-MiniLM-L6-v2
        return self.model.get_sentence_embedding_dimension()
