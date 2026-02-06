"""
Tenant SSO Configuration API Routes
Phase: User Management & SSO

Provides REST API endpoints for managing tenant SSO settings.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import json
import logging

from db import get_db
from models_rbac import User, Tenant, TenantSSOConfig, Role
from auth_dependencies import (
    get_current_user_required,
    require_permission,
    get_tenant_context,
    TenantContext,
)
from hub.security import TokenEncryption
from services.encryption_key_service import get_google_encryption_key
import settings

logger = logging.getLogger(__name__)


def _get_sso_encryptor(db: Session) -> TokenEncryption:
    """Get TokenEncryption instance for SSO client secret encryption."""
    encryption_key = get_google_encryption_key(db)
    return TokenEncryption(encryption_key.encode())


def _encrypt_client_secret(db: Session, tenant_id: str, secret: str) -> str:
    """Encrypt SSO client secret for storage."""
    encryptor = _get_sso_encryptor(db)
    identifier = f"sso_client_secret_{tenant_id}"
    return encryptor.encrypt(secret, identifier)


def _decrypt_client_secret(db: Session, tenant_id: str, encrypted_secret: str) -> str:
    """Decrypt SSO client secret for use."""
    encryptor = _get_sso_encryptor(db)
    identifier = f"sso_client_secret_{tenant_id}"
    return encryptor.decrypt(encrypted_secret, identifier)
router = APIRouter(prefix="/api/settings/sso", tags=["sso-config"])


# Request/Response Models
class SSOConfigResponse(BaseModel):
    id: int
    tenant_id: str
    google_sso_enabled: bool
    google_client_id: Optional[str] = None
    has_client_secret: bool = False
    allowed_domains: List[str] = []
    auto_provision_users: bool
    default_role_id: Optional[int] = None
    default_role_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SSOConfigUpdate(BaseModel):
    google_sso_enabled: Optional[bool] = None
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None  # Only set to update, never returned
    allowed_domains: Optional[List[str]] = None
    auto_provision_users: Optional[bool] = None
    default_role_id: Optional[int] = None


class PlatformSSOStatus(BaseModel):
    platform_sso_available: bool
    tenant_can_use_platform_sso: bool
    tenant_has_custom_credentials: bool


# Helper functions
def config_to_response(config: SSOConfigResponse, db: Session) -> SSOConfigResponse:
    """Convert SSO config to response format."""
    # Parse allowed domains
    allowed_domains = []
    if config.allowed_domains:
        try:
            allowed_domains = json.loads(config.allowed_domains)
        except json.JSONDecodeError:
            allowed_domains = []

    # Get default role name
    default_role_name = None
    if config.default_role_id:
        role = db.query(Role).filter(Role.id == config.default_role_id).first()
        if role:
            default_role_name = role.display_name

    return SSOConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        google_sso_enabled=config.google_sso_enabled,
        google_client_id=config.google_client_id,
        has_client_secret=bool(config.google_client_secret_encrypted),  # MED-007: Use encrypted column
        allowed_domains=allowed_domains,
        auto_provision_users=config.auto_provision_users,
        default_role_id=config.default_role_id,
        default_role_name=default_role_name,
        created_at=config.created_at.isoformat() if config.created_at else None,
        updated_at=config.updated_at.isoformat() if config.updated_at else None,
    )


@router.get("/status", response_model=PlatformSSOStatus)
async def get_platform_sso_status(
    current_user: User = Depends(get_current_user_required),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Check if platform-wide SSO is available.

    Returns information about SSO availability for the current tenant.
    """
    platform_available = bool(settings.GOOGLE_SSO_CLIENT_ID and settings.GOOGLE_SSO_CLIENT_SECRET)

    # Check if tenant has custom credentials
    config = db.query(TenantSSOConfig).filter(
        TenantSSOConfig.tenant_id == tenant_context.tenant_id
    ).first()

    has_custom = bool(config and config.google_client_id and config.google_client_secret_encrypted)  # MED-007

    return PlatformSSOStatus(
        platform_sso_available=platform_available,
        tenant_can_use_platform_sso=platform_available,
        tenant_has_custom_credentials=has_custom,
    )


