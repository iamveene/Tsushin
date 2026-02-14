"""
Google Integration API Routes

Provides endpoints for:
- Google OAuth credentials configuration (BYOT)
- Gmail integration OAuth flow and management
- Calendar integration OAuth flow and management
- Multi-account support per tenant

All endpoints require tenant authentication.
"""

import os
import logging
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

import settings
from db import get_db as get_session
from auth_dependencies import TenantContext, get_tenant_context as get_current_tenant_context
from models import (
    GoogleOAuthCredentials,
    GmailIntegration,
    CalendarIntegration,
    HubIntegration,
    OAuthToken,
)
from hub.google import GoogleOAuthHandler, get_google_oauth_handler, GmailService, CalendarService
from hub.security import TokenEncryption
from services.encryption_key_service import get_google_encryption_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hub/google", tags=["Google Integration"])


# ============================================
# Pydantic Models
# ============================================

class GoogleCredentialsCreate(BaseModel):
    """Request body for creating Google OAuth credentials."""
    client_id: str
    client_secret: str
    redirect_uri: Optional[str] = None


class GoogleCredentialsResponse(BaseModel):
    """Response for Google OAuth credentials."""
    id: int
    tenant_id: str
    client_id: str
    redirect_uri: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IntegrationResponse(BaseModel):
    """Response for Gmail/Calendar integration."""
    id: int
    type: str
    name: str
    display_name: Optional[str]
    email_address: str
    is_active: bool
    authorized_at: datetime
    health_status: str
    health_status_reason: Optional[str] = None

    class Config:
        from_attributes = True


class IntegrationListResponse(BaseModel):
    """Response for listing integrations."""
    integrations: List[IntegrationResponse]
    count: int


class OAuthAuthorizeResponse(BaseModel):
    """Response for OAuth authorization URL."""
    authorization_url: str
    state: str


class IntegrationUpdateRequest(BaseModel):
    """Request for updating integration."""
    display_name: Optional[str] = None
    default_calendar_id: Optional[str] = None  # For calendar only
    timezone: Optional[str] = None  # For calendar only


# ============================================
# Helper Functions
# ============================================

def get_encryption_key(db: Session) -> str:
    """Get encryption key from database or environment."""
    key = get_google_encryption_key(db)
    if not key:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_ENCRYPTION_KEY not configured in database or environment"
        )
    return key


# ============================================
# Google OAuth Credentials (BYOT)
# ============================================

