"""
v0.6.0 Item 34: Discord Integration
API Routes for Discord Bot Integration Management
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db import get_db
from models import DiscordIntegration, Agent
from models_rbac import User
from hub.security import TokenEncryption
from services.encryption_key_service import get_discord_encryption_key
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Discord Integration"], redirect_slashes=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_encryption(db: Session) -> TokenEncryption:
    """Get TokenEncryption instance for Discord tokens."""
    key = get_discord_encryption_key(db)
    if not key:
        raise HTTPException(status_code=500, detail="Discord encryption key not configured")
    return TokenEncryption(key.encode())


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class DiscordIntegrationCreate(BaseModel):
    bot_token: str = Field(..., description="Discord bot token")
    application_id: str = Field(..., description="Discord Application ID")
    dm_policy: Optional[str] = Field(default="allowlist", description="DM policy: open/allowlist/disabled")

    class Config:
        json_schema_extra = {
            "example": {
                "bot_token": "your-discord-bot-token",
                "application_id": "your-application-id"
            }
        }


class DiscordIntegrationUpdate(BaseModel):
    bot_token: Optional[str] = Field(None, description="New bot token")
    application_id: Optional[str] = Field(None, description="New Application ID")
    is_active: Optional[bool] = None
    dm_policy: Optional[str] = Field(None, description="DM policy: open/allowlist/disabled")
    allowed_guilds: Optional[List[str]] = Field(None, description="List of allowed guild (server) IDs")
    guild_channel_config: Optional[dict] = Field(None, description="Per-guild channel configuration")


class DiscordIntegrationResponse(BaseModel):
    id: int
    tenant_id: str
    application_id: str
    bot_user_id: Optional[str]
    is_active: bool
    status: str
    dm_policy: str
    allowed_guilds: Optional[List[str]]
    guild_channel_config: Optional[dict]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DiscordTestResponse(BaseModel):
    success: bool
    bot_user: Optional[str] = None
    guilds: Optional[int] = None
    error: Optional[str] = None


class DiscordGuildInfo(BaseModel):
    id: str
    name: str
    icon: Optional[str] = None
    member_count: Optional[int] = None
    owner: bool = False


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=List[DiscordIntegrationResponse])
async def list_discord_integrations(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List all Discord integrations for current tenant."""
    query = context.filter_by_tenant(
        db.query(DiscordIntegration),
        DiscordIntegration.tenant_id
    )
    integrations = query.order_by(DiscordIntegration.created_at.desc()).all()
    return [DiscordIntegrationResponse.model_validate(i) for i in integrations]


