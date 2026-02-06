"""
Sandboxed Tools API Routes (formerly Custom Tools)
Skills-as-Tools Phase 6: Renamed from custom tools to sandboxed tools

Phase 6.1: Original implementation as Custom Tools API
Phase: Custom Tools Hub - Added tenant-aware container execution
Provides CRUD operations for sandboxed tools and execution endpoints.

Security: CRIT-008 fix - All endpoints now require authentication and tenant isolation.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter, SandboxedToolExecution, AgentSandboxedTool, Agent
from models_rbac import User
from agent.tools.sandboxed_tool_service import SandboxedToolService
from agent.tools.workspace_manager import WorkspaceManager
from auth_dependencies import get_tenant_context, TenantContext, require_permission

router = APIRouter()

# Global engine (set by app.py)
_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


def get_db():
    if _engine is None:
        raise RuntimeError("Database engine not initialized")
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Pydantic Models
# ============================================================================

class SandboxedToolCreate(BaseModel):
    name: str
    tool_type: str  # 'command', 'webhook', 'http'
    system_prompt: str
    # DEPRECATED: workspace_dir is ignored - all tools use /workspace in container
    workspace_dir: Optional[str] = None  # Deprecated, kept for backward compatibility
    is_enabled: bool = True


class SandboxedToolUpdate(BaseModel):
    name: Optional[str] = None
    tool_type: Optional[str] = None
    system_prompt: Optional[str] = None
    # DEPRECATED: workspace_dir is ignored - all tools use /workspace in container
    workspace_dir: Optional[str] = None  # Deprecated, kept for backward compatibility
    is_enabled: Optional[bool] = None


class SandboxedToolResponse(BaseModel):
    id: int
    name: str
    tool_type: str
    system_prompt: str
    workspace_dir: Optional[str]  # Deprecated field, always returns legacy value
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None  # Made optional for backward compatibility

    class Config:
        from_attributes = True


class SandboxedToolCommandCreate(BaseModel):
    tool_id: int
    command_name: str
    command_template: str
    is_long_running: bool = False
    timeout_seconds: int = 30


class SandboxedToolCommandResponse(BaseModel):
    id: int
    tool_id: int
    command_name: str
    command_template: str
    is_long_running: bool
    timeout_seconds: int
    created_at: datetime

    class Config:
        from_attributes = True


class SandboxedToolParameterCreate(BaseModel):
    command_id: int
    parameter_name: str
    is_mandatory: bool = False
    default_value: Optional[str] = None
    description: Optional[str] = None


class SandboxedToolParameterResponse(BaseModel):
    id: int
    command_id: int
    parameter_name: str
    is_mandatory: bool
    default_value: Optional[str]
    description: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class SandboxedToolExecuteRequest(BaseModel):
    tool_id: int
    command_id: int
    parameters: Dict[str, Any]
    agent_run_id: Optional[int] = None


class SandboxedToolExecutionResponse(BaseModel):
    id: int
    agent_run_id: Optional[int]
    tool_id: int
    command_id: int
    rendered_command: str
    status: str
    output: Optional[str]
    error: Optional[str]
    execution_time_ms: Optional[int]
    created_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True


# ============================================================================
# Custom Tools CRUD
# ============================================================================

@router.get("/custom-tools/", response_model=List[SandboxedToolResponse])
def list_sandboxed_tools(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all custom tools for the current tenant (requires tools.execute permission)."""
    query = ctx.filter_by_tenant(db.query(SandboxedTool), SandboxedTool.tenant_id)
    tools = query.all()
    return tools


