"""
Phase 22.4: MCP Server Integration - API Routes

Provides CRUD endpoints for MCP server configurations, connection
management, tool discovery, and health monitoring. Follows the
same patterns as routes_provider_instances.py.
"""

import logging
import time
import asyncio
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import MCPServerConfig, MCPDiscoveredTool, MCPServerHealth
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
)
from services.audit_service import log_tenant_event, TenantAuditActions

logger = logging.getLogger(__name__)

router = APIRouter()

# Global engine reference
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine


def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== Pydantic Schemas ====================

VALID_TRANSPORT_TYPES = {"sse", "streamable_http", "stdio"}
VALID_AUTH_TYPES = {"none", "bearer", "header", "api_key"}
VALID_TRUST_LEVELS = {"system", "verified", "untrusted"}


class MCPServerCreate(BaseModel):
    server_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    transport_type: str = Field(..., description="sse|streamable_http|stdio")
    server_url: Optional[str] = None
    auth_type: str = Field(default="none", description="none|bearer|header|api_key")
    auth_token: Optional[str] = None  # Plaintext token (will be encrypted)
    auth_header_name: Optional[str] = None
    stdio_binary: Optional[str] = None
    stdio_args: List[str] = Field(default_factory=list)
    trust_level: str = Field(default="untrusted")
    max_retries: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=5, le=300)
    idle_timeout_seconds: int = Field(default=300, ge=60, le=3600)


class MCPServerUpdate(BaseModel):
    server_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    transport_type: Optional[str] = None
    server_url: Optional[str] = None
    auth_type: Optional[str] = None
    auth_token: Optional[str] = None
    auth_header_name: Optional[str] = None
    stdio_binary: Optional[str] = None
    stdio_args: Optional[List[str]] = None
    trust_level: Optional[str] = None
    max_retries: Optional[int] = Field(None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(None, ge=5, le=300)
    idle_timeout_seconds: Optional[int] = Field(None, ge=60, le=3600)
    is_active: Optional[bool] = None


class MCPServerResponse(BaseModel):
    id: int
    tenant_id: str
    server_name: str
    description: Optional[str] = None
    transport_type: str
    server_url: Optional[str] = None
    auth_type: str
    auth_configured: bool
    auth_header_name: Optional[str] = None
    stdio_binary: Optional[str] = None
    stdio_args: List[str] = []
    trust_level: str
    connection_status: str
    max_retries: int
    timeout_seconds: int
    idle_timeout_seconds: int
    is_active: bool
    last_connected_at: Optional[str] = None
    last_error: Optional[str] = None
    tool_count: int = 0
    created_at: str
    updated_at: str


class MCPToolResponse(BaseModel):
    id: int
    server_id: int
    tool_name: str
    namespaced_name: str
    description: Optional[str] = None
    input_schema: dict = {}
    is_enabled: bool
    scan_status: str
    discovered_at: str


class MCPToolToggle(BaseModel):
    is_enabled: bool


class MCPHealthResponse(BaseModel):
    id: int
    server_id: int
    check_type: str
    success: bool
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    checked_at: str


class MCPTestResponse(BaseModel):
    success: bool
    message: str
    tools_found: int = 0
    latency_ms: Optional[int] = None


# ==================== Helpers ====================


def _to_server_response(config: MCPServerConfig, db: Session) -> MCPServerResponse:
    """Convert MCPServerConfig model to response schema."""
    tool_count = db.query(MCPDiscoveredTool).filter(
        MCPDiscoveredTool.server_id == config.id
    ).count()

    return MCPServerResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        server_name=config.server_name,
        description=config.description,
        transport_type=config.transport_type,
        server_url=config.server_url,
        auth_type=config.auth_type or 'none',
        auth_configured=bool(config.auth_token_encrypted),
        auth_header_name=config.auth_header_name,
        stdio_binary=config.stdio_binary,
        stdio_args=config.stdio_args or [],
        trust_level=config.trust_level or 'untrusted',
        connection_status=config.connection_status or 'disconnected',
        max_retries=config.max_retries or 3,
        timeout_seconds=config.timeout_seconds or 30,
        idle_timeout_seconds=config.idle_timeout_seconds or 300,
        is_active=config.is_active,
        last_connected_at=config.last_connected_at.isoformat() if config.last_connected_at else None,
        last_error=config.last_error,
        tool_count=tool_count,
        created_at=config.created_at.isoformat() if config.created_at else "",
        updated_at=config.updated_at.isoformat() if config.updated_at else "",
    )


