"""Remote Access (Cloudflare Tunnel) admin REST API — v0.6.0.

Global-admin-only endpoints for configuring the system-wide Cloudflare tunnel,
controlling its lifecycle, and managing per-tenant entitlement.

All routes require ``require_global_admin()``.

Security notes:
- The tunnel token is NEVER returned in any response. GETs expose
  ``tunnel_token_configured: bool`` only.
- Config updates use optimistic concurrency via ``expected_updated_at`` to
  prevent two admins from clobbering each other.
- Every mutation emits an audit event (global + tenant streams for tenant
  entitlement changes).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import get_current_user_required
from db import get_db
from models_rbac import User
from services.cloudflare_tunnel_service import (
    CloudflareTunnelService,
    TunnelConfigurationError,
    get_cloudflare_tunnel_service,
)
from services.remote_access_config_service import (
    ConfigConflictError,
    compute_callbacks,
    get_or_create_config,
    list_tenants_with_entitlement,
    serialize_config,
    set_tenant_entitlement,
    update_config,
)
from services.audit_service import log_admin_action

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/admin/remote-access",
    tags=["remote-access"],
)


# ---------- Auth helper ----------

def require_global_admin(
    current_user: User = Depends(get_current_user_required),
) -> User:
    if not current_user.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Global admin privileges required",
        )
    return current_user


# ---------- Schemas ----------

ALLOWED_MODES = {"quick", "named"}
ALLOWED_PROTOCOLS = {"auto", "http2", "quic"}
HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$"
)


class RemoteAccessConfigOut(BaseModel):
    enabled: bool
    mode: Literal["quick", "named"]
    autostart: bool
    protocol: Literal["auto", "http2", "quic"]
    tunnel_hostname: Optional[str] = None
    tunnel_dns_target: Optional[str] = None
    target_url: str
    tunnel_token_configured: bool
    last_started_at: Optional[str] = None
    last_stopped_at: Optional[str] = None
    last_error: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by_email: Optional[str] = None


class RemoteAccessConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[Literal["quick", "named"]] = None
    autostart: Optional[bool] = None
    protocol: Optional[Literal["auto", "http2", "quic"]] = None
    tunnel_hostname: Optional[str] = None
    tunnel_dns_target: Optional[str] = None
    target_url: Optional[str] = None
    tunnel_token: Optional[str] = Field(default=None, repr=False)
    clear_tunnel_token: bool = False
    expected_updated_at: Optional[datetime] = None

    @field_validator("tunnel_hostname")
    @classmethod
    def _validate_hostname(cls, v):
        if v is None or v == "":
            return None
        v = v.strip().lower().rstrip("/")
        if "://" in v:
            v = v.split("://", 1)[1]
        v = v.split("/", 1)[0]
        if not HOSTNAME_RE.match(v):
            raise ValueError("Invalid hostname (must be a fully qualified domain)")
        return v


class StartRequest(BaseModel):
    mode: Optional[Literal["quick", "named"]] = None


class TunnelStatusOut(BaseModel):
    state: Literal[
        "stopped", "starting", "running", "stopping",
        "crashed", "error", "unavailable",
    ]
    mode: Optional[Literal["quick", "named"]] = None
    public_url: Optional[str] = None
    hostname: Optional[str] = None
    target_url: Optional[str] = None
    pid: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_error: Optional[str] = None
    restart_attempts: int = 0
    supervisor_active: bool = False
    binary_available: bool = False
    cloudflared_path: Optional[str] = None
    message: Optional[str] = None


class TenantRemoteAccessRow(BaseModel):
    id: str
    name: str
    slug: str
    user_count: int
    remote_access_enabled: bool
    last_changed_at: Optional[str] = None
    last_changed_by_email: Optional[str] = None


class SetTenantRemoteAccessRequest(BaseModel):
    enabled: bool
    reason: Optional[str] = None


class RemoteAccessCallback(BaseModel):
    label: str
    uri: str
    purpose: Literal["google_sso", "hub_oauth"]


class CallbacksOut(BaseModel):
    hostname: Optional[str] = None
    callbacks: List[RemoteAccessCallback] = []


# ---------- Helpers ----------

def _tunnel_service(db: Session) -> CloudflareTunnelService:
    from sqlalchemy.orm import sessionmaker
    # Service is a process-wide singleton; first call in the lifespan sets
    # its session_factory. We import lazily here to avoid circular imports.
    return get_cloudflare_tunnel_service()


# ---------- Endpoints ----------

@router.get("/config", response_model=RemoteAccessConfigOut)
def get_config(
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    row = get_or_create_config(db)
    return serialize_config(db, row)


@router.put("/config", response_model=RemoteAccessConfigOut)
async def put_config(
    payload: RemoteAccessConfigUpdate,
    request: Request,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    try:
        row = update_config(
            db=db,
            admin=admin,
            payload=payload.model_dump(exclude_unset=True),
            expected_updated_at=payload.expected_updated_at,
            request=request,
        )
    except ConfigConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        logger.error("Config update failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        )

    # If the tunnel is currently running, trigger a reload so new settings apply
    try:
        service = _tunnel_service(db)
        snapshot = await service.get_snapshot()
        if snapshot.get("state") == "running":
            await service.reload_config()
    except Exception as exc:
        logger.warning("Config reload after update failed (non-fatal): %s", exc)

    return serialize_config(db, row)


@router.post("/start", response_model=TunnelStatusOut)
async def start_tunnel(
    payload: StartRequest,
    request: Request,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    try:
        service = _tunnel_service(db)
        snapshot = await service.start(mode=payload.mode)
    except TunnelConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        logger.warning("Tunnel start failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    log_admin_action(
        db=db,
        admin=admin,
        action="remote_access.tunnel.started",
        resource_type="remote_access_tunnel",
        resource_id="1",
        details={"mode": snapshot.get("mode"), "state": snapshot.get("state")},
        request=request,
    )
    return snapshot


@router.post("/stop", response_model=TunnelStatusOut)
async def stop_tunnel(
    request: Request,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    try:
        service = _tunnel_service(db)
        snapshot = await service.stop()
    except Exception as exc:
        logger.warning("Tunnel stop failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))

    log_admin_action(
        db=db,
        admin=admin,
        action="remote_access.tunnel.stopped",
        resource_type="remote_access_tunnel",
        resource_id="1",
        details={"state": snapshot.get("state")},
        request=request,
    )
    return snapshot


@router.get("/status", response_model=TunnelStatusOut)
async def get_status(
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    try:
        service = _tunnel_service(db)
    except RuntimeError:
        # Service not yet initialized — return an unavailable snapshot
        return TunnelStatusOut(
            state="unavailable",
            binary_available=False,
            message="Tunnel service not initialized",
        )
    return await service.get_snapshot()


@router.get("/tenants", response_model=List[TenantRemoteAccessRow])
def get_tenants(
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    return list_tenants_with_entitlement(db)


@router.put("/tenants/{tenant_id}", response_model=TenantRemoteAccessRow)
def put_tenant_entitlement(
    tenant_id: str,
    payload: SetTenantRemoteAccessRequest,
    request: Request,
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    try:
        return set_tenant_entitlement(
            db=db,
            admin=admin,
            tenant_id=tenant_id,
            enabled=payload.enabled,
            reason=payload.reason,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/callbacks", response_model=CallbacksOut)
def get_callbacks(
    admin: User = Depends(require_global_admin),
    db: Session = Depends(get_db),
):
    row = get_or_create_config(db)
    return compute_callbacks(row.tunnel_hostname)
