"""
v0.6.1: ChromaDB adapter — wraps existing VectorStore as a VectorStoreProvider.

This is the default adapter used when an agent has no external vector store configured
(vector_store_instance_id IS NULL). It delegates to the existing VectorStore/CachedVectorStore
via VectorStoreManager, preserving all existing behavior including query caching.

The key difference from the raw VectorStore: this adapter accepts pre-computed embeddings
rather than text (matching the VectorStoreProvider ABC). For backward compatibility,
the ProviderBridgeStore handles text-to-embedding conversion.
"""

import logging
import time
from typing import List, Dict, Optional, Tuple

from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult

logger = logging.getLogger(__name__)


class ChromaDBAdapter(VectorStoreProvider):
    """
    Wraps the existing VectorStore + CachedVectorStore singleton as a provider.
    """

    def __init__(self, persist_directory: str, embedding_service=None):
        from agent.memory.vector_store_manager import get_vector_store
        self._store = get_vector_store(persist_directory)
        self._persist_directory = persist_directory
        # Expose embedding_service for bridge compatibility
        self._embedding_service = embedding_service or self._store.embedding_service

    @property
    def embedding_service(self):
        return self._embedding_service

    @property
    def collection(self):
        """Direct access to ChromaDB collection (for legacy callers)."""
        return self._store.collection

    @property
    def persist_directory(self):
        return self._persist_directory

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        msg_metadata = {"sender_key": sender_key, "text": text}
        if metadata:
            msg_metadata.update(metadata)

        self._store.collection.upsert(
            ids=[message_id],
            embeddings=[embedding],
            metadatas=[msg_metadata],
            documents=[text],
        )

    async def add_batch(self, records: List[Dict]) -> None:
        if not records:
            return
        ids = [r["message_id"] for r in records]
        embeddings = [r["embedding"] for r in records]
        documents = [r["text"] for r in records]
        metadatas = []
        for r in records:
            meta = {"sender_key": r["sender_key"], "text": r["text"]}
            if r.get("metadata"):
                meta.update(r["metadata"])
            metadatas.append(meta)

        self._store.collection.upsert(
            ids=ids, embeddings=embeddings, metadatas=metadatas, documents=documents
        )

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[VectorRecord]:
        if self._store.collection.count() == 0:
            return []

        where_filter = {"sender_key": sender_key} if sender_key else None

        results = self._store.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_filter,
        )

        return self._format_results(results)

    async def search_similar_with_embeddings(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        if self._store.collection.count() == 0:
            return [], []

        where_filter = {"sender_key": sender_key} if sender_key else None

        results = self._store.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            where=where_filter,
            include=["documents", "metadatas", "distances", "embeddings"],
        )

        records = self._format_results(results)
        result_embeddings = []
        if results.get("embeddings") and results["embeddings"][0]:
            result_embeddings = list(results["embeddings"][0])
        else:
            result_embeddings = [[] for _ in records]

        return records, result_embeddings

    async def delete_message(self, message_id: str) -> None:
        self._store.collection.delete(ids=[message_id])

    async def delete_by_sender(self, sender_key: str) -> None:
        self._store.collection.delete(where={"sender_key": sender_key})

    async def clear_all(self) -> None:
        client = self._store.collection._client if hasattr(self._store.collection, '_client') else self._store.client
        try:
            client.delete_collection(name="whatsapp_messages")
        except Exception:
            pass
        self._store.collection = client.get_or_create_collection(
            name="whatsapp_messages",
            metadata={"description": "WhatsApp message embeddings"},
        )

    async def update_access_time(self, message_ids: List[str]) -> None:
        if not message_ids:
            return
        from datetime import datetime

        now_iso = datetime.utcnow().isoformat() + "Z"
        existing = self._store.collection.get(ids=message_ids, include=["metadatas"])
        if not existing or not existing["ids"]:
            return

        updated_metadatas = []
        for metadata in existing["metadatas"]:
            meta = dict(metadata) if metadata else {}
            meta["last_accessed_at"] = now_iso
            updated_metadatas.append(meta)

        self._store.collection.update(ids=existing["ids"], metadatas=updated_metadatas)

    async def health_check(self) -> ProviderHealthResult:
        start = time.time()
        try:
            count = self._store.collection.count()
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=True,
                latency_ms=latency,
                message="ChromaDB operational",
                vector_count=count,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=False, latency_ms=latency, message=str(e)
            )

    async def get_stats(self) -> Dict:
        return {
            "total_messages": self._store.collection.count(),
            "collection_name": self._store.collection.name,
            "persist_directory": self._persist_directory,
            "provider": "chromadb",
        }

    def _format_results(self, results: Dict) -> List[VectorRecord]:
        records = []
        if results["ids"] and len(results["ids"][0]) > 0:
            for i in range(len(results["ids"][0])):
                meta = results["metadatas"][0][i] if results.get("metadatas") else {}
                extra_meta = {
                    k: v for k, v in meta.items() if k not in ("sender_key", "text")
                }
                records.append(
                    VectorRecord(
                        message_id=results["ids"][0][i],
                        text=results["documents"][0][i] if results.get("documents") else "",
                        distance=results["distances"][0][i] if results.get("distances") else 0.0,
                        sender_key=meta.get("sender_key"),
                        metadata=extra_meta,
                    )
                )
        return records
