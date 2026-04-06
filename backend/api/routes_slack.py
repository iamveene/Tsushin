"""
v0.6.0 Item 33: Slack Integration
API Routes for Slack Workspace Integration Management
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db import get_db
from models import SlackIntegration, Agent
from models_rbac import User
from hub.security import TokenEncryption
from services.encryption_key_service import get_slack_encryption_key
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Slack Integration"], redirect_slashes=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_encryption(db: Session) -> TokenEncryption:
    """Get TokenEncryption instance for Slack tokens."""
    key = get_slack_encryption_key(db)
    if not key:
        raise HTTPException(status_code=500, detail="Slack encryption key not configured")
    return TokenEncryption(key.encode())


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class SlackIntegrationCreate(BaseModel):
    bot_token: str = Field(..., description="Slack bot token (xoxb-...)")
    app_token: Optional[str] = Field(None, description="Slack app-level token (xapp-...) for Socket Mode")
    signing_secret: Optional[str] = Field(None, description="Slack signing secret for HTTP mode verification")
    mode: str = Field(default="socket", description="Connection mode: 'socket' or 'http'")

    class Config:
        json_schema_extra = {
            "example": {
                "bot_token": "xoxb-1234567890-abcdef",
                "app_token": "xapp-1-ABCDEF",
                "mode": "socket"
            }
        }


class SlackIntegrationUpdate(BaseModel):
    bot_token: Optional[str] = Field(None, description="New bot token")
    app_token: Optional[str] = Field(None, description="New app-level token")
    signing_secret: Optional[str] = Field(None, description="New signing secret")
    mode: Optional[str] = Field(None, description="Connection mode: 'socket' or 'http'")
    is_active: Optional[bool] = None
    dm_policy: Optional[str] = Field(None, description="DM policy: open/allowlist/disabled")
    allowed_channels: Optional[List[str]] = Field(None, description="List of allowed Slack channel IDs")


class SlackIntegrationResponse(BaseModel):
    id: int
    tenant_id: str
    workspace_id: str
    workspace_name: Optional[str]
    mode: str
    bot_user_id: Optional[str]
    is_active: bool
    status: str
    dm_policy: str
    allowed_channels: Optional[List[str]]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SlackTestResponse(BaseModel):
    success: bool
    bot_user: Optional[str] = None
    workspace: Optional[str] = None
    error: Optional[str] = None


class SlackChannelInfo(BaseModel):
    id: str
    name: str
    is_private: bool
    num_members: Optional[int] = None


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[SlackIntegrationResponse])
async def list_slack_integrations(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List all Slack integrations for current tenant."""
    query = context.filter_by_tenant(
        db.query(SlackIntegration),
        SlackIntegration.tenant_id
    )
    integrations = query.order_by(SlackIntegration.created_at.desc()).all()
    return [SlackIntegrationResponse.model_validate(i) for i in integrations]


