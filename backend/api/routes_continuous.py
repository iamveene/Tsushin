"""Continuous-agent control-plane APIs.

Exposes list/detail read contracts plus CRUD for ContinuousAgent and
ContinuousSubscription rows. Wake events and continuous runs remain read-only
(they are produced by the runtime, not by user writes).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Type

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from api.api_auth import ApiCaller, get_api_caller
from auth_dependencies import (
    ensure_permission,
    get_current_user_optional_strict_from_request,
)
from db import get_db
from models import (
    Agent,
    BudgetPolicy,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    EmailChannelInstance,
    GitHubChannelInstance,
    JiraChannelInstance,
    SentinelProfile,
    WakeEvent,
    WebhookIntegration,
    WhatsAppMCPInstance,
)


router = APIRouter(tags=["Continuous Agents"])
security = HTTPBearer(auto_error=False)
BACKEND_ROOT = Path(__file__).resolve().parents[1]
WAKE_EVENT_PAYLOAD_ROOT = (BACKEND_ROOT / "data" / "wake_events").resolve()
WAKE_EVENT_PAYLOAD_REF_PREFIX = Path("backend") / "data" / "wake_events"


@dataclass(frozen=True)
class ContinuousCaller:
    tenant_id: str
    is_api_client: bool = False
    user_id: Optional[int] = None
    client_id: Optional[str] = None


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class ContinuousAgentRead(BaseModel):
    id: int
    tenant_id: str
    agent_id: int
    agent_name: Optional[str] = None
    name: Optional[str] = None
    purpose: Optional[str] = None
    action_kind: Optional[str] = None
    execution_mode: str
    status: str
    delivery_policy_id: Optional[int] = None
    budget_policy_id: Optional[int] = None
    approval_policy_id: Optional[int] = None
    is_system_owned: bool
    subscription_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class ContinuousAgentPage(BaseModel):
    items: list[ContinuousAgentRead]
    total: int
    limit: int
    offset: int


class ContinuousRunRead(BaseModel):
    id: int
    tenant_id: str
    continuous_agent_id: int
    wake_event_ids: list[int] = Field(default_factory=list)
    execution_mode: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    watcher_run_ref: Optional[str] = None
    memory_refs: Optional[dict[str, Any]] = None
    run_threat_signals: Optional[dict[str, Any]] = None
    outcome_state: Optional[dict[str, Any]] = None
    agentic_scratchpad: Optional[Any] = None
    run_type: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class ContinuousRunPage(BaseModel):
    items: list[ContinuousRunRead]
    total: int
    limit: int
    offset: int


class WakeEventRead(BaseModel):
    id: int
    tenant_id: str
    continuous_agent_id: Optional[int] = None
    continuous_subscription_id: Optional[int] = None
    channel_type: str
    channel_instance_id: int
    event_type: str
    occurred_at: datetime
    dedupe_key: str
    importance: str
    payload_ref: Optional[str] = None
    status: str
    created_at: datetime


class WakeEventPage(BaseModel):
    items: list[WakeEventRead]
    total: int
    limit: int
    offset: int


class WakeEventPayloadRead(BaseModel):
    wake_event_id: int
    payload_ref: str
    payload: Any


_AGENT_EXECUTION_MODES = {"autonomous", "hybrid", "notify_only"}
_AGENT_USER_STATUSES = {"active", "paused", "disabled"}
# v0.7.0-fix Phase 6: action_kind values communicate "what does this agent do
# when it wakes up?" — see also frontend explainer copy in agent-vs-flow-explainer.tsx
_AGENT_ACTION_KINDS = {"tool_run", "send_message", "conditional_branch", "react_only"}
# Purpose minimum length so "test", "asdf", and emoji-only inputs don't pass.
_PURPOSE_MIN_LENGTH = 30
_SUBSCRIPTION_USER_STATUSES = {"active", "paused", "disabled"}
_SUBSCRIPTION_CREATE_STATUSES = {"active", "paused"}
_ACTION_CONFIG_MAX_BYTES = 64 * 1024
_CHANNEL_INSTANCE_MODELS: dict[str, Type] = {
    "email": EmailChannelInstance,
    "jira": JiraChannelInstance,
    "github": GitHubChannelInstance,
    "webhook": WebhookIntegration,
    "whatsapp": WhatsAppMCPInstance,
}


class ContinuousAgentCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    agent_id: int = Field(..., ge=1)
    # v0.7.0-fix Phase 6: purpose + action_kind are required so operators
    # always know what each continuous agent does without reading the
    # underlying Agent's system prompt.
    purpose: str = Field(..., min_length=_PURPOSE_MIN_LENGTH, max_length=2000)
    action_kind: str = Field(...)
    execution_mode: str = "hybrid"
    delivery_policy_id: Optional[int] = Field(default=None, ge=1)
    budget_policy_id: Optional[int] = Field(default=None, ge=1)
    approval_policy_id: Optional[int] = Field(default=None, ge=1)
    status: str = "active"

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("purpose")
    @classmethod
    def _validate_purpose(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < _PURPOSE_MIN_LENGTH:
            raise ValueError(
                f"purpose must be at least {_PURPOSE_MIN_LENGTH} characters; "
                "describe what the agent does when it wakes."
            )
        return normalized

    @field_validator("action_kind")
    @classmethod
    def _validate_action_kind(cls, value: str) -> str:
        if value not in _AGENT_ACTION_KINDS:
            raise ValueError(
                f"action_kind must be one of {sorted(_AGENT_ACTION_KINDS)}"
            )
        return value

    @field_validator("execution_mode")
    @classmethod
    def _validate_mode(cls, value: str) -> str:
        if value not in _AGENT_EXECUTION_MODES:
            raise ValueError(
                f"execution_mode must be one of {sorted(_AGENT_EXECUTION_MODES)}"
            )
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in _AGENT_USER_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_AGENT_USER_STATUSES)}"
            )
        return value


class ContinuousAgentUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    purpose: Optional[str] = Field(default=None, min_length=_PURPOSE_MIN_LENGTH, max_length=2000)
    action_kind: Optional[str] = None
    execution_mode: Optional[str] = None
    delivery_policy_id: Optional[int] = Field(default=None, ge=1)
    budget_policy_id: Optional[int] = Field(default=None, ge=1)
    approval_policy_id: Optional[int] = Field(default=None, ge=1)
    status: Optional[str] = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("purpose")
    @classmethod
    def _validate_purpose(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if len(normalized) < _PURPOSE_MIN_LENGTH:
            raise ValueError(
                f"purpose must be at least {_PURPOSE_MIN_LENGTH} characters; "
                "describe what the agent does when it wakes."
            )
        return normalized

    @field_validator("action_kind")
    @classmethod
    def _validate_action_kind(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _AGENT_ACTION_KINDS:
            raise ValueError(
                f"action_kind must be one of {sorted(_AGENT_ACTION_KINDS)}"
            )
        return value

    @field_validator("execution_mode")
    @classmethod
    def _validate_mode(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _AGENT_EXECUTION_MODES:
            raise ValueError(
                f"execution_mode must be one of {sorted(_AGENT_EXECUTION_MODES)}"
            )
        return value

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _AGENT_USER_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_AGENT_USER_STATUSES)}"
            )
        return value


class ContinuousSubscriptionCreate(BaseModel):
    channel_type: str = Field(..., min_length=1, max_length=32)
    channel_instance_id: int = Field(..., ge=1)
    event_type: Optional[str] = Field(default=None, max_length=64)
    delivery_policy_id: Optional[int] = Field(default=None, ge=1)
    action_config: Optional[dict[str, Any]] = None
    status: str = "active"

    @field_validator("channel_type")
    @classmethod
    def _normalize_channel(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("event_type")
    @classmethod
    def _strip_event(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: str) -> str:
        if value not in _SUBSCRIPTION_CREATE_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_SUBSCRIPTION_CREATE_STATUSES)}"
            )
        return value

    @field_validator("action_config")
    @classmethod
    def _bound_action_config(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > _ACTION_CONFIG_MAX_BYTES:
            raise ValueError("action_config exceeds 64KB limit")
        return value


class ContinuousSubscriptionUpdate(BaseModel):
    event_type: Optional[str] = Field(default=None, max_length=64)
    delivery_policy_id: Optional[int] = Field(default=None, ge=1)
    action_config: Optional[dict[str, Any]] = None
    status: Optional[str] = None

    @field_validator("event_type")
    @classmethod
    def _strip_event(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if value not in _SUBSCRIPTION_USER_STATUSES:
            raise ValueError(
                f"status must be one of {sorted(_SUBSCRIPTION_USER_STATUSES)}"
            )
        return value

    @field_validator("action_config")
    @classmethod
    def _bound_action_config(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded.encode("utf-8")) > _ACTION_CONFIG_MAX_BYTES:
            raise ValueError("action_config exceeds 64KB limit")
        return value


class ContinuousSubscriptionRead(BaseModel):
    id: int
    tenant_id: str
    continuous_agent_id: int
    channel_type: str
    channel_instance_id: int
    event_type: Optional[str] = None
    delivery_policy_id: Optional[int] = None
    action_config: Optional[dict[str, Any]] = None
    status: str
    is_system_owned: bool
    created_at: datetime
    updated_at: Optional[datetime] = None


class ContinuousSubscriptionPage(BaseModel):
    items: list[ContinuousSubscriptionRead]
    total: int
    limit: int
    offset: int


def _caller_from_api(api_caller: ApiCaller, permission: str) -> ContinuousCaller:
    if not api_caller.has_permission(permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required: {permission}",
        )
    if not api_caller.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return ContinuousCaller(
        tenant_id=api_caller.tenant_id,
        is_api_client=api_caller.is_api_client,
        user_id=api_caller.user_id,
        client_id=api_caller.client_id,
    )


def _continuous_caller_dependency(permission: str):
    def _resolve(
        request: Request,
        credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
        x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
        db: Session = Depends(get_db),
    ) -> ContinuousCaller:
        if request.cookies.get("tsushin_session") and not credentials and not x_api_key:
            user = get_current_user_optional_strict_from_request(request, db)
            if user is None:
                raise HTTPException(status_code=401, detail="Authentication required")
            ensure_permission(user, permission, db)
            if not user.tenant_id:
                raise HTTPException(status_code=403, detail="Tenant context required")
            return ContinuousCaller(tenant_id=user.tenant_id, user_id=user.id)

        api_caller = get_api_caller(
            request=request,
            credentials=credentials,
            x_api_key=x_api_key,
            db=db,
        )
        return _caller_from_api(api_caller, permission)

    return _resolve


read_agents_caller = _continuous_caller_dependency("agents.read")
read_watcher_caller = _continuous_caller_dependency("watcher.read")
write_agents_caller = _continuous_caller_dependency("agents.write")


def _page(query, *, limit: int, offset: int):
    total = query.count()
    items = query.offset(offset).limit(limit).all()
    return items, total


def _agent_name(db: Session, agent_id: int) -> Optional[str]:
    row = db.query(Contact.friendly_name).join(Agent, Agent.contact_id == Contact.id).filter(
        Agent.id == agent_id,
    ).first()
    return row.friendly_name if row else None


def _continuous_agent_read(db: Session, row: ContinuousAgent) -> ContinuousAgentRead:
    subscription_count = db.query(ContinuousSubscription.id).filter(
        ContinuousSubscription.tenant_id == row.tenant_id,
        ContinuousSubscription.continuous_agent_id == row.id,
    ).count()
    return ContinuousAgentRead(
        id=row.id,
        tenant_id=row.tenant_id,
        agent_id=row.agent_id,
        agent_name=_agent_name(db, row.agent_id),
        name=row.name,
        purpose=row.purpose,
        action_kind=row.action_kind,
        execution_mode=row.execution_mode,
        status=row.status,
        delivery_policy_id=row.delivery_policy_id,
        budget_policy_id=row.budget_policy_id,
        approval_policy_id=row.approval_policy_id,
        is_system_owned=bool(row.is_system_owned),
        subscription_count=subscription_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _continuous_run_read(row: ContinuousRun) -> ContinuousRunRead:
    wake_ids = row.wake_event_ids or []
    return ContinuousRunRead(
        id=row.id,
        tenant_id=row.tenant_id,
        continuous_agent_id=row.continuous_agent_id,
        wake_event_ids=list(wake_ids),
        execution_mode=row.execution_mode,
        status=row.status,
        started_at=row.started_at,
        finished_at=row.finished_at,
        watcher_run_ref=row.watcher_run_ref,
        memory_refs=row.memory_refs,
        run_threat_signals=row.run_threat_signals,
        outcome_state=row.outcome_state,
        agentic_scratchpad=row.agentic_scratchpad,
        run_type=row.run_type,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _wake_event_read(row: WakeEvent) -> WakeEventRead:
    return WakeEventRead(
        id=row.id,
        tenant_id=row.tenant_id,
        continuous_agent_id=row.continuous_agent_id,
        continuous_subscription_id=row.continuous_subscription_id,
        channel_type=row.channel_type,
        channel_instance_id=row.channel_instance_id,
        event_type=row.event_type,
        occurred_at=row.occurred_at,
        dedupe_key=row.dedupe_key,
        importance=row.importance,
        payload_ref=row.payload_ref,
        status=row.status,
        created_at=row.created_at,
    )


def _load_owned_or_forbidden(
    db: Session,
    model: Type,
    row_id: int,
    tenant_id: str,
    not_found_detail: str,
):
    row = db.query(model).filter(model.id == row_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail=not_found_detail)
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    return row


def _load_policy_or_400(
    db: Session,
    model: Type,
    policy_id: Optional[int],
    tenant_id: str,
    field_name: str,
):
    if policy_id is None:
        return None
    row = db.query(model).filter(model.id == policy_id).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} not found",
        )
    if getattr(row, "tenant_id", None) != tenant_id:
        raise HTTPException(
            status_code=403,
            detail=f"{field_name} not owned by tenant",
        )
    return row


def _validate_channel_instance(
    db: Session,
    *,
    tenant_id: str,
    channel_type: str,
    channel_instance_id: int,
) -> None:
    model = _CHANNEL_INSTANCE_MODELS.get(channel_type)
    if model is None:
        raise HTTPException(
            status_code=400,
            detail="unsupported_channel_type",
        )
    row = db.query(model).filter(model.id == channel_instance_id).first()
    if row is None:
        raise HTTPException(
            status_code=400,
            detail="channel_instance_not_found",
        )
    # Inverted guard (post-review hardening, BUG-FIX-AUDIT 2026-04-25):
    # missing tenant_id is now treated as a hard failure rather than a pass.
    # Previously the code skipped the check when `instance_tenant is None`
    # which would have silently allowed cross-tenant linkage if any future
    # channel-instance model in `_CHANNEL_INSTANCE_MODELS` lacked the column.
    instance_tenant = getattr(row, "tenant_id", None)
    if instance_tenant is None or instance_tenant != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="channel_instance_cross_tenant",
        )


def _continuous_subscription_read(row: ContinuousSubscription) -> ContinuousSubscriptionRead:
    return ContinuousSubscriptionRead(
        id=row.id,
        tenant_id=row.tenant_id,
        continuous_agent_id=row.continuous_agent_id,
        channel_type=row.channel_type,
        channel_instance_id=row.channel_instance_id,
        event_type=row.event_type,
        delivery_policy_id=row.delivery_policy_id,
        action_config=row.action_config,
        status=row.status,
        is_system_owned=bool(row.is_system_owned),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _ensure_user_writable_agent(row: ContinuousAgent, *, action: str) -> None:
    if bool(row.is_system_owned):
        raise HTTPException(
            status_code=403,
            detail=f"system_owned_agent_{action}_blocked",
        )


def _path_is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _wake_payload_path(payload_ref: str) -> Path:
    root = WAKE_EVENT_PAYLOAD_ROOT.resolve()
    ref_path = Path(payload_ref)

    if ref_path.is_absolute():
        candidate = ref_path.resolve()
    else:
        normalized = Path(*[part for part in ref_path.parts if part not in ("", ".")])
        if _path_is_relative_to(normalized, WAKE_EVENT_PAYLOAD_REF_PREFIX):
            candidate = (root / normalized.relative_to(WAKE_EVENT_PAYLOAD_REF_PREFIX)).resolve()
        elif len(normalized.parts) == 1:
            candidate = (root / normalized).resolve()
        else:
            raise HTTPException(status_code=404, detail="Wake event payload not found")

    if not _path_is_relative_to(candidate, root):
        raise HTTPException(status_code=404, detail="Wake event payload not found")
    if candidate.suffix.lower() != ".json" or not candidate.is_file():
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Wake event payload unavailable")
    return candidate


@router.get("/api/continuous-agents", response_model=ContinuousAgentPage)
def list_continuous_agents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    caller: ContinuousCaller = Depends(read_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousAgentPage:
    query = db.query(ContinuousAgent).filter(ContinuousAgent.tenant_id == caller.tenant_id)
    if status_filter:
        query = query.filter(ContinuousAgent.status == status_filter)
    query = query.order_by(ContinuousAgent.created_at.desc(), ContinuousAgent.id.desc())
    rows, total = _page(query, limit=limit, offset=offset)
    return ContinuousAgentPage(
        items=[_continuous_agent_read(db, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/continuous-agents/{continuous_agent_id}", response_model=ContinuousAgentRead)
def get_continuous_agent(
    continuous_agent_id: int,
    caller: ContinuousCaller = Depends(read_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousAgentRead:
    row = _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    return _continuous_agent_read(db, row)


@router.get("/api/continuous-runs", response_model=ContinuousRunPage)
def list_continuous_runs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    continuous_agent_id: Optional[int] = Query(default=None, ge=1),
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> ContinuousRunPage:
    query = db.query(ContinuousRun).filter(ContinuousRun.tenant_id == caller.tenant_id)
    if status_filter:
        query = query.filter(ContinuousRun.status == status_filter)
    if continuous_agent_id is not None:
        owned = db.query(ContinuousAgent.id).filter(
            ContinuousAgent.id == continuous_agent_id,
        ).first()
        if owned is None:
            raise HTTPException(status_code=404, detail="Continuous agent not found")
        owned_for_tenant = db.query(ContinuousAgent.id).filter(
            ContinuousAgent.id == continuous_agent_id,
            ContinuousAgent.tenant_id == caller.tenant_id,
        ).first()
        if owned_for_tenant is None:
            raise HTTPException(status_code=403, detail="Cross-tenant access denied")
        query = query.filter(ContinuousRun.continuous_agent_id == continuous_agent_id)
    query = query.order_by(ContinuousRun.created_at.desc(), ContinuousRun.id.desc())
    rows, total = _page(query, limit=limit, offset=offset)
    return ContinuousRunPage(
        items=[_continuous_run_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/continuous-runs/{continuous_run_id}", response_model=ContinuousRunRead)
def get_continuous_run(
    continuous_run_id: int,
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> ContinuousRunRead:
    row = _load_owned_or_forbidden(
        db,
        ContinuousRun,
        continuous_run_id,
        caller.tenant_id,
        "Continuous run not found",
    )
    return _continuous_run_read(row)


@router.get("/api/wake-events", response_model=WakeEventPage)
def list_wake_events(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    channel_type: Optional[str] = Query(default=None),
    channel_instance_id: Optional[int] = Query(default=None, ge=1),
    occurred_after: Optional[datetime] = Query(default=None),
    occurred_before: Optional[datetime] = Query(default=None),
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> WakeEventPage:
    query = db.query(WakeEvent).filter(WakeEvent.tenant_id == caller.tenant_id)
    if status_filter:
        query = query.filter(WakeEvent.status == status_filter)
    if channel_type:
        query = query.filter(WakeEvent.channel_type == channel_type)
    if channel_instance_id is not None:
        query = query.filter(WakeEvent.channel_instance_id == channel_instance_id)
    if occurred_after is not None:
        query = query.filter(WakeEvent.occurred_at >= occurred_after)
    if occurred_before is not None:
        query = query.filter(WakeEvent.occurred_at <= occurred_before)
    query = query.order_by(WakeEvent.occurred_at.desc(), WakeEvent.id.desc())
    rows, total = _page(query, limit=limit, offset=offset)
    return WakeEventPage(
        items=[_wake_event_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/api/wake-events/{wake_event_id}/payload", response_model=WakeEventPayloadRead)
def get_wake_event_payload(
    wake_event_id: int,
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> WakeEventPayloadRead:
    row = _load_owned_or_forbidden(
        db,
        WakeEvent,
        wake_event_id,
        caller.tenant_id,
        "Wake event not found",
    )
    if not row.payload_ref:
        raise HTTPException(status_code=404, detail="Wake event payload not found")

    payload_path = _wake_payload_path(row.payload_ref)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Wake event payload unavailable")

    return WakeEventPayloadRead(
        wake_event_id=row.id,
        payload_ref=row.payload_ref,
        payload=payload,
    )


@router.get("/api/wake-events/{wake_event_id}", response_model=WakeEventRead)
def get_wake_event(
    wake_event_id: int,
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> WakeEventRead:
    row = _load_owned_or_forbidden(
        db,
        WakeEvent,
        wake_event_id,
        caller.tenant_id,
        "Wake event not found",
    )
    return _wake_event_read(row)


@router.post(
    "/api/continuous-agents",
    response_model=ContinuousAgentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_continuous_agent(
    payload: ContinuousAgentCreate,
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousAgentRead:
    agent = db.query(Agent).filter(Agent.id == payload.agent_id).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    if agent.tenant_id != caller.tenant_id:
        raise HTTPException(status_code=403, detail="Agent not owned by tenant")

    _load_policy_or_400(db, DeliveryPolicy, payload.delivery_policy_id, caller.tenant_id, "delivery_policy")
    _load_policy_or_400(db, BudgetPolicy, payload.budget_policy_id, caller.tenant_id, "budget_policy")
    _load_policy_or_400(db, SentinelProfile, payload.approval_policy_id, caller.tenant_id, "approval_policy")

    row = ContinuousAgent(
        tenant_id=caller.tenant_id,
        agent_id=payload.agent_id,
        name=payload.name,
        purpose=payload.purpose,
        action_kind=payload.action_kind,
        execution_mode=payload.execution_mode,
        delivery_policy_id=payload.delivery_policy_id,
        budget_policy_id=payload.budget_policy_id,
        approval_policy_id=payload.approval_policy_id,
        status=payload.status,
        is_system_owned=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _continuous_agent_read(db, row)


@router.patch(
    "/api/continuous-agents/{continuous_agent_id}",
    response_model=ContinuousAgentRead,
)
def update_continuous_agent(
    continuous_agent_id: int,
    payload: ContinuousAgentUpdate,
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousAgentRead:
    row = _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return _continuous_agent_read(db, row)

    if bool(row.is_system_owned) and data.get("status") == "disabled":
        raise HTTPException(
            status_code=403,
            detail="system_owned_agent_disable_blocked",
        )

    if "delivery_policy_id" in data and data["delivery_policy_id"] is not None:
        _load_policy_or_400(db, DeliveryPolicy, data["delivery_policy_id"], caller.tenant_id, "delivery_policy")
    if "budget_policy_id" in data and data["budget_policy_id"] is not None:
        _load_policy_or_400(db, BudgetPolicy, data["budget_policy_id"], caller.tenant_id, "budget_policy")
    if "approval_policy_id" in data and data["approval_policy_id"] is not None:
        _load_policy_or_400(db, SentinelProfile, data["approval_policy_id"], caller.tenant_id, "approval_policy")

    for field in (
        "name",
        "purpose",
        "action_kind",
        "execution_mode",
        "delivery_policy_id",
        "budget_policy_id",
        "approval_policy_id",
        "status",
    ):
        if field in data:
            setattr(row, field, data[field])

    db.add(row)
    db.commit()
    db.refresh(row)
    return _continuous_agent_read(db, row)


@router.delete(
    "/api/continuous-agents/{continuous_agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_continuous_agent(
    continuous_agent_id: int,
    force: bool = Query(default=False),
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> None:
    row = _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    _ensure_user_writable_agent(row, action="delete")

    pending_q = db.query(WakeEvent).filter(
        WakeEvent.tenant_id == caller.tenant_id,
        WakeEvent.continuous_agent_id == continuous_agent_id,
        WakeEvent.status.in_(("pending", "claimed")),
    )
    pending_count = pending_q.count()
    if pending_count > 0 and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "agent_has_pending_wake_events",
                "count": pending_count,
                "message": (
                    "Agent has pending or claimed wake events. "
                    "Pass ?force=true to filter them and delete the agent."
                ),
            },
        )
    if pending_count > 0:
        for event in pending_q.all():
            event.status = "filtered"
            event.continuous_agent_id = None
            db.add(event)
        db.flush()

    db.query(ContinuousSubscription).filter(
        ContinuousSubscription.continuous_agent_id == continuous_agent_id,
    ).delete(synchronize_session=False)

    db.delete(row)
    db.commit()


@router.get(
    "/api/continuous-agents/{continuous_agent_id}/subscriptions",
    response_model=ContinuousSubscriptionPage,
)
def list_continuous_subscriptions(
    continuous_agent_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    caller: ContinuousCaller = Depends(read_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousSubscriptionPage:
    _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    query = db.query(ContinuousSubscription).filter(
        ContinuousSubscription.tenant_id == caller.tenant_id,
        ContinuousSubscription.continuous_agent_id == continuous_agent_id,
    ).order_by(ContinuousSubscription.created_at.desc(), ContinuousSubscription.id.desc())
    rows, total = _page(query, limit=limit, offset=offset)
    return ContinuousSubscriptionPage(
        items=[_continuous_subscription_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/api/continuous-agents/{continuous_agent_id}/subscriptions",
    response_model=ContinuousSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_continuous_subscription(
    continuous_agent_id: int,
    payload: ContinuousSubscriptionCreate,
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousSubscriptionRead:
    parent = _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )

    _validate_channel_instance(
        db,
        tenant_id=caller.tenant_id,
        channel_type=payload.channel_type,
        channel_instance_id=payload.channel_instance_id,
    )

    if payload.delivery_policy_id is not None:
        _load_policy_or_400(
            db, DeliveryPolicy, payload.delivery_policy_id, caller.tenant_id, "delivery_policy",
        )

    duplicate = db.query(ContinuousSubscription).filter(
        ContinuousSubscription.tenant_id == caller.tenant_id,
        ContinuousSubscription.continuous_agent_id == parent.id,
        ContinuousSubscription.channel_type == payload.channel_type,
        ContinuousSubscription.channel_instance_id == payload.channel_instance_id,
        ContinuousSubscription.event_type == payload.event_type,
    ).first()
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="subscription_already_exists",
        )

    row = ContinuousSubscription(
        tenant_id=caller.tenant_id,
        continuous_agent_id=parent.id,
        channel_type=payload.channel_type,
        channel_instance_id=payload.channel_instance_id,
        event_type=payload.event_type,
        delivery_policy_id=payload.delivery_policy_id,
        action_config=payload.action_config,
        status=payload.status,
        is_system_owned=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _continuous_subscription_read(row)


@router.patch(
    "/api/continuous-agents/{continuous_agent_id}/subscriptions/{subscription_id}",
    response_model=ContinuousSubscriptionRead,
)
def update_continuous_subscription(
    continuous_agent_id: int,
    subscription_id: int,
    payload: ContinuousSubscriptionUpdate,
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> ContinuousSubscriptionRead:
    _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    sub = _load_owned_or_forbidden(
        db,
        ContinuousSubscription,
        subscription_id,
        caller.tenant_id,
        "Continuous subscription not found",
    )
    if sub.continuous_agent_id != continuous_agent_id:
        raise HTTPException(status_code=404, detail="Continuous subscription not found")

    data = payload.model_dump(exclude_unset=True)
    if not data:
        return _continuous_subscription_read(sub)

    if bool(sub.is_system_owned) and data.get("status") == "disabled":
        raise HTTPException(
            status_code=403,
            detail="system_owned_subscription_disable_blocked",
        )

    if "delivery_policy_id" in data and data["delivery_policy_id"] is not None:
        _load_policy_or_400(
            db, DeliveryPolicy, data["delivery_policy_id"], caller.tenant_id, "delivery_policy",
        )

    for field in ("event_type", "delivery_policy_id", "action_config", "status"):
        if field in data:
            setattr(sub, field, data[field])

    db.add(sub)
    db.commit()
    db.refresh(sub)
    return _continuous_subscription_read(sub)


@router.delete(
    "/api/continuous-agents/{continuous_agent_id}/subscriptions/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_continuous_subscription(
    continuous_agent_id: int,
    subscription_id: int,
    caller: ContinuousCaller = Depends(write_agents_caller),
    db: Session = Depends(get_db),
) -> None:
    _load_owned_or_forbidden(
        db,
        ContinuousAgent,
        continuous_agent_id,
        caller.tenant_id,
        "Continuous agent not found",
    )
    sub = _load_owned_or_forbidden(
        db,
        ContinuousSubscription,
        subscription_id,
        caller.tenant_id,
        "Continuous subscription not found",
    )
    if sub.continuous_agent_id != continuous_agent_id:
        raise HTTPException(status_code=404, detail="Continuous subscription not found")
    if bool(sub.is_system_owned):
        raise HTTPException(
            status_code=403,
            detail="system_owned_subscription_delete_blocked",
        )
    db.delete(sub)
    db.commit()


__all__ = [
    "BudgetPolicy",
    "ContinuousAgent",
    "ContinuousRun",
    "ContinuousSubscription",
    "DeliveryPolicy",
    "WakeEvent",
    "router",
]
