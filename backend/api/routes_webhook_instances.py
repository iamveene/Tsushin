"""
v0.6.0: Webhook Integration Management API.

Tenant-scoped CRUD for WebhookIntegration. Secret is generated server-side,
returned **once in plaintext** on create/rotate, and thereafter only the
masked preview is exposed.

All endpoints authenticated via JWT (get_tenant_context) and isolated via
filter_by_tenant().
"""

from __future__ import annotations

import ipaddress
import json as _json
import logging
import secrets
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import Agent, WebhookIntegration
from utils.ssrf_validator import SSRFValidationError, validate_url

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/webhook-integrations",
    tags=["Webhook Integrations"],
    redirect_slashes=False,
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class WebhookIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    callback_url: Optional[str] = Field(default=None, max_length=500)
    callback_enabled: bool = False
    ip_allowlist: Optional[List[str]] = None  # list of CIDRs
    rate_limit_rpm: int = Field(default=30, ge=1, le=600)
    max_payload_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)

    @field_validator("ip_allowlist")
    @classmethod
    def _validate_cidrs(cls, v):
        if v is None:
            return v
        for cidr in v:
            try:
                ipaddress.ip_network(str(cidr), strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid CIDR '{cidr}': {e}")
        return v


class WebhookIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    callback_url: Optional[str] = Field(default=None, max_length=500)
    callback_enabled: Optional[bool] = None
    ip_allowlist: Optional[List[str]] = None
    rate_limit_rpm: Optional[int] = Field(default=None, ge=1, le=600)
    max_payload_bytes: Optional[int] = Field(default=None, ge=1024, le=10_485_760)
    is_active: Optional[bool] = None

    @field_validator("ip_allowlist")
    @classmethod
    def _validate_cidrs(cls, v):
        if v is None:
            return v
        for cidr in v:
            try:
                ipaddress.ip_network(str(cidr), strict=False)
            except ValueError as e:
                raise ValueError(f"Invalid CIDR '{cidr}': {e}")
        return v


class WebhookIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    api_secret_preview: str
    callback_url: Optional[str]
    callback_enabled: bool
    ip_allowlist: Optional[List[str]]
    rate_limit_rpm: int
    max_payload_bytes: int
    is_active: bool
    status: str
    health_status: str
    last_health_check: Optional[datetime]
    last_activity_at: Optional[datetime]
    circuit_breaker_state: str
    created_at: datetime
    updated_at: Optional[datetime]
    inbound_url: str  # derived


class WebhookIntegrationCreateResponse(BaseModel):
    integration: WebhookIntegrationRead
    api_secret: str  # ONLY returned here, plaintext once
    warning: str = (
        "Store this secret securely now. It will never be shown again. "
        "You can rotate it, but you cannot view it."
    )


class WebhookSecretRotateResponse(BaseModel):
    api_secret: str
    api_secret_preview: str
    warning: str = "Previous secret is invalidated. Update your external system."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_secret() -> tuple[str, str]:
    """Return (plaintext_secret, preview)."""
    plaintext = "whsec_" + secrets.token_urlsafe(32)
    preview = plaintext[:10] + "…"
    return plaintext, preview


def _encrypt_secret(db: Session, tenant_id: str, plaintext: str) -> str:
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_webhook_encryption_key

    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise HTTPException(status_code=500, detail="Server configuration error")
    return TokenEncryption(master_key.encode()).encrypt(plaintext, tenant_id)


def _inbound_url(webhook_id: int) -> str:
    # Caller builds absolute URL from their own base; we return a relative path
    return f"/api/webhooks/{webhook_id}/inbound"


def _to_read(integration: WebhookIntegration) -> WebhookIntegrationRead:
    ip_allowlist = None
    if integration.ip_allowlist_json:
        try:
            ip_allowlist = _json.loads(integration.ip_allowlist_json)
        except Exception:
            ip_allowlist = None
    return WebhookIntegrationRead(
        id=integration.id,
        tenant_id=integration.tenant_id,
        integration_name=integration.integration_name,
        api_secret_preview=integration.api_secret_preview,
        callback_url=integration.callback_url,
        callback_enabled=bool(integration.callback_enabled),
        ip_allowlist=ip_allowlist,
        rate_limit_rpm=integration.rate_limit_rpm or 30,
        max_payload_bytes=integration.max_payload_bytes or 1_048_576,
        is_active=bool(integration.is_active),
        status=integration.status or "active",
        health_status=integration.health_status or "unknown",
        last_health_check=integration.last_health_check,
        last_activity_at=integration.last_activity_at,
        circuit_breaker_state=integration.circuit_breaker_state or "closed",
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        inbound_url=_inbound_url(integration.id),
    )


def _validate_callback(url: Optional[str]) -> None:
    if not url:
        return
    try:
        validate_url(url)
    except SSRFValidationError as e:
        raise HTTPException(status_code=400, detail=f"callback_url blocked by SSRF policy: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("", response_model=WebhookIntegrationCreateResponse)
async def create_webhook_integration(
    body: WebhookIntegrationCreate,
    _: None = Depends(require_permission("integrations.webhook.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    if not context.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    _validate_callback(body.callback_url)

    plaintext, preview = _make_secret()
    encrypted = _encrypt_secret(db, context.tenant_id, plaintext)

    integration = WebhookIntegration(
        tenant_id=context.tenant_id,
        integration_name=body.integration_name,
        api_secret_encrypted=encrypted,
        api_secret_preview=preview,
        callback_url=body.callback_url,
        callback_enabled=body.callback_enabled,
        ip_allowlist_json=_json.dumps(body.ip_allowlist) if body.ip_allowlist else None,
        rate_limit_rpm=body.rate_limit_rpm,
        max_payload_bytes=body.max_payload_bytes,
        is_active=True,
        status="active",
        created_by=context.user.id,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    logger.info(
        f"Created webhook integration {integration.id} for tenant {context.tenant_id}"
    )
    return WebhookIntegrationCreateResponse(
        integration=_to_read(integration),
        api_secret=plaintext,
    )


@router.get("", response_model=List[WebhookIntegrationRead])
async def list_webhook_integrations(
    _: None = Depends(require_permission("integrations.webhook.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    q = context.filter_by_tenant(db.query(WebhookIntegration), WebhookIntegration.tenant_id)
    integrations = q.order_by(WebhookIntegration.created_at.desc()).all()
    return [_to_read(i) for i in integrations]


@router.get("/{integration_id}", response_model=WebhookIntegrationRead)
async def get_webhook_integration(
    integration_id: int,
    _: None = Depends(require_permission("integrations.webhook.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    integration = db.query(WebhookIntegration).filter_by(id=integration_id).first()
    if integration is None or not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Webhook integration not found")
    return _to_read(integration)


@router.patch("/{integration_id}", response_model=WebhookIntegrationRead)
async def update_webhook_integration(
    integration_id: int,
    body: WebhookIntegrationUpdate,
    _: None = Depends(require_permission("integrations.webhook.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    integration = db.query(WebhookIntegration).filter_by(id=integration_id).first()
    if integration is None or not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Webhook integration not found")

    if body.callback_url is not None:
        _validate_callback(body.callback_url)
        integration.callback_url = body.callback_url
    if body.integration_name is not None:
        integration.integration_name = body.integration_name
    if body.callback_enabled is not None:
        integration.callback_enabled = body.callback_enabled
    if body.ip_allowlist is not None:
        integration.ip_allowlist_json = (
            _json.dumps(body.ip_allowlist) if body.ip_allowlist else None
        )
    if body.rate_limit_rpm is not None:
        integration.rate_limit_rpm = body.rate_limit_rpm
    if body.max_payload_bytes is not None:
        integration.max_payload_bytes = body.max_payload_bytes
    if body.is_active is not None:
        integration.is_active = body.is_active
        integration.status = "active" if body.is_active else "paused"

    integration.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(integration)
    return _to_read(integration)


@router.post("/{integration_id}/rotate-secret", response_model=WebhookSecretRotateResponse)
async def rotate_webhook_secret(
    integration_id: int,
    _: None = Depends(require_permission("integrations.webhook.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    integration = db.query(WebhookIntegration).filter_by(id=integration_id).first()
    if integration is None or not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Webhook integration not found")

    plaintext, preview = _make_secret()
    integration.api_secret_encrypted = _encrypt_secret(db, integration.tenant_id, plaintext)
    integration.api_secret_preview = preview
    integration.updated_at = datetime.utcnow()
    db.commit()
    logger.info(f"Rotated secret for webhook integration {integration_id}")
    return WebhookSecretRotateResponse(api_secret=plaintext, api_secret_preview=preview)


@router.delete("/{integration_id}")
async def delete_webhook_integration(
    integration_id: int,
    _: None = Depends(require_permission("integrations.webhook.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    integration = db.query(WebhookIntegration).filter_by(id=integration_id).first()
    if integration is None or not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Webhook integration not found")

    # Unbind from any agents (defensive — DB onDelete=SET NULL will also do this)
    db.query(Agent).filter(
        Agent.webhook_integration_id == integration_id,
        Agent.tenant_id == integration.tenant_id,
    ).update({"webhook_integration_id": None})

    db.delete(integration)
    db.commit()
    logger.info(f"Deleted webhook integration {integration_id}")
    return {"status": "deleted", "id": integration_id}
