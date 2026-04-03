"""
v0.6.1: Pinecone vector store adapter.

Uses the Pinecone SDK for serverless vector search.
Distance convention: Pinecone returns similarity (0-1), we convert to distance = 1 - score.

Namespace convention: tsushin_{tenant_id}_{agent_id}
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult, ProviderConnectionError

logger = logging.getLogger(__name__)


class PineconeVectorAdapter(VectorStoreProvider):
    """
    Pinecone serverless vector store adapter.

    Stores vectors with metadata: sender_key, text, last_accessed_at.
    Uses Pinecone namespaces for agent isolation.
    """

    def __init__(
        self,
        api_key: str,
        index_name: str,
        namespace: str = "",
        environment: str = "",
        embedding_dims: int = 384,
        timeout_seconds: int = 5,
    ):
        try:
            from pinecone import Pinecone
        except ImportError:
            raise ProviderConnectionError(
                "pinecone-client is not installed. Install with: pip install pinecone-client"
            )

        self._namespace = namespace
        self._embedding_dims = embedding_dims

        try:
            self._pc = Pinecone(api_key=api_key, timeout=timeout_seconds)
            self._index = self._pc.Index(index_name)
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone connection failed: {e}")

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        meta = {
            "sender_key": sender_key,
            "text": text[:1000],  # Pinecone metadata size limit
            "last_accessed_at": datetime.utcnow().isoformat(),
        }
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    meta[k] = v

        try:
            self._index.upsert(
                vectors=[{"id": message_id, "values": embedding, "metadata": meta}],
                namespace=self._namespace,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone add_message failed: {e}")

    async def add_batch(self, records: List[Dict]) -> None:
        if not records:
            return

        vectors = []
        for r in records:
            meta = {
                "sender_key": r["sender_key"],
                "text": r["text"][:1000],
                "last_accessed_at": datetime.utcnow().isoformat(),
            }
            if r.get("metadata"):
                for k, v in r["metadata"].items():
                    if isinstance(v, (str, int, float, bool)):
                        meta[k] = v
            vectors.append({
                "id": r["message_id"],
                "values": r["embedding"],
                "metadata": meta,
            })

        try:
            # Pinecone batch upsert limit: 100 vectors
            for i in range(0, len(vectors), 100):
                batch = vectors[i : i + 100]
                self._index.upsert(vectors=batch, namespace=self._namespace)
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone add_batch failed: {e}")

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[VectorRecord]:
        filter_dict = {"sender_key": {"$eq": sender_key}} if sender_key else None

        try:
            results = self._index.query(
                vector=query_embedding,
                top_k=limit,
                namespace=self._namespace,
                filter=filter_dict,
                include_metadata=True,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone search failed: {e}")

        return [
            VectorRecord(
                message_id=match["id"],
                text=match.get("metadata", {}).get("text", ""),
                distance=1.0 - match.get("score", 0.0),  # Convert similarity to distance
                sender_key=match.get("metadata", {}).get("sender_key"),
                metadata={
                    k: v
                    for k, v in match.get("metadata", {}).items()
                    if k not in ("sender_key", "text")
                },
            )
            for match in results.get("matches", [])
        ]

    async def search_similar_with_embeddings(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        filter_dict = {"sender_key": {"$eq": sender_key}} if sender_key else None

        try:
            results = self._index.query(
                vector=query_embedding,
                top_k=limit,
                namespace=self._namespace,
                filter=filter_dict,
                include_metadata=True,
                include_values=True,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone search_with_embeddings failed: {e}")

        records = []
        embeddings = []
        for match in results.get("matches", []):
            records.append(
                VectorRecord(
                    message_id=match["id"],
                    text=match.get("metadata", {}).get("text", ""),
                    distance=1.0 - match.get("score", 0.0),
                    sender_key=match.get("metadata", {}).get("sender_key"),
                    metadata={
                        k: v
                        for k, v in match.get("metadata", {}).items()
                        if k not in ("sender_key", "text")
                    },
                )
            )
            embeddings.append(match.get("values", []))

        return records, embeddings

    async def delete_message(self, message_id: str) -> None:
        try:
            self._index.delete(ids=[message_id], namespace=self._namespace)
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone delete failed: {e}")

    async def delete_by_sender(self, sender_key: str) -> None:
        try:
            self._index.delete(
                filter={"sender_key": {"$eq": sender_key}},
                namespace=self._namespace,
            )
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone delete_by_sender failed: {e}")

    async def clear_all(self) -> None:
        try:
            self._index.delete(delete_all=True, namespace=self._namespace)
        except Exception as e:
            raise ProviderConnectionError(f"Pinecone clear_all failed: {e}")

    async def update_access_time(self, message_ids: List[str]) -> None:
        if not message_ids:
            return
        now_iso = datetime.utcnow().isoformat()
        try:
            for mid in message_ids:
                self._index.update(
                    id=mid,
                    set_metadata={"last_accessed_at": now_iso},
                    namespace=self._namespace,
                )
        except Exception as e:
            logger.warning(f"Pinecone update_access_time failed: {e}")

    async def health_check(self) -> ProviderHealthResult:
        start = time.time()
        try:
            stats = self._index.describe_index_stats()
            ns_stats = stats.get("namespaces", {}).get(self._namespace, {})
            count = ns_stats.get("vector_count", 0)
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=True,
                latency_ms=latency,
                message="Pinecone connected",
                vector_count=count,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=False, latency_ms=latency, message=str(e)
            )

    async def get_stats(self) -> Dict:
        try:
            stats = self._index.describe_index_stats()
            ns_stats = stats.get("namespaces", {}).get(self._namespace, {})
            return {
                "total_messages": ns_stats.get("vector_count", 0),
                "namespace": self._namespace,
                "total_vector_count": stats.get("total_vector_count", 0),
                "provider": "pinecone",
            }
        except Exception:
            return {"total_messages": -1, "namespace": self._namespace, "provider": "pinecone"}
