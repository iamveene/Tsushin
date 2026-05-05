"""Flow ↔ Trigger Binding CRUD endpoints (v0.7.0 Wave 4).

Public REST surface for the ``flow_trigger_binding`` table — used by the
trigger-detail "Wired Flows" card on the frontend (list + suppress-default
toggle + unbind), and by the create-flow modal's deep-link prefill flow
(POST a binding right after the flow is created).

System-managed bindings (``is_system_managed=True``, created by Wave 4's
auto-Flow generation) cannot be deleted via this endpoint — they live and
die with the trigger. Their flows are also protected by Wave 2's
``editable_by_tenant=True, deletable_by_tenant=False`` rules so the user
can edit the auto-flow's nodes (e.g. to flip the Notification node) but
not delete the flow itself.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import (
    EmailChannelInstance,
    FlowDefinition,
    FlowNode,
    FlowRun,
    FlowTriggerBinding,
    GitHubChannelInstance,
    JiraChannelInstance,
    WebhookIntegration,
)
from services.flow_binding_service import find_source_node_id

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flow-trigger-bindings", tags=["flow-trigger-bindings"])


_VALID_KINDS = {"jira", "email", "github", "webhook"}
_TRIGGER_MODELS = {
    "email": EmailChannelInstance,
    "jira": JiraChannelInstance,
    "github": GitHubChannelInstance,
    "webhook": WebhookIntegration,
}


class FlowTriggerBindingRead(BaseModel):
    id: int
    tenant_id: str
    flow_definition_id: int
    flow_name: Optional[str] = None
    trigger_kind: str
    trigger_instance_id: int
    source_node_id: Optional[int] = None
    suppress_default_agent: bool
    is_active: bool
    is_system_managed: bool
    created_at: datetime
    updated_at: datetime
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime] = None


class FlowTriggerBindingCreate(BaseModel):
    flow_definition_id: int
    trigger_kind: str = Field(pattern="^(jira|email|github|webhook)$")
    trigger_instance_id: int = Field(ge=1)
    suppress_default_agent: bool = True
    source_node_id: Optional[int] = None
    is_active: bool = True


class FlowTriggerBindingUpdate(BaseModel):
    is_active: Optional[bool] = None
    suppress_default_agent: Optional[bool] = None


def _to_read(db: Session, binding: FlowTriggerBinding) -> FlowTriggerBindingRead:
    flow = db.query(FlowDefinition).filter(FlowDefinition.id == binding.flow_definition_id).first()
    last_run = (
        db.query(FlowRun)
        .filter(FlowRun.flow_definition_id == binding.flow_definition_id)
        .order_by(FlowRun.created_at.desc())
        .first()
    )
    return FlowTriggerBindingRead(
        id=binding.id,
        tenant_id=binding.tenant_id,
        flow_definition_id=binding.flow_definition_id,
        flow_name=flow.name if flow else None,
        trigger_kind=binding.trigger_kind,
        trigger_instance_id=binding.trigger_instance_id,
        source_node_id=binding.source_node_id,
        suppress_default_agent=binding.suppress_default_agent,
        is_active=binding.is_active,
        is_system_managed=binding.is_system_managed,
        created_at=binding.created_at,
        updated_at=binding.updated_at,
        last_run_status=last_run.status if last_run else None,
        last_run_at=last_run.completed_at or (last_run.started_at if last_run else None) if last_run else None,
    )


def _load_trigger_or_404(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
):
    model = _TRIGGER_MODELS.get(trigger_kind)
    if model is None:
        raise HTTPException(status_code=422, detail=f"trigger_kind must be one of {sorted(_VALID_KINDS)}")
    trigger = db.query(model).filter(model.id == trigger_instance_id).first()
    if trigger is None:
        raise HTTPException(status_code=404, detail=f"{trigger_kind} trigger not found")
    if getattr(trigger, "tenant_id", None) != tenant_id:
        raise HTTPException(status_code=403, detail=f"{trigger_kind} trigger not owned by tenant")
    return trigger


@router.get("", response_model=list[FlowTriggerBindingRead], dependencies=[Depends(require_permission("flows.read"))])
def list_bindings(
    trigger_kind: Optional[str] = None,
    trigger_id: Optional[int] = None,
    flow_id: Optional[int] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List bindings, scoped to the calling tenant.

    Filters compose: ``trigger_kind`` + ``trigger_id`` together return all
    flows wired to a single trigger; ``flow_id`` returns all triggers a
    flow listens to. Both can be supplied together.
    """
    if trigger_kind is not None and trigger_kind not in _VALID_KINDS:
        raise HTTPException(status_code=422, detail=f"trigger_kind must be one of {sorted(_VALID_KINDS)}")

    query = db.query(FlowTriggerBinding).filter(
        FlowTriggerBinding.tenant_id == ctx.tenant_id,
        FlowTriggerBinding.trigger_kind.in_(sorted(_VALID_KINDS)),
    )
    if trigger_kind is not None:
        query = query.filter(FlowTriggerBinding.trigger_kind == trigger_kind)
    if trigger_id is not None:
        query = query.filter(FlowTriggerBinding.trigger_instance_id == trigger_id)
    if flow_id is not None:
        query = query.filter(FlowTriggerBinding.flow_definition_id == flow_id)
    if is_active is not None:
        query = query.filter(FlowTriggerBinding.is_active == is_active)

    bindings = query.order_by(FlowTriggerBinding.created_at.desc()).all()
    return [_to_read(db, b) for b in bindings]


