"""
Memory package for Phase 4 - Enhanced Memory & Context

This package contains:
- embedding_service.py: Generate text embeddings
- vector_store.py: Vector database (ChromaDB)
- semantic_memory.py: Semantic search integration
"""

from .embedding_service import EmbeddingService
from .vector_store import VectorStore
from .semantic_memory import SemanticMemoryService

__all__ = ['EmbeddingService', 'VectorStore', 'SemanticMemoryService']
