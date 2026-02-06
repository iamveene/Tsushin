"""
Phase 6.11.3: Cached Vector Store

Wraps VectorStore with query result caching to reduce expensive vector searches.

Performance Goals:
- 50%+ cache hit rate (similar queries repeated)
- ~200-500ms saved per cache hit
- 500 query capacity with 10-minute TTL
"""

import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import logging
from .vector_store import VectorStore

logger = logging.getLogger(__name__)


class CachedVectorStore:
    """
    Vector store wrapper with query result caching (Phase 6.11.3).

    Cache Strategy:
    - Cache search results by query hash
    - 10-minute TTL (longer than contacts due to less frequent updates)
    - 500 query maximum
    - MD5 hash key: normalized_query + limit + sender_key

    Expected Performance:
    - 50%+ cache hit rate (similar queries repeated)
    - ~200-500ms saved per cache hit (vector search eliminated)
    """

    def __init__(self, vector_store: VectorStore):
        """
        Initialize cached vector store.

        Args:
            vector_store: VectorStore instance to wrap
        """
        self.vector_store = vector_store
        self._query_cache: Dict[str, Tuple[datetime, List[Dict]]] = {}
        self._cache_ttl = timedelta(minutes=10)
        self._cache_hits = 0
        self._cache_misses = 0
        self._max_cache_size = 500
        self.logger = logging.getLogger(__name__)

    def search_similar(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None
    ) -> List[Dict]:
        """
        Search with result caching.

        Args:
            query_text: Text to search for
            limit: Maximum number of results
            sender_key: Optional filter by sender

        Returns:
            List of search results (from cache or vector store)
        """
        # Generate cache key
        cache_key = self._generate_cache_key(query_text, limit, sender_key)
        now = datetime.utcnow()

        # Check cache
        if cache_key in self._query_cache:
            cached_time, results = self._query_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                self._cache_hits += 1
                self.logger.debug(f"Vector search cache HIT for query hash {cache_key[:8]}...")
                return results
            else:
                # Expired, remove
                del self._query_cache[cache_key]
                self.logger.debug(f"Vector search cache EXPIRED for query hash {cache_key[:8]}...")

        # Cache miss - perform vector search
        self._cache_misses += 1
        self.logger.debug(f"Vector search cache MISS for query hash {cache_key[:8]}..., performing search")

        # Call underlying vector store search
        results = self.vector_store.search_similar(
            query_text=query_text,
            limit=limit,
            sender_key=sender_key
        )

        # Store in cache
        self._query_cache[cache_key] = (now, results)

        # Evict if needed
        self._evict_if_needed(now)

        return results

    def _generate_cache_key(self, query: str, limit: int, sender_key: Optional[str]) -> str:
        """
        Generate cache key from query parameters.

        Includes:
        - normalized query (lowercase, stripped)
        - limit (different result counts cached separately)
        - sender_key (prevent cross-sender cache pollution)
        """
        # Normalize query
        normalized = query.lower().strip()

        # Build key string
        sender_part = sender_key if sender_key else "all"
        key_string = f"query_{normalized}:limit_{limit}:sender_{sender_part}"

        # Hash to fixed-length (32 chars)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _evict_if_needed(self, now: datetime):
        """Evict expired or excess entries"""
        # Remove expired
        expired = [
            key for key, (cached_time, _) in self._query_cache.items()
            if now - cached_time > self._cache_ttl
        ]
        for key in expired:
            del self._query_cache[key]

        if expired:
            self.logger.debug(f"Evicted {len(expired)} expired vector search cache entries")

        # If still too large, remove oldest (LRU)
        if len(self._query_cache) > self._max_cache_size:
            sorted_entries = sorted(
                self._query_cache.items(),
                key=lambda x: x[1][0]  # Sort by timestamp
            )
            to_remove = len(self._query_cache) - self._max_cache_size
            for key, _ in sorted_entries[:to_remove]:
                del self._query_cache[key]

            self.logger.info(f"Evicted {to_remove} LRU vector search cache entries (max size reached)")

    def clear_cache(self):
        """Clear all cached search results"""
        cache_size = len(self._query_cache)
        self._query_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0
        self.logger.info(f"Vector search cache cleared ({cache_size} entries removed)")

    def get_cache_stats(self) -> Dict:
        """Get cache performance statistics"""
        total = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total * 100) if total > 0 else 0

        return {
            "cache_size": len(self._query_cache),
            "max_size": self._max_cache_size,
            "ttl_minutes": int(self._cache_ttl.total_seconds() / 60),
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "total_searches": total,
            "hit_rate_percent": round(hit_rate, 2)
        }

    # Delegate all other VectorStore methods without caching
    def add_message(self, *args, **kwargs):
        """Add message and clear cache (new data invalidates old results)"""
        result = self.vector_store.add_message(*args, **kwargs)
        # Don't clear entire cache on single message add (too aggressive)
        # Cache will naturally expire via TTL
        return result

    def delete_message(self, *args, **kwargs):
        """Delete message and clear cache"""
        result = self.vector_store.delete_message(*args, **kwargs)
        self.clear_cache()  # Deletion requires cache clear
        return result

    def delete_by_sender(self, *args, **kwargs):
        """Delete by sender and clear cache"""
        result = self.vector_store.delete_by_sender(*args, **kwargs)
        self.clear_cache()  # Deletion requires cache clear
        return result

    def clear_all(self, *args, **kwargs):
        """Clear all and clear cache"""
        result = self.vector_store.clear_all(*args, **kwargs)
        self.clear_cache()
        return result

    def get_stats(self) -> Dict:
        """Get combined stats (vector store + cache)"""
        stats = self.vector_store.get_stats()
        stats['cache_stats'] = self.get_cache_stats()
        return stats

    # Expose underlying attributes for compatibility
    @property
    def embedding_service(self):
        """Expose embedding service from underlying vector store"""
        return self.vector_store.embedding_service

    @property
    def collection(self):
        """Expose collection from underlying vector store"""
        return self.vector_store.collection

    @property
    def persist_directory(self):
        """Expose persist directory from underlying vector store"""
        return self.vector_store.persist_directory
