"""
Phase 16: Slash Commands API Routes

RESTful API for slash command management and execution.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_dependencies import get_current_user_required
from services.slash_command_service import SlashCommandService

router = APIRouter(tags=["Commands"])


# ============================================================================
# Request/Response Models
# ============================================================================

class CommandResponse(BaseModel):
    """Response for a single command."""
    id: int
    category: str
    command_name: str
    language_code: str
    pattern: str
    aliases: List[str]
    description: Optional[str]
    help_text: Optional[str]
    is_enabled: bool
    handler_type: str
    sort_order: int


class CommandExecuteRequest(BaseModel):
    """Request to execute a slash command."""
    message: str
    agent_id: int
    channel: str = "playground"
    sender_key: Optional[str] = None
    thread_id: Optional[int] = None  # Thread ID for playground channel


class CommandExecuteResponse(BaseModel):
    """Response from command execution."""
    status: str
    action: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class CommandsByCategory(BaseModel):
    """Commands organized by category."""
    categories: Dict[str, List[CommandResponse]]


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/api/commands", response_model=List[CommandResponse])
async def list_commands(
    category: Optional[str] = None,
    language_code: str = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: List available slash commands.

    Optionally filter by category or language.
    """
    service = SlashCommandService(db)
    commands = service.get_commands(
        tenant_id=current_user.tenant_id,
        category=category,
        language_code=language_code
    )

    return [CommandResponse(**cmd) for cmd in commands]


