"""
Channel Catalog API — serves the wizard-facing channel list.

The Agent Wizard's StepChannels component fetches this endpoint at mount so
that adding a new channel adapter on the backend automatically flows through
to the UI without a parallel frontend edit. The frontend retains a static
fallback array for offline / degraded mode.

Authentication is required (tenant context is used to compute per-tenant
"configured" flags), but all tenants in the system see the same channel
catalog — the per-tenant bit is strictly the ``tenant_has_configured`` flag.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context
from channels.catalog import CHANNEL_CATALOG
from db import get_db
from models import (
    DiscordIntegration,
    SlackIntegration,
    TelegramBotInstance,
    WhatsAppMCPInstance,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelCatalogEntry(BaseModel):
    """Wire shape for a single channel catalog entry."""
    id: str
    display_name: str
    description: str
    requires_setup: bool
    setup_hint: str
    icon_hint: str
    tenant_has_configured: bool


def _tenant_has_configured(channel_id: str, tenant_id: str, db: Session) -> bool:
    """
    Conservative check: does this tenant have at least one instance/integration
    row for the given channel? Channels without any setup requirement
    (playground) always return True; unknown channels default to False so the
    UI surfaces the "Needs setup" badge rather than silently claiming readiness.
    """
    if channel_id == "playground":
        return True

    try:
        if channel_id == "whatsapp":
            return db.query(WhatsAppMCPInstance.id).filter(
                WhatsAppMCPInstance.tenant_id == tenant_id
            ).first() is not None
        if channel_id == "telegram":
            return db.query(TelegramBotInstance.id).filter(
                TelegramBotInstance.tenant_id == tenant_id
            ).first() is not None
        if channel_id == "slack":
            return db.query(SlackIntegration.id).filter(
                SlackIntegration.tenant_id == tenant_id
            ).first() is not None
        if channel_id == "discord":
            return db.query(DiscordIntegration.id).filter(
                DiscordIntegration.tenant_id == tenant_id
            ).first() is not None
    except Exception as exc:
        # Tables that don't exist yet (partial migration) or transient DB
        # errors should degrade gracefully rather than 500 the whole catalog.
        logger.warning(
            "channel catalog: tenant_has_configured lookup failed for %s: %s",
            channel_id, exc,
        )
        return False

    return False


@router.get("", response_model=List[ChannelCatalogEntry])
def list_channels(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> List[ChannelCatalogEntry]:
    """
    Return the channel catalog annotated with per-tenant configuration status.

    Preserves ``CHANNEL_CATALOG`` ordering so the wizard renders channels in
    the same sequence regardless of tenant state.
    """
    tenant_id = ctx.tenant_id
    return [
        ChannelCatalogEntry(
            id=ch.id,
            display_name=ch.display_name,
            description=ch.description,
            requires_setup=ch.requires_setup,
            setup_hint=ch.setup_hint,
            icon_hint=ch.icon_hint,
            tenant_has_configured=_tenant_has_configured(ch.id, tenant_id, db),
        )
        for ch in CHANNEL_CATALOG
    ]
