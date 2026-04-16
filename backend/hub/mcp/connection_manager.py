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
from types import SimpleNamespace
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
                validate_url(config.server_url, allow_private=True)
            except SSRFValidationError as e:
                raise ValueError(f"SSRF blocked: {e}")

        # BUG-512: For stdio transports the binary runs inside the tenant's
        # toolbox container. Auto-start that container here so first-time
        # /test calls don't fail with "Container not found for tenant ...".
        if config.transport_type == 'stdio':
            try:
                from services.toolbox_container_service import ToolboxContainerService
                ToolboxContainerService().ensure_container_running(
                    tenant_id=config.tenant_id, db=db
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to start toolbox container for tenant {config.tenant_id}: {e}"
                ) from e

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
        # Cache a plain snapshot instead of a live ORM object so reused MCP
        # connections do not fail after the originating SQLAlchemy session ends.
        config_snapshot = SimpleNamespace(
            id=config.id,
            tenant_id=config.tenant_id,
            server_name=config.server_name,
            transport_type=config.transport_type,
            server_url=config.server_url,
            auth_type=config.auth_type,
            auth_token_encrypted=config.auth_token_encrypted,
            auth_header_name=config.auth_header_name,
            stdio_binary=config.stdio_binary,
            stdio_args=list(config.stdio_args or []),
            trust_level=config.trust_level,
            timeout_seconds=config.timeout_seconds,
            idle_timeout_seconds=config.idle_timeout_seconds,
            is_active=config.is_active,
        )

        if config.transport_type in ('sse', 'streamable_http'):
            from hub.mcp.sse_transport import SSETransport
            return SSETransport(config_snapshot)
        elif config.transport_type == 'stdio':
            from hub.mcp.stdio_transport import StdioTransport
            return StdioTransport(config_snapshot)
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

    # Security C-3: Maximum description length for MCP tool descriptions
    MAX_TOOL_DESCRIPTION_CHARS = 1000

    async def _scan_tool_description(
        self, description: str, tool_name: str, trust_level: str, tenant_id: str, db: Session
    ) -> str:
        """Run Sentinel scan on an MCP tool description.

        Trusted sources (system/verified) are whitelisted to avoid false
        positives and unnecessary LLM calls. Untrusted descriptions are
        scanned for prompt injection and other threats.

        Args:
            description: Tool description text (already truncated).
            tool_name: Name of the tool (for logging).
            trust_level: Server trust level ('system', 'verified', 'untrusted').
            tenant_id: Tenant ID for Sentinel config resolution.
            db: SQLAlchemy session.

        Returns:
            Scan status string: 'clean' or 'rejected'.
        """
        # Trusted servers skip scanning
        if trust_level in ('system', 'verified'):
            return 'clean'

        # Empty descriptions are trivially clean
        if not description or not description.strip():
            return 'clean'

        try:
            from services.sentinel_service import SentinelService
            sentinel = SentinelService(db, tenant_id=tenant_id)
            result = await sentinel.analyze_prompt(
                prompt=description,
                source=None,  # Not an internal source — should be scanned
            )
            if hasattr(result, 'is_threat_detected') and result.is_threat_detected:
                logger.warning(
                    f"Sentinel rejected MCP tool description: tool={tool_name}, "
                    f"reason={getattr(result, 'threat_reason', 'unknown')}"
                )
                return 'rejected'
            return 'clean'
        except Exception as e:
            # Fail-open: if Sentinel is unavailable, allow the tool
            logger.warning(f"Sentinel scan unavailable for tool '{tool_name}', defaulting to clean: {e}")
            return 'clean'

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
            tool_name = self._get_tool_value(tool, "name")
            if not tool_name:
                logger.warning(f"Skipping MCP tool without a name on server {server_id}: {tool!r}")
                continue
            seen_tool_names.add(tool_name)
            namespaced = f"{config.server_name}__{tool_name}"

            # Security C-3: Truncate description to prevent oversized payloads
            raw_description = self._get_tool_value(tool, "description", default="") or ""
            description = raw_description[:self.MAX_TOOL_DESCRIPTION_CHARS]
            input_schema = (
                self._get_tool_value(tool, "inputSchema")
                or self._get_tool_value(tool, "input_schema")
                or {}
            )

            # Security M-4: Sentinel scan for untrusted tool descriptions
            scan_status = await self._scan_tool_description(
                description, tool_name, config.trust_level, config.tenant_id, db
            )

            existing = db.query(MCPDiscoveredTool).filter(
                MCPDiscoveredTool.server_id == server_id,
                MCPDiscoveredTool.tool_name == tool_name
            ).first()

            if existing:
                existing.description = description
                existing.input_schema = input_schema
                existing.namespaced_name = namespaced
                existing.scan_status = scan_status
            else:
                new_tool = MCPDiscoveredTool(
                    server_id=server_id,
                    tenant_id=config.tenant_id,
                    tool_name=tool_name,
                    namespaced_name=namespaced,
                    description=description,
                    input_schema=input_schema,
                    is_enabled=True,
                    scan_status=scan_status
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

    @staticmethod
    def _get_tool_value(tool: Any, key: str, default: Any = None) -> Any:
        """Read a tool field from MCP SDK objects or stdio JSON dictionaries."""
        if isinstance(tool, dict):
            return tool.get(key, default)
        return getattr(tool, key, default)
