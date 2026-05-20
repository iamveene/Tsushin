"""Retired legacy Service API Keys routes.

The legacy ``api_key`` table is audit/migration-only. Runtime credentials are
stored in typed models such as ProviderInstance, TTSInstance, SearchProvider,
GoogleFlightsIntegration, AmadeusIntegration, and SearxngInstance.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from models_rbac import User


router = APIRouter()

_engine = None


def set_engine(engine):
    """Set the global engine reference for app startup compatibility."""
    global _engine
    _engine = engine


def _legacy_api_keys_gone() -> None:
    raise HTTPException(
        status_code=410,
        detail=(
            "Legacy Service API Keys are retired. Use Provider Instances or "
            "typed Hub integrations instead."
        ),
    )


@router.get("/api-keys", status_code=410)
def list_api_keys(
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()


@router.get("/api-keys/services", status_code=410)
def list_supported_services(
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()


@router.get("/api-keys/{service}", status_code=410)
def get_api_key_route(
    service: str,
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()


@router.post("/api-keys", status_code=410)
def create_or_update_api_key(
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()


@router.put("/api-keys/{service}", status_code=410)
def update_api_key(
    service: str,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()


@router.delete("/api-keys/{service}", status_code=410)
def delete_api_key(
    service: str,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    _legacy_api_keys_gone()
