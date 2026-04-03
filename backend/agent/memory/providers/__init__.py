"""
v0.6.1: Pluggable vector store provider abstraction layer.

Provides ABC interface, data types, and adapters for external vector databases
(MongoDB Atlas, Pinecone, Qdrant) alongside the built-in ChromaDB default.
"""

from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult, ProviderConnectionError
from .chroma_adapter import ChromaDBAdapter

__all__ = [
    "VectorStoreProvider",
    "VectorRecord",
    "ProviderHealthResult",
    "ProviderConnectionError",
    "ChromaDBAdapter",
]
