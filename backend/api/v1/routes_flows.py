"""
Flows API — Public API v1
Provides flow definition CRUD, step management, execution, and run monitoring
endpoints as thin adapters over existing internal flow logic.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import FlowDefinition, FlowNode, FlowRun, FlowNodeRun
from api.api_auth import ApiCaller, require_api_permission
from api.v1.schemas import PaginationMeta, StatusResponse, COMMON_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class FlowStepSummary(BaseModel):
    """Summary of a flow step (node)."""
    id: int = Field(description="Step ID", example=1)
    type: str = Field(description="Step type", example="message")
    position: int = Field(description="Position in the flow (1-based)", example=1)
    name: Optional[str] = Field(None, description="Human-readable step name", example="Send welcome message")
    timeout_seconds: int = Field(300, description="Step execution timeout in seconds", example=300)


class FlowSummary(BaseModel):
    """Summary of a flow definition."""
    id: int = Field(description="Flow definition ID", example=1)
    name: str = Field(description="Flow name", example="Customer Onboarding")
    description: Optional[str] = Field(None, description="Flow description", example="Onboarding workflow for new customers")
    is_active: bool = Field(description="Whether the flow is active", example=True)
    version: int = Field(description="Flow version number", example=1)
    execution_method: Optional[str] = Field("immediate", description="Execution method", example="immediate")
    flow_type: Optional[str] = Field("workflow", description="Flow type category", example="workflow")
    node_count: int = Field(0, description="Number of steps in the flow", example=3)
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)", example="2026-01-15T10:30:00")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)", example="2026-01-15T10:30:00")


class FlowDetailResponse(BaseModel):
    """Flow definition with all steps."""
    id: int = Field(description="Flow definition ID", example=1)
    name: str = Field(description="Flow name", example="Customer Onboarding")
    description: Optional[str] = Field(None, description="Flow description")
    is_active: bool = Field(description="Whether the flow is active", example=True)
    version: int = Field(description="Flow version number", example=1)
    execution_method: Optional[str] = Field("immediate", description="Execution method")
    flow_type: Optional[str] = Field("workflow", description="Flow type category")
    node_count: int = Field(0, description="Number of steps")
    steps: List[FlowStepSummary] = Field(default_factory=list, description="Flow steps ordered by position")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")
    updated_at: Optional[str] = Field(None, description="Last update timestamp (ISO 8601)")


class FlowCreateRequest(BaseModel):
    """Request body for creating a new flow definition."""
    name: str = Field(..., min_length=1, max_length=200, description="Flow name", example="Customer Onboarding")
    description: Optional[str] = Field(None, description="Flow description", example="Automated onboarding workflow")
    is_active: bool = Field(True, description="Whether the flow should be active on creation", example=True)
    execution_method: Optional[str] = Field("immediate", description="Execution method: immediate, scheduled, recurring", example="immediate")
    flow_type: Optional[str] = Field("workflow", description="Flow type: notification, conversation, workflow, task", example="workflow")


class FlowUpdateRequest(BaseModel):
    """Request body for updating a flow definition."""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="Flow name")
    description: Optional[str] = Field(None, description="Flow description")
    is_active: Optional[bool] = Field(None, description="Active status")
    execution_method: Optional[str] = Field(None, description="Execution method")
    flow_type: Optional[str] = Field(None, description="Flow type")


class StepCreateRequest(BaseModel):
    """Request body for adding a step to a flow."""
    type: str = Field(..., description="Step type: notification, message, tool, conversation, Trigger, Message, Tool, Conversation", example="message")
    position: int = Field(..., ge=1, description="Position in the flow (1-based)", example=1)
    config_json: Dict[str, Any] = Field(..., description="Step configuration (schema depends on step type)", example={"recipient": "+5511999999999", "message": "Hello!"})
    name: Optional[str] = Field(None, description="Human-readable step name", example="Send greeting")
    description: Optional[str] = Field(None, description="Step description")
    next_node_id: Optional[int] = Field(None, description="Next node ID (legacy)")
    timeout_seconds: int = Field(300, description="Step timeout in seconds", example=300)
    retry_on_failure: bool = Field(False, description="Whether to retry on failure")
    max_retries: int = Field(0, description="Maximum retry count")
    allow_multi_turn: bool = Field(False, description="Enable multi-turn conversation")
    max_turns: int = Field(20, description="Maximum conversation turns")
    conversation_objective: Optional[str] = Field(None, description="Objective for conversation steps")
    agent_id: Optional[int] = Field(None, description="Agent ID override for this step")
    persona_id: Optional[int] = Field(None, description="Persona ID for this step")
    on_failure: Optional[str] = Field(None, description="Failure behavior: continue, skip, end (default: end)")
    on_success: Optional[str] = Field(None, description="Success behavior: continue, skip_to:{step}, end (default: continue)")


class StepUpdateRequest(BaseModel):
    """Request body for updating a step."""
    type: Optional[str] = Field(None, description="Step type")
    position: Optional[int] = Field(None, ge=1, description="Position in the flow")
    config_json: Optional[Dict[str, Any]] = Field(None, description="Step configuration")
    name: Optional[str] = Field(None, description="Human-readable step name")
    description: Optional[str] = Field(None, description="Step description")
    next_node_id: Optional[int] = Field(None, description="Next node ID (legacy)")
    timeout_seconds: Optional[int] = Field(None, description="Step timeout in seconds")
    retry_on_failure: Optional[bool] = Field(None, description="Whether to retry on failure")
    max_retries: Optional[int] = Field(None, description="Maximum retry count")
    allow_multi_turn: Optional[bool] = Field(None, description="Enable multi-turn conversation")
    max_turns: Optional[int] = Field(None, description="Maximum conversation turns")
    conversation_objective: Optional[str] = Field(None, description="Objective for conversation steps")
    agent_id: Optional[int] = Field(None, description="Agent ID override")
    persona_id: Optional[int] = Field(None, description="Persona ID for this step")
    on_failure: Optional[str] = Field(None, description="Failure behavior: continue, skip, end")
    on_success: Optional[str] = Field(None, description="Success behavior: continue, skip_to:{step}, end")


class StepResponse(BaseModel):
    """Full step/node response."""
    id: int = Field(description="Step ID")
    flow_definition_id: int = Field(description="Parent flow ID")
    type: str = Field(description="Step type")
    position: int = Field(description="Position in the flow")
    config_json: Dict[str, Any] = Field(description="Step configuration")
    next_node_id: Optional[int] = Field(None, description="Next node ID (legacy)")
    name: Optional[str] = Field(None, description="Human-readable step name")
    step_description: Optional[str] = Field(None, description="Step description")
    timeout_seconds: int = Field(300, description="Step timeout in seconds")
    retry_on_failure: bool = Field(False, description="Retry on failure flag")
    max_retries: int = Field(0, description="Maximum retries")
    allow_multi_turn: bool = Field(False, description="Multi-turn conversation flag")
    max_turns: int = Field(20, description="Maximum conversation turns")
    conversation_objective: Optional[str] = Field(None, description="Conversation objective")
    agent_id: Optional[int] = Field(None, description="Agent ID override")
    persona_id: Optional[int] = Field(None, description="Persona ID")
    on_failure: Optional[str] = Field(None, description="Failure behavior")
    on_success: Optional[str] = Field(None, description="Success behavior")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class FlowExecuteRequest(BaseModel):
    """Request body for executing a flow."""
    trigger_context_json: Optional[Dict[str, Any]] = Field(None, description="Trigger context / input variables", example={"customer_name": "John"})


class FlowExecuteResponse(BaseModel):
    """Response for flow execution (HTTP 202 Accepted)."""
    run_id: int = Field(description="Flow run ID for status polling", example=42)
    flow_definition_id: int = Field(description="Flow definition ID", example=1)
    status: str = Field(description="Initial run status", example="pending")
    message: str = Field(description="Status message", example="Flow execution started")


class FlowRunSummary(BaseModel):
    """Summary of a flow run."""
    id: int = Field(description="Flow run ID")
    flow_definition_id: int = Field(description="Flow definition ID")
    status: str = Field(description="Run status: pending, running, completed, failed, cancelled")
    started_at: Optional[str] = Field(None, description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    initiator: Optional[str] = Field(None, description="Who initiated the run")
    total_steps: int = Field(0, description="Total steps in the run")
    completed_steps: int = Field(0, description="Completed steps count")
    failed_steps: int = Field(0, description="Failed steps count")
    error_text: Optional[str] = Field(None, description="Error message if failed")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class StepRunSummary(BaseModel):
    """Summary of a step run within a flow run."""
    id: int = Field(description="Step run ID")
    flow_run_id: int = Field(description="Parent flow run ID")
    flow_node_id: int = Field(description="Flow node/step ID")
    status: str = Field(description="Step run status")
    started_at: Optional[str] = Field(None, description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    execution_time_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    error_text: Optional[str] = Field(None, description="Error message if failed")
    retry_count: int = Field(0, description="Number of retries")
    tool_used: Optional[str] = Field(None, description="Tool used in this step")


class FlowRunDetailResponse(BaseModel):
    """Flow run with step runs."""
    id: int = Field(description="Flow run ID")
    flow_definition_id: int = Field(description="Flow definition ID")
    status: str = Field(description="Run status")
    started_at: Optional[str] = Field(None, description="Start timestamp")
    completed_at: Optional[str] = Field(None, description="Completion timestamp")
    initiator: Optional[str] = Field(None, description="Who initiated the run")
    total_steps: int = Field(0, description="Total steps")
    completed_steps: int = Field(0, description="Completed steps")
    failed_steps: int = Field(0, description="Failed steps")
    error_text: Optional[str] = Field(None, description="Error message")
    trigger_context_json: Optional[str] = Field(None, description="Trigger context data")
    final_report_json: Optional[str] = Field(None, description="Final report data")
    step_runs: List[StepRunSummary] = Field(default_factory=list, description="Individual step run results")
    created_at: Optional[str] = Field(None, description="Creation timestamp")


class PaginatedFlowsResponse(BaseModel):
    """Paginated list of flow definitions."""
    data: List[FlowSummary] = Field(description="Flow definitions")
    meta: dict = Field(description="Pagination metadata")


# ============================================================================
# Helpers
# ============================================================================

def _count_flow_nodes(db: Session, flow_id: int) -> int:
    """Count nodes/steps in a flow."""
    return db.query(FlowNode).filter(FlowNode.flow_definition_id == flow_id).count()


def _flow_to_summary(flow: FlowDefinition, db: Session) -> dict:
    """Convert FlowDefinition to a summary dict."""
    return {
        "id": flow.id,
        "name": flow.name,
        "description": flow.description,
        "is_active": flow.is_active,
        "version": flow.version,
        "execution_method": flow.execution_method or "immediate",
        "flow_type": flow.flow_type or "workflow",
        "node_count": _count_flow_nodes(db, flow.id),
        "created_at": flow.created_at.isoformat() if flow.created_at else None,
        "updated_at": (flow.updated_at or flow.created_at).isoformat() if (flow.updated_at or flow.created_at) else None,
    }


def _node_to_response(node: FlowNode) -> dict:
    """Convert FlowNode to response dict."""
    config = json.loads(node.config_json) if isinstance(node.config_json, str) else (node.config_json or {})
    return {
        "id": node.id,
        "flow_definition_id": node.flow_definition_id,
        "type": node.type,
        "position": node.position,
        "config_json": config,
        "next_node_id": node.next_node_id,
        "name": node.name,
        "step_description": node.step_description,
        "timeout_seconds": node.timeout_seconds or 300,
        "retry_on_failure": node.retry_on_failure or False,
        "max_retries": node.max_retries or 0,
        "allow_multi_turn": node.allow_multi_turn or False,
        "max_turns": node.max_turns or 20,
        "conversation_objective": node.conversation_objective,
        "agent_id": node.agent_id,
        "persona_id": node.persona_id,
        "on_failure": node.on_failure,
        "on_success": node.on_success,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": (node.updated_at or node.created_at).isoformat() if (node.updated_at or node.created_at) else None,
    }


def _run_to_summary(run: FlowRun) -> dict:
    """Convert FlowRun to a summary dict."""
    return {
        "id": run.id,
        "flow_definition_id": run.flow_definition_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "initiator": run.initiator,
        "total_steps": run.total_steps or 0,
        "completed_steps": run.completed_steps or 0,
        "failed_steps": run.failed_steps or 0,
        "error_text": run.error_text,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _step_run_to_summary(step_run: FlowNodeRun) -> dict:
    """Convert FlowNodeRun to a summary dict."""
    return {
        "id": step_run.id,
        "flow_run_id": step_run.flow_run_id,
        "flow_node_id": step_run.flow_node_id,
        "status": step_run.status,
        "started_at": step_run.started_at.isoformat() if step_run.started_at else None,
        "completed_at": step_run.completed_at.isoformat() if step_run.completed_at else None,
        "execution_time_ms": step_run.execution_time_ms,
        "error_text": step_run.error_text,
        "retry_count": step_run.retry_count or 0,
        "tool_used": step_run.tool_used,
    }


# ============================================================================
# Flow Definition Endpoints
# ============================================================================

@router.get("/api/v1/flows", responses=COMMON_RESPONSES)
async def list_flows(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    flow_type: Optional[str] = Query(None, description="Filter by flow type: notification, conversation, workflow, task"),
    execution_method: Optional[str] = Query(None, description="Filter by execution method: immediate, scheduled, recurring"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.read")),
):
    """List flow definitions with pagination and filtering.

    Returns a paginated list of flow definitions belonging to the caller's tenant.
    Supports filtering by active status, flow type, and execution method.
    Requires **flows.read** permission.
    """
    query = db.query(FlowDefinition).filter(FlowDefinition.tenant_id == caller.tenant_id)

    if is_active is not None:
        query = query.filter(FlowDefinition.is_active == is_active)
    if flow_type is not None:
        query = query.filter(FlowDefinition.flow_type == flow_type)
    if execution_method is not None:
        query = query.filter(FlowDefinition.execution_method == execution_method)

    total = query.count()
    flows = query.order_by(FlowDefinition.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "data": [_flow_to_summary(f, db) for f in flows],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.post("/api/v1/flows", status_code=201, response_model=FlowSummary, responses={**COMMON_RESPONSES, **VALIDATION_RESPONSE})
async def create_flow(
    request: FlowCreateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Create a new flow definition.

    Creates a flow in the caller's tenant with the given name and configuration.
    The flow defaults to active status; steps must be added separately via POST /flows/{id}/steps.
    Requires **flows.write** permission.
    """
    db_flow = FlowDefinition(
        name=request.name,
        description=request.description,
        is_active=request.is_active,
        tenant_id=caller.tenant_id,
        execution_method=request.execution_method or "immediate",
        flow_type=request.flow_type or "workflow",
    )
    db.add(db_flow)
    db.commit()
    db.refresh(db_flow)

    logger.info(f"API v1 created flow '{request.name}' (id={db_flow.id}) for tenant={caller.tenant_id}")
    return _flow_to_summary(db_flow, db)