@router.post("", response_model=FlowTriggerBindingRead, status_code=201, dependencies=[Depends(require_permission("flows.write"))])
def create_binding(
    payload: FlowTriggerBindingCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create a binding between a flow and a trigger.

    Validates: flow exists in this tenant; the (flow, kind, instance)
    triple is unique (the unique constraint on the table will reject
    duplicates anyway, but we 409 explicitly for a friendlier message).
    Auto-fills ``source_node_id`` if the caller didn't supply one and
    the flow has a Source step.
    """
    flow = (
        db.query(FlowDefinition)
        .filter(
            FlowDefinition.id == payload.flow_definition_id,
            FlowDefinition.tenant_id == ctx.tenant_id,
        )
        .first()
    )
    if flow is None:
        raise HTTPException(status_code=404, detail="Flow not found")

    _load_trigger_or_404(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind=payload.trigger_kind,
        trigger_instance_id=payload.trigger_instance_id,
    )

    existing = (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.tenant_id == ctx.tenant_id,
            FlowTriggerBinding.flow_definition_id == payload.flow_definition_id,
            FlowTriggerBinding.trigger_kind == payload.trigger_kind,
            FlowTriggerBinding.trigger_instance_id == payload.trigger_instance_id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Binding already exists for this (flow, trigger) pair")

    source_node_id = payload.source_node_id
    if source_node_id is None:
        source_node_id = find_source_node_id(db, flow_definition_id=payload.flow_definition_id)

    binding = FlowTriggerBinding(
        tenant_id=ctx.tenant_id,
        flow_definition_id=payload.flow_definition_id,
        trigger_kind=payload.trigger_kind,
        trigger_instance_id=payload.trigger_instance_id,
        source_node_id=source_node_id,
        suppress_default_agent=payload.suppress_default_agent,
        is_active=payload.is_active,
        is_system_managed=False,  # only auto-gen creates system-managed rows
    )
    db.add(binding)
    db.commit()
    db.refresh(binding)
    logger.info(
        "Created flow_trigger_binding %s flow=%s kind=%s instance=%s suppress_default=%s",
        binding.id,
        binding.flow_definition_id,
        binding.trigger_kind,
        binding.trigger_instance_id,
        binding.suppress_default_agent,
    )
    return _to_read(db, binding)


@router.patch("/{binding_id}", response_model=FlowTriggerBindingRead, dependencies=[Depends(require_permission("flows.write"))])
def update_binding(
    binding_id: int,
    payload: FlowTriggerBindingUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Toggle ``is_active`` and/or ``suppress_default_agent``.

    System-managed bindings can be toggled (suppress_default starts False
    and the user may want to flip it once they're ready to retire the
    legacy ContinuousAgent for that trigger), but cannot be deleted.
    """
    binding = (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.id == binding_id,
            FlowTriggerBinding.tenant_id == ctx.tenant_id,
            FlowTriggerBinding.trigger_kind.in_(sorted(_VALID_KINDS)),
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Binding not found")

    if payload.is_active is not None:
        binding.is_active = payload.is_active
    if payload.suppress_default_agent is not None:
        binding.suppress_default_agent = payload.suppress_default_agent
    binding.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(binding)
    return _to_read(db, binding)


@router.delete("/{binding_id}", status_code=204, dependencies=[Depends(require_permission("flows.write"))])
def delete_binding(
    binding_id: int,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Hard-delete a binding.

    System-managed bindings (``is_system_managed=True``) are protected:
    they live and die with their trigger and are cleaned up by the
    per-kind trigger DELETE handlers via
    ``flow_binding_service.delete_bindings_for_trigger``.
    """
    binding = (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.id == binding_id,
            FlowTriggerBinding.tenant_id == ctx.tenant_id,
            FlowTriggerBinding.trigger_kind.in_(sorted(_VALID_KINDS)),
        )
        .first()
    )
    if binding is None:
        raise HTTPException(status_code=404, detail="Binding not found")
    if binding.is_system_managed:
        raise HTTPException(
            status_code=403,
            detail="System-managed bindings cannot be deleted directly. Delete the underlying trigger instead.",
        )

    db.delete(binding)
    db.commit()
    logger.info("Deleted flow_trigger_binding %s", binding_id)
    return None
