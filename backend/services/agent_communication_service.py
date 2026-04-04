"""
Agent-to-Agent Communication Service (v0.6.0 Item 15)

Orchestrates inter-agent communication with permission checks, rate limiting,
loop detection, Sentinel security analysis, and full audit logging.
"""

import asyncio
import time
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session

from services.watcher_activity_service import emit_agent_communication_async
from models import (
    Agent,
    AgentSkill,
    AgentCommunicationPermission,
    AgentCommunicationSession,
    AgentCommunicationMessage,
    Contact,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------

@dataclass
class AgentCommunicationResult:
    success: bool
    session_id: Optional[int] = None
    response_text: Optional[str] = None
    from_agent_id: Optional[int] = None
    from_agent_name: Optional[str] = None
    execution_time_ms: Optional[int] = None
    token_usage: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    blocked_by_sentinel: bool = False


@dataclass
class AgentDiscoveryInfo:
    agent_id: int
    agent_name: str
    description: Optional[str]
    capabilities: List[str]
    is_available: bool


@dataclass
class AgentCapabilities:
    agent_id: int
    agent_name: str
    description: Optional[str]
    skills: List[str]
    model_provider: str
    model_name: str


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

# Hard system ceiling for delegation depth regardless of permission settings
SYSTEM_MAX_DEPTH = 5

VALID_SESSION_STATUSES = {"pending", "in_progress", "completed", "failed", "timeout", "blocked"}


class AgentCommunicationService:
    """
    Orchestrates inter-agent communication.

    Follows the established service pattern:
        svc = AgentCommunicationService(db, tenant_id, token_tracker)
    """

    DEFAULT_MAX_DEPTH = 3
    DEFAULT_TIMEOUT_SECONDS = 60
    DEFAULT_RATE_LIMIT_RPM = 30
    GLOBAL_RATE_LIMIT_RPM = 100
    MAX_MESSAGE_LENGTH = 4000
    MAX_CONTEXT_LENGTH = 2000

    def __init__(
        self,
        db: Session,
        tenant_id: str,
        token_tracker=None,
        config: Optional[Dict] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.token_tracker = token_tracker
        self.config = config or {}

    # ------------------------------------------------------------------
    # Core: send_message
    # ------------------------------------------------------------------

    async def send_message(
        self,
        source_agent_id: int,
        target_agent_id: int,
        message: str,
        context: Optional[str] = None,
        depth: int = 0,
        parent_session_id: Optional[int] = None,
        timeout: Optional[int] = None,
        session_type: str = "sync",
        original_sender_key: Optional[str] = None,
        original_message_preview: Optional[str] = None,
    ) -> AgentCommunicationResult:
        """Send a message from one agent to another and return the response."""
        start_time = time.time()

        # 1. Validate both agents exist, active, same tenant
        source_agent = self._get_agent(source_agent_id)
        target_agent = self._get_agent(target_agent_id)

        if not source_agent:
            return AgentCommunicationResult(success=False, error=f"Source agent {source_agent_id} not found")
        if not target_agent:
            return AgentCommunicationResult(success=False, error=f"Target agent {target_agent_id} not found")
        if not source_agent.is_active:
            return AgentCommunicationResult(success=False, error="Source agent is inactive")
        if not target_agent.is_active:
            return AgentCommunicationResult(success=False, error="Target agent is inactive")
        if source_agent.tenant_id != self.tenant_id or target_agent.tenant_id != self.tenant_id:
            return AgentCommunicationResult(success=False, error="Cross-tenant communication not allowed")

        # 1b. Self-communication guard
        if source_agent_id == target_agent_id:
            return AgentCommunicationResult(success=False, error="An agent cannot communicate with itself")

        # 2. Check permission
        permission = self._check_permission(source_agent_id, target_agent_id)
        if not permission:
            self._audit_log("agent_comm.blocked", source_agent_id, target_agent_id, {"reason": "no_permission"})
            return AgentCommunicationResult(success=False, error="No communication permission between these agents")

        # 3. Check depth (enforce system ceiling regardless of permission)
        max_depth = min(permission.max_depth or self.DEFAULT_MAX_DEPTH, SYSTEM_MAX_DEPTH)
        if depth >= max_depth:
            self._audit_log("agent_comm.blocked", source_agent_id, target_agent_id, {"reason": "depth_exceeded", "depth": depth, "max_depth": max_depth})
            return AgentCommunicationResult(success=False, error=f"Maximum delegation depth ({max_depth}) exceeded")

        # 4. Rate limit check
        rate_limit_error = self._check_rate_limit(source_agent_id, target_agent_id, permission.rate_limit_rpm)
        if rate_limit_error:
            return AgentCommunicationResult(success=False, error=rate_limit_error)

        # 5. Loop detection
        if parent_session_id and self._detect_loop(parent_session_id, target_agent_id):
            self._audit_log("agent_comm.blocked", source_agent_id, target_agent_id, {"reason": "loop_detected"})
            return AgentCommunicationResult(success=False, error="Circular delegation detected — would create an infinite loop")

        # 6. Enforce message size limits
        message = message[:self.MAX_MESSAGE_LENGTH]
        if context:
            context = context[:self.MAX_CONTEXT_LENGTH]

        # 7. Create session
        effective_timeout = timeout or self.DEFAULT_TIMEOUT_SECONDS
        session = AgentCommunicationSession(
            tenant_id=self.tenant_id,
            initiator_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            original_sender_key=original_sender_key,
            original_message_preview=(original_message_preview or "")[:200],
            session_type=session_type,
            status="in_progress",
            depth=depth,
            max_depth=max_depth,
            timeout_seconds=effective_timeout,
            parent_session_id=parent_session_id,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        # Emit A2A communication start event (non-blocking)
        emit_agent_communication_async(
            tenant_id=self.tenant_id,
            initiator_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            session_id=session.id,
            status="start",
            session_type=session_type,
            depth=depth,
        )

        # 8. Record request message
        request_msg = AgentCommunicationMessage(
            session_id=session.id,
            from_agent_id=source_agent_id,
            to_agent_id=target_agent_id,
            direction="request",
            message_content=message,
            message_preview=message[:500],
            context_transferred={"context": context} if context else None,
        )
        self.db.add(request_msg)
        self.db.commit()

        # 9. Sentinel analysis (fail-closed for inter-agent comms)
        try:
            sentinel_result_data = await self._sentinel_analyze(message, source_agent_id, target_agent_id, depth)
        except Exception as e:
            logger.error(f"Sentinel analysis error (blocking as precaution): {e}", exc_info=True)
            sentinel_result_data = {"blocked": True, "reason": "Sentinel analysis error — blocking as precaution"}

        request_msg.sentinel_analyzed = True
        request_msg.sentinel_result = sentinel_result_data
        self.db.commit()

        if sentinel_result_data and sentinel_result_data.get("blocked"):
            session.status = "blocked"
            session.error_text = sentinel_result_data.get("reason", "Blocked by Sentinel")
            session.completed_at = datetime.utcnow()
            self.db.commit()
            self._audit_log("agent_comm.blocked", source_agent_id, target_agent_id, {
                "reason": "sentinel_blocked",
                "session_id": session.id,
                "sentinel_reason": sentinel_result_data.get("reason"),
            })
            # Emit A2A communication end event (non-blocking)
            emit_agent_communication_async(
                tenant_id=self.tenant_id,
                initiator_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                session_id=session.id,
                status="end",
                session_type=session_type,
                depth=depth,
            )
            return AgentCommunicationResult(
                success=False,
                session_id=session.id,
                error="Message blocked by Sentinel security analysis",
                blocked_by_sentinel=True,
            )

        # 10. Invoke target agent
        try:
            ai_result = await asyncio.wait_for(
                self._invoke_target_agent(target_agent, message, context, source_agent, depth),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            session.status = "timeout"
            session.error_text = f"Timeout after {effective_timeout}s"
            session.completed_at = datetime.utcnow()
            self.db.commit()
            self._audit_log("agent_comm.send", source_agent_id, target_agent_id, {
                "session_id": session.id, "status": "timeout",
            })
            # Emit A2A communication end event (non-blocking)
            emit_agent_communication_async(
                tenant_id=self.tenant_id,
                initiator_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                session_id=session.id,
                status="end",
                session_type=session_type,
                depth=depth,
            )
            return AgentCommunicationResult(
                success=False,
                session_id=session.id,
                error=f"Target agent did not respond within {effective_timeout} seconds",
            )
        except Exception as exc:
            session.status = "failed"
            session.error_text = str(exc)[:500]
            session.completed_at = datetime.utcnow()
            self.db.commit()
            logger.error(f"Agent comm error: {exc}", exc_info=True)
            # Emit A2A communication end event (non-blocking)
            emit_agent_communication_async(
                tenant_id=self.tenant_id,
                initiator_agent_id=source_agent_id,
                target_agent_id=target_agent_id,
                session_id=session.id,
                status="end",
                session_type=session_type,
                depth=depth,
            )
            return AgentCommunicationResult(
                success=False,
                session_id=session.id,
                error=f"Target agent processing error: {str(exc)[:200]}",
            )

        # 11. Record response message
        response_text = ai_result.get("answer") or ""
        elapsed_ms = int((time.time() - start_time) * 1000)

        response_msg = AgentCommunicationMessage(
            session_id=session.id,
            from_agent_id=target_agent_id,
            to_agent_id=source_agent_id,
            direction="response",
            message_content=response_text,
            message_preview=response_text[:500] if response_text else "",
            model_used=f"{target_agent.model_provider}/{target_agent.model_name}",
            token_usage_json=ai_result.get("tokens"),
            execution_time_ms=elapsed_ms,
        )
        self.db.add(response_msg)
        self.db.flush()  # Ensure response_msg PK is assigned and relationship is coherent

        # 12. Finalize session
        session.status = "completed"
        session.completed_at = datetime.utcnow()
        session.total_messages = len(session.messages)
        self.db.commit()

        # Emit A2A communication end event (non-blocking)
        emit_agent_communication_async(
            tenant_id=self.tenant_id,
            initiator_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            session_id=session.id,
            status="end",
            session_type=session_type,
            depth=depth,
        )

        # 13. Get target agent display name
        target_contact = self.db.query(Contact).filter(Contact.id == target_agent.contact_id).first()
        target_display_name = target_contact.friendly_name if target_contact else f"Agent {target_agent_id}"

        # 14. Audit log
        self._audit_log("agent_comm.send", source_agent_id, target_agent_id, {
            "session_id": session.id,
            "status": "completed",
            "depth": depth,
            "execution_time_ms": elapsed_ms,
        })

        return AgentCommunicationResult(
            success=True,
            session_id=session.id,
            response_text=response_text,
            from_agent_id=target_agent_id,
            from_agent_name=target_display_name,
            execution_time_ms=elapsed_ms,
            token_usage=ai_result.get("tokens"),
        )

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def discover_agents(self, requesting_agent_id: int) -> List[AgentDiscoveryInfo]:
        """List agents that the requesting agent is permitted to communicate with."""
        # Validate requester belongs to this tenant
        requester = self._get_agent(requesting_agent_id)
        if not requester:
            return []

        permissions = (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.tenant_id == self.tenant_id,
                AgentCommunicationPermission.source_agent_id == requesting_agent_id,
                AgentCommunicationPermission.is_enabled == True,
            )
            .all()
        )

        results: List[AgentDiscoveryInfo] = []
        for perm in permissions:
            agent = self.db.query(Agent).filter(
                Agent.id == perm.target_agent_id,
                Agent.is_active == True,
            ).first()
            if not agent:
                continue
            contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

            # Get enabled skills (expose skill types, not system prompts)
            skills = (
                self.db.query(AgentSkill)
                .filter(AgentSkill.agent_id == agent.id, AgentSkill.is_enabled == True)
                .all()
            )
            capabilities = [s.skill_type for s in skills]

            results.append(AgentDiscoveryInfo(
                agent_id=agent.id,
                agent_name=agent_name,
                description=None,  # Don't leak system prompts
                capabilities=capabilities,
                is_available=agent.is_active,
            ))

        return results

    def get_agent_capabilities(self, agent_id: int) -> Optional[AgentCapabilities]:
        """Get detailed capabilities of a specific agent."""
        agent = self._get_agent(agent_id)
        if not agent:
            return None

        contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
        agent_name = contact.friendly_name if contact else f"Agent {agent_id}"

        skills = (
            self.db.query(AgentSkill)
            .filter(AgentSkill.agent_id == agent_id, AgentSkill.is_enabled == True)
            .all()
        )

        return AgentCapabilities(
            agent_id=agent.id,
            agent_name=agent_name,
            description=None,  # Don't leak system prompts
            skills=[s.skill_type for s in skills],
            model_provider=agent.model_provider,
            model_name=agent.model_name,
        )

    # ------------------------------------------------------------------
    # Permission CRUD (for API routes)
    # ------------------------------------------------------------------

    def list_permissions(self) -> List[AgentCommunicationPermission]:
        return (
            self.db.query(AgentCommunicationPermission)
            .filter(AgentCommunicationPermission.tenant_id == self.tenant_id)
            .order_by(AgentCommunicationPermission.created_at.desc())
            .all()
        )

    def create_permission(
        self,
        source_agent_id: int,
        target_agent_id: int,
        max_depth: int = 3,
        rate_limit_rpm: int = 30,
    ) -> AgentCommunicationPermission:
        perm = AgentCommunicationPermission(
            tenant_id=self.tenant_id,
            source_agent_id=source_agent_id,
            target_agent_id=target_agent_id,
            is_enabled=True,
            max_depth=max_depth,
            rate_limit_rpm=rate_limit_rpm,
        )
        self.db.add(perm)
        self.db.commit()
        self.db.refresh(perm)
        self._audit_log("agent_comm.permission.create", source_agent_id, target_agent_id, {
            "permission_id": perm.id,
        })
        return perm

    def update_permission(self, perm_id: int, **kwargs) -> Optional[AgentCommunicationPermission]:
        perm = (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.id == perm_id,
                AgentCommunicationPermission.tenant_id == self.tenant_id,
            )
            .first()
        )
        if not perm:
            return None
        for key in ("is_enabled", "max_depth", "rate_limit_rpm"):
            if key in kwargs:
                setattr(perm, key, kwargs[key])
        perm.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(perm)
        self._audit_log("agent_comm.permission.update", perm.source_agent_id, perm.target_agent_id, {
            "permission_id": perm.id, "changes": kwargs,
        })
        return perm

    def delete_permission(self, perm_id: int) -> bool:
        perm = (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.id == perm_id,
                AgentCommunicationPermission.tenant_id == self.tenant_id,
            )
            .first()
        )
        if not perm:
            return False
        self._audit_log("agent_comm.permission.delete", perm.source_agent_id, perm.target_agent_id, {
            "permission_id": perm.id,
        })
        self.db.delete(perm)
        self.db.commit()
        return True

    # ------------------------------------------------------------------
    # Session queries (for API routes)
    # ------------------------------------------------------------------

    def list_sessions(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
    ) -> List[AgentCommunicationSession]:
        q = (
            self.db.query(AgentCommunicationSession)
            .filter(AgentCommunicationSession.tenant_id == self.tenant_id)
        )
        if status:
            q = q.filter(AgentCommunicationSession.status == status)
        if agent_id:
            q = q.filter(
                (AgentCommunicationSession.initiator_agent_id == agent_id)
                | (AgentCommunicationSession.target_agent_id == agent_id)
            )
        return q.order_by(AgentCommunicationSession.started_at.desc()).offset(offset).limit(limit).all()

    def get_session_detail(self, session_id: int) -> Optional[AgentCommunicationSession]:
        return (
            self.db.query(AgentCommunicationSession)
            .filter(
                AgentCommunicationSession.id == session_id,
                AgentCommunicationSession.tenant_id == self.tenant_id,
            )
            .first()
        )

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate communication statistics for the tenant."""
        from sqlalchemy import func

        total = (
            self.db.query(func.count(AgentCommunicationSession.id))
            .filter(AgentCommunicationSession.tenant_id == self.tenant_id)
            .scalar()
        ) or 0

        completed = (
            self.db.query(func.count(AgentCommunicationSession.id))
            .filter(
                AgentCommunicationSession.tenant_id == self.tenant_id,
                AgentCommunicationSession.status == "completed",
            )
            .scalar()
        ) or 0

        blocked = (
            self.db.query(func.count(AgentCommunicationSession.id))
            .filter(
                AgentCommunicationSession.tenant_id == self.tenant_id,
                AgentCommunicationSession.status == "blocked",
            )
            .scalar()
        ) or 0

        avg_time = (
            self.db.query(func.avg(AgentCommunicationMessage.execution_time_ms))
            .join(AgentCommunicationSession)
            .filter(
                AgentCommunicationSession.tenant_id == self.tenant_id,
                AgentCommunicationMessage.direction == "response",
            )
            .scalar()
        )

        return {
            "total_sessions": total,
            "completed_sessions": completed,
            "blocked_sessions": blocked,
            "success_rate": round((completed / total * 100) if total > 0 else 0, 1),
            "avg_response_time_ms": int(avg_time) if avg_time else 0,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_agent(self, agent_id: int) -> Optional[Agent]:
        return self.db.query(Agent).filter(
            Agent.id == agent_id,
            Agent.tenant_id == self.tenant_id,
        ).first()

    def _check_permission(self, source_id: int, target_id: int) -> Optional[AgentCommunicationPermission]:
        return (
            self.db.query(AgentCommunicationPermission)
            .filter(
                AgentCommunicationPermission.tenant_id == self.tenant_id,
                AgentCommunicationPermission.source_agent_id == source_id,
                AgentCommunicationPermission.target_agent_id == target_id,
                AgentCommunicationPermission.is_enabled == True,
            )
            .first()
        )

    def _check_rate_limit(self, source_id: int, target_id: int, pair_rpm: int) -> Optional[str]:
        """Check rate limits. Returns error string if exceeded, None if OK.
        Fails closed on errors (blocks rather than allowing)."""
        try:
            from middleware.rate_limiter import api_rate_limiter
        except ImportError:
            logger.error("Rate limiter module unavailable — agent comm rate limiting disabled")
            return None  # ImportError only: module not available, allow (rate limiter is optional infra)

        try:
            pair_key = f"agent_comm:{source_id}:{target_id}"
            if not api_rate_limiter.allow(pair_key, pair_rpm or self.DEFAULT_RATE_LIMIT_RPM):
                return f"Rate limit exceeded for agent pair ({source_id} -> {target_id})"
            global_key = f"agent_comm_global:{source_id}"
            if not api_rate_limiter.allow(global_key, self.GLOBAL_RATE_LIMIT_RPM):
                return f"Global inter-agent rate limit exceeded for agent {source_id}"
        except Exception as e:
            logger.error(f"Rate limit check error (blocking as precaution): {e}", exc_info=True)
            return "Rate limit check failed; blocking as precaution"
        return None

    def _detect_loop(self, session_id: int, target_agent_id: int) -> bool:
        """Walk the parent_session chain; return True if target already appears."""
        visited_agents = set()
        current_id = session_id
        for _ in range(10):  # safety cap
            sess = self.db.query(AgentCommunicationSession).filter(
                AgentCommunicationSession.id == current_id,
                AgentCommunicationSession.tenant_id == self.tenant_id,
            ).first()
            if not sess:
                break
            visited_agents.add(sess.initiator_agent_id)
            visited_agents.add(sess.target_agent_id)
            if not sess.parent_session_id:
                break
            current_id = sess.parent_session_id
        return target_agent_id in visited_agents

    async def _sentinel_analyze(
        self,
        message: str,
        source_agent_id: int,
        target_agent_id: int,
        depth: int,
    ) -> Optional[Dict]:
        """Run Sentinel analysis on the inter-agent message.
        Raises on failure so the caller can decide fail-open/closed policy."""
        from services.sentinel_service import SentinelService
        sentinel = SentinelService(self.db, self.tenant_id, token_tracker=self.token_tracker)
        result = await sentinel.analyze_prompt(
            prompt=message,
            agent_id=target_agent_id,
            source="agent_communication",
        )
        if result and result.is_threat_detected:
            if result.action == "blocked":
                return {"blocked": True, "reason": result.threat_reason, "score": result.threat_score}
            return {"blocked": False, "reason": result.threat_reason, "score": result.threat_score}
        return None

    async def _invoke_target_agent(
        self,
        target_agent: Agent,
        message: str,
        context: Optional[str],
        source_agent: Agent,
        depth: int,
    ) -> Dict:
        """Invoke the target agent's AI processing and return the result dict."""
        from agent.agent_service import AgentService

        # Build config dict directly (follows playground_service.py pattern)
        # Note: enabled_tools is empty to prevent recursive tool invocations
        # during inter-agent calls. The target agent uses its LLM knowledge only.
        agent_config = {
            "agent_id": target_agent.id,
            "model_provider": target_agent.model_provider,
            "model_name": target_agent.model_name,
            "system_prompt": target_agent.system_prompt,
            "keywords": target_agent.keywords or [],
            "memory_size": target_agent.memory_size or 1000,
            "enabled_tools": [],
            "response_template": target_agent.response_template,
            "enable_semantic_search": target_agent.enable_semantic_search or False,
            "context_message_count": target_agent.context_message_count or 10,
            "memory_isolation_mode": target_agent.memory_isolation_mode or "isolated",
        }

        # Get source agent's display name
        source_contact = self.db.query(Contact).filter(Contact.id == source_agent.contact_id).first()
        source_name = source_contact.friendly_name if source_contact else f"Agent {source_agent.id}"

        # Enrich with memory context from target agent's vector store
        # A2A searches across ALL the agent's memories (no sender filter)
        sender_key = f"agent:{source_agent.id}"
        memory_context = ""
        if target_agent.enable_semantic_search:
            try:
                from agent.memory.providers.registry import VectorStoreRegistry
                from agent.memory.embedding_service import EmbeddingService

                # Get embedding for the query
                embedder = EmbeddingService()
                query_embedding = embedder.embed_text(message)

                if target_agent.vector_store_instance_id:
                    # Use external vector store provider
                    registry = VectorStoreRegistry()
                    provider = registry.get_provider(
                        target_agent.vector_store_instance_id,
                        self.db,
                        tenant_id=self.tenant_id,
                    )
                    # Search without sender_key filter to find ALL memories
                    results = await provider.search_similar(
                        query_embedding=query_embedding,
                        limit=5,
                        sender_key=None,  # No sender filter for A2A
                    )
                    if results:
                        memory_parts = [f"- {r.text}" for r in results if r.text]
                        if memory_parts:
                            memory_context = "Relevant memories:\n" + "\n".join(memory_parts)
                            logger.info(f"A2A memory enrichment: found {len(memory_parts)} results for agent {target_agent.id}")
                else:
                    # ChromaDB default - use vector store manager
                    persist_dir = target_agent.chroma_db_path or f"./data/chroma_db/agent_{target_agent.id}"
                    from agent.memory.vector_store import VectorStore
                    vs = VectorStore(persist_dir)
                    results = vs.search_similar(query_embedding, limit=5)
                    if results:
                        memory_parts = [f"- {r['text']}" for r in results if r.get('text')]
                        if memory_parts:
                            memory_context = "Relevant memories:\n" + "\n".join(memory_parts)
            except Exception as e:
                logger.warning(f"A2A memory enrichment failed for agent {target_agent.id}: {e}", exc_info=True)

        # Build the prompt with context
        prompt_parts = [
            f"[INTER-AGENT REQUEST from '{source_name}' (depth {depth})]",
            f"Respond concisely and factually. Use your memory context to answer if available.",
        ]
        if memory_context:
            prompt_parts.append(f"\n--- Your Memory Context ---\n{memory_context}\n---")
        if context:
            prompt_parts.append(f"Additional Context: {context}")
        prompt_parts.append(f"Question: {message}")
        full_prompt = "\n".join(prompt_parts)

        agent_service = AgentService(
            agent_config,
            db=self.db,
            agent_id=target_agent.id,
            token_tracker=self.token_tracker,
            tenant_id=self.tenant_id,
            disable_skills=True,  # Prevent recursive tool use during A2A
        )

        result = await agent_service.process_message(
            sender_key=sender_key,
            message_text=full_prompt,
            original_query=message,
        )
        return result

    def _audit_log(
        self,
        action: str,
        source_agent_id: int,
        target_agent_id: int,
        details: Dict[str, Any],
    ):
        """Record a tenant-scoped audit event."""
        try:
            from services.audit_service import TenantAuditService
            audit = TenantAuditService(self.db)
            audit.log_event(
                tenant_id=self.tenant_id,
                user_id=None,
                action=action,
                resource_type="agent_communication",
                resource_id=str(source_agent_id),
                details={**details, "target_agent_id": target_agent_id},
                channel="system",
                severity="info" if "blocked" not in action else "warning",
            )
        except Exception as e:
            logger.warning(f"Audit log failed: {e}")
