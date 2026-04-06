"""
v0.6.0: Vector Store Resolver — resolves agent config into provider(s) with mode logic.

The resolver is the single entry point for AgentMemorySystem. It returns a
ResolvedVectorStore that implements mode logic (override/complement/shadow)
and circuit breaker fallback to ChromaDB.

When agent.vector_store_instance_id IS NULL → returns None (caller uses ChromaDB default).
"""

import logging
from typing import List, Dict, Optional, Tuple

from services.circuit_breaker import CircuitBreakerState
from .base import VectorStoreProvider, VectorRecord, ProviderHealthResult, ProviderConnectionError
from .registry import VectorStoreRegistry

logger = logging.getLogger(__name__)


class ResolvedVectorStore(VectorStoreProvider):
    """
    Facade that dispatches to one or two providers based on mode.

    Modes:
    - override: external only, circuit breaker fallback to ChromaDB
    - complement: fetch both, merge by score-weighted interleaving
    - shadow: writes to both, reads from ChromaDB only (migration mode)
    """

    def __init__(
        self,
        mode: str,
        primary: VectorStoreProvider,
        chromadb_fallback: VectorStoreProvider,
        circuit_breaker=None,
    ):
        self.mode = mode
        self.primary = primary
        self.chromadb_fallback = chromadb_fallback
        self.circuit_breaker = circuit_breaker

    def _is_circuit_open(self) -> bool:
        if not self.circuit_breaker:
            return False
        if self.circuit_breaker.state == CircuitBreakerState.OPEN:
            if self.circuit_breaker.should_probe():
                self.circuit_breaker.try_recover()
                return False  # Allow probe attempt
            return True  # Still in cooldown
        return False

    def _record_success(self):
        if self.circuit_breaker:
            self.circuit_breaker.record_success()

    def _record_failure(self, error):
        if self.circuit_breaker:
            self.circuit_breaker.record_failure(str(error))

    # --- Write operations ---

    async def add_message(self, message_id, sender_key, text, embedding, metadata=None):
        if self.mode == "shadow":
            # Write to both, read from ChromaDB
            await self.chromadb_fallback.add_message(message_id, sender_key, text, embedding, metadata)
            try:
                await self.primary.add_message(message_id, sender_key, text, embedding, metadata)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Shadow write to external store failed: {e}")
        elif self.mode == "complement":
            # Write to both
            await self.chromadb_fallback.add_message(message_id, sender_key, text, embedding, metadata)
            try:
                await self.primary.add_message(message_id, sender_key, text, embedding, metadata)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Complement write to external store failed: {e}")
        else:  # override
            if self._is_circuit_open():
                await self.chromadb_fallback.add_message(message_id, sender_key, text, embedding, metadata)
                return
            try:
                await self.primary.add_message(message_id, sender_key, text, embedding, metadata)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Override write failed, falling back to ChromaDB: {e}")
                await self.chromadb_fallback.add_message(message_id, sender_key, text, embedding, metadata)

    async def add_batch(self, records):
        if self.mode == "shadow":
            await self.chromadb_fallback.add_batch(records)
            try:
                await self.primary.add_batch(records)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Shadow batch write failed: {e}")
        elif self.mode == "complement":
            await self.chromadb_fallback.add_batch(records)
            try:
                await self.primary.add_batch(records)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Complement batch write failed: {e}")
        else:  # override
            if self._is_circuit_open():
                await self.chromadb_fallback.add_batch(records)
                return
            try:
                await self.primary.add_batch(records)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Override batch write failed, falling back: {e}")
                await self.chromadb_fallback.add_batch(records)

    # --- Read operations ---

    async def search_similar(self, query_embedding, limit=5, sender_key=None):
        if self.mode == "shadow":
            # Read from ChromaDB only
            return await self.chromadb_fallback.search_similar(query_embedding, limit, sender_key)

        elif self.mode == "complement":
            # Fetch from both, merge
            chroma_results = await self.chromadb_fallback.search_similar(query_embedding, limit, sender_key)
            external_results = []
            try:
                external_results = await self.primary.search_similar(query_embedding, limit, sender_key)
                self._record_success()
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Complement read from external failed, using ChromaDB only: {e}")
            return self._merge_results(external_results, chroma_results, limit)

        else:  # override
            if self._is_circuit_open():
                return await self.chromadb_fallback.search_similar(query_embedding, limit, sender_key)
            try:
                results = await self.primary.search_similar(query_embedding, limit, sender_key)
                self._record_success()
                return results
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Override read failed, falling back to ChromaDB: {e}")
                return await self.chromadb_fallback.search_similar(query_embedding, limit, sender_key)

    async def search_similar_with_embeddings(self, query_embedding, limit=5, sender_key=None):
        if self.mode == "shadow":
            return await self.chromadb_fallback.search_similar_with_embeddings(query_embedding, limit, sender_key)

        elif self.mode == "complement":
            chroma_records, chroma_embs = await self.chromadb_fallback.search_similar_with_embeddings(query_embedding, limit, sender_key)
            try:
                ext_records, ext_embs = await self.primary.search_similar_with_embeddings(query_embedding, limit, sender_key)
                self._record_success()
                # Build embedding lookup keyed by message_id for correct alignment after merge
                emb_lookup = {}
                for rec, emb in zip(ext_records, ext_embs):
                    emb_lookup[rec.message_id] = emb
                for rec, emb in zip(chroma_records, chroma_embs):
                    if rec.message_id not in emb_lookup:
                        emb_lookup[rec.message_id] = emb
                merged = self._merge_results(ext_records, chroma_records, limit)
                aligned_embs = [emb_lookup.get(r.message_id, []) for r in merged]
                return merged, aligned_embs
            except Exception as e:
                self._record_failure(e)
                return chroma_records, chroma_embs

        else:  # override
            if self._is_circuit_open():
                return await self.chromadb_fallback.search_similar_with_embeddings(query_embedding, limit, sender_key)
            try:
                result = await self.primary.search_similar_with_embeddings(query_embedding, limit, sender_key)
                self._record_success()
                return result
            except Exception as e:
                self._record_failure(e)
                logger.warning(f"Override search_with_embeddings failed, falling back: {e}")
                return await self.chromadb_fallback.search_similar_with_embeddings(query_embedding, limit, sender_key)

    # --- Delete operations ---

    async def delete_message(self, message_id):
        if self.mode in ("shadow", "complement"):
            await self.chromadb_fallback.delete_message(message_id)
            try:
                await self.primary.delete_message(message_id)
            except Exception as e:
                logger.warning(f"External delete_message failed: {e}")
        else:  # override
            if self._is_circuit_open():
                await self.chromadb_fallback.delete_message(message_id)
                return
            try:
                await self.primary.delete_message(message_id)
            except Exception as e:
                logger.warning(f"Override delete failed: {e}")
                await self.chromadb_fallback.delete_message(message_id)

    async def delete_by_sender(self, sender_key):
        if self.mode in ("shadow", "complement"):
            await self.chromadb_fallback.delete_by_sender(sender_key)
            try:
                await self.primary.delete_by_sender(sender_key)
            except Exception as e:
                logger.warning(f"External delete_by_sender failed: {e}")
        else:
            if self._is_circuit_open():
                await self.chromadb_fallback.delete_by_sender(sender_key)
                return
            try:
                await self.primary.delete_by_sender(sender_key)
            except Exception as e:
                logger.warning(f"Override delete_by_sender failed: {e}")
                await self.chromadb_fallback.delete_by_sender(sender_key)

    async def clear_all(self):
        if self.mode in ("shadow", "complement"):
            await self.chromadb_fallback.clear_all()
            try:
                await self.primary.clear_all()
            except Exception as e:
                logger.warning(f"External clear_all failed: {e}")
        else:
            if self._is_circuit_open():
                await self.chromadb_fallback.clear_all()
                return
            try:
                await self.primary.clear_all()
            except Exception as e:
                logger.warning(f"Override clear_all failed: {e}")
                await self.chromadb_fallback.clear_all()

    async def update_access_time(self, message_ids):
        if self.mode in ("shadow", "complement"):
            await self.chromadb_fallback.update_access_time(message_ids)
            try:
                await self.primary.update_access_time(message_ids)
            except Exception:
                pass
        else:
            if self._is_circuit_open():
                await self.chromadb_fallback.update_access_time(message_ids)
                return
            try:
                await self.primary.update_access_time(message_ids)
            except Exception:
                await self.chromadb_fallback.update_access_time(message_ids)

    async def health_check(self):
        return await self.primary.health_check()

    async def get_stats(self):
        return await self.primary.get_stats()

    @staticmethod
    def _merge_results(
        external: List[VectorRecord],
        chroma: List[VectorRecord],
        limit: int,
    ) -> List[VectorRecord]:
        """Merge results from two providers, deduplicate by message_id, sort by distance."""
        seen = set()
        merged = []
        for record in external + chroma:
            if record.message_id not in seen:
                seen.add(record.message_id)
                merged.append(record)
        merged.sort(key=lambda r: r.distance)
        return merged[:limit]


