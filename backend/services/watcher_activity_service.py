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
        for websocket in self.tenant_connections[tenant_id]:
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
        logger.debug(f"Emitted agent_processing: agent={agent_id}, status={status}, channel={channel}")

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
