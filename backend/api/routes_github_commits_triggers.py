"""GitHub commit-polling trigger CRUD + poll-now + test-connection endpoints.

Mirrors ``routes_github_projects_triggers.py``. On create it provisions a
**notification-only** system-managed Flow (Source → Gate → Notification) whose
Notification node renders ``{{source.payload.message}}`` — the trigger
pre-composes the WhatsApp text, so no LLM runs per commit.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.github_commits.trigger import GitHubCommitsPollResult, GitHubCommitsTrigger
from db import get_db
from hub.github.github_repository_service import GitHubRepositoryError, GitHubRepositoryService
from models import Agent, Contact, GitHubCommitsChannelInstance, GitHubIntegration
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
    prefix="/api/triggers/github-commits",
    tags=["GitHub Commits Triggers"],
    redirect_slashes=False,
)

_TRIGGER_KIND = "github_commits"
# The trigger pre-composes the message; the Notification node renders it verbatim.
_NOTIFICATION_TEMPLATE = "{{source.payload.message}}"


# --------------------------------------------------------------------------- schemas

class GitHubCommitsTriggerCreate(BaseModel):
    integration_name: str = Field(min_length=1, max_length=100)
    github_integration_id: int = Field(ge=1)
    repo_owner: str = Field(min_length=1, max_length=100)
    repo_name: str = Field(min_length=1, max_length=100)
    branch: Optional[str] = Field(default=None, max_length=255)  # NULL = repo default branch
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)
    # Required: commit notifications are delivered through this agent's bound Flow
    # (dispatch only fans out to the Notification node when an agent resolves).
    default_agent_id: int = Field(ge=1)
    notify_recipient_raw: str = Field(default="@Playground", min_length=1, max_length=100)
    notification_enabled: bool = True
    trigger_criteria: Optional[dict] = None
    is_active: bool = True

    @field_validator("repo_owner", "repo_name")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("branch")
    @classmethod
    def _strip_branch(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class GitHubCommitsTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, max_length=100)
    repo_owner: Optional[str] = Field(default=None, max_length=100)
    repo_name: Optional[str] = Field(default=None, max_length=100)
    branch: Optional[str] = Field(default=None, max_length=255)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    notify_recipient_raw: Optional[str] = Field(default=None, max_length=100)
    notification_enabled: Optional[bool] = None
    trigger_criteria: Optional[dict] = None
    is_active: Optional[bool] = None


class GitHubCommitsTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    github_integration_id: int
    github_integration_name: Optional[str] = None
    repo_owner: str
    repo_name: str
    branch: Optional[str] = None
    last_seen_sha: Optional[str] = None
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


class GitHubCommitsTestConnectionRequest(BaseModel):
    github_integration_id: Optional[int] = Field(default=None, ge=1)
    repo_owner: Optional[str] = None
    repo_name: Optional[str] = None
    branch: Optional[str] = None


class GitHubCommitsTestConnectionResponse(BaseModel):
    ok: bool
    repo_full_name: Optional[str] = None
    branch: Optional[str] = None
    latest_sha: Optional[str] = None
    latest_message: Optional[str] = None
    error: Optional[str] = None


class GitHubCommitsPollNowResponse(BaseModel):
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


def _load_trigger(db: Session, tenant_id: str, trigger_id: int) -> GitHubCommitsChannelInstance:
    instance = db.query(GitHubCommitsChannelInstance).filter(
        GitHubCommitsChannelInstance.id == trigger_id,
        GitHubCommitsChannelInstance.tenant_id == tenant_id,
    ).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="GitHub commits trigger not found")
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


def _to_read(db: Session, instance: GitHubCommitsChannelInstance) -> GitHubCommitsTriggerRead:
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
    return GitHubCommitsTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        github_integration_id=instance.github_integration_id,
        github_integration_name=integration_name,
        repo_owner=instance.repo_owner,
        repo_name=instance.repo_name,
        branch=instance.branch,
        last_seen_sha=instance.last_seen_sha,
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


def _poll_response(result: GitHubCommitsPollResult) -> GitHubCommitsPollNowResponse:
    return GitHubCommitsPollNowResponse(
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
    db: Session, tenant_id: str, integration_id: int, owner: str, repo: str, branch: Optional[str]
) -> GitHubCommitsTestConnectionResponse:
    try:
        service = GitHubRepositoryService(db, tenant_id, integration_id)
        commits = await service.list_commits(owner, repo, sha=(branch or None), max_results=1)
        if not commits:
            return GitHubCommitsTestConnectionResponse(
                ok=False,
                repo_full_name=f"{owner}/{repo}",
                branch=branch,
                error="No commits found for that repo/branch (check the branch name).",
            )
        head = commits[0]
        message = str((head.get("commit") or {}).get("message") or "").strip().splitlines()
        return GitHubCommitsTestConnectionResponse(
            ok=True,
            repo_full_name=f"{owner}/{repo}",
            branch=branch,
            latest_sha=str(head.get("sha") or "")[:40] or None,
            latest_message=(message[0][:200] if message else None),
        )
    except GitHubRepositoryError as exc:
        return GitHubCommitsTestConnectionResponse(
            ok=False, repo_full_name=f"{owner}/{repo}", branch=branch, error=str(exc)
        )
    except Exception as exc:  # noqa: BLE001 — test endpoint surfaces failures, never 500s
        logger.warning("GitHub commits test-connection failed: %s", type(exc).__name__)
        return GitHubCommitsTestConnectionResponse(
            ok=False,
            repo_full_name=f"{owner}/{repo}",
            branch=branch,
            error=f"Unexpected error contacting GitHub ({type(exc).__name__}).",
        )


# --------------------------------------------------------------------------- routes

@router.get("", response_model=list[GitHubCommitsTriggerRead])
def list_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitHubCommitsTriggerRead]:
    rows = db.query(GitHubCommitsChannelInstance).filter(
        GitHubCommitsChannelInstance.tenant_id == ctx.tenant_id,
    ).order_by(
        GitHubCommitsChannelInstance.created_at.desc(),
        GitHubCommitsChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=GitHubCommitsTriggerRead, status_code=status.HTTP_201_CREATED)
def create_trigger(
    payload: GitHubCommitsTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubCommitsTriggerRead:
    _load_active_agent(db, ctx.tenant_id, payload.default_agent_id)
    _load_integration(db, ctx.tenant_id, payload.github_integration_id)

    instance = GitHubCommitsChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        github_integration_id=payload.github_integration_id,
        repo_owner=payload.repo_owner,
        repo_name=payload.repo_name,
        branch=payload.branch,
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
            "Auto-flow generation failed for github_commits trigger %s; trigger persists",
            instance.id,
        )
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-connection", response_model=GitHubCommitsTestConnectionResponse)
async def test_connection(
    payload: GitHubCommitsTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubCommitsTestConnectionResponse:
    if payload.github_integration_id is None:
        raise HTTPException(status_code=400, detail="github_integration_id is required")
    if not payload.repo_owner or not payload.repo_name:
        raise HTTPException(status_code=400, detail="repo_owner and repo_name are required")
    return await _run_test_connection(
        db, ctx.tenant_id, payload.github_integration_id,
        payload.repo_owner.strip(), payload.repo_name.strip(),
        (payload.branch or "").strip() or None,
    )


@router.post("/{trigger_id}/test-connection", response_model=GitHubCommitsTestConnectionResponse)
async def test_saved_connection(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubCommitsTestConnectionResponse:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    return await _run_test_connection(
        db, ctx.tenant_id, instance.github_integration_id,
        instance.repo_owner, instance.repo_name, instance.branch,
    )


@router.post("/{trigger_id}/poll-now", response_model=GitHubCommitsPollNowResponse)
async def poll_trigger_now(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubCommitsPollNowResponse:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    result = await GitHubCommitsTrigger.poll_instance(db, instance, force=True)
    return _poll_response(result)


@router.get("/{trigger_id}", response_model=GitHubCommitsTriggerRead)
def get_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubCommitsTriggerRead:
    instance = _load_trigger(db, ctx.tenant_id, trigger_id)
    return _to_read(db, instance)


@router.patch("/{trigger_id}", response_model=GitHubCommitsTriggerRead)
def update_trigger(
    trigger_id: int,
    payload: GitHubCommitsTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubCommitsTriggerRead:
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
    if "integration_name" in data and data["integration_name"] is not None:
        instance.integration_name = data["integration_name"]
    if "repo_owner" in data and data["repo_owner"] is not None:
        instance.repo_owner = data["repo_owner"].strip()
        instance.last_seen_sha = None  # repo changed → re-seed on next poll
        instance.seeded_at = None
    if "repo_name" in data and data["repo_name"] is not None:
        instance.repo_name = data["repo_name"].strip()
        instance.last_seen_sha = None
        instance.seeded_at = None
    if "branch" in data:
        new_branch = (data["branch"] or "").strip() or None
        if new_branch != instance.branch:
            instance.branch = new_branch
            instance.last_seen_sha = None  # branch changed → re-seed on next poll
            instance.seeded_at = None
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
