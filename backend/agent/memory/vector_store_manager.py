"""
VectorStore Manager - Singleton pattern for ChromaDB instances

Ensures only one VectorStore instance exists per path to prevent ChromaDB conflicts.
ChromaDB enforces singleton pattern internally - multiple clients with same path cause errors.
"""

import logging
from typing import Dict
from threading import Lock
from agent.memory.vector_store import VectorStore
from agent.memory.vector_store_cached import CachedVectorStore  # Phase 6.11.3
from agent.memory.embedding_service import EmbeddingService


class VectorStoreManager:
    """
    Manages VectorStore instances with singleton pattern.

    Ensures only one VectorStore instance per ChromaDB path exists,
    preventing "An instance of Chroma already exists" errors.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        """Implement singleton pattern for the manager itself"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """Initialize the manager (only once)"""
        if self._initialized:
            return

        self.logger = logging.getLogger(__name__)
        self._stores: Dict[str, VectorStore] = {}
        self._embedding_services: Dict[str, EmbeddingService] = {}
        self._initialized = True
        self.logger.info("VectorStoreManager initialized")

    def get_vector_store(self, persist_directory: str, embedding_model: str = "all-MiniLM-L6-v2") -> VectorStore:
        """
        Get or create a VectorStore instance for the given path.

        Args:
            persist_directory: ChromaDB storage path
            embedding_model: Embedding model name

        Returns:
            VectorStore instance (cached or newly created)
        """
        # Normalize path to prevent duplicates (handle relative vs absolute, trailing slashes)
        import os
        normalized_path = os.path.abspath(persist_directory)

        with self._lock:
            # Return existing instance if available
            if normalized_path in self._stores:
                self.logger.debug(f"Reusing existing VectorStore for {normalized_path}")
                return self._stores[normalized_path]

            # Create new instance
            self.logger.info(f"Creating new VectorStore for {normalized_path}")

            # Get or create embedding service
            if embedding_model not in self._embedding_services:
                self._embedding_services[embedding_model] = EmbeddingService(model_name=embedding_model)

            embedding_service = self._embedding_services[embedding_model]

            # Create VectorStore
            base_vector_store = VectorStore(persist_directory, embedding_service)

            # Phase 6.11.3: Wrap with caching layer
            cached_vector_store = CachedVectorStore(base_vector_store)
            self._stores[normalized_path] = cached_vector_store

            return cached_vector_store

    def close_vector_store(self, persist_directory: str) -> None:
        """
        Close and remove a VectorStore instance.

        Args:
            persist_directory: ChromaDB storage path
        """
        import os
        normalized_path = os.path.abspath(persist_directory)

        with self._lock:
            if normalized_path in self._stores:
                self.logger.info(f"Closing VectorStore for {normalized_path}")
                # ChromaDB PersistentClient doesn't have explicit close, but we can remove reference
                del self._stores[normalized_path]

    def close_all(self) -> None:
        """Close all VectorStore instances"""
        with self._lock:
            self.logger.info(f"Closing all {len(self._stores)} VectorStore instances")
            self._stores.clear()

    def get_stats(self) -> Dict:
        """Get statistics about managed VectorStores"""
        with self._lock:
            return {
                "active_stores": len(self._stores),
                "paths": list(self._stores.keys()),
                "embedding_models": list(self._embedding_services.keys())
            }


# Global singleton instance
_manager = VectorStoreManager()


def get_vector_store(persist_directory: str, embedding_model: str = "all-MiniLM-L6-v2") -> VectorStore:
    """
    Convenience function to get a VectorStore instance.

    Args:
        persist_directory: ChromaDB storage path
        embedding_model: Embedding model name (default: all-MiniLM-L6-v2)

    Returns:
        VectorStore instance
    """
    return _manager.get_vector_store(persist_directory, embedding_model)


def close_vector_store(persist_directory: str) -> None:
    """
    Convenience function to close a VectorStore instance.

    Args:
        persist_directory: ChromaDB storage path
    """
    _manager.close_vector_store(persist_directory)


def get_manager_stats() -> Dict:
    """Get statistics about the VectorStore manager"""
    return _manager.get_stats()
