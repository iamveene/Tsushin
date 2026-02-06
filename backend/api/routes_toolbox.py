"""
Toolbox Container API Routes
Phase: Custom Tools Hub Integration

Provides REST API endpoints for managing per-tenant toolbox containers.
Handles container lifecycle, command execution, package installation, and image commits.
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db import get_db
from models_rbac import User
from services.toolbox_container_service import get_toolbox_service, ToolboxContainerService
from services.tool_discovery_service import get_tool_discovery_service, ToolManifestError
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/toolbox",
    tags=["Toolbox"],
    redirect_slashes=False
)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class ContainerStatusResponse(BaseModel):
    """Response schema for container status"""
    tenant_id: str
    container_name: str
    status: str  # 'running', 'stopped', 'not_created', 'error'
    container_id: Optional[str]
    image: Optional[str]
    created_at: Optional[str]
    started_at: Optional[str]
    health: str
    error: Optional[str]


class CommandExecuteRequest(BaseModel):
    """Request schema for command execution"""
    command: str = Field(..., description="Command to execute in the container")
    timeout: Optional[int] = Field(default=300, description="Execution timeout in seconds")
    workdir: Optional[str] = Field(default="/workspace", description="Working directory")
    # BUG-004 Fix: Allow global admins to specify tenant_id explicitly
    tenant_id: Optional[str] = Field(default=None, description="Tenant ID override (for global admins)")

    class Config:
        json_schema_extra = {
            "example": {
                "command": "nmap -sV localhost",
                "timeout": 60,
                "workdir": "/workspace",
                "tenant_id": "acme"
            }
        }


class CommandExecuteResponse(BaseModel):
    """Response schema for command execution"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time_ms: int
    command: str
    tenant_id: str


class PackageInstallRequest(BaseModel):
    """Request schema for package installation"""
    package_name: str = Field(..., description="Package name to install")
    package_type: str = Field(..., pattern="^(pip|apt)$", description="Package type: 'pip' or 'apt'")

    class Config:
        json_schema_extra = {
            "example": {
                "package_name": "requests",
                "package_type": "pip"
            }
        }


class PackageResponse(BaseModel):
    """Response schema for package info"""
    id: int
    package_name: str
    package_type: str
    version: Optional[str]
    installed_at: Optional[str]
    is_committed: bool


class CommitResponse(BaseModel):
    """Response schema for container commit"""
    success: bool
    image_tag: str
    image_id: str
    committed_at: str


class ResetResponse(BaseModel):
    """Response schema for reset to base"""
    success: bool
    message: str
    container_status: ContainerStatusResponse


class ToolSyncInfo(BaseModel):
    """Info about a synced tool"""
    name: str
    id: int
    file: str


class ToolSyncError(BaseModel):
    """Info about a sync error"""
    file: str
    error: str


class ToolSyncResponse(BaseModel):
    """Response schema for tool manifest sync"""
    created: List[ToolSyncInfo]
    updated: List[ToolSyncInfo]
    unchanged: List[ToolSyncInfo]
    errors: List[ToolSyncError]
    total_manifests: int
    sync_time: str


# ============================================================================
# Container Lifecycle Endpoints
# ============================================================================

