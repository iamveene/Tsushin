"""
Automation Skill - Multi-step workflow automation

Competes with: Zapier, Make (Integromat), n8n, Power Automate

This skill provides workflow automation capabilities through the Flows engine.
It allows agents to execute, list, and manage multi-step automation workflows.

Capabilities:
- Execute flows on-demand
- List available workflows
- Query flow execution status
- Multi-step process orchestration

Does NOT handle:
- Simple calendar reminders (use SchedulerSkill/FlowsSkill)
- Meeting scheduling (use SchedulerSkill with Google Calendar)
- Task management (use SchedulerSkill with Asana)
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional
import logging
import json

logger = logging.getLogger(__name__)


class AutomationSkill(BaseSkill):
    """
    Automation Skill - Multi-step workflow automation.

    Directly integrates with the Flow Engine for workflow execution.
    No provider system needed - this is a standalone capability.

    Skills-as-Tools (Phase 4):
    - Tool name: manage_flows
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    - Actions: list, run, status
    """

    skill_type = "automation"
    skill_name = "Automation"
    skill_description = "Multi-step workflow automation and process orchestration"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self):
        """Initialize the automation skill."""
        super().__init__()
        self._flow_engine = None  # Lazy init when needed

    def _get_flow_engine(self):
        """Lazy initialization of flow engine."""
        if self._flow_engine is None and self._db_session is not None:
            from flows.flow_engine import FlowEngine
            self._flow_engine = FlowEngine(self._db_session)
        return self._flow_engine

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this skill should handle the message.

        Detects automation-related requests:
        - "run my workflow"
        - "execute the weekly report flow"
        - "show me my flows"
        - "list my automations"
        - "start the data sync workflow"
        - "trigger my automation"

        Args:
            message: The incoming message

        Returns:
            True if message is automation-related, False otherwise
        """
        # Check if skill is enabled in config
        if not self._config.get('is_enabled', True):
            return False

        body_lower = message.body.lower()

        # Automation keywords
        automation_keywords = [
            'workflow',
            'automation',
            'automate',
            'flow',
            'orchestration',
            'orchestrate',
            'process',
            'run flow',
            'execute flow',
            'start flow',
            'trigger flow',
            'list flow',
            'show flow',
            'my flows',
            'my automations',
            'my workflows'
        ]

        # Check for keyword matches
        for keyword in automation_keywords:
            if keyword in body_lower:
                logger.info(f"AutomationSkill: Matched keyword '{keyword}' in message")
                return True

        # Check for specific action patterns
        action_patterns = [
            'run the',
            'execute the',
            'start the',
            'trigger the',
            'show me the',
            'list my',
            'what are my'
        ]

        for pattern in action_patterns:
            if pattern in body_lower:
                # Check if followed by automation-related terms
                if any(term in body_lower for term in ['flow', 'workflow', 'automation']):
                    logger.info(f"AutomationSkill: Matched pattern '{pattern}' with automation term")
                    return True

        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process automation-related message.

        Detects intent and routes to appropriate handler:
        - LIST: Show available workflows
        - RUN: Execute a specific workflow
        - STATUS: Check flow execution status
        - HELP: Show automation help

        Args:
            message: The incoming message
            config: Skill configuration

        Returns:
            SkillResult with execution outcome
        """
        try:
            # Store config for use in methods
            self._config = config

            body_lower = message.body.lower()

            # Detect intent
            intent = self._detect_intent(body_lower)
            logger.info(f"AutomationSkill: Detected intent '{intent}'")

            # Route to appropriate handler
            if intent == 'list':
                return await self._handle_list(message, config)
            elif intent == 'run':
                return await self._handle_run(message, config)
            elif intent == 'status':
                return await self._handle_status(message, config)
            elif intent == 'help':
                return await self._handle_help(message, config)
            else:
                # Default to help for unclear requests
                return await self._handle_help(message, config)

        except Exception as e:
            logger.error(f"AutomationSkill: Error processing message: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error processing automation request: {str(e)}",
                metadata={"error": str(e)}
            )

    def _detect_intent(self, body_lower: str) -> str:
        """
        Detect the user's intent from the message.

        Args:
            body_lower: Lowercased message body

        Returns:
            Intent string: 'list', 'run', 'status', 'help'
        """
        # List intent
        list_keywords = ['list', 'show', 'what are', 'display', 'see my']
        if any(keyword in body_lower for keyword in list_keywords):
            return 'list'

        # Run intent
        run_keywords = ['run', 'execute', 'start', 'trigger', 'launch']
        if any(keyword in body_lower for keyword in run_keywords):
            return 'run'

        # Status intent
        status_keywords = ['status', 'check', 'progress', 'running', 'completed']
        if any(keyword in body_lower for keyword in status_keywords):
            return 'status'

        # Help intent
        help_keywords = ['help', 'how', 'what can', 'explain']
        if any(keyword in body_lower for keyword in help_keywords):
            return 'help'

        # Default to help
        return 'help'

    async def _handle_list(self, message: InboundMessage, config: Dict) -> SkillResult:
        """
        List available workflows.

        Uses FlowCommandService to retrieve and format flows.
        """
        try:
            from services.flow_command_service import FlowCommandService

            # Get tenant_id and agent_id from config
            tenant_id = config.get('tenant_id')
            agent_id = config.get('agent_id')

            if not tenant_id or not agent_id:
                return SkillResult(
                    success=False,
                    output="❌ Missing tenant or agent configuration",
                    metadata={}
                )

            service = FlowCommandService(self._db_session)
            result = await service.execute_list(tenant_id, agent_id)

            return SkillResult(
                success=result['status'] == 'success',
                output=result['message'],
                metadata=result.get('data', {})
            )

        except Exception as e:
            logger.error(f"AutomationSkill: Error listing flows: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error listing workflows: {str(e)}",
                metadata={"error": str(e)}
            )

    async def _handle_run(self, message: InboundMessage, config: Dict) -> SkillResult:
        """
        Execute a workflow.

        Extracts flow identifier from message and executes it.
        """
        try:
            from services.flow_command_service import FlowCommandService

            # Get tenant_id and agent_id from config
            tenant_id = config.get('tenant_id')
            agent_id = config.get('agent_id')
            sender_key = message.sender_key

            if not tenant_id or not agent_id:
                return SkillResult(
                    success=False,
                    output="❌ Missing tenant or agent configuration",
                    metadata={}
                )

            # Extract flow identifier from message
            flow_identifier = self._extract_flow_identifier(message.body)

            if not flow_identifier:
                return SkillResult(
                    success=False,
                    output="❌ Please specify which flow to run. Example: 'run flow 1' or 'execute my weekly report flow'",
                    metadata={}
                )

            service = FlowCommandService(self._db_session)
            result = await service.execute_run(tenant_id, agent_id, flow_identifier, sender_key)

            return SkillResult(
                success=result['status'] == 'success',
                output=result['message'],
                metadata=result.get('data', {})
            )

        except Exception as e:
            logger.error(f"AutomationSkill: Error running flow: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error executing workflow: {str(e)}",
                metadata={"error": str(e)}
            )

    def _extract_flow_identifier(self, body: str) -> Optional[str]:
        """
        Extract flow identifier (ID or name) from message.

        Examples:
        - "run flow 5" -> "5"
        - "execute my weekly report" -> "weekly report"
        - "start the data sync workflow" -> "data sync"

        Args:
            body: Message body

        Returns:
            Flow identifier or None
        """
        import re

        # Try to extract number after "flow", "id", etc.
        number_match = re.search(r'(?:flow|id|number)\s+(\d+)', body, re.IGNORECASE)
        if number_match:
            return number_match.group(1)

        # Try to extract quoted text
        quote_match = re.search(r'["\']([^"\']+)["\']', body)
        if quote_match:
            return quote_match.group(1)

        # Try to extract text after "the" or "my"
        the_match = re.search(r'(?:the|my)\s+([a-zA-Z0-9\s]+?)(?:\s+(?:flow|workflow|automation))?$', body, re.IGNORECASE)
        if the_match:
            return the_match.group(1).strip()

        # Try to extract text between action verb and "flow/workflow"
        action_match = re.search(r'(?:run|execute|start|trigger)\s+(?:the\s+)?([a-zA-Z0-9\s]+?)(?:\s+(?:flow|workflow|automation))', body, re.IGNORECASE)
        if action_match:
            return action_match.group(1).strip()

        return None

    async def _handle_status(self, message: InboundMessage, config: Dict) -> SkillResult:
        """
        Check flow execution status.

        Future enhancement - not implemented yet.
        """
        return SkillResult(
            success=True,
            output="ℹ️ Flow status checking is coming soon! Use the UI to check execution status.",
            metadata={}
        )

    async def _handle_help(self, message: InboundMessage, config: Dict) -> SkillResult:
        """
        Show automation help.
        """
        help_text = """
