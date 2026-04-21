"""
Phase 23: Discord Bot Integration API Routes
BUG-311 Fix: Per-integration public_key storage for tenant-isolated signature verification
BUG-313 Fix: public_key exposed in create/update schemas for full configurability

Provides REST API endpoints for Discord bot instance management:
- Create/Read/Update/Delete Discord integrations
- Each integration stores bot_token, application_id, and public_key
- public_key is used for Ed25519 interaction signature verification (per-tenant)
"""

import logging
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from cryptography.fernet import Fernet

from db import get_db
from hub.security import TokenEncryption
from models import DiscordIntegration
from models_rbac import User
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext
from services.encryption_key_service import get_discord_encryption_key

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/discord/integrations",
    tags=["Discord Integrations"],
    redirect_slashes=False
)


# ============================================================================
# Pydantic Schemas
# ============================================================================

class DiscordIntegrationCreate(BaseModel):
    """Create a new Discord integration."""
    bot_token: str = Field(..., description="Discord bot token (from Developer Portal)")
    application_id: str = Field(..., description="Discord Application ID")
    public_key: str = Field(..., description="Discord Application Public Key (Ed25519, for interaction signature verification)")

    @field_validator('public_key')
    @classmethod
    def validate_public_key(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("public_key cannot be empty")
        if len(v) != 64:
            raise ValueError(f"public_key must be 64 hex characters (got {len(v)})")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("public_key must be a valid hex string")
        return v

    @field_validator('application_id')
    @classmethod
    def validate_application_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("application_id cannot be empty")
        if not v.isdigit():
            raise ValueError("application_id must be a numeric string (Discord snowflake)")
        return v


class DiscordIntegrationUpdate(BaseModel):
    """Update an existing Discord integration."""
    bot_token: Optional[str] = Field(None, description="New bot token (re-encrypted)")
    public_key: Optional[str] = Field(None, description="New public key for interaction verification")
    is_active: Optional[bool] = Field(None, description="Enable/disable integration")

    @field_validator('public_key')
    @classmethod
    def validate_public_key(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("public_key cannot be empty when provided")
        if len(v) != 64:
            raise ValueError(f"public_key must be 64 hex characters (got {len(v)})")
        try:
            bytes.fromhex(v)
        except ValueError:
            raise ValueError("public_key must be a valid hex string")
        return v


class DiscordIntegrationResponse(BaseModel):
    """Response model for Discord integration."""
    id: int
    is_active: bool
    status: str
    health_status: str
    tenant_id: str
    application_id: str
    public_key: Optional[str] = None
    interactions_endpoint_url: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


def _to_response(integration: DiscordIntegration) -> DiscordIntegrationResponse:
    """Convert a DiscordIntegration model to response."""
    return DiscordIntegrationResponse(
        id=integration.id,
        is_active=integration.is_active,
        status=integration.status or "inactive",
        health_status=integration.health_status or "unknown",
        tenant_id=integration.tenant_id,
        application_id=integration.application_id,
        public_key=integration.public_key,
        interactions_endpoint_url=f"/api/channels/discord/{integration.id}/interactions",
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("", response_model=DiscordIntegrationResponse, include_in_schema=False)
@router.post("/", response_model=DiscordIntegrationResponse)
async def create_discord_integration(
    data: DiscordIntegrationCreate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Create a new Discord bot integration with per-integration public_key (BUG-311/313 fix).

    V060-CHN-002 FIX: Use TokenEncryption with per-tenant key derivation so the
    AgentRouter (which decrypts via TokenEncryption) can read the token back.
    Previously create used raw Fernet while the consumer used per-tenant-derived
    Fernet, causing silent decrypt failures when an agent tried to send.
    """
    try:
        encryption_key = get_discord_encryption_key(db)
        if not encryption_key:
            raise HTTPException(status_code=500, detail="Discord encryption key not available")

        enc = TokenEncryption(encryption_key.encode())
        bot_token_encrypted = enc.encrypt(data.bot_token, current_user.tenant_id)

        integration = DiscordIntegration(
            tenant_id=current_user.tenant_id,
            bot_token_encrypted=bot_token_encrypted,
            application_id=data.application_id,
            public_key=data.public_key,
            is_active=True,
            status="inactive",
            health_status="unknown",
        )

        db.add(integration)
        db.commit()
        db.refresh(integration)

        logger.info(f"Created Discord integration {integration.id} (app_id={data.application_id}, tenant={current_user.tenant_id})")
        return _to_response(integration)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create Discord integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create Discord integration: {str(e)}")


@router.get("", response_model=List[DiscordIntegrationResponse], include_in_schema=False)
@router.get("/", response_model=List[DiscordIntegrationResponse])
async def list_discord_integrations(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List all Discord integrations for the current tenant."""
    integrations = db.query(DiscordIntegration).filter(
        DiscordIntegration.tenant_id == current_user.tenant_id
    ).all()
    return [_to_response(i) for i in integrations]


@router.get("/{integration_id}", response_model=DiscordIntegrationResponse)
async def get_discord_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Get a specific Discord integration by ID."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Discord integration not found")

    return _to_response(integration)


@router.put("/{integration_id}", response_model=DiscordIntegrationResponse)
async def update_discord_integration(
    integration_id: int,
    data: DiscordIntegrationUpdate,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Update an existing Discord integration. public_key can be rotated (BUG-313 fix)."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Discord integration not found")

    try:
        if data.bot_token is not None:
            encryption_key = get_discord_encryption_key(db)
            if not encryption_key:
                raise HTTPException(status_code=500, detail="Discord encryption key not available")
            enc = TokenEncryption(encryption_key.encode())
            integration.bot_token_encrypted = enc.encrypt(data.bot_token, integration.tenant_id)

        if data.public_key is not None:
            integration.public_key = data.public_key

        if data.is_active is not None:
            integration.is_active = data.is_active

        db.commit()
        db.refresh(integration)

        logger.info(f"Updated Discord integration {integration_id} (tenant={current_user.tenant_id})")
        return _to_response(integration)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update Discord integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update Discord integration: {str(e)}")


@router.delete("/{integration_id}")
async def delete_discord_integration(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.write")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Delete a Discord integration."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.tenant_id == current_user.tenant_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Discord integration not found")

    db.delete(integration)
    db.commit()

    logger.info(f"Deleted Discord integration {integration_id} (tenant={current_user.tenant_id})")
    return {"status": "deleted", "id": integration_id}


# ============================================================================
# BUG-675: Test Connection + Guilds list endpoints
# The Hub frontend has buttons that hit these paths; previously they 404'd.
# ============================================================================

@router.post("/{integration_id}/test")
async def test_discord_connection(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    db: Session = Depends(get_db),
):
    """Verify the Discord bot token via `/users/@me`."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.tenant_id == current_user.tenant_id,
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Discord integration not found")

    encryption_key = get_discord_encryption_key(db)
    if not encryption_key:
        raise HTTPException(status_code=500, detail="Discord encryption key not available")
    enc = TokenEncryption(encryption_key.encode())
    try:
        bot_token = enc.decrypt(integration.bot_token_encrypted, integration.tenant_id)
    except Exception as e:
        logger.warning(f"Discord test: decrypt failed for integration {integration_id}: {e}")
        return {"success": False, "error": "Stored bot token could not be decrypted."}

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {bot_token}"},
            )
        if resp.status_code == 200:
            data = resp.json()
            bot_user = f"{data.get('username', '?')}#{data.get('discriminator', '0000')}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                g_resp = await client.get(
                    "https://discord.com/api/v10/users/@me/guilds",
                    headers={"Authorization": f"Bot {bot_token}"},
                )
            guild_count = len(g_resp.json()) if g_resp.status_code == 200 else 0
            return {"success": True, "bot_user": bot_user, "guilds": guild_count}
        return {"success": False, "error": f"Discord rejected token (HTTP {resp.status_code})"}
    except Exception as e:
        logger.warning(f"Discord test for integration {integration_id} failed: {e}")
        return {"success": False, "error": str(e)}


@router.get("/{integration_id}/guilds")
async def list_discord_guilds(
    integration_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("integrations.discord.read")),
    db: Session = Depends(get_db),
):
    """List the guilds the bot is a member of."""
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.tenant_id == current_user.tenant_id,
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Discord integration not found")

    encryption_key = get_discord_encryption_key(db)
    if not encryption_key:
        raise HTTPException(status_code=500, detail="Discord encryption key not available")
    enc = TokenEncryption(encryption_key.encode())
    try:
        bot_token = enc.decrypt(integration.bot_token_encrypted, integration.tenant_id)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not decrypt stored bot token")

    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://discord.com/api/v10/users/@me/guilds",
                headers={"Authorization": f"Bot {bot_token}"},
            )
        if resp.status_code != 200:
            return {"guilds": [], "error": f"HTTP {resp.status_code}"}
        return {
            "guilds": [
                {"id": g.get("id"), "name": g.get("name"), "owner": bool(g.get("owner"))}
                for g in resp.json()
            ]
        }
    except Exception as e:
        logger.warning(f"Discord guilds list for integration {integration_id} failed: {e}")
        return {"guilds": [], "error": str(e)}
