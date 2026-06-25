"""GitHub Projects v2 trigger CRUD + poll-now + test-connection endpoints.

Mirrors ``routes_jira_triggers.py`` (the poll-based precedent). On create it
provisions a **notification-only** system-managed Flow (Source → Gate →
Notification) whose Notification node renders ``{{source.payload.message}}`` —
the trigger pre-composes the WhatsApp text, so no LLM runs per board event.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.github_projects.trigger import GitHubProjectsPollResult, GitHubProjectsTrigger
from db import get_db
from hub.github.github_projects_service import GitHubProjectsError, GitHubProjectsService
from models import Agent, Contact, GitHubIntegration, GitHubProjectsChannelInstance
from services.flow_binding_service import (
    delete_bindings_for_trigger,
    delete_system_owned_continuous_artifacts_for_trigger,
    find_system_managed_flow_for_trigger,
    sync_system_managed_flow_default_agent,
    update_auto_flow_notification,
)
from services.github_integration_service import load_github_integration


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/github-projects",
    tags=["GitHub Projects Triggers"],
    redirect_slashes=False,
)

_TRIGGER_KIND = "github_projects"
# The trigger pre-composes the message; the Notification node renders it verbatim.
_NOTIFICATION_TEMPLATE = "{{source.payload.message}}"


# --------------------------------------------------------------------------- schemas

class GitHubProjectsTriggerCreate(BaseModel):
    integration_name: str = Field(min_length=1, max_length=100)
    github_integration_id: int = Field(ge=1)
    project_owner: str = Field(min_length=1, max_length=100)
    project_number: int = Field(ge=1)
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)
    # Required: board notifications are delivered through this agent's bound Flow
    # (dispatch only fans out to the Notification node when an agent resolves).
    default_agent_id: int = Field(ge=1)
    notify_recipient_raw: str = Field(default="@Vini", min_length=1, max_length=100)
    notification_enabled: bool = True
    trigger_criteria: Optional[dict] = None
    is_active: bool = True

    @field_validator("project_owner")
    @classmethod
    def _strip_owner(cls, value: str) -> str:
        return value.strip()


class GitHubProjectsTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, max_length=100)
    project_owner: Optional[str] = Field(default=None, max_length=100)
    project_number: Optional[int] = Field(default=None, ge=1)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    notify_recipient_raw: Optional[str] = Field(default=None, max_length=100)
    notification_enabled: Optional[bool] = None
    trigger_criteria: Optional[dict] = None
    is_active: Optional[bool] = None


class GitHubProjectsTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    github_integration_id: int
    github_integration_name: Optional[str] = None
    project_owner: str
    project_number: int
    project_node_id: Optional[str] = None
    project_name: Optional[str] = None
    poll_interval_seconds: int
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
    notify_recipient_raw: Optional[str] = None
    notification_enabled: bool
    trigger_criteria: Optional[dict] = None
    is_active: bool
    status: str
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    seeded_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    auto_flow_id: Optional[int] = None


class GitHubProjectsTestConnectionRequest(BaseModel):
    github_integration_id: Optional[int] = Field(default=None, ge=1)
    project_owner: Optional[str] = None
    project_number: Optional[int] = Field(default=None, ge=1)


class GitHubProjectsTestConnectionResponse(BaseModel):
    ok: bool
    project_node_id: Optional[str] = None
    title: Optional[str] = None
    url: Optional[str] = None
    number: Optional[int] = None
    error: Optional[str] = None


class GitHubProjectsPollNowResponse(BaseModel):
    instance_id: int
    status: str
    fetched_count: int = 0
    event_count: int = 0
    dispatched_count: int = 0
    duplicate_count: int = 0
    skipped_count: int = 0
    seeded: bool = False
    reason: Optional[str] = None
    dispatch_statuses: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- helpers

def _load_active_agent(db: Session, tenant_id: str, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _load_integration(db: Session, tenant_id: str, integration_id: int) -> GitHubIntegration:
    integration = load_github_integration(db, tenant_id=tenant_id, integration_id=integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="GitHub integration not found")
    return integration


def _load_trigger(db: Session, tenant_id: str, trigger_id: int) -> GitHubProjectsChannelInstance:
    instance = db.query(GitHubProjectsChannelInstance).filter(
        GitHubProjectsChannelInstance.id == trigger_id,
        GitHubProjectsChannelInstance.tenant_id == tenant_id,
    ).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="GitHub Projects trigger not found")
    return instance


def _agent_name(db: Session, tenant_id: str, agent_id: Optional[int]) -> Optional[str]:
    if not agent_id:
        return None
    row = db.query(Contact.friendly_name).join(
        Agent, Agent.contact_id == Contact.id,
    ).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
    ).first()
    return row.friendly_name if row else None


def _to_read(db: Session, instance: GitHubProjectsChannelInstance) -> GitHubProjectsTriggerRead:
    auto_flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=instance.tenant_id,
        trigger_kind=_TRIGGER_KIND,
        trigger_instance_id=instance.id,
    )
    integration_name = None
    integration = db.query(GitHubIntegration).filter(
        GitHubIntegration.id == instance.github_integration_id,
        GitHubIntegration.tenant_id == instance.tenant_id,
    ).first()
    if integration is not None:
        integration_name = integration.display_name or integration.name
    return GitHubProjectsTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        github_integration_id=instance.github_integration_id,
        github_integration_name=integration_name,
        project_owner=instance.project_owner,
        project_number=instance.project_number,
        project_node_id=instance.project_node_id,
        project_name=instance.project_name,
        poll_interval_seconds=instance.poll_interval_seconds,
        default_agent_id=instance.default_agent_id,
        default_agent_name=_agent_name(db, instance.tenant_id, instance.default_agent_id),
        notify_recipient_raw=instance.notify_recipient_raw,
        notification_enabled=bool(instance.notification_enabled),
        trigger_criteria=instance.trigger_criteria,
        is_active=bool(instance.is_active),
        status=instance.status or "active",
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check,
        last_activity_at=instance.last_activity_at,
        seeded_at=instance.seeded_at,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        auto_flow_id=auto_flow.id if auto_flow else None,
    )


def _poll_response(result: GitHubProjectsPollResult) -> GitHubProjectsPollNowResponse:
    return GitHubProjectsPollNowResponse(
        instance_id=result.instance_id,
        status=result.status,
        fetched_count=result.fetched_count,
        event_count=result.event_count,
        dispatched_count=result.dispatched_count,
        duplicate_count=result.duplicate_count,
        skipped_count=result.skipped_count,
        seeded=result.seeded,
        reason=result.reason,
        dispatch_statuses=list(result.dispatch_statuses),
    )


async def _run_test_connection(
    db: Session, tenant_id: str, integration_id: int, owner: str, number: int
) -> GitHubProjectsTestConnectionResponse:
    try:
        service = GitHubProjectsService(db, tenant_id, integration_id)
        info = await service.test_connection(owner, number)
        return GitHubProjectsTestConnectionResponse(
            ok=True,
            project_node_id=info.get("project_node_id"),
            title=info.get("title"),
            url=info.get("url"),
            number=info.get("number"),
        )
    except GitHubProjectsError as exc:
        return GitHubProjectsTestConnectionResponse(ok=False, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — test endpoint surfaces failures, never 500s
        logger.warning("GitHub Projects test-connection failed: %s", type(exc).__name__)
        return GitHubProjectsTestConnectionResponse(
            ok=False, error=f"Unexpected error contacting GitHub ({type(exc).__name__})."
        )


# --------------------------------------------------------------------------- routes

@router.get("", response_model=list[GitHubProjectsTriggerRead])
def list_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitHubProjectsTriggerRead]:
    rows = db.query(GitHubProjectsChannelInstance).filter(
        GitHubProjectsChannelInstance.tenant_id == ctx.tenant_id,
    ).order_by(
        GitHubProjectsChannelInstance.created_at.desc(),
        GitHubProjectsChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=GitHubProjectsTriggerRead, status_code=status.HTTP_201_CREATED)
def create_trigger(
    payload: GitHubProjectsTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubProjectsTriggerRead:
    _load_active_agent(db, ctx.tenant_id, payload.default_agent_id)
    _load_integration(db, ctx.tenant_id, payload.github_integration_id)

    instance = GitHubProjectsChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        github_integration_id=payload.github_integration_id,
        project_owner=payload.project_owner,
        project_number=payload.project_number,
        poll_interval_seconds=payload.poll_interval_seconds,
        trigger_criteria=payload.trigger_criteria,
        default_agent_id=payload.default_agent_id,
        notify_recipient_raw=payload.notify_recipient_raw,
        notification_enabled=payload.notification_enabled,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # Provision the notification-only system-managed Flow (Source → Gate →
    # Notification). Gated by TSN_FLOWS_AUTO_GENERATION_ENABLED. Failure NEVER
    # aborts trigger creation — the row is the source of truth.
    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=ctx.tenant_id,
                trigger_kind=_TRIGGER_KIND,
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
                notification_recipient=instance.notify_recipient_raw,
                notification_enabled=instance.notification_enabled,
                notification_only=True,
                notification_template=_NOTIFICATION_TEMPLATE,
            )
            db.commit()
    except Exception:
        logger.exception(
            "Auto-flow generation failed for github_projects trigger %s; trigger persists",
            instance.id,
        )
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-connection", response_model=GitHubProjectsTestConnectionResponse)
async def test_connection(
    payload: GitHubProjectsTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubProjectsTestConnectionResponse:
    if payload.github_integration_id is None:
        raise HTTPException(status_code=400, detail="github_integration_id is required")
    if not payload.project_owner or payload.project_number is None:
        raise HTTPException(status_code=400, detail="project_owner and project_number are required")
    return await _run_test_connection(
        db, ctx.tenant_id, payload.github_integration_id,
        payload.project_owner.strip(), payload.project_number,
    )


@router.post("/{trigger_id}/test-connection", response_model=GitHubProjectsTestConnectionResponse)
async def test_saved_connection(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubProjectsTestConnectionResponse:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    return await _run_test_connection(
        db, ctx.tenant_id, instance.github_integration_id,
        instance.project_owner, instance.project_number,
    )


@router.post("/{trigger_id}/poll-now", response_model=GitHubProjectsPollNowResponse)
async def poll_trigger_now(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubProjectsPollNowResponse:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    result = await GitHubProjectsTrigger.poll_instance(db, instance, force=True)
    return _poll_response(result)


@router.get("/{trigger_id}", response_model=GitHubProjectsTriggerRead)
def get_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubProjectsTriggerRead:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    return _to_read(db, instance)


@router.patch("/{trigger_id}", response_model=GitHubProjectsTriggerRead)
def update_trigger(
    trigger_id: int,
    payload: GitHubProjectsTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubProjectsTriggerRead:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    data = payload.model_dump(exclude_unset=True)

    if "default_agent_id" in data and data["default_agent_id"] is not None:
        _load_active_agent(db, ctx.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
        sync_system_managed_flow_default_agent(
            db,
            tenant_id=ctx.tenant_id,
            trigger_kind=_TRIGGER_KIND,
            trigger_instance_id=instance.id,
            default_agent_id=instance.default_agent_id,
        )
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "project_owner" in data and data["project_owner"] is not None:
        instance.project_owner = data["project_owner"].strip()
        instance.project_node_id = None  # force re-resolve on next poll
        instance.project_name = None
    if "project_number" in data and data["project_number"] is not None:
        instance.project_number = data["project_number"]
        instance.project_node_id = None
        instance.project_name = None
    if "poll_interval_seconds" in data and data["poll_interval_seconds"] is not None:
        instance.poll_interval_seconds = data["poll_interval_seconds"]
    if "trigger_criteria" in data:
        instance.trigger_criteria = data["trigger_criteria"]
    if "is_active" in data and data["is_active"] is not None:
        instance.is_active = data["is_active"]
        instance.status = "active" if data["is_active"] else "paused"

    notification_touched = False
    if "notify_recipient_raw" in data and data["notify_recipient_raw"] is not None:
        instance.notify_recipient_raw = data["notify_recipient_raw"]
        notification_touched = True
    if "notification_enabled" in data and data["notification_enabled"] is not None:
        instance.notification_enabled = data["notification_enabled"]
        notification_touched = True
    if notification_touched:
        update_auto_flow_notification(
            db,
            tenant_id=ctx.tenant_id,
            trigger_kind=_TRIGGER_KIND,
            trigger_instance_id=instance.id,
            enabled=bool(instance.notification_enabled),
            recipient_phone=instance.notify_recipient_raw,
        )

    instance.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)
    return _to_read(db, instance)


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    delete_bindings_for_trigger(
        db, tenant_id=ctx.tenant_id, trigger_kind=_TRIGGER_KIND, trigger_instance_id=trigger_id,
    )
    delete_system_owned_continuous_artifacts_for_trigger(
        db, tenant_id=ctx.tenant_id, trigger_kind=_TRIGGER_KIND, trigger_instance_id=trigger_id,
    )
    db.delete(instance)
    db.commit()
    return None
