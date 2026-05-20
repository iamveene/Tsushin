"""
Hub Providers — catalog endpoints for the "Add Integration" wizard.

These endpoints expose the backend provider registries (search + flight/travel)
as flat catalogs the frontend AddIntegrationWizard can render without shipping
a hardcoded list. They mirror the shape of /api/tts-providers and add a
`tenant_has_configured` boolean so the UI can badge already-configured cards.

Endpoints
---------
GET /api/hub/search-providers   — SearchProviderRegistry catalog (brave, searxng, …)
GET /api/hub/travel-providers   — FlightProviderRegistry catalog (amadeus, google_flights, …)

Both require the `hub.read` permission and are tenant-scoped for the
`tenant_has_configured` check (API keys, SearXNG instances, Amadeus / Google
Flights integrations are all tenant-owned).

Drift guard: backend/tests/test_wizard_drift.py cross-checks these registries
against the static fallback array in AddIntegrationWizard.tsx, so a new
provider can never ship backend-only.
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models import GoogleOAuthCredentials, HubIntegration, SearxngInstance
from models_rbac import User
from auth_dependencies import require_permission, get_tenant_context, TenantContext
from hub.productivity_catalog import PRODUCTIVITY_CATALOG
from hub.providers import SearchProviderRegistry, FlightProviderRegistry
from services.google_flights_integration_service import configure_google_flights_integration
from services.search_provider_integration_service import (
    configure_search_provider,
    has_search_provider_credentials,
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hub", tags=["Hub Providers"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------

class ProviderCatalogEntry(BaseModel):
    """One row in a provider catalog (search or travel)."""
    id: str
    name: str
    description: Optional[str] = None
    status: str = "available"  # "available" | "coming_soon" | …
    requires_api_key: bool = True
    is_free: bool = False
    tenant_has_configured: bool = False


class ProviderCredentialRequest(BaseModel):
    api_key: str
    default_country: Optional[str] = None
    default_language: Optional[str] = None
    default_currency: Optional[str] = None


# ---------------------------------------------------------------------------
# Tenant-config probes
# ---------------------------------------------------------------------------

def _search_tenant_has_configured(provider_id: str, tenant_id: Optional[str], db: Session) -> bool:
    """Best-effort check: does this tenant already have credentials/provisioning
    for this search provider?"""
    if provider_id == "searxng":
        q = db.query(SearxngInstance).filter(SearxngInstance.is_active == True)
        if tenant_id is not None:
            q = q.filter(SearxngInstance.tenant_id == tenant_id)
        return q.first() is not None

    return has_search_provider_credentials(provider_id, tenant_id, db)


def _travel_tenant_has_configured(provider_id: str, tenant_id: Optional[str], db: Session) -> bool:
    """For flight providers, only an active typed HubIntegration counts."""
    q = db.query(HubIntegration).filter(
        HubIntegration.type == provider_id,
        HubIntegration.is_active == True,
    )
    if tenant_id is not None:
        q = q.filter(HubIntegration.tenant_id == tenant_id)
    return q.first() is not None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/search-providers", response_model=List[ProviderCatalogEntry])
def list_search_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    List every registered search provider with catalog metadata.

    Used by the Hub's "Add Integration" wizard to render provider cards
    without shipping a hardcoded list. Each row includes a
    `tenant_has_configured` boolean so the UI can badge configured providers.
    """
    try:
        SearchProviderRegistry.initialize_providers()
        providers = SearchProviderRegistry.list_providers(db, tenant_id=ctx.tenant_id)

        out: List[ProviderCatalogEntry] = []
        for p in providers:
            pid = p["id"]
            config = SearchProviderRegistry.get_provider_config(pid) or {}
            description = (
                config.get("description")
                or (p.get("pricing") or {}).get("description")
                or None
            )
            out.append(
                ProviderCatalogEntry(
                    id=pid,
                    name=p["name"],
                    description=description,
                    status=p.get("status", "available"),
                    requires_api_key=bool(p.get("requires_api_key", True)),
                    is_free=bool((p.get("pricing") or {}).get("is_free", False)),
                    tenant_has_configured=_search_tenant_has_configured(
                        pid, ctx.tenant_id, db
                    ),
                )
            )
        return out
    except Exception as e:
        logger.exception(f"Failed to list search providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list search providers",
        )


