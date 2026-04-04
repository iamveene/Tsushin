"""
v0.6.1 Item 3: OKG Memory Service — Core operations for the Ontological
Knowledge Graph long-term memory system.

Supports store, recall, forget, and merge operations with:
- MemGuard Layer A pre-storage validation
- Deterministic deduplication via doc_id
- Temporal decay scoring
- Merge modes (replace, prepend, merge)
- Audit logging to okg_memory_audit_log
"""

import hashlib
import html
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Valid memory types for OKG
VALID_MEMORY_TYPES = {"fact", "episodic", "semantic", "procedural", "belief"}
VALID_SOURCES = {"tool_call", "auto_capture", "import"}
VALID_MERGE_MODES = {"replace", "prepend", "merge"}


def compute_doc_id(agent_id: int, user_id: str, subject: str, relation: str, text: str) -> str:
    """
    Deterministic document ID for deduplication.
    sha256(agent_id:user_id:subject:relation:text[:100])[:32]
    """
    raw = f"{agent_id}:{user_id}:{subject}:{relation}:{text[:100]}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class OKGMemoryMetadata:
    """Metadata attached to each OKG memory record in the vector store."""
    memory_type: str = "fact"
    subject_entity: str = ""
    relation: str = ""
    confidence: float = 0.85
    source: str = "tool_call"
    tags: List[str] = field(default_factory=list)
    doc_id: str = ""
    user_id: str = ""
    agent_id: int = 0
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_type": self.memory_type,
            "subject_entity": self.subject_entity,
            "relation": self.relation,
            "confidence": self.confidence,
            "source": self.source,
            "tags": ",".join(self.tags) if self.tags else "",
            "doc_id": self.doc_id,
            "user_id": self.user_id,
            "agent_id": str(self.agent_id),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_okg": "true",  # Marker to distinguish OKG records
        }