@router.get("/api/v1/flows/runs", responses=COMMON_RESPONSES)
async def list_runs(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    status: Optional[str] = Query(None, description="Filter by run status: pending, running, completed, failed, cancelled"),
    flow_id: Optional[int] = Query(None, description="Filter by flow definition ID"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.read")),
):
    """List flow runs with pagination and optional filtering.

    Returns flow execution runs for the caller's tenant, ordered by most recent first.
    Filterable by run status and flow definition ID.
    Requires **flows.read** permission.
    """
    query = db.query(FlowRun).filter(FlowRun.tenant_id == caller.tenant_id)

    if status is not None:
        query = query.filter(FlowRun.status == status)
    if flow_id is not None:
        query = query.filter(FlowRun.flow_definition_id == flow_id)

    total = query.count()
    runs = query.order_by(FlowRun.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "data": [_run_to_summary(r) for r in runs],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


@router.get("/api/v1/flows/runs/{run_id}", response_model=FlowRunDetailResponse, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.read")),
):
    """Get detailed information about a specific flow run.

    Returns the flow run with all associated step-level results for monitoring
    execution progress. Returns 404 if the run does not exist or belongs to another tenant.
    Requires **flows.read** permission.
    """
    run = db.query(FlowRun).filter(
        FlowRun.id == run_id,
        FlowRun.tenant_id == caller.tenant_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Flow run not found")

    step_runs = db.query(FlowNodeRun).filter(
        FlowNodeRun.flow_run_id == run_id,
    ).order_by(FlowNodeRun.id).all()

    return {
        "id": run.id,
        "flow_definition_id": run.flow_definition_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "initiator": run.initiator,
        "total_steps": run.total_steps or 0,
        "completed_steps": run.completed_steps or 0,
        "failed_steps": run.failed_steps or 0,
        "error_text": run.error_text,
        "trigger_context_json": run.trigger_context_json,
        "final_report_json": run.final_report_json,
        "step_runs": [_step_run_to_summary(sr) for sr in step_runs],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.post("/api/v1/flows/runs/{run_id}/cancel", responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def cancel_run(
    run_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.execute")),
):
    """Cancel a running or pending flow execution.

    Sets the run status to 'cancelled' and marks all incomplete step runs as cancelled.
    Only runs in 'pending' or 'running' status can be cancelled; returns 400 otherwise.
    Requires **flows.execute** permission.
    """
    run = db.query(FlowRun).filter(
        FlowRun.id == run_id,
        FlowRun.tenant_id == caller.tenant_id,
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Flow run not found")

    if run.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel run with status '{run.status}'")

    run.status = "cancelled"
    run.completed_at = datetime.utcnow()

    # Cancel pending/running step runs
    db.query(FlowNodeRun).filter(
        FlowNodeRun.flow_run_id == run_id,
        FlowNodeRun.status.in_(["pending", "running"]),
    ).update({"status": "cancelled", "completed_at": datetime.utcnow()}, synchronize_session=False)

    db.commit()

    logger.info(f"API v1 cancelled flow run {run_id} for tenant={caller.tenant_id}")
    return {"run_id": run_id, "status": "cancelled", "message": "Flow run cancelled successfully"}


@router.get("/api/v1/flows/{flow_id}", response_model=FlowDetailResponse, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def get_flow(
    flow_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.read")),
):
    """Get a flow definition with all its steps.

    Returns the full flow configuration including all steps ordered by position.
    Returns 404 if the flow does not exist or belongs to another tenant.
    Requires **flows.read** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    steps = db.query(FlowNode).filter(
        FlowNode.flow_definition_id == flow_id,
    ).order_by(FlowNode.position).all()

    result = _flow_to_summary(flow, db)
    result["steps"] = [
        {
            "id": s.id,
            "type": s.type,
            "position": s.position,
            "name": s.name,
            "timeout_seconds": s.timeout_seconds or 300,
        }
        for s in steps
    ]
    return result


@router.put("/api/v1/flows/{flow_id}", response_model=FlowSummary, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE})
async def update_flow(
    flow_id: int,
    request: FlowUpdateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Update a flow definition's metadata.

    Supports partial updates -- only provided fields are modified.
    Use this to rename, change description, toggle active status, or change execution method.
    Requires **flows.write** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    if request.name is not None:
        flow.name = request.name
    if request.description is not None:
        flow.description = request.description
    if request.is_active is not None:
        flow.is_active = request.is_active
    if request.execution_method is not None:
        flow.execution_method = request.execution_method
    if request.flow_type is not None:
        flow.flow_type = request.flow_type

    flow.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(flow)

    logger.info(f"API v1 updated flow {flow_id} for tenant={caller.tenant_id}")
    return _flow_to_summary(flow, db)


@router.delete("/api/v1/flows/{flow_id}", status_code=204, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def delete_flow(
    flow_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Soft-delete a flow definition.

    Sets is_active to False rather than permanently removing the record.
    This preserves flow history and run data. Returns 204 No Content on success.
    Requires **flows.write** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    flow.is_active = False
    flow.updated_at = datetime.utcnow()
    db.commit()

    logger.info(f"API v1 soft-deleted flow {flow_id} for tenant={caller.tenant_id}")


# ============================================================================
# Step Endpoints
# ============================================================================

@router.get("/api/v1/flows/{flow_id}/steps", responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def list_steps(
    flow_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.read")),
):
    """List all steps for a flow, ordered by position.

    Returns the complete step configuration for each step in the flow.
    Returns 404 if the parent flow does not exist or belongs to another tenant.
    Requires **flows.read** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    steps = db.query(FlowNode).filter(
        FlowNode.flow_definition_id == flow_id,
    ).order_by(FlowNode.position).all()

    return {"data": [_node_to_response(s) for s in steps]}


@router.post("/api/v1/flows/{flow_id}/steps", status_code=201, response_model=StepResponse, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE})
async def create_step(
    flow_id: int,
    request: StepCreateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Add a step to a flow at the specified position.

    The position must be unique within the flow; returns 400 if already occupied.
    Step type determines execution behavior (message, tool, conversation, etc.).
    Requires **flows.write** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    # Check position conflict
    existing = db.query(FlowNode).filter(
        FlowNode.flow_definition_id == flow_id,
        FlowNode.position == request.position,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Position {request.position} is already occupied")

    # Validate agent_id belongs to caller's tenant
    if request.agent_id is not None:
        from models import Agent
        ref_agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == caller.tenant_id,
        ).first()
        if not ref_agent:
            raise HTTPException(status_code=400, detail="Agent not found")

    # Validate persona_id belongs to caller's tenant
    if request.persona_id is not None:
        from models import Persona
        ref_persona = db.query(Persona).filter(
            Persona.id == request.persona_id,
            Persona.tenant_id == caller.tenant_id,
        ).first()
        if not ref_persona:
            raise HTTPException(status_code=400, detail="Persona not found")

    db_step = FlowNode(
        flow_definition_id=flow_id,
        type=request.type,
        position=request.position,
        config_json=json.dumps(request.config_json),
        next_node_id=request.next_node_id,
        name=request.name,
        step_description=request.description,
        timeout_seconds=request.timeout_seconds,
        retry_on_failure=request.retry_on_failure,
        max_retries=request.max_retries,
        allow_multi_turn=request.allow_multi_turn,
        max_turns=request.max_turns,
        conversation_objective=request.conversation_objective,
        agent_id=request.agent_id,
        persona_id=request.persona_id,
        on_failure=request.on_failure,
        on_success=request.on_success,
    )
    db.add(db_step)
    db.commit()
    db.refresh(db_step)

    logger.info(f"API v1 created step {db_step.id} for flow {flow_id}")
    return _node_to_response(db_step)


@router.put("/api/v1/flows/{flow_id}/steps/{step_id}", response_model=StepResponse, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE})
async def update_step(
    flow_id: int,
    step_id: int,
    request: StepUpdateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Update a step's configuration.

    Supports partial updates -- only provided fields are modified.
    The step must belong to the specified flow; returns 404 if either is missing.
    Requires **flows.write** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    step = db.query(FlowNode).filter(
        FlowNode.id == step_id,
        FlowNode.flow_definition_id == flow_id,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    if request.type is not None:
        step.type = request.type
    if request.position is not None:
        step.position = request.position
    if request.config_json is not None:
        step.config_json = json.dumps(request.config_json)
    if request.next_node_id is not None:
        step.next_node_id = request.next_node_id
    if request.name is not None:
        step.name = request.name
    if request.description is not None:
        step.step_description = request.description
    if request.timeout_seconds is not None:
        step.timeout_seconds = request.timeout_seconds
    if request.retry_on_failure is not None:
        step.retry_on_failure = request.retry_on_failure
    if request.max_retries is not None:
        step.max_retries = request.max_retries
    if request.allow_multi_turn is not None:
        step.allow_multi_turn = request.allow_multi_turn
    if request.max_turns is not None:
        step.max_turns = request.max_turns
    if request.conversation_objective is not None:
        step.conversation_objective = request.conversation_objective
    if request.agent_id is not None:
        from models import Agent
        ref_agent = db.query(Agent).filter(
            Agent.id == request.agent_id,
            Agent.tenant_id == caller.tenant_id,
        ).first()
        if not ref_agent:
            raise HTTPException(status_code=400, detail="Agent not found")
        step.agent_id = request.agent_id
    if request.persona_id is not None:
        from models import Persona
        ref_persona = db.query(Persona).filter(
            Persona.id == request.persona_id,
            Persona.tenant_id == caller.tenant_id,
        ).first()
        if not ref_persona:
            raise HTTPException(status_code=400, detail="Persona not found")
        step.persona_id = request.persona_id
    if request.on_failure is not None:
        step.on_failure = request.on_failure
    if request.on_success is not None:
        step.on_success = request.on_success

    step.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(step)

    logger.info(f"API v1 updated step {step_id} in flow {flow_id}")
    return _node_to_response(step)


@router.delete("/api/v1/flows/{flow_id}/steps/{step_id}", status_code=204, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def delete_step(
    flow_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.write")),
):
    """Delete a step from a flow.

    Permanently removes the step (hard delete). Returns 204 No Content on success.
    Returns 404 if the flow or step does not exist.
    Requires **flows.write** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    step = db.query(FlowNode).filter(
        FlowNode.id == step_id,
        FlowNode.flow_definition_id == flow_id,
    ).first()
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")

    db.delete(step)
    db.commit()

    logger.info(f"API v1 deleted step {step_id} from flow {flow_id}")


# ============================================================================
# Execution Endpoints
# ============================================================================

@router.post("/api/v1/flows/{flow_id}/execute", status_code=202, response_model=FlowExecuteResponse, responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def execute_flow(
    flow_id: int,
    request: Optional[FlowExecuteRequest] = None,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("flows.execute")),
):
    """Execute a flow asynchronously.

    Validates the flow is active and has at least one step, then starts execution.
    Returns 202 Accepted with a run_id for polling progress via GET /flows/runs/{run_id}.
    Requires **flows.execute** permission.
    """
    flow = db.query(FlowDefinition).filter(
        FlowDefinition.id == flow_id,
        FlowDefinition.tenant_id == caller.tenant_id,
    ).first()
    if not flow:
        raise HTTPException(status_code=404, detail="Flow not found")

    if not flow.is_active:
        raise HTTPException(status_code=400, detail="Flow is not active")

    # Validate structure
    steps = db.query(FlowNode).filter(FlowNode.flow_definition_id == flow_id).all()
    if not steps:
        raise HTTPException(status_code=400, detail="Flow must have at least one step")

    try:
        from flows.flow_engine import FlowEngine

        engine = FlowEngine(db)
        trigger_context = request.trigger_context_json if request else None

        flow_run = await engine.run_flow(
            flow_definition_id=flow_id,
            trigger_context=trigger_context,
            initiator="api_v1",
            trigger_type="immediate",
        )

        logger.info(f"API v1 executed flow {flow_id}, run_id={flow_run.id}, status={flow_run.status}")

        return {
            "run_id": flow_run.id,
            "flow_definition_id": flow_id,
            "status": flow_run.status,
            "message": "Flow execution started",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API v1 flow execution failed for flow {flow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Flow execution failed. Check server logs for details.")
