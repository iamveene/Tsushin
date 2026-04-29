"""
v0.6.0: Provider Bridge Store — impedance adapter between SemanticMemoryService
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

    v0.6.0 Item 4: Optional security context for MemGuard + rate limiting.
    When security_context is provided:
      - add_message runs write rate limit check + pre-storage MemGuard scan (Layer A)
      - search_similar runs read rate limit check + post-retrieval validation (Layer C)
      - add_batch runs batch size check + batch poisoning detection (Layer B)
    Security hooks fail-open on unexpected errors but propagate explicit RuntimeError
    blocks (rate limit exceeded, content blocked by MemGuard).
    """

    def __init__(
        self,
        provider: VectorStoreProvider,
        embedding_service,
        security_context: Optional[Dict] = None,
    ):
        self._provider = provider
        self._embedding_service = embedding_service
        # v0.6.0: Optional security context for MemGuard hooks
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
        """Convert text to embedding, then delegate to provider.

        When security_context is set, runs:
        1. Rate limit check (write)
        2. Pre-storage MemGuard scan (Layer A)
        3. Delegates to provider
        """
        # v0.6.0 Item 4: Security hooks (when security_context is provided)
        if self._security:
            try:
                from services.vector_store_rate_limiter import VectorStoreRateLimiter
                from services.memguard_service import MemGuardService

                db = self._security.get("db")
                tenant_id = self._security.get("tenant_id", "")
                agent_id = self._security.get("agent_id", 0)
                instance_id = self._security.get("instance_id", 0)

                if db and tenant_id and instance_id:
                    memguard = MemGuardService(db, tenant_id)
                    security_config = memguard._get_security_config(instance_id)

                    # Rate limit check
                    limiter = VectorStoreRateLimiter()
                    if not limiter.check_write(
                        instance_id, tenant_id,
                        max_per_minute=security_config.get("max_writes_per_minute_per_tenant", 100)
                    ):
                        logger.warning(f"Vector store write rate limit exceeded for tenant {tenant_id}")
                        raise RuntimeError("Vector store write rate limit exceeded")

                    # Pre-storage MemGuard Layer A scan
                    try:
                        from services.sentinel_service import SentinelService
                        sentinel = SentinelService(db, tenant_id=tenant_id)
                        effective_config = sentinel.get_effective_config(agent_id=agent_id)
                        mg_result = await memguard.analyze_for_memory_poisoning(
                            content=text,
                            agent_id=agent_id,
                            sender_key=sender_key,
                            config=effective_config,
                        )
                        if mg_result.blocked:
                            logger.warning(
                                f"Bridge pre-storage MemGuard blocked: {mg_result.reason}"
                            )
                            raise RuntimeError(
                                f"Content blocked by MemGuard pre-storage scan: {mg_result.reason}"
                            )
                    except RuntimeError:
                        raise  # Re-raise MemGuard blocks
                    except Exception as e:
                        logger.debug(f"Pre-storage MemGuard check skipped (fail-open): {e}")
            except RuntimeError:
                raise  # Propagate blocks and rate limits
            except Exception as e:
                logger.debug(f"Pre-storage security hooks skipped: {e}")

        embedding = await self._embedding_service.embed_text_async(text)
        await self._provider.add_message(message_id, sender_key, text, embedding, metadata)

    async def add_batch(self, records: List[Dict]) -> None:
        """Add multiple records with batch size + poisoning checks.

        Args:
            records: List of dicts with keys: message_id, sender_key, text, metadata
        """
        if not records:
            return

        # v0.6.0 Item 4: Batch security checks
        if self._security:
            try:
                from services.vector_store_rate_limiter import VectorStoreRateLimiter
                from services.memguard_service import MemGuardService

                db = self._security.get("db")
                tenant_id = self._security.get("tenant_id", "")
                agent_id = self._security.get("agent_id", 0)
                instance_id = self._security.get("instance_id", 0)

                if db and tenant_id and instance_id:
                    memguard = MemGuardService(db, tenant_id)
                    security_config = memguard._get_security_config(instance_id)

                    # Batch size check
                    limiter = VectorStoreRateLimiter()
                    if not limiter.check_batch_size(
                        len(records),
                        max_batch=security_config.get("max_batch_write_size", 500)
                    ):
                        raise RuntimeError(
                            f"Batch size {len(records)} exceeds max_batch_write_size"
                        )

                    # Batch poisoning detection
                    mg_result = await memguard.detect_batch_poisoning(
                        documents=records,
                        instance_id=instance_id,
                        agent_id=agent_id,
                        security_config=security_config,
                    )
                    if mg_result.blocked:
                        raise RuntimeError(f"Batch blocked by MemGuard: {mg_result.reason}")
            except RuntimeError:
                raise
            except Exception as e:
                logger.debug(f"Batch security checks skipped: {e}")

        # Delegate to individual add_message calls
        for record in records:
            await self.add_message(
                message_id=record.get("message_id", ""),
                sender_key=record.get("sender_key", ""),
                text=record.get("text", ""),
                metadata=record.get("metadata"),
            )

    async def search_similar(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[Dict]:
        """Convert text to embedding, search, return List[Dict] format."""
        # v0.6.0 Item 4: Rate limit check (read)
        if self._security:
            try:
                from services.vector_store_rate_limiter import VectorStoreRateLimiter
                from services.memguard_service import MemGuardService

                db = self._security.get("db")
                tenant_id = self._security.get("tenant_id", "")
                agent_id = self._security.get("agent_id", 0)
                instance_id = self._security.get("instance_id", 0)

                if db and tenant_id and instance_id:
                    memguard = MemGuardService(db, tenant_id)
                    security_config = memguard._get_security_config(instance_id)

                    limiter = VectorStoreRateLimiter()
                    if not limiter.check_read(
                        instance_id, agent_id,
                        max_per_minute=security_config.get("max_reads_per_minute_per_agent", 30)
                    ):
                        logger.warning(f"Vector store read rate limit exceeded for agent {agent_id}")
                        return []  # Graceful degradation
            except Exception as e:
                logger.debug(f"Read rate limit check skipped: {e}")

        embedding = await self._embedding_service.embed_text_async(query_text)
        records = await self._provider.search_similar(embedding, limit, sender_key)
        results = self._records_to_dicts(records)

        # v0.6.0 Item 4: Post-retrieval MemGuard validation
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

    async def search_similar_by_embedding(
        self,
        query_embedding: List[float],
        limit: int = 5,
        sender_key: Optional[str] = None,
    ) -> List[Dict]:
        """Search with a pre-computed embedding (no re-embed).

        Mirrors ``search_similar`` but skips the bridge-level embedding
        step. Used by the case-memory query path
        (``search_similar_cases``) so a Gemini ``RETRIEVAL_QUERY``
        embedding isn't silently re-computed under the bridge's own
        ``embedding_service`` (which may default to a different
        provider/model and produce a different vector).
        """
        records = await self._provider.search_similar(
            query_embedding, limit, sender_key
        )
        return self._records_to_dicts(records)

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
        """Convert VectorRecord list to List[Dict] matching CachedVectorStore format.

        V060-MEM-001 FIX: Also preserve the full metadata dict under a nested
        ``metadata`` key so callers that expect the OKG record shape
        (``record.get("metadata", {}).get("is_okg")``) can read it. Previously
        only the flat ``**r.metadata`` spread was exposed, which meant every
        OKG recall post-filter saw ``meta == {}`` and skipped every record —
        making OKG non-functional with external vector stores.
        """
        return [
            {
                "message_id": r.message_id,
                "text": r.text,
                "distance": r.distance,
                "sender_key": r.sender_key,
                "metadata": dict(r.metadata or {}),  # V060-MEM-001: nested for OKG reader
                **(r.metadata or {}),                  # legacy flat spread for existing callers
            }
            for r in records
        ]
