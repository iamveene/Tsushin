"""Browser session profile CRUD endpoints for UI-first browser flows."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import BrowserAutomationIntegration, HubIntegration
from services.audit_service import log_tenant_event
from services.browser_session_profile_service import (
    BrowserSessionProfileError,
    apply_storage_state,
    decrypt_storage_state,
    normalize_profile_name,
    parse_storage_state,
    summarize_storage_state,
)


router = APIRouter(
    prefix="/api/hub/browser-session-profiles",
    tags=["Browser Session Profiles"],
    redirect_slashes=False,
)


class BrowserSessionProfileCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=120)
    profile_name: str = Field(..., min_length=1, max_length=120)
    provider_type: str = Field(default="playwright", max_length=50)
    mode: str = Field(default="container", max_length=20)
    browser_type: str = Field(default="chromium", max_length=20)
    headless: bool = True
    timeout_seconds: int = Field(default=45, ge=1, le=180)
    viewport_width: int = Field(default=1280, ge=320, le=3840)
    viewport_height: int = Field(default=720, ge=240, le=2160)
    session_ttl_seconds: int = Field(default=900, ge=0, le=86400)
    cdp_url: Optional[str] = Field(default=None, max_length=255)
    storage_state_json: Optional[Any] = None
    is_active: bool = True

    @field_validator("integration_name", "profile_name", "provider_type", "mode", "browser_type", "cdp_url")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class BrowserSessionProfileUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    profile_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    provider_type: Optional[str] = Field(default=None, max_length=50)
    mode: Optional[str] = Field(default=None, max_length=20)
    browser_type: Optional[str] = Field(default=None, max_length=20)
    headless: Optional[bool] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=1, le=180)
    viewport_width: Optional[int] = Field(default=None, ge=320, le=3840)
    viewport_height: Optional[int] = Field(default=None, ge=240, le=2160)
    session_ttl_seconds: Optional[int] = Field(default=None, ge=0, le=86400)
    cdp_url: Optional[str] = Field(default=None, max_length=255)
    storage_state_json: Optional[Any] = None
    clear_storage_state: bool = False
    is_active: Optional[bool] = None

    @field_validator("integration_name", "profile_name", "provider_type", "mode", "browser_type", "cdp_url")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None


class BrowserSessionProfileRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    name: str
    profile_name: str
    provider_type: str
    mode: str
    browser_type: str
    headless: bool
    timeout_seconds: int
    viewport_width: int
    viewport_height: int
    session_persistence: bool
    session_ttl_seconds: int
    cdp_url: Optional[str] = None
    is_active: bool
    health_status: Optional[str] = None
    health_status_reason: Optional[str] = None
    has_storage_state: bool
    storage_state_imported_at: Optional[datetime] = None
    storage_state_summary: Dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime] = None


class BrowserSessionProfileTestRequest(BaseModel):
    url: Optional[str] = Field(default=None, max_length=1000)


class BrowserSessionProfileTestResponse(BaseModel):
    ok: bool
    status: str
    details: Dict[str, Any]
    errors: List[str] = Field(default_factory=list)


def _require_tenant(ctx: TenantContext) -> str:
    if not getattr(ctx, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return str(ctx.tenant_id)


def _get_profile_or_404(db: Session, tenant_id: str, profile_id: int) -> BrowserAutomationIntegration:
    profile = (
        db.query(BrowserAutomationIntegration)
        .join(HubIntegration, HubIntegration.id == BrowserAutomationIntegration.id)
        .filter(BrowserAutomationIntegration.id == profile_id)
        .filter(HubIntegration.tenant_id == tenant_id)
        .filter(HubIntegration.type == "browser_automation")
        .first()
    )
    if not profile:
        raise HTTPException(status_code=404, detail="Browser session profile not found")
    return profile


def _summary_from_row(profile: BrowserAutomationIntegration, tenant_id: str, db: Session) -> Dict[str, Any]:
    if profile.storage_state_summary_json:
        try:
            parsed = json.loads(profile.storage_state_summary_json)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    try:
        return summarize_storage_state(decrypt_storage_state(db, tenant_id, profile.storage_state_encrypted))
    except Exception:
        return {"cookie_count": 0, "origin_count": 0, "domains": []}


def _to_read(profile: BrowserAutomationIntegration, tenant_id: str, db: Session) -> BrowserSessionProfileRead:
    profile_name = profile.session_profile_name or f"profile-{profile.id}"
    return BrowserSessionProfileRead(
        id=profile.id,
        tenant_id=tenant_id,
        integration_name=profile.display_name or profile.name,
        name=profile.name,
        profile_name=profile_name,
        provider_type=profile.provider_type or "playwright",
        mode=profile.mode or "container",
        browser_type=profile.browser_type or "chromium",
        headless=bool(profile.headless),
        timeout_seconds=int(profile.timeout_seconds or 45),
        viewport_width=int(profile.viewport_width or 1280),
        viewport_height=int(profile.viewport_height or 720),
        session_persistence=bool(profile.session_persistence),
        session_ttl_seconds=int(profile.session_ttl_seconds or 900),
        cdp_url=profile.cdp_url,
        is_active=bool(profile.is_active),
        health_status=profile.health_status,
        health_status_reason=profile.health_status_reason,
        has_storage_state=bool(profile.storage_state_encrypted),
        storage_state_imported_at=profile.storage_state_imported_at,
        storage_state_summary=_summary_from_row(profile, tenant_id, db),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.get("", response_model=list[BrowserSessionProfileRead])
def list_browser_session_profiles(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    _current_user=Depends(require_permission("hub.read")),
) -> list[BrowserSessionProfileRead]:
    tenant_id = _require_tenant(ctx)
    profiles = (
        db.query(BrowserAutomationIntegration)
        .join(HubIntegration, HubIntegration.id == BrowserAutomationIntegration.id)
        .filter(HubIntegration.tenant_id == tenant_id)
        .filter(HubIntegration.type == "browser_automation")
        .order_by(BrowserAutomationIntegration.id.desc())
        .all()
    )
    return [_to_read(profile, tenant_id, db) for profile in profiles]


@router.post("", response_model=BrowserSessionProfileRead, status_code=status.HTTP_201_CREATED)
def create_browser_session_profile(
    payload: BrowserSessionProfileCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
) -> BrowserSessionProfileRead:
    tenant_id = _require_tenant(ctx)
    profile_name = normalize_profile_name(payload.profile_name)
    if not profile_name:
        raise HTTPException(status_code=400, detail="Profile name is required")

    existing = (
        db.query(BrowserAutomationIntegration.id)
        .join(HubIntegration, HubIntegration.id == BrowserAutomationIntegration.id)
        .filter(HubIntegration.tenant_id == tenant_id)
        .filter(HubIntegration.type == "browser_automation")
        .filter(BrowserAutomationIntegration.session_profile_name == profile_name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail=f"Browser session profile '{profile_name}' already exists")

    profile = BrowserAutomationIntegration(
        type="browser_automation",
        tenant_id=tenant_id,
        name=f"Browser Session - {profile_name}",
        display_name=payload.integration_name,
        provider_type=payload.provider_type or "playwright",
        mode=payload.mode or "container",
        browser_type=payload.browser_type or "chromium",
        headless=payload.headless,
        timeout_seconds=payload.timeout_seconds,
        viewport_width=payload.viewport_width,
        viewport_height=payload.viewport_height,
        session_persistence=True,
        session_ttl_seconds=payload.session_ttl_seconds,
        cdp_url=payload.cdp_url or "http://host.docker.internal:9222",
        session_profile_name=profile_name,
        is_active=payload.is_active,
        health_status="healthy" if payload.storage_state_json else "unknown",
    )
    if payload.storage_state_json is not None:
        try:
            apply_storage_state(db, profile, tenant_id, parse_storage_state(payload.storage_state_json))
        except BrowserSessionProfileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid storage state JSON") from exc

    db.add(profile)
    db.commit()
    db.refresh(profile)
    log_tenant_event(
        db,
        tenant_id,
        getattr(current_user, "id", None),
        "integration.create",
        "browser_session_profile",
        str(profile.id),
        {"profile_name": profile_name, "provider_type": profile.provider_type},
    )
    return _to_read(profile, tenant_id, db)


@router.patch("/{profile_id}", response_model=BrowserSessionProfileRead)
def update_browser_session_profile(
    profile_id: int,
    payload: BrowserSessionProfileUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
) -> BrowserSessionProfileRead:
    tenant_id = _require_tenant(ctx)
    profile = _get_profile_or_404(db, tenant_id, profile_id)
    data = payload.model_dump(exclude_unset=True)

    if "integration_name" in data and data["integration_name"]:
        profile.display_name = data["integration_name"]
        profile.name = f"Browser Session - {normalize_profile_name(data['integration_name']) or profile.session_profile_name or profile.id}"
    if "profile_name" in data and data["profile_name"]:
        next_name = normalize_profile_name(data["profile_name"])
        if not next_name:
            raise HTTPException(status_code=400, detail="Profile name is required")
        duplicate = (
            db.query(BrowserAutomationIntegration.id)
            .join(HubIntegration, HubIntegration.id == BrowserAutomationIntegration.id)
            .filter(HubIntegration.tenant_id == tenant_id)
            .filter(HubIntegration.type == "browser_automation")
            .filter(BrowserAutomationIntegration.session_profile_name == next_name)
            .filter(BrowserAutomationIntegration.id != profile_id)
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=400, detail=f"Browser session profile '{next_name}' already exists")
        profile.session_profile_name = next_name
    for field_name in (
        "provider_type",
        "mode",
        "browser_type",
        "headless",
        "timeout_seconds",
        "viewport_width",
        "viewport_height",
        "session_ttl_seconds",
        "cdp_url",
        "is_active",
    ):
        if field_name in data:
            setattr(profile, field_name, data[field_name])

    if data.get("clear_storage_state"):
        profile.storage_state_encrypted = None
        profile.storage_state_imported_at = None
        profile.storage_state_summary_json = None
        profile.health_status = "unknown"
    elif "storage_state_json" in data and data["storage_state_json"] is not None:
        try:
            apply_storage_state(db, profile, tenant_id, parse_storage_state(data["storage_state_json"]))
            profile.health_status = "healthy"
            profile.health_status_reason = None
        except BrowserSessionProfileError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Invalid storage state JSON") from exc

    db.commit()
    db.refresh(profile)
    log_tenant_event(
        db,
        tenant_id,
        getattr(current_user, "id", None),
        "integration.update",
        "browser_session_profile",
        str(profile.id),
        {"profile_name": profile.session_profile_name},
    )
    return _to_read(profile, tenant_id, db)


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_browser_session_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
) -> None:
    tenant_id = _require_tenant(ctx)
    profile = _get_profile_or_404(db, tenant_id, profile_id)
    profile.is_active = False
    profile.health_status = "disconnected"
    db.commit()
    log_tenant_event(
        db,
        tenant_id,
        getattr(current_user, "id", None),
        "integration.delete",
        "browser_session_profile",
        str(profile_id),
        {"profile_name": profile.session_profile_name},
    )


@router.post("/{profile_id}/test", response_model=BrowserSessionProfileTestResponse)
async def test_browser_session_profile(
    profile_id: int,
    payload: BrowserSessionProfileTestRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    _current_user=Depends(require_permission("hub.write")),
) -> BrowserSessionProfileTestResponse:
    tenant_id = _require_tenant(ctx)
    profile = _get_profile_or_404(db, tenant_id, profile_id)
    errors: List[str] = []
    details: Dict[str, Any] = {
        "profile_name": profile.session_profile_name,
        "has_storage_state": bool(profile.storage_state_encrypted),
        "storage_state_summary": _summary_from_row(profile, tenant_id, db),
    }
    if not profile.storage_state_encrypted:
        errors.append("No storage state has been imported for this profile")
    test_url = (payload.url or "").strip()
    if test_url:
        try:
            from hub.providers.browser_automation_provider import BrowserConfig
            from hub.providers.playwright_provider import PlaywrightProvider

            state = decrypt_storage_state(db, tenant_id, profile.storage_state_encrypted)
            provider = PlaywrightProvider(
                BrowserConfig(
                    provider_type=profile.provider_type or "playwright",
                    mode=profile.mode or "container",
                    browser_type=profile.browser_type or "chromium",
                    headless=bool(profile.headless),
                    timeout_seconds=int(profile.timeout_seconds or 45),
                    viewport_width=int(profile.viewport_width or 1280),
                    viewport_height=int(profile.viewport_height or 720),
                    session_persistence=True,
                    session_ttl_seconds=int(profile.session_ttl_seconds or 900),
                    cdp_url=profile.cdp_url or "http://host.docker.internal:9222",
                    tenant_id=tenant_id,
                    browser_session_profile_name=profile.session_profile_name,
                    storage_state=state,
                )
            )
            await provider.initialize()
            try:
                result = await provider.navigate(test_url, wait_until="domcontentloaded")
                details["navigation"] = result.to_dict()
                details["final_url"] = await provider.get_current_url()
                details["title"] = await provider.get_page_title()
                if not result.success:
                    errors.append(result.error or "Navigation failed")
            finally:
                await provider.cleanup()
        except Exception as exc:
            errors.append(str(exc)[:500])

    status_value = "healthy" if not errors else "degraded"
    profile.health_status = status_value
    profile.health_status_reason = "; ".join(errors)[:500] if errors else None
    profile.last_health_check = datetime.utcnow()
    db.commit()
    return BrowserSessionProfileTestResponse(
        ok=not errors,
        status=status_value,
        details=details,
        errors=errors,
    )
