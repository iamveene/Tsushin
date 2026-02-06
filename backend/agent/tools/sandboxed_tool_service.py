"""
Sandboxed Tool Service (formerly SandboxedToolService)
Skills-as-Tools Phase 6: Renamed from sandboxed_tool_service.py

Phase 6.1: Original implementation as SandboxedToolService
Phase 9+: Container-only execution (removed legacy local mode)

Executes sandboxed tools (commands, webhooks, HTTP requests) in isolated per-tenant toolbox containers.
"""

import asyncio
import time
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter, SandboxedToolExecution


class CommandExecutionError(Exception):
    """Raised when command execution fails."""
    pass


class SandboxedToolService:
    """Service for executing sandboxed tools in per-tenant toolbox containers."""

    def __init__(self, db_session: Session, tenant_id: Optional[str] = None):
        self.db = db_session
        self.tenant_id = tenant_id  # Required for container execution
        self.logger = logging.getLogger(__name__)
        self._toolbox_service = None

    @property
    def toolbox_service(self):
        """Lazy-load toolbox service to avoid circular imports"""
        if self._toolbox_service is None:
            from services.toolbox_container_service import get_toolbox_service
            self._toolbox_service = get_toolbox_service()
        return self._toolbox_service

    async def execute_command(
        self,
        tool_id: int,
        command_id: int,
        parameters: Dict[str, Any],
        agent_run_id: Optional[int] = None
    ) -> SandboxedToolExecution:
        """
        Execute a sandboxed tool command with given parameters.

        Args:
            tool_id: ID of the sandboxed tool
            command_id: ID of the command to execute
            parameters: Dictionary of parameter values
            agent_run_id: Optional AgentRun ID for tracking

        Returns:
            SandboxedToolExecution record with results

        Raises:
            ValueError: If tool/command not found or invalid
            CommandExecutionError: If execution fails
        """
        # Load tool and command
        tool = self.db.query(SandboxedTool).filter_by(id=tool_id).first()
        if not tool:
            raise ValueError(f"Tool not found: {tool_id}")

        if not tool.is_enabled:
            raise ValueError(f"Tool is disabled: {tool.name}")

        command = self.db.query(SandboxedToolCommand).filter_by(id=command_id, tool_id=tool_id).first()
        if not command:
            raise ValueError(f"Command not found: {command_id}")

        # Validate and render command template
        rendered_command = self._render_command(command, parameters)

        # Create execution record
        execution = SandboxedToolExecution(
            agent_run_id=agent_run_id,
            tool_id=tool_id,
            command_id=command_id,
            rendered_command=rendered_command,
            status="pending"
        )
        self.db.add(execution)
        self.db.commit()

        try:
            # Execute based on tool type
            if tool.tool_type == "command":
                # All command tools execute in tenant's toolbox container
                if not self.tenant_id:
                    raise CommandExecutionError("Tenant ID required for tool execution")

                output, error, exec_time = await self._execute_in_container(
                    tool=tool,
                    command_template=rendered_command,
                    timeout=command.timeout_seconds,
                    is_long_running=command.is_long_running
                )

                # Update execution record
                # For long-running commands that returned immediately, mark as "running"
                if command.is_long_running and "background" in output.lower():
                    execution.status = "running"
                    execution.output = output
                    execution.execution_time_ms = exec_time
                    # Don't set completed_at for running commands
                else:
                    execution.status = "completed" if not error else "failed"
                    execution.output = output
                    execution.error = error
                    execution.execution_time_ms = exec_time
                    execution.completed_at = datetime.utcnow()

            elif tool.tool_type == "webhook":
                raise NotImplementedError("Webhook execution not yet implemented (Phase 6.1 MVP)")

            elif tool.tool_type == "http":
                raise NotImplementedError("HTTP execution not yet implemented (Phase 6.1 MVP)")

            else:
                raise ValueError(f"Unknown tool type: {tool.tool_type}")

            self.db.commit()
            self.logger.info(f"Command executed successfully: {execution.id}")

            return execution

        except Exception as e:
            self.logger.error(f"Command execution failed: {e}", exc_info=True)
            execution.status = "failed"
            execution.error = str(e)
            execution.completed_at = datetime.utcnow()
            self.db.commit()
            raise CommandExecutionError(f"Execution failed: {e}")

    async def _execute_in_container(
        self,
        tool: SandboxedTool,
        command_template: str,
        timeout: int,
        is_long_running: bool
    ) -> tuple[str, str, int]:
        """
        Execute a command in the tenant's toolbox container.

        Args:
            tool: SandboxedTool instance
            command_template: Rendered command string
            timeout: Timeout in seconds
            is_long_running: Whether command is expected to run long

        Returns:
            Tuple of (stdout, stderr, execution_time_ms)

        Raises:
            CommandExecutionError: If execution fails
        """
        if not self.tenant_id:
            raise CommandExecutionError("Tenant ID required for container execution")

        self.logger.info(f"Executing in container for tenant {self.tenant_id}: {command_template[:100]}...")

        try:
            # Ensure container is running
            self.toolbox_service.ensure_container_running(self.tenant_id, self.db)

            # Use default workspace directory (tool-specific subdirs not guaranteed to exist)
            workdir = "/workspace"

            # Execute command in container
            result = await self.toolbox_service.execute_command(
                tenant_id=self.tenant_id,
                command=command_template,
                timeout=timeout,
                workdir=workdir,
                db=self.db
            )

            stdout = result.get('stdout', '')
            stderr = result.get('stderr', '')
            exec_time = result.get('execution_time_ms', 0)

            # Handle timeout gracefully
            if result.get('timed_out'):
                error_msg = f"Command timed out after {timeout}s. Try reducing scope (e.g., lower depth, fewer targets)."
                self.logger.warning(f"Tool execution timed out: {command_template[:100]}")
                return stdout, error_msg, exec_time

            # Handle OOM kill gracefully
            if result.get('oom_killed'):
                error_msg = (
                    "Process was killed due to excessive memory usage (container limit: 2GB). "
                    "Try reducing scope: use lower crawl depth, fewer concurrent requests, or a smaller target."
                )
                self.logger.warning(f"Tool execution OOM killed: {command_template[:100]}")
                return stdout, error_msg, exec_time

            # Check for other errors
            if not result.get('success', False) and stderr:
                self.logger.warning(f"Container command returned errors: {stderr[:200]}")

            return stdout, stderr, exec_time

        except RuntimeError as e:
            self.logger.error(f"Container execution failed: {e}")
            raise CommandExecutionError(f"Container execution failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error in container execution: {e}", exc_info=True)
            raise CommandExecutionError(f"Container execution error: {e}")

    def _render_command(self, command: SandboxedToolCommand, parameters: Dict[str, Any]) -> str:
        """
        Render command template with parameter values.

        Args:
            command: SandboxedToolCommand instance
            parameters: Dictionary of parameter values

        Returns:
            Rendered command string

        Raises:
            ValueError: If required parameters missing
        """
        # Load command parameters
        cmd_params = self.db.query(SandboxedToolParameter).filter_by(command_id=command.id).all()

        # Build parameter map with defaults
        param_map = {}
        for param in cmd_params:
            if param.parameter_name in parameters:
                param_map[param.parameter_name] = parameters[param.parameter_name]
            elif param.default_value:
                param_map[param.parameter_name] = param.default_value
            elif param.is_mandatory:
                raise ValueError(f"Missing required parameter: {param.parameter_name}")

        # Render template (replace both <param_name> and {param_name} with values)
        rendered = command.command_template
        for param_name, param_value in param_map.items():
            # Support both <param_name> and {param_name} placeholder formats
            angle_placeholder = f"<{param_name}>"
            curly_placeholder = f"{{{param_name}}}"
            rendered = rendered.replace(angle_placeholder, str(param_value))
            rendered = rendered.replace(curly_placeholder, str(param_value))

        # Check for unresolved placeholders
        has_angle = '<' in rendered and '>' in rendered
        has_curly = '{' in rendered and '}' in rendered and not rendered.startswith('curl')
        if has_angle or has_curly:
            self.logger.warning(f"Unresolved placeholders in command: {rendered}")

        return rendered

    def get_tool_by_name(self, tool_name: str) -> Optional[SandboxedTool]:
        """Get a sandboxed tool by name."""
        return self.db.query(SandboxedTool).filter_by(name=tool_name).first()

    def get_tool_commands(self, tool_id: int) -> list[SandboxedToolCommand]:
        """Get all commands for a tool."""
        return self.db.query(SandboxedToolCommand).filter_by(tool_id=tool_id).all()

    def get_command_parameters(self, command_id: int) -> list[SandboxedToolParameter]:
        """Get all parameters for a command."""
        return self.db.query(SandboxedToolParameter).filter_by(command_id=command_id).all()

    def get_execution_history(
        self,
        tool_id: Optional[int] = None,
        agent_run_id: Optional[int] = None,
        limit: int = 50
    ) -> list[SandboxedToolExecution]:
        """
        Get execution history with optional filters.

        Args:
            tool_id: Filter by tool ID
            agent_run_id: Filter by agent run ID
            limit: Maximum number of records to return

        Returns:
            List of SandboxedToolExecution records
        """
        query = self.db.query(SandboxedToolExecution)

        if tool_id is not None:
            query = query.filter_by(tool_id=tool_id)

        if agent_run_id is not None:
            query = query.filter_by(agent_run_id=agent_run_id)

        return query.order_by(SandboxedToolExecution.created_at.desc()).limit(limit).all()