class VectorStoreResolver:
    """
    Resolves an agent's vector store configuration into a ResolvedVectorStore.
    Returns None when agent uses ChromaDB default (vector_store_instance_id IS NULL).
    """

    def __init__(self, registry: Optional[VectorStoreRegistry] = None):
        self.registry = registry or VectorStoreRegistry()

    VALID_MODES = {"override", "complement", "shadow"}

    def resolve(
        self,
        agent_id: int,
        db,
        persist_directory: str,
        vector_store_instance_id: Optional[int] = None,
        vector_store_mode: str = "override",
        tenant_id: Optional[str] = None,
    ) -> Optional[ResolvedVectorStore]:
        """
        Resolve agent's vector store config into a provider facade.

        Args:
            agent_id: Agent ID
            db: SQLAlchemy session
            persist_directory: ChromaDB persist path (for fallback)
            vector_store_instance_id: FK to VectorStoreInstance (None = ChromaDB default)
            vector_store_mode: override|complement|shadow
            tenant_id: Tenant ID for multi-tenancy isolation

        Returns:
            ResolvedVectorStore or None (None = use ChromaDB via existing path)
        """
        if not vector_store_instance_id:
            return None  # ChromaDB default — zero regression

        # Validate mode
        if vector_store_mode not in self.VALID_MODES:
            logger.warning(f"Invalid vector_store_mode '{vector_store_mode}' for agent {agent_id}, using 'override'")
            vector_store_mode = "override"

        # v0.6.0 Item 5: Enforce per-agent vector store access control
        try:
            from models import SentinelAgentConfig
            agent_sentinel = db.query(SentinelAgentConfig).filter(
                SentinelAgentConfig.agent_id == agent_id
            ).first()

            if agent_sentinel:
                # Check if vector store access is explicitly disabled for this agent
                if agent_sentinel.vector_store_access_enabled is False:
                    logger.warning(
                        f"Agent {agent_id} has vector_store_access_enabled=False, "
                        f"denying access to instance {vector_store_instance_id}"
                    )
                    return None  # Falls back to ChromaDB

                # Check allowlist if configured
                allowed = agent_sentinel.vector_store_allowed_configs
                if allowed is not None and len(allowed) > 0:
                    if vector_store_instance_id not in allowed:
                        logger.warning(
                            f"Agent {agent_id} attempted to access instance "
                            f"{vector_store_instance_id} but it's not in allowed_configs={allowed}"
                        )
                        return None  # Falls back to ChromaDB
        except Exception as e:
            logger.debug(f"Access control check failed (fail-open): {e}")

        try:
            primary = self.registry.get_provider(vector_store_instance_id, db, tenant_id=tenant_id)
            chromadb_fallback = self.registry.get_chromadb_fallback(persist_directory)
            circuit_breaker = self.registry.get_circuit_breaker(vector_store_instance_id)

            return ResolvedVectorStore(
                mode=vector_store_mode or "override",
                primary=primary,
                chromadb_fallback=chromadb_fallback,
                circuit_breaker=circuit_breaker,
            )
        except Exception as e:
            logger.error(
                f"Failed to resolve vector store for agent {agent_id} "
                f"(instance={vector_store_instance_id}): {e}. Falling back to ChromaDB."
            )
            return None