@router.get("/api/commands/by-category")
async def get_commands_by_category(
    language_code: str = "en",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Get commands organized by category.

    Useful for building command palettes and menus.
    """
    service = SlashCommandService(db)
    by_category = service.get_commands_by_category(
        tenant_id=current_user.tenant_id,
        language_code=language_code
    )

    return {"categories": by_category}


@router.post("/api/commands/detect")
async def detect_command(
    message: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Detect if a message is a slash command.

    Returns command info if detected, null otherwise.
    """
    service = SlashCommandService(db)
    detection = service.detect_command(message, current_user.tenant_id)

    if not detection:
        return {"is_command": False, "command": None}

    return {
        "is_command": True,
        "command": detection["command"],
        "groups": detection["groups"],
        "args": detection["args"]
    }


@router.post("/api/commands/execute", response_model=CommandExecuteResponse)
async def execute_command(
    data: CommandExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Execute a slash command.

    Handles built-in commands and routes to appropriate handlers.
    """
    from agent.memory.tool_output_buffer import get_tool_output_buffer
    import logging

    logger = logging.getLogger(__name__)
    service = SlashCommandService(db)

    # Use provided sender_key or generate from user ID
    # Match the format used in playground_service.py for proper tool buffer integration
    if data.channel == "playground" and data.thread_id:
        # Use thread-specific sender_key format for proper isolation
        sender_key = data.sender_key or f"playground_u{current_user.id}_a{data.agent_id}_t{data.thread_id}"
    elif data.channel == "playground":
        sender_key = data.sender_key or f"playground_user_{current_user.id}"
    else:
        sender_key = data.sender_key or f"user_{current_user.id}"

    result = await service.execute_command(
        message=data.message,
        tenant_id=current_user.tenant_id,
        agent_id=data.agent_id,
        sender_key=sender_key,
        channel=data.channel,
        user_id=current_user.id
    )

    # Layer 5: Store tool output in ephemeral buffer for follow-up interactions
    # This enables agentic analysis of tool results with execution IDs
    if result.get("action") in ("tool_executed", "tool_running") and result.get("message"):
        tool_buffer = get_tool_output_buffer()
        tool_name = result.get("tool_name", "unknown")
        command_name = result.get("command_name", "execute")

        execution_id = tool_buffer.add_tool_output(
            agent_id=data.agent_id,
            sender_key=sender_key,
            tool_name=tool_name,
            command_name=command_name,
            output=result["message"]
        )
        result["execution_id"] = execution_id

    # Store command and response in conversation memory for complete history
    # This fixes the "broken/split" conversation issue in Playground UI
    if data.channel == "playground" and result.get("message"):
        try:
            from agent.memory.multi_agent_memory import MultiAgentMemoryManager
            from models import Agent
            import json as json_module

            # Get agent configuration from database
            agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
            if not agent:
                logger.warning(f"Agent {data.agent_id} not found, skipping memory storage")
                return CommandExecuteResponse(
                    status=result.get("status", "unknown"),
                    action=result.get("action"),
                    message=result.get("message"),
                    data={k: v for k, v in result.items() if k not in ["status", "action", "message"]}
                )

            # Build minimal config dict for memory manager
            config_dict = {
                "agent_id": agent.id,
                "model_provider": agent.model_provider,
                "model_name": agent.model_name,
                "memory_size": agent.memory_size or 1000,
            }

            memory_manager = MultiAgentMemoryManager(db, config_dict)

            # Store user's command as a user message
            await memory_manager.add_message(
                agent_id=data.agent_id,
                sender_key=sender_key,
                role="user",
                content=data.message,
                metadata={"source": "slash_command", "command_type": result.get("action")},
                use_contact_mapping=False  # Playground keys don't need contact mapping (prevents double-prefix bug)
            )

            # Store the response as an assistant message
            await memory_manager.add_message(
                agent_id=data.agent_id,
                sender_key=sender_key,
                role="assistant",
                content=result["message"],
                metadata={
                    "source": "slash_command",
                    "command_type": result.get("action"),
                    "execution_id": result.get("execution_id")
                },
                use_contact_mapping=False  # Playground keys don't need contact mapping (prevents double-prefix bug)
            )
            logger.info(f"Stored slash command and response in conversation memory for {sender_key}")
        except Exception as e:
            logger.warning(f"Failed to store slash command in memory: {e}")

    response = CommandExecuteResponse(
        status=result.get("status", "unknown"),
        action=result.get("action"),
        message=result.get("message"),
        data=result.get("data")
    )

    # Debug logging for project commands
    if result.get("action") in ["project_entered", "project_exited"]:
        logger.info(f"[PROJECT CMD] Returning response: action={response.action}, data={response.data}")

    return response


@router.get("/api/commands/{command_id}/help")
async def get_command_help(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Get detailed help for a specific command.
    """
    from models import SlashCommand

    command = db.query(SlashCommand).filter(
        SlashCommand.id == command_id,
        SlashCommand.tenant_id.in_([current_user.tenant_id, "_system"])
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    return {
        "command_name": command.command_name,
        "category": command.category,
        "description": command.description,
        "help_text": command.help_text,
        "pattern": command.pattern,
        "aliases": command.aliases
    }


@router.get("/api/commands/autocomplete")
async def autocomplete_commands(
    query: str,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_required)
):
    """
    Phase 16: Autocomplete command suggestions.

    Returns matching commands for the given prefix.
    """
    service = SlashCommandService(db)
    all_commands = service.get_commands(current_user.tenant_id)

    # Remove leading slash if present
    search = query.lstrip("/").lower()

    matches = []
    for cmd in all_commands:
        cmd_name = cmd["command_name"].lower()
        aliases = [a.lower() for a in cmd.get("aliases", [])]

        # Match on command name or aliases
        if cmd_name.startswith(search) or any(a.startswith(search) for a in aliases):
            matches.append({
                "command_name": cmd["command_name"],
                "description": cmd.get("description", ""),
                "category": cmd["category"],
                "aliases": cmd.get("aliases", [])
            })

    # Sort by relevance (exact prefix matches first)
    matches.sort(key=lambda x: (
        0 if x["command_name"].lower().startswith(search) else 1,
        len(x["command_name"])
    ))

    return {"suggestions": matches[:limit]}
