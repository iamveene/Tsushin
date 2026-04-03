"""
v0.6.1: Qdrant vector store adapter.

Uses qdrant-client for self-hosted or Qdrant Cloud vector search.
Supports both cosine and dot product distance metrics.

Namespace convention: collection = tsushin_{tenant_id}_{agent_id}
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult, ProviderConnectionError

logger = logging.getLogger(__name__)


class QdrantVectorAdapter(VectorStoreProvider):
    """
    Qdrant vector store adapter.

    Uses Qdrant's point-based storage with payload filtering.
    Collection auto-creation with cosine distance metric.
    """

    def __init__(
        self,
        url: str,
        collection_name: str,
        api_key: Optional[str] = None,
        embedding_dims: int = 384,
        timeout_seconds: int = 5,
    ):
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams
        except ImportError:
            raise ProviderConnectionError(
                "qdrant-client is not installed. Install with: pip install qdrant-client"
            )

        self._collection_name = collection_name
        self._embedding_dims = embedding_dims

        try:
            self._client = QdrantClient(
                url=url,
                api_key=api_key,
                timeout=timeout_seconds,
            )
            # Auto-create collection if it doesn't exist
            collections = [c.name for c in self._client.get_collections().collections]
            if collection_name not in collections:
                self._client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=embedding_dims,
                        distance=Distance.COSINE,
                    ),
                )
                # Create payload index for sender_key filtering
                self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name="sender_key",
                    field_schema="keyword",
                )
                logger.info(f"Created Qdrant collection: {collection_name}")
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant connection failed: {e}")

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        from qdrant_client.models import PointStruct

        payload = {
            "sender_key": sender_key,
            "text": text,
            "last_accessed_at": datetime.utcnow().isoformat(),
        }
        if metadata:
            payload.update(metadata)

        try:
            self._client.upsert(
                collection_name=self._collection_name,
                points=[
                    PointStruct(
                        id=self._hash_id(message_id),
                        vector=embedding,
                        payload={"message_id": message_id, **payload},
                    )
                ],
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant add_message failed: {e}")

    async def add_batch(self, records: List[Dict]) -> None:
        if not records:
            return
        from qdrant_client.models import PointStruct

        points = []
        now = datetime.utcnow().isoformat()
        for r in records:
            payload = {
                "message_id": r["message_id"],
                "sender_key": r["sender_key"],
                "text": r["text"],
                "last_accessed_at": now,
            }
            if r.get("metadata"):
                payload.update(r["metadata"])
            points.append(
                PointStruct(
                    id=self._hash_id(r["message_id"]),
                    vector=r["embedding"],
                    payload=payload,
                )
            )

        try:
            # Qdrant batch limit: 100 points per request
            for i in range(0, len(points), 100):
                batch = points[i : i + 100]
                self._client.upsert(
                    collection_name=self._collection_name, points=batch
                )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant add_batch failed: {e}")

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[VectorRecord]:
        query_filter = self._build_filter(sender_key)

        try:
            results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant search failed: {e}")

        return [
            VectorRecord(
                message_id=hit.payload.get("message_id", str(hit.id)),
                text=hit.payload.get("text", ""),
                distance=1.0 - hit.score,  # Cosine similarity to distance
                sender_key=hit.payload.get("sender_key"),
                metadata={
                    k: v
                    for k, v in hit.payload.items()
                    if k not in ("message_id", "sender_key", "text")
                },
            )
            for hit in results
        ]

    async def search_similar_with_embeddings(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        query_filter = self._build_filter(sender_key)

        try:
            results = self._client.search(
                collection_name=self._collection_name,
                query_vector=query_embedding,
                limit=limit,
                query_filter=query_filter,
                with_payload=True,
                with_vectors=True,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant search_with_embeddings failed: {e}")

        records = []
        embeddings = []
        for hit in results:
            records.append(
                VectorRecord(
                    message_id=hit.payload.get("message_id", str(hit.id)),
                    text=hit.payload.get("text", ""),
                    distance=1.0 - hit.score,
                    sender_key=hit.payload.get("sender_key"),
                    metadata={
                        k: v
                        for k, v in hit.payload.items()
                        if k not in ("message_id", "sender_key", "text")
                    },
                )
            )
            embeddings.append(hit.vector if hit.vector else [])

        return records, embeddings

    async def delete_message(self, message_id: str) -> None:
        from qdrant_client.models import PointIdsList

        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=PointIdsList(points=[self._hash_id(message_id)]),
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant delete failed: {e}")

    async def delete_by_sender(self, sender_key: str) -> None:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        try:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="sender_key", match=MatchValue(value=sender_key)
                        )
                    ]
                ),
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant delete_by_sender failed: {e}")

    async def clear_all(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        try:
            self._client.delete_collection(self._collection_name)
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(
                    size=self._embedding_dims,
                    distance=Distance.COSINE,
                ),
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="sender_key",
                field_schema="keyword",
            )
        except Exception as e:
            raise ProviderConnectionError(f"Qdrant clear_all failed: {e}")

    async def update_access_time(self, message_ids: List[str]) -> None:
        if not message_ids:
            return
        now_iso = datetime.utcnow().isoformat()
        try:
            point_ids = [self._hash_id(mid) for mid in message_ids]
            self._client.set_payload(
                collection_name=self._collection_name,
                payload={"last_accessed_at": now_iso},
                points=point_ids,
            )
        except Exception as e:
            logger.warning(f"Qdrant update_access_time failed: {e}")

    async def health_check(self) -> ProviderHealthResult:
        start = time.time()
        try:
            info = self._client.get_collection(self._collection_name)
            count = info.points_count
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=True,
                latency_ms=latency,
                message="Qdrant connected",
                vector_count=count,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=False, latency_ms=latency, message=str(e)
            )

    async def get_stats(self) -> Dict:
        try:
            info = self._client.get_collection(self._collection_name)
            return {
                "total_messages": info.points_count,
                "collection_name": self._collection_name,
                "vectors_count": info.vectors_count,
                "indexed_vectors_count": getattr(info, "indexed_vectors_count", None),
                "provider": "qdrant",
            }
        except Exception:
            return {
                "total_messages": -1,
                "collection_name": self._collection_name,
                "provider": "qdrant",
            }

    def _build_filter(self, sender_key: Optional[str]):
        if not sender_key:
            return None
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        return Filter(
            must=[FieldCondition(key="sender_key", match=MatchValue(value=sender_key))]
        )

    @staticmethod
    def _hash_id(message_id: str) -> int:
        """Convert string ID to integer (Qdrant uses integer point IDs by default)."""
        import hashlib

        return int(hashlib.sha256(message_id.encode()).hexdigest()[:16], 16)