def _to_tool_response(tool: MCPDiscoveredTool) -> MCPToolResponse:
    """Convert MCPDiscoveredTool model to response schema."""
    return MCPToolResponse(
        id=tool.id,
        server_id=tool.server_id,
        tool_name=tool.tool_name,
        namespaced_name=tool.namespaced_name,
        description=tool.description,
        input_schema=tool.input_schema or {},
        is_enabled=tool.is_enabled,
        scan_status=tool.scan_status or 'pending',
        discovered_at=tool.discovered_at.isoformat() if tool.discovered_at else "",
    )


def _get_server_or_404(server_id: int, db: Session, ctx: TenantContext) -> MCPServerConfig:
    """Load MCPServerConfig by ID with tenant isolation."""
    config = db.query(MCPServerConfig).filter(MCPServerConfig.id == server_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if not ctx.can_access_resource(config.tenant_id):
        raise HTTPException(status_code=404, detail="MCP server not found")
    return config


# ==================== Endpoints ====================


@router.get("/mcp-servers", response_model=List[MCPServerResponse])
def list_mcp_servers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all MCP server configurations for the current tenant."""
    query = db.query(MCPServerConfig)
    query = ctx.filter_by_tenant(query, MCPServerConfig.tenant_id)
    query = query.filter(MCPServerConfig.is_active == True)
    servers = query.order_by(MCPServerConfig.server_name).all()
    return [_to_server_response(s, db) for s in servers]


@router.get("/mcp-servers/allowed-binaries")
def get_allowed_binaries(
    _user: User = Depends(require_permission("skills.mcp_server.manage")),
):
    """Return list of allowed stdio binary names."""
    from hub.mcp.stdio_transport import ALLOWED_MCP_STDIO_BINARIES
    return {"binaries": ALLOWED_MCP_STDIO_BINARIES}


@router.post("/mcp-servers", response_model=MCPServerResponse, status_code=201)
def create_mcp_server(
    data: MCPServerCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create a new MCP server configuration."""
    # Validate transport type
    if data.transport_type not in VALID_TRANSPORT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transport_type. Must be one of: {', '.join(sorted(VALID_TRANSPORT_TYPES))}"
        )

    # Validate auth type
    if data.auth_type not in VALID_AUTH_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid auth_type. Must be one of: {', '.join(sorted(VALID_AUTH_TYPES))}"
        )

    # Validate trust level
    if data.trust_level not in VALID_TRUST_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid trust_level. Must be one of: {', '.join(sorted(VALID_TRUST_LEVELS))}"
        )

    # SSE/HTTP transports require server_url
    if data.transport_type in ('sse', 'streamable_http') and not data.server_url:
        raise HTTPException(status_code=400, detail="server_url is required for SSE/HTTP transports")

    # stdio transport validation
    if data.transport_type == 'stdio':
        if not data.stdio_binary:
            raise HTTPException(status_code=400, detail="stdio_binary is required for stdio transport")

        from hub.mcp.stdio_transport import ALLOWED_MCP_STDIO_BINARIES

        # Reject path traversal in binary name
        if '/' in data.stdio_binary or '..' in data.stdio_binary or '\\' in data.stdio_binary:
            raise HTTPException(
                status_code=400,
                detail=f"Binary name contains path characters: '{data.stdio_binary}'"
            )

        # Validate binary is in allowlist
        if data.stdio_binary not in ALLOWED_MCP_STDIO_BINARIES:
            raise HTTPException(
                status_code=400,
                detail=f"Binary '{data.stdio_binary}' not allowed. Must be one of: {', '.join(ALLOWED_MCP_STDIO_BINARIES)}"
            )

        # server_url should be null/empty for stdio
        if data.server_url:
            raise HTTPException(
                status_code=400,
                detail="server_url should not be set for stdio transport"
            )

    # SSRF validate URL
    if data.server_url:
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(data.server_url)
        except SSRFValidationError as e:
            raise HTTPException(status_code=400, detail=f"Invalid server URL: {e}")

        # V060-SKL-002 FIX: Require HTTPS whenever an authentication credential
        # (bearer/header/api_key) is attached — bearer tokens over plaintext HTTP
        # are vulnerable to MITM interception.
        if data.auth_type and data.auth_type != "none":
            from urllib.parse import urlparse
            scheme = (urlparse(data.server_url).scheme or "").lower()
            if scheme != "https":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "MCP servers with authentication (bearer/header/api_key) "
                        "must use HTTPS — plaintext HTTP transmits credentials in the clear."
                    ),
                )

    # Check for duplicate server name within tenant
    existing = db.query(MCPServerConfig).filter(
        MCPServerConfig.tenant_id == ctx.tenant_id,
        MCPServerConfig.server_name == data.server_name,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Server name '{data.server_name}' already exists for this tenant"
        )

    # Create config
    config = MCPServerConfig(
        tenant_id=ctx.tenant_id,
        server_name=data.server_name,
        description=data.description,
        transport_type=data.transport_type,
        server_url=data.server_url,
        auth_type=data.auth_type,
        auth_header_name=data.auth_header_name,
        stdio_binary=data.stdio_binary,
        stdio_args=data.stdio_args,
        trust_level=data.trust_level,
        max_retries=data.max_retries,
        timeout_seconds=data.timeout_seconds,
        idle_timeout_seconds=data.idle_timeout_seconds,
        is_active=True,
        connection_status='disconnected',
    )
    db.add(config)
    db.flush()  # Get the ID for encryption identifier

    # Encrypt and store auth token if provided
    if data.auth_token:
        from hub.mcp.utils import encrypt_auth_token
        encrypted = encrypt_auth_token(data.auth_token, config.id, db)
        if not encrypted:
            raise HTTPException(status_code=500, detail="Failed to encrypt auth token")
        config.auth_token_encrypted = encrypted

    db.commit()
    db.refresh(config)
    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.MCP_CREATE, "mcp_server", str(config.id), {"name": data.server_name}, request)
    logger.info(f"Created MCP server '{data.server_name}' (transport={data.transport_type}) for tenant {ctx.tenant_id}")
    return _to_server_response(config, db)


