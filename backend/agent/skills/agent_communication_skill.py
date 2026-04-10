"""
Agent Communication Skill (v0.6.0 Item 15)

Exposes inter-agent communication as an LLM tool so agents can:
- Ask another agent a question and get a response
- List available agents they can communicate with
- Delegate a task entirely to another agent

Follows the BaseSkill / Skills-as-Tools pattern.
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func
import logging
import re

logger = logging.getLogger(__name__)


class AgentCommunicationSkill(BaseSkill):
    """
    Skill for inter-agent communication.

    Execution mode: tool (LLM decides when to invoke, no keyword triggers).
    """

    skill_type = "agent_communication"
    skill_name = "Agent Communication"
    skill_description = "Ask other agents questions, discover available agents, or delegate tasks"
    execution_mode = "tool"

    def __init__(self):
        super().__init__()
        self.db_session: Optional[Session] = None

    def set_db_session(self, db: Session):
        super().set_db_session(db)
        self.db_session = db

    async def can_handle(self, message: InboundMessage) -> bool:
        """Tool-only skill — never handles messages via keyword detection."""
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """Not used — tool-only execution via execute_tool()."""
        return SkillResult(
            success=False,
            output="Agent communication is only available as a tool call.",
            metadata={"skip_ai": True},
        )

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "keywords": [],
            "use_ai_fallback": False,
            "ai_model": "gemini-2.5-flash-lite",
            "default_timeout": 60,
            "default_max_depth": 3,
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "default_timeout": {
                    "type": "integer",
                    "description": "Default timeout in seconds for inter-agent communication",
                    "default": 60,
                    "minimum": 5,
                    "maximum": 120,
                },
                "default_max_depth": {
                    "type": "integer",
                    "description": "Maximum delegation chain depth",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 5,
                },
            },
            "required": [],
        }

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """Return MCP-compliant tool definition for agent communication."""
        return {
            "name": "agent_communication",
            "title": "Agent Communication",
            "description": (
                "Communicate with other agents. Use 'ask' to send a question and get a response, "
                "'list_agents' to discover available agents you can communicate with, "
                "or 'delegate' to hand off a task entirely to another agent."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["ask", "list_agents", "delegate"],
                        "description": (
                            "'ask' = send a question to another agent and get their response, "
                            "'list_agents' = discover available agents with their capabilities, "
                            "'delegate' = fully hand off to another agent (their response goes directly to user)"
                        ),
                    },
                    "target_agent_name": {
                        "type": "string",
                        "description": "Name of the agent to communicate with (required for 'ask' and 'delegate')",
                    },
                    "message": {
                        "type": "string",
                        "description": "Message to send to the target agent (required for 'ask' and 'delegate')",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional context to pass to the target agent (e.g., conversation summary)",
                    },
                },
                "required": ["action"],
            },
            "annotations": {
                "destructive": False,
                "idempotent": False,
                "audience": ["user", "agent"],
            },
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        return {
            "expected_intents": [
                "Ask another agent for information or help",
                "List available agents and their capabilities",
                "Delegate a task to a specialized agent",
            ],
            "expected_patterns": [
                "ask agent", "delegate to", "let me check with",
                "pergunte ao agente", "delegue para", "consulte o agente",
            ],
            "risk_notes": "Monitor for privilege escalation through inter-agent delegation chains.",
        }

    @classmethod
    def get_sentinel_exemptions(cls) -> list:
        return ["agent_escalation"]

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any],
    ) -> SkillResult:
        """Execute agent communication as a tool call."""
        action = arguments.get("action")

        if not self.db_session:
            return SkillResult(
                success=False,
                output="Database session not available for agent communication.",
                metadata={"error": "no_db_session", "skip_ai": False},
            )

        # Resolve tenant_id and agent_id from config (set by skill_manager.execute_tool_call)
        tenant_id = config.get("tenant_id")
        agent_id = self._agent_id

        if not agent_id or not tenant_id:
            return SkillResult(
                success=False,
                output="Agent ID or tenant ID not available.",
                metadata={"error": "missing_context", "skip_ai": False},
            )

        if action == "list_agents":
            promoted = await self._promote_list_request(arguments, message, config, agent_id, tenant_id)
            if promoted is not None:
                return promoted

        if action == "list_agents":
            return await self._handle_list_agents(agent_id, tenant_id)
        elif action == "ask":
            return await self._handle_ask(arguments, message, config, agent_id, tenant_id)
        elif action == "delegate":
            return await self._handle_delegate(arguments, message, config, agent_id, tenant_id)
        else:
            return SkillResult(
                success=False,
                output=f"Unknown action: {action}. Use 'ask', 'list_agents', or 'delegate'.",
                metadata={"error": "unknown_action", "skip_ai": False},
            )

    async def _handle_list_agents(self, agent_id: int, tenant_id: str) -> SkillResult:
        """List available agents for communication."""
        from services.agent_communication_service import AgentCommunicationService

        svc = AgentCommunicationService(self.db_session, tenant_id, self._token_tracker)
        agents = svc.discover_agents(agent_id)

        if not agents:
            return SkillResult(
                success=True,
                output="No agents are currently available for communication. An administrator needs to set up communication permissions first.",
                metadata={"agents_count": 0, "skip_ai": False},
            )

        lines = ["Available agents for communication:\n"]
        for a in agents:
            status = "active" if a.is_available else "inactive"
            caps = ", ".join(a.capabilities) if a.capabilities else "none"
            lines.append(f"- **{a.agent_name}** (ID: {a.agent_id}, {status})")
            lines.append(f"  Capabilities: {caps}")
            if a.description:
                lines.append(f"  Description: {a.description[:100]}")
            lines.append("")

        return SkillResult(
            success=True,
            output="\n".join(lines),
            metadata={"agents_count": len(agents), "skip_ai": False},
        )

    async def _handle_ask(self, arguments: Dict, message: InboundMessage, config: Dict, agent_id: int, tenant_id: str) -> SkillResult:
        """Ask another agent a question and return their response."""
        target_name = arguments.get("target_agent_name")
        msg_text = arguments.get("message")
        context = arguments.get("context")

        if not target_name:
            return SkillResult(
                success=False,
                output="Please specify the target agent name.",
                metadata={"error": "missing_target", "skip_ai": False},
            )
        if not msg_text:
            return SkillResult(
                success=False,
                output="Please specify the message to send.",
                metadata={"error": "missing_message", "skip_ai": False},
            )

        target_agent = self._resolve_agent_by_name(target_name, tenant_id)
        if not target_agent:
            return SkillResult(
                success=False,
                output=f"Agent '{target_name}' not found. Use the 'list_agents' action to see available agents.",
                metadata={"error": "agent_not_found", "skip_ai": False},
            )

        from services.agent_communication_service import AgentCommunicationService
        svc = AgentCommunicationService(self.db_session, tenant_id, self._token_tracker)

        # Forward depth/parent_session_id to prevent infinite recursion
        current_depth = config.get("comm_depth", 0)
        parent_session_id = config.get("comm_parent_session_id")

        result = await svc.send_message(
            source_agent_id=agent_id,
            target_agent_id=target_agent.id,
            message=msg_text,
            context=context,
            original_sender_key=message.sender_key,
            original_message_preview=message.body[:200],
            session_type="ask",
            timeout=config.get("default_timeout", 60),
            depth=current_depth + 1,
            parent_session_id=parent_session_id,
        )

        if not result.success:
            return SkillResult(
                success=False,
                output=f"Communication failed: {result.error}",
                metadata={"error": "comm_failed", "session_id": result.session_id, "skip_ai": False},
            )

        return SkillResult(
            success=True,
            output=f"Response from {result.from_agent_name}:\n\n{result.response_text}",
            metadata={
                "session_id": result.session_id,
                "from_agent_id": result.from_agent_id,
                "from_agent_name": result.from_agent_name,
                "execution_time_ms": result.execution_time_ms,
                "skip_ai": False,  # Let the calling agent incorporate this response
            },
        )

    async def _handle_delegate(self, arguments: Dict, message: InboundMessage, config: Dict, agent_id: int, tenant_id: str) -> SkillResult:
        """Delegate a task entirely to another agent (response goes directly to user)."""
        target_name = arguments.get("target_agent_name")
        msg_text = arguments.get("message")
        context = arguments.get("context")

        if not target_name:
            return SkillResult(
                success=False,
                output="Please specify the target agent name.",
                metadata={"error": "missing_target", "skip_ai": True},
            )
        if not msg_text:
            return SkillResult(
                success=False,
                output="Please specify the message to send.",
                metadata={"error": "missing_message", "skip_ai": True},
            )

        target_agent = self._resolve_agent_by_name(target_name, tenant_id)
        if not target_agent:
            return SkillResult(
                success=False,
                output=f"Agent '{target_name}' not found.",
                metadata={"error": "agent_not_found", "skip_ai": True},
            )

        from services.agent_communication_service import AgentCommunicationService
        svc = AgentCommunicationService(self.db_session, tenant_id, self._token_tracker)

        # Forward depth/parent_session_id to prevent infinite recursion
        current_depth = config.get("comm_depth", 0)
        parent_session_id = config.get("comm_parent_session_id")

        result = await svc.send_message(
            source_agent_id=agent_id,
            target_agent_id=target_agent.id,
            message=msg_text,
            context=context,
            original_sender_key=message.sender_key,
            original_message_preview=message.body[:200],
            session_type="delegate",
            timeout=config.get("default_timeout", 60),
            depth=current_depth + 1,
            parent_session_id=parent_session_id,
        )

        if not result.success:
            return SkillResult(
                success=False,
                output=f"Delegation failed: {result.error}",
                metadata={"error": "delegation_failed", "skip_ai": True},
            )

        # skip_ai=True means the delegation target's response goes directly to user
        return SkillResult(
            success=True,
            output=result.response_text or "",
            metadata={
                "session_id": result.session_id,
                "from_agent_id": result.from_agent_id,
                "from_agent_name": result.from_agent_name,
                "delegation": True,
                "skip_ai": True,
            },
        )

    async def _promote_list_request(
        self,
        arguments: Dict[str, Any],
        message: Optional[InboundMessage],
        config: Dict[str, Any],
        agent_id: int,
        tenant_id: str,
    ) -> Optional[SkillResult]:
        intent = self._infer_direct_action(arguments, message)
        if not intent:
            return None

        target_name = arguments.get("target_agent_name") or self._infer_target_agent_name(
            message.body if message else "",
            agent_id,
            tenant_id,
        )
        if not target_name:
            return None

        delegated_message = arguments.get("message") or (message.body.strip() if message and message.body else None)
        if not delegated_message:
            return None

        promoted_arguments = {
            **arguments,
            "action": intent,
            "target_agent_name": target_name,
            "message": delegated_message,
        }

        logger.info(
            "Promoting agent_communication list_agents call to %s for agent '%s'",
            intent,
            target_name,
        )

        if intent == "delegate":
            return await self._handle_delegate(promoted_arguments, message, config, agent_id, tenant_id)
        return await self._handle_ask(promoted_arguments, message, config, agent_id, tenant_id)

    def _infer_direct_action(
        self,
        arguments: Dict[str, Any],
        message: Optional[InboundMessage],
    ) -> Optional[str]:
        body = (message.body if message else "") or ""
        target_name = arguments.get("target_agent_name")
        delegated_message = arguments.get("message")

        lowered = body.lower()
        delegate_patterns = (
            "delegate",
            "delegat",
            "hand off",
            "handoff",
            "pass this to",
            "route this to",
            "assign this to",
            "delegue",
            "delegar",
        )
        ask_patterns = (
            "ask",
            "question for",
            "check with",
            "consult",
            "pergunte",
            "consulte",
        )

        if target_name and delegated_message:
            if any(pattern in lowered for pattern in delegate_patterns):
                return "delegate"
            return "ask"

        if any(pattern in lowered for pattern in delegate_patterns):
            return "delegate"
        if any(pattern in lowered for pattern in ask_patterns):
            return "ask"
        return None

    def _infer_target_agent_name(
        self,
        body: str,
        agent_id: int,
        tenant_id: str,
    ) -> Optional[str]:
        if not body:
            return None

        from services.agent_communication_service import AgentCommunicationService

        svc = AgentCommunicationService(self.db_session, tenant_id, self._token_tracker)
        available_agents = svc.discover_agents(agent_id)
        body_lower = body.lower()

        matches = [
            info.agent_name
            for info in available_agents
            if info.agent_name and re.search(rf"\b{re.escape(info.agent_name.lower())}\b", body_lower)
        ]
        if len(matches) == 1:
            return matches[0]
        return None

    def _resolve_agent_by_name(self, name: str, tenant_id: str):
        """Resolve an agent by friendly name (exact case-insensitive match).
        Uses func.lower() equality to prevent SQL wildcard injection."""
        from models import Contact, Agent

        clean_name = name.strip().lower()

        contact = (
            self.db_session.query(Contact)
            .filter(
                Contact.role == "agent",
                Contact.is_active == True,
                func.lower(Contact.friendly_name) == clean_name,
                Contact.tenant_id == tenant_id,
            )
            .first()
        )
        if not contact:
            return None

        agent = (
            self.db_session.query(Agent)
            .filter(
                Agent.contact_id == contact.id,
                Agent.tenant_id == tenant_id,
                Agent.is_active == True,
            )
            .first()
        )
        return agent
