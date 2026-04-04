"""
v0.6.0: MongoDB Vector Search adapter.

Supports two modes:
- Atlas mode (default): Uses $vectorSearch aggregation pipeline (requires Atlas).
- Local mode: Computes cosine similarity in Python for self-hosted MongoDB.

Namespace convention: collection = tsushin_{tenant_id}_{agent_id}
"""

import logging
import time
from datetime import datetime
from typing import List, Dict, Optional, Tuple

from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult, ProviderConnectionError

logger = logging.getLogger(__name__)


class MongoDBVectorAdapter(VectorStoreProvider):
    """
    MongoDB Vector Search adapter.

    Stores documents as:
    {
        _id: message_id,
        text: str,
        sender_key: str,
        embedding: List[float],
        metadata: Dict,
        last_accessed_at: datetime,
        created_at: datetime
    }

    When use_native_search=True (default), requires Atlas Vector Search index.
    When use_native_search=False, computes cosine similarity locally (for self-hosted MongoDB).
    """

    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_name: str,
        index_name: str = "vector_index",
        embedding_dims: int = 384,
        timeout_ms: int = 5000,
        use_native_search: bool = True,
    ):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ProviderConnectionError(
                "pymongo is not installed. Install with: pip install 'pymongo[srv]'"
            )

        self._index_name = index_name
        self._embedding_dims = embedding_dims
        self._use_native_search = use_native_search

        try:
            self._client = MongoClient(
                connection_string,
                serverSelectionTimeoutMS=timeout_ms,
                connectTimeoutMS=timeout_ms,
                socketTimeoutMS=timeout_ms,
            )
            self._db = self._client[database_name]
            self._collection = self._db[collection_name]
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB connection failed: {e}")

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        embedding: List[float],
        metadata: Optional[Dict] = None,
    ) -> None:
        doc = {
            "_id": message_id,
            "text": text,
            "sender_key": sender_key,
            "embedding": embedding,
            "metadata": metadata or {},
            "last_accessed_at": datetime.utcnow(),
            "created_at": datetime.utcnow(),
        }
        try:
            self._collection.replace_one({"_id": message_id}, doc, upsert=True)
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB add_message failed: {e}")

    async def add_batch(self, records: List[Dict]) -> None:
        if not records:
            return
        from pymongo import ReplaceOne

        ops = []
        now = datetime.utcnow()
        for r in records:
            doc = {
                "_id": r["message_id"],
                "text": r["text"],
                "sender_key": r["sender_key"],
                "embedding": r["embedding"],
                "metadata": r.get("metadata", {}),
                "last_accessed_at": now,
                "created_at": now,
            }
            ops.append(ReplaceOne({"_id": r["message_id"]}, doc, upsert=True))

        try:
            self._collection.bulk_write(ops, ordered=False)
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB add_batch failed: {e}")

    async def search_similar(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[VectorRecord]:
        if not self._use_native_search:
            import asyncio
            return await asyncio.to_thread(self._local_cosine_search, query_embedding, limit, sender_key)

        pipeline = self._build_search_pipeline(query_embedding, limit, sender_key)

        try:
            results = list(self._collection.aggregate(pipeline))
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB search failed: {e}")

        return [
            VectorRecord(
                message_id=str(doc["_id"]),
                text=doc.get("text", ""),
                distance=1.0 - doc.get("score", 0.0),  # Convert similarity to distance
                sender_key=doc.get("sender_key"),
                metadata=doc.get("metadata", {}),
            )
            for doc in results
        ]

    async def search_similar_with_embeddings(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        if not self._use_native_search:
            import asyncio
            return await asyncio.to_thread(self._local_cosine_search_with_embeddings, query_embedding, limit, sender_key)

        pipeline = self._build_search_pipeline(query_embedding, limit, sender_key)

        try:
            results = list(self._collection.aggregate(pipeline))
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB search_with_embeddings failed: {e}")

        records = []
        embeddings = []
        for doc in results:
            records.append(
                VectorRecord(
                    message_id=str(doc["_id"]),
                    text=doc.get("text", ""),
                    distance=1.0 - doc.get("score", 0.0),
                    sender_key=doc.get("sender_key"),
                    metadata=doc.get("metadata", {}),
                )
            )
            embeddings.append(doc.get("embedding", []))

        return records, embeddings

    async def delete_message(self, message_id: str) -> None:
        try:
            self._collection.delete_one({"_id": message_id})
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB delete failed: {e}")

    async def delete_by_sender(self, sender_key: str) -> None:
        try:
            self._collection.delete_many({"sender_key": sender_key})
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB delete_by_sender failed: {e}")

    async def clear_all(self) -> None:
        try:
            self._collection.delete_many({})
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB clear_all failed: {e}")

    async def update_access_time(self, message_ids: List[str]) -> None:
        if not message_ids:
            return
        try:
            self._collection.update_many(
                {"_id": {"$in": message_ids}},
                {"$set": {"last_accessed_at": datetime.utcnow()}},
            )
        except Exception as e:
            logger.warning(f"MongoDB update_access_time failed: {e}")

    async def health_check(self) -> ProviderHealthResult:
        start = time.time()
        try:
            self._client.admin.command("ping")
            count = self._collection.count_documents({})
            latency = int((time.time() - start) * 1000)
            mode = "Atlas" if self._use_native_search else "Local"
            return ProviderHealthResult(
                healthy=True,
                latency_ms=latency,
                message=f"MongoDB ({mode}) connected",
                vector_count=count,
            )
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return ProviderHealthResult(
                healthy=False, latency_ms=latency, message=str(e)
            )

    async def get_stats(self) -> Dict:
        try:
            count = self._collection.count_documents({})
        except Exception:
            count = -1
        return {
            "total_messages": count,
            "collection_name": self._collection.name,
            "database_name": self._db.name,
            "index_name": self._index_name,
            "provider": "mongodb",
        }

    def _build_search_pipeline(
        self, query_embedding: List[float], limit: int, sender_key: Optional[str]
    ) -> List[Dict]:
        search_stage = {
            "$vectorSearch": {
                "index": self._index_name,
                "path": "embedding",
                "queryVector": query_embedding,
                "numCandidates": limit * 10,
                "limit": limit,
            }
        }
        if sender_key:
            search_stage["$vectorSearch"]["filter"] = {"sender_key": {"$eq": sender_key}}

        pipeline = [
            search_stage,
            {"$addFields": {"score": {"$meta": "vectorSearchScore"}}},
            {
                "$project": {
                    "_id": 1,
                    "text": 1,
                    "sender_key": 1,
                    "embedding": 1,
                    "metadata": 1,
                    "score": 1,
                }
            },
        ]
        return pipeline

    def _local_cosine_search(
        self, query_embedding: List[float], limit: int, sender_key: Optional[str]
    ) -> List[VectorRecord]:
        """Compute cosine similarity in Python for self-hosted MongoDB (no Atlas)."""
        import numpy as np

        query_filter: Dict = {}
        if sender_key:
            query_filter["sender_key"] = sender_key

        try:
            docs = list(self._collection.find(query_filter, {"_id": 1, "text": 1, "sender_key": 1, "embedding": 1, "metadata": 1}))
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB local search failed: {e}")

        if not docs:
            return []

        q = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm < 1e-10:
            return []

        scored = []
        for doc in docs:
            emb = doc.get("embedding")
            if not emb or len(emb) != len(query_embedding):
                continue
            e = np.array(emb, dtype=np.float32)
            e_norm = np.linalg.norm(e)
            if e_norm < 1e-10:
                continue
            cos_sim = float(np.dot(q, e) / (q_norm * e_norm))
            scored.append((doc, cos_sim))

        scored.sort(key=lambda x: x[1], reverse=True)

        return [
            VectorRecord(
                message_id=str(doc["_id"]),
                text=doc.get("text", ""),
                distance=1.0 - sim,
                sender_key=doc.get("sender_key"),
                metadata=doc.get("metadata", {}),
            )
            for doc, sim in scored[:limit]
        ]

    def _local_cosine_search_with_embeddings(
        self, query_embedding: List[float], limit: int, sender_key: Optional[str]
    ) -> Tuple[List[VectorRecord], List[List[float]]]:
        """Local cosine search returning embeddings too."""
        import numpy as np

        query_filter: Dict = {}
        if sender_key:
            query_filter["sender_key"] = sender_key

        try:
            docs = list(self._collection.find(query_filter, {"_id": 1, "text": 1, "sender_key": 1, "embedding": 1, "metadata": 1}))
        except Exception as e:
            raise ProviderConnectionError(f"MongoDB local search failed: {e}")

        if not docs:
            return [], []

        q = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm < 1e-10:
            return [], []

        scored = []
        for doc in docs:
            emb = doc.get("embedding")
            if not emb or len(emb) != len(query_embedding):
                continue
            e = np.array(emb, dtype=np.float32)
            e_norm = np.linalg.norm(e)
            if e_norm < 1e-10:
                continue
            cos_sim = float(np.dot(q, e) / (q_norm * e_norm))
            scored.append((doc, cos_sim))

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:limit]

        records = [
            VectorRecord(
                message_id=str(doc["_id"]),
                text=doc.get("text", ""),
                distance=1.0 - sim,
                sender_key=doc.get("sender_key"),
                metadata=doc.get("metadata", {}),
            )
            for doc, sim in top
        ]
        embeddings = [doc.get("embedding", []) for doc, _ in top]

        return records, embeddings