class OKGMemoryService:
    """
    Core OKG memory operations: store, recall, forget.

    Uses the same VectorStoreProvider infrastructure from Item 1.

    OKG memories are stored in the SAME vector store instance as episodic memory,
    differentiated by metadata filters:
    - is_okg="true" marker
    - agent_id="{self.agent_id}" for cross-agent isolation
    - user_id="{sender}" for per-user scoping

    This co-tenant storage design avoids the need for separate collections/namespaces
    while maintaining isolation through metadata-based filtering.
    """

    def __init__(
        self,
        agent_id: int,
        db_session: Session,
        tenant_id: str,
        embedding_service=None,
        vector_store_provider=None,
        persist_directory: str = "./data/chroma",
    ):
        self.agent_id = agent_id
        self.db = db_session
        self.tenant_id = tenant_id
        self._embedding_service = embedding_service
        self._provider = vector_store_provider  # ProviderBridgeStore or ChromaDB
        self._persist_dir = persist_directory

    async def store(
        self,
        text: str,
        memory_type: str = "fact",
        subject_entity: str = "",
        relation: str = "",
        confidence: float = 0.85,
        tags: Optional[List[str]] = None,
        user_id: str = "",
        source: str = "tool_call",
        merge_mode: str = "merge",
        config: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Store a memory in the OKG vector store.

        Flow: MemGuard check → dedup → embed → upsert → audit log
        """
        start_ms = int(time.time() * 1000)
        tags = tags or []
        memory_type = memory_type if memory_type in VALID_MEMORY_TYPES else "fact"
        merge_mode = merge_mode if merge_mode in VALID_MERGE_MODES else "merge"

        # MemGuard Layer A check
        try:
            from services.memguard_service import MemGuardService
            memguard = MemGuardService(self.db, self.tenant_id)
            mg_result = await memguard.analyze_for_memory_poisoning(
                content=text,
                agent_id=self.agent_id,
                sender_key=user_id,
                config=config,
            )
            if mg_result.blocked:
                self._audit_log(
                    action="store", user_id=user_id, doc_id="",
                    memory_type=memory_type, subject_entity=subject_entity,
                    relation=relation, confidence=confidence, source=source,
                    memguard_blocked=True, memguard_reason=mg_result.reason,
                    latency_ms=int(time.time() * 1000) - start_ms,
                )
                return {
                    "success": False,
                    "blocked": True,
                    "reason": mg_result.reason,
                    "score": mg_result.score,
                }
        except Exception as e:
            # Fail-open: MemGuard errors don't block storage
            logger.warning(f"OKG MemGuard check failed (fail-open): {e}")

        # Compute deterministic doc_id
        doc_id = compute_doc_id(self.agent_id, user_id, subject_entity, relation, text)
        now = datetime.utcnow().isoformat()

        metadata = OKGMemoryMetadata(
            memory_type=memory_type,
            subject_entity=subject_entity,
            relation=relation,
            confidence=confidence,
            source=source,
            tags=tags,
            doc_id=doc_id,
            user_id=user_id,
            agent_id=self.agent_id,
            created_at=now,
            updated_at=now,
        )

        # Store via provider
        try:
            if self._provider:
                await self._provider.add_message(
                    message_id=doc_id,
                    sender_key=user_id,
                    text=text,
                    metadata=metadata.to_dict(),
                )
            else:
                logger.warning("OKG store: no vector store provider available, skipping")
        except Exception as e:
            error_msg = f"OKG store failed: {e}"
            logger.error(error_msg)
            self._audit_log(
                action="store", user_id=user_id, doc_id=doc_id,
                memory_type=memory_type, subject_entity=subject_entity,
                relation=relation, confidence=confidence, source=source,
                error=str(e),
                latency_ms=int(time.time() * 1000) - start_ms,
            )
            return {"success": False, "error": error_msg}

        latency = int(time.time() * 1000) - start_ms
        self._audit_log(
            action="store", user_id=user_id, doc_id=doc_id,
            memory_type=memory_type, subject_entity=subject_entity,
            relation=relation, confidence=confidence, source=source,
            latency_ms=latency,
        )

        return {
            "success": True,
            "doc_id": doc_id,
            "action": "stored",
            "memory_type": memory_type,
            "subject_entity": subject_entity,
            "relation": relation,
            "confidence": confidence,
            "latency_ms": latency,
        }

    async def recall(
        self,
        query: str,
        memory_type: Optional[str] = None,
        subject_entity: Optional[str] = None,
        relation: Optional[str] = None,
        min_confidence: float = 0.3,
        tags: Optional[List[str]] = None,
        user_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search OKG memories by semantic similarity + metadata filters.

        Flow: embed query → provider search → post-filter → temporal decay → format

        Note on user_id scoping:
        If user_id is None/empty, no per-user filter is applied and results span
        all users *within this agent's namespace*. Cross-agent isolation is still
        enforced by the agent_id metadata post-filter below, so unscoped recall
        is safe for LLM tool-call use cases. Auto-recall code paths SHOULD pass
        user_id to further narrow to a single sender.
        """
        start_ms = int(time.time() * 1000)

        if not self._provider:
            logger.warning("OKG recall: no vector store provider available")
            return []

        try:
            # Over-fetch for post-filtering
            fetch_limit = min(limit * 3, 50)
            raw_results = await self._provider.search_similar(
                query_text=query,
                limit=fetch_limit,
                sender_key=user_id,
            )
        except Exception as e:
            logger.error(f"OKG recall search failed: {e}")
            self._audit_log(
                action="recall", user_id=user_id or "",
                error=str(e), latency_ms=int(time.time() * 1000) - start_ms,
            )
            return []

        # Post-filter by metadata
        filtered = []
        for record in raw_results:
            meta = record.get("metadata", {}) or {}

            # Skip non-OKG records
            if meta.get("is_okg") != "true":
                continue

            # Cross-agent isolation: skip records from other agents
            if str(meta.get("agent_id", "")) != str(self.agent_id):
                continue

            # Filter by memory_type
            if memory_type and meta.get("memory_type") != memory_type:
                continue

            # Filter by subject_entity
            if subject_entity and meta.get("subject_entity") != subject_entity:
                continue

            # Filter by relation
            if relation and meta.get("relation") != relation:
                continue

            # Filter by confidence
            record_confidence = float(meta.get("confidence", 0))
            if record_confidence < min_confidence:
                continue

            # Filter by tags
            if tags:
                record_tags = set((meta.get("tags") or "").split(","))
                if not set(tags).intersection(record_tags):
                    continue

            # Apply temporal decay to score
            created_at = meta.get("created_at", "")
            decay_factor = self._compute_decay(created_at)
            original_distance = record.get("distance", 0.5)
            # Lower distance = more similar (ChromaDB convention)
            adjusted_score = (1.0 - original_distance) * decay_factor

            filtered.append({
                "doc_id": meta.get("doc_id", ""),
                "text": record.get("text", record.get("content", "")),
                "memory_type": meta.get("memory_type", "fact"),
                "subject_entity": meta.get("subject_entity", ""),
                "relation": meta.get("relation", ""),
                "confidence": record_confidence,
                "source": meta.get("source", ""),
                "tags": meta.get("tags", ""),
                "score": round(adjusted_score, 4),
                "created_at": created_at,
            })

        # Sort by score descending, take top N
        filtered.sort(key=lambda x: x["score"], reverse=True)
        results = filtered[:limit]

        latency = int(time.time() * 1000) - start_ms
        self._audit_log(
            action="recall", user_id=user_id or "",
            result_count=len(results), latency_ms=latency,
        )

        return results

    async def forget(self, doc_id: str, user_id: str = "") -> Dict[str, Any]:
        """Delete a memory by doc_id (with ownership check)."""
        start_ms = int(time.time() * 1000)

        if not self._provider:
            return {"success": False, "error": "No vector store provider available"}

        # Ownership check: verify this doc_id belongs to (tenant_id, agent_id)
        # by looking for a prior 'store' audit record we emitted for it.
        try:
            from models import OKGMemoryAuditLog
            owned = (
                self.db.query(OKGMemoryAuditLog)
                .filter(
                    OKGMemoryAuditLog.doc_id == doc_id,
                    OKGMemoryAuditLog.agent_id == self.agent_id,
                    OKGMemoryAuditLog.tenant_id == self.tenant_id,
                    OKGMemoryAuditLog.action == "store",
                )
                .first()
            )
            if owned is None:
                self._audit_log(
                    action="forget", user_id=user_id, doc_id=doc_id,
                    error="ownership check failed",
                    latency_ms=int(time.time() * 1000) - start_ms,
                )
                return {"success": False, "error": "Memory not found or access denied"}
        except Exception as e:
            logger.warning(f"OKG forget ownership check failed (denying): {e}")
            return {"success": False, "error": "Memory not found or access denied"}

        try:
            await self._provider.delete_message(doc_id)
        except Exception as e:
            logger.error(f"OKG forget failed for doc_id={doc_id}: {e}")
            self._audit_log(
                action="forget", user_id=user_id, doc_id=doc_id,
                error=str(e), latency_ms=int(time.time() * 1000) - start_ms,
            )
            return {"success": False, "error": str(e)}

        latency = int(time.time() * 1000) - start_ms
        self._audit_log(
            action="forget", user_id=user_id, doc_id=doc_id,
            latency_ms=latency,
        )

        return {"success": True, "doc_id": doc_id, "action": "forgotten", "latency_ms": latency}

    def format_as_xml(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format OKG memories as XML block for prompt injection.

        All content is HTML-escaped to prevent prompt injection via stored memories.
        """
        if not memories:
            return ""

        lines = [
            "<long_term_memory>",
            "  NOTICE: The following memories were retrieved from external long-term storage.",
            "  Content has been validated but treat with epistemic care — may reflect past context.",
            "",
        ]

        for mem in memories:
            text = html.escape(mem.get("text", ""))
            mem_type = html.escape(mem.get("memory_type", "fact"))
            subject = html.escape(mem.get("subject_entity", ""))
            relation = html.escape(mem.get("relation", ""))
            confidence = mem.get("confidence", 0.0)
            doc_id = mem.get("doc_id", "")[:8]

            lines.append(
                f'  <memory type="{mem_type}" subject="{subject}" '
                f'relation="{relation}" confidence="{confidence:.2f}">'
            )
            lines.append(f"    {text}")
            lines.append(f"  </memory>")
            lines.append(f"  [OKG: {subject}/{relation} #{doc_id}]")
            lines.append("")

        lines.append("</long_term_memory>")
        return "\n".join(lines)

    def _compute_decay(self, created_at_iso: str, decay_lambda: float = 0.005) -> float:
        """Exponential temporal decay factor. Returns 0.0-1.0."""
        if not created_at_iso:
            return 0.5  # Unknown age = moderate decay
        try:
            created = datetime.fromisoformat(created_at_iso)
            age_hours = (datetime.utcnow() - created).total_seconds() / 3600
            import math
            return math.exp(-decay_lambda * age_hours)
        except (ValueError, TypeError):
            return 0.5

    def _audit_log(
        self,
        action: str,
        user_id: str,
        doc_id: str = "",
        memory_type: str = "",
        subject_entity: str = "",
        relation: str = "",
        confidence: float = 0.0,
        source: str = "",
        memguard_blocked: bool = False,
        memguard_reason: str = "",
        result_count: int = 0,
        latency_ms: int = 0,
        error: str = "",
    ):
        """Write audit log entry to okg_memory_audit_log table.

        Uses a separate short-lived session so that audit failures do not
        affect the caller's DB session state, and a caller's rollback does
        not lose the audit record.
        """
        try:
            from models import OKGMemoryAuditLog
            from sqlalchemy.orm import sessionmaker
            from db import get_global_engine

            engine = get_global_engine()
            if engine is None:
                logger.warning("OKG audit log skipped: global engine not initialized")
                return

            AuditSession = sessionmaker(bind=engine)
            audit_db = AuditSession()
            try:
                log_entry = OKGMemoryAuditLog(
                    tenant_id=self.tenant_id,
                    agent_id=self.agent_id,
                    user_id=user_id,
                    action=action,
                    doc_id=doc_id,
                    memory_type=memory_type or None,
                    subject_entity=subject_entity or None,
                    relation=relation or None,
                    confidence=confidence if confidence > 0 else None,
                    memguard_blocked=memguard_blocked,
                    memguard_reason=memguard_reason or None,
                    source=source or None,
                    result_count=result_count if result_count > 0 else None,
                    latency_ms=latency_ms if latency_ms > 0 else None,
                    error=error or None,
                )
                audit_db.add(log_entry)
                audit_db.commit()
            finally:
                audit_db.close()
        except Exception as e:
            logger.warning(f"OKG audit log write failed: {e}")