@router.get("/mcp-servers/{server_id}", response_model=MCPServerResponse)
def get_mcp_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get a single MCP server configuration."""
    config = _get_server_or_404(server_id, db, ctx)
    return _to_server_response(config, db)


@router.put("/mcp-servers/{server_id}", response_model=MCPServerResponse)
def update_mcp_server(
    server_id: int,
    data: MCPServerUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update an MCP server configuration."""
    config = _get_server_or_404(server_id, db, ctx)

    if data.server_name is not None:
        # Check for duplicate name (excluding self)
        existing = db.query(MCPServerConfig).filter(
            MCPServerConfig.tenant_id == config.tenant_id,
            MCPServerConfig.server_name == data.server_name,
            MCPServerConfig.id != server_id,
        ).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Server name '{data.server_name}' already exists for this tenant"
            )
        config.server_name = data.server_name

    if data.transport_type is not None:
        if data.transport_type not in VALID_TRANSPORT_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid transport_type")
        config.transport_type = data.transport_type

    if data.server_url is not None:
        if data.server_url:
            from utils.ssrf_validator import validate_url, SSRFValidationError
            try:
                validate_url(data.server_url)
            except SSRFValidationError as e:
                raise HTTPException(status_code=400, detail=f"Invalid server URL: {e}")
        config.server_url = data.server_url or None

    if data.auth_type is not None:
        if data.auth_type not in VALID_AUTH_TYPES:
            raise HTTPException(status_code=400, detail=f"Invalid auth_type")
        config.auth_type = data.auth_type

    # V060-SKL-002 FIX: After applying server_url/auth_type updates, enforce
    # HTTPS whenever the server has an authentication credential attached.
    if config.server_url and config.auth_type and config.auth_type != "none":
        from urllib.parse import urlparse
        scheme = (urlparse(config.server_url).scheme or "").lower()
        if scheme != "https":
            raise HTTPException(
                status_code=400,
                detail=(
                    "MCP servers with authentication (bearer/header/api_key) "
                    "must use HTTPS — plaintext HTTP transmits credentials in the clear."
                ),
            )

    if data.auth_token is not None:
        if data.auth_token:
            from hub.mcp.utils import encrypt_auth_token
            encrypted = encrypt_auth_token(data.auth_token, config.id, db)
            if not encrypted:
                raise HTTPException(status_code=500, detail="Failed to encrypt auth token")
            config.auth_token_encrypted = encrypted
        else:
            config.auth_token_encrypted = None

    if data.auth_header_name is not None:
        config.auth_header_name = data.auth_header_name

    if data.stdio_binary is not None:
        if data.stdio_binary:
            # Reject path traversal in binary name
            if '/' in data.stdio_binary or '..' in data.stdio_binary or '\\' in data.stdio_binary:
                raise HTTPException(
                    status_code=400,
                    detail=f"Binary name contains path characters: '{data.stdio_binary}'"
                )

            from hub.mcp.stdio_transport import ALLOWED_MCP_STDIO_BINARIES
            # Validate binary is in allowlist
            if data.stdio_binary not in ALLOWED_MCP_STDIO_BINARIES:
                raise HTTPException(
                    status_code=400,
                    detail=f"Binary '{data.stdio_binary}' not allowed. Must be one of: {', '.join(ALLOWED_MCP_STDIO_BINARIES)}"
                )
        config.stdio_binary = data.stdio_binary

    if data.stdio_args is not None:
        # Validate stdio_args for shell metacharacters
        if data.stdio_args:
            import re as _re
            for arg in data.stdio_args:
                if _re.search(r'[;&|`$(){}]', arg):
                    raise HTTPException(
                        status_code=400,
                        detail=f"stdio_args contains shell metacharacters: '{arg}'"
                    )
        config.stdio_args = data.stdio_args

    if data.trust_level is not None:
        if data.trust_level not in VALID_TRUST_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid trust_level")
        config.trust_level = data.trust_level

    if data.max_retries is not None:
        config.max_retries = data.max_retries

    if data.timeout_seconds is not None:
        config.timeout_seconds = data.timeout_seconds

    if data.idle_timeout_seconds is not None:
        config.idle_timeout_seconds = data.idle_timeout_seconds

    if data.is_active is not None:
        config.is_active = data.is_active

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)
    logger.info(f"Updated MCP server {server_id} for tenant {config.tenant_id}")
    return _to_server_response(config, db)