@router.get("/custom-tools/{tool_id}", response_model=SandboxedToolResponse)
def get_sandboxed_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get a specific custom tool by ID (requires tools.execute permission)."""
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Custom tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    return tool


@router.post("/custom-tools/", response_model=SandboxedToolResponse)
def create_sandboxed_tool(
    tool: SandboxedToolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new custom tool (requires tools.manage permission)."""
    # Check for duplicate name within the tenant
    existing = db.query(SandboxedTool).filter(
        SandboxedTool.name == tool.name,
        SandboxedTool.tenant_id == ctx.tenant_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Tool with this name already exists")

    new_tool = SandboxedTool(
        name=tool.name,
        tool_type=tool.tool_type,
        system_prompt=tool.system_prompt,
        workspace_dir=tool.workspace_dir or f"./data/workspace/{tool.name}",
        is_enabled=tool.is_enabled,
        tenant_id=ctx.tenant_id  # Assign to current tenant
    )
    db.add(new_tool)
    db.flush()  # Get the tool ID

    # AUTO-ASSIGN: Automatically enable this tool for all agents in the tenant
    # This ensures newly created tools are immediately available to agents
    tenant_agents = db.query(Agent).filter(Agent.tenant_id == ctx.tenant_id).all()
    for agent in tenant_agents:
        agent_tool = AgentSandboxedTool(
            agent_id=agent.id,
            sandboxed_tool_id=new_tool.id,
            is_enabled=True
        )
        db.add(agent_tool)

    db.commit()
    db.refresh(new_tool)
    return new_tool


@router.put("/custom-tools/{tool_id}", response_model=SandboxedToolResponse)
def update_sandboxed_tool(
    tool_id: int,
    tool: SandboxedToolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update an existing custom tool (requires tools.manage permission)."""
    existing = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not existing:
        raise HTTPException(status_code=404, detail="Custom tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(existing.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    if tool.name is not None:
        existing.name = tool.name
    if tool.tool_type is not None:
        existing.tool_type = tool.tool_type
    if tool.system_prompt is not None:
        existing.system_prompt = tool.system_prompt
    if tool.workspace_dir is not None:
        existing.workspace_dir = tool.workspace_dir
    if tool.is_enabled is not None:
        existing.is_enabled = tool.is_enabled

    existing.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(existing)
    return existing


@router.delete("/custom-tools/{tool_id}")
def delete_sandboxed_tool(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a custom tool and all associated data (requires tools.manage permission)."""
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Custom tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    db.delete(tool)
    db.commit()
    return {"status": "success", "message": f"Tool '{tool.name}' deleted"}


# ============================================================================
# Commands CRUD
# ============================================================================

@router.get("/custom-tools/{tool_id}/commands", response_model=List[SandboxedToolCommandResponse])
def list_tool_commands(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all commands for a tool (requires tools.execute permission)."""
    # Verify tool exists and user has access
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    commands = db.query(SandboxedToolCommand).filter_by(tool_id=tool_id).all()
    return commands


@router.post("/custom-tools/commands/", response_model=SandboxedToolCommandResponse)
def create_tool_command(
    command: SandboxedToolCommandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new command for a tool (requires tools.manage permission)."""
    # Verify tool exists and user has access
    tool = db.query(SandboxedTool).filter_by(id=command.tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    new_command = SandboxedToolCommand(
        tool_id=command.tool_id,
        command_name=command.command_name,
        command_template=command.command_template,
        is_long_running=command.is_long_running,
        timeout_seconds=command.timeout_seconds
    )
    db.add(new_command)
    db.commit()
    db.refresh(new_command)
    return new_command


@router.delete("/custom-tools/commands/{command_id}")
def delete_tool_command(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a command (requires tools.manage permission)."""
    command = db.query(SandboxedToolCommand).filter_by(id=command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    # Verify access through the parent tool
    tool = db.query(SandboxedTool).filter_by(id=command.tool_id).first()
    if not tool or not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this command")

    db.delete(command)
    db.commit()
    return {"status": "success", "message": "Command deleted"}


# ============================================================================
# Parameters CRUD
# ============================================================================

@router.get("/custom-tools/commands/{command_id}/parameters", response_model=List[SandboxedToolParameterResponse])
def list_command_parameters(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all parameters for a command (requires tools.execute permission)."""
    # Verify command exists and get parent tool for tenant check
    command = db.query(SandboxedToolCommand).filter_by(id=command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    tool = db.query(SandboxedTool).filter_by(id=command.tool_id).first()
    if not tool or not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this command")

    parameters = db.query(SandboxedToolParameter).filter_by(command_id=command_id).all()
    return parameters


@router.post("/custom-tools/parameters/", response_model=SandboxedToolParameterResponse)
def create_command_parameter(
    parameter: SandboxedToolParameterCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new parameter for a command (requires tools.manage permission)."""
    # Verify command exists
    command = db.query(SandboxedToolCommand).filter_by(id=parameter.command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    # Verify tenant access through parent tool
    tool = db.query(SandboxedTool).filter_by(id=command.tool_id).first()
    if not tool or not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this command")

    new_param = SandboxedToolParameter(
        command_id=parameter.command_id,
        parameter_name=parameter.parameter_name,
        is_mandatory=parameter.is_mandatory,
        default_value=parameter.default_value,
        description=parameter.description
    )
    db.add(new_param)
    db.commit()
    db.refresh(new_param)
    return new_param


@router.delete("/custom-tools/parameters/{parameter_id}")
def delete_command_parameter(
    parameter_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a parameter (requires tools.manage permission)."""
    parameter = db.query(SandboxedToolParameter).filter_by(id=parameter_id).first()
    if not parameter:
        raise HTTPException(status_code=404, detail="Parameter not found")

    # Verify access through command -> tool chain
    command = db.query(SandboxedToolCommand).filter_by(id=parameter.command_id).first()
    if not command:
        raise HTTPException(status_code=403, detail="Access denied to this parameter")

    tool = db.query(SandboxedTool).filter_by(id=command.tool_id).first()
    if not tool or not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this parameter")

    db.delete(parameter)
    db.commit()
    return {"status": "success", "message": "Parameter deleted"}


# ============================================================================
# Execution
# ============================================================================

@router.post("/custom-tools/execute/", response_model=SandboxedToolExecutionResponse)
async def execute_sandboxed_tool(
    request: SandboxedToolExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Execute a custom tool command with given parameters (requires tools.execute permission).

    If the tool's execution_mode is 'container', the command will be executed
    in the tenant's toolbox container. Otherwise, it runs locally.
    """
    # Verify tool exists and user has access
    tool = db.query(SandboxedTool).filter_by(id=request.tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    # Pass tenant_id for container execution support
    service = SandboxedToolService(db, tenant_id=ctx.tenant_id if ctx else None)

    try:
        execution = await service.execute_command(
            tool_id=request.tool_id,
            command_id=request.command_id,
            parameters=request.parameters,
            agent_run_id=request.agent_run_id
        )
        return execution

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Execution failed: {str(e)}")


@router.get("/custom-tools/executions/", response_model=List[SandboxedToolExecutionResponse])
def list_executions(
    tool_id: Optional[int] = None,
    agent_run_id: Optional[int] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List execution history with optional filters (requires tools.execute permission)."""
    # Build query with tenant filtering via explicit JOIN condition
    query = db.query(SandboxedToolExecution).join(
        SandboxedTool,
        SandboxedToolExecution.tool_id == SandboxedTool.id
    )
    query = ctx.filter_by_tenant(query, SandboxedTool.tenant_id)

    if tool_id is not None:
        query = query.filter(SandboxedToolExecution.tool_id == tool_id)
    if agent_run_id is not None:
        query = query.filter(SandboxedToolExecution.agent_run_id == agent_run_id)

    executions = query.order_by(SandboxedToolExecution.created_at.desc()).limit(limit).all()
    return executions


@router.get("/custom-tools/executions/{execution_id}", response_model=SandboxedToolExecutionResponse)
def get_execution(
    execution_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get a specific execution by ID (requires tools.execute permission)."""
    execution = db.query(SandboxedToolExecution).filter_by(id=execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    # Verify access through the parent tool
    tool = db.query(SandboxedTool).filter_by(id=execution.tool_id).first()
    if not tool or not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this execution")

    return execution


# ============================================================================
# Workspace Management
# ============================================================================

@router.get("/custom-tools/{tool_id}/workspace/files")
def list_workspace_files(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List files in a tool's workspace (requires tools.manage permission)."""
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    workspace = WorkspaceManager()
    try:
        files = workspace.list_files(tool.name)
        return {"tool_name": tool.name, "files": files}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list files: {str(e)}")


@router.get("/custom-tools/{tool_id}/workspace/files/{file_path:path}")
def read_workspace_file(
    tool_id: int,
    file_path: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Read a file from a tool's workspace (requires tools.manage permission)."""
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    workspace = WorkspaceManager()
    try:
        content = workspace.read_file(tool.name, file_path)
        return {"file_path": file_path, "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file: {str(e)}")


@router.delete("/custom-tools/{tool_id}/workspace")
def clean_workspace(
    tool_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("tools.manage")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Clean all files from a tool's workspace (requires tools.manage permission)."""
    tool = db.query(SandboxedTool).filter_by(id=tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    # Verify tenant access
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tool")

    workspace = WorkspaceManager()
    try:
        workspace.clean_workspace(tool.name)
        return {"status": "success", "message": f"Workspace cleaned for tool '{tool.name}'"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clean workspace: {str(e)}")