@router.post("/", response_model=SlackIntegrationResponse)
async def create_slack_integration(
    data: SlackIntegrationCreate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Create a new Slack integration.

    Validates the bot token against Slack API (auth.test), encrypts tokens,
    and stores the integration record.
    """
    if data.mode not in ("socket", "http"):
        raise HTTPException(status_code=400, detail="mode must be 'socket' or 'http'")

    if data.mode == "socket" and not data.app_token:
        raise HTTPException(status_code=400, detail="app_token is required for Socket Mode")

    # Validate bot token format
    if not data.bot_token.startswith("xoxb-"):
        raise HTTPException(status_code=400, detail="Bot token must start with 'xoxb-'")

    # Validate token against Slack API
    try:
        from slack_sdk import WebClient
        client = WebClient(token=data.bot_token)
        auth_response = client.auth_test()

        if not auth_response.get("ok"):
            raise HTTPException(status_code=400, detail=f"Slack auth failed: {auth_response.get('error', 'unknown')}")

        workspace_id = auth_response.get("team_id", "")
        workspace_name = auth_response.get("team", "")
        bot_user_id = auth_response.get("user_id", "")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack auth.test failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to validate Slack token: {str(e)}")

    # Check for duplicate registration (same tenant + workspace)
    tenant_id = current_user.tenant_id
    existing = db.query(SlackIntegration).filter(
        SlackIntegration.tenant_id == tenant_id,
        SlackIntegration.workspace_id == workspace_id,
    ).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Slack workspace {workspace_id} is already registered for this tenant"
        )

    # Encrypt tokens
    encryption = _get_encryption(db)

    integration = SlackIntegration(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        bot_token_encrypted=encryption.encrypt(data.bot_token, tenant_id),
        app_token_encrypted=encryption.encrypt(data.app_token, tenant_id) if data.app_token else None,
        signing_secret_encrypted=encryption.encrypt(data.signing_secret, tenant_id) if data.signing_secret else None,
        mode=data.mode,
        bot_user_id=bot_user_id,
        is_active=True,
        status="connected",
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    logger.info(
        f"Created Slack integration {integration.id} for tenant {tenant_id}: "
        f"workspace={workspace_name} ({workspace_id})"
    )

    # Auto-link: assign this Slack integration to agents that have
    # "slack" enabled but no slack_integration_id yet
    import json as json_lib

    unlinked_agents = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.slack_integration_id == None,
        Agent.is_active == True
    ).all()

    linked_count = 0
    for agent in unlinked_agents:
        enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
            json_lib.loads(agent.enabled_channels) if agent.enabled_channels else []
        )
        if "slack" in enabled_channels:
            agent.slack_integration_id = integration.id
            linked_count += 1

    if linked_count > 0:
        db.commit()
        logger.info(f"Auto-linked Slack integration {integration.id} to {linked_count} agent(s)")

    return SlackIntegrationResponse.model_validate(integration)


@router.put("/{integration_id}", response_model=SlackIntegrationResponse)
async def update_slack_integration(
    integration_id: int,
    data: SlackIntegrationUpdate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Update an existing Slack integration."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    encryption = _get_encryption(db)
    tenant_id = integration.tenant_id

    if data.mode is not None:
        if data.mode not in ("socket", "http"):
            raise HTTPException(status_code=400, detail="mode must be 'socket' or 'http'")
        integration.mode = data.mode

    if data.bot_token is not None:
        if not data.bot_token.startswith("xoxb-"):
            raise HTTPException(status_code=400, detail="Bot token must start with 'xoxb-'")
        integration.bot_token_encrypted = encryption.encrypt(data.bot_token, tenant_id)
        integration.status = "inactive"  # Re-validate needed

    if data.app_token is not None:
        integration.app_token_encrypted = encryption.encrypt(data.app_token, tenant_id)

    if data.signing_secret is not None:
        integration.signing_secret_encrypted = encryption.encrypt(data.signing_secret, tenant_id)

    if data.is_active is not None:
        integration.is_active = data.is_active

    if data.dm_policy is not None:
        if data.dm_policy not in ("open", "allowlist", "disabled"):
            raise HTTPException(status_code=400, detail="dm_policy must be 'open', 'allowlist', or 'disabled'")
        integration.dm_policy = data.dm_policy

    if data.allowed_channels is not None:
        integration.allowed_channels = data.allowed_channels

    db.commit()
    db.refresh(integration)

    logger.info(f"Updated Slack integration {integration_id} for tenant {tenant_id}")
    return SlackIntegrationResponse.model_validate(integration)


@router.delete("/{integration_id}")
async def delete_slack_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Delete a Slack integration and unlink any agents."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    # Unlink agents that reference this integration (scoped to same tenant)
    linked_agents = db.query(Agent).filter(
        Agent.slack_integration_id == integration_id,
        Agent.tenant_id == integration.tenant_id,
    ).all()
    for agent in linked_agents:
        agent.slack_integration_id = None

    db.delete(integration)
    db.commit()

    logger.info(
        f"Deleted Slack integration {integration_id} for tenant {integration.tenant_id} "
        f"(unlinked {len(linked_agents)} agent(s))"
    )
    return {"success": True, "message": "Integration deleted"}


@router.post("/{integration_id}/test", response_model=SlackTestResponse)
async def test_slack_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Test Slack integration connectivity via auth.test."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        encryption = _get_encryption(db)
        bot_token = encryption.decrypt(integration.bot_token_encrypted, integration.tenant_id)

        from slack_sdk import WebClient
        client = WebClient(token=bot_token)
        auth_response = client.auth_test()

        if auth_response.get("ok"):
            # Update status to connected
            integration.status = "connected"
            integration.bot_user_id = auth_response.get("user_id")
            integration.workspace_name = auth_response.get("team")
            db.commit()

            return SlackTestResponse(
                success=True,
                bot_user=auth_response.get("user"),
                workspace=auth_response.get("team"),
            )
        else:
            integration.status = "error"
            db.commit()
            return SlackTestResponse(
                success=False,
                error=auth_response.get("error", "unknown")
            )

    except Exception as e:
        logger.error(f"Slack test failed for integration {integration_id}: {e}", exc_info=True)
        integration.status = "error"
        db.commit()
        return SlackTestResponse(success=False, error=str(e))


@router.get("/{integration_id}/channels", response_model=List[SlackChannelInfo])
async def list_slack_channels(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.slack.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List available channels from the Slack workspace."""
    integration = db.query(SlackIntegration).filter(
        SlackIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        encryption = _get_encryption(db)
        bot_token = encryption.decrypt(integration.bot_token_encrypted, integration.tenant_id)

        from slack_sdk import WebClient
        client = WebClient(token=bot_token)

        channels = []
        cursor = None

        # Paginate through conversations.list
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor

            response = client.conversations_list(**kwargs)

            if not response.get("ok"):
                raise HTTPException(status_code=502, detail=f"Slack API error: {response.get('error', 'unknown')}")

            for ch in response.get("channels", []):
                channels.append(SlackChannelInfo(
                    id=ch["id"],
                    name=ch.get("name", ""),
                    is_private=ch.get("is_private", False),
                    num_members=ch.get("num_members"),
                ))

            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list Slack channels for integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to list Slack channels: {str(e)}")
