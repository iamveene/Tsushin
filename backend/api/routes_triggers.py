"""Trigger catalog API."""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context
from channels.catalog import TRIGGER_CATALOG
from db import get_db
from models import (
    EmailChannelInstance,
    GitHubChannelInstance,
    JiraChannelInstance,
    ScheduleChannelInstance,
    WebhookIntegration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/triggers", tags=["triggers"])


class TriggerCatalogEntry(BaseModel):
    id: str
    display_name: str
    description: str
    requires_setup: bool
    setup_hint: str
    icon_hint: str
    tenant_has_configured: bool


def _tenant_has_configured(trigger_id: str, tenant_id: str, db: Session) -> bool:
    try:
        if trigger_id == "email":
            return db.query(EmailChannelInstance.id).filter(
                EmailChannelInstance.tenant_id == tenant_id
            ).first() is not None
        if trigger_id == "webhook":
            return db.query(WebhookIntegration.id).filter(
                WebhookIntegration.tenant_id == tenant_id
            ).first() is not None
        if trigger_id == "jira":
            return db.query(JiraChannelInstance.id).filter(
                JiraChannelInstance.tenant_id == tenant_id
            ).first() is not None
        if trigger_id == "schedule":
            return db.query(ScheduleChannelInstance.id).filter(
                ScheduleChannelInstance.tenant_id == tenant_id
            ).first() is not None
        if trigger_id == "github":
            return db.query(GitHubChannelInstance.id).filter(
                GitHubChannelInstance.tenant_id == tenant_id
            ).first() is not None
    except Exception as exc:
        logger.warning(
            "trigger catalog: tenant_has_configured lookup failed for %s: %s",
            trigger_id,
            exc,
        )
        return False

    return False


@router.get("", response_model=List[TriggerCatalogEntry])
def list_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> List[TriggerCatalogEntry]:
    tenant_id = ctx.tenant_id
    return [
        TriggerCatalogEntry(
            id=entry.id,
            display_name=entry.display_name,
            description=entry.description,
            requires_setup=entry.requires_setup,
            setup_hint=entry.setup_hint,
            icon_hint=entry.icon_hint,
            tenant_has_configured=_tenant_has_configured(entry.id, tenant_id, db),
        )
        for entry in TRIGGER_CATALOG
    ]
