"""
Phase 23: Slack Workspace Integration API Routes
BUG-312 Fix: app_id stored per-integration, signing_secret required for HTTP mode

Provides REST API endpoints for Slack workspace integration management:
- Create/Read/Update/Delete Slack integrations
- Supports socket mode (WebSocket) and HTTP Events API mode
- signing_secret is mandatory for mode="http" to enable signature verification
- app_id is stored for robust url_verification handshake resolution
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator, model_validator
from cryptography.fernet import Fernet

from db import get_db
from hub.security import TokenEncryption
from models import SlackIntegration
from models_rbac import User
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext
from services.encryption_key_service import get_slack_encryption_key

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/slack/integrations",
    tags=["Slack Integrations"],
    redirect_slashes=False
)


async def _restart_socket_worker_if_needed(request: Request, integration_id: int) -> None:
    """V060-CHN-002: When a socket-mode integration is created/updated, (re)start
    its Slack Socket Mode WebSocket worker. No-op if the manager is unavailable
    (e.g. during tests) or if the integration is HTTP-mode."""
    manager = getattr(request.app.state, "slack_socket_mode_manager", None)
    if manager is None:
        return
    try:
        await manager.restart_one(integration_id)
    except Exception as e:
        logger.warning(
            f"Failed to (re)start Slack Socket Mode worker for integration {integration_id}: {e}"
        )


async def _stop_socket_worker_if_running(request: Request, integration_id: int) -> None:
    manager = getattr(request.app.state, "slack_socket_mode_manager", None)
    if manager is None:
        return
    try:
        await manager.stop_one(integration_id)
    except Exception as e:
        logger.warning(
            f"Failed to stop Slack Socket Mode worker for integration {integration_id}: {e}"
        )


# ============================================================================
# Pydantic Schemas
# ============================================================================

class SlackIntegrationCreate(BaseModel):
    """Create a new Slack integration."""
    bot_token: str = Field(..., description="Slack bot token (xoxb-*)")
    mode: str = Field("socket", description="Connection mode: 'socket' (WebSocket) or 'http' (Events API)")
    app_id: Optional[str] = Field(None, description="Slack App ID (A0xxxxx) -- required for HTTP mode")
    workspace_id: Optional[str] = Field(None, description="Slack Team/Workspace ID (T0xxxxx)")
    workspace_name: Optional[str] = Field(None, description="Workspace display name")
    signing_secret: Optional[str] = Field(None, description="Slack Signing Secret (required for mode='http')")
    app_level_token: Optional[str] = Field(None, description="Slack App-Level Token (xapp-*, required for mode='socket')")

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("socket", "http"):
            raise ValueError("mode must be 'socket' or 'http'")
        return v

    @field_validator('bot_token')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("bot_token cannot be empty")
        if not v.startswith("xoxb-"):
            raise ValueError("bot_token must start with 'xoxb-' (Slack Bot User OAuth Token)")
        return v

    @model_validator(mode='after')
    def validate_mode_requirements(self):
        """BUG-312 Fix: Enforce signing_secret for HTTP mode, app_level_token for socket mode."""
        if self.mode == "http":
            if not self.signing_secret or not self.signing_secret.strip():
                raise ValueError("signing_secret is required when mode='http'.")
            if not self.app_id or not self.app_id.strip():
                raise ValueError("app_id is required when mode='http' for url_verification handshake.")
        elif self.mode == "socket":
            if not self.app_level_token or not self.app_level_token.strip():
                raise ValueError("app_level_token is required when mode='socket'.")
        return self


class SlackIntegrationUpdate(BaseModel):
    """Update an existing Slack integration."""
    bot_token: Optional[str] = Field(None, description="New bot token (re-encrypted)")
    mode: Optional[str] = Field(None, description="Connection mode: 'socket' or 'http'")
    app_id: Optional[str] = Field(None, description="Slack App ID")
    workspace_id: Optional[str] = Field(None, description="Slack Team/Workspace ID")
    workspace_name: Optional[str] = Field(None, description="Workspace display name")
    signing_secret: Optional[str] = Field(None, description="Slack Signing Secret")
    app_level_token: Optional[str] = Field(None, description="Slack App-Level Token")
    is_active: Optional[bool] = Field(None, description="Enable/disable integration")

    @field_validator('mode')
    @classmethod
    def validate_mode(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().lower()
        if v not in ("socket", "http"):
            raise ValueError("mode must be 'socket' or 'http'")
        return v

    @field_validator('bot_token')
    @classmethod
    def validate_bot_token(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v.startswith("xoxb-"):
            raise ValueError("bot_token must start with 'xoxb-'")
        return v


class SlackIntegrationResponse(BaseModel):
    """Response model for Slack integration."""
    id: int
    is_active: bool
    status: str
    health_status: str
    tenant_id: str
    workspace_id: Optional[str] = None
    app_id: Optional[str] = None
    workspace_name: Optional[str] = None
    mode: str
    has_signing_secret: bool = False
    has_app_level_token: bool = False
    events_endpoint_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _to_response(integration: SlackIntegration) -> SlackIntegrationResponse:
    """Convert a SlackIntegration model to response."""
    events_url = None
    if integration.mode == "http":
        events_url = f"/api/channels/slack/{integration.id}/events"
    return SlackIntegrationResponse(
        id=integration.id,
        is_active=integration.is_active,
        status=integration.status or "inactive",
        health_status=integration.health_status or "unknown",
        tenant_id=integration.tenant_id,
        workspace_id=integration.workspace_id,
        app_id=integration.app_id,
        workspace_name=integration.workspace_name,
        mode=integration.mode or "socket",
        has_signing_secret=bool(integration.signing_secret_encrypted),
        has_app_level_token=bool(integration.app_token_encrypted),
        events_endpoint_url=events_url,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=SlackIntegrationResponse)
async def create_slack_integration(
    data: SlackIntegrationCreate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Create a new Slack workspace integration (BUG-312 fix: signing_secret required for HTTP mode).

    V060-CHN-002 FIX: Use TokenEncryption with per-tenant key derivation so the
    SlackSocketModeManager and AgentRouter (which decrypt via TokenEncryption)
    can actually read the tokens back. Previously routes_slack used raw Fernet
    while the consumers used per-tenant-derived Fernet, causing silent decrypt
    failures the moment anything tried to use the tokens.
    """
    try:
        encryption_key = get_slack_encryption_key(db)
        if not encryption_key:
            raise HTTPException(status_code=500, detail="Slack encryption key not available")

        enc = TokenEncryption(encryption_key.encode())
        tenant_key = current_user.tenant_id
        bot_token_encrypted = enc.encrypt(data.bot_token, tenant_key)

        signing_secret_encrypted = None
        if data.signing_secret:
            signing_secret_encrypted = enc.encrypt(data.signing_secret, tenant_key)

        app_token_encrypted = None
        if data.app_level_token:
            app_token_encrypted = enc.encrypt(data.app_level_token, tenant_key)

        integration = SlackIntegration(
            tenant_id=current_user.tenant_id,
            workspace_id=data.workspace_id or "",
            app_id=data.app_id,
            workspace_name=data.workspace_name,
            bot_token_encrypted=bot_token_encrypted,
            app_token_encrypted=app_token_encrypted,
            signing_secret_encrypted=signing_secret_encrypted,
            mode=data.mode,
            is_active=True,
            status="inactive",
            health_status="unknown",
        )

        db.add(integration)
        db.commit()
        db.refresh(integration)

        logger.info(f"Created Slack integration {integration.id} (mode={data.mode}, tenant={current_user.tenant_id})")

        # V060-CHN-002: Spin up the Socket Mode worker for socket-mode integrations.
        if integration.mode == "socket":
            await _restart_socket_worker_if_needed(request, integration.id)

        return _to_response(integration)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create Slack integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create Slack integration: {str(e)}")


