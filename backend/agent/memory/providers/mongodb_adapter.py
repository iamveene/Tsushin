"""
v0.6.1: MongoDB Atlas Vector Search adapter.

Uses pymongo with MongoDB Atlas $vectorSearch aggregation pipeline.
Requires MongoDB 7.0+ with Atlas Vector Search index configured.

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
    MongoDB Atlas Vector Search adapter.

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

    Requires an Atlas Vector Search index on the 'embedding' field.
    """

    def __init__(
        self,
        connection_string: str,
        database_name: str,
        collection_name: str,
        index_name: str = "vector_index",
        embedding_dims: int = 384,
        timeout_ms: int = 5000,
    ):
        try:
            from pymongo import MongoClient
        except ImportError:
            raise ProviderConnectionError(
                "pymongo is not installed. Install with: pip install 'pymongo[srv]'"
            )

        self._index_name = index_name
        self._embedding_dims = embedding_dims

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
            return ProviderHealthResult(
                healthy=True,
                latency_ms=latency,
                message="MongoDB Atlas connected",
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
