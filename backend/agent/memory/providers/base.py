"""
v0.6.1: Abstract base class for vector store providers.

All vector store adapters (ChromaDB, MongoDB, Pinecone, Qdrant) implement
this interface. Embeddings are pre-computed externally — adapters only
store/retrieve vectors, they don't generate embeddings.

Distance convention: lower = more similar (ChromaDB convention).
Adapters for providers using similarity scores must invert: distance = 1 - score.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple


@dataclass
class VectorRecord:
    """Normalized result from any vector store provider."""
    message_id: str
    text: str
    distance: float  # Lower = more similar (ChromaDB convention)
    sender_key: Optional[str] = None
    metadata: Dict = field(default_factory=dict)


@dataclass
class ProviderHealthResult:
    """Result of a provider health check."""
    healthy: bool
    latency_ms: int = 0
    message: str = ""
    vector_count: Optional[int] = None


class ProviderConnectionError(Exception):
    """Raised when a provider connection fails. Registry handles fallback."""
    pass


class VectorStoreProvider(ABC):
    """
    Abstract base class for all vector store adapters.

    Implementors must handle:
    - Thread safety for concurrent access
    - Connection pooling where applicable
    - Timeout enforcement (default 5s)
    - Namespace isolation per agent (tsushin_{tenant_id}_{agent_id})
    """

    @abstractmethod
    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        """Store a message with its pre-computed embedding vector."""
        ...

    @abstractmethod
    async def add_batch(
        self,
        records: List[Dict],
    ) -> None:
        """
        Batch insert records. Each dict has: message_id, sender_key, text, embedding, metadata.
        """
        ...

    @abstractmethod
    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[VectorRecord]:
        """Search for similar vectors. Returns results sorted by distance (ascending)."""
        ...

    @abstractmethod
    async def search_similar_with_embeddings(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        """Search and also return the result embeddings (for MMR reranking)."""
        ...

    @abstractmethod
    async def delete_message(self, message_id: str) -> None:
        """Delete a single message by ID."""
        ...

    @abstractmethod
    async def delete_by_sender(self, sender_key: str) -> None:
        """Delete all messages from a specific sender."""
        ...

    @abstractmethod
    async def clear_all(self) -> None:
        """Delete all messages in this namespace."""
        ...

    @abstractmethod
    async def update_access_time(self, message_ids: List[str]) -> None:
        """Update last_accessed_at metadata for temporal decay tracking."""
        ...

    @abstractmethod
    async def health_check(self) -> ProviderHealthResult:
        """Probe provider health. Used by circuit breaker and Hub UI."""
        ...

    @abstractmethod
    async def get_stats(self) -> Dict:
        """Return namespace statistics (vector_count, etc.)."""
        ...