🤖 **Automation Skill Help**

I can help you manage workflow automations:

**List Workflows:**
- "list my flows"
- "show my automations"
- "what workflows do I have?"

**Run a Workflow:**
- "run flow 5"
- "execute my weekly report flow"
- "start the data sync workflow"

**Slash Commands:**
- `/flows list` - List all workflows
- `/flows run <id>` - Execute a specific workflow

Need more help? Check the documentation or use `/help automation`
        """.strip()

        return SkillResult(
            success=True,
            output=help_text,
            metadata={}
        )

    @staticmethod
    def get_default_config() -> Dict[str, Any]:
        """
        Get default configuration for this skill.

        Returns:
            Default configuration dict
        """
        return {
            "is_enabled": True,
            "allow_agentic_creation": False,  # Future: allow AI to create flows
            "require_confirmation": True,  # Future: require confirmation before execution
            "max_parallel_flows": 5  # Future: limit concurrent executions
        }

    @staticmethod
    def get_config_schema() -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration.

        Returns:
            JSON schema dict
        """
        return {
            "type": "object",
            "properties": {
                "is_enabled": {
                    "type": "boolean",
                    "title": "Enable Automation Skill",
                    "description": "Enable or disable automation capabilities",
                    "default": True
                },
                "allow_agentic_creation": {
                    "type": "boolean",
                    "title": "Allow AI Flow Creation",
                    "description": "Allow the AI to create new workflows from natural language (future feature)",
                    "default": False
                },
                "require_confirmation": {
                    "type": "boolean",
                    "title": "Require Confirmation",
                    "description": "Require user confirmation before executing workflows (future feature)",
                    "default": True
                },
                "max_parallel_flows": {
                    "type": "integer",
                    "title": "Max Parallel Flows",
                    "description": "Maximum number of flows that can run simultaneously",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20
                },
                "execution_mode": {
                    "type": "string",
                    "enum": ["tool", "legacy", "hybrid"],
                    "description": "Execution mode: tool (AI decides), legacy (keywords only), hybrid (both)",
                    "default": "hybrid"
                }
            }
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 4)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for flow/automation management.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "manage_flows",
            "title": "Flow Management",
            "description": (
                "Manage multi-step workflow automations. "
                "List available flows, execute workflows by ID or name, and check execution status."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["list", "run", "status"],
                        "description": "Action to perform: 'list' (show available flows), 'run' (execute a flow), 'status' (check execution status)"
                    },
                    "flow_identifier": {
                        "type": "string",
                        "description": "Flow ID (number) or name (for 'run' and 'status' actions)"
                    }
                },
                "required": ["action"]
            },
            "annotations": {
                "destructive": True,  # Can execute workflows that modify data
                "idempotent": False,
                "audience": ["user", "assistant"]
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Automation workflows can be powerful - monitor for suspicious patterns.
        """
        return {
            "expected_intents": [
                "List available workflow automations",
                "Execute a workflow by ID or name",
                "Check workflow execution status"
            ],
            "expected_patterns": [
                "workflow", "flow", "automation", "automate",
                "run", "execute", "start", "trigger",
                "list", "show", "status", "check"
            ],
            "risk_notes": (
                "Workflow execution can trigger multi-step processes with significant effects. "
                "Monitor for: unusual execution frequency, unexpected flow names, "
                "attempts to run flows the user hasn't previously used."
            )
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute flow management as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - action: 'list', 'run', or 'status' (required)
                - flow_identifier: Flow ID or name (for run/status)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with operation result
        """
        action = arguments.get("action")

        if not action:
            return SkillResult(
                success=False,
                output="Action is required. Use 'list', 'run', or 'status'.",
                metadata={"error": "missing_action", "skip_ai": True}
            )

        # Store config
        self._config = config

        logger.info(f"AutomationSkill.execute_tool: action={action}")

        try:
            if action == "list":
                return await self._execute_tool_list(message, config)
            elif action == "run":
                return await self._execute_tool_run(arguments, message, config)
            elif action == "status":
                return await self._execute_tool_status(arguments, message, config)
            else:
                return SkillResult(
                    success=False,
                    output=f"Unknown action: {action}. Use 'list', 'run', or 'status'.",
                    metadata={"error": "invalid_action", "skip_ai": True}
                )

        except Exception as e:
            logger.error(f"AutomationSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error executing automation: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    async def _execute_tool_list(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Execute list flows action for tool mode."""
        try:
            from services.flow_command_service import FlowCommandService

            tenant_id = config.get('tenant_id')
            agent_id = config.get('agent_id')

            if not tenant_id or not agent_id:
                return SkillResult(
                    success=False,
                    output="❌ Missing tenant or agent configuration",
                    metadata={"error": "missing_config", "skip_ai": True}
                )

            service = FlowCommandService(self._db_session)
            result = await service.execute_list(tenant_id, agent_id)

            return SkillResult(
                success=result['status'] == 'success',
                output=result['message'],
                metadata={**result.get('data', {}), "action": "list", "skip_ai": True}
            )

        except Exception as e:
            logger.error(f"AutomationSkill._execute_tool_list error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error listing workflows: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    async def _execute_tool_run(self, arguments: Dict[str, Any], message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Execute run flow action for tool mode."""
        try:
            from services.flow_command_service import FlowCommandService

            tenant_id = config.get('tenant_id')
            agent_id = config.get('agent_id')
            sender_key = message.sender_key

            if not tenant_id or not agent_id:
                return SkillResult(
                    success=False,
                    output="❌ Missing tenant or agent configuration",
                    metadata={"error": "missing_config", "skip_ai": True}
                )

            flow_identifier = arguments.get("flow_identifier")
            if not flow_identifier:
                return SkillResult(
                    success=False,
                    output="❌ Flow identifier is required. Specify the flow ID (number) or name.",
                    metadata={"error": "missing_flow_identifier", "skip_ai": True}
                )

            service = FlowCommandService(self._db_session)
            result = await service.execute_run(tenant_id, agent_id, flow_identifier, sender_key)

            return SkillResult(
                success=result['status'] == 'success',
                output=result['message'],
                metadata={**result.get('data', {}), "action": "run", "skip_ai": True}
            )

        except Exception as e:
            logger.error(f"AutomationSkill._execute_tool_run error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Error executing workflow: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )

    async def _execute_tool_status(self, arguments: Dict[str, Any], message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Execute status check action for tool mode."""
        # Status checking is not yet implemented
        return SkillResult(
            success=True,
            output="ℹ️ Flow status checking is coming soon! Use the UI to check execution status.",
            metadata={"action": "status", "skip_ai": True}
        )
