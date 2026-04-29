"""v0.7.0 Trigger Case Memory MVP — admin/debug API.

Three endpoints, all tenant-scoped via ``TenantContext``:
  - ``GET  /api/case-memory``         — list cases with filters.
  - ``GET  /api/case-memory/{id}``    — single case detail.
  - ``POST /api/case-memory/search``  — semantic search across the
                                         tenant's cases.

Permission scope: this is an operator/debug surface — there is no
dedicated ``memory.read`` permission in the current RBAC seeding, so we
piggy-back on ``agents.read`` (the closest existing read scope used by
``routes_knowledge.py``). Authenticated tenant members with read access
to agents see only their own tenant's cases; ``ctx.filter_by_tenant``
enforces strict isolation.

Mounting: ``app.py`` mounts this router only when
``case_memory_enabled()`` returns True at startup. When the flag flips
without a restart, the endpoints simply won't be served — flipping the
flag requires a backend restart by design (matches other v0.7.0 flag
toggles).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import Agent, CaseMemory
from models_rbac import User

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/case-memory", tags=["case-memory"])


# --- Schemas -----------------------------------------------------------------


class CaseMemoryRead(BaseModel):
    """Read-side projection of a ``CaseMemory`` row.

    Mirrors §4 of the research doc (``.private/TRIGGER_MEMORY_RESEARCH.md``).
    """

    id: int
    tenant_id: str
    agent_id: int
    wake_event_id: Optional[int] = None
    continuous_run_id: Optional[int] = None
    flow_run_id: Optional[int] = None
    origin_kind: str
    trigger_kind: Optional[str] = None
    subject_digest: Optional[str] = None
    problem_summary: Optional[str] = None
    action_summary: Optional[str] = None
    outcome_summary: Optional[str] = None
    outcome_label: str
    vector_store_instance_id: Optional[int] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    embedding_dims: Optional[int] = None
    embedding_metric: Optional[str] = None
    embedding_task: Optional[str] = None
    vector_refs_json: Optional[Any] = None
    index_status: str
    summary_status: str
    occurred_at: Optional[datetime] = None
    indexed_at: Optional[datetime] = None
    last_recalled_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CaseMemoryPage(BaseModel):
    items: List[CaseMemoryRead]
    total: int
    limit: int
    offset: int


class CaseMemorySearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=4096)
    scope: str = Field("agent", pattern="^(agent|trigger_kind|tenant)$")
    k: int = Field(3, ge=1, le=50)
    min_similarity: float = Field(0.65, ge=0.0, le=1.0)
    vector: str = Field("problem", pattern="^(problem|action|outcome|any)$")
    trigger_kind: Optional[str] = None
    include_failed: bool = True
    agent_id: Optional[int] = None


class CaseMemorySearchResultItem(BaseModel):
    case_id: int
    occurred_at_iso: Optional[str] = None
    similarity: float
    problem_summary: Optional[str] = None
    action_summary: Optional[str] = None
    outcome_summary: Optional[str] = None
    outcome_label: Optional[str] = None
    origin_kind: Optional[str] = None
    trigger_kind: Optional[str] = None
    wake_event_id: Optional[int] = None
    continuous_run_id: Optional[int] = None
    flow_run_id: Optional[int] = None


class CaseMemorySearchResponse(BaseModel):
    items: List[CaseMemorySearchResultItem]
    scope: str
    k: int
    min_similarity: float


# --- Helpers -----------------------------------------------------------------


def _validate_agent_belongs_to_tenant(
    db: Session, *, tenant_id: str, agent_id: int
) -> None:
    agent = (
        db.query(Agent)
        .filter(Agent.id == agent_id, Agent.tenant_id == tenant_id)
        .first()
    )
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found in this tenant",
        )


# --- Routes ------------------------------------------------------------------


@router.get("", response_model=CaseMemoryPage)
def list_case_memory(
    agent_id: Optional[int] = Query(None),
    trigger_kind: Optional[str] = Query(None),
    origin_kind: Optional[str] = Query(None, pattern="^(continuous_run|flow_run)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    ctx: TenantContext = Depends(get_tenant_context),
    _: User = Depends(require_permission("agents.read")),
    db: Session = Depends(get_db),
) -> CaseMemoryPage:
    """List CaseMemory rows for the current tenant with optional filters."""
    query = db.query(CaseMemory)
    query = ctx.filter_by_tenant(query, CaseMemory.tenant_id)
    if agent_id is not None:
        query = query.filter(CaseMemory.agent_id == agent_id)
    if trigger_kind is not None:
        query = query.filter(CaseMemory.trigger_kind == trigger_kind)
    if origin_kind is not None:
        query = query.filter(CaseMemory.origin_kind == origin_kind)

    total = query.count()
    rows = (
        query.order_by(CaseMemory.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return CaseMemoryPage(
        items=[CaseMemoryRead.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{case_id}", response_model=CaseMemoryRead)
def get_case_memory(
    case_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _: User = Depends(require_permission("agents.read")),
    db: Session = Depends(get_db),
) -> CaseMemoryRead:
    """Fetch a single CaseMemory row, scoped to the current tenant."""
    query = db.query(CaseMemory).filter(CaseMemory.id == case_id)
    query = ctx.filter_by_tenant(query, CaseMemory.tenant_id)
    row = query.first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CaseMemory {case_id} not found",
        )
    return CaseMemoryRead.model_validate(row)


@router.post("/search", response_model=CaseMemorySearchResponse)
def search_case_memory(
    body: CaseMemorySearchRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _: User = Depends(require_permission("agents.read")),
    db: Session = Depends(get_db),
) -> CaseMemorySearchResponse:
    """Semantic search over the tenant's CaseMemory rows.

    Note: ``scope="tenant"`` resolves the vector store against a representative
    agent. If different agents in the tenant use different
    ``VectorStoreInstance`` rows, tenant-scope search may miss cases stored
    against a non-representative agent's instance. For 0.7.0 the API requires
    ``agent_id`` whenever ``scope="tenant"`` is used, so callers must pick a
    representative agent themselves and acknowledge the limitation. A future
    iteration will fan out across instances or add a dedicated case-memory
    routing layer.
    """
    from services.case_memory_service import search_similar_cases

    if body.scope == "tenant" and body.agent_id is None:
        raise HTTPException(
            status_code=400,
            detail=(
                "scope='tenant' requires agent_id in the v0.7.0 MVP — "
                "the underlying vector store is resolved per agent, so a "
                "representative agent_id must be supplied."
            ),
        )

    if body.agent_id is not None:
        _validate_agent_belongs_to_tenant(db, tenant_id=ctx.tenant_id, agent_id=body.agent_id)

    results = search_similar_cases(
        db,
        tenant_id=ctx.tenant_id,
        agent_id=body.agent_id,
        query=body.query,
        scope=body.scope,
        k=body.k,
        min_similarity=body.min_similarity,
        vector=body.vector,
        trigger_kind=body.trigger_kind,
        include_failed=body.include_failed,
    )

    return CaseMemorySearchResponse(
        items=[CaseMemorySearchResultItem(**r) for r in results],
        scope=body.scope,
        k=body.k,
        min_similarity=body.min_similarity,
    )
