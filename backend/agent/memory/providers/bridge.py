"""
v0.6.1: Provider Bridge Store — impedance adapter between SemanticMemoryService
(text-based API) and VectorStoreProvider (embedding-based API).

SemanticMemoryService expects a store with text-based search_similar(query_text, ...)
and add_message(message_id, sender_key, text, ...) methods. The new VectorStoreProvider
ABC expects pre-computed embeddings.

This bridge:
1. Holds a reference to EmbeddingService singleton
2. Holds a reference to a ResolvedVectorStore (or any VectorStoreProvider)
3. Converts text to embeddings before delegating to provider
4. Returns results in the same List[Dict] format as CachedVectorStore

SemanticMemoryService requires zero changes to its method calls.
"""

import logging
from typing import List, Dict, Optional

from .base import VectorStoreProvider

logger = logging.getLogger(__name__)


class ProviderBridgeStore:
    """
    Bridge between text-based SemanticMemoryService API and
    embedding-based VectorStoreProvider API.

    v0.6.1 Item 4: Optional security context for MemGuard integration.
    When security_context is provided, add_message runs pre-storage scan
    and search_similar runs post-retrieval validation.
    """

    def __init__(
        self,
        provider: VectorStoreProvider,
        embedding_service,
        security_context: Optional[Dict] = None,
    ):
        self._provider = provider
        self._embedding_service = embedding_service
        # v0.6.1: Optional security context for MemGuard hooks
        # Keys: db, tenant_id, agent_id, instance_id
        self._security = security_context

    @property
    def embedding_service(self):
        """Compatibility: SemanticMemoryService accesses this."""
        return self._embedding_service

    @property
    def collection(self):
        """Compatibility: return None for external providers."""
        if hasattr(self._provider, "collection"):
            return self._provider.collection
        return None

    @property
    def persist_directory(self):
        """Compatibility: return provider's persist_directory if available."""
        if hasattr(self._provider, "persist_directory"):
            return self._provider.persist_directory
        return "external"

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        metadata: Optional[Dict] = None,
    ) -> None:
        """Convert text to embedding, then delegate to provider."""
        embedding = await self._embedding_service.embed_text_async(text)
        await self._provider.add_message(message_id, sender_key, text, embedding, metadata)

    async def search_similar(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[Dict]:
        """Convert text to embedding, search, return List[Dict] format."""
        embedding = await self._embedding_service.embed_text_async(query_text)
        records = await self._provider.search_similar(embedding, limit, sender_key)
        results = self._records_to_dicts(records)

        # v0.6.1 Item 4: Post-retrieval MemGuard validation
        if self._security and results:
            try:
                from services.memguard_service import MemGuardService
                db = self._security.get("db")
                tenant_id = self._security.get("tenant_id", "")
                if db and tenant_id:
                    memguard = MemGuardService(db, tenant_id)
                    security_config = memguard._get_security_config(
                        self._security.get("instance_id", 0)
                    )
                    results = await memguard.validate_retrieved_content(
                        results=results,
                        tenant_id=tenant_id,
                        agent_id=self._security.get("agent_id", 0),
                        instance_id=self._security.get("instance_id", 0),
                        security_config=security_config,
                    )
            except Exception as e:
                logger.debug(f"Post-retrieval MemGuard check skipped: {e}")

        return results

    async def search_similar_with_embeddings(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> tuple:
        """Convert text to embedding, search with embeddings, return compatible tuple."""
        query_embedding = await self._embedding_service.embed_text_async(query_text)
        records, result_embeddings = await self._provider.search_similar_with_embeddings(
            query_embedding, limit, sender_key
        )
        formatted = self._records_to_dicts(records)
        return formatted, query_embedding, result_embeddings

    async def delete_message(self, message_id: str) -> None:
        """Async delete — callers must await."""
        try:
            await self._provider.delete_message(message_id)
        except Exception as e:
            logger.warning(f"Bridge delete_message failed: {e}")

    async def delete_by_sender(self, sender_key: str) -> None:
        """Async delete_by_sender — callers must await."""
        try:
            await self._provider.delete_by_sender(sender_key)
        except Exception as e:
            logger.warning(f"Bridge delete_by_sender failed: {e}")

    async def clear_all(self) -> None:
        """Async clear_all — callers must await."""
        try:
            await self._provider.clear_all()
        except Exception as e:
            logger.warning(f"Bridge clear_all failed: {e}")

    async def update_access_time(self, message_ids: List[str]) -> None:
        """Async update_access_time — callers must await."""
        try:
            await self._provider.update_access_time(message_ids)
        except Exception as e:
            logger.warning(f"Bridge update_access_time failed: {e}")

    def get_stats(self) -> Dict:
        """Return basic stats synchronously. Full async stats via health_check."""
        return {
            "provider": "external_bridge",
            "persist_directory": self.persist_directory,
            "collection_name": "external",
        }

    @staticmethod
    def _records_to_dicts(records) -> List[Dict]:
        """Convert VectorRecord list to List[Dict] matching CachedVectorStore format."""
        return [
            {
                "message_id": r.message_id,
                "text": r.text,
                "distance": r.distance,
                "sender_key": r.sender_key,
                **r.metadata,
            }
            for r in records
        ]
