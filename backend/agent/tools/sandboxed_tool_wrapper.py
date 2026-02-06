"""
Sandboxed Tool Wrapper (formerly SandboxedToolWrapper)
Skills-as-Tools Phase 6: Renamed from sandboxed_tool_wrapper.py

Phase 6.1: Original implementation as SandboxedToolWrapper
Phase: Custom Tools Hub - Added long-running command support with WhatsApp notifications

Wraps sandboxed tools for integration with the agent service.
Sandboxed tools run in isolated Docker containers (nmap, nuclei, etc.).
Uses LLM-based detection via system prompt instead of keyword matching.
"""

import asyncio
import logging
from typing import Optional, Dict, Any, List, Callable, Awaitable
from sqlalchemy.orm import Session

from models import SandboxedTool, SandboxedToolCommand, SandboxedToolParameter, AgentSandboxedTool
from .sandboxed_tool_service import SandboxedToolService
from .workspace_manager import WorkspaceManager


class SandboxedToolWrapper:
    """Wrapper for integrating sandboxed tools with agent service."""

    def __init__(
        self,
        db_session: Session,
        agent_id: Optional[int] = None,
        tenant_id: Optional[str] = None,
        persona_id: Optional[int] = None,
        on_complete_callback: Optional[Callable[[str, str], Awaitable[None]]] = None
    ):
        """
        Initialize sandboxed tool wrapper.

        Args:
            db_session: Database session
            agent_id: Optional agent ID for per-agent tool filtering
            tenant_id: Optional tenant ID for container execution and multi-tenancy
            persona_id: Optional persona ID for persona-based tool filtering
            on_complete_callback: Async callback(recipient, message) for sending follow-up messages
        """
        self.db = db_session
        self.agent_id = agent_id
        self.tenant_id = tenant_id
        self.persona_id = persona_id
        self.service = SandboxedToolService(db_session, tenant_id=tenant_id)
        self.on_complete_callback = on_complete_callback
        self.logger = logging.getLogger(__name__)

    def get_available_tools(self) -> List[SandboxedTool]:
        """
        Get all enabled sandboxed tools for this agent/persona.

        Tool discovery sources (combined):
        1. AgentSandboxedTool junction table (legacy, if agent_id is set)
        2. Persona's enabled_sandboxed_tools JSON field (if persona_id is set)

        Returns tools that are enabled and belong to the tenant.
        """
        from models import Persona

        tool_ids = set()

        # Source 1: AgentSandboxedTool junction table (legacy support)
        if self.agent_id:
            agent_mappings = self.db.query(AgentSandboxedTool).filter(
                AgentSandboxedTool.agent_id == self.agent_id,
                AgentSandboxedTool.is_enabled == True
            ).all()
            tool_ids.update([m.sandboxed_tool_id for m in agent_mappings])
            self.logger.debug(f"AgentSandboxedTool mappings found: {[m.sandboxed_tool_id for m in agent_mappings]}")

        # Source 2: Persona's enabled_sandboxed_tools JSON field
        if self.persona_id:
            persona = self.db.query(Persona).filter(Persona.id == self.persona_id).first()
            if persona and persona.enabled_sandboxed_tools:
                # enabled_sandboxed_tools is a JSON array of tool IDs
                persona_tool_ids = persona.enabled_sandboxed_tools
                if isinstance(persona_tool_ids, list):
                    tool_ids.update(persona_tool_ids)
                    self.logger.info(f"Persona {self.persona_id} has enabled_sandboxed_tools: {persona_tool_ids}")
                else:
                    self.logger.warning(f"Persona {self.persona_id} has invalid enabled_sandboxed_tools format: {persona_tool_ids}")
            else:
                self.logger.debug(f"Persona {self.persona_id} has no enabled_sandboxed_tools")

        # If no tools found from any source
        if not tool_ids:
            self.logger.info(f"No sandboxed tools found for agent_id={self.agent_id}, persona_id={self.persona_id}")
            return []

        self.logger.info(f"Combined tool IDs to query: {tool_ids}")

        # Build query for the actual tool objects
        query = self.db.query(SandboxedTool).filter(
            SandboxedTool.id.in_(tool_ids),
            SandboxedTool.is_enabled == True
        )

        # Filter by tenant if specified (multi-tenancy)
        if self.tenant_id:
            query = query.filter(SandboxedTool.tenant_id == self.tenant_id)

        tools = query.all()
        self.logger.info(f"Found {len(tools)} enabled sandboxed tools: {[t.name for t in tools]}")
        return tools

    def get_tool_system_prompts(self) -> str:
        """
        Get combined system prompts for all enabled sandboxed tools.

        Returns:
            Combined system prompts describing available tools
        """
        tools = self.get_available_tools()
        if not tools:
            return ""

        prompts = []
        prompts.append("\n## Available Custom Tools\n")

        for tool in tools:
            prompts.append(f"\n### {tool.name} ({tool.tool_type})")
            prompts.append(tool.system_prompt)

            # List commands
            commands = self.db.query(SandboxedToolCommand).filter_by(tool_id=tool.id).all()
            if commands:
                prompts.append(f"\nCommands:")
                for cmd in commands:
                    prompts.append(f"- {cmd.command_name}: {cmd.command_template}")

                    # List parameters
                    params = self.db.query(SandboxedToolParameter).filter_by(command_id=cmd.id).all()
                    if params:
                        for param in params:
                            mandatory_str = "required" if param.is_mandatory else "optional"
                            default_str = f" (default: {param.default_value})" if param.default_value else ""
                            prompts.append(f"  * {param.parameter_name} ({mandatory_str}){default_str}: {param.description}")

        return "\n".join(prompts)

    def get_ollama_tools(self) -> list:
        """
        Generate Ollama-compatible tool definitions for native tool calling.

        Returns:
            List of tool definitions in Ollama's native format
        """
        ollama_tools = []
        available_tools = self.get_available_tools()

        for tool_obj in available_tools:
            # Query commands for this tool
            commands = self.db.query(SandboxedToolCommand).filter_by(tool_id=tool_obj.id).all()

            for cmd in commands:
                # Build parameters schema
                properties = {}
                required = []

                params = self.db.query(SandboxedToolParameter).filter_by(command_id=cmd.id).all()
                for param in params:
                    properties[param.parameter_name] = {
                        "type": "string",
                        "description": param.description or f"Parameter {param.parameter_name}"
                    }
                    if param.is_mandatory:
                        required.append(param.parameter_name)

                # Add 'command' as an implicit required parameter
                properties["command"] = {
                    "type": "string",
                    "description": f"Command to execute (use: {cmd.command_name})"
                }
                required.append("command")

                tool_def = {
                    "type": "function",
                    "function": {
                        "name": tool_obj.name,
                        "description": f"{tool_obj.name}: {cmd.command_name}",
                        "parameters": {
                            "type": "object",
                            "properties": properties,
                            "required": required
                        }
                    }
                }
                ollama_tools.append(tool_def)

        self.logger.info(f"Generated {len(ollama_tools)} Ollama-compatible tool definitions")
        return ollama_tools

    def parse_tool_call(self, ai_response: str) -> Optional[Dict[str, Any]]:
        """
        Parse AI response for tool call instructions.

        Supported formats:
        1. Standard format with backticks:
           ```tool:nuclei
           command:scan_url
           url:http://example.com
           output_file:results.txt
           ```

        2. Simple format without backticks (used by some Ollama models):
           tool:nuclei
           command:scan_url
           url:http://example.com
           output_file:results.txt

        3. JSON format (used by MFDoom/deepseek-v2-tool-calling):
           ```json
           {"name":"nmap","parameters":{"command":"quick_scan","target":"host.docker.internal"}}
           ```

        4. TOOL_CALL format (used by sandboxed tool system prompts):
           [TOOL_CALL]
           tool_name: nmap
           command_name: quick_scan
           parameters:
             target: scanme.nmap.org
           [/TOOL_CALL]

        Args:
            ai_response: AI model response text

        Returns:
            Dict with tool_name, command_name, parameters or None
        """
        import re
        import json

        tool_block = None
        tool_name = None

        # Try [TOOL_CALL] format first (used by sandboxed tool system prompts)
        if "[TOOL_CALL]" in ai_response and "[/TOOL_CALL]" in ai_response:
            try:
                start = ai_response.find("[TOOL_CALL]") + len("[TOOL_CALL]")
                end = ai_response.find("[/TOOL_CALL]")
                if end > start:
                    tool_call_block = ai_response[start:end].strip()
                    lines = [line.strip() for line in tool_call_block.split("\n") if line.strip()]

                    tool_name = None
                    command_name = None
                    parameters = {}
                    in_parameters = False

                    for line in lines:
                        if line.startswith("tool_name:"):
                            tool_name = line.split(":", 1)[1].strip()
                        elif line.startswith("command_name:"):
                            command_name = line.split(":", 1)[1].strip()
                        elif line.startswith("parameters:"):
                            in_parameters = True
                        elif in_parameters and ":" in line:
                            # Parse parameter (handles indented key: value pairs)
                            key, value = line.split(":", 1)
                            parameters[key.strip()] = value.strip()

                    if tool_name and command_name:
                        self.logger.info(f"Parsed [TOOL_CALL] format: tool={tool_name}, command={command_name}")
                        return {
                            "tool_name": tool_name,
                            "command_name": command_name,
                            "parameters": parameters
                        }
            except Exception as e:
                self.logger.warning(f"Error parsing [TOOL_CALL] format: {e}")

        # Try JSON format (for MFDoom/deepseek-v2-tool-calling)
        if "```json" in ai_response:
            try:
                start = ai_response.find("```json") + 7
                end = ai_response.find("```", start)
                if end != -1:
                    json_str = ai_response[start:end].strip()
                    tool_data = json.loads(json_str)

                    if "name" in tool_data and "parameters" in tool_data:
                        tool_name = tool_data["name"]
                        params = tool_data["parameters"]
                        command_name = params.pop("command", None)

                        if command_name:
                            self.logger.info(f"Parsed JSON tool format: tool={tool_name}, command={command_name}")
                            return {
                                "tool_name": tool_name,
                                "command_name": command_name,
                                "parameters": params
                            }
            except json.JSONDecodeError as e:
                self.logger.warning(f"Error parsing JSON tool format: {e}")
            except Exception as e:
                self.logger.warning(f"Error parsing JSON tool format: {e}")

        # Try standard format with backticks
        if "```tool:" in ai_response:
            try:
                start = ai_response.find("```tool:")
                end = ai_response.find("```", start + 7)
                if end != -1:
                    tool_block = ai_response[start + 7:end].strip()
                    lines = [line.strip() for line in tool_block.split("\n") if line.strip()]
                    if lines:
                        tool_name = lines[0].lstrip(':')
                        tool_block = "\n".join(lines[1:])  # Rest of lines
            except Exception as e:
                self.logger.warning(f"Error parsing backtick format: {e}")

        # Try simple format without backticks (for Ollama models)
        if not tool_name:
            # Look for pattern: tool:toolname\ncommand:...
            match = re.search(r'(?:^|\n)tool:(\w+)\s*\n((?:(?:command|target|output_file|url|[a-z_]+):[^\n]+\n?)+)', ai_response, re.MULTILINE)
            if match:
                tool_name = match.group(1).strip()
                tool_block = match.group(2).strip()
                self.logger.info(f"Parsed simple tool format: tool={tool_name}")

        if not tool_name or not tool_block:
            return None

        try:
            lines = [line.strip() for line in tool_block.split("\n") if line.strip()]

            # Parse parameters
            parameters = {}
            command_name = None

            for line in lines:
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "command":
                        command_name = value
                    else:
                        parameters[key] = value

            if not command_name:
                self.logger.warning(f"No command specified in tool call for {tool_name}")
                return None

            return {
                "tool_name": tool_name,
                "command_name": command_name,
                "parameters": parameters
            }

        except Exception as e:
            self.logger.error(f"Error parsing tool call: {e}", exc_info=True)
            return None

    async def _execute_python_internal_tool(
        self,
        tool_name: str,
        command_name: str,
        parameters: Dict[str, str]
    ) -> str:
        """
        Execute a Python-internal tool (like flights, asana).

        Args:
            tool_name: Name of the tool (e.g., "flights", "asana")
            command_name: Command to execute (e.g., "search", "list_tasks")
            parameters: Command parameters

        Returns:
            Formatted result string
        """
        import time
        start_time = time.time()

        try:
            # NOTE: Flights tool has been migrated to FlightSearchSkill (Hub provider architecture)
            # See: backend/agent/skills/flight_search_skill.py
            # See: backend/hub/providers/amadeus_provider.py
            # Migration script: scripts/migrate_flight_tool_to_skill.py

            # No built-in python_internal tools - all should be registered via sandboxed_tools table
            return f"Error: Unknown python_internal tool: {tool_name}.{command_name}"

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"Error in python_internal tool execution: {e}", exc_info=True)
            return f"Error executing {tool_name}.{command_name}: {str(e)}"

    async def execute_tool_call(
        self,
        tool_call: Dict[str, Any],
        agent_run_id: Optional[int] = None,
        recipient: Optional[str] = None
    ) -> Optional[str]:
        """
        Execute a parsed tool call.

        For long-running commands with a callback and recipient:
        - Returns immediately with "Starting..." message
        - Executes in background
        - Sends results via callback when complete

        Args:
            tool_call: Parsed tool call dict
            agent_run_id: Optional agent run ID for tracking
            recipient: Optional recipient for follow-up messages (WhatsApp chat_id)

        Returns:
            Tool execution result or None on error
        """
        try:
            tool_name = tool_call["tool_name"]
            command_name = tool_call["command_name"]
            parameters = tool_call["parameters"]

            # Get tool
            tool = self.service.get_tool_by_name(tool_name)
            if not tool:
                self.logger.error(f"Tool not found: {tool_name}")
                return f"Error: Tool '{tool_name}' not found"

            # Get command
            commands = self.service.get_tool_commands(tool.id)
            command = next((cmd for cmd in commands if cmd.command_name == command_name), None)
            if not command:
                self.logger.error(f"Command not found: {command_name}")
                return f"Error: Command '{command_name}' not found for tool '{tool_name}'"

            # Handle python_internal tools specially
            if tool.tool_type == "python_internal":
                self.logger.info(f"Executing python_internal tool: {tool_name}.{command_name}")
                return await self._execute_python_internal_tool(
                    tool_name, command_name, parameters
                )

            # Check if this is a long-running command that should be backgrounded
            # Only background if we have a callback and recipient for follow-up
            if command.is_long_running and self.on_complete_callback and recipient:
                self.logger.info(f"Starting long-running command in background: {tool_name}.{command_name}")

                # Schedule background execution
                asyncio.create_task(
                    self._execute_and_notify(
                        tool=tool,
                        command=command,
                        parameters=parameters,
                        agent_run_id=agent_run_id,
                        recipient=recipient
                    )
                )

                # Return immediate acknowledgment
                return (
                    f"⏳ Starting {tool_name} ({command_name})...\n\n"
                    f"This may take a while. I'll send the results when complete."
                )

            # Execute external command tools (synchronous for non-long-running)
            self.logger.info(f"Executing sandboxed tool: {tool_name}.{command_name} with params {parameters}")
            execution = await self.service.execute_command(
                tool_id=tool.id,
                command_id=command.id,
                parameters=parameters,
                agent_run_id=agent_run_id
            )

            return self._format_execution_result(tool_name, command_name, execution, parameters)

        except Exception as e:
            self.logger.error(f"Error executing tool call: {e}", exc_info=True)
            return f"Error executing tool: {str(e)}"

    async def _execute_and_notify(
        self,
        tool: SandboxedTool,
        command: SandboxedToolCommand,
        parameters: Dict[str, Any],
        agent_run_id: Optional[int],
        recipient: str
    ):
        """
        Execute command in background and notify recipient when complete.
        Used for long-running commands via WhatsApp.
        """
        try:
            self.logger.info(f"Background execution started: {tool.name}.{command.command_name}")

            # Execute the command
            execution = await self.service.execute_command(
                tool_id=tool.id,
                command_id=command.id,
                parameters=parameters,
                agent_run_id=agent_run_id
            )

            # Format result
            result = self._format_execution_result(
                tool.name, command.command_name, execution, parameters
            )

            # Prepend completion header
            if execution.status == "completed":
                message = f"✅ **{tool.name}** completed!\n\n{result}"
            else:
                message = f"❌ **{tool.name}** failed\n\n{result}"

            # Truncate for WhatsApp if too long
            MAX_WHATSAPP_LENGTH = 4000
            if len(message) > MAX_WHATSAPP_LENGTH:
                message = message[:MAX_WHATSAPP_LENGTH - 100] + "\n\n... (output truncated)"

            # Send follow-up message via callback
            if self.on_complete_callback:
                await self.on_complete_callback(recipient, message)
                self.logger.info(f"Follow-up message sent to {recipient}")

        except Exception as e:
            self.logger.error(f"Background execution failed: {e}", exc_info=True)

            # Try to notify about the error
            if self.on_complete_callback:
                try:
                    error_msg = f"❌ **{tool.name}** failed\n\nError: {str(e)}"
                    await self.on_complete_callback(recipient, error_msg)
                except Exception as notify_error:
                    self.logger.error(f"Failed to send error notification: {notify_error}")

    def _format_execution_result(
        self,
        tool_name: str,
        command_name: str,
        execution,
        parameters: Dict[str, Any]
    ) -> str:
        """Format execution result for display."""
        if execution.status == "running":
            # Long-running command started in background
            result = f"## {tool_name} - {command_name}\n\n"
            result += f"Status: ⏳ {execution.status}\n"
            result += f"Start time: {execution.execution_time_ms}ms\n\n"
            result += f"{execution.output}\n"
            return result

        elif execution.status == "completed":
            result = f"## {tool_name} - {command_name}\n\n"
            result += f"Status: ✅ {execution.status}\n"
            result += f"Execution time: {execution.execution_time_ms}ms\n\n"

            # For tools that write to output files, read the file content
            file_content = None
            if tool_name == "webhook" and "output_file" in parameters:
                output_file = parameters["output_file"]
                file_content = self.read_workspace_file(tool_name, output_file)
            elif tool_name == "nuclei" and "output_file" in parameters:
                # Nuclei writes scan results to file with -o flag, stdout only shows progress
                output_file = parameters["output_file"]
                file_content = self.read_workspace_file(tool_name, output_file)

            # Show file content first (actual API response)
            # CRITICAL: Truncate large files to prevent WhatsApp message size errors (error 479)
            # WhatsApp text message limit is ~65KB, so we limit file content to 5000 chars (~5KB)
            if file_content:
                MAX_FILE_CONTENT_CHARS = 5000
                original_length = len(file_content)

                if original_length > MAX_FILE_CONTENT_CHARS:
                    truncated_content = file_content[:MAX_FILE_CONTENT_CHARS]
                    result += f"Response Data (showing first {MAX_FILE_CONTENT_CHARS} of {original_length} characters):\n```\n{truncated_content}\n```\n\n"
                    result += f"⚠️ **Note**: Response was truncated due to size ({original_length} chars). "
                    result += f"File saved at: workspace/{tool_name}/{parameters['output_file']}\n\n"
                else:
                    result += f"Response Data:\n```json\n{file_content}\n```\n\n"

            # Then show stdout (HTTP status line)
            if execution.output:
                output_text = execution.output

                # Special handling for nuclei: detect and clarify "no findings" scenarios
                if tool_name == "nuclei":
                    # Check if output contains actual findings (lines starting with [ that have severity)
                    finding_lines = [l for l in output_text.split('\n')
                                    if l.startswith('[') and any(sev in l for sev in ['critical]', 'high]', 'medium]', 'low]', 'info]'])]

                    if not finding_lines:
                        # No findings detected
                        severity = parameters.get('severity', 'all')
                        result += f"**🔍 Scan Complete - No vulnerabilities found at severity: {severity}**\n\n"
                        result += "This could mean:\n"
                        result += "- The target has no vulnerabilities at this severity level\n"
                        result += "- The target may be rate-limiting requests\n"
                        result += "- Try a broader severity like `critical,high,medium` or `info`\n\n"
                    else:
                        result += f"**🔍 Found {len(finding_lines)} vulnerabilities:**\n\n"

                result += f"Output:\n```\n{output_text}\n```\n"

            if execution.error:
                result += f"\nWarnings/Errors:\n```\n{execution.error}\n```\n"

            return result
        else:
            # Failed or unknown status
            error_msg = execution.error or "Unknown error"
            return f"Error executing {tool_name}.{command_name}: {error_msg}"

    def get_workspace_files(self, tool_name: str) -> List[str]:
        """
        Get list of files in a tool's workspace.

        Args:
            tool_name: Name of the tool

        Returns:
            List of file paths
        """
        workspace = WorkspaceManager()
        try:
            return workspace.list_files(tool_name)
        except Exception as e:
            self.logger.error(f"Error listing workspace files for {tool_name}: {e}")
            return []

    def read_workspace_file(self, tool_name: str, file_path: str) -> Optional[str]:
        """
        Read a file from a tool's workspace.

        Args:
            tool_name: Name of the tool
            file_path: Relative path within workspace

        Returns:
            File content or None on error
        """
        workspace = WorkspaceManager()
        try:
            return workspace.read_file(tool_name, file_path)
        except Exception as e:
            self.logger.error(f"Error reading workspace file {file_path} for {tool_name}: {e}")
            return None
