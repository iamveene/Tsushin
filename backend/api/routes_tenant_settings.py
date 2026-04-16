"""
Tenant self-service settings (v0.6.0 V060-CHN-002).

These endpoints let an authenticated tenant user (org owner / admin) read and
update their own tenant's runtime settings without going through the
global-admin tenant CRUD at /api/tenants.

Today the only setting exposed is `public_base_url`, the publicly-reachable
HTTPS URL (e.g. a Cloudflare tunnel) that the Hub UI uses to render the exact
Slack Events / Discord Interactions URL the user must paste back into the
third-party portal.

Read access: any authenticated user belonging to the tenant (so the Hub UI can
fetch and display the current value).
Write access: requires the `org.settings.write` permission so only org admins
can change it.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import get_current_user_required, require_permission
from db import get_db
from models_rbac import Tenant, User

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/tenant/me",
    tags=["Tenant Self-Service Settings"],
    redirect_slashes=False,
)


class TenantSelfSettingsResponse(BaseModel):
    tenant_id: str
    public_base_url: Optional[str] = None

    class Config:
        from_attributes = True


class TenantSelfSettingsUpdate(BaseModel):
    public_base_url: Optional[str] = Field(
        None,
        description=(
            "Publicly-reachable HTTPS base URL (no trailing slash) the Hub uses to "
            "compute Slack/Discord webhook URLs. Pass empty string or null to clear."
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
        if not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("public_base_url must start with https:// or http://")
        return v.rstrip("/")


def _load_tenant(db: Session, current_user: User) -> Tenant:
    if not current_user.tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant")
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if tenant is None:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


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
        tenant.public_base_url = fields["public_base_url"]

    db.commit()
    db.refresh(tenant)
    logger.info(
        "Tenant %s public_base_url updated by user %s",
        tenant.id, current_user.id,
    )
    return TenantSelfSettingsResponse(
        tenant_id=tenant.id,
        public_base_url=tenant.public_base_url,
    )
