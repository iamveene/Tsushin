"""Read-only continuous-agent control-plane APIs.

A2 deliberately exposes list/detail read endpoints only. Creation and mutation
of continuous agents, subscriptions, wake events, and runs are reserved for
later trigger/wizard tracks once the contracts are stable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Type

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
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
    WakeEvent,
)


router = APIRouter(tags=["Continuous Agents"])
security = HTTPBearer(auto_error=False)


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
    caller: ContinuousCaller = Depends(read_watcher_caller),
    db: Session = Depends(get_db),
) -> WakeEventPage:
    query = db.query(WakeEvent).filter(WakeEvent.tenant_id == caller.tenant_id)
    if status_filter:
        query = query.filter(WakeEvent.status == status_filter)
    if channel_type:
        query = query.filter(WakeEvent.channel_type == channel_type)
    query = query.order_by(WakeEvent.occurred_at.desc(), WakeEvent.id.desc())
    rows, total = _page(query, limit=limit, offset=offset)
    return WakeEventPage(
        items=[_wake_event_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
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


__all__ = [
    "BudgetPolicy",
    "ContinuousAgent",
    "ContinuousRun",
    "DeliveryPolicy",
    "WakeEvent",
    "router",
]
