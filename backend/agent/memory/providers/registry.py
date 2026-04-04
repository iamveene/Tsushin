"""
v0.6.1: Vector Store Registry — singleton cache of provider instances.

Manages lifecycle of vector store adapters, keyed by instance_id.
Includes circuit breaker per instance for fail-open fallback to ChromaDB.
Thread-safe via Lock.
"""

import logging
from threading import Lock
from typing import Dict, Optional

from services.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState
from .base import VectorStoreProvider, ProviderConnectionError
from .chroma_adapter import ChromaDBAdapter

logger = logging.getLogger(__name__)

# Vendor -> adapter class mapping
VENDOR_ADAPTERS = {
    "chromadb": "agent.memory.providers.chroma_adapter.ChromaDBAdapter",
    "mongodb": "agent.memory.providers.mongodb_adapter.MongoDBVectorAdapter",
    "pinecone": "agent.memory.providers.pinecone_adapter.PineconeVectorAdapter",
    "qdrant": "agent.memory.providers.qdrant_adapter.QdrantVectorAdapter",
}

VALID_VENDORS = set(VENDOR_ADAPTERS.keys())


class VectorStoreRegistry:
    """
    Singleton registry that caches live provider instances by vector_store_instance_id.
    Manages circuit breakers per instance for fail-open fallback to ChromaDB.
    """

    _instance = None
    _lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    inst = super().__new__(cls)
                    inst._providers: Dict[int, VectorStoreProvider] = {}
                    inst._circuit_breakers: Dict[int, CircuitBreaker] = {}
                    inst._chromadb_cache: Dict[str, ChromaDBAdapter] = {}
                    inst._provider_lock = Lock()
                    cls._instance = inst
        return cls._instance

    def get_provider(self, instance_id: int, db, tenant_id: str = None) -> VectorStoreProvider:
        """
        Get or create a provider adapter for the given vector store instance.
        Decrypts credentials on first access and caches the adapter.
        tenant_id is required for multi-tenancy isolation — prevents cross-tenant access.
        """
        if instance_id in self._providers:
            return self._providers[instance_id]

        with self._provider_lock:
            # Double-check after acquiring lock
            if instance_id in self._providers:
                return self._providers[instance_id]

            from models import VectorStoreInstance
            query = db.query(VectorStoreInstance).filter(
                VectorStoreInstance.id == instance_id,
                VectorStoreInstance.is_active == True,
            )
            # Multi-tenancy guard: prevent cross-tenant vector store access
            if tenant_id:
                query = query.filter(VectorStoreInstance.tenant_id == tenant_id)

            instance = query.first()

            if not instance:
                raise ProviderConnectionError(
                    f"VectorStoreInstance {instance_id} not found or inactive"
                )

            adapter = self._create_adapter(instance, db)
            self._providers[instance_id] = adapter
            return adapter

    def get_chromadb_fallback(self, persist_directory: str) -> ChromaDBAdapter:
        """Get or create a ChromaDB adapter for fallback. Always available."""
        if persist_directory in self._chromadb_cache:
            return self._chromadb_cache[persist_directory]

        with self._provider_lock:
            if persist_directory in self._chromadb_cache:
                return self._chromadb_cache[persist_directory]

            adapter = ChromaDBAdapter(persist_directory)
            self._chromadb_cache[persist_directory] = adapter
            return adapter

    def get_circuit_breaker(self, instance_id: int) -> CircuitBreaker:
        """Get or create a circuit breaker for an instance. Thread-safe."""
        if instance_id in self._circuit_breakers:
            return self._circuit_breakers[instance_id]
        with self._provider_lock:
            if instance_id not in self._circuit_breakers:
                self._circuit_breakers[instance_id] = CircuitBreaker(
                    config=CircuitBreakerConfig(
                        failure_threshold=3,
                        recovery_timeout_seconds=60,
                        half_open_max_failures=1,
                        success_threshold=2,
                    )
                )
            return self._circuit_breakers[instance_id]

    def evict(self, instance_id: int) -> None:
        """Remove cached provider (called on instance update/delete)."""
        with self._provider_lock:
            self._providers.pop(instance_id, None)
            self._circuit_breakers.pop(instance_id, None)

    def evict_all(self) -> None:
        """Clear all cached providers."""
        with self._provider_lock:
            self._providers.clear()
            self._circuit_breakers.clear()
            self._chromadb_cache.clear()

    def _create_adapter(self, instance, db) -> VectorStoreProvider:
        """Instantiate the correct adapter based on vendor type."""
        vendor = instance.vendor
        if vendor not in VALID_VENDORS:
            raise ProviderConnectionError(f"Unknown vendor: {vendor}")

        # Decrypt credentials
        credentials = self._decrypt_credentials(instance, db)
        extra_config = instance.extra_config or {}

        if vendor == "chromadb":
            persist_dir = instance.base_url or extra_config.get("persist_directory", "")
            return ChromaDBAdapter(persist_dir)

        elif vendor == "mongodb":
            from .mongodb_adapter import MongoDBVectorAdapter
            connection_string = credentials.get("connection_string") or instance.base_url
            if not connection_string:
                raise ProviderConnectionError("MongoDB requires a connection string")
            return MongoDBVectorAdapter(
                connection_string=connection_string,
                database_name=extra_config.get("database_name", "tsushin"),
                collection_name=extra_config.get("collection_name", "vectors"),
                index_name=extra_config.get("index_name", "vector_index"),
                embedding_dims=extra_config.get("embedding_dims", 384),
                use_native_search=extra_config.get("use_native_search", True),
            )

        elif vendor == "pinecone":
            from .pinecone_adapter import PineconeVectorAdapter
            api_key = credentials.get("api_key", "")
            if not api_key:
                raise ProviderConnectionError("Pinecone requires an API key")
            return PineconeVectorAdapter(
                api_key=api_key,
                index_name=extra_config.get("index_name", "tsushin"),
                namespace=extra_config.get("namespace", ""),
                environment=extra_config.get("environment", ""),
                embedding_dims=extra_config.get("embedding_dims", 384),
            )

        elif vendor == "qdrant":
            from .qdrant_adapter import QdrantVectorAdapter
            url = instance.base_url
            if not url:
                raise ProviderConnectionError("Qdrant requires a base URL")
            return QdrantVectorAdapter(
                url=url,
                collection_name=extra_config.get("collection_name", "tsushin"),
                api_key=credentials.get("api_key"),
                embedding_dims=extra_config.get("embedding_dims", 384),
            )

        raise ProviderConnectionError(f"Unhandled vendor: {vendor}")

    def _decrypt_credentials(self, instance, db) -> Dict:
        """Decrypt the credentials_encrypted JSON blob."""
        if not instance.credentials_encrypted:
            return {}

        try:
            import json
            from hub.security import TokenEncryption
            from services.encryption_key_service import get_api_key_encryption_key

            encryption_key = get_api_key_encryption_key(db)
            identifier = f"vector_store_{instance.tenant_id}"
            encryptor = TokenEncryption(encryption_key.encode())
            decrypted = encryptor.decrypt(instance.credentials_encrypted, identifier)
            return json.loads(decrypted)
        except Exception as e:
            logger.error(f"Failed to decrypt credentials for instance {instance.id}: {e}")
            return {}
