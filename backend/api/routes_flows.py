"""
Phase 6.6: Multi-Step Flows API Routes
Phase 8.0: Unified Flow Architecture - Merged with scheduler functionality
Handles CRUD operations for flow definitions, steps, runs, conversation threads, and execution.
Phase 7.9: Added RBAC protection and tenant isolation
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
import logging
import json
import asyncio

from models import FlowDefinition, FlowNode, FlowRun, FlowNodeRun, ConversationThread, Agent
from auth_dependencies import (
    require_permission,
    get_current_user_required,
    get_tenant_context,
    TenantContext
)
from models_rbac import User
from schemas import (
    FlowCreate, FlowUpdate, FlowResponse, FlowDetailResponse,
    FlowStepCreate, FlowStepUpdate, FlowStepResponse,
    FlowRunCreate, FlowRunResponse, FlowStepRunResponse,
    ConversationThreadResponse, ConversationReplyRequest, ConversationReplyResponse,
    ExecutionMethod, FlowType, StepType
)
from flows.template_parser import TemplateParser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flows", tags=["flows"])

# Global engine reference (set by main app.py)
_engine = None

def set_engine(engine):
    global _engine
    _engine = engine

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============= LEGACY PYDANTIC SCHEMAS (backward compat) =============

class FlowDefinitionCreate(BaseModel):
    """Legacy schema - use FlowCreate for new code"""
    name: str
    description: Optional[str] = None
    is_active: bool = True


class FlowDefinitionUpdate(BaseModel):
    """Legacy schema - use FlowUpdate for new code"""
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class FlowDefinitionResponse(BaseModel):
    """Legacy schema - use FlowResponse for new code"""
    id: int
    name: str
    description: Optional[str]
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime
    node_count: int = 0
    # Phase 8.0 fields (optional for backward compat)
    execution_method: Optional[str] = "immediate"
    scheduled_at: Optional[datetime] = None
    flow_type: Optional[str] = "workflow"

    class Config:
        from_attributes = True


class FlowNodeCreate(BaseModel):
    """Legacy schema - works for both old and new step types"""
    type: str  # 'Trigger', 'Message', 'Tool', 'Conversation', 'Subflow' OR 'notification', 'message', 'tool', 'conversation'
    position: int
    config_json: Dict[str, Any]
    next_node_id: Optional[int] = None
    # Phase 8.0 fields
    name: Optional[str] = None
    description: Optional[str] = None
    timeout_seconds: int = 300
    retry_on_failure: bool = False
    max_retries: int = 0
    allow_multi_turn: bool = False
    max_turns: int = 20
    conversation_objective: Optional[str] = None
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None


class FlowNodeUpdate(BaseModel):
    type: Optional[str] = None
    position: Optional[int] = None
    config_json: Optional[Dict[str, Any]] = None
    next_node_id: Optional[int] = None
    name: Optional[str] = None
    description: Optional[str] = None
    timeout_seconds: Optional[int] = None
    retry_on_failure: Optional[bool] = None
    max_retries: Optional[int] = None
    allow_multi_turn: Optional[bool] = None
    max_turns: Optional[int] = None
    conversation_objective: Optional[str] = None
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None


class FlowNodeResponse(BaseModel):
    id: int
    flow_definition_id: int
    type: str
    position: int
    config_json: Dict[str, Any]
    next_node_id: Optional[int]
    name: Optional[str] = None
    step_description: Optional[str] = None
    timeout_seconds: int = 300
    retry_on_failure: bool = False
    max_retries: int = 0
    allow_multi_turn: bool = False
    max_turns: int = 20
    conversation_objective: Optional[str] = None
    agent_id: Optional[int] = None
    persona_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LegacyFlowRunCreate(BaseModel):
    """Legacy schema for running flows"""
    trigger_context_json: Optional[Dict[str, Any]] = None


class LegacyFlowRunResponse(BaseModel):
    id: int
    flow_definition_id: int
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    initiator: Optional[str]
    trigger_context_json: Optional[str]
    final_report_json: Optional[str]
    error_text: Optional[str]
    created_at: datetime
    # Phase 8.0 fields
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0

    class Config:
        from_attributes = True


class FlowNodeRunResponse(BaseModel):
    id: int
    flow_run_id: int
    flow_node_id: int
    status: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    input_json: Optional[str]
    output_json: Optional[str]
    error_text: Optional[str]
    execution_time_ms: Optional[int]
    token_usage_json: Optional[str]
    tool_used: Optional[str]
    idempotency_key: Optional[str]
    retry_count: int = 0

    class Config:
        from_attributes = True


# ============= HELPER FUNCTIONS =============

def validate_flow_structure(db: Session, flow_id: int, strict: bool = False) -> tuple[bool, Optional[str]]:
    """
    Validates flow structure.

    Args:
        db: Database session
        flow_id: Flow ID to validate
        strict: If True, enforce legacy Trigger requirement
    """
    nodes = db.query(FlowNode).filter(FlowNode.flow_definition_id == flow_id).order_by(FlowNode.position).all()

    if not nodes:
        return False, "Flow must have at least one step"

    if strict:
        # Legacy mode: require Trigger at position 1
        if nodes[0].type != 'Trigger' or nodes[0].position != 1:
            return False, "First node must be a Trigger at position 1"

        trigger_count = sum(1 for n in nodes if n.type == 'Trigger')
        if trigger_count > 1:
            return False, "Flow can only have one Trigger node"

    # Check positions are unique and valid
    positions = [n.position for n in nodes]
    if len(positions) != len(set(positions)):
        return False, "Duplicate step positions found"

    if min(positions) < 1:
        return False, "Step positions must be >= 1"

    return True, None


def count_flow_nodes(db: Session, flow_id: int) -> int:
    """Count nodes/steps in a flow."""
    return db.query(FlowNode).filter(FlowNode.flow_definition_id == flow_id).count()


def flow_to_response(flow: FlowDefinition, db: Session) -> FlowDefinitionResponse:
    """Convert FlowDefinition to response model."""
    return FlowDefinitionResponse(
        id=flow.id,
        name=flow.name,
        description=flow.description,
        is_active=flow.is_active,
        version=flow.version,
        created_at=flow.created_at,
        updated_at=flow.updated_at or flow.created_at,
        node_count=count_flow_nodes(db, flow.id),
        execution_method=flow.execution_method or "immediate",
        scheduled_at=flow.scheduled_at,
        flow_type=flow.flow_type or "workflow"
    )


def node_to_response(node: FlowNode) -> FlowNodeResponse:
    """Convert FlowNode to response model."""
    config = json.loads(node.config_json) if isinstance(node.config_json, str) else node.config_json
    return FlowNodeResponse(
        id=node.id,
        flow_definition_id=node.flow_definition_id,
        type=node.type,
        position=node.position,
        config_json=config,
        next_node_id=node.next_node_id,
        name=node.name,
        step_description=node.step_description,
        timeout_seconds=node.timeout_seconds or 300,
        retry_on_failure=node.retry_on_failure or False,
        max_retries=node.max_retries or 0,
        allow_multi_turn=node.allow_multi_turn or False,
        max_turns=node.max_turns or 20,
        conversation_objective=node.conversation_objective,
        agent_id=node.agent_id,
        persona_id=node.persona_id,
        created_at=node.created_at,
        updated_at=node.updated_at or node.created_at
    )


# ============= TEMPLATE VALIDATION (Phase 13.1) =============

class TemplateValidationRequest(BaseModel):
    """Request for template validation"""
    template: str
    context: Optional[Dict[str, Any]] = None  # Sample context for testing


class TemplateValidationResponse(BaseModel):
    """Response for template validation"""
    valid: bool
    errors: List[str]
    variables: List[str]
    rendered: Optional[str] = None  # Only if context provided


@router.post("/template/validate", response_model=TemplateValidationResponse)
def validate_template(
    request: TemplateValidationRequest,
    db: Session = Depends(get_db)
):
    """
    Validate a template string for syntax errors and extract variables.

    Phase 13.1: Step Output Injection

    Optionally renders the template with provided sample context.

    Example request:
    {
        "template": "Scan complete!\\nStatus: {{#if step_1.success}}OK{{else}}FAIL{{/if}}\\nOutput: {{truncate step_1.raw_output 100}}",
        "context": {
            "step_1": {"success": true, "raw_output": "Port 22: Open\\nPort 80: Open"}
        }
    }
    """
    try:
        parser = TemplateParser()

        # Validate syntax
        errors = parser.validate_template(request.template)

        # Extract variables
        variables = parser.extract_variables(request.template)

        # Render if context provided
        rendered = None
        if request.context and not errors:
            try:
                rendered = parser.render(request.template, request.context)
            except Exception as e:
                errors.append(f"Render error: {str(e)}")

        return TemplateValidationResponse(
            valid=len(errors) == 0,
            errors=errors,
            variables=variables,
            rendered=rendered
        )

    except Exception as e:
        logger.error(f"Template validation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/template/render")
def render_template(
    request: TemplateValidationRequest,
    db: Session = Depends(get_db)
):
    """
    Render a template with the provided context.

    Phase 13.1: Step Output Injection

    Useful for testing template output before creating a flow.
    """
    try:
        if not request.context:
            raise HTTPException(
                status_code=400,
                detail="Context is required for rendering"
            )

        parser = TemplateParser()

        # Validate first
        errors = parser.validate_template(request.template)
        if errors:
            raise HTTPException(
                status_code=400,
                detail={"message": "Template validation failed", "errors": errors}
            )

        # Render
        rendered = parser.render(request.template, request.context)

        return {
            "rendered": rendered,
            "variables_used": parser.extract_variables(request.template)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Template render error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= STATS ENDPOINT (must be before /{flow_id} routes) =============

@router.get("/stats")
def get_flow_stats(
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get flow statistics."""
    try:
        flow_query = db.query(FlowDefinition)
        flow_query = tenant_context.filter_by_tenant(flow_query, FlowDefinition.tenant_id)

        total_flows = flow_query.count()
        active_flows = flow_query.filter(FlowDefinition.is_active == True).count()

        run_query = db.query(FlowRun)
        if tenant_context.tenant_id:
            run_query = run_query.filter(FlowRun.tenant_id == tenant_context.tenant_id)

        total_runs = run_query.count()
        completed_runs = run_query.filter(FlowRun.status == 'completed').count()
        failed_runs = run_query.filter(FlowRun.status == 'failed').count()
        running_runs = run_query.filter(FlowRun.status == 'running').count()

        active_threads = db.query(ConversationThread).filter(
            ConversationThread.status == 'active'
        ).count()

        return {
            "flows": {
                "total": total_flows,
                "active": active_flows,
                "inactive": total_flows - active_flows
            },
            "runs": {
                "total": total_runs,
                "completed": completed_runs,
                "failed": failed_runs,
                "running": running_runs
            },
            "conversations": {
                "active_threads": active_threads
            }
        }

    except Exception as e:
        logger.error(f"Error getting flow stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= CONVERSATION THREAD ENDPOINTS (must be before /{flow_id} routes) =============

@router.get("/conversations/active", response_model=List[ConversationThreadResponse])
def list_active_conversations(
    recipient: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """List all active conversation threads with flow info."""
    try:
        # Only return flow-type threads (with flow_step_run_id) to match schema requirements
        query = db.query(ConversationThread).filter(
            ConversationThread.status == 'active',
            ConversationThread.flow_step_run_id.isnot(None)
        )

        # Apply tenant isolation (handles global admins and NULL tenant_id)
        query = tenant_context.filter_by_tenant(query, ConversationThread.tenant_id)

        if recipient:
            query = query.filter(ConversationThread.recipient == recipient)

        threads = query.order_by(ConversationThread.last_activity_at.desc()).all()

        # Enrich threads with flow info
        result = []
        for thread in threads:
            thread_dict = {
                "id": thread.id,
                "flow_step_run_id": thread.flow_step_run_id,
                "flow_definition_id": None,
                "flow_name": None,
                "status": thread.status,
                "current_turn": thread.current_turn,
                "max_turns": thread.max_turns,
                "recipient": thread.recipient,
                "agent_id": thread.agent_id,
                "persona_id": thread.persona_id,
                "objective": thread.objective,
                "conversation_history": thread.conversation_history or [],
                "context_data": thread.context_data or {},
                "goal_achieved": thread.goal_achieved,
                "goal_summary": thread.goal_summary,
                "started_at": thread.started_at,
                "last_activity_at": thread.last_activity_at,
                "completed_at": thread.completed_at,
                "timeout_at": thread.timeout_at
            }

            # Get flow info through step_run -> run (FlowRun) -> flow (FlowDefinition)
            if thread.step_run and thread.step_run.run and thread.step_run.run.flow:
                thread_dict["flow_definition_id"] = thread.step_run.run.flow.id
                thread_dict["flow_name"] = thread.step_run.run.flow.name

            result.append(thread_dict)

        return result

    except Exception as e:
        logger.error(f"Error listing active conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{thread_id}", response_model=ConversationThreadResponse)
def get_conversation_thread(
    thread_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get a specific conversation thread."""
    try:
        query = db.query(ConversationThread).filter(ConversationThread.id == thread_id)
        # Apply tenant isolation (handles global admins and NULL tenant_id)
        query = tenant_context.filter_by_tenant(query, ConversationThread.tenant_id)
        thread = query.first()
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation thread not found")

        return thread

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting conversation thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{thread_id}/reply", response_model=ConversationReplyResponse,
    dependencies=[Depends(require_permission("flows.execute"))])
async def process_conversation_reply(
    thread_id: int,
    reply: ConversationReplyRequest,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Process a reply to an active conversation thread.
    This endpoint is called by the AgentRouter when a message matches an active thread.
    """
    try:
        query = db.query(ConversationThread).filter(ConversationThread.id == thread_id)
        # Apply tenant isolation (handles global admins and NULL tenant_id)
        query = tenant_context.filter_by_tenant(query, ConversationThread.tenant_id)
        thread = query.first()
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation thread not found")

        if thread.status != 'active':
            return ConversationReplyResponse(
                should_reply=False,
                reply_content=None,
                status="error",
                thread_status=thread.status,
                current_turn=thread.current_turn,
                goal_achieved=thread.goal_achieved
            )

        # Add user message to history
        history = thread.conversation_history or []
        history.append({
            "role": "user",
            "content": reply.message_content,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        thread.conversation_history = history
        thread.current_turn += 1
        thread.last_activity_at = datetime.utcnow()

        # Check turn limit
        if thread.current_turn >= thread.max_turns:
            thread.status = 'completed'
            thread.completed_at = datetime.utcnow()
            thread.goal_summary = f"Max turns ({thread.max_turns}) reached"
            db.commit()

            return ConversationReplyResponse(
                should_reply=False,
                reply_content=None,
                status="max_turns_reached",
                thread_status="completed",
                current_turn=thread.current_turn,
                goal_achieved=False
            )

        # Generate AI response (simplified - in production would use agent system)
        from agent.agent_core import AgentCore

        agent = db.query(Agent).filter(Agent.id == thread.agent_id).first()
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not found for conversation")

        agent_core = AgentCore(db, agent.id)

        # Build context from conversation history
        context = f"Conversation objective: {thread.objective}\n\n"
        for msg in history[-10:]:  # Last 10 messages
            role = "Agent" if msg["role"] == "agent" else "User"
            context += f"{role}: {msg['content']}\n"

        # Generate response
        response = await agent_core.process_message(
            message_text=reply.message_content,
            sender_key=reply.sender,
            context=context
        )

        ai_reply = response.get("answer", "")

        # Add AI response to history
        history.append({
            "role": "agent",
            "content": ai_reply,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        thread.conversation_history = history

        # Check for goal completion (simplified check)
        goal_keywords = ["completed", "done", "finished", "thank you", "thanks", "bye", "goodbye"]
        if any(kw in reply.message_content.lower() for kw in goal_keywords):
            thread.status = 'goal_achieved'
            thread.goal_achieved = True
            thread.completed_at = datetime.utcnow()
            thread.goal_summary = "User indicated completion"

        db.commit()

        return ConversationReplyResponse(
            should_reply=True,
            reply_content=ai_reply,
            status="success",
            thread_status=thread.status,
            current_turn=thread.current_turn,
            goal_achieved=thread.goal_achieved
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing reply for thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/conversations/{thread_id}/complete", status_code=200,
    dependencies=[Depends(require_permission("flows.execute"))])
def complete_conversation_thread(
    thread_id: int,
    goal_achieved: bool = True,
    summary: Optional[str] = None,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Manually mark a conversation thread as completed."""
    try:
        query = db.query(ConversationThread).filter(ConversationThread.id == thread_id)
        # Apply tenant isolation (handles global admins and NULL tenant_id)
        query = tenant_context.filter_by_tenant(query, ConversationThread.tenant_id)
        thread = query.first()
        if not thread:
            raise HTTPException(status_code=404, detail="Conversation thread not found")

        thread.status = 'goal_achieved' if goal_achieved else 'completed'
        thread.goal_achieved = goal_achieved
        thread.completed_at = datetime.utcnow()
        thread.goal_summary = summary

        db.commit()

        return {
            "thread_id": thread_id,
            "status": thread.status,
            "goal_achieved": goal_achieved,
            "message": "Conversation thread completed"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing conversation thread {thread_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= FLOW RUN ENDPOINTS =============

@router.get("/runs", response_model=List[LegacyFlowRunResponse],
    dependencies=[Depends(require_permission("flows.read"))])
def list_runs(
    flow_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """List flow runs with optional filtering."""
    try:
        query = db.query(FlowRun)

        # Tenant isolation
        if tenant_context.tenant_id:
            query = query.filter(FlowRun.tenant_id == tenant_context.tenant_id)

        if flow_id is not None:
            query = query.filter(FlowRun.flow_definition_id == flow_id)

        if status is not None:
            query = query.filter(FlowRun.status == status)

        runs = query.order_by(FlowRun.created_at.desc()).limit(limit).all()

        return [LegacyFlowRunResponse(
            id=run.id,
            flow_definition_id=run.flow_definition_id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            initiator=run.initiator,
            trigger_context_json=run.trigger_context_json,
            final_report_json=run.final_report_json,
            error_text=run.error_text,
            created_at=run.created_at,
            total_steps=run.total_steps or 0,
            completed_steps=run.completed_steps or 0,
            failed_steps=run.failed_steps or 0
        ) for run in runs]

    except Exception as e:
        logger.error(f"Error listing flow runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}", response_model=LegacyFlowRunResponse,
    dependencies=[Depends(require_permission("flows.read"))])
def get_run(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get a specific flow run by ID."""
    try:
        # Apply tenant isolation
        query = db.query(FlowRun).filter(FlowRun.id == run_id)
        query = tenant_context.filter_by_tenant(query, FlowRun.tenant_id)
        run = query.first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        return LegacyFlowRunResponse(
            id=run.id,
            flow_definition_id=run.flow_definition_id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            initiator=run.initiator,
            trigger_context_json=run.trigger_context_json,
            final_report_json=run.final_report_json,
            error_text=run.error_text,
            created_at=run.created_at,
            total_steps=run.total_steps or 0,
            completed_steps=run.completed_steps or 0,
            failed_steps=run.failed_steps or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/runs/{run_id}/steps", response_model=List[FlowNodeRunResponse],
    dependencies=[Depends(require_permission("flows.read"))])
def get_run_steps(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get all step runs for a flow run."""
    try:
        # Verify run exists and belongs to user's tenant
        query = db.query(FlowRun).filter(FlowRun.id == run_id)
        query = tenant_context.filter_by_tenant(query, FlowRun.tenant_id)
        run = query.first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        step_runs = db.query(FlowNodeRun).filter(
            FlowNodeRun.flow_run_id == run_id
        ).all()

        return step_runs

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting step runs for run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.get("/runs/{run_id}/nodes", response_model=List[FlowNodeRunResponse],
    dependencies=[Depends(require_permission("flows.read"))])
def get_run_nodes(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Alias for get_run_steps (backward compatibility)."""
    return get_run_steps(run_id, db, tenant_context)


# ============= FLOW DEFINITION ENDPOINTS =============

@router.post("/", response_model=FlowDefinitionResponse, status_code=201, dependencies=[Depends(require_permission("flows.write"))])
def create_flow(
    flow: FlowDefinitionCreate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Create a new flow definition."""
    try:
        db_flow = FlowDefinition(
            name=flow.name,
            description=flow.description,
            is_active=flow.is_active,
            tenant_id=tenant_context.tenant_id,
            execution_method="immediate",
            flow_type="workflow"
        )
        db.add(db_flow)
        db.commit()
        db.refresh(db_flow)

        logger.info(f"Created flow definition: {db_flow.id} - {db_flow.name}")

        return flow_to_response(db_flow, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating flow definition: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create", response_model=FlowDefinitionResponse, status_code=201, dependencies=[Depends(require_permission("flows.write"))])
def create_flow_v2(
    flow: FlowCreate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Create a new flow definition with full Phase 8.0 support.
    Supports execution methods, flow types, and inline step creation.
    """
    try:
        db_flow = FlowDefinition(
            name=flow.name,
            description=flow.description,
            tenant_id=tenant_context.tenant_id,
            execution_method=flow.execution_method.value,
            scheduled_at=flow.scheduled_at,
            recurrence_rule=flow.recurrence_rule.model_dump() if flow.recurrence_rule else None,
            flow_type=flow.flow_type.value,
            default_agent_id=flow.default_agent_id,
            is_active=True
        )
        db.add(db_flow)
        db.commit()
        db.refresh(db_flow)

        # Create steps if provided
        if flow.steps:
            for step_data in flow.steps:
                db_step = FlowNode(
                    flow_definition_id=db_flow.id,
                    name=step_data.name,
                    step_description=step_data.description,
                    type=step_data.type.value,
                    position=step_data.position,
                    config_json=json.dumps(step_data.config.model_dump() if step_data.config else {}),
                    timeout_seconds=step_data.timeout_seconds,
                    retry_on_failure=step_data.retry_on_failure,
                    max_retries=step_data.max_retries,
                    retry_delay_seconds=step_data.retry_delay_seconds,
                    condition=step_data.condition,
                    on_success=step_data.on_success,
                    on_failure=step_data.on_failure,
                    allow_multi_turn=step_data.allow_multi_turn,
                    max_turns=step_data.max_turns,
                    conversation_objective=step_data.conversation_objective,
                    agent_id=step_data.agent_id,
                    persona_id=step_data.persona_id
                )
                db.add(db_step)
            db.commit()

        logger.info(f"Created flow definition v2: {db_flow.id} - {db_flow.name}")

        return flow_to_response(db_flow, db)

    except Exception as e:
        db.rollback()
        logger.error(f"Error creating flow definition v2: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[FlowDefinitionResponse], dependencies=[Depends(require_permission("flows.read"))])
def list_flows(
    active: Optional[bool] = None,
    flow_type: Optional[str] = None,
    execution_method: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """List all flow definitions with optional filtering."""
    try:
        query = db.query(FlowDefinition)

        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)

        if active is not None:
            query = query.filter(FlowDefinition.is_active == active)

        if flow_type is not None:
            query = query.filter(FlowDefinition.flow_type == flow_type)

        if execution_method is not None:
            query = query.filter(FlowDefinition.execution_method == execution_method)

        flows = query.order_by(FlowDefinition.created_at.desc()).limit(limit).all()

        return [flow_to_response(flow, db) for flow in flows]

    except Exception as e:
        logger.error(f"Error listing flows: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Tool Metadata for Flow Configuration
# IMPORTANT: Must be BEFORE /{flow_id} routes to avoid path parameter conflict
# ============================================================================

@router.get("/tool-metadata")
def get_tool_metadata(
    tool_type: str,
    tool_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Get tool metadata including commands and parameters for flow configuration.

    Args:
        tool_type: 'built_in' or 'custom'
        tool_id: Tool identifier (for custom tools) or tool name (for built-in)

    Returns:
        Tool metadata with commands and parameters
    """
    from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter

    try:
        logger.info(f"Tool metadata request: type={tool_type}, id={tool_id}, user={current_user.email}")

        if tool_type == "built_in":
            # Return built-in tool parameter schemas
            builtin_tools = {
                "google_search": {
                    "id": "google_search",
                    "name": "Google Search",
                    "commands": [{
                        "id": "search",
                        "name": "search",
                        "parameters": [
                            {
                                "name": "query",
                                "required": True,
                                "description": "Search query text"
                            }
                        ]
                    }]
                },
                "weather": {
                    "id": "weather",
                    "name": "Weather",
                    "commands": [{
                        "id": "current",
                        "name": "current",
                        "parameters": [
                            {
                                "name": "location",
                                "required": True,
                                "description": "City name or coordinates"
                            }
                        ]
                    }]
                },
                "web_scraping": {
                    "id": "web_scraping",
                    "name": "Web Scraping",
                    "commands": [{
                        "id": "scrape",
                        "name": "scrape",
                        "parameters": [
                            {
                                "name": "url",
                                "required": True,
                                "description": "URL to scrape"
                            }
                        ]
                    }]
                },
                "asana_tasks": {
                    "id": "asana_tasks",
                    "name": "Asana Tasks",
                    "commands": [{
                        "id": "create",
                        "name": "create",
                        "parameters": [
                            {
                                "name": "title",
                                "required": True,
                                "description": "Task title"
                            },
                            {
                                "name": "notes",
                                "required": False,
                                "description": "Task description"
                            }
                        ]
                    }]
                },
                "send_message": {
                    "id": "send_message",
                    "name": "Send Message",
                    "commands": [{
                        "id": "send",
                        "name": "send",
                        "parameters": [
                            {
                                "name": "recipient",
                                "required": True,
                                "description": "Phone number or contact identifier"
                            },
                            {
                                "name": "message",
                                "required": True,
                                "description": "Message content"
                            }
                        ]
                    }]
                }
            }

            if tool_id and tool_id in builtin_tools:
                return builtin_tools[tool_id]
            else:
                raise HTTPException(status_code=404, detail="Built-in tool not found")

        elif tool_type == "custom":
            if not tool_id:
                raise HTTPException(status_code=400, detail="tool_id required for custom tools")

            try:
                tool_id_int = int(tool_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid tool_id: must be an integer, got '{tool_id}'")

            # Fetch sandboxed tool with commands and parameters
            # Note: tenant_id can be NULL for global tools, so we check both cases
            tool = db.query(SandboxedTool).filter(
                SandboxedTool.id == tool_id_int
            ).filter(
                (SandboxedTool.tenant_id == current_user.tenant_id) | (SandboxedTool.tenant_id == None)
            ).first()

            if not tool:
                logger.warning(f"Sandboxed tool {tool_id_int} not found for user {current_user.email} (tenant: {current_user.tenant_id})")
                raise HTTPException(status_code=404, detail="Sandboxed tool not found")

            # Get commands for this tool
            commands = db.query(SandboxedToolCommand).filter(
                SandboxedToolCommand.tool_id == tool.id
            ).all()

            # Build response with commands and parameters
            commands_list = []
            for cmd in commands:
                params = db.query(SandboxedToolParameter).filter(
                    SandboxedToolParameter.command_id == cmd.id
                ).all()

                commands_list.append({
                    "id": cmd.id,
                    "name": cmd.command_name,
                    "description": cmd.command_template,
                    "parameters": [
                        {
                            "name": p.parameter_name,
                            "required": p.is_mandatory,
                            "description": p.description or "",
                            "default": p.default_value
                        }
                        for p in params
                    ]
                })

            return {
                "id": tool.id,
                "name": tool.name,
                "tool_type": tool.tool_type,
                "commands": commands_list
            }

        else:
            raise HTTPException(status_code=400, detail="Invalid tool_type. Must be 'built_in' or 'custom'")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching tool metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch tool metadata: {str(e)}")


@router.get("/{flow_id}", response_model=FlowDefinitionResponse, dependencies=[Depends(require_permission("flows.read"))])
def get_flow(
    flow_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get a specific flow definition by ID."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        return flow_to_response(flow, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{flow_id}/detail", dependencies=[Depends(require_permission("flows.read"))])
def get_flow_detail(
    flow_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Get flow with all steps."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        steps = db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_id
        ).order_by(FlowNode.position).all()

        return {
            **flow_to_response(flow, db).model_dump(),
            "steps": [node_to_response(step).model_dump() for step in steps]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting flow detail {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{flow_id}", response_model=FlowDefinitionResponse, dependencies=[Depends(require_permission("flows.write"))])
def update_flow(
    flow_id: int,
    flow: FlowDefinitionUpdate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Update flow definition metadata."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        db_flow = query.first()
        if not db_flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if flow.name is not None:
            db_flow.name = flow.name
        if flow.description is not None:
            db_flow.description = flow.description
        if flow.is_active is not None:
            # CRITICAL FIX 2026-01-08: Close active conversation threads when flow is deactivated
            if flow.is_active == False and db_flow.is_active == True:
                logger.info(f"Flow {flow_id} being deactivated - closing active conversation threads")

                # Find all active threads created by this flow
                from models import ConversationThread, FlowRun, FlowNodeRun

                # Get all flow runs for this flow
                flow_runs = db.query(FlowRun).filter(FlowRun.flow_definition_id == flow_id).all()
                run_ids = [r.id for r in flow_runs]

                if run_ids:
                    # Get all node runs for these flow runs
                    node_runs = db.query(FlowNodeRun).filter(FlowNodeRun.flow_run_id.in_(run_ids)).all()
                    node_run_ids = [nr.id for nr in node_runs]

                    if node_run_ids:
                        # Close all active conversation threads linked to this flow
                        closed_count = db.query(ConversationThread).filter(
                            ConversationThread.flow_step_run_id.in_(node_run_ids),
                            ConversationThread.status == 'active'
                        ).update({
                            'status': 'cancelled',
                            'completed_at': datetime.utcnow(),
                            'goal_summary': f'Flow {flow_id} was deactivated'
                        }, synchronize_session=False)

                        if closed_count > 0:
                            logger.info(f"Closed {closed_count} active conversation thread(s) for flow {flow_id}")

            db_flow.is_active = flow.is_active

        db_flow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(db_flow)

        logger.info(f"Updated flow: {flow_id}")

        return flow_to_response(db_flow, db)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{flow_id}", response_model=FlowDefinitionResponse, dependencies=[Depends(require_permission("flows.write"))])
def patch_flow(
    flow_id: int,
    flow: FlowUpdate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Update flow with Phase 8.0 fields support."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        db_flow = query.first()
        if not db_flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if flow.name is not None:
            db_flow.name = flow.name
        if flow.description is not None:
            db_flow.description = flow.description
        if flow.execution_method is not None:
            db_flow.execution_method = flow.execution_method.value
        if flow.scheduled_at is not None:
            db_flow.scheduled_at = flow.scheduled_at
        if flow.recurrence_rule is not None:
            db_flow.recurrence_rule = flow.recurrence_rule.model_dump()
        if flow.flow_type is not None:
            db_flow.flow_type = flow.flow_type.value
        if flow.default_agent_id is not None:
            db_flow.default_agent_id = flow.default_agent_id
        if flow.is_active is not None:
            # CRITICAL FIX 2026-01-08: Close active conversation threads when flow is deactivated
            if flow.is_active == False and db_flow.is_active == True:
                logger.info(f"Flow {flow_id} being deactivated - closing active conversation threads")

                # Find all active threads created by this flow
                from models import ConversationThread, FlowRun, FlowNodeRun

                # Get all flow runs for this flow
                flow_runs = db.query(FlowRun).filter(FlowRun.flow_definition_id == flow_id).all()
                run_ids = [r.id for r in flow_runs]

                if run_ids:
                    # Get all node runs for these flow runs
                    node_runs = db.query(FlowNodeRun).filter(FlowNodeRun.flow_run_id.in_(run_ids)).all()
                    node_run_ids = [nr.id for nr in node_runs]

                    if node_run_ids:
                        # Close all active conversation threads linked to this flow
                        closed_count = db.query(ConversationThread).filter(
                            ConversationThread.flow_step_run_id.in_(node_run_ids),
                            ConversationThread.status == 'active'
                        ).update({
                            'status': 'cancelled',
                            'completed_at': datetime.utcnow(),
                            'goal_summary': f'Flow {flow_id} was deactivated'
                        }, synchronize_session=False)

                        if closed_count > 0:
                            logger.info(f"Closed {closed_count} active conversation thread(s) for flow {flow_id}")

            db_flow.is_active = flow.is_active

        db_flow.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(db_flow)

        logger.info(f"Patched flow: {flow_id}")

        return flow_to_response(db_flow, db)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error patching flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{flow_id}", status_code=204, dependencies=[Depends(require_permission("flows.delete"))])
def delete_flow(
    flow_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Delete a flow definition and all associated steps."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        run_count = db.query(FlowRun).filter(FlowRun.flow_definition_id == flow_id).count()
        if run_count > 0 and not force:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot delete flow with {run_count} existing run(s). Use force=true or deactivate instead."
            )

        # Cancel any active conversation threads before deleting
        if force and run_count > 0:
            # Find all FlowNodeRun IDs for this flow's runs
            run_ids = [r.id for r in db.query(FlowRun.id).filter(FlowRun.flow_definition_id == flow_id).all()]
            if run_ids:
                node_run_ids = [nr.id for nr in db.query(FlowNodeRun.id).filter(FlowNodeRun.flow_run_id.in_(run_ids)).all()]
                if node_run_ids:
                    # Mark active conversation threads as cancelled (not deleted)
                    from datetime import datetime
                    db.query(ConversationThread).filter(
                        ConversationThread.flow_step_run_id.in_(node_run_ids),
                        ConversationThread.status == 'active'
                    ).update({
                        'status': 'cancelled',
                        'completed_at': datetime.utcnow(),
                        'goal_summary': 'Flow was deleted'
                    }, synchronize_session=False)

            # Delete related runs
            db.query(FlowRun).filter(FlowRun.flow_definition_id == flow_id).delete()

        db.delete(flow)
        db.commit()

        logger.info(f"Deleted flow: {flow_id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= FLOW STEP ENDPOINTS =============

@router.post("/{flow_id}/steps", response_model=FlowNodeResponse, status_code=201, dependencies=[Depends(require_permission("flows.write"))])
def create_step(
    flow_id: int,
    step: FlowNodeCreate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Add a step to a flow."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        # Validate position
        if step.position < 1:
            raise HTTPException(status_code=400, detail="Position must be >= 1")

        # Check if position is already taken
        existing = db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_id,
            FlowNode.position == step.position
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Position {step.position} is already occupied")

        db_step = FlowNode(
            flow_definition_id=flow_id,
            type=step.type,
            position=step.position,
            config_json=json.dumps(step.config_json),
            next_node_id=step.next_node_id,
            name=step.name,
            step_description=step.description,
            timeout_seconds=step.timeout_seconds,
            retry_on_failure=step.retry_on_failure,
            max_retries=step.max_retries,
            allow_multi_turn=step.allow_multi_turn,
            max_turns=step.max_turns,
            conversation_objective=step.conversation_objective,
            agent_id=step.agent_id,
            persona_id=step.persona_id
        )
        db.add(db_step)
        db.commit()
        db.refresh(db_step)

        logger.info(f"Created step {db_step.id} for flow {flow_id}")

        return node_to_response(db_step)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating step for flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.post("/{flow_id}/nodes", response_model=FlowNodeResponse, status_code=201, dependencies=[Depends(require_permission("flows.write"))])
def create_node(
    flow_id: int,
    node: FlowNodeCreate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Add a node to a flow (alias for create_step)."""
    return create_step(flow_id, node, db, tenant_context)


@router.get("/{flow_id}/steps", response_model=List[FlowNodeResponse], dependencies=[Depends(require_permission("flows.read"))])
def list_steps(
    flow_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """List all steps for a flow, ordered by position."""
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        steps = db.query(FlowNode).filter(
            FlowNode.flow_definition_id == flow_id
        ).order_by(FlowNode.position).all()

        return [node_to_response(step) for step in steps]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing steps for flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.get("/{flow_id}/nodes", response_model=List[FlowNodeResponse], dependencies=[Depends(require_permission("flows.read"))])
def list_nodes(
    flow_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """List all nodes for a flow (alias for list_steps)."""
    return list_steps(flow_id, db, tenant_context)


@router.put("/{flow_id}/steps/{step_id}", response_model=FlowNodeResponse, dependencies=[Depends(require_permission("flows.write"))])
def update_step(
    flow_id: int,
    step_id: int,
    step: FlowNodeUpdate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Update step configuration."""
    try:
        flow_query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        flow_query = tenant_context.filter_by_tenant(flow_query, FlowDefinition.tenant_id)
        if not flow_query.first():
            raise HTTPException(status_code=404, detail="Flow not found")

        db_step = db.query(FlowNode).filter(
            FlowNode.id == step_id,
            FlowNode.flow_definition_id == flow_id
        ).first()

        if not db_step:
            raise HTTPException(status_code=404, detail="Step not found")

        if step.type is not None:
            db_step.type = step.type
        if step.position is not None:
            db_step.position = step.position
        if step.config_json is not None:
            db_step.config_json = json.dumps(step.config_json)
        if step.next_node_id is not None:
            db_step.next_node_id = step.next_node_id
        if step.name is not None:
            db_step.name = step.name
        if step.description is not None:
            db_step.step_description = step.description
        if step.timeout_seconds is not None:
            db_step.timeout_seconds = step.timeout_seconds
        if step.retry_on_failure is not None:
            db_step.retry_on_failure = step.retry_on_failure
        if step.max_retries is not None:
            db_step.max_retries = step.max_retries
        if step.allow_multi_turn is not None:
            db_step.allow_multi_turn = step.allow_multi_turn
        if step.max_turns is not None:
            db_step.max_turns = step.max_turns
        if step.conversation_objective is not None:
            db_step.conversation_objective = step.conversation_objective
        if step.agent_id is not None:
            db_step.agent_id = step.agent_id
        if step.persona_id is not None:
            db_step.persona_id = step.persona_id

        db_step.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(db_step)

        logger.info(f"Updated step {step_id} for flow {flow_id}")

        return node_to_response(db_step)

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.put("/{flow_id}/nodes/{node_id}", response_model=FlowNodeResponse, dependencies=[Depends(require_permission("flows.write"))])
def update_node(
    flow_id: int,
    node_id: int,
    node: FlowNodeUpdate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Update node configuration (alias for update_step)."""
    return update_step(flow_id, node_id, node, db, tenant_context)


@router.delete("/{flow_id}/steps/{step_id}", status_code=204, dependencies=[Depends(require_permission("flows.write"))])
def delete_step(
    flow_id: int,
    step_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Delete a step from a flow."""
    try:
        flow_query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        flow_query = tenant_context.filter_by_tenant(flow_query, FlowDefinition.tenant_id)
        if not flow_query.first():
            raise HTTPException(status_code=404, detail="Flow not found")

        step = db.query(FlowNode).filter(
            FlowNode.id == step_id,
            FlowNode.flow_definition_id == flow_id
        ).first()

        if not step:
            raise HTTPException(status_code=404, detail="Step not found")

        db.delete(step)
        db.commit()

        logger.info(f"Deleted step {step_id} from flow {flow_id}")

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting step {step_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.delete("/{flow_id}/nodes/{node_id}", status_code=204, dependencies=[Depends(require_permission("flows.write"))])
def delete_node(
    flow_id: int,
    node_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Delete a node from a flow (alias for delete_step)."""
    return delete_step(flow_id, node_id, db, tenant_context)


# ============= VALIDATION ENDPOINT =============

@router.get("/{flow_id}/validate", dependencies=[Depends(require_permission("flows.read"))])
def validate_flow(
    flow_id: int,
    strict: bool = False,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Validate flow structure before execution.

    Args:
        strict: If True, enforce legacy Trigger requirement
    """
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        is_valid, error_message = validate_flow_structure(db, flow_id, strict=strict)

        return {
            "valid": is_valid,
            "errors": [error_message] if error_message else [],
            "flow_id": flow_id,
            "node_count": count_flow_nodes(db, flow_id),
            "step_count": count_flow_nodes(db, flow_id)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error validating flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= FLOW EXECUTION ENDPOINTS =============

@router.post("/{flow_id}/execute", response_model=LegacyFlowRunResponse, status_code=202, dependencies=[Depends(require_permission("flows.execute"))])
async def execute_flow(
    flow_id: int,
    run_data: Optional[LegacyFlowRunCreate] = None,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """
    Execute a flow immediately (Phase 8.0).
    Returns immediately with created FlowRun.
    """
    try:
        query = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id)
        query = tenant_context.filter_by_tenant(query, FlowDefinition.tenant_id)
        flow = query.first()
        if not flow:
            raise HTTPException(status_code=404, detail="Flow not found")

        if not flow.is_active:
            raise HTTPException(status_code=400, detail="Flow is not active")

        is_valid, error_message = validate_flow_structure(db, flow_id, strict=False)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid flow structure: {error_message}")

        logger.info(f"Executing flow {flow_id}")

        from flows.flow_engine import FlowEngine

        engine = FlowEngine(db)
        trigger_context = run_data.trigger_context_json if run_data else None

        flow_run = await engine.run_flow(
            flow_definition_id=flow_id,
            trigger_context=trigger_context,
            initiator="api",
            trigger_type="immediate"
        )

        logger.info(f"Flow run {flow_run.id} completed with status: {flow_run.status}")

        return LegacyFlowRunResponse(
            id=flow_run.id,
            flow_definition_id=flow_run.flow_definition_id,
            status=flow_run.status,
            started_at=flow_run.started_at,
            completed_at=flow_run.completed_at,
            initiator=flow_run.initiator,
            trigger_context_json=flow_run.trigger_context_json,
            final_report_json=flow_run.final_report_json,
            error_text=flow_run.error_text,
            created_at=flow_run.created_at,
            total_steps=flow_run.total_steps or 0,
            completed_steps=flow_run.completed_steps or 0,
            failed_steps=flow_run.failed_steps or 0
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing flow {flow_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Alias for backward compatibility
@router.post("/{flow_id}/run", response_model=LegacyFlowRunResponse, status_code=202, dependencies=[Depends(require_permission("flows.execute"))])
async def run_flow(
    flow_id: int,
    run_data: LegacyFlowRunCreate,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Execute a flow (alias for execute_flow)."""
    return await execute_flow(flow_id, run_data, db, tenant_context)


@router.post("/runs/{run_id}/cancel", status_code=200,
    dependencies=[Depends(require_permission("flows.execute"))])
def cancel_run(
    run_id: int,
    db: Session = Depends(get_db),
    tenant_context: TenantContext = Depends(get_tenant_context)
):
    """Cancel a pending or running flow run."""
    try:
        # Verify run exists and belongs to user's tenant
        query = db.query(FlowRun).filter(FlowRun.id == run_id)
        query = tenant_context.filter_by_tenant(query, FlowRun.tenant_id)
        run = query.first()
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        if run.status not in ['pending', 'running']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel run with status: {run.status}"
            )

        run.status = "cancelled"
        run.completed_at = datetime.utcnow()
        run.error_text = "Cancelled by user"

        db.commit()

        logger.info(f"Flow run {run_id} cancelled")

        return {
            "run_id": run_id,
            "status": "cancelled",
            "message": "Flow run cancelled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling run {run_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
