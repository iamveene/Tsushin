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
    """

    def __init__(self, provider: VectorStoreProvider, embedding_service):
        self._provider = provider
        self._embedding_service = embedding_service

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
        return self._records_to_dicts(records)

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

    def delete_message(self, message_id: str) -> None:
        """Sync wrapper for delete_message."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._provider.delete_message(message_id))
        except RuntimeError:
            asyncio.run(self._provider.delete_message(message_id))

    def delete_by_sender(self, sender_key: str) -> None:
        """Sync wrapper for delete_by_sender."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._provider.delete_by_sender(sender_key))
        except RuntimeError:
            asyncio.run(self._provider.delete_by_sender(sender_key))

    def clear_all(self) -> None:
        """Sync wrapper for clear_all."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._provider.clear_all())
        except RuntimeError:
            asyncio.run(self._provider.clear_all())

    def update_access_time(self, message_ids: List[str]) -> None:
        """Sync wrapper for update_access_time."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._provider.update_access_time(message_ids))
        except RuntimeError:
            asyncio.run(self._provider.update_access_time(message_ids))

    def get_stats(self) -> Dict:
        """Sync wrapper for get_stats."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # Can't await in sync context, return basic info
            return {"provider": "external_bridge", "persist_directory": self.persist_directory}
        except RuntimeError:
            return asyncio.run(self._provider.get_stats())

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
