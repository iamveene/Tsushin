"""
Agent Switcher Skill - Allows users to switch their default agent for direct messages

Enables users to dynamically change which agent handles their DM conversations
by issuing natural language commands like "invoke agent <name>".

Features:
- Multilingual support (English, Portuguese, Spanish)
- Works via text or audio (transcription)
- DM-only (not applicable to group chats)
- Intelligent agent name resolution
- Helpful error messages with agent suggestions
"""

from .base import BaseSkill, InboundMessage, SkillResult
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from models import Contact, Agent, ContactAgentMapping, UserAgentSession
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentSwitcherSkill(BaseSkill):
    """
    Skill for switching the user's default agent in direct message conversations.

    Trigger commands (natural language only, not slash commands):
    - English: "invoke agent <name>", "invoke <name>"
    - Portuguese: "invocar agente <nome>", "invocar <nome>"

    Skills-as-Tools (Phase 2):
    - Tool name: switch_agent
    - Execution mode: hybrid (supports both tool and legacy keyword modes)
    """

    skill_type = "agent_switcher"
    skill_name = "Agent Switcher"
    skill_description = "Allows users to switch their default agent for direct messages via natural language commands"
    execution_mode = "hybrid"  # Support both tool and legacy modes

    def __init__(self):
        super().__init__()
        self.db_session: Optional[Session] = None

    def set_db_session(self, db: Session):
        """Inject database session for DB operations"""
        # Set parent's _db_session for AI classification
        super().set_db_session(db)
        # Also set our own db_session for convenience
        self.db_session = db

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Check if this message is an agent switching request.

        Phase 7.1.2: Uses configurable keywords + AI fallback approach.

        Requirements:
        1. Must be a direct message (not group)
        2. Must NOT start with "/" (those are slash commands only)
        3. Must contain configured keywords (pre-filter)
        4. If AI fallback enabled, verify intent with AI

        Args:
            message: Inbound message to evaluate

        Returns:
            True if this is an agent switching request
        """
        # Skills-as-Tools: If in tool-only mode, don't handle via keywords
        config = self._config or self.get_default_config()
        if not self.is_legacy_enabled(config):
            return False

        # Only handle direct messages
        if message.is_group:
            logger.debug(f"AgentSwitcherSkill: Ignoring group message")
            return False

        # Don't handle slash commands - those are for the slash command system
        if message.body.strip().startswith("/"):
            logger.debug(f"AgentSwitcherSkill: Ignoring slash command")
            return False

        keywords = config.get("keywords", self.get_default_config()["keywords"])
        use_ai_fallback = config.get("use_ai_fallback", True)

        # Step 1: Keyword pre-filter (fast, free)
        if not self._keyword_matches(message.body, keywords):
            logger.debug(f"AgentSwitcherSkill: No keyword match in '{message.body[:50]}...'")
            return False

        logger.info(f"AgentSwitcherSkill: Keywords matched in '{message.body[:50]}...'")

        # Step 2: AI fallback (optional, for intent verification)
        if use_ai_fallback:
            result = await self._ai_classify(message.body, config)
            logger.info(f"AgentSwitcherSkill: AI classification result={result}")
            return result

        # Keywords matched, no AI verification needed
        return True

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process the agent switching request.

        Steps:
        1. Extract target agent name from message
        2. Resolve agent name to Agent ID
        3. Identify the requesting user (contact)
        4. Update/Create ContactAgentMapping
        5. Return confirmation

        Args:
            message: The agent switching request message
            config: Skill configuration (unused for this skill)

        Returns:
            SkillResult with success status and confirmation message
        """
        try:
            if not self.db_session:
                raise RuntimeError("Database session not initialized. Call set_db_session() first.")

            # Step 1: Extract agent name from message using AI
            available_agents = self._get_available_agents()
            agent_names = [a.friendly_name for a in available_agents]

            from agent.skills.ai_classifier import get_classifier
            classifier = get_classifier()
            ai_model = config.get("ai_model", "gemini-2.5-flash")

            agent_name = await classifier.extract_entity(
                message=message.body,
                entity_type="agent name",
                available_options=agent_names,
                model=ai_model,
                db=self.db_session  # Phase 7.4: Pass db for API key loading
            )

            if not agent_name:
                agent_list = "\n".join([f"  • {a.friendly_name}" for a in available_agents])
                return SkillResult(
                    success=False,
                    output="❌ Could not identify which agent to switch to. Please specify the agent name.\n\n"
                           f"Available agents:\n{agent_list}\n\n"
                           "Example: 'Invoke agent Tsushin' or 'Invocar agente Agendador'",
                    metadata={"error": "agent_name_not_found", "skip_ai": True}
                )

            logger.info(f"AgentSwitcherSkill: Extracted agent name: '{agent_name}'")

            # Step 2: Resolve agent name to Agent ID
            target_agent = self._find_agent_by_name(agent_name)
            if not target_agent:
                # Agent not found - provide helpful suggestions
                available_agents = self._get_available_agents()
                agent_list = "\n".join([f"  • {a.friendly_name}" for a in available_agents])

                return SkillResult(
                    success=False,
                    output=f"❌ Agent '{agent_name}' not found.\n\n"
                           f"Available agents:\n{agent_list}\n\n"
                           f"Please try again with one of these names.",
                    metadata={"error": "agent_not_found", "requested_agent": agent_name, "skip_ai": True}
                )

            if not target_agent.is_active:
                return SkillResult(
                    success=False,
                    output=f"❌ Agent '{agent_name}' is currently inactive and cannot be assigned.",
                    metadata={"error": "agent_inactive", "agent_id": target_agent.id, "skip_ai": True}
                )

            logger.info(f"AgentSwitcherSkill: Resolved to Agent ID: {target_agent.id}")

            # Step 3: Identify the requesting user
            sender_contact = self._identify_sender(message.sender)
            if not sender_contact:
                # Contact not found - create error message
                return SkillResult(
                    success=False,
                    output="❌ Could not identify your contact profile. Please ensure you're registered in the system.",
                    metadata={"error": "contact_not_found", "sender": message.sender, "skip_ai": True}
                )

            logger.info(f"AgentSwitcherSkill: Identified sender: {sender_contact.friendly_name} (ID: {sender_contact.id})")

            # Step 4: Update/Create ContactAgentMapping
            self._update_agent_mapping(sender_contact.id, target_agent.id)

            # Phase 7.3: Save UserAgentSession for persistence across messages
            self._save_user_agent_session(message.sender_key, target_agent.id)

            # Step 5: Get agent's friendly name for confirmation
            agent_contact = self.db_session.query(Contact).filter(
                Contact.id == target_agent.contact_id
            ).first()
            agent_display_name = agent_contact.friendly_name if agent_contact else f"Agent {target_agent.id}"

            # Success!
            return SkillResult(
                success=True,
                output=f"✅ Successfully switched to agent **{agent_display_name}**.\n\n"
                       f"All your future direct messages will be handled by {agent_display_name}.",
                metadata={
                    "previous_agent_id": self._get_current_agent_id(sender_contact.id),
                    "new_agent_id": target_agent.id,
                    "contact_id": sender_contact.id,
                    "agent_name": agent_display_name,
                    "skip_ai": True  # Return skill output directly without AI processing
                }
            )

        except Exception as e:
            logger.error(f"AgentSwitcherSkill: Error processing request: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ An error occurred while switching agents: {str(e)}",
                metadata={"error": "processing_error", "exception": str(e), "skip_ai": True}
            )

    # Phase 7.1.2: Removed _extract_agent_name (now using AI extraction in process method)

    def _find_agent_by_name(self, agent_name: str) -> Optional[Agent]:
        """
        Find an agent by their friendly name (case-insensitive).

        Searches the Contact table for agents with matching friendly_name.

        Args:
            agent_name: The friendly name to search for

        Returns:
            Agent object if found, None otherwise
        """
        # Search contacts with role="agent" (case-insensitive)
        contact = self.db_session.query(Contact).filter(
            Contact.role == "agent",
            Contact.is_active == True,
            Contact.friendly_name.ilike(agent_name)  # Case-insensitive LIKE
        ).first()

        if not contact:
            return None

        # Find the corresponding Agent record
        agent = self.db_session.query(Agent).filter(
            Agent.contact_id == contact.id
        ).first()

        return agent

    def _get_available_agents(self) -> List[Contact]:
        """
        Get list of all available (active) agent contacts.

        Returns:
            List of Contact objects with role="agent" and is_active=True
        """
        return self.db_session.query(Contact).filter(
            Contact.role == "agent",
            Contact.is_active == True
        ).all()

    def _identify_sender(self, sender: str) -> Optional[Contact]:
        """
        Identify the sender's contact record.

        Searches by phone number (with or without + prefix).

        Args:
            sender: Phone number from message

        Returns:
            Contact object if found, None otherwise
        """
        # Normalize sender (remove + prefix if present)
        sender_normalized = sender.lstrip("+")

        # Search by phone number
        contact = self.db_session.query(Contact).filter(
            Contact.is_active == True,
            Contact.phone_number.like(f"%{sender_normalized}")
        ).first()

        return contact

    def _get_current_agent_id(self, contact_id: int) -> Optional[int]:
        """
        Get the current agent ID for a contact (if mapped).

        Args:
            contact_id: Contact ID to lookup

        Returns:
            Agent ID if mapped, None otherwise
        """
        mapping = self.db_session.query(ContactAgentMapping).filter(
            ContactAgentMapping.contact_id == contact_id
        ).first()

        return mapping.agent_id if mapping else None

    def _update_agent_mapping(self, contact_id: int, agent_id: int):
        """
        Update or create the ContactAgentMapping for the user.

        If mapping exists, updates agent_id and updated_at.
        If not, creates new mapping.

        Args:
            contact_id: User's contact ID
            agent_id: Target agent ID
        """
        # Check if mapping exists
        mapping = self.db_session.query(ContactAgentMapping).filter(
            ContactAgentMapping.contact_id == contact_id
        ).first()

        if mapping:
            # Update existing mapping
            logger.info(f"AgentSwitcherSkill: Updating mapping {mapping.id} - Agent {mapping.agent_id} → {agent_id}")
            mapping.agent_id = agent_id
            mapping.updated_at = datetime.utcnow()
        else:
            # Create new mapping
            logger.info(f"AgentSwitcherSkill: Creating new mapping - Contact {contact_id} → Agent {agent_id}")
            mapping = ContactAgentMapping(
                contact_id=contact_id,
                agent_id=agent_id,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            self.db_session.add(mapping)

        # Commit changes
        self.db_session.commit()
        logger.info(f"AgentSwitcherSkill: Mapping updated successfully")

    def _save_user_agent_session(self, user_identifier: str, agent_id: int):
        """
        Save user's agent preference to UserAgentSession table for persistence.

        Phase 7.3: This ensures agent switches persist across messages.

        Args:
            user_identifier: User's sender key (phone or chat_id)
            agent_id: Target agent ID
        """
        try:
            # Check if session exists
            session = self.db_session.query(UserAgentSession).filter(
                UserAgentSession.user_identifier == user_identifier
            ).first()

            if session:
                # Update existing session
                logger.info(f"AgentSwitcherSkill: Updating UserAgentSession - Agent {session.agent_id} → {agent_id}")
                session.agent_id = agent_id
                session.updated_at = datetime.utcnow()
            else:
                # Create new session
                logger.info(f"AgentSwitcherSkill: Creating new UserAgentSession - {user_identifier} → Agent {agent_id}")
                session = UserAgentSession(
                    user_identifier=user_identifier,
                    agent_id=agent_id
                )
                self.db_session.add(session)

            # Commit changes
            self.db_session.commit()
            logger.info(f"AgentSwitcherSkill: UserAgentSession saved successfully")

        except Exception as e:
            logger.error(f"AgentSwitcherSkill: Failed to save UserAgentSession: {e}", exc_info=True)
            self.db_session.rollback()

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for Agent Switcher skill.

        Phase 7.1.2: Simplified keywords to avoid confusion with slash commands.
        The AI will verify the full context to ensure it's an agent switch request.

        Supported trigger words:
        - English: invoke
        - Portuguese: invocar
        """
        return {
            "keywords": [
                # English
                "invoke",   # invoke
                # Portuguese
                "invocar",  # invoke
            ],
            "use_ai_fallback": True,
            "ai_model": "gemini-2.5-flash-lite"
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration.

        Phase 7.1.2: Inherits base schema (keywords, use_ai_fallback, ai_model).
        """
        base_schema = super().get_config_schema()
        # Add execution_mode to schema
        base_schema["properties"]["execution_mode"] = {
            "type": "string",
            "enum": ["tool", "legacy", "hybrid"],
            "description": "Execution mode: tool (AI decides), legacy (keywords only), hybrid (both)",
            "default": "hybrid"
        }
        return base_schema

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Phase 2)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Dict[str, Any]:
        """
        Return MCP-compliant tool definition for agent switching.

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools
        """
        return {
            "name": "switch_agent",
            "title": "Agent Switcher",
            "description": (
                "Switch the user's default agent for direct message conversations. "
                "Use when user wants to invoke, switch to, or change their active agent."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent to switch to (e.g., 'Tsushin', 'Agendador')"
                    }
                },
                "required": ["agent_name"]
            },
            "annotations": {
                "destructive": False,
                "idempotent": True,
                "audience": ["user"]  # Only for user-initiated actions
            }
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Agent switching is a user-initiated action that modifies
        their own preferences, so it's generally low-risk.
        """
        return {
            "expected_intents": [
                "Switch to a different agent",
                "Change active agent for conversations",
                "Invoke a specific agent"
            ],
            "expected_patterns": [
                "invoke", "invocar", "switch", "change agent", "use agent"
            ],
            "risk_notes": None  # Agent switching is low-risk
        }

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute agent switch as a tool call.

        Called by the agent's tool execution loop when AI invokes the tool.

        Args:
            arguments: Parsed arguments from LLM tool call
                - agent_name: Name of the agent to switch to (required)
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with switch confirmation
        """
        agent_name = arguments.get("agent_name")

        if not agent_name:
            return SkillResult(
                success=False,
                output="Agent name is required",
                metadata={"error": "missing_agent_name", "skip_ai": True}
            )

        # Only allow switching in direct messages
        if message.is_group:
            return SkillResult(
                success=False,
                output="Agent switching is only available in direct messages, not group chats.",
                metadata={"error": "group_not_supported", "skip_ai": True}
            )

        try:
            logger.info(f"AgentSwitcherSkill.execute_tool: agent_name='{agent_name}'")

            if not self.db_session:
                raise RuntimeError("Database session not initialized. Call set_db_session() first.")

            # Step 1: Find the target agent
            target_agent = self._find_agent_by_name(agent_name)

            if not target_agent:
                # Agent not found - provide helpful suggestions
                available_agents = self._get_available_agents()
                agent_list = "\n".join([f"  • {a.friendly_name}" for a in available_agents])

                return SkillResult(
                    success=False,
                    output=f"Agent '{agent_name}' not found.\n\nAvailable agents:\n{agent_list}",
                    metadata={"error": "agent_not_found", "requested_agent": agent_name, "skip_ai": True}
                )

            if not target_agent.is_active:
                return SkillResult(
                    success=False,
                    output=f"Agent '{agent_name}' is currently inactive and cannot be assigned.",
                    metadata={"error": "agent_inactive", "agent_id": target_agent.id, "skip_ai": True}
                )

            # Step 2: Identify the requesting user
            sender_contact = self._identify_sender(message.sender)
            if not sender_contact:
                return SkillResult(
                    success=False,
                    output="Could not identify your contact profile. Please ensure you're registered in the system.",
                    metadata={"error": "contact_not_found", "sender": message.sender, "skip_ai": True}
                )

            # Step 3: Update agent mapping
            previous_agent_id = self._get_current_agent_id(sender_contact.id)
            self._update_agent_mapping(sender_contact.id, target_agent.id)

            # Step 4: Save UserAgentSession for persistence
            self._save_user_agent_session(message.sender_key, target_agent.id)

            # Step 5: Get agent's friendly name for confirmation
            agent_contact = self.db_session.query(Contact).filter(
                Contact.id == target_agent.contact_id
            ).first()
            agent_display_name = agent_contact.friendly_name if agent_contact else f"Agent {target_agent.id}"

            return SkillResult(
                success=True,
                output=f"Successfully switched to agent **{agent_display_name}**.\n\nAll your future direct messages will be handled by {agent_display_name}.",
                metadata={
                    "previous_agent_id": previous_agent_id,
                    "new_agent_id": target_agent.id,
                    "contact_id": sender_contact.id,
                    "agent_name": agent_display_name,
                    "skip_ai": True
                }
            )

        except Exception as e:
            logger.error(f"AgentSwitcherSkill.execute_tool error: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"Error switching agents: {str(e)}",
                metadata={"error": str(e), "skip_ai": True}
            )
