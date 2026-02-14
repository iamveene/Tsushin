"""
Shell Skill - Phase 18.3: Tool Integration

Enables AI agents to execute shell commands on registered remote hosts
via the C2 (Command & Control) architecture.

Features:
- Tool use: AI calls run_shell_command tool
- Slash command: /shell for programmatic fire-and-forget
- Target resolution: default, hostname, @all
- Timeout handling with DB polling
"""

import re
import logging
from typing import Dict, Any, Optional, List

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from services.shell_command_service import ShellCommandService, CommandResult
from models import Agent

logger = logging.getLogger(__name__)


class ShellSkill(BaseSkill):
    """
    Shell Skill for remote command execution.

    Supports two modes:
    1. Tool Use (Agentic Mode): AI agent calls run_shell_command tool
    2. Slash Command (/shell): Fire-and-forget command queueing

    Examples:
        /shell ls -la
        /shell hostname:df -h
        /shell @all:uptime
    """

    skill_type = "shell"
    skill_name = "Shell Commands"
    skill_description = "Execute shell commands on registered remote hosts via secure beacon agents"
    execution_mode = "hybrid"  # Supports both /shell command and AI tool calls

    # Regex patterns for slash command
    SHELL_COMMAND_PATTERN = re.compile(
        r'^/shell\s+(?:(?P<target>[\w\-@]+):)?(?P<command>.+)$',
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self):
        """Initialize the shell skill."""
        super().__init__()
        self._service: Optional[ShellCommandService] = None

    def _get_service(self) -> Optional[ShellCommandService]:
        """Get or create the ShellCommandService instance."""
        if self._service is None and self._db_session:
            self._service = ShellCommandService(self._db_session)
        return self._service

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Get default configuration for this skill."""
        return {
            # Default target when none specified
            "default_target": "default",

            # Default timeout for command execution (seconds)
            "default_timeout": 120,

            # Maximum timeout allowed
            "max_timeout": 300,

            # Whether to wait for result by default
            "wait_for_result": True,

            # Enable /shell slash command
            "enable_slash_command": True,

            # Keywords for AI detection (optional)
            "keywords": [],

            # AI classification fallback
            "use_ai_fallback": False
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """Get JSON schema for skill configuration."""
        return {
            "type": "object",
            "properties": {
                "default_target": {
                    "type": "string",
                    "description": "Default target when none specified (hostname or 'default')",
                    "default": "default"
                },
                "default_timeout": {
                    "type": "integer",
                    "description": "Default timeout in seconds",
                    "default": 120,
                    "minimum": 1,
                    "maximum": 300
                },
                "max_timeout": {
                    "type": "integer",
                    "description": "Maximum allowed timeout in seconds",
                    "default": 300,
                    "minimum": 1,
                    "maximum": 3600
                },
                "wait_for_result": {
                    "type": "boolean",
                    "description": "Wait for command result by default",
                    "default": True
                },
                "enable_slash_command": {
                    "type": "boolean",
                    "description": "Enable /shell slash command",
                    "default": True
                },
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger shell skill detection",
                    "default": []
                },
                "use_ai_fallback": {
                    "type": "boolean",
                    "description": "Use AI classification for intent detection",
                    "default": False
                }
            },
            "required": []
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Phase 20: Skill-aware Sentinel security system.
        Provides context about expected shell command behaviors
        so legitimate commands aren't blocked.

        Returns:
            Sentinel context dict with expected intents and patterns
        """
        return {
            "expected_intents": [
                "Execute shell commands on remote hosts",
                "Check system status (disk, memory, CPU, processes)",
                "List files and directories",
                "Run scripts on servers",
                "Check server health and resources"
            ],
            "expected_patterns": [
                "/shell", "run command", "execute", "check status",
                "disk usage", "memory", "cpu", "process",
                "ls", "df", "top", "ps", "free", "uptime"
            ],
            "risk_notes": (
                "Shell command execution is expected for this skill. "
                "Still flag and analyze for: data exfiltration, reverse shells, "
                "unauthorized system modifications, cryptominer installation, "
                "commands targeting sensitive directories (/etc, /root, credentials)."
            )
        }

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """MCP-compliant tool definition for shell command execution."""
        return {
            "name": "run_shell_command",
            "title": "Shell Command Executor",
            "description": (
                "Execute shell commands on registered remote hosts. "
                "Use this to run system commands, check server status, "
                "manage files, or execute scripts on remote machines."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": (
                            "The command or multi-line script to execute. "
                            "Commands are executed in sequence. "
                            "Example: 'ls -la' or 'cd /tmp && ls -la && pwd'"
                        )
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Target host to execute on. Options: "
                            "'default' (first available), hostname (specific host), "
                            "or '@all' (all hosts)."
                        ),
                        "default": "default"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            "Maximum time to wait for result in seconds. "
                            "If exceeded, command may still run in background."
                        ),
                        "default": 120
                    }
                },
                "required": ["script"]
            },
            "annotations": {
                "destructive": True,
                "idempotent": False
            }
        }

    @classmethod
    def get_tool_definition(cls) -> Dict[str, Any]:
        """
        DEPRECATED: Use get_mcp_tool_definition() instead.

        Legacy tool definition for backward compatibility.
        """
        return {
            "name": "run_shell_command",
            "description": (
                "Execute shell commands on registered remote hosts. "
                "Use this to run system commands, check server status, "
                "manage files, or execute scripts on remote machines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": (
                            "The command or multi-line script to execute. "
                            "Commands are executed in sequence. "
                            "Example: 'ls -la' or 'cd /tmp\\nls -la\\npwd'"
                        )
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "Target host to execute on. Options: "
                            "'default' (first available), hostname (specific host), "
                            "or '@all' (all hosts). Default: 'default'"
                        ),
                        "default": "default"
                    },
                    "timeout": {
                        "type": "integer",
                        "description": (
                            "Maximum time to wait for result in seconds. "
                            "Default: 120. If exceeded, command may still run in background."
                        ),
                        "default": 120
                    }
                },
                "required": ["script"]
            }
        }

    def is_tool_enabled(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if the run_shell_command tool should be exposed to the agent.

        Returns:
            True if tool should be available for AI/agentic use.
            False if only /shell slash command should work (programmatic mode).
        """
        config = config or getattr(self, '_config', {}) or {}
        execution_mode = config.get('execution_mode', self.execution_mode)

        # Support both old and new terminology
        # - "agentic" / "tool": Tool-only mode
        # - "hybrid": Both tool and slash command
        # - "programmatic" / "legacy": Slash command only
        return execution_mode in ('agentic', 'tool', 'hybrid')

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this skill can handle the given message.

        Handles:
        - /shell slash command
        - Keyword matches (if configured)
        - AI classification (if enabled)
        """
        if not message.body:
            return False

        body = message.body.strip()
        config = getattr(self, '_config', {}) or {}

        # Check for /shell slash command
        if config.get('enable_slash_command', True):
            if self.SHELL_COMMAND_PATTERN.match(body):
                logger.info("ShellSkill: Matched /shell slash command")
                return True

        # Check for keyword matches
        keywords = config.get('keywords', [])
        if keywords and self._keyword_matches(body, keywords):
            # Optional: Use AI to confirm intent
            if config.get('use_ai_fallback', False):
                return await self._ai_classify(body, config)
            return True

        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process a shell command request.

        Handles the /shell slash command. Supports two modes based on config:
        - wait_for_result=True (default): Wait for command output and return inline
        - wait_for_result=False: Fire-and-forget, use /inject to retrieve output later

        FIX (2026-01-30): Changed default to wait_for_result=True so slash commands
        return actual output inline in the chat.
        """
        body = message.body.strip()

        # Parse /shell command
        match = self.SHELL_COMMAND_PATTERN.match(body)
        if not match:
            return SkillResult(
                success=False,
                output="Invalid shell command format. Use: /shell [target:]<command>",
                metadata={"error": "parse_error"}
            )

        target = match.group('target') or config.get('default_target', 'default')
        command = match.group('command').strip()

        if not command:
            return SkillResult(
                success=False,
                output="No command specified. Use: /shell [target:]<command>",
                metadata={"error": "empty_command"}
            )

        # Get service
        service = self._get_service()
        if not service:
            return SkillResult(
                success=False,
                output="Shell service not available (database not configured)",
                metadata={"error": "service_unavailable"}
            )

        # Get agent and tenant info
        agent_id = getattr(self, '_agent_id', None)
        tenant_id = self._get_tenant_id(agent_id)

        if not tenant_id:
            return SkillResult(
                success=False,
                output="Could not determine tenant for shell command",
                metadata={"error": "no_tenant"}
            )

        # FIX (2026-01-30): Read wait_for_result from config, default to True
        # This allows users to toggle between synchronous (inline output) and
        # fire-and-forget modes via the Skill Configuration UI
        wait_for_result = config.get('wait_for_result', True)
        timeout_seconds = config.get('default_timeout', 120)

        # Execute command
        result = service.execute_command(
            script=command,
            target=target,
            tenant_id=tenant_id,
            initiated_by=f"user:{message.sender_key}",
            agent_id=agent_id,
            timeout_seconds=timeout_seconds,
            wait_for_result=wait_for_result
        )

        # Handle fire-and-forget mode
        if not wait_for_result:
            if result.success:
                output = f"✅ Command queued (ID: `{result.command_id}`)\n**Target:** {target}\n**Command:** `{command}`\n\n_Use `/inject list` to check results later._"
                return SkillResult(
                    success=True,
                    output=output,
                    metadata={
                        "command_id": result.command_id,
                        "target": target,
                        "command": command,
                        "mode": "fire_and_forget"
                    }
                )
            else:
                return SkillResult(
                    success=False,
                    output=f"❌ Failed to queue command: {result.error_message}",
                    metadata={
                        "error": result.error_message,
                        "status": result.status
                    }
                )

        # Handle synchronous mode (wait_for_result=True)
        if result.timed_out:
            return SkillResult(
                success=False,
                output=f"⏱️ Command timed out after {timeout_seconds}s (ID: `{result.command_id}`)\n\n_The beacon may still be processing. Use `/inject {result.command_id}` to check later._",
                metadata={
                    "command_id": result.command_id,
                    "status": "timeout",
                    "mode": "synchronous"
                }
            )

        if result.success:
            # Format successful output
            stdout = result.stdout or "(no output)"
            # Truncate very long output for chat display
            if len(stdout) > 4000:
                stdout = stdout[:4000] + "\n... (output truncated, full result in command history)"

            output = f"✅ **Command completed** (exit code: {result.exit_code})\n```\n{stdout}\n```"

            if result.stderr:
                stderr = result.stderr
                if len(stderr) > 500:
                    stderr = stderr[:500] + "... (truncated)"
                output += f"\n\n⚠️ **Stderr:**\n```\n{stderr}\n```"

            if result.execution_time_ms:
                output += f"\n\n⏱️ Execution time: {result.execution_time_ms}ms"

            return SkillResult(
                success=True,
                output=output,
                metadata={
                    "command_id": result.command_id,
                    "target": target,
                    "command": command,
                    "exit_code": result.exit_code,
                    "execution_time_ms": result.execution_time_ms,
                    "mode": "synchronous"
                }
            )
        else:
            # Format error output
            error_msg = result.error_message or result.stderr or "Unknown error"
            output = f"❌ **Command failed** (exit code: {result.exit_code})\n```\n{error_msg}\n```"

            return SkillResult(
                success=False,
                output=output,
                metadata={
                    "command_id": result.command_id,
                    "error": result.error_message,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "mode": "synchronous"
                }
            )

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute the run_shell_command tool.

        Called by the skill_manager when AI invokes the tool via skills-as-tools.

        Args:
            arguments: Parsed arguments from LLM tool call
                - script: Command or multi-line script to execute (required)
                - target: Target host ("default", hostname, or "@all")
                - timeout: Maximum wait time in seconds
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with execution output
        """
        # Extract arguments
        script = arguments.get('script', '')
        target = arguments.get('target', 'default')
        timeout = arguments.get('timeout', 120)

        # Ensure timeout is an integer
        if isinstance(timeout, str):
            try:
                timeout = int(timeout)
            except ValueError:
                timeout = 120

        if not script:
            return SkillResult(
                success=False,
                output="No script/command provided",
                metadata={"error": "missing_script"}
            )

        config = config or getattr(self, '_config', {}) or {}

        # Enforce max timeout
        max_timeout = config.get('max_timeout', 300)
        timeout = min(timeout, max_timeout)

        # Get service
        service = self._get_service()
        if not service:
            return SkillResult(
                success=False,
                output="Shell service not available (database not configured)",
                metadata={"error": "service_unavailable"}
            )

        # Get agent and tenant info
        agent_id = getattr(self, '_agent_id', None)
        tenant_id = self._get_tenant_id(agent_id)

        if not tenant_id:
            return SkillResult(
                success=False,
                output="Could not determine tenant for shell command",
                metadata={"error": "no_tenant"}
            )

        # Use default target if not specified
        if not target:
            target = config.get('default_target', 'default')

        # Execute with waiting
        result = service.execute_command(
            script=script,
            target=target,
            tenant_id=tenant_id,
            initiated_by=f"agent:{agent_id}",
            agent_id=agent_id,
            timeout_seconds=timeout,
            wait_for_result=config.get('wait_for_result', True)
        )

        # Convert CommandResult to SkillResult
        if result.success:
            output = f"✅ **Command executed successfully**"
            if result.stdout:
                stdout = result.stdout.strip()
                if len(stdout) > 2000:
                    stdout = stdout[:2000] + "... (truncated)"
                output += f"\n```\n{stdout}\n```"
            if result.stderr:
                stderr = result.stderr.strip()
                if len(stderr) > 500:
                    stderr = stderr[:500] + "... (truncated)"
                output += f"\n\n⚠️ **Stderr:**\n```\n{stderr}\n```"
            if result.execution_time_ms:
                output += f"\n\n⏱️ Execution time: {result.execution_time_ms}ms"

            return SkillResult(
                success=True,
                output=output,
                metadata={
                    "command_id": result.command_id,
                    "target": target,
                    "command": script,
                    "exit_code": result.exit_code,
                    "execution_time_ms": result.execution_time_ms,
                    "mode": "tool_execution"
                }
            )
        else:
            error_msg = result.error_message or result.stderr or "Unknown error"
            output = f"❌ **Command failed** (exit code: {result.exit_code})\n```\n{error_msg}\n```"

            return SkillResult(
                success=False,
                output=output,
                metadata={
                    "command_id": result.command_id,
                    "error": result.error_message,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "mode": "tool_execution"
                }
            )

    def _get_tenant_id(self, agent_id: Optional[int]) -> Optional[str]:
        """Get tenant ID from agent."""
        if not agent_id or not self._db_session:
            return None

        try:
            agent = self._db_session.query(Agent).filter(
                Agent.id == agent_id
            ).first()
            return agent.tenant_id if agent else None
        except Exception as e:
            logger.error(f"ShellSkill: Error getting tenant_id: {e}")
            return None

    def get_available_targets(self, config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get list of available shell targets.

        Useful for UI or agent to see what hosts are available.

        Returns:
            List of dicts with shell info:
            [{"id": 1, "hostname": "server-001", "is_online": True}, ...]
        """
        service = self._get_service()
        if not service:
            return []

        agent_id = getattr(self, '_agent_id', None)
        tenant_id = self._get_tenant_id(agent_id)

        if not tenant_id:
            return []

        shells = service.get_available_shells(tenant_id)

        return [
            {
                "id": shell.id,
                "name": shell.name,
                "hostname": shell.hostname,
                "is_online": shell.is_online,
                "mode": shell.mode,
                "last_checkin": shell.last_checkin.isoformat() if shell.last_checkin else None
            }
            for shell in shells
        ]

    def get_targets_os_context(self) -> str:
        """
        Get OS information for all available shell targets.

        This is used to inject OS context into the AI's system prompt
        so it generates OS-appropriate commands (e.g., `top -l 1` for
        macOS instead of `top -bn1` for Linux).

        Returns:
            Formatted string with OS details for each target, or empty string.
        """
        service = self._get_service()
        if not service:
            return ""

        agent_id = getattr(self, '_agent_id', None)
        tenant_id = self._get_tenant_id(agent_id)

        if not tenant_id:
            return ""

        return service.get_targets_os_context(tenant_id)
