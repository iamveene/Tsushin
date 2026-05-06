"""Password Vault provider integration CRUD and test endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import AgentSkillIntegration, PasswordVaultIntegration
from services.audit_service import log_tenant_event
from services.password_vault_service import (
    PasswordVaultError,
    PasswordVaultService,
    encrypt_vault_token,
    normalize_optional,
    token_preview,
)


router = APIRouter(
    prefix="/api/hub/password-vault-integrations",
    tags=["Password Vault Integrations"],
    redirect_slashes=False,
)

_VALID_PROVIDERS = {"onepassword"}
_VALID_AUTH_METHODS = {"service_account"}


class PasswordVaultIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(default="onepassword", max_length=32)
    auth_method: str = Field(default="service_account", max_length=32)
    token: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    service_account_token: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    account_url: Optional[str] = Field(default=None, max_length=500)
    account_email: Optional[str] = Field(default=None, max_length=255)
    default_vault: Optional[str] = Field(default=None, max_length=200)
    default_vault_name: Optional[str] = Field(default=None, max_length=200)
    default_vault_id: Optional[str] = Field(default=None, max_length=128)
    allowed_items: List[str] = Field(default_factory=list)
    allowed_fields: List[str] = Field(default_factory=list)
    allow_secret_read: bool = False
    allow_totp_read: bool = False
    allow_metadata_read: bool = True
    is_active: bool = True

    @field_validator("integration_name")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("provider")
    @classmethod
    def _validate_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _VALID_PROVIDERS:
            raise ValueError(f"unsupported provider '{normalized}'")
        return normalized

    @field_validator("auth_method")
    @classmethod
    def _validate_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in _VALID_AUTH_METHODS:
            raise ValueError(f"unsupported auth method '{normalized}'")
        return normalized

    @field_validator(
        "token",
        "service_account_token",
        "account_url",
        "account_email",
        "default_vault",
        "default_vault_name",
        "default_vault_id",
    )
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @model_validator(mode="after")
    def _normalize_aliases(self) -> "PasswordVaultIntegrationCreate":
        self.token = self.token or self.service_account_token
        self.default_vault = self.default_vault or self.default_vault_name
        if not self.token:
            raise ValueError("1Password service account token is required")
        return self


class PasswordVaultIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    token: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    service_account_token: Optional[str] = Field(default=None, min_length=1, max_length=8192)
    provider: Optional[str] = Field(default=None, max_length=32)
    auth_method: Optional[str] = Field(default=None, max_length=32)
    account_url: Optional[str] = Field(default=None, max_length=500)
    account_email: Optional[str] = Field(default=None, max_length=255)
    default_vault: Optional[str] = Field(default=None, max_length=200)
    default_vault_name: Optional[str] = Field(default=None, max_length=200)
    default_vault_id: Optional[str] = Field(default=None, max_length=128)
    allowed_items: Optional[List[str]] = None
    allowed_fields: Optional[List[str]] = None
    allow_secret_read: Optional[bool] = None
    allow_totp_read: Optional[bool] = None
    allow_metadata_read: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator(
        "integration_name",
        "token",
        "service_account_token",
        "provider",
        "auth_method",
        "account_url",
        "account_email",
        "default_vault",
        "default_vault_name",
        "default_vault_id",
    )
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)


class PasswordVaultIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    name: str
    provider: str
    provider_label: str
    auth_method: str
    account_url: Optional[str] = None
    account_email: Optional[str] = None
    default_vault: Optional[str] = None
    default_vault_id: Optional[str] = None
    token_preview: Optional[str] = None
    service_account_token_preview: Optional[str] = None
    default_vault_name: Optional[str] = None
    allowed_items: List[str]
    allowed_fields: List[str]
    allow_secret_read: bool
    allow_totp_read: bool
    allow_metadata_read: bool
    is_active: bool
    health_status: Optional[str] = None
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    linked_agent_count: int = 0
    skill_attached_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class PasswordVaultItemTestRequest(BaseModel):
    item_ref: Optional[str] = Field(default=None, min_length=1, max_length=300)
    item_id: Optional[str] = Field(default=None, min_length=1, max_length=300)
    reference: Optional[str] = Field(default=None, min_length=1, max_length=500)
    field_name: Optional[str] = Field(default=None, max_length=200)
    vault: Optional[str] = Field(default=None, max_length=200)
    vault_id: Optional[str] = Field(default=None, max_length=200)
    mode: str = Field(default="metadata", pattern="^(metadata|field|totp)$")

    @field_validator("item_ref", "item_id", "reference", "field_name", "vault", "vault_id")
    @classmethod
    def _strip_values(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)


class PasswordVaultSecretOverrideRequest(BaseModel):
    vault: Optional[str] = Field(default=None, max_length=200)
    item_ref: str = Field(..., min_length=1, max_length=300)
    field_name: str = Field(..., min_length=1, max_length=200)
    field_type: str = Field(default="CONCEALED", max_length=32)
    value: str = Field(..., min_length=1, max_length=8192)

    @field_validator("vault", "item_ref", "field_name", "field_type", "value")
    @classmethod
    def _strip_override_values(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)


class PasswordVaultSecretOverrideUpdate(BaseModel):
    vault: Optional[str] = Field(default=None, max_length=200)
    item_ref: Optional[str] = Field(default=None, min_length=1, max_length=300)
    field_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    field_type: Optional[str] = Field(default=None, max_length=32)
    value: Optional[str] = Field(default=None, min_length=1, max_length=8192)

    @field_validator("vault", "item_ref", "field_name", "field_type", "value")
    @classmethod
    def _strip_override_update_values(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)


class PasswordVaultSecretOverrideRead(BaseModel):
    id: int
    tenant_id: str
    integration_id: int
    vault: Optional[str] = None
    item_ref: str
    field_name: str
    field_type: str
    value_preview: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


def _require_tenant(ctx: TenantContext) -> str:
    if not getattr(ctx, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return ctx.tenant_id


def _service(db: Session, tenant_id: str) -> PasswordVaultService:
    return PasswordVaultService(db, tenant_id=tenant_id)


def _accessible_integrations(db: Session, ctx: TenantContext):
    query = db.query(PasswordVaultIntegration).filter(
        PasswordVaultIntegration.type == "password_vault",
    )
    return ctx.filter_by_tenant(query, PasswordVaultIntegration.tenant_id)


def _load_or_404(db: Session, ctx: TenantContext, integration_id: int) -> PasswordVaultIntegration:
    integration = _accessible_integrations(db, ctx).filter(
        PasswordVaultIntegration.id == integration_id,
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="password_vault_integration_not_found")
    if not integration.tenant_id:
        raise HTTPException(status_code=400, detail="password_vault_integration_requires_tenant")
    return integration


def _to_read(db: Session, integration: PasswordVaultIntegration) -> PasswordVaultIntegrationRead:
    svc = PasswordVaultService(db, tenant_id=integration.tenant_id)
    linked_agent_count = db.query(AgentSkillIntegration.id).filter(
        AgentSkillIntegration.integration_id == integration.id,
        AgentSkillIntegration.skill_type == "password_vault",
    ).count()
    display_name = integration.display_name or integration.name
    return PasswordVaultIntegrationRead(
        id=integration.id,
        tenant_id=integration.tenant_id,
        integration_name=display_name,
        name=display_name,
        provider=integration.provider or "onepassword",
        provider_label="1Password" if (integration.provider or "onepassword") == "onepassword" else integration.provider,
        auth_method=integration.auth_method or "service_account",
        account_url=integration.account_url,
        account_email=integration.account_email,
        default_vault=integration.default_vault,
        default_vault_id=integration.default_vault_id,
        default_vault_name=integration.default_vault,
        token_preview=integration.token_preview,
        service_account_token_preview=integration.token_preview,
        allowed_items=svc.allowed_items(integration),
        allowed_fields=svc.allowed_fields(integration),
        allow_secret_read=bool(integration.allow_secret_read),
        allow_totp_read=bool(integration.allow_totp_read),
        allow_metadata_read=bool(integration.allow_metadata_read),
        is_active=bool(integration.is_active),
        health_status=integration.health_status or "unknown",
        health_status_reason=integration.health_status_reason,
        last_health_check=integration.last_health_check,
        linked_agent_count=linked_agent_count,
        skill_attached_count=linked_agent_count,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _parse_op_reference(reference: Optional[str]) -> dict:
    ref = normalize_optional(reference)
    if not ref:
        return {}
    if not ref.lower().startswith("op://"):
        return {"item_ref": ref}
    parts = [part for part in ref[5:].split("/") if part]
    parsed: dict = {}
    if len(parts) >= 1:
        parsed["vault"] = parts[0]
    if len(parts) >= 2:
        parsed["item_ref"] = parts[1]
    if len(parts) >= 3:
        parsed["field_name"] = parts[2]
    return parsed


def _resolved_item_test(payload: PasswordVaultItemTestRequest) -> dict:
    parsed = _parse_op_reference(payload.reference)
    vault = payload.vault or payload.vault_id or parsed.get("vault")
    item_ref = payload.item_ref or payload.item_id or parsed.get("item_ref")
    field_name = payload.field_name or parsed.get("field_name")
    mode = payload.mode
    if mode == "metadata" and field_name:
        mode = "field"
    return {
        "vault": vault,
        "item_ref": item_ref,
        "field_name": field_name,
        "mode": mode,
    }


def _audit(
    db: Session,
    ctx: TenantContext,
    user: Any,
    request: Optional[Request],
    action: str,
    integration: PasswordVaultIntegration,
    details: Optional[dict] = None,
) -> None:
    log_tenant_event(
        db,
        integration.tenant_id or ctx.tenant_id,
        getattr(user, "id", None),
        action,
        "password_vault_integration",
        str(integration.id),
        details or {},
        request,
    )


@router.get("", response_model=list[PasswordVaultIntegrationRead])
def list_password_vault_integrations(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[PasswordVaultIntegrationRead]:
    rows = _accessible_integrations(db, ctx).order_by(
        PasswordVaultIntegration.created_at.desc(),
        PasswordVaultIntegration.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=PasswordVaultIntegrationRead, status_code=status.HTTP_201_CREATED)
def create_password_vault_integration(
    payload: PasswordVaultIntegrationCreate,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> PasswordVaultIntegrationRead:
    tenant_id = _require_tenant(ctx)
    svc = _service(db, tenant_id)
    integration = PasswordVaultIntegration(
        type="password_vault",
        name=payload.integration_name,
        display_name=payload.integration_name,
        tenant_id=tenant_id,
        is_active=payload.is_active,
        health_status="unknown",
        provider=payload.provider,
        auth_method=payload.auth_method,
        token_encrypted=encrypt_vault_token(db, tenant_id, payload.token),
        token_preview=token_preview(payload.token),
        account_url=payload.account_url,
        account_email=payload.account_email,
        default_vault=payload.default_vault,
        default_vault_id=payload.default_vault_id,
        allowed_items_json=svc.serialize_allowed_items(payload.allowed_items),
        allowed_fields_json=svc.serialize_allowed_fields(payload.allowed_fields),
        allow_secret_read=payload.allow_secret_read,
        allow_totp_read=payload.allow_totp_read,
        allow_metadata_read=payload.allow_metadata_read,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    _audit(db, ctx, current_user, request, "password_vault.integration.create", integration, {
        "provider": integration.provider,
        "default_vault": integration.default_vault,
        "allowed_items_count": len(payload.allowed_items),
        "allowed_fields_count": len(payload.allowed_fields),
    })
    return _to_read(db, integration)


@router.patch("/{integration_id}", response_model=PasswordVaultIntegrationRead)
def update_password_vault_integration(
    integration_id: int,
    payload: PasswordVaultIntegrationUpdate,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> PasswordVaultIntegrationRead:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    data = payload.model_dump(exclude_unset=True)
    if data.get("service_account_token") and not data.get("token"):
        data["token"] = data["service_account_token"]
    if data.get("default_vault_name") and "default_vault" not in data:
        data["default_vault"] = data["default_vault_name"]
    svc = _service(db, tenant_id)
    if "integration_name" in data and data["integration_name"] is not None:
        integration.name = data["integration_name"]
        integration.display_name = data["integration_name"]
    if "token" in data and data["token"] is not None:
        integration.token_encrypted = encrypt_vault_token(db, tenant_id, data["token"])
        integration.token_preview = token_preview(data["token"])
        integration.health_status = "unknown"
        integration.health_status_reason = None
    if "provider" in data and data["provider"] is not None:
        provider = data["provider"].strip().lower()
        if provider not in _VALID_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"unsupported provider '{provider}'")
        integration.provider = provider
    if "auth_method" in data and data["auth_method"] is not None:
        auth_method = data["auth_method"].strip().lower()
        if auth_method not in _VALID_AUTH_METHODS:
            raise HTTPException(status_code=400, detail=f"unsupported auth method '{auth_method}'")
        integration.auth_method = auth_method
    if "account_url" in data:
        integration.account_url = data["account_url"]
    if "account_email" in data:
        integration.account_email = data["account_email"]
    if "default_vault" in data:
        integration.default_vault = data["default_vault"]
    if "default_vault_id" in data:
        integration.default_vault_id = data["default_vault_id"]
    if "allowed_items" in data and data["allowed_items"] is not None:
        integration.allowed_items_json = svc.serialize_allowed_items(data["allowed_items"])
    if "allowed_fields" in data and data["allowed_fields"] is not None:
        integration.allowed_fields_json = svc.serialize_allowed_fields(data["allowed_fields"])
    for key in ("allow_secret_read", "allow_totp_read", "allow_metadata_read", "is_active"):
        if key in data and data[key] is not None:
            setattr(integration, key, data[key])
    integration.updated_at = datetime.utcnow()
    db.add(integration)
    db.commit()
    db.refresh(integration)
    _audit(db, ctx, current_user, request, "password_vault.integration.update", integration, {
        "provider": integration.provider,
        "default_vault": integration.default_vault,
        "token_rotated": "token" in data,
    })
    return _to_read(db, integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_password_vault_integration(
    integration_id: int,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    integration = _load_or_404(db, ctx, integration_id)
    in_use_skill = db.query(AgentSkillIntegration.id).filter(
        AgentSkillIntegration.integration_id == integration.id,
        AgentSkillIntegration.skill_type == "password_vault",
    ).first()
    if in_use_skill is not None:
        raise HTTPException(
            status_code=409,
            detail="Password Vault integration is linked to one or more agent skills. Detach it from agents first.",
        )
    _audit(db, ctx, current_user, request, "password_vault.integration.delete", integration, {
        "provider": integration.provider,
        "default_vault": integration.default_vault,
    })
    db.delete(integration)
    db.commit()
    return None


@router.post("/{integration_id}/test")
def test_password_vault_integration(
    integration_id: int,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    try:
        result = _service(db, tenant_id).test_connection(integration)
    except PasswordVaultError as exc:
        integration.last_health_check = datetime.utcnow()
        integration.health_status = "unavailable"
        integration.health_status_reason = str(exc)[:500]
        db.add(integration)
        db.commit()
        _audit(db, ctx, current_user, request, "password_vault.integration.test", integration, {
            "success": False,
            "provider": integration.provider,
            "error": str(exc)[:120],
        })
        return {"success": False, "message": str(exc)}
    _audit(db, ctx, current_user, request, "password_vault.integration.test", integration, {
        "success": True,
        "provider": integration.provider,
        "vault_count": result.get("vault_count"),
        "configured_vault_found": result.get("configured_vault_found"),
    })
    result["success"] = True
    result["message"] = f"Connection resolved {result.get('vault_count', 0)} vault(s)."
    return result


@router.get("/{integration_id}/vaults")
def list_password_vaults(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    try:
        return {"vaults": _service(db, tenant_id).list_vaults(integration)}
    except PasswordVaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/items")
def list_password_vault_items(
    integration_id: int,
    vault: Optional[str] = None,
    vault_id: Optional[str] = None,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    try:
        return {"items": _service(db, tenant_id).list_items(integration, vault=vault or vault_id)}
    except PasswordVaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{integration_id}/secret-overrides", response_model=list[PasswordVaultSecretOverrideRead])
def list_password_vault_secret_overrides(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[PasswordVaultSecretOverrideRead]:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    return _service(db, tenant_id).list_secret_overrides(integration)


@router.post("/{integration_id}/secret-overrides", response_model=PasswordVaultSecretOverrideRead, status_code=status.HTTP_201_CREATED)
def upsert_password_vault_secret_override(
    integration_id: int,
    payload: PasswordVaultSecretOverrideRequest,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> PasswordVaultSecretOverrideRead:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    svc = _service(db, tenant_id)
    try:
        row = svc.upsert_secret_override(
            integration,
            vault=payload.vault,
            item_ref=payload.item_ref,
            field_name=payload.field_name,
            field_type=payload.field_type,
            value=payload.value,
        )
    except PasswordVaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(db, ctx, current_user, request, "password_vault.managed_secret.upsert", integration, {
        "vault": payload.vault,
        "item_ref": payload.item_ref,
        "field_name": payload.field_name,
        "field_type": payload.field_type,
    })
    return svc.serialize_secret_override(row)


@router.patch("/{integration_id}/secret-overrides/{secret_id}", response_model=PasswordVaultSecretOverrideRead)
def update_password_vault_secret_override(
    integration_id: int,
    secret_id: int,
    payload: PasswordVaultSecretOverrideUpdate,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> PasswordVaultSecretOverrideRead:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    svc = _service(db, tenant_id)
    try:
        row = svc.update_secret_override(
            integration,
            secret_id,
            vault=payload.vault,
            item_ref=payload.item_ref,
            field_name=payload.field_name,
            field_type=payload.field_type,
            value=payload.value,
        )
    except PasswordVaultError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(db, ctx, current_user, request, "password_vault.managed_secret.update", integration, {
        "secret_id": secret_id,
        "field_name": row.field_name,
    })
    return svc.serialize_secret_override(row)


@router.delete("/{integration_id}/secret-overrides/{secret_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_password_vault_secret_override(
    integration_id: int,
    secret_id: int,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    try:
        _service(db, tenant_id).delete_secret_override(integration, secret_id)
    except PasswordVaultError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _audit(db, ctx, current_user, request, "password_vault.managed_secret.delete", integration, {
        "secret_id": secret_id,
    })
    return None


@router.post("/{integration_id}/item-test")
def test_password_vault_item(
    integration_id: int,
    payload: PasswordVaultItemTestRequest,
    request: Request,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> dict:
    integration = _load_or_404(db, ctx, integration_id)
    tenant_id = integration.tenant_id
    svc = _service(db, tenant_id)
    resolved = _resolved_item_test(payload)
    item_ref = resolved.get("item_ref")
    if not item_ref:
        raise HTTPException(status_code=422, detail="item_ref, item_id, or op:// reference is required")
    try:
        if resolved["mode"] == "metadata":
            items = svc.list_items(integration, vault=resolved.get("vault"))
            matched = [
                item for item in items
                if item.get("title") == item_ref or item.get("id") == item_ref
            ]
            result = {"success": bool(matched), "matched_items": matched[:3], "redacted": True}
        elif resolved["mode"] == "totp":
            result = svc.read_totp(integration, item_ref=item_ref, vault=resolved.get("vault"), issue_handle=False)
        else:
            if not resolved.get("field_name"):
                raise PasswordVaultError("field_name_required")
            result = svc.read_field(
                integration,
                item_ref=item_ref,
                field_name=resolved.get("field_name"),
                vault=resolved.get("vault"),
                issue_handle=False,
            )
    except PasswordVaultError as exc:
        _audit(db, ctx, current_user, request, "password_vault.item.test", integration, {
            "success": False,
            "mode": resolved["mode"],
            "item_ref": item_ref,
            "field_name": resolved.get("field_name"),
            "error": str(exc)[:120],
        })
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _audit(db, ctx, current_user, request, "password_vault.item.test", integration, {
        "success": True,
        "mode": resolved["mode"],
        "item_ref": item_ref,
        "field_name": resolved.get("field_name"),
    })
    return result
