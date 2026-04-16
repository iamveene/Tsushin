"""
Watcher Activity Service - Real-time Activity Events for Graph View (Phase 8)

Emits tenant-scoped activity events for Graph View visualization:
- Agent processing start/end (message being handled)
- Skill execution (when a skill is used)
- Knowledge Base usage (when KB is searched)

Events are non-blocking (fire-and-forget via asyncio.create_task) to avoid
impacting message processing performance.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WatcherActivityService:
    """
    Singleton service for emitting real-time activity events to Graph View WebSocket connections.

    This service manages a separate set of WebSocket connections specifically for
    Graph View activity updates. It follows the same tenant-scoped pattern used
    in shell_websocket.py for UI status updates.
    """

    _instance: Optional['WatcherActivityService'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Tenant -> Set of WebSocket connections
        self.tenant_connections: Dict[str, Set[WebSocket]] = {}
        self._initialized = True
        logger.info("WatcherActivityService initialized")

    @classmethod
    def get_instance(cls) -> 'WatcherActivityService':
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def register_connection(self, tenant_id: str, websocket: WebSocket):
        """
        Register a Graph View WebSocket connection for a tenant.

        Args:
            tenant_id: Tenant ID
            websocket: WebSocket connection
        """
        if tenant_id not in self.tenant_connections:
            self.tenant_connections[tenant_id] = set()
        self.tenant_connections[tenant_id].add(websocket)
        logger.info(f"Graph View connection registered: tenant={tenant_id}, total={len(self.tenant_connections[tenant_id])}")

    def unregister_connection(self, tenant_id: str, websocket: WebSocket):
        """
        Remove a Graph View WebSocket connection.

        Args:
            tenant_id: Tenant ID
            websocket: WebSocket connection
        """
        if tenant_id in self.tenant_connections:
            self.tenant_connections[tenant_id].discard(websocket)
            if not self.tenant_connections[tenant_id]:
                del self.tenant_connections[tenant_id]
            logger.info(f"Graph View connection unregistered: tenant={tenant_id}")

    def get_connection_count(self, tenant_id: Optional[str] = None) -> int:
        """Get number of active connections, optionally filtered by tenant."""
        if tenant_id:
            return len(self.tenant_connections.get(tenant_id, set()))
        return sum(len(conns) for conns in self.tenant_connections.values())

    # =========================================================================
    # Event Broadcasting
    # =========================================================================

    async def _broadcast_to_tenant(self, tenant_id: str, message: Dict[str, Any]):
        """
        Broadcast a message to all Graph View connections for a tenant.

        Args:
            tenant_id: Target tenant ID
            message: Message payload
        """
        if tenant_id not in self.tenant_connections:
            return

        disconnected = set()
        for websocket in set(self.tenant_connections[tenant_id]):
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Error broadcasting to tenant {tenant_id}: {e}")
                disconnected.add(websocket)

        # Clean up disconnected clients
        for ws in disconnected:
            self.tenant_connections[tenant_id].discard(ws)

        if disconnected:
            logger.debug(f"Cleaned up {len(disconnected)} disconnected Graph View clients")

    # =========================================================================
    # Activity Event Emitters
    # =========================================================================

    async def emit_agent_processing(
        self,
        tenant_id: str,
        agent_id: int,
        status: str,
        sender_key: Optional[str] = None,
        channel: Optional[str] = None
    ):
        """
        Emit agent processing start/end event.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID
            status: "start" or "end"
            sender_key: Optional sender key for context
            channel: Optional channel type (e.g. "whatsapp", "playground")
        """
        if tenant_id not in self.tenant_connections:
            return  # No listeners, skip

        message = {
            "type": "agent_processing",
            "agent_id": agent_id,
            "status": status,
            "sender_key": sender_key,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        if channel:
            message["channel"] = channel

        await self._broadcast_to_tenant(tenant_id, message)
        logger.info(f"Emitted agent_processing: agent={agent_id}, status={status}, channel={channel}")

    async def emit_skill_used(
        self,
        tenant_id: str,
        agent_id: int,
        skill_type: str,
        skill_name: str
    ):
        """
        Emit skill execution event.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID that used the skill
            skill_type: Skill type identifier (e.g., "web_search")
            skill_name: Human-readable skill name
        """
        if tenant_id not in self.tenant_connections:
            return  # No listeners, skip

        message = {
            "type": "skill_used",
            "agent_id": agent_id,
            "skill_type": skill_type,
            "skill_name": skill_name,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        await self._broadcast_to_tenant(tenant_id, message)
        logger.debug(f"Emitted skill_used: agent={agent_id}, skill={skill_type}")

    async def emit_kb_used(
        self,
        tenant_id: str,
        agent_id: int,
        doc_count: int,
        chunk_count: int
    ):
        """
        Emit knowledge base usage event.

        Args:
            tenant_id: Tenant ID
            agent_id: Agent ID that used KB
            doc_count: Number of documents matched
            chunk_count: Number of chunks retrieved
        """
        if tenant_id not in self.tenant_connections:
            return  # No listeners, skip

        message = {
            "type": "kb_used",
            "agent_id": agent_id,
            "doc_count": doc_count,
            "chunk_count": chunk_count,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        await self._broadcast_to_tenant(tenant_id, message)
        logger.debug(f"Emitted kb_used: agent={agent_id}, docs={doc_count}, chunks={chunk_count}")

    async def emit_channel_health(
        self,
        tenant_id: str,
        channel_type: str,
        instance_id: int,
        circuit_state: str,
        health_status: str,
        latency_ms: float = None,
        detail: str = None
    ):
        """
        Emit channel health update event (Item 38).

        Args:
            tenant_id: Tenant ID
            channel_type: Channel type (whatsapp, telegram)
            instance_id: Channel instance ID
            circuit_state: Circuit breaker state (closed, open, half_open)
            health_status: Health status (healthy, unhealthy, degraded)
            latency_ms: Health check latency in milliseconds
            detail: Optional detail message
        """
        if tenant_id not in self.tenant_connections:
            return  # No listeners, skip

        message = {
            "type": "channel_health",
            "channel_type": channel_type,
            "instance_id": instance_id,
            "circuit_state": circuit_state,
            "health_status": health_status,
            "latency_ms": latency_ms,
            "detail": detail,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

        await self._broadcast_to_tenant(tenant_id, message)
        logger.debug(f"Emitted channel_health: {channel_type}/{instance_id}, state={circuit_state}")

    async def emit_agent_communication(
        self,
        tenant_id: str,
        initiator_agent_id: int,
        target_agent_id: int,
        session_id: int,
        status: str,
        session_type: str,
        depth: int = 1
    ) -> None:
        """
        Emit A2A communication event to Watcher WebSocket clients.

        Args:
            tenant_id: Tenant ID
            initiator_agent_id: ID of the agent initiating the communication
            target_agent_id: ID of the agent receiving the communication
            session_id: AgentCommunicationSession ID
            status: "start" or "end"
            session_type: "ask" or "delegate" (maps to session_type in AgentCommunicationSession)
            depth: Delegation depth (0-based from AgentCommunicationSession.depth, displayed as 1-based)
        """
        if tenant_id not in self.tenant_connections:
            return  # No listeners, skip

        message = {
            "type": "agent_communication",
            "initiator_agent_id": initiator_agent_id,
            "target_agent_id": target_agent_id,
            "session_id": session_id,
            "status": status,
            "session_type": session_type,
            "depth": depth,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        await self._broadcast_to_tenant(tenant_id, message)
        logger.debug(f"Emitted agent_communication: {initiator_agent_id}->{target_agent_id}, status={status}, depth={depth}")


# Convenience functions for fire-and-forget event emission
def emit_agent_processing_async(
    tenant_id: str,
    agent_id: int,
    status: str,
    sender_key: Optional[str] = None,
    channel: Optional[str] = None
):
    """
    Fire-and-forget wrapper for agent processing events.

    Safe to call from sync or async contexts - creates a background task.
    """
    service = WatcherActivityService.get_instance()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(service.emit_agent_processing(
            tenant_id=tenant_id,
            agent_id=agent_id,
            status=status,
            sender_key=sender_key,
            channel=channel
        ))
    except RuntimeError:
        # No running loop, skip emission
        pass


def emit_skill_used_async(
    tenant_id: str,
    agent_id: int,
    skill_type: str,
    skill_name: str
):
    """Fire-and-forget wrapper for skill used events."""
    service = WatcherActivityService.get_instance()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(service.emit_skill_used(
            tenant_id=tenant_id,
            agent_id=agent_id,
            skill_type=skill_type,
            skill_name=skill_name
        ))
    except RuntimeError:
        pass


def emit_kb_used_async(
    tenant_id: str,
    agent_id: int,
    doc_count: int,
    chunk_count: int
):
    """Fire-and-forget wrapper for KB used events."""
    service = WatcherActivityService.get_instance()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(service.emit_kb_used(
            tenant_id=tenant_id,
            agent_id=agent_id,
            doc_count=doc_count,
            chunk_count=chunk_count
        ))
    except RuntimeError:
        pass


def emit_channel_health_async(
    tenant_id: str,
    channel_type: str,
    instance_id: int,
    circuit_state: str,
    health_status: str,
    latency_ms: float = None,
    detail: str = None
):
    """Fire-and-forget wrapper for channel health events (Item 38)."""
    service = WatcherActivityService.get_instance()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(service.emit_channel_health(
            tenant_id=tenant_id,
            channel_type=channel_type,
            instance_id=instance_id,
            circuit_state=circuit_state,
            health_status=health_status,
            latency_ms=latency_ms,
            detail=detail
        ))
    except RuntimeError:
        pass


def emit_agent_communication_async(
    tenant_id: str,
    initiator_agent_id: int,
    target_agent_id: int,
    session_id: int,
    status: str,
    session_type: str,
    depth: int = 1
):
    """Fire-and-forget wrapper for A2A communication events."""
    service = WatcherActivityService.get_instance()
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(service.emit_agent_communication(
            tenant_id=tenant_id,
            initiator_agent_id=initiator_agent_id,
            target_agent_id=target_agent_id,
            session_id=session_id,
            status=status,
            session_type=session_type,
            depth=depth
        ))
    except RuntimeError:
        pass
