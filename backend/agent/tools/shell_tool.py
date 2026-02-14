"""
Shell Tool - Phase 18.3: Tool Integration

Tool wrapper for shell command execution via the ShellSkill.
This tool is called by the AI agent when it needs to run shell commands.

Provides:
- run_shell_command function for agent tool use
- Integration with ShellCommandService
- Proper error handling and response formatting
- ToolOutputBuffer integration for /inject support (Phase 18.3.7)
"""

import logging
from typing import Dict, Any, Optional

from sqlalchemy.orm import Session

from services.shell_command_service import ShellCommandService, CommandResult
from models import Agent

logger = logging.getLogger(__name__)


def get_tool_definition() -> Dict[str, Any]:
    """
    Get the OpenAI-compatible tool definition for shell commands.

    Returns:
        Tool schema for AI agent function calling
    """
    return {
        "type": "function",
        "function": {
            "name": "run_shell_command",
            "description": (
                "Execute shell commands on registered remote hosts. "
                "Use this to run system commands, check server status, "
                "manage files, query system info, or execute scripts on remote machines. "
                "Commands are executed via secure beacon agents."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": (
                            "The command or multi-line script to execute. "
                            "Commands are executed in sequence with working directory tracking. "
                            "Examples: 'ls -la', 'df -h', 'cd /tmp && ls', "
                            "'uname -a\\nhostname\\nuptime'"
                        )
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Target host for execution. Options:\n"
                            "- 'default': First available beacon (recommended)\n"
                            "- hostname: Specific host by name (e.g., 'server-001')\n"
                            "- '@all': Execute on all registered hosts\n"
                            "Default: 'default'"
                        ),
                        "default": "default"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            "Maximum seconds to wait for the command result. "
                            "If exceeded, command may continue running in background. "
                            "Range: 1-300. Default: 120"
                        ),
                        "default": 120,
                        "minimum": 1,
                        "maximum": 300
                    }
                },
                "required": ["script"]
            }
        }
    }


async def run_shell_command(
    script: str,
    db: Session,
    agent_id: int,
    target: str = "default",
    timeout: int = 120,
    sender_key: str = None
) -> str:
    """
    Execute a shell command and return formatted result.

    This function is called by the agent's tool execution loop.

    Args:
        script: Command or multi-line script to execute
        db: Database session
        agent_id: ID of the agent executing the command
        target: Target host ("default", hostname, or "@all")
        timeout: Maximum wait time in seconds
        sender_key: Sender identifier for ToolOutputBuffer (optional)

    Returns:
        Formatted string result for the agent
    """
    try:
        # Get tenant ID from agent
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return "❌ Error: Agent not found"

        tenant_id = agent.tenant_id
        if not tenant_id:
            return "❌ Error: Agent has no tenant configured"

        # NOTE: Sentinel LLM analysis has been moved to ShellCommandService
        # to ensure pattern-based security checks run FIRST (cheaper, faster)
        # Sentinel only analyzes commands that pass pattern matching

        # Create service
        service = ShellCommandService(db)

        # Validate timeout
        timeout = max(1, min(timeout, 300))

        logger.debug(f"[SHELL-TOOL] run_shell_command: script={script[:50]}, agent_id={agent_id}, tenant_id={tenant_id}, target={target}, timeout={timeout}")

        # Execute command - CRITICAL: Use async version to avoid blocking the event loop!
        # The sync execute_command() uses time.sleep() which blocks beacon checkins.
        result = await service.execute_command_async(
            script=script,
            target=target,
            tenant_id=tenant_id,
            initiated_by=f"agent:{agent_id}",
            agent_id=agent_id,
            timeout_seconds=timeout,
            wait_for_result=True
        )

        logger.debug(f"[SHELL-TOOL] run_shell_command result: success={result.success}, status={result.status}, timed_out={result.timed_out}")

        # Phase 18.3.7: Add output to ToolOutputBuffer for /inject support
        if result.success or result.stdout or result.stderr:
            try:
                from agent.memory.tool_output_buffer import get_tool_output_buffer

                buffer = get_tool_output_buffer()
                # Determine sender_key - use provided or fallback to agent identifier
                effective_sender = sender_key or f"agent:{agent_id}"

                # Combine stdout and stderr for the output
                output_parts = []
                if result.stdout:
                    output_parts.append(result.stdout)
                if result.stderr:
                    output_parts.append(f"[STDERR]\n{result.stderr}")
                output = "\n".join(output_parts) if output_parts else "(no output)"

                # Add to buffer with shell as tool name and target as command
                execution_id = buffer.add_tool_output(
                    agent_id=agent_id,
                    sender_key=effective_sender,
                    tool_name="shell",
                    command_name=target or "default",
                    output=output,
                    target=target
                )
                logger.info(f"Shell output added to buffer: execution #{execution_id}")
            except Exception as buffer_error:
                logger.warning(f"Failed to add shell output to buffer: {buffer_error}")

        # Format response
        return result.to_agent_response()

    except Exception as e:
        logger.error(f"Shell tool error: {e}", exc_info=True)
        return f"❌ Error executing shell command: {str(e)}"


def format_shell_result(result: CommandResult) -> Dict[str, Any]:
    """
    Format a CommandResult for structured output.

    Used when you need the raw data rather than a formatted string.

    Args:
        result: CommandResult from service

    Returns:
        Dict with structured result data
    """
    return {
        "success": result.success,
        "command_id": result.command_id,
        "status": result.status,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "execution_time_ms": result.execution_time_ms,
        "error": result.error_message,
        "timed_out": result.timed_out,
        "delivery_failed": result.delivery_failed,
        # Security fields (CRIT-005)
        "blocked": result.blocked,
        "blocked_reason": result.blocked_reason,
        "requires_approval": result.requires_approval,
        "risk_level": result.risk_level,
        "security_warnings": result.security_warnings,
        "yolo_mode_auto_approved": result.yolo_mode_auto_approved
    }


# Tool registration info for the agent's tool registry
TOOL_INFO = {
    "name": "run_shell_command",
    "category": "system",
    "description": "Execute shell commands on remote hosts via secure beacon agents",
    "requires_db": True,
    "requires_agent": True,
    "handler": run_shell_command,
    "definition": get_tool_definition
}
