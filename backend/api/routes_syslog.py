"""
Tenant Syslog Configuration Routes
Provides REST endpoints for managing per-tenant syslog forwarding settings.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User, TenantSyslogConfig
from auth_dependencies import require_permission, get_tenant_context, TenantContext
from hub.security import TokenEncryption
from services.encryption_key_service import get_google_encryption_key

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings/syslog", tags=["syslog-config"])


# ============================================================================
# Schemas
# ============================================================================

class SyslogConfigResponse(BaseModel):
    id: int
    tenant_id: str
    enabled: bool
    host: Optional[str] = None
    port: int = 514
    protocol: str = "tcp"
    facility: int = 1
    app_name: str = "tsushin"
    tls_verify: bool = True
    has_ca_cert: bool = False
    has_client_cert: bool = False
    has_client_key: bool = False
    event_categories: List[str] = []
    last_successful_send: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SyslogConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    host: Optional[str] = None
    port: Optional[int] = None
    protocol: Optional[str] = None
    facility: Optional[int] = None
    app_name: Optional[str] = None
    tls_ca_cert: Optional[str] = None
    tls_client_cert: Optional[str] = None
    tls_client_key: Optional[str] = None
    tls_verify: Optional[bool] = None
    event_categories: Optional[List[str]] = None

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v):
        if v is not None and v not in ("tcp", "udp", "tls"):
            raise ValueError("Protocol must be 'tcp', 'udp', or 'tls'")
        return v

    @field_validator("facility")
    @classmethod
    def validate_facility(cls, v):
        if v is not None and (v < 0 or v > 23):
            raise ValueError("Facility must be 0-23 (RFC 5424)")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if v is not None and (v < 1 or v > 65535):
            raise ValueError("Port must be 1-65535")
        return v

    @field_validator("app_name")
    @classmethod
    def validate_app_name(cls, v):
        import re
        if v is not None:
            v = v.strip()
            if not re.match(r'^[\x21-\x7e]{1,48}$', v):
                raise ValueError("App name must be 1-48 printable ASCII characters with no spaces")
        return v


class SyslogTestRequest(BaseModel):
    host: str
    port: int = 514
    protocol: str = "tcp"
    tls_ca_cert: Optional[str] = None
    tls_verify: bool = True

    @field_validator("host")
    @classmethod
    def validate_host(cls, v):
        """Block private/loopback/link-local addresses to prevent SSRF."""
        import ipaddress
        v = v.strip()
        if not v:
            raise ValueError("Host is required")
        # Block obvious internal hostnames
        blocked_names = {"localhost", "postgres", "tsushin-postgres", "backend", "tsushin-backend", "host.docker.internal"}
        if v.lower() in blocked_names:
            raise ValueError("Internal hostnames are not allowed")
        # Try to parse as IP and block private ranges
        try:
            ip = ipaddress.ip_address(v)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private, loopback, and link-local addresses are not allowed")
        except ValueError as e:
            if "not allowed" in str(e):
                raise
            # Not an IP — it's a hostname, allow it (DNS resolution happens at connect time)
        return v

    @field_validator("protocol")
    @classmethod
    def validate_protocol(cls, v):
        if v not in ("tcp", "udp", "tls"):
            raise ValueError("Protocol must be 'tcp', 'udp', or 'tls'")
        return v

    @field_validator("port")
    @classmethod
    def validate_port(cls, v):
        if v < 1 or v > 65535:
            raise ValueError("Port must be 1-65535")
        return v


class SyslogTestResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[float] = None


# ============================================================================
# Encryption helpers
# ============================================================================

def _get_encryptor(db: Session) -> TokenEncryption:
    encryption_key = get_google_encryption_key(db)
    return TokenEncryption(encryption_key.encode())


def _encrypt_field(db: Session, tenant_id: str, value: str, field_name: str) -> str:
    enc = _get_encryptor(db)
    return enc.encrypt(value, f"syslog_{field_name}_{tenant_id}")


def _config_to_response(config: TenantSyslogConfig) -> SyslogConfigResponse:
    categories = []
    if config.event_categories:
        try:
            categories = json.loads(config.event_categories)
        except (json.JSONDecodeError, TypeError):
            categories = []

    return SyslogConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        enabled=config.enabled or False,
        host=config.host,
        port=config.port or 514,
        protocol=config.protocol or "tcp",
        facility=config.facility or 1,
        app_name=config.app_name or "tsushin",
        tls_verify=config.tls_verify if config.tls_verify is not None else True,
        has_ca_cert=bool(config.tls_ca_cert_encrypted),
        has_client_cert=bool(config.tls_client_cert_encrypted),
        has_client_key=bool(config.tls_client_key_encrypted),
        event_categories=categories,
        last_successful_send=config.last_successful_send.isoformat() if config.last_successful_send else None,
        last_error=config.last_error,
        last_error_at=config.last_error_at.isoformat() if config.last_error_at else None,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/", response_model=SyslogConfigResponse)
async def get_syslog_config(
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get tenant syslog forwarding configuration."""
    config = ctx.db.query(TenantSyslogConfig).filter(
        TenantSyslogConfig.tenant_id == ctx.tenant_id
    ).first()

    if not config:
        return SyslogConfigResponse(
            id=0, tenant_id=ctx.tenant_id, enabled=False,
        )

    return _config_to_response(config)