@router.post("/", response_model=DiscordIntegrationResponse)
async def create_discord_integration(
    data: DiscordIntegrationCreate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Create a new Discord integration.

    Validates the bot token against Discord API (/users/@me), encrypts it,
    and stores the integration record.
    """
    # Validate application_id format (snowflake: 17-20 digit number)
    if not data.application_id.isdigit() or not (17 <= len(data.application_id) <= 20):
        raise HTTPException(status_code=400, detail="Application ID must be a 17-20 digit snowflake ID")

    # Validate bot token against Discord API
    try:
        import aiohttp
        headers = {
            "Authorization": f"Bot {data.bot_token}",
            "Content-Type": "application/json"
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://discord.com/api/v10/users/@me") as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    raise HTTPException(
                        status_code=400,
                        detail=f"Discord auth failed: {error_data.get('message', 'Invalid token')}"
                    )
                bot_data = await resp.json()
                bot_user_id = bot_data.get("id", "")
                bot_username = bot_data.get("username", "")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Discord auth validation failed: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to validate Discord token: {str(e)}")

    # Encrypt token
    encryption = _get_encryption(db)
    tenant_id = current_user.tenant_id

    integration = DiscordIntegration(
        tenant_id=tenant_id,
        bot_token_encrypted=encryption.encrypt(data.bot_token, tenant_id),
        application_id=data.application_id,
        bot_user_id=bot_user_id,
        is_active=True,
        status="connected",
        dm_policy=data.dm_policy or "allowlist",
    )

    db.add(integration)
    db.commit()
    db.refresh(integration)

    logger.info(
        f"Created Discord integration {integration.id} for tenant {tenant_id}: "
        f"bot={bot_username} (app_id: {data.application_id})"
    )

    # Auto-link: assign this Discord integration to agents that have
    # "discord" enabled but no discord_integration_id yet
    import json as json_lib

    unlinked_agents = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.discord_integration_id == None,
        Agent.is_active == True
    ).all()

    linked_count = 0
    for agent in unlinked_agents:
        enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
            json_lib.loads(agent.enabled_channels) if agent.enabled_channels else []
        )
        if "discord" in enabled_channels:
            agent.discord_integration_id = integration.id
            linked_count += 1

    if linked_count > 0:
        db.commit()
        logger.info(f"Auto-linked Discord integration {integration.id} to {linked_count} agent(s)")

    return DiscordIntegrationResponse.model_validate(integration)


@router.put("/{integration_id}", response_model=DiscordIntegrationResponse)
async def update_discord_integration(
    integration_id: int,
    data: DiscordIntegrationUpdate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Update an existing Discord integration."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    encryption = _get_encryption(db)
    tenant_id = integration.tenant_id

    if data.bot_token is not None:
        integration.bot_token_encrypted = encryption.encrypt(data.bot_token, tenant_id)
        integration.status = "inactive"  # Re-validate needed

    if data.application_id is not None:
        if not data.application_id.isdigit() or not (17 <= len(data.application_id) <= 20):
            raise HTTPException(status_code=400, detail="Application ID must be a 17-20 digit snowflake ID")
        integration.application_id = data.application_id

    if data.is_active is not None:
        integration.is_active = data.is_active

    if data.dm_policy is not None:
        if data.dm_policy not in ("open", "allowlist", "disabled"):
            raise HTTPException(status_code=400, detail="dm_policy must be 'open', 'allowlist', or 'disabled'")
        integration.dm_policy = data.dm_policy

    if data.allowed_guilds is not None:
        integration.allowed_guilds = data.allowed_guilds

    if data.guild_channel_config is not None:
        integration.guild_channel_config = data.guild_channel_config

    db.commit()
    db.refresh(integration)

    logger.info(f"Updated Discord integration {integration_id} for tenant {tenant_id}")
    return DiscordIntegrationResponse.model_validate(integration)


@router.delete("/{integration_id}")
async def delete_discord_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Delete a Discord integration and unlink any agents."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    # Unlink agents that reference this integration
    linked_agents = db.query(Agent).filter(
        Agent.discord_integration_id == integration_id
    ).all()
    for agent in linked_agents:
        agent.discord_integration_id = None

    db.delete(integration)
    db.commit()

    logger.info(
        f"Deleted Discord integration {integration_id} for tenant {integration.tenant_id} "
        f"(unlinked {len(linked_agents)} agent(s))"
    )
    return {"success": True, "message": "Integration deleted"}


@router.post("/{integration_id}/test", response_model=DiscordTestResponse)
async def test_discord_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Test Discord integration connectivity via /users/@me."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        encryption = _get_encryption(db)
        bot_token = encryption.decrypt(integration.bot_token_encrypted, integration.tenant_id)

        import aiohttp
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            # Test authentication
            async with session.get("https://discord.com/api/v10/users/@me") as resp:
                if resp.status == 200:
                    bot_data = await resp.json()
                    bot_username = bot_data.get("username", "unknown")

                    # Update status to connected
                    integration.status = "connected"
                    integration.bot_user_id = bot_data.get("id")
                    db.commit()

                    # Get guild count
                    async with session.get("https://discord.com/api/v10/users/@me/guilds") as guilds_resp:
                        guild_count = 0
                        if guilds_resp.status == 200:
                            guilds = await guilds_resp.json()
                            guild_count = len(guilds)

                    return DiscordTestResponse(
                        success=True,
                        bot_user=bot_username,
                        guilds=guild_count,
                    )
                else:
                    integration.status = "error"
                    db.commit()
                    error_data = await resp.json()
                    return DiscordTestResponse(
                        success=False,
                        error=error_data.get("message", f"HTTP {resp.status}")
                    )

    except Exception as e:
        logger.error(f"Discord test failed for integration {integration_id}: {e}", exc_info=True)
        integration.status = "error"
        db.commit()
        return DiscordTestResponse(success=False, error=str(e))


@router.get("/{integration_id}/guilds", response_model=List[DiscordGuildInfo])
async def list_discord_guilds(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List guilds (servers) the bot has been added to."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    if not context.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=404, detail="Integration not found")

    try:
        encryption = _get_encryption(db)
        bot_token = encryption.decrypt(integration.bot_token_encrypted, integration.tenant_id)

        import aiohttp
        headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get("https://discord.com/api/v10/users/@me/guilds") as resp:
                if resp.status != 200:
                    error_data = await resp.json()
                    raise HTTPException(
                        status_code=502,
                        detail=f"Discord API error: {error_data.get('message', 'unknown')}"
                    )

                guilds_data = await resp.json()
                guilds = []
                for g in guilds_data:
                    guilds.append(DiscordGuildInfo(
                        id=g["id"],
                        name=g.get("name", ""),
                        icon=g.get("icon"),
                        owner=g.get("owner", False),
                    ))

                return guilds

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list Discord guilds for integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Failed to list Discord guilds: {str(e)}")
