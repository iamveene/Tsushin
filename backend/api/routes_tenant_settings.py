"""
Tenant self-service settings.

Endpoints for authenticated tenant users to read/update their own tenant's
runtime settings and to resolve the current public ingress URL (v0.6.1).

Read access: any authenticated user belonging to the tenant.
Write access: requires the `org.settings.write` permission (org owner/admin).

v0.6.1 Public Ingress Resolver
------------------------------
`GET /api/tenant/me/public-ingress` returns the authoritative public HTTPS URL
for this tenant (override → platform tunnel → dev env var → none), replacing
ad-hoc reads of `tenant.public_base_url` and `window.location.origin` across
the frontend. See services/public_ingress_resolver.py for precedence details.
"""

from __future__ import annotations

import logging
import socket
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

import settings as app_settings
from auth_dependencies import get_current_user_required, require_permission
from db import get_db
from models_rbac import Tenant, User
from services.audit_service import TenantAuditActions, log_tenant_event
from services.public_ingress_resolver import resolve_public_ingress

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/tenant/me",
    tags=["Tenant Self-Service Settings"],
    redirect_slashes=False,
)


# --- Schemas ---

class TenantSelfSettingsResponse(BaseModel):
    tenant_id: str
    public_base_url: Optional[str] = None

    class Config:
        from_attributes = True


class TenantSelfSettingsUpdate(BaseModel):
    public_base_url: Optional[str] = Field(
        None,
        description=(
            "Publicly-reachable HTTPS base URL (no trailing slash) used as this "
            "tenant's ingress override. Pass empty string or null to clear. In "
            "production only https:// is accepted; http:// is permitted only when "
            "TSUSHIN_DEV_PUBLIC_BASE_URL is set."
        ),
        max_length=512,
    )

    @field_validator("public_base_url")
    @classmethod
    def _normalize(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        v = value.strip()
        if not v:
            return None  # treat empty string as clear

        dev_mode = bool(app_settings.DEV_PUBLIC_BASE_URL)
        if v.startswith("http://"):
            if not dev_mode:
                raise ValueError(
                    "public_base_url must start with https:// "
                    "(http:// only allowed when TSUSHIN_DEV_PUBLIC_BASE_URL is set)"
                )
        elif not v.startswith("https://"):
            raise ValueError("public_base_url must start with https://")

        # Structural check: must have a hostname with a dot (FQDN-ish) and no whitespace.
        if " " in v or "\t" in v:
            raise ValueError("public_base_url must not contain whitespace")

        # Pull the host portion out and require at least one dot so we reject
        # things like "https://localhost" or "https://example" — the ingress
        # URL must be resolvable from the public internet.
        try:
            host_part = v.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
        except Exception:
            raise ValueError("public_base_url is malformed")
        if not host_part or "." not in host_part:
            raise ValueError(
                "public_base_url hostname must be a fully-qualified domain "
                "(e.g. https://example.com)"
            )

        return v.rstrip("/")


class PublicIngressResponse(BaseModel):
    """Resolver response for tenant-facing callers.

    `url` is None when `source == "none"` or when the override is stored but
    currently invalid (in which case `source == "override"` and `warning`
    explains the problem so the UI can surface it).
    """
    url: Optional[str] = None
    source: Literal["override", "tunnel", "dev", "none"]
    warning: Optional[str] = None
    override_url: Optional[str] = None


# --- Helpers ---

def _load_tenant(db: Session, current_user: User) -> Tenant:
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant")
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


def _dns_check(url: str, timeout_s: float = 2.0) -> Optional[str]:
    """Resolve the URL's hostname with a bounded timeout.

    Returns None on success, or a human-readable error message on failure.
    The tenant override is rejected on DNS failure so we catch typos at save
    time rather than letting Slack/Discord deliveries fail silently later.
    """
    try:
        host = url.split("://", 1)[1].split("/", 1)[0].split(":", 1)[0]
    except Exception:
        return "Could not parse hostname"
    if not host:
        return "Could not parse hostname"

    old_default = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout_s)
        socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return f"DNS resolution failed for {host}: {exc}"
    except socket.timeout:
        return f"DNS resolution timed out for {host}"
    except Exception as exc:  # pragma: no cover
        return f"DNS resolution error for {host}: {exc}"
    finally:
        socket.setdefaulttimeout(old_default)
    return None


# --- Endpoints ---

@router.get("/settings", response_model=TenantSelfSettingsResponse)
async def get_my_tenant_settings(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return the calling user's tenant settings (public_base_url and friends)."""
    tenant = _load_tenant(db, current_user)
    return TenantSelfSettingsResponse(
        tenant_id=tenant.id,
        public_base_url=tenant.public_base_url,
    )


@router.patch("/settings", response_model=TenantSelfSettingsResponse)
async def update_my_tenant_settings(
    payload: TenantSelfSettingsUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    """Update the calling user's tenant settings.

    Requires `org.settings.write` permission (org owner / admin role).
    Today the only writable field is `public_base_url`. Pass null/empty to clear.
    """
    tenant = _load_tenant(db, current_user)

    fields = payload.model_dump(exclude_unset=True)
    if "public_base_url" in fields:
        new_value = fields["public_base_url"]
        old_value = tenant.public_base_url

        if new_value is not None:
            err = _dns_check(new_value)
            if err is not None:
                raise HTTPException(status_code=422, detail=err)

        tenant.public_base_url = new_value

        db.commit()
        db.refresh(tenant)

        log_tenant_event(
            db,
            tenant.id,
            current_user.id,
            TenantAuditActions.SETTINGS_UPDATE,
            "tenant",
            tenant.id,
            {
                "field": "public_base_url",
                "old_value": old_value,
                "new_value": new_value,
            },
            request,
        )
        logger.info(
            "Tenant %s public_base_url updated by user %s",
            tenant.id, current_user.id,
        )
    else:
        db.commit()
        db.refresh(tenant)

    return TenantSelfSettingsResponse(
        tenant_id=tenant.id,
        public_base_url=tenant.public_base_url,
    )


@router.get("/public-ingress", response_model=PublicIngressResponse)
async def get_my_public_ingress(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """Return the authoritative public HTTPS URL for this tenant.

    See services/public_ingress_resolver.py for precedence (override → tunnel
    → dev → none). Consumers (Slack/Discord wizards, Webhook setup modal,
    PublicBaseUrlCard) should call this endpoint rather than reading
    `public_base_url` directly or inferring a URL from window.location.
    """
    tenant = _load_tenant(db, current_user)
    result = resolve_public_ingress(tenant)
    return PublicIngressResponse(
        url=result.url,
        source=result.source,
        warning=result.warning,
        override_url=result.override_url or tenant.public_base_url,
    )