@router.get("/", response_model=List[SlackIntegrationResponse])
async def list_slack_integrations(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List all Slack integrations for the current tenant."""
    integrations = db.query(SlackIntegration).filter(
        SlackIntegration.tenant_id == current_user.tenant_id
    ).all()
    return [_to_response(i) for i in integrations]


@router.get("/{integration_id}", response_model=SlackIntegrationResponse)
async def get_slack_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Get a specific Slack integration by ID."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id,
        SlackIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration not found")

    return _to_response(integration)


@router.put("/{integration_id}", response_model=SlackIntegrationResponse)
async def update_slack_integration(
    integration_id: int,
    data: SlackIntegrationUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Update an existing Slack integration."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id,
        SlackIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration not found")

    try:
        encryption_key = get_slack_encryption_key(db)
        enc = TokenEncryption(encryption_key.encode()) if encryption_key else None
        tenant_key = integration.tenant_id

        if data.bot_token is not None and enc:
            integration.bot_token_encrypted = enc.encrypt(data.bot_token, tenant_key)

        if data.signing_secret is not None and enc:
            integration.signing_secret_encrypted = enc.encrypt(data.signing_secret, tenant_key)

        if data.app_level_token is not None and enc:
            integration.app_token_encrypted = enc.encrypt(data.app_level_token, tenant_key)

        if data.mode is not None:
            integration.mode = data.mode
        if data.app_id is not None:
            integration.app_id = data.app_id
        if data.workspace_id is not None:
            integration.workspace_id = data.workspace_id
        if data.workspace_name is not None:
            integration.workspace_name = data.workspace_name
        if data.is_active is not None:
            integration.is_active = data.is_active

        db.commit()
        db.refresh(integration)

        logger.info(f"Updated Slack integration {integration_id} (tenant={current_user.tenant_id})")

        # V060-CHN-002: React to mode/active/token changes by restarting (or stopping)
        # the Slack Socket Mode worker for this integration.
        if integration.mode == "socket" and integration.is_active:
            await _restart_socket_worker_if_needed(request, integration.id)
        else:
            await _stop_socket_worker_if_running(request, integration.id)

        return _to_response(integration)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update Slack integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update Slack integration: {str(e)}")


@router.delete("/{integration_id}")
async def delete_slack_integration(
    integration_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Delete a Slack integration."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id,
        SlackIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Slack integration not found")

    # V060-CHN-002: Stop the Socket Mode worker before deleting the row so we
    # don't leak a WebSocket connection for a row that no longer exists.
    await _stop_socket_worker_if_running(request, integration_id)

    db.delete(integration)
    db.commit()

    logger.info(f"Deleted Slack integration {integration_id} (tenant={current_user.tenant_id})")
    return {"status": "deleted", "id": integration_id}
