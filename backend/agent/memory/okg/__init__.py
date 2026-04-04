"""
v0.6.0 Item 3: Ontological Knowledge Graph (OKG) Term Memory

Provides structured, graph-aware long-term memory with typed metadata
(subject/relation/type) on top of vector store providers.
"""

from .okg_memory_service import OKGMemoryService, OKGMemoryMetadata, compute_doc_id
from .okg_context_injector import OKGContextInjector

__all__ = [
    "OKGMemoryService",
    "OKGMemoryMetadata",
    "OKGContextInjector",
    "compute_doc_id",
]
