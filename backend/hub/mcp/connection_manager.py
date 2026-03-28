"""Singleton connection manager for MCP server connections.

Manages the lifecycle of MCP transport connections with:
- Lazy connection establishment (connect on first use)
- Tenant-indexed connection tracking
- Failure counting with circuit-breaker-style degradation
- SSRF validation on all outbound URLs
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Set, Optional, Any
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_instance = None


class MCPConnectionManager:
    """Manages persistent MCP server transport connections.

    Uses a singleton pattern (via get_instance) to maintain a global
    pool of active connections indexed by server_id, with tenant-level
    grouping for bulk operations.
    """

    _connections: Dict[int, Any]  # server_id -> transport
    _tenant_index: Dict[str, Set[int]]  # tenant_id -> server_ids
    _failure_counts: Dict[int, int]
    _degraded_until: Dict[int, float]

    def __init__(self):
        self._connections = {}
        self._tenant_index = {}
        self._failure_counts = {}
        self._degraded_until = {}

    @classmethod
    def get_instance(cls) -> 'MCPConnectionManager':
        """Get or create the singleton MCPConnectionManager."""
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    async def get_or_connect(self, server_id: int, db: Session) -> Any:
        """Get existing connection or create new one.

        Args:
            server_id: ID of the MCPServerConfig record.
            db: SQLAlchemy session for loading config.

        Returns:
            Connected transport object.

        Raises:
            RuntimeError: If server is in degraded cooldown.
            ValueError: If server not found or SSRF blocked.
        """
        # Check degraded cooldown
        if server_id in self._degraded_until:
            if time.time() < self._degraded_until[server_id]:
                raise RuntimeError(f"Server {server_id} is degraded, retry after cooldown")
            else:
                del self._degraded_until[server_id]
                self._failure_counts.pop(server_id, None)

        # Return existing healthy connection
        if server_id in self._connections:
            transport = self._connections[server_id]
            if transport.is_connected():
                return transport

        # Load config from DB
        from models import MCPServerConfig
        config = db.query(MCPServerConfig).filter(MCPServerConfig.id == server_id).first()
        if not config:
            raise ValueError(f"MCP server {server_id} not found")

        if not config.is_active:
            raise ValueError(f"MCP server {server_id} is not active")

        # SSRF validate URL before connecting
        if config.server_url:
            from utils.ssrf_validator import validate_url, SSRFValidationError
            try:
                validate_url(config.server_url)
            except SSRFValidationError as e:
                raise ValueError(f"SSRF blocked: {e}")

        # Create transport and connect
        transport = self._create_transport(config)
        await transport.connect()

        # Update tracking state
        self._connections[server_id] = transport
        self._tenant_index.setdefault(config.tenant_id, set()).add(server_id)
        self._failure_counts[server_id] = 0

        # Update DB connection status
        config.connection_status = 'healthy'
        config.last_connected_at = datetime.utcnow()
        config.last_error = None
        db.commit()

        return transport

    def _create_transport(self, config):
        """Create the appropriate transport for the server config.

        Args:
            config: MCPServerConfig model instance.

        Returns:
            Transport instance (not yet connected).

        Raises:
            ValueError: If transport type is unsupported.
        """
        if config.transport_type in ('sse', 'streamable_http'):
            from hub.mcp.sse_transport import SSETransport
            return SSETransport(config)
        else:
            raise ValueError(f"Unsupported transport type: {config.transport_type}")

    async def disconnect(self, server_id: int, db: Optional[Session] = None):
        """Disconnect a specific server.

        Args:
            server_id: Server to disconnect.
            db: Optional DB session to update connection status.
        """
        if server_id in self._connections:
            try:
                await self._connections[server_id].disconnect()
            except Exception:
                pass
            del self._connections[server_id]

        # Clean up tenant index
        for tenant_id, server_ids in self._tenant_index.items():
            server_ids.discard(server_id)

        # Update DB status if session provided
        if db:
            from models import MCPServerConfig
            config = db.query(MCPServerConfig).filter(MCPServerConfig.id == server_id).first()
            if config:
                config.connection_status = 'disconnected'
                db.commit()

    async def disconnect_tenant(self, tenant_id: str, db: Optional[Session] = None):
        """Disconnect all servers for a tenant.

        Args:
            tenant_id: Tenant whose servers to disconnect.
            db: Optional DB session.
        """
        server_ids = list(self._tenant_index.get(tenant_id, set()))
        for server_id in server_ids:
            await self.disconnect(server_id, db)

    async def refresh_tools(self, server_id: int, db: Session) -> list:
        """Discover tools from the MCP server and upsert into DB.

        Args:
            server_id: Server to refresh tools from.
            db: SQLAlchemy session.

        Returns:
            List of newly discovered MCPDiscoveredTool records.
        """
        transport = await self.get_or_connect(server_id, db)
        tools = await transport.list_tools()

        from models import MCPServerConfig, MCPDiscoveredTool
        config = db.query(MCPServerConfig).filter(MCPServerConfig.id == server_id).first()

        discovered = []
        seen_tool_names = set()

        for tool in tools:
            tool_name = tool.name if hasattr(tool, 'name') else str(tool)
            seen_tool_names.add(tool_name)
            namespaced = f"{config.server_name}__{tool_name}"

            existing = db.query(MCPDiscoveredTool).filter(
                MCPDiscoveredTool.server_id == server_id,
                MCPDiscoveredTool.tool_name == tool_name
            ).first()

            if existing:
                existing.description = getattr(tool, 'description', '') or ''
                existing.input_schema = getattr(tool, 'inputSchema', {}) or {}
                existing.namespaced_name = namespaced
            else:
                new_tool = MCPDiscoveredTool(
                    server_id=server_id,
                    tenant_id=config.tenant_id,
                    tool_name=tool_name,
                    namespaced_name=namespaced,
                    description=getattr(tool, 'description', '') or '',
                    input_schema=getattr(tool, 'inputSchema', {}) or {},
                    is_enabled=True,
                    scan_status='clean'
                )
                db.add(new_tool)
                discovered.append(new_tool)

        db.commit()
        return discovered

    def record_failure(self, server_id: int, db: Optional[Session] = None, error: Optional[str] = None):
        """Record a connection/call failure for circuit breaker tracking.

        After 5 consecutive failures, the server enters a 5-minute degraded
        cooldown during which new connection attempts are rejected.

        Args:
            server_id: Server that failed.
            db: Optional DB session to update status.
            error: Optional error message.
        """
        self._failure_counts[server_id] = self._failure_counts.get(server_id, 0) + 1
        if self._failure_counts[server_id] >= 5:
            self._degraded_until[server_id] = time.time() + 300  # 5 min cooldown
            logger.warning(f"MCP server {server_id} marked DEGRADED after 5 failures")

            if db:
                from models import MCPServerConfig
                config = db.query(MCPServerConfig).filter(MCPServerConfig.id == server_id).first()
                if config:
                    config.connection_status = 'degraded'
                    config.last_error = error
                    db.commit()

    def record_success(self, server_id: int):
        """Reset failure count after a successful operation."""
        self._failure_counts[server_id] = 0

    def get_connection_status(self, server_id: int) -> str:
        """Get the current connection status for a server.

        Returns:
            One of 'connected', 'disconnected', 'degraded'.
        """
        if server_id in self._degraded_until and time.time() < self._degraded_until[server_id]:
            return 'degraded'
        if server_id in self._connections and self._connections[server_id].is_connected():
            return 'connected'
        return 'disconnected'