@router.get("/status", response_model=ContainerStatusResponse)
async def get_container_status(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Get toolbox container status for current tenant

    **Permissions Required:** None (authenticated user)

    Returns current container status including health state.
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        status = service.get_container_status(ctx.tenant_id)
        return ContainerStatusResponse(**status)
    except Exception as e:
        logger.error(f"Failed to get container status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start", response_model=ContainerStatusResponse)
async def start_container(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Start toolbox container for current tenant

    **Permissions Required:** `tools.manage`

    Creates the container if it doesn't exist.
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        status = service.start_container(ctx.tenant_id, db)
        logger.info(f"Toolbox container started for tenant {ctx.tenant_id}")
        return ContainerStatusResponse(**status)
    except RuntimeError as e:
        logger.error(f"Failed to start container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=ContainerStatusResponse)
async def stop_container(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Stop toolbox container for current tenant

    **Permissions Required:** `tools.manage`
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        status = service.stop_container(ctx.tenant_id, db)
        logger.info(f"Toolbox container stopped for tenant {ctx.tenant_id}")
        return ContainerStatusResponse(**status)
    except RuntimeError as e:
        logger.error(f"Failed to stop container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart", response_model=ContainerStatusResponse)
async def restart_container(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Restart toolbox container for current tenant

    **Permissions Required:** `tools.manage`
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        status = service.restart_container(ctx.tenant_id, db)
        logger.info(f"Toolbox container restarted for tenant {ctx.tenant_id}")
        return ContainerStatusResponse(**status)
    except RuntimeError as e:
        logger.error(f"Failed to restart container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Command Execution Endpoints
# ============================================================================

@router.post("/execute", response_model=CommandExecuteResponse)
async def execute_command(
    request: CommandExecuteRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.execute")),
    db: Session = Depends(get_db)
):
    """
    Execute command in toolbox container

    **Permissions Required:** `tools.execute`

    Runs a shell command in the tenant's toolbox container.
    Container will be started automatically if not running.

    BUG-004 Fix: Global admins can specify tenant_id in the request body
    to execute commands in any tenant's container.
    """
    # BUG-004 Fix: Determine effective tenant_id
    effective_tenant_id = ctx.tenant_id

    if not effective_tenant_id:
        # Global admin without tenant_id - check if request specifies one
        if ctx.is_global_admin and request.tenant_id:
            effective_tenant_id = request.tenant_id
            logger.info(f"Global admin using tenant_id override: {effective_tenant_id}")
        else:
            raise HTTPException(
                status_code=400,
                detail="Tenant context required. Global admins must specify tenant_id in request body."
            )

    try:
        service = get_toolbox_service()

        # Ensure container is running
        service.ensure_container_running(effective_tenant_id, db)

        # Execute command
        result = await service.execute_command(
            tenant_id=effective_tenant_id,
            command=request.command,
            timeout=request.timeout,
            workdir=request.workdir,
            db=db
        )

        logger.info(f"Command executed for tenant {effective_tenant_id}: exit_code={result['exit_code']}")
        return CommandExecuteResponse(**result)

    except RuntimeError as e:
        logger.error(f"Command execution failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Package Management Endpoints
# ============================================================================

@router.get("/packages", response_model=List[PackageResponse])
async def list_packages(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    List installed packages for current tenant

    **Permissions Required:** None (authenticated user)

    Returns all packages installed in the tenant's toolbox container.
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        packages = service.list_installed_packages(ctx.tenant_id, db)
        return [PackageResponse(**pkg) for pkg in packages]
    except Exception as e:
        logger.error(f"Failed to list packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/packages/install", response_model=CommandExecuteResponse)
async def install_package(
    request: PackageInstallRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Install package in toolbox container

    **Permissions Required:** `tools.manage`

    Installs a pip or apt package in the tenant's container.
    Note: apt packages require special handling (container runs as non-root).
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()

        # Ensure container is running
        service.ensure_container_running(ctx.tenant_id, db)

        # Install package
        result = await service.install_package(
            tenant_id=ctx.tenant_id,
            package_name=request.package_name,
            package_type=request.package_type,
            db=db
        )

        logger.info(f"Package '{request.package_name}' installed for tenant {ctx.tenant_id}")
        return CommandExecuteResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Package installation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Image Management Endpoints
# ============================================================================

@router.post("/commit", response_model=CommitResponse)
async def commit_container(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Commit container state to tenant-specific image

    **Permissions Required:** `tools.manage`

    Saves the current container state (including all installed packages)
    to a tenant-specific Docker image. Future container restarts will use
    this image, preserving all customizations.
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        result = service.commit_container(ctx.tenant_id, db)
        logger.info(f"Container committed for tenant {ctx.tenant_id}: {result['image_tag']}")
        return CommitResponse(**result)
    except RuntimeError as e:
        logger.error(f"Container commit failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset", response_model=ResetResponse)
async def reset_to_base(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Reset container to base image

    **Permissions Required:** `tools.manage`

    Deletes the tenant-specific image and recreates the container from
    the base image. All installed packages will be lost.
    """
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context required")

    try:
        service = get_toolbox_service()
        status = service.reset_to_base(ctx.tenant_id, db)
        logger.info(f"Container reset to base for tenant {ctx.tenant_id}")
        return ResetResponse(
            success=True,
            message="Container reset to base image successfully",
            container_status=ContainerStatusResponse(**status)
        )
    except RuntimeError as e:
        logger.error(f"Container reset failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Utility Endpoints
# ============================================================================

@router.get("/available-tools")
async def list_available_tools(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    List pre-installed tools available in the toolbox

    **Permissions Required:** None (authenticated user)

    Returns list of tools pre-installed in the base toolbox image.
    """
    # These are the tools we install in Dockerfile.toolbox
    tools = [
        {
            "name": "nmap",
            "description": "Network exploration and security auditing",
            "commands": ["nmap -sV <target>", "nmap -sn <network>", "nmap -A <target>"]
        },
        {
            "name": "nuclei",
            "description": "Fast vulnerability scanner based on templates",
            "commands": ["nuclei -u <url>", "nuclei -l urls.txt", "nuclei -u <url> -t cves/"]
        },
        {
            "name": "katana",
            "description": "Fast web crawler for gathering endpoints",
            "commands": ["katana -u <url>", "katana -u <url> -d 3"]
        },
        {
            "name": "httpx",
            "description": "HTTP toolkit for probing web servers",
            "commands": ["httpx -u <url>", "httpx -l urls.txt -sc"]
        },
        {
            "name": "subfinder",
            "description": "Subdomain discovery tool",
            "commands": ["subfinder -d <domain>", "subfinder -dL domains.txt"]
        },
        {
            "name": "python",
            "description": "Python 3.11 interpreter with common packages",
            "commands": ["python script.py", "python -c '<code>'"]
        }
    ]

    return {"tools": tools}


# ============================================================================
# Tool Discovery & Sync Endpoints
# ============================================================================

@router.post("/sync-tools", response_model=ToolSyncResponse)
async def sync_tools_from_manifests(
    ctx: TenantContext = Depends(get_tenant_context),
    _: None = Depends(require_permission("tools.manage")),
    db: Session = Depends(get_db)
):
    """
    Sync custom tools from YAML manifests to database

    **Permissions Required:** `tools.manage`

    Discovers tool manifests in backend/tools/manifests/ directory and syncs
    them to the custom_tools database. Creates new tools, updates existing ones,
    and reports any errors.

    This enables automatic tool registration - just add a YAML manifest file
    and call this endpoint to register the tool.
    """
    try:
        service = get_tool_discovery_service(db)

        # Sync tools (optionally scoped to tenant)
        # For now, we sync to global scope (tenant_id=None)
        # In future, could add parameter to scope to current tenant
        results = service.sync_all_tools(tenant_id=None)

        logger.info(
            f"Tool sync completed: {len(results['created'])} created, "
            f"{len(results['updated'])} updated, {len(results['errors'])} errors"
        )

        return ToolSyncResponse(
            created=[ToolSyncInfo(**t) for t in results["created"]],
            updated=[ToolSyncInfo(**t) for t in results["updated"]],
            unchanged=[ToolSyncInfo(**t) for t in results["unchanged"]],
            errors=[ToolSyncError(**e) for e in results["errors"]],
            total_manifests=results["total_manifests"],
            sync_time=results["sync_time"]
        )

    except Exception as e:
        logger.error(f"Tool sync failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Tool sync failed: {str(e)}")


@router.get("/tool-info/{tool_name}")
async def get_tool_info(
    tool_name: str,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a registered custom tool

    **Permissions Required:** None (authenticated user)

    Returns tool details including all commands and their parameters.
    """
    try:
        service = get_tool_discovery_service(db)
        tool_info = service.get_tool_info(tool_name, tenant_id=None)

        if not tool_info:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

        return tool_info

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get tool info: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