@router.delete("/mcp-servers/{server_id}")
def delete_mcp_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Soft-delete an MCP server (set is_active=False)."""
    config = _get_server_or_404(server_id, db, ctx)
    config.is_active = False
    config.connection_status = 'disconnected'
    config.updated_at = datetime.utcnow()
    db.commit()
    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.MCP_DELETE, "mcp_server", str(server_id), {"name": config.server_name}, request)
    logger.info(f"Soft-deleted MCP server {server_id} for tenant {config.tenant_id}")
    return {"message": f"MCP server '{config.server_name}' deleted successfully"}


@router.post("/mcp-servers/{server_id}/connect")
async def connect_mcp_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Establish a persistent connection to the MCP server."""
    config = _get_server_or_404(server_id, db, ctx)

    from hub.mcp.connection_manager import MCPConnectionManager
    manager = MCPConnectionManager.get_instance()

    start_time = time.time()
    try:
        config.connection_status = 'connecting'
        db.commit()

        await manager.get_or_connect(server_id, db)
        latency_ms = int((time.time() - start_time) * 1000)

        # Log health check
        health = MCPServerHealth(
            server_id=server_id,
            check_type='manual',
            success=True,
            latency_ms=latency_ms,
        )
        db.add(health)
        db.commit()

        log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.MCP_CONNECT, "mcp_server", str(server_id), {"name": config.server_name}, request)

        return {"status": "connected", "latency_ms": latency_ms}

    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)

        config.connection_status = 'disconnected'
        config.last_error = error_msg
        db.commit()

        # Log failed health check
        health = MCPServerHealth(
            server_id=server_id,
            check_type='manual',
            success=False,
            latency_ms=latency_ms,
            error_message=error_msg,
        )
        db.add(health)
        db.commit()

        manager.record_failure(server_id, db, error_msg)
        raise HTTPException(status_code=502, detail=f"Connection failed: {error_msg}")