@router.put("/", response_model=SyslogConfigResponse)
async def update_syslog_config(
    update: SyslogConfigUpdate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update tenant syslog forwarding configuration."""
    config = ctx.db.query(TenantSyslogConfig).filter(
        TenantSyslogConfig.tenant_id == ctx.tenant_id
    ).first()

    if not config:
        config = TenantSyslogConfig(tenant_id=ctx.tenant_id)
        ctx.db.add(config)

    if update.enabled is not None:
        config.enabled = update.enabled
    if update.host is not None:
        config.host = update.host or None
    if update.port is not None:
        config.port = update.port
    if update.protocol is not None:
        config.protocol = update.protocol
    if update.facility is not None:
        config.facility = update.facility
    if update.app_name is not None:
        config.app_name = update.app_name or "tsushin"
    if update.tls_verify is not None:
        config.tls_verify = update.tls_verify

    # Encrypt TLS certs
    if update.tls_ca_cert is not None:
        config.tls_ca_cert_encrypted = (
            _encrypt_field(ctx.db, ctx.tenant_id, update.tls_ca_cert, "ca_cert")
            if update.tls_ca_cert else None
        )
    if update.tls_client_cert is not None:
        config.tls_client_cert_encrypted = (
            _encrypt_field(ctx.db, ctx.tenant_id, update.tls_client_cert, "client_cert")
            if update.tls_client_cert else None
        )
    if update.tls_client_key is not None:
        config.tls_client_key_encrypted = (
            _encrypt_field(ctx.db, ctx.tenant_id, update.tls_client_key, "client_key")
            if update.tls_client_key else None
        )

    if update.event_categories is not None:
        config.event_categories = json.dumps(update.event_categories) if update.event_categories else None

    config.last_error = None
    config.last_error_at = None
    config.updated_at = datetime.utcnow()

    ctx.db.commit()
    ctx.db.refresh(config)

    # Invalidate forwarder cache
    try:
        from services.syslog_forwarder import invalidate_config_cache
        invalidate_config_cache(ctx.tenant_id)
    except Exception:
        pass

    # Audit log the settings change
    try:
        from services.audit_service import log_tenant_event, TenantAuditActions
        log_tenant_event(ctx.db, ctx.tenant_id, current_user.id,
                         TenantAuditActions.SETTINGS_UPDATE, "syslog_config", str(config.id),
                         {"enabled": config.enabled, "host": config.host, "protocol": config.protocol})
    except Exception:
        pass

    return _config_to_response(config)


@router.post("/test", response_model=SyslogTestResponse)
async def test_syslog_connection(
    request: SyslogTestRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Test connectivity to a syslog server."""
    from services.syslog_service import SyslogSender

    tls_config = None
    if request.protocol == "tls" and request.tls_ca_cert:
        tls_config = {"ca_cert": request.tls_ca_cert, "verify": request.tls_verify}

    sender = SyslogSender()
    result = sender.test_connection(
        host=request.host,
        port=request.port,
        protocol=request.protocol,
        tls_config=tls_config,
    )

    return SyslogTestResponse(**result)