@router.get("/", response_model=Optional[SSOConfigResponse])
async def get_sso_config(
    current_user: User = Depends(get_current_user_required),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("org.settings.read")),
):
    """
    Get current tenant's SSO configuration.
    """
    # For global admins, use their assigned tenant_id (not the context which is None)
    tenant_id = current_user.tenant_id if current_user.is_global_admin else tenant_context.tenant_id

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant assigned. SSO configuration requires a tenant context."
        )

    config = db.query(TenantSSOConfig).filter(
        TenantSSOConfig.tenant_id == tenant_id
    ).first()

    if not config:
        # Return default config if none exists
        return SSOConfigResponse(
            id=0,
            tenant_id=tenant_id,
            google_sso_enabled=False,
            google_client_id=None,
            has_client_secret=False,
            allowed_domains=[],
            auto_provision_users=False,
            default_role_id=None,
            default_role_name=None,
            created_at=None,
            updated_at=None,
        )

    return config_to_response(config, db)


@router.put("/", response_model=SSOConfigResponse)
async def update_sso_config(
    request: SSOConfigUpdate,
    current_user: User = Depends(get_current_user_required),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("org.settings.write")),
):
    """
    Update tenant's SSO configuration.

    Requires 'settings:update' permission (typically owner or admin).
    """
    # For global admins, use their assigned tenant_id
    tenant_id = current_user.tenant_id if current_user.is_global_admin else tenant_context.tenant_id

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant assigned. SSO configuration requires a tenant context."
        )

    # Get or create config
    config = db.query(TenantSSOConfig).filter(
        TenantSSOConfig.tenant_id == tenant_id
    ).first()

    if not config:
        config = TenantSSOConfig(tenant_id=tenant_id)
        db.add(config)

    # Update fields
    if request.google_sso_enabled is not None:
        config.google_sso_enabled = request.google_sso_enabled

    if request.google_client_id is not None:
        config.google_client_id = request.google_client_id or None

    if request.google_client_secret is not None:
        if request.google_client_secret:
            # MED-007 Security Fix: Encrypt the client secret before storing
            encrypted_secret = _encrypt_client_secret(db, tenant_id, request.google_client_secret)
            config.google_client_secret_encrypted = encrypted_secret
        else:
            config.google_client_secret_encrypted = None

    if request.allowed_domains is not None:
        config.allowed_domains = json.dumps(request.allowed_domains) if request.allowed_domains else None

    if request.auto_provision_users is not None:
        config.auto_provision_users = request.auto_provision_users

    if request.default_role_id is not None:
        # Validate role exists
        if request.default_role_id:
            role = db.query(Role).filter(Role.id == request.default_role_id).first()
            if not role:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid role ID"
                )
        config.default_role_id = request.default_role_id or None

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    logger.info(f"SSO config updated for tenant: {tenant_id}")

    return config_to_response(config, db)


@router.delete("/credentials")
async def delete_sso_credentials(
    current_user: User = Depends(get_current_user_required),
    tenant_context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
    _: None = Depends(require_permission("org.settings.write")),
):
    """
    Delete tenant's custom SSO credentials.

    This will revert to using platform-wide SSO if available.
    """
    # For global admins, use their assigned tenant_id
    tenant_id = current_user.tenant_id if current_user.is_global_admin else tenant_context.tenant_id

    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant assigned. SSO configuration requires a tenant context."
        )

    config = db.query(TenantSSOConfig).filter(
        TenantSSOConfig.tenant_id == tenant_id
    ).first()

    if config:
        config.google_client_id = None
        config.google_client_secret_encrypted = None  # MED-007
        config.updated_at = datetime.utcnow()
        db.commit()

    return {"message": "SSO credentials deleted"}


@router.get("/roles")
async def get_available_roles_for_sso(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Get available roles that can be assigned to auto-provisioned users.
    """
    roles = db.query(Role).all()

    return [
        {
            "id": role.id,
            "name": role.name,
            "display_name": role.display_name,
            "description": role.description,
        }
        for role in roles
    ]