class NucleiToolSetup:
    """Helper class for setting up the Nuclei tool."""

    DEFAULT_TEST_URL = "http://testphp.vulnweb.com"

    @staticmethod
    def create_nuclei_tool(db_session: Session) -> SandboxedTool:
        """
        Create the pre-built Nuclei security scanner tool.

        Args:
            db_session: SQLAlchemy database session

        Returns:
            Created SandboxedTool instance
        """
        # Check if tool already exists
        existing = db_session.query(SandboxedTool).filter_by(name="nuclei").first()
        if existing:
            return existing

        # Create tool
        tool = SandboxedTool(
            name="nuclei",
            tool_type="command",
            system_prompt=(
                "You are a security analyst assistant with access to the Nuclei vulnerability scanner. "
                "Nuclei is a fast, template-based vulnerability scanner that can detect security issues. "
                "CRITICAL: Always extract the URL from the user's CURRENT message. "
                "NEVER use URLs from previous conversations or memory. "
                "When the user asks to scan a URL, use the 'scan_url' command with the exact URL they specified."
            ),
            workspace_dir="./data/workspace/nuclei",
            is_enabled=True
        )
        db_session.add(tool)
        db_session.flush()

        # Create scan_url command
        scan_command = SandboxedToolCommand(
            tool_id=tool.id,
            command_name="scan_url",
            command_template="nuclei -u <url> -o <output_file> -silent",
            is_long_running=False,
            timeout_seconds=120
        )
        db_session.add(scan_command)
        db_session.flush()

        # Create parameters for scan_url
        url_param = SandboxedToolParameter(
            command_id=scan_command.id,
            parameter_name="url",
            is_mandatory=True,
            default_value=None,  # No default - force AI to extract URL from user's current request
            description="Target URL to scan - MUST be extracted from user's current request, never from memory"
        )
        output_param = SandboxedToolParameter(
            command_id=scan_command.id,
            parameter_name="output_file",
            is_mandatory=False,
            default_value="nuclei_results.txt",
            description="Output file for scan results"
        )
        db_session.add(url_param)
        db_session.add(output_param)

        db_session.commit()

        return tool
