"""
Shell Skill API Routes (Phase 18)
Remote Command Execution via C2 Architecture

Provides REST API endpoints for:
- Shell integration management (CRUD)
- Beacon registration and check-in
- Command queue management
"""

import logging
import secrets
import hashlib
import uuid
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Header, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from models import ShellIntegration, ShellCommand, HubIntegration, Agent
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
    get_current_user_required
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shell", tags=["Shell Skill"])

# Global engine reference (set by main app.py)
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine


def get_db():
    """Dependency to get database session"""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Helper Functions
# ============================================================================

def generate_api_key() -> tuple[str, str]:
    """
    Generate a secure API key for beacon authentication.

    Returns:
        tuple: (plaintext_key, hashed_key)

    Key format: shb_<43 chars of base64>
    Total length: 47 characters
    """
    # Generate 32 random bytes (256 bits of entropy)
    random_bytes = secrets.token_bytes(32)
    # Encode as URL-safe base64 (43 chars for 32 bytes)
    key_body = secrets.token_urlsafe(32)
    # Add prefix
    plaintext_key = f"shb_{key_body}"
    # Hash for storage
    hashed_key = hashlib.sha256(plaintext_key.encode()).hexdigest()
    return plaintext_key, hashed_key


def hash_api_key(api_key: str) -> str:
    """Hash an API key for comparison."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_beacon_api_key(
    api_key: str,
    db: Session
) -> Optional[ShellIntegration]:
    """
    Verify beacon API key and return the integration.

    Returns:
        ShellIntegration if valid, None otherwise
    """
    hashed = hash_api_key(api_key)
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.api_key_hash == hashed,
        ShellIntegration.is_active == True
    ).first()
    return integration


def verify_integration_access(
    integration: HubIntegration,
    ctx: TenantContext
) -> None:
    """Verify user can access an integration (tenant check)."""
    if not ctx.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this integration")


# ============================================================================
# Request/Response Models
# ============================================================================

class ShellIntegrationCreate(BaseModel):
    """Request model for creating a shell integration."""
    name: str = Field(..., min_length=1, max_length=200, description="Friendly name for the beacon")
    display_name: Optional[str] = Field(None, max_length=200, description="Display name")
    poll_interval: int = Field(5, ge=1, le=3600, description="Poll interval in seconds")
    mode: str = Field("beacon", pattern="^(beacon|interactive)$", description="Connection mode")
    allowed_commands: Optional[List[str]] = Field(default=[], description="Allowed commands (empty = all)")
    allowed_paths: Optional[List[str]] = Field(default=[], description="Allowed paths (empty = all)")
    retention_days: Optional[int] = Field(None, ge=1, le=365, description="Result retention in days")
    yolo_mode: bool = Field(False, description="YOLO mode - auto-approve high-risk commands (blocked commands still rejected)")


class ShellIntegrationUpdate(BaseModel):
    """Request model for updating a shell integration."""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    display_name: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None
    poll_interval: Optional[int] = Field(None, ge=1, le=3600)
    mode: Optional[str] = Field(None, pattern="^(beacon|interactive)$")
    allowed_commands: Optional[List[str]] = None
    allowed_paths: Optional[List[str]] = None
    retention_days: Optional[int] = Field(None, ge=1, le=365)
    yolo_mode: Optional[bool] = Field(None, description="YOLO mode - auto-approve high-risk commands")


class ShellIntegrationResponse(BaseModel):
    """Response model for shell integration."""
    id: int
    name: str
    display_name: Optional[str]
    type: str
    is_active: bool
    health_status: str
    tenant_id: Optional[str]
    poll_interval: int
    mode: str
    hostname: Optional[str]
    remote_ip: Optional[str]
    os_info: Optional[Dict]
    last_checkin: Optional[str]
    is_online: bool
    allowed_commands: List[str]
    allowed_paths: List[str]
    retention_days: Optional[int]
    registered_at: Optional[str]
    created_at: str
    yolo_mode: bool = Field(False, description="YOLO mode - auto-approve high-risk commands")


class ShellIntegrationCreateResponse(BaseModel):
    """Response model for newly created shell integration (includes API key)."""
    id: int
    name: str
    api_key: str  # Only returned on creation - SAVE THIS!
    message: str


class BeaconRegistrationRequest(BaseModel):
    """Request model for beacon registration (first check-in)."""
    hostname: str = Field(..., max_length=255)
    os_info: Optional[Dict] = None


class BeaconCheckinRequest(BaseModel):
    """Request model for beacon check-in."""
    hostname: Optional[str] = None  # Can update hostname on checkin
    os_info: Optional[Dict] = None  # Can update OS info


class BeaconCheckinResponse(BaseModel):
    """Response model for beacon check-in."""
    status: str
    poll_interval: int
    pending_commands: List[Dict]


class CommandQueueRequest(BaseModel):
    """Request model for queueing a command."""
    commands: List[str] = Field(..., min_items=1, description="Commands to execute")
    timeout_seconds: int = Field(300, ge=1, le=3600, description="Timeout in seconds")


class CommandResponse(BaseModel):
    """Response model for shell command."""
    id: str
    shell_id: int
    tenant_id: str
    commands: List[str]
    initiated_by: str
    status: str
    queued_at: str
    sent_at: Optional[str]
    completed_at: Optional[str]
    exit_code: Optional[int]
    stdout: Optional[str]
    stderr: Optional[str]
    execution_time_ms: Optional[int]
    error_message: Optional[str]


class CommandResultRequest(BaseModel):
    """Request model for beacon to report command results."""
    command_id: str
    exit_code: int
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    execution_time_ms: Optional[int] = None
    final_working_dir: Optional[str] = None
    full_result_json: Optional[List[Dict]] = None
    error_message: Optional[str] = None


# ============================================================================
# Shell Integration Endpoints (Admin)
# ============================================================================

@router.get("/integrations", response_model=List[ShellIntegrationResponse])
async def list_shell_integrations(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all shell integrations for the tenant.
    """
    query = db.query(ShellIntegration)
    query = ctx.filter_by_tenant(query, ShellIntegration.tenant_id)

    if active_only:
        query = query.filter(ShellIntegration.is_active == True)

    integrations = query.all()

    result = []
    for integ in integrations:
        result.append(ShellIntegrationResponse(
            id=integ.id,
            name=integ.name,
            display_name=integ.display_name,
            type=integ.type,
            is_active=integ.is_active,
            health_status=integ.health_status,
            tenant_id=integ.tenant_id,
            poll_interval=integ.poll_interval,
            mode=integ.mode,
            hostname=integ.hostname,
            remote_ip=integ.remote_ip,
            os_info=integ.os_info,
            last_checkin=integ.last_checkin.isoformat() if integ.last_checkin else None,
            is_online=integ.is_online,
            allowed_commands=integ.allowed_commands or [],
            allowed_paths=integ.allowed_paths or [],
            retention_days=integ.retention_days,
            registered_at=integ.registered_at.isoformat() if integ.registered_at else None,
            created_at=integ.created_at.isoformat() if integ.created_at else "",
            yolo_mode=integ.yolo_mode
        ))

    return result