@router.get("/credentials", response_model=GoogleCredentialsResponse)
async def get_credentials(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Get Google OAuth credentials for the tenant.

    Returns the configured Google Cloud OAuth app credentials.
    The client_secret is not returned for security.
    """
    credentials = db.query(GoogleOAuthCredentials).filter(
        GoogleOAuthCredentials.tenant_id == ctx.tenant_id
    ).first()

    if not credentials:
        raise HTTPException(
            status_code=404,
            detail="Google credentials not configured. Please configure in Hub settings."
        )

    return credentials


@router.post("/credentials", response_model=GoogleCredentialsResponse)
async def create_or_update_credentials(
    data: GoogleCredentialsCreate,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Create or update Google OAuth credentials for the tenant.

    Each tenant configures their own Google Cloud project credentials.
    This enables multi-tenant isolation.
    """
    encryption_key = get_encryption_key(db)
    token_encryption = TokenEncryption(encryption_key.encode())

    # Encrypt client secret
    encrypted_secret = token_encryption.encrypt(data.client_secret, ctx.tenant_id)

    # Check for existing
    existing = db.query(GoogleOAuthCredentials).filter(
        GoogleOAuthCredentials.tenant_id == ctx.tenant_id
    ).first()

    if existing:
        # Update
        existing.client_id = data.client_id
        existing.client_secret_encrypted = encrypted_secret
        existing.redirect_uri = data.redirect_uri
        existing.updated_at = datetime.utcnow()
        credentials = existing
        logger.info(f"Updated Google credentials for tenant {ctx.tenant_id}")
    else:
        # Create
        credentials = GoogleOAuthCredentials(
            tenant_id=ctx.tenant_id,
            client_id=data.client_id,
            client_secret_encrypted=encrypted_secret,
            redirect_uri=data.redirect_uri,
            created_by=ctx.user.id,
        )
        db.add(credentials)
        logger.info(f"Created Google credentials for tenant {ctx.tenant_id}")

    db.commit()
    db.refresh(credentials)

    return credentials


@router.delete("/credentials")
async def delete_credentials(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Delete Google OAuth credentials for the tenant.

    WARNING: This will invalidate all Gmail and Calendar integrations!
    """
    credentials = db.query(GoogleOAuthCredentials).filter(
        GoogleOAuthCredentials.tenant_id == ctx.tenant_id
    ).first()

    if not credentials:
        raise HTTPException(status_code=404, detail="Credentials not found")

    db.delete(credentials)
    db.commit()

    logger.info(f"Deleted Google credentials for tenant {ctx.tenant_id}")

    return {"status": "deleted"}


# ============================================
# Gmail Integrations
# ============================================

@router.get("/gmail/integrations", response_model=IntegrationListResponse)
async def list_gmail_integrations(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    List all Gmail integrations for the tenant.

    Returns all connected Gmail accounts.
    """
    integrations = db.query(GmailIntegration).join(HubIntegration).filter(
        HubIntegration.tenant_id == ctx.tenant_id,
        HubIntegration.type == 'gmail'
    ).all()

    result = []
    for integration in integrations:
        base = db.query(HubIntegration).filter(HubIntegration.id == integration.id).first()
        result.append(IntegrationResponse(
            id=integration.id,
            type='gmail',
            name=base.name if base else f"Gmail - {integration.email_address}",
            display_name=base.display_name if base else None,
            email_address=integration.email_address,
            is_active=base.is_active if base else True,
            authorized_at=integration.authorized_at,
            health_status=base.health_status if base else "unknown",
            health_status_reason=getattr(base, 'health_status_reason', None) if base else None
        ))

    return IntegrationListResponse(integrations=result, count=len(result))


@router.post("/gmail/oauth/authorize", response_model=OAuthAuthorizeResponse)
async def gmail_oauth_authorize(
    display_name: Optional[str] = Query(None, description="User-friendly name for this account"),
    login_hint: Optional[str] = Query(None, description="Email hint for account selector"),
    redirect_url: Optional[str] = Query(None, description="URL to redirect after OAuth"),
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Start Gmail OAuth flow.

    Returns authorization URL to redirect user to Google sign-in.
    """
    try:
        handler = get_google_oauth_handler(db, ctx.tenant_id)

        auth_url, state = await handler.generate_authorization_url(
            integration_type="gmail",
            redirect_url=redirect_url,
            display_name=display_name,
            login_hint=login_hint
        )

        return OAuthAuthorizeResponse(authorization_url=auth_url, state=state)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/gmail/oauth/disconnect/{integration_id}")
async def gmail_oauth_disconnect(
    integration_id: int,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Disconnect a Gmail integration.

    Revokes OAuth tokens and deactivates the integration.
    """
    # Verify ownership
    integration = db.query(GmailIntegration).join(HubIntegration).filter(
        GmailIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        handler = get_google_oauth_handler(db, ctx.tenant_id)
        await handler.disconnect_integration(integration_id)

        return {"status": "disconnected", "integration_id": integration_id}

    except Exception as e:
        logger.error(f"Error disconnecting Gmail integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/gmail/{integration_id}")
async def update_gmail_integration(
    integration_id: int,
    data: IntegrationUpdateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Update Gmail integration settings.

    Currently only supports updating display_name.
    """
    # Verify ownership
    integration = db.query(GmailIntegration).join(HubIntegration).filter(
        GmailIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    base = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()

    if data.display_name is not None:
        if base:
            base.display_name = data.display_name

    db.commit()

    return {"status": "updated", "integration_id": integration_id}


# ============================================
# Calendar Integrations
# ============================================

@router.get("/calendar/integrations", response_model=IntegrationListResponse)
async def list_calendar_integrations(
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    List all Calendar integrations for the tenant.

    Returns all connected Google Calendar accounts.
    """
    integrations = db.query(CalendarIntegration).join(HubIntegration).filter(
        HubIntegration.tenant_id == ctx.tenant_id,
        HubIntegration.type == 'calendar'
    ).all()

    result = []
    for integration in integrations:
        base = db.query(HubIntegration).filter(HubIntegration.id == integration.id).first()
        result.append(IntegrationResponse(
            id=integration.id,
            type='calendar',
            name=base.name if base else f"Calendar - {integration.email_address}",
            display_name=base.display_name if base else None,
            email_address=integration.email_address,
            is_active=base.is_active if base else True,
            authorized_at=integration.authorized_at,
            health_status=base.health_status if base else "unknown",
            health_status_reason=getattr(base, 'health_status_reason', None) if base else None
        ))

    return IntegrationListResponse(integrations=result, count=len(result))


@router.post("/calendar/oauth/authorize", response_model=OAuthAuthorizeResponse)
async def calendar_oauth_authorize(
    display_name: Optional[str] = Query(None, description="User-friendly name for this calendar"),
    login_hint: Optional[str] = Query(None, description="Email hint for account selector"),
    redirect_url: Optional[str] = Query(None, description="URL to redirect after OAuth"),
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Start Calendar OAuth flow.

    Returns authorization URL to redirect user to Google sign-in.
    """
    try:
        handler = get_google_oauth_handler(db, ctx.tenant_id)

        auth_url, state = await handler.generate_authorization_url(
            integration_type="calendar",
            redirect_url=redirect_url,
            display_name=display_name,
            login_hint=login_hint
        )

        return OAuthAuthorizeResponse(authorization_url=auth_url, state=state)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/calendar/oauth/disconnect/{integration_id}")
async def calendar_oauth_disconnect(
    integration_id: int,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Disconnect a Calendar integration.

    Revokes OAuth tokens and deactivates the integration.
    """
    # Verify ownership
    integration = db.query(CalendarIntegration).join(HubIntegration).filter(
        CalendarIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        handler = get_google_oauth_handler(db, ctx.tenant_id)
        await handler.disconnect_integration(integration_id)

        return {"status": "disconnected", "integration_id": integration_id}

    except Exception as e:
        logger.error(f"Error disconnecting Calendar integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/calendar/{integration_id}")
async def update_calendar_integration(
    integration_id: int,
    data: IntegrationUpdateRequest,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Update Calendar integration settings.

    Supports updating:
    - display_name
    - default_calendar_id
    - timezone
    """
    # Verify ownership
    integration = db.query(CalendarIntegration).join(HubIntegration).filter(
        CalendarIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    base = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()

    if data.display_name is not None:
        if base:
            base.display_name = data.display_name

    if data.default_calendar_id is not None:
        integration.default_calendar_id = data.default_calendar_id

    if data.timezone is not None:
        integration.timezone = data.timezone

    db.commit()

    return {"status": "updated", "integration_id": integration_id}


# ============================================
# OAuth Callback (shared for Gmail and Calendar)
# ============================================

@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: str = Query(..., description="State token for CSRF validation"),
    db: Session = Depends(get_session)
):
    """
    OAuth callback handler for both Gmail and Calendar.

    Google redirects here after user authorizes access.
    The state token determines which tenant and integration type.
    """
    try:
        # Validate state and get metadata
        from hub.security import OAuthStateManager
        state_manager = OAuthStateManager(db)

        # Get state data without consuming (to extract tenant info)
        from models import OAuthState
        state_record = db.query(OAuthState).filter(
            OAuthState.state_token == state
        ).first()

        if not state_record:
            raise HTTPException(status_code=400, detail="Invalid or expired state token")

        # Extract integration_type from state
        integration_type = state_record.integration_type.replace('google_', '')

        # Get tenant_id from the state (stored when OAuth flow was initiated)
        tenant_id = state_record.tenant_id

        if not tenant_id:
            raise HTTPException(
                status_code=400,
                detail="Tenant ID not found in OAuth state. Please try connecting again."
            )

        # Handle callback
        handler = get_google_oauth_handler(db, tenant_id)
        result = await handler.handle_callback(code, state)

        # Redirect to success page
        frontend_url = settings.FRONTEND_URL
        redirect_to = result.get("redirect_url") or f"{frontend_url}/hub?integration={integration_type}&status=success"

        # Clean up redirect URL (remove internal params)
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
        parsed = urlparse(redirect_to)
        params = parse_qs(parsed.query)
        params.pop('integration_type', None)
        params.pop('display_name', None)
        params['status'] = ['success']
        params['type'] = [integration_type]
        params['id'] = [str(result.get('integration_id', ''))]

        # Ensure we redirect to frontend
        parsed_frontend = urlparse(frontend_url)
        clean_redirect = urlunparse((
            parsed.scheme or parsed_frontend.scheme or 'http',
            parsed.netloc or parsed_frontend.netloc,
            parsed.path or '/hub',
            '',
            urlencode(params, doseq=True),
            ''
        ))

        return RedirectResponse(url=clean_redirect)

    except ValueError as e:
        logger.error(f"OAuth callback error: {e}")
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/hub?status=error&message={str(e)}")
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return RedirectResponse(url=f"{settings.FRONTEND_URL}/hub?status=error&message=Authentication+failed")


# ============================================
# Health Check
# ============================================

@router.get("/gmail/{integration_id}/health")
async def check_gmail_health(
    integration_id: int,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """Check health of a Gmail integration."""
    # Verify ownership
    integration = db.query(GmailIntegration).join(HubIntegration).filter(
        GmailIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        service = GmailService(db, integration_id)
        health = await service.check_health()

        # Update health status in database
        base = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
        if base:
            base.health_status = health["status"]
            base.last_health_check = datetime.utcnow()
            db.commit()

        return health
    except Exception as e:
        return {"status": "unavailable", "errors": [str(e)]}


@router.get("/calendar/{integration_id}/health")
async def check_calendar_health(
    integration_id: int,
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """Check health of a Calendar integration."""
    # Verify ownership
    integration = db.query(CalendarIntegration).join(HubIntegration).filter(
        CalendarIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        service = CalendarService(db, integration_id)
        health = await service.check_health()

        # Update health status in database
        base = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
        if base:
            base.health_status = health["status"]
            base.last_health_check = datetime.utcnow()
            db.commit()

        return health
    except Exception as e:
        return {"status": "unavailable", "errors": [str(e)]}


# ============================================
# Re-Authorization
# ============================================

@router.post("/reauthorize/{integration_id}", response_model=OAuthAuthorizeResponse)
async def reauthorize_integration(
    integration_id: int,
    redirect_url: Optional[str] = Query(None, description="URL to redirect after OAuth"),
    ctx: TenantContext = Depends(get_current_tenant_context),
    db: Session = Depends(get_session)
):
    """
    Generate a re-authorization URL for a disconnected/expired integration.

    Used when a refresh token is revoked (e.g., Google Testing mode 7-day expiry
    or user revocation). Returns a new OAuth URL with login_hint pre-filled.
    """
    integration = db.query(HubIntegration).filter(
        HubIntegration.id == integration_id,
        HubIntegration.tenant_id == ctx.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Get email for login_hint
    email = None
    if integration.type == 'calendar':
        cal = db.query(CalendarIntegration).filter(
            CalendarIntegration.id == integration_id
        ).first()
        email = cal.email_address if cal else None
    elif integration.type == 'gmail':
        gmail = db.query(GmailIntegration).filter(
            GmailIntegration.id == integration_id
        ).first()
        email = gmail.email_address if gmail else None

    try:
        handler = get_google_oauth_handler(db, ctx.tenant_id)

        auth_url, state = await handler.generate_authorization_url(
            integration_type=integration.type,
            redirect_url=redirect_url or f"{settings.FRONTEND_URL}/hub",
            display_name=integration.display_name,
            login_hint=email
        )

        logger.info(
            "Generated re-authorization URL for integration %s (type=%s, email=%s)",
            integration_id, integration.type, email
        )

        return OAuthAuthorizeResponse(authorization_url=auth_url, state=state)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
