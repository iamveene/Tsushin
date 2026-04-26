"""
v0.7.0: Webhook Trigger Management API.

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
import re
import secrets
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.trigger_criteria import evaluate_payload_criteria, validate_criteria
from db import get_db
from models import Agent, Contact, WebhookIntegration
from utils.ssrf_validator import SSRFValidationError, validate_url

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/triggers/webhook",
    tags=["Webhook Triggers"],
    redirect_slashes=False,
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class WebhookIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, max_length=64)
    callback_url: Optional[str] = Field(default=None, max_length=500)
    callback_enabled: bool = False
    ip_allowlist: Optional[List[str]] = None  # list of CIDRs
    rate_limit_rpm: int = Field(default=30, ge=1, le=600)
    max_payload_bytes: int = Field(default=1_048_576, ge=1024, le=10_485_760)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    trigger_criteria: Optional[dict[str, Any]] = None

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

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, v):
        if v is None:
            return v
        try:
            return validate_criteria(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class WebhookIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, max_length=64)
    callback_url: Optional[str] = Field(default=None, max_length=500)
    callback_enabled: Optional[bool] = None
    ip_allowlist: Optional[List[str]] = None
    rate_limit_rpm: Optional[int] = Field(default=None, ge=1, le=600)
    max_payload_bytes: Optional[int] = Field(default=None, ge=1024, le=10_485_760)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    trigger_criteria: Optional[dict[str, Any]] = None
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

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, v):
        if v is None:
            return v
        try:
            return validate_criteria(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class WebhookIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    slug: str
    api_secret_preview: str
    callback_url: Optional[str]
    callback_enabled: bool
    ip_allowlist: Optional[List[str]]
    rate_limit_rpm: int
    max_payload_bytes: int
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
    trigger_criteria: Optional[dict[str, Any]] = None
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


class WebhookCriteriaTestRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    trigger_criteria: Optional[dict[str, Any]] = None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, v):
        if v is None:
            return v
        try:
            return validate_criteria(v)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class WebhookCriteriaTestResponse(BaseModel):
    matched: bool
    reason: Optional[str] = None


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


def _load_active_agent(db: Session, tenant_id: str, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _agent_name(db: Session, tenant_id: str, agent_id: Optional[int]) -> Optional[str]:
    if not agent_id:
        return None
    row = db.query(Contact.friendly_name).join(
        Agent,
        Agent.contact_id == Contact.id,
    ).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
    ).first()
    return row.friendly_name if row else None


# v0.7.1: Custom webhook slug validation
_SLUG_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")
_RESERVED_SLUGS = frozenset({
    "inbound", "rotate-secret", "health", "status", "test",
    "callback", "docs", "openapi", "api", "webhooks", "admin", "v1",
})


def _slug_format_error(slug: str) -> Optional[str]:
    if not isinstance(slug, str):
        return "Slug must be a string"
    if len(slug) < 3:
        return "Slug must be at least 3 characters"
    if len(slug) > 64:
        return "Slug must be at most 64 characters"
    if not _SLUG_RE.match(slug):
        if slug[:1].isdigit():
            return "Slug must start with a lowercase letter"
        if slug != slug.lower():
            return "Slug must be lowercase"
        if slug.startswith("-") or slug.endswith("-"):
            return "Slug cannot start or end with a hyphen"
        if "--" in slug:
            return "Slug cannot contain consecutive hyphens"
        return "Slug may only contain lowercase letters, digits, and single hyphens"
    if slug in _RESERVED_SLUGS:
        return "Slug is reserved"
    return None


def _validate_slug_format(slug: str) -> None:
    err = _slug_format_error(slug)
    if err:
        raise HTTPException(status_code=400, detail=err)


def _check_slug_unique(db: Session, slug: str, exclude_id: Optional[int] = None) -> None:
    q = db.query(WebhookIntegration).filter(WebhookIntegration.slug == slug)
    if exclude_id is not None:
        q = q.filter(WebhookIntegration.id != exclude_id)
    if q.first() is not None:
        raise HTTPException(status_code=409, detail="Slug already in use")


def _generate_auto_slug(db: Session) -> str:
    for _ in range(8):
        candidate = f"wh-{secrets.token_hex(3)}"
        if db.query(WebhookIntegration).filter_by(slug=candidate).first() is None:
            return candidate
    raise HTTPException(status_code=500, detail="Could not generate unique slug")


def _inbound_url(slug: str) -> str:
    # Caller builds absolute URL from their own base; we return a relative path
    return f"/api/webhooks/{slug}/inbound"


def _to_read(db: Session, integration: WebhookIntegration) -> WebhookIntegrationRead:
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
        slug=integration.slug,
        api_secret_preview=integration.api_secret_preview,
        callback_url=integration.callback_url,
        callback_enabled=bool(integration.callback_enabled),
        ip_allowlist=ip_allowlist,
        rate_limit_rpm=integration.rate_limit_rpm or 30,
        max_payload_bytes=integration.max_payload_bytes or 1_048_576,
        default_agent_id=integration.default_agent_id,
        default_agent_name=_agent_name(db, integration.tenant_id, integration.default_agent_id),
        trigger_criteria=integration.trigger_criteria,
        is_active=bool(integration.is_active),
        status=integration.status or "active",
        health_status=integration.health_status or "unknown",
        last_health_check=integration.last_health_check,
        last_activity_at=integration.last_activity_at,
        circuit_breaker_state=integration.circuit_breaker_state or "closed",
        created_at=integration.created_at,
        updated_at=integration.updated_at,
        inbound_url=_inbound_url(integration.slug),
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


@router.get("/slug-available")
async def check_slug_available(
    slug: str,
    exclude_id: Optional[int] = None,
    _: None = Depends(require_permission("integrations.webhook.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Live-validation endpoint for the custom URI slug input.

    Returns {"available": bool, "reason": str | None}. Does not raise — the
    UI renders the reason inline. Format and reserved-word checks run first;
    only valid slugs hit the DB for uniqueness. ``exclude_id`` lets the
    edit flow check "is this slug free for me to keep or rename to?"
    without treating the integration's own current slug as a collision.

    Uniqueness is global and independent of ``is_active`` — a paused
    webhook's slug stays reserved; only deleting the integration frees it.
    """
    fmt_err = _slug_format_error(slug)
    if fmt_err:
        return {"available": False, "reason": fmt_err}
    q = db.query(WebhookIntegration).filter(WebhookIntegration.slug == slug)
    if exclude_id is not None:
        q = q.filter(WebhookIntegration.id != exclude_id)
    if q.first() is not None:
        return {"available": False, "reason": "Slug already in use"}
    return {"available": True, "reason": None}


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
    if body.default_agent_id is not None:
        _load_active_agent(db, context.tenant_id, body.default_agent_id)

    # v0.7.1: resolve slug (auto or custom)
    if body.slug:
        slug = body.slug.strip()
        _validate_slug_format(slug)
        _check_slug_unique(db, slug)
    else:
        slug = _generate_auto_slug(db)

    plaintext, preview = _make_secret()
    encrypted = _encrypt_secret(db, context.tenant_id, plaintext)

    integration = WebhookIntegration(
        tenant_id=context.tenant_id,
        integration_name=body.integration_name,
        slug=slug,
        api_secret_encrypted=encrypted,
        api_secret_preview=preview,
        callback_url=body.callback_url,
        callback_enabled=body.callback_enabled,
        ip_allowlist_json=_json.dumps(body.ip_allowlist) if body.ip_allowlist else None,
        rate_limit_rpm=body.rate_limit_rpm,
        max_payload_bytes=body.max_payload_bytes,
        default_agent_id=body.default_agent_id,
        trigger_criteria=body.trigger_criteria,
        is_active=True,
        status="active",
        created_by=context.user.id,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    logger.info(
        f"Created webhook integration {integration.id} (slug={slug}) for tenant {context.tenant_id}"
    )

    # v0.7.0 Wave 4 — auto-generate the system-managed Flow for this trigger.
    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=context.tenant_id,
                trigger_kind="webhook",
                trigger_instance_id=integration.id,
                default_agent_id=integration.default_agent_id,
            )
            db.commit()
    except Exception:
        logger.exception(
            "Auto-flow generation failed for webhook integration %s; integration persists", integration.id
        )
        db.rollback()

    return WebhookIntegrationCreateResponse(
        integration=_to_read(db, integration),
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
    return [_to_read(db, i) for i in integrations]


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
    return _to_read(db, integration)


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
    if body.slug is not None:
        new_slug = body.slug.strip()
        if new_slug != integration.slug:
            _validate_slug_format(new_slug)
            _check_slug_unique(db, new_slug, exclude_id=integration.id)
            integration.slug = new_slug
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
    if "default_agent_id" in body.model_fields_set:
        if body.default_agent_id is not None:
            _load_active_agent(db, integration.tenant_id, body.default_agent_id)
        integration.default_agent_id = body.default_agent_id
    if "trigger_criteria" in body.model_fields_set:
        integration.trigger_criteria = body.trigger_criteria
    if body.is_active is not None:
        integration.is_active = body.is_active
        integration.status = "active" if body.is_active else "paused"

    integration.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(integration)
    return _to_read(db, integration)


@router.post("/{integration_id}/criteria/test", response_model=WebhookCriteriaTestResponse)
async def test_webhook_criteria(
    integration_id: int,
    body: WebhookCriteriaTestRequest,
    _: None = Depends(require_permission("integrations.webhook.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    integration = db.query(WebhookIntegration).filter_by(id=integration_id).first()
    if integration is None or not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Webhook integration not found")

    criteria = body.trigger_criteria if body.trigger_criteria is not None else integration.trigger_criteria
    try:
        matched, reason = evaluate_payload_criteria(body.payload, criteria)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return WebhookCriteriaTestResponse(matched=matched, reason=reason)


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