@router.post("/integrations", response_model=ShellIntegrationCreateResponse)
async def create_shell_integration(
    request: ShellIntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create a new shell integration.

    Returns the API key - SAVE IT! It cannot be retrieved later.
    """
    # Generate API key
    plaintext_key, hashed_key = generate_api_key()

    # Create ShellIntegration directly (inherits from HubIntegration)
    # SQLAlchemy's joined table inheritance handles inserting into both tables
    shell_integration = ShellIntegration(
        # Parent (HubIntegration) fields
        type="shell",
        name=request.name,
        display_name=request.display_name,
        is_active=True,
        tenant_id=ctx.tenant_id,
        health_status="unknown",
        # Child (ShellIntegration) fields
        api_key_hash=hashed_key,
        poll_interval=request.poll_interval,
        mode=request.mode,
        allowed_commands=request.allowed_commands or [],
        allowed_paths=request.allowed_paths or [],
        retention_days=request.retention_days,
        yolo_mode=request.yolo_mode
    )
    db.add(shell_integration)
    db.commit()
    db.refresh(shell_integration)

    logger.info(f"Created shell integration {shell_integration.id} for tenant {ctx.tenant_id}")

    return ShellIntegrationCreateResponse(
        id=shell_integration.id,
        name=request.name,
        api_key=plaintext_key,
        message="Integration created. SAVE THE API KEY - it cannot be retrieved later!"
    )


@router.get("/integrations/{integration_id}", response_model=ShellIntegrationResponse)
async def get_shell_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get details of a specific shell integration.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    return ShellIntegrationResponse(
        id=integration.id,
        name=integration.name,
        display_name=integration.display_name,
        type=integration.type,
        is_active=integration.is_active,
        health_status=integration.health_status,
        tenant_id=integration.tenant_id,
        poll_interval=integration.poll_interval,
        mode=integration.mode,
        hostname=integration.hostname,
        remote_ip=integration.remote_ip,
        os_info=integration.os_info,
        last_checkin=integration.last_checkin.isoformat() if integration.last_checkin else None,
        is_online=integration.is_online,
        allowed_commands=integration.allowed_commands or [],
        allowed_paths=integration.allowed_paths or [],
        retention_days=integration.retention_days,
        registered_at=integration.registered_at.isoformat() if integration.registered_at else None,
        created_at=integration.created_at.isoformat() if integration.created_at else "",
        yolo_mode=integration.yolo_mode
    )


@router.patch("/integrations/{integration_id}", response_model=ShellIntegrationResponse)
async def update_shell_integration(
    integration_id: int,
    request: ShellIntegrationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update a shell integration.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    # Update fields
    if request.name is not None:
        integration.name = request.name
    if request.display_name is not None:
        integration.display_name = request.display_name
    if request.is_active is not None:
        integration.is_active = request.is_active
    if request.poll_interval is not None:
        integration.poll_interval = request.poll_interval
    if request.mode is not None:
        integration.mode = request.mode
    if request.allowed_commands is not None:
        integration.allowed_commands = request.allowed_commands
    if request.allowed_paths is not None:
        integration.allowed_paths = request.allowed_paths
    if request.retention_days is not None:
        integration.retention_days = request.retention_days
    if request.yolo_mode is not None:
        integration.yolo_mode = request.yolo_mode

    db.commit()
    db.refresh(integration)

    return ShellIntegrationResponse(
        id=integration.id,
        name=integration.name,
        display_name=integration.display_name,
        type=integration.type,
        is_active=integration.is_active,
        health_status=integration.health_status,
        tenant_id=integration.tenant_id,
        poll_interval=integration.poll_interval,
        mode=integration.mode,
        hostname=integration.hostname,
        remote_ip=integration.remote_ip,
        os_info=integration.os_info,
        last_checkin=integration.last_checkin.isoformat() if integration.last_checkin else None,
        is_online=integration.is_online,
        allowed_commands=integration.allowed_commands or [],
        allowed_paths=integration.allowed_paths or [],
        retention_days=integration.retention_days,
        registered_at=integration.registered_at.isoformat() if integration.registered_at else None,
        created_at=integration.created_at.isoformat() if integration.created_at else "",
        yolo_mode=integration.yolo_mode
    )


@router.delete("/integrations/{integration_id}")
async def delete_shell_integration(
    integration_id: int,
    graceful: bool = Query(True, description="Send shutdown command before deleting (default: true)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete a shell integration (and all associated commands).

    By default, sends a graceful shutdown command to stop the beacon process
    before deleting the integration. Use graceful=false to skip this.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    shutdown_sent = False

    # If beacon is online and graceful shutdown is requested, queue shutdown + persistence uninstall
    if graceful and integration.is_online:
        # First uninstall persistence so beacon doesn't restart
        uninstall_cmd = ShellCommand(
            id=str(uuid.uuid4()),
            shell_id=integration_id,
            tenant_id=ctx.tenant_id,
            commands=["__beacon_persistence_uninstall__"],
            initiated_by=f"system:delete",
            status="queued",
            timeout_seconds=30
        )
        db.add(uninstall_cmd)

        # Then shutdown the beacon
        shutdown_cmd = ShellCommand(
            id=str(uuid.uuid4()),
            shell_id=integration_id,
            tenant_id=ctx.tenant_id,
            commands=["__beacon_shutdown__"],
            initiated_by=f"system:delete",
            status="queued",
            timeout_seconds=30
        )
        db.add(shutdown_cmd)
        db.commit()
        shutdown_sent = True
        logger.info(f"Queued persistence uninstall and shutdown for shell {integration_id} before deletion")

    # Delete associated commands first (no cascade configured on relationship)
    # Use no_autoflush to prevent SQLAlchemy from trying to set shell_id=NULL
    with db.no_autoflush:
        db.query(ShellCommand).filter(ShellCommand.shell_id == integration_id).delete(synchronize_session='fetch')

        # Delete shell_integration (child in joined table inheritance)
        db.delete(integration)

        # Also delete the hub_integration base (parent table in joined inheritance)
        hub = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
        if hub:
            db.delete(hub)

    db.commit()

    logger.info(f"Deleted shell integration {integration_id}")

    message = "Integration deleted successfully"
    if shutdown_sent:
        message += " (shutdown command sent to beacon)"

    return {"message": message, "shutdown_sent": shutdown_sent}


@router.post("/integrations/{integration_id}/regenerate-key", response_model=ShellIntegrationCreateResponse)
async def regenerate_api_key(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Regenerate the API key for a shell integration.

    The old key will be immediately invalidated.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    # Generate new key
    plaintext_key, hashed_key = generate_api_key()
    integration.api_key_hash = hashed_key

    db.commit()

    logger.info(f"Regenerated API key for shell integration {integration_id}")

    return ShellIntegrationCreateResponse(
        id=integration.id,
        name=integration.name,
        api_key=plaintext_key,
        message="API key regenerated. SAVE THE NEW KEY - it cannot be retrieved later!"
    )


@router.post("/integrations/{integration_id}/persistence")
async def toggle_persistence(
    integration_id: int,
    action: str = Query(..., pattern="^(install|uninstall|status)$", description="Action: install, uninstall, or status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Control beacon persistence (auto-start on reboot).

    Sends a system command to the beacon to install/uninstall persistence
    or check its status.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    if not integration.is_active:
        raise HTTPException(status_code=400, detail="Integration is not active")

    if not integration.is_online:
        raise HTTPException(status_code=400, detail="Beacon is offline - cannot send persistence command")

    # Map action to system command
    system_commands = {
        "install": "__beacon_persistence_install__",
        "uninstall": "__beacon_persistence_uninstall__",
        "status": "__beacon_persistence_status__"
    }

    # Queue the system command
    command = ShellCommand(
        id=str(uuid.uuid4()),
        shell_id=integration_id,
        tenant_id=ctx.tenant_id,
        commands=[system_commands[action]],
        initiated_by=f"user:{current_user.email}",
        status="queued",
        timeout_seconds=120
    )

    db.add(command)
    db.commit()
    db.refresh(command)

    logger.info(f"Queued persistence {action} command {command.id} for shell {integration_id}")

    return {
        "message": f"Persistence {action} command queued",
        "command_id": command.id,
        "action": action
    }


@router.post("/integrations/{integration_id}/shutdown")
async def shutdown_beacon(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Send a graceful shutdown command to the beacon.

    The beacon will stop its polling loop and exit cleanly.
    Note: If persistence is installed, the beacon will restart on next login/reboot.
    """
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    if not integration.is_online:
        raise HTTPException(status_code=400, detail="Beacon is offline - nothing to shutdown")

    # Queue the shutdown command
    command = ShellCommand(
        id=str(uuid.uuid4()),
        shell_id=integration_id,
        tenant_id=ctx.tenant_id,
        commands=["__beacon_shutdown__"],
        initiated_by=f"user:{current_user.email}",
        status="queued",
        timeout_seconds=30
    )

    db.add(command)
    db.commit()
    db.refresh(command)

    logger.info(f"Queued shutdown command {command.id} for shell {integration_id}")

    return {
        "message": "Shutdown command queued - beacon will stop on next check-in",
        "command_id": command.id
    }


# ============================================================================
# Beacon Endpoints (Authenticated via API Key)
# ============================================================================

@router.post("/register")
async def beacon_register(
    request: BeaconRegistrationRequest,
    http_request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Register a beacon (first-time connection).

    Called by the beacon client on startup to register with the backend.
    Requires valid API key in X-API-Key header.
    """
    integration = verify_beacon_api_key(x_api_key, db)

    if not integration:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Get client IP
    client_ip = http_request.client.host if http_request.client else None

    # Update registration info
    integration.hostname = request.hostname
    integration.os_info = request.os_info
    integration.remote_ip = client_ip
    integration.registered_at = datetime.utcnow()
    integration.last_checkin = datetime.utcnow()
    integration.health_status = "healthy"

    db.commit()

    logger.info(f"Beacon registered: {request.hostname} (integration {integration.id})")

    return {
        "status": "registered",
        "integration_id": integration.id,
        "poll_interval": integration.poll_interval,
        "mode": integration.mode
    }


@router.post("/checkin", response_model=BeaconCheckinResponse)
async def beacon_checkin(
    request: BeaconCheckinRequest,
    http_request: Request,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Beacon check-in (heartbeat + fetch pending commands).

    Called periodically by the beacon to:
    1. Update last_checkin timestamp
    2. Optionally update hostname/os_info
    3. Fetch pending commands

    FIX (2026-01-30): Use a fresh session from db._global_engine to ensure
    we see commands committed by the shell_command_service. The routes_shell.py
    _engine and db._global_engine should be the same, but using the same module
    ensures consistency.
    """
    integration = verify_beacon_api_key(x_api_key, db)

    if not integration:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Update checkin info
    integration.last_checkin = datetime.utcnow()
    integration.health_status = "healthy"

    if request.hostname:
        integration.hostname = request.hostname
    if request.os_info:
        integration.os_info = request.os_info

    # Get client IP
    client_ip = http_request.client.host if http_request.client else None
    if client_ip:
        integration.remote_ip = client_ip

    # FIX: Commit the checkin update BEFORE expire_all()
    # Otherwise expire_all() will cause the integration to be reloaded
    # from DB when accessed, discarding the pending changes.
    shell_id = integration.id  # Store ID before commit to use in logs
    db.commit()

    # FIX (2026-01-30): Use a FRESH session from db._global_engine to query commands
    # This ensures we're using the exact same engine as shell_command_service.py
    # and guarantees we see the committed commands
    from sqlalchemy.orm import sessionmaker
    import db as db_module

    logger.debug(f"[BEACON-DEBUG] beacon_checkin: shell_id={shell_id}")
    logger.debug(f"[BEACON-DEBUG] routes_shell._engine = {_engine}")
    logger.debug(f"[BEACON-DEBUG] db._global_engine = {db_module._global_engine}")

    if db_module._global_engine:
        # Use fresh session from the global engine for querying commands
        FreshSession = sessionmaker(bind=db_module._global_engine)
        fresh_db = FreshSession()
        try:
            pending = fresh_db.query(ShellCommand).filter(
                ShellCommand.shell_id == shell_id,
                ShellCommand.status == "queued"
            ).order_by(ShellCommand.queued_at).all()

            logger.debug(f"[BEACON-DEBUG] shell_id={shell_id} found {len(pending)} queued commands (fresh session)")

            if pending:
                logger.debug(f"[BEACON-DEBUG] commands: {[p.id for p in pending]}")
            else:
                # Check if there are any commands at all for this shell
                all_commands = fresh_db.query(ShellCommand).filter(
                    ShellCommand.shell_id == shell_id
                ).order_by(ShellCommand.queued_at.desc()).limit(3).all()
                if all_commands:
                    logger.debug(f"[BEACON-DEBUG] no queued, recent: {[(c.id[:8], c.status) for c in all_commands]}")

            # Mark commands as sent using fresh session
            pending_commands = []
            for cmd in pending:
                cmd.status = "sent"
                cmd.sent_at = datetime.utcnow()
                pending_commands.append({
                    "id": cmd.id,
                    "commands": cmd.commands,
                    "timeout": cmd.timeout_seconds
                })

            fresh_db.commit()
        finally:
            fresh_db.close()
    else:
        # Fallback to original session with expire_all
        logger.debug(f"[BEACON-DEBUG] FALLBACK: db._global_engine is None, using original session")
        db.expire_all()

        pending = db.query(ShellCommand).filter(
            ShellCommand.shell_id == shell_id,
            ShellCommand.status == "queued"
        ).order_by(ShellCommand.queued_at).all()

        if pending:
            logger.debug(f"[BEACON-DEBUG] shell_id={shell_id} found {len(pending)} queued commands (fallback)")
        else:
            all_commands = db.query(ShellCommand).filter(
                ShellCommand.shell_id == shell_id
            ).order_by(ShellCommand.queued_at.desc()).limit(3).all()
            if all_commands:
                logger.debug(f"[BEACON-DEBUG] no queued, recent: {[(c.id[:8], c.status) for c in all_commands]}")

        # Mark commands as sent
        pending_commands = []
        for cmd in pending:
            cmd.status = "sent"
            cmd.sent_at = datetime.utcnow()
            pending_commands.append({
                "id": cmd.id,
                "commands": cmd.commands,
                "timeout": cmd.timeout_seconds
            })

        db.commit()

    return BeaconCheckinResponse(
        status="ok",
        poll_interval=integration.poll_interval,
        pending_commands=pending_commands
    )


@router.post("/result")
async def beacon_report_result(
    request: CommandResultRequest,
    x_api_key: str = Header(..., alias="X-API-Key"),
    db: Session = Depends(get_db)
):
    """
    Beacon reports command execution result.

    Called by the beacon after executing a command to report results.
    """
    integration = verify_beacon_api_key(x_api_key, db)

    if not integration:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Find the command
    command = db.query(ShellCommand).filter(
        ShellCommand.id == request.command_id,
        ShellCommand.shell_id == integration.id
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    # Update command with results
    command.status = "completed" if request.exit_code == 0 else "failed"
    command.completed_at = datetime.utcnow()
    command.exit_code = request.exit_code
    command.stdout = request.stdout
    command.stderr = request.stderr
    command.execution_time_ms = request.execution_time_ms
    command.final_working_dir = request.final_working_dir
    command.full_result_json = request.full_result_json
    command.error_message = request.error_message

    db.commit()

    logger.info(f"Command {request.command_id} completed with exit code {request.exit_code}")

    return {"status": "recorded"}


# ============================================================================
# Command Queue Endpoints (Admin)
# ============================================================================

@router.get("/commands", response_model=List[CommandResponse])
async def list_commands(
    shell_id: Optional[int] = Query(None, description="Filter by shell integration"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List shell commands.
    """
    query = db.query(ShellCommand)
    query = ctx.filter_by_tenant(query, ShellCommand.tenant_id)

    if shell_id:
        query = query.filter(ShellCommand.shell_id == shell_id)
    if status:
        query = query.filter(ShellCommand.status == status)

    commands = query.order_by(ShellCommand.queued_at.desc()).limit(limit).all()

    return [
        CommandResponse(
            id=cmd.id,
            shell_id=cmd.shell_id,
            tenant_id=cmd.tenant_id,
            commands=cmd.commands,
            initiated_by=cmd.initiated_by,
            status=cmd.status,
            queued_at=cmd.queued_at.isoformat(),
            sent_at=cmd.sent_at.isoformat() if cmd.sent_at else None,
            completed_at=cmd.completed_at.isoformat() if cmd.completed_at else None,
            exit_code=cmd.exit_code,
            stdout=cmd.stdout,
            stderr=cmd.stderr,
            execution_time_ms=cmd.execution_time_ms,
            error_message=cmd.error_message
        )
        for cmd in commands
    ]


@router.post("/commands/{shell_id}")
async def queue_command(
    shell_id: int,
    request: CommandQueueRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required),
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("shell.write"))
):
    """
    Queue a command for execution on a shell integration.

    SECURITY (CRIT-005): Commands are validated against security policies:
    - Blocked patterns return HTTP 403
    - High-risk patterns return HTTP 202 (pending approval) unless YOLO mode
    - Safe commands return HTTP 200 (queued)
    """
    from fastapi.responses import JSONResponse
    from services.shell_security_service import get_security_service

    # Verify integration exists and user has access
    integration = db.query(ShellIntegration).filter(
        ShellIntegration.id == shell_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    verify_integration_access(integration, ctx)

    if not integration.is_active:
        raise HTTPException(status_code=400, detail="Integration is not active")

    # =========================================================================
    # SECURITY CHECK (CRIT-005 Fix)
    # =========================================================================
    security_service = get_security_service()

    # Check all commands against patterns
    all_allowed, security_result = security_service.check_commands(
        commands=request.commands,
        allowed_commands=integration.allowed_commands or None,
        allowed_paths=integration.allowed_paths or None,
        require_approval_for_high_risk=True
    )

    if not all_allowed:
        # Log blocked command for audit
        blocked_cmd = ShellCommand(
            id=str(uuid.uuid4()),
            shell_id=shell_id,
            tenant_id=ctx.tenant_id,
            commands=request.commands,
            initiated_by=f"user:{current_user.email}",
            status="blocked",
            error_message=security_result.blocked_reason,
            timeout_seconds=request.timeout_seconds
        )
        blocked_cmd.completed_at = datetime.utcnow()
        db.add(blocked_cmd)
        db.commit()

        logger.warning(
            f"Command blocked: {security_result.blocked_reason} "
            f"(user={current_user.email}, shell={shell_id})"
        )

        raise HTTPException(
            status_code=403,
            detail={
                "error": "Command blocked by security policy",
                "reason": security_result.blocked_reason,
                "risk_level": security_result.risk_level.value,
                "command_id": blocked_cmd.id
            }
        )

    # Check if approval required
    if security_result.requires_approval:
        # Check YOLO mode
        if integration.yolo_mode:
            logger.warning(
                f"YOLO MODE: Auto-approving high-risk command via API "
                f"(user={current_user.email}, shell={shell_id})"
            )
            # Continue to create command normally
        else:
            # Create command in pending_approval status
            command = ShellCommand(
                id=str(uuid.uuid4()),
                shell_id=shell_id,
                tenant_id=ctx.tenant_id,
                commands=request.commands,
                initiated_by=f"user:{current_user.email}",
                status="pending_approval",
                approval_required=True,
                timeout_seconds=request.timeout_seconds
            )

            db.add(command)
            db.commit()
            db.refresh(command)

            logger.info(
                f"Command {command.id} requires approval "
                f"(risk={security_result.risk_level.value})"
            )

            # Return 202 Accepted with approval info
            return JSONResponse(
                status_code=202,
                content={
                    "id": command.id,
                    "status": "pending_approval",
                    "message": "Command requires admin approval",
                    "risk_level": security_result.risk_level.value,
                    "security_warnings": security_result.warnings,
                    "approval_url": f"/api/shell/approvals/{command.id}"
                }
            )
    # =========================================================================
    # END SECURITY CHECK
    # =========================================================================

    # Create command (passed security check)
    command = ShellCommand(
        id=str(uuid.uuid4()),
        shell_id=shell_id,
        tenant_id=ctx.tenant_id,
        commands=request.commands,
        initiated_by=f"user:{current_user.email}",
        status="queued",
        timeout_seconds=request.timeout_seconds
    )

    db.add(command)
    db.commit()
    db.refresh(command)

    logger.info(f"Command {command.id} queued for shell {shell_id}")

    return CommandResponse(
        id=command.id,
        shell_id=command.shell_id,
        tenant_id=command.tenant_id,
        commands=command.commands,
        initiated_by=command.initiated_by,
        status=command.status,
        queued_at=command.queued_at.isoformat(),
        sent_at=None,
        completed_at=None,
        exit_code=None,
        stdout=None,
        stderr=None,
        execution_time_ms=None,
        error_message=None
    )


@router.get("/commands/{command_id}", response_model=CommandResponse)
async def get_command(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get details of a specific command.
    """
    command = db.query(ShellCommand).filter(
        ShellCommand.id == command_id
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if not ctx.can_access_resource(command.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return CommandResponse(
        id=command.id,
        shell_id=command.shell_id,
        tenant_id=command.tenant_id,
        commands=command.commands,
        initiated_by=command.initiated_by,
        status=command.status,
        queued_at=command.queued_at.isoformat(),
        sent_at=command.sent_at.isoformat() if command.sent_at else None,
        completed_at=command.completed_at.isoformat() if command.completed_at else None,
        exit_code=command.exit_code,
        stdout=command.stdout,
        stderr=command.stderr,
        execution_time_ms=command.execution_time_ms,
        error_message=command.error_message
    )


# ============================================================================
# Beacon Version & Update Endpoints
# ============================================================================

# Current beacon version (update when releasing new versions)
BEACON_VERSION = "1.0.0"


class BeaconVersionResponse(BaseModel):
    """Response model for beacon version check."""
    version: str
    download_url: Optional[str] = None
    checksum: Optional[str] = None
    checksum_algorithm: str = "sha256"
    release_notes: str = ""
    size_bytes: int = 0


@router.get("/beacon/version", response_model=BeaconVersionResponse)
async def get_beacon_version():
    """
    Get the latest beacon version info for auto-update.

    Beacons call this endpoint on startup and periodically to check for updates.
    """
    import os
    import hashlib
    from pathlib import Path

    # Path to beacon package (for serving updates)
    beacon_dir = Path(__file__).parent.parent / "shell_beacon"
    beacon_file = beacon_dir / "beacon.py"

    # Calculate checksum if file exists
    checksum = None
    size_bytes = 0

    if beacon_file.exists():
        size_bytes = beacon_file.stat().st_size
        sha256 = hashlib.sha256()
        with open(beacon_file, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        checksum = f"sha256:{sha256.hexdigest()}"

    return BeaconVersionResponse(
        version=BEACON_VERSION,
        download_url="/api/shell/beacon/download",
        checksum=checksum,
        checksum_algorithm="sha256",
        release_notes="Shell Beacon v1.0.0 - Initial release with HTTP polling, stacked execution, and auto-update support.",
        size_bytes=size_bytes
    )


@router.get("/beacon/download")
async def download_beacon():
    """
    Download the latest beacon package as a zip file.

    Returns the shell_beacon package for installation on remote hosts.
    """
    import io
    import zipfile
    from pathlib import Path
    from fastapi.responses import StreamingResponse

    beacon_dir = Path(__file__).parent.parent / "shell_beacon"

    if not beacon_dir.exists():
        raise HTTPException(status_code=404, detail="Beacon package not found")

    # Create zip in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in beacon_dir.glob("*.py"):
            arcname = f"shell_beacon/{file_path.name}"
            zf.write(file_path, arcname)

        # Include requirements.txt
        req_file = beacon_dir / "requirements.txt"
        if req_file.exists():
            zf.write(req_file, "shell_beacon/requirements.txt")

        # Include README.md
        readme_file = beacon_dir / "README.md"
        if readme_file.exists():
            zf.write(readme_file, "shell_beacon/README.md")

    zip_buffer.seek(0)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=tsushin_beacon_{BEACON_VERSION}.zip"
        }
    )


@router.delete("/commands/{command_id}")
async def cancel_command(
    command_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Cancel a queued command.

    Only works for commands in 'queued' status.
    """
    command = db.query(ShellCommand).filter(
        ShellCommand.id == command_id
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if not ctx.can_access_resource(command.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if command.status != "queued":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel command in '{command.status}' status"
        )

    command.status = "cancelled"
    command.completed_at = datetime.utcnow()
    command.error_message = f"Cancelled by {current_user.email}"

    db.commit()

    return {"message": "Command cancelled"}


# ============================================================================
# Phase 19: Security Pattern Management
# ============================================================================

class SecurityPatternResponse(BaseModel):
    """Response model for security pattern."""
    id: int
    tenant_id: Optional[str]
    pattern: str
    pattern_type: str
    risk_level: Optional[str]
    description: str
    category: Optional[str]
    is_system_default: bool
    is_active: bool
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class SecurityPatternCreate(BaseModel):
    """Request model for creating a security pattern."""
    pattern: str = Field(..., min_length=1, max_length=500)
    pattern_type: str = Field(..., pattern="^(blocked|high_risk)$")
    risk_level: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    description: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=50)
    is_active: bool = True


class SecurityPatternUpdate(BaseModel):
    """Request model for updating a security pattern."""
    pattern: Optional[str] = Field(None, min_length=1, max_length=500)
    pattern_type: Optional[str] = Field(None, pattern="^(blocked|high_risk)$")
    risk_level: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    description: Optional[str] = Field(None, min_length=1, max_length=255)
    category: Optional[str] = None
    is_active: Optional[bool] = None


class PatternTestRequest(BaseModel):
    """Request model for testing a pattern."""
    pattern: str
    test_commands: List[str]


class PatternTestResponse(BaseModel):
    """Response model for pattern test."""
    pattern: str
    is_valid: bool
    error: Optional[str]
    matches: List[dict]


def _pattern_to_response(pattern) -> dict:
    """Convert ShellSecurityPattern to response dict."""
    return {
        "id": pattern.id,
        "tenant_id": pattern.tenant_id,
        "pattern": pattern.pattern,
        "pattern_type": pattern.pattern_type,
        "risk_level": pattern.risk_level,
        "description": pattern.description,
        "category": pattern.category,
        "is_system_default": pattern.is_system_default,
        "is_active": pattern.is_active,
        "created_at": pattern.created_at.isoformat() if pattern.created_at else None,
        "updated_at": pattern.updated_at.isoformat() if pattern.updated_at else None,
    }


@router.get("/security-patterns", response_model=List[SecurityPatternResponse])
async def list_security_patterns(
    pattern_type: Optional[str] = Query(None, pattern="^(blocked|high_risk)$"),
    category: Optional[str] = Query(None),
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all security patterns (system defaults + tenant-specific).

    Returns patterns where:
    - tenant_id is NULL (system defaults), OR
    - tenant_id matches the current user's tenant
    """
    from models import ShellSecurityPattern
    from sqlalchemy import or_

    query = db.query(ShellSecurityPattern)

    # Filter: system defaults (NULL tenant_id) + tenant patterns
    query = query.filter(
        or_(
            ShellSecurityPattern.tenant_id.is_(None),
            ShellSecurityPattern.tenant_id == ctx.tenant_id
        )
    )

    if pattern_type:
        query = query.filter(ShellSecurityPattern.pattern_type == pattern_type)
    if category:
        query = query.filter(ShellSecurityPattern.category == category)
    if not include_inactive:
        query = query.filter(ShellSecurityPattern.is_active == True)

    patterns = query.order_by(
        ShellSecurityPattern.is_system_default.desc(),
        ShellSecurityPattern.pattern_type,
        ShellSecurityPattern.category,
        ShellSecurityPattern.created_at
    ).all()

    return [_pattern_to_response(p) for p in patterns]


@router.post("/security-patterns", response_model=SecurityPatternResponse)
async def create_security_pattern(
    request: SecurityPatternCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create a new tenant-specific security pattern.

    System default patterns cannot be created via API.
    """
    import re
    from models import ShellSecurityPattern
    from sqlalchemy import or_
    from services.shell_security_service import get_security_service

    # Validate regex
    try:
        re.compile(request.pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    # Check for duplicate pattern in tenant or system
    existing = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.pattern == request.pattern,
        or_(
            ShellSecurityPattern.tenant_id.is_(None),
            ShellSecurityPattern.tenant_id == ctx.tenant_id
        )
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Pattern already exists")

    # Validate risk_level for high_risk patterns
    risk_level = request.risk_level
    if request.pattern_type == 'high_risk' and not risk_level:
        risk_level = 'high'  # Default
    elif request.pattern_type == 'blocked':
        risk_level = 'critical'  # Blocked patterns are always critical

    pattern = ShellSecurityPattern(
        tenant_id=ctx.tenant_id,
        pattern=request.pattern,
        pattern_type=request.pattern_type,
        risk_level=risk_level,
        description=request.description,
        category=request.category,
        is_system_default=False,
        is_active=request.is_active,
        created_by=current_user.id
    )

    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    # Invalidate cache
    get_security_service().invalidate_cache(ctx.tenant_id)

    logger.info(f"Created security pattern {pattern.id} by user {current_user.email}")

    return _pattern_to_response(pattern)


@router.patch("/security-patterns/{pattern_id}", response_model=SecurityPatternResponse)
async def update_security_pattern(
    pattern_id: int,
    request: SecurityPatternUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update a security pattern.

    System default patterns can only have is_active toggled.
    Tenant patterns can be fully modified.
    """
    import re
    from models import ShellSecurityPattern
    from services.shell_security_service import get_security_service

    pattern = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.id == pattern_id
    ).first()

    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    # System defaults can only have is_active toggled
    if pattern.is_system_default:
        if request.is_active is not None:
            pattern.is_active = request.is_active
            pattern.updated_by = current_user.id
            db.commit()
            db.refresh(pattern)

            # Invalidate cache
            get_security_service().invalidate_cache(ctx.tenant_id)

            logger.info(f"Toggled system pattern {pattern_id} active={request.is_active} by {current_user.email}")
            return _pattern_to_response(pattern)
        else:
            raise HTTPException(
                status_code=403,
                detail="System default patterns can only be activated/deactivated, not modified"
            )

    # Tenant patterns - check access
    if not ctx.can_access_resource(pattern.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Apply updates
    if request.pattern is not None:
        try:
            re.compile(request.pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {str(e)}")
        pattern.pattern = request.pattern

    if request.pattern_type is not None:
        pattern.pattern_type = request.pattern_type

    if request.risk_level is not None:
        pattern.risk_level = request.risk_level

    if request.description is not None:
        pattern.description = request.description

    if request.category is not None:
        pattern.category = request.category

    if request.is_active is not None:
        pattern.is_active = request.is_active

    pattern.updated_by = current_user.id

    db.commit()
    db.refresh(pattern)

    # Invalidate cache
    get_security_service().invalidate_cache(ctx.tenant_id)

    logger.info(f"Updated security pattern {pattern_id} by {current_user.email}")

    return _pattern_to_response(pattern)


@router.delete("/security-patterns/{pattern_id}")
async def delete_security_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete a tenant-specific security pattern.

    System default patterns cannot be deleted, only deactivated.
    """
    from models import ShellSecurityPattern
    from services.shell_security_service import get_security_service

    pattern = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.id == pattern_id
    ).first()

    if not pattern:
        raise HTTPException(status_code=404, detail="Pattern not found")

    if pattern.is_system_default:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system default patterns. Use PATCH to deactivate instead."
        )

    if not ctx.can_access_resource(pattern.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    db.delete(pattern)
    db.commit()

    # Invalidate cache
    get_security_service().invalidate_cache(ctx.tenant_id)

    logger.info(f"Deleted security pattern {pattern_id} by {current_user.email}")

    return {"message": "Pattern deleted successfully"}


@router.post("/security-patterns/test", response_model=PatternTestResponse)
async def test_security_pattern(
    request: PatternTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Test a regex pattern against sample commands.

    Returns which commands match the pattern.
    """
    import re

    # Validate pattern
    try:
        compiled = re.compile(request.pattern, re.IGNORECASE)
    except re.error as e:
        return PatternTestResponse(
            pattern=request.pattern,
            is_valid=False,
            error=str(e),
            matches=[]
        )

    matches = []
    for cmd in request.test_commands:
        match = compiled.search(cmd)
        matches.append({
            "command": cmd,
            "matched": bool(match),
            "match_text": match.group(0) if match else None
        })

    return PatternTestResponse(
        pattern=request.pattern,
        is_valid=True,
        error=None,
        matches=matches
    )


@router.get("/security-patterns/stats")
async def get_security_pattern_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get statistics about security patterns.
    """
    from services.shell_pattern_seeding import get_seeding_stats
    from services.shell_security_service import get_security_service

    stats = get_seeding_stats(db)
    cache_stats = get_security_service().get_cache_stats()

    return {
        "patterns": stats,
        "cache": cache_stats
    }
