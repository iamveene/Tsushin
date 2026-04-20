"""
Global SSO Configuration API Routes

Provides REST API endpoints for global admins to manage the platform-wide
Google SSO configuration (singleton). This is used when a user signs in via
Google without a tenant context (e.g. accepting a global-admin invitation).

Mirrors the encryption pattern used in ``backend/api/routes_sso_config.py``
(Fernet via ``services.encryption_key_service.get_google_encryption_key``),
with a single well-known identifier string for the envelope — there is no
tenant ID for the global config.

Endpoints:
    GET /api/admin/sso-config         — fetch current config (secret masked)
    PUT /api/admin/sso-config         — upsert config
    DELETE /api/admin/sso-config/credentials — clear credentials

All endpoints require global admin privileges.
"""

from datetime import datetime
from typing import List, Optional
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import GlobalSSOConfig, Role, User
from auth_dependencies import require_global_admin
from hub.security import TokenEncryption
from services.audit_service import AuditActions, log_admin_action
from services.encryption_key_service import get_google_encryption_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/sso-config", tags=["admin-sso"])

# Identifier passed into the Fernet envelope — mirrors the per-tenant
# ``sso_client_secret_{tenant_id}`` scheme used in routes_sso_config.py but
# with a fixed well-known suffix because there is no tenant.
_GLOBAL_SECRET_IDENTIFIER = "sso_client_secret_global"


def _get_encryptor(db: Session) -> TokenEncryption:
    key = get_google_encryption_key(db)
    return TokenEncryption(key.encode())


def _encrypt_secret(db: Session, secret: str) -> str:
    return _get_encryptor(db).encrypt(secret, _GLOBAL_SECRET_IDENTIFIER)


def _decrypt_secret(db: Session, encrypted_secret: str) -> str:
    return _get_encryptor(db).decrypt(encrypted_secret, _GLOBAL_SECRET_IDENTIFIER)


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class GlobalSSOConfigResponse(BaseModel):
    id: int
    google_sso_enabled: bool
    google_client_id: Optional[str] = None
    has_client_secret: bool = False
    google_client_secret: Optional[str] = None  # Only populated with ?include_secret=true
    allowed_domains: List[str] = []
    auto_provision_users: bool
    default_role_id: Optional[int] = None
    default_role_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class GlobalSSOConfigUpdate(BaseModel):
    google_sso_enabled: Optional[bool] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None  # Write-only
    allowed_domains: Optional[List[str]] = None
    auto_provision_users: Optional[bool] = None
    default_role_id: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_or_create_singleton(db: Session) -> GlobalSSOConfig:
    cfg = db.query(GlobalSSOConfig).first()
    if not cfg:
        cfg = GlobalSSOConfig(
            google_sso_enabled=False,
            auto_provision_users=False,
        )
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def _config_to_response(
    cfg: GlobalSSOConfig,
    db: Session,
    include_secret: bool = False,
) -> GlobalSSOConfigResponse:
    allowed_domains: List[str] = []
    if cfg.allowed_domains:
        try:
            parsed = json.loads(cfg.allowed_domains)
            if isinstance(parsed, list):
                allowed_domains = [str(x) for x in parsed]
        except json.JSONDecodeError:
            allowed_domains = []

    default_role_name = None
    if cfg.default_role_id:
        role = db.query(Role).filter(Role.id == cfg.default_role_id).first()
        if role:
            default_role_name = role.display_name

    secret_plain: Optional[str] = None
    if include_secret and cfg.google_client_secret_encrypted:
        try:
            secret_plain = _decrypt_secret(db, cfg.google_client_secret_encrypted)
        except Exception as e:
            logger.warning("Failed to decrypt global SSO secret: %s", e)

    return GlobalSSOConfigResponse(
        id=cfg.id,
        google_sso_enabled=bool(cfg.google_sso_enabled),
        google_client_id=cfg.google_client_id,
        has_client_secret=bool(cfg.google_client_secret_encrypted),
        google_client_secret=secret_plain,
        allowed_domains=allowed_domains,
        auto_provision_users=bool(cfg.auto_provision_users),
        default_role_id=cfg.default_role_id,
        default_role_name=default_role_name,
        created_at=cfg.created_at.isoformat() if cfg.created_at else None,
        updated_at=cfg.updated_at.isoformat() if cfg.updated_at else None,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=GlobalSSOConfigResponse, include_in_schema=False)
@router.get("/", response_model=GlobalSSOConfigResponse)
async def get_global_sso_config(
    include_secret: bool = Query(False, description="Include decrypted client secret"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    cfg = _get_or_create_singleton(db)
    return _config_to_response(cfg, db, include_secret=include_secret)


@router.put("", response_model=GlobalSSOConfigResponse, include_in_schema=False)
@router.put("/", response_model=GlobalSSOConfigResponse)
async def update_global_sso_config(
    payload: GlobalSSOConfigUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    cfg = _get_or_create_singleton(db)

    if payload.google_sso_enabled is not None:
        cfg.google_sso_enabled = payload.google_sso_enabled

    if payload.google_client_id is not None:
        cfg.google_client_id = payload.google_client_id or None

    if payload.google_client_secret is not None:
        if payload.google_client_secret:
            cfg.google_client_secret_encrypted = _encrypt_secret(db, payload.google_client_secret)
        else:
            cfg.google_client_secret_encrypted = None

    if payload.allowed_domains is not None:
        cfg.allowed_domains = (
            json.dumps(payload.allowed_domains) if payload.allowed_domains else None
        )

    if payload.auto_provision_users is not None:
        cfg.auto_provision_users = payload.auto_provision_users

    if payload.default_role_id is not None:
        if payload.default_role_id:
            role = db.query(Role).filter(Role.id == payload.default_role_id).first()
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role ID",
                )
        cfg.default_role_id = payload.default_role_id or None

    cfg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cfg)

    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.SSO_CONFIG_UPDATE,
        resource_type="global_sso_config",
        resource_id=str(cfg.id),
        details={
            "google_sso_enabled": bool(cfg.google_sso_enabled),
            "has_client_id": bool(cfg.google_client_id),
            "has_client_secret": bool(cfg.google_client_secret_encrypted),
            "auto_provision_users": bool(cfg.auto_provision_users),
        },
        request=request,
    )

    logger.info("Global SSO config updated by admin id=%s", current_user.id)
    return _config_to_response(cfg, db)


@router.delete("/credentials")
async def delete_global_sso_credentials(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    cfg = _get_or_create_singleton(db)
    cfg.google_client_id = None
    cfg.google_client_secret_encrypted = None
    cfg.updated_at = datetime.utcnow()
    db.commit()

    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.SSO_CONFIG_DELETE,
        resource_type="global_sso_config",
        resource_id=str(cfg.id),
        request=request,
    )

    return {"message": "Global SSO credentials deleted"}