@router.post("/mcp-servers/{server_id}/disconnect")
async def disconnect_mcp_server(
    server_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Close the connection to the MCP server."""
    config = _get_server_or_404(server_id, db, ctx)

    from hub.mcp.connection_manager import MCPConnectionManager
    manager = MCPConnectionManager.get_instance()

    await manager.disconnect(server_id, db)

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.MCP_DISCONNECT, "mcp_server", str(server_id), {"name": config.server_name}, request)

    return {"status": "disconnected"}


@router.post("/mcp-servers/{server_id}/test", response_model=MCPTestResponse)
async def test_mcp_server(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Test MCP server connection: connect, list tools, then disconnect."""
    config = _get_server_or_404(server_id, db, ctx)

    from hub.mcp.connection_manager import MCPConnectionManager
    manager = MCPConnectionManager.get_instance()

    start_time = time.time()
    tools_found = 0
    error_msg = None
    success = False

    try:
        transport = await manager.get_or_connect(server_id, db)
        tools = await transport.list_tools()
        tools_found = len(tools)
        success = True
    except Exception as e:
        error_msg = str(e)
        manager.record_failure(server_id, db, error_msg)
    finally:
        # Always disconnect after test
        await manager.disconnect(server_id, db)

    latency_ms = int((time.time() - start_time) * 1000)

    # Log health check
    health = MCPServerHealth(
        server_id=server_id,
        check_type='list_tools',
        success=success,
        latency_ms=latency_ms,
        error_message=error_msg,
    )
    db.add(health)

    # Update config status
    if success:
        config.last_error = None
        manager.record_success(server_id)
    else:
        config.last_error = error_msg

    config.connection_status = 'disconnected'
    db.commit()

    if success:
        return MCPTestResponse(
            success=True,
            message=f"Connected successfully. Found {tools_found} tools.",
            tools_found=tools_found,
            latency_ms=latency_ms,
        )
    else:
        return MCPTestResponse(
            success=False,
            message=f"Connection failed: {error_msg}",
            tools_found=0,
            latency_ms=latency_ms,
        )


@router.post("/mcp-servers/{server_id}/refresh-tools")
async def refresh_mcp_tools(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Discover/refresh tools from the MCP server."""
    config = _get_server_or_404(server_id, db, ctx)

    from hub.mcp.connection_manager import MCPConnectionManager
    manager = MCPConnectionManager.get_instance()

    start_time = time.time()

    try:
        new_tools = await manager.refresh_tools(server_id, db)
        latency_ms = int((time.time() - start_time) * 1000)

        # Count total tools after refresh
        total = db.query(MCPDiscoveredTool).filter(
            MCPDiscoveredTool.server_id == server_id
        ).count()

        # Log health check
        health = MCPServerHealth(
            server_id=server_id,
            check_type='list_tools',
            success=True,
            latency_ms=latency_ms,
        )
        db.add(health)
        db.commit()

        return {
            "total_tools": total,
            "new_tools": len(new_tools),
            "latency_ms": latency_ms,
        }

    except Exception as e:
        manager.record_failure(server_id, db, str(e))
        raise HTTPException(status_code=502, detail=f"Tool refresh failed: {e}")


@router.get("/mcp-servers/{server_id}/tools", response_model=List[MCPToolResponse])
def list_mcp_tools(
    server_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List discovered tools for an MCP server."""
    config = _get_server_or_404(server_id, db, ctx)

    tools = db.query(MCPDiscoveredTool).filter(
        MCPDiscoveredTool.server_id == server_id,
        MCPDiscoveredTool.tenant_id == ctx.tenant_id,
    ).order_by(MCPDiscoveredTool.tool_name).all()

    return [_to_tool_response(t) for t in tools]


@router.put("/mcp-servers/{server_id}/tools/{tool_id}", response_model=MCPToolResponse)
def toggle_mcp_tool(
    server_id: int,
    tool_id: int,
    data: MCPToolToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.mcp_server.manage")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Enable or disable a discovered MCP tool."""
    config = _get_server_or_404(server_id, db, ctx)

    tool = db.query(MCPDiscoveredTool).filter(
        MCPDiscoveredTool.id == tool_id,
        MCPDiscoveredTool.server_id == server_id,
        MCPDiscoveredTool.tenant_id == ctx.tenant_id,
    ).first()

    if not tool:
        raise HTTPException(status_code=404, detail="MCP tool not found")

    tool.is_enabled = data.is_enabled
    db.commit()
    db.refresh(tool)

    logger.info(
        f"{'Enabled' if data.is_enabled else 'Disabled'} MCP tool "
        f"'{tool.tool_name}' on server {server_id}"
    )
    return _to_tool_response(tool)


@router.get("/mcp-servers/{server_id}/health", response_model=List[MCPHealthResponse])
def get_mcp_health(
    server_id: int,
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get health check history for an MCP server."""
    config = _get_server_or_404(server_id, db, ctx)

    checks = db.query(MCPServerHealth).filter(
        MCPServerHealth.server_id == server_id
    ).order_by(MCPServerHealth.checked_at.desc()).limit(min(limit, 100)).all()

    return [
        MCPHealthResponse(
            id=c.id,
            server_id=c.server_id,
            check_type=c.check_type,
            success=c.success,
            latency_ms=c.latency_ms,
            error_message=c.error_message,
            checked_at=c.checked_at.isoformat() if c.checked_at else "",
        )
        for c in checks
    ]