@router.post("/search-providers/{provider_id}/configure", response_model=ProviderCatalogEntry)
def configure_hosted_search_provider(
    provider_id: str,
    data: ProviderCredentialRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required")
    try:
        SearchProviderRegistry.initialize_providers()
        config = SearchProviderRegistry.get_provider_config(provider_id) or {}
        row = configure_search_provider(
            provider_id=provider_id,
            tenant_id=ctx.tenant_id,
            api_key=data.api_key,
            db=db,
            default_country=data.default_country or "US",
            default_language=data.default_language or "en",
        )
        return ProviderCatalogEntry(
            id=row.provider_id,
            name=config.get("name") or row.display_name or row.name,
            description=config.get("description"),
            status="available",
            requires_api_key=True,
            is_free=bool((config.get("pricing") or {}).get("is_free", False)),
            tenant_has_configured=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to configure search provider %s", provider_id)
        raise HTTPException(status_code=500, detail="Failed to configure search provider") from exc


# Per-provider human-friendly defaults for flight registry rows (registry
# stores only id + class today; UI needs a short blurb).
_TRAVEL_DESCRIPTIONS: Dict[str, str] = {
    "amadeus": "Live flight search via Amadeus self-service APIs (test or production).",
    "google_flights": "Google Flights via a tenant-scoped SerpAPI credential.",
}

_TRAVEL_REQUIRES_API_KEY: Dict[str, bool] = {
    "amadeus": True,
    "google_flights": True,
}


class ProductivityServiceEntry(BaseModel):
    """One row in the productivity-services catalog."""
    id: str
    name: str
    description: Optional[str] = None
    category: str               # "calendar" | "email" | "tasks" | …
    vendor: str                 # "google" | "asana" | …
    requires_oauth: bool = False
    oauth_provider: str = ""    # drives credential-step reuse
    integration_type: str       # HubIntegration.type
    icon_hint: str
    status: str = "available"
    tenant_has_configured: bool = False
    tenant_has_oauth_credentials: bool = False  # e.g. GoogleOAuthCredentials row


def _productivity_tenant_has_configured(
    integration_type: str, tenant_id: Optional[str], db: Session
) -> bool:
    """Has this tenant created at least one active integration row of the
    given polymorphic type? Used to badge the productivity wizard cards.

    ``integration_type`` matches ``HubIntegration.type`` (e.g. 'gmail',
    'calendar', 'asana'); everything lives under the shared hub_integration
    table with a polymorphic identity."""
    q = db.query(HubIntegration).filter(
        HubIntegration.type == integration_type,
        HubIntegration.is_active == True,
    )
    if tenant_id is not None:
        q = q.filter(HubIntegration.tenant_id == tenant_id)
    return q.first() is not None


def _tenant_has_google_oauth(tenant_id: Optional[str], db: Session) -> bool:
    """True if the tenant has uploaded a Google OAuth client_id/secret pair.

    The guided wizard uses this to skip the 'Upload Google credentials' step
    when credentials already exist tenant-wide, so successive Google-backed
    integrations (Gmail + Calendar) don't re-ask for the same secret."""
    if tenant_id is None:
        return False
    return db.query(GoogleOAuthCredentials.id).filter(
        GoogleOAuthCredentials.tenant_id == tenant_id
    ).first() is not None


@router.get("/productivity-services", response_model=List[ProductivityServiceEntry])
def list_productivity_services(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Catalog endpoint for the Hub > Productivity guided wizard.

    Lists every productivity service (calendar / email / tasks / knowledge-
    base) known to the backend. Each entry is annotated with per-tenant
    state so the wizard can (a) render only unconfigured services in its
    picker step, and (b) skip credential-upload steps when a Google OAuth
    client is already on file.
    """
    try:
        has_google_oauth = _tenant_has_google_oauth(ctx.tenant_id, db)
        out: List[ProductivityServiceEntry] = []
        for svc in PRODUCTIVITY_CATALOG:
            out.append(
                ProductivityServiceEntry(
                    id=svc.id,
                    name=svc.display_name,
                    description=svc.description,
                    category=svc.category,
                    vendor=svc.vendor,
                    requires_oauth=svc.requires_oauth,
                    oauth_provider=svc.oauth_provider,
                    integration_type=svc.integration_type,
                    icon_hint=svc.icon_hint,
                    status=svc.status,
                    tenant_has_configured=_productivity_tenant_has_configured(
                        svc.integration_type, ctx.tenant_id, db
                    ),
                    tenant_has_oauth_credentials=(
                        has_google_oauth if svc.oauth_provider == "google" else False
                    ),
                )
            )
        return out
    except Exception as e:
        logger.exception(f"Failed to list productivity services: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list productivity services",
        )


@router.get("/travel-providers", response_model=List[ProviderCatalogEntry])
def list_travel_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    List every registered flight/travel provider with catalog metadata.

    Mirrors /api/hub/search-providers. The FlightProviderRegistry doesn't
    currently store descriptions, so we provide short per-provider blurbs here
    and let the frontend override with richer copy if it wants.
    """
    try:
        FlightProviderRegistry.initialize_providers()
        providers = FlightProviderRegistry.list_available_providers(db)

        out: List[ProviderCatalogEntry] = []
        for p in providers:
            pid = p["id"]
            out.append(
                ProviderCatalogEntry(
                    id=pid,
                    name=p["name"],
                    description=_TRAVEL_DESCRIPTIONS.get(pid),
                    status="available",
                    requires_api_key=_TRAVEL_REQUIRES_API_KEY.get(pid, True),
                    is_free=False,
                    tenant_has_configured=_travel_tenant_has_configured(
                        pid, ctx.tenant_id, db
                    ),
                )
            )
        return out
    except Exception as e:
        logger.exception(f"Failed to list travel providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list travel providers",
        )


@router.post("/travel-providers/google_flights/configure", response_model=ProviderCatalogEntry)
def configure_google_flights_provider(
    data: ProviderCredentialRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    if not ctx.tenant_id:
        raise HTTPException(status_code=400, detail="Tenant context is required")
    try:
        configure_google_flights_integration(
            tenant_id=ctx.tenant_id,
            api_key=data.api_key,
            db=db,
            default_currency=data.default_currency or "USD",
            default_language=data.default_language or "en",
        )
        return ProviderCatalogEntry(
            id="google_flights",
            name="Google Flights",
            description=_TRAVEL_DESCRIPTIONS["google_flights"],
            status="available",
            requires_api_key=True,
            is_free=False,
            tenant_has_configured=True,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Failed to configure Google Flights")
        raise HTTPException(status_code=500, detail="Failed to configure Google Flights") from exc
