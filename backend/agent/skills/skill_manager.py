"""
Phase 5.0 Skills System - Skill Manager
Central registry and executor for agent skills.
"""

from typing import Dict, List, Type, Optional, TYPE_CHECKING, Any, Tuple, Union
from sqlalchemy.orm import Session
import logging

from models import AgentSkill
from agent.skills.base import BaseSkill, InboundMessage, SkillResult
# Phase 8: Watcher Activity Events
from services.watcher_activity_service import emit_skill_used_async

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class SkillManager:
    """
    Central manager for agent skills.

    Responsibilities:
    - Register skill types (audio_transcript, audio_response, etc.)
    - Discover which skills are enabled for an agent
    - Execute skills in priority order
    - Handle skill failures gracefully
    - Pass token tracker to skills for Phase 7.2 analytics
    """

    def __init__(self, token_tracker: Optional["TokenTracker"] = None):
        """
        Initialize the skill manager with empty registry.

        Args:
            token_tracker: TokenTracker instance for Phase 7.2 analytics (optional)
        """
        self.registry: Dict[str, Type[BaseSkill]] = {}
        self.token_tracker = token_tracker  # Phase 7.2: Store for passing to skills
        self._register_builtin_skills()
        logger.info(f"SkillManager initialized with {len(self.registry)} registered skills")

    # Reserved config keys that should stay out of per-skill AgentSkill.config
    # payloads. Track A will eventually thread scratchpad/queue-style metadata
    # through a separate contract; this audit surface is intentionally
    # observational only for now.
    RESERVED_AGENT_SKILL_CONFIG_KEYS = frozenset({
        "execution_mode",
        "keywords",
        "use_ai_fallback",
        "ai_model",
        "scratchpad",
        "queue",
        "max_agentic_rounds",
        "auto_inject_results",
        "skip_ai_on_data_fetch",
        "max_result_bytes",
        "max_results_retained",
        "max_turns_lookback",
    })

    def _register_builtin_skills(self):
        """
        Register built-in skills.

        Phase 5.0 Week 3: Audio transcription (Whisper)
        Phase 6.4 Week 5: Scheduler skills
        Task 3: Knowledge sharing skill
        Phase 5.5: Asana skill
        Agent Switcher: DM agent switching
        Phase 7.3: Audio TTS response

        API Tools Migration: Migrated API Tools to Skills system:
        - SearchSkill (web_search) - replaces google_search tool
        - (web_scraping removed — functionality merged into search skill)
        """
        try:
            # Note: Asana is now a provider for the Scheduler skill (not standalone)
            # Asana tasks are accessed through FlowsSkill with asana provider

            # Flight Search Skill (Provider-based architecture)
            from agent.skills.flight_search_skill import FlightSearchSkill
            self.register_skill(FlightSearchSkill)

            # API Tools Migration: Web Search
            from agent.skills.search_skill import SearchSkill
            self.register_skill(SearchSkill)

            # Import audio transcription skill
            from agent.skills.audio_transcript import AudioTranscriptSkill
            self.register_skill(AudioTranscriptSkill)

            # Phase 7.3: Import audio TTS response skill
            from agent.skills.audio_tts_skill import AudioTTSSkill
            self.register_skill(AudioTTSSkill)

            # Scheduler skill abstraction. FlowsSkill is the provider-aware
            # implementation that dispatches to Flows (built-in), Google
            # Calendar, or Asana based on AgentSkillIntegration.scheduler_provider.
            # Registered under BOTH "scheduler" (canonical abstraction name used
            # by integration wizards, flow templates, and the Flows page
            # dropdown) and "flows" (alias used by some DB rows created via
            # AgentSkillsManager). Do not remove either alias without migrating
            # the corresponding AgentSkill / AgentSkillIntegration rows.
            from agent.skills.flows_skill import FlowsSkill
            self.register_skill(FlowsSkill)
            self.registry["scheduler"] = FlowsSkill

            # Automation Skill: Multi-step workflow automation
            from agent.skills.automation_skill import AutomationSkill
            self.register_skill(AutomationSkill)

            # Phase 4.8 Week 3: Import adaptive personality skill
            from agent.skills.adaptive_personality_skill import AdaptivePersonalitySkill
            self.register_skill(AdaptivePersonalitySkill)

            # Task 3: Import knowledge sharing skill
            from agent.skills.knowledge_sharing_skill import KnowledgeSharingSkill
            self.register_skill(KnowledgeSharingSkill)

            # Agent Switcher: Import agent switcher skill
            from agent.skills.agent_switcher_skill import AgentSwitcherSkill
            self.register_skill(AgentSwitcherSkill)

            # Agent Communication: Inter-agent messaging (v0.6.0 Item 15)
            from agent.skills.agent_communication_skill import AgentCommunicationSkill
            self.register_skill(AgentCommunicationSkill)

            # Gmail: Import Gmail skill for email reading
            from agent.skills.gmail_skill import GmailSkill
            self.register_skill(GmailSkill)

            # Shell: Import Shell skill for remote command execution (Phase 18.3)
            from agent.skills.shell_skill import ShellSkill
            self.register_skill(ShellSkill)

            # Browser Automation: Import browser automation skill (Phase 14.5)
            from agent.skills.browser_automation_skill import BrowserAutomationSkill
            self.register_skill(BrowserAutomationSkill)

            # Image Analysis Skill: multimodal understanding for inbound images
            from agent.skills.image_analysis_skill import ImageAnalysisSkill
            self.register_skill(ImageAnalysisSkill)

            # Image Skill: Image generation and editing (Skills-as-Tools)
            from agent.skills.image_skill import ImageSkill
            self.register_skill(ImageSkill)

            # Sandboxed Tools: Master toggle for sandboxed tool access (nmap, nuclei, etc.)
            from agent.skills.sandboxed_tools_skill import SandboxedToolsSkill
            self.register_skill(SandboxedToolsSkill)

            # v0.6.0 Item 3: OKG Term Memory — structured long-term memory
            from agent.skills.okg_term_memory_skill import OKGTermMemorySkill
            self.register_skill(OKGTermMemorySkill)

            # v0.7.0: Ticket Management — Jira provider (read/write capability-gated)
            from agent.skills.jira_skill import JiraSkill
            self.register_skill(JiraSkill)

            logger.info("Built-in skills registered: flight_search, web_search, audio_transcript, audio_tts, flows, automation, adaptive_personality, knowledge_sharing, agent_switcher, agent_communication, gmail, shell, browser_automation, image_analysis, image, sandboxed_tools, okg_term_memory, ticket_management")
        except Exception as e:
            logger.error(f"Error registering built-in skills: {e}", exc_info=True)

    def register_skill(self, skill_class: Type[BaseSkill]):
        """
        Register a skill type in the manager.

        Args:
            skill_class: The skill class to register (must inherit from BaseSkill)

        Raises:
            ValueError: If skill_class is not a BaseSkill subclass
            ValueError: If skill_type is already registered
        """
        if not issubclass(skill_class, BaseSkill):
            raise ValueError(f"{skill_class.__name__} must inherit from BaseSkill")

        skill_type = skill_class.skill_type

        if skill_type in self.registry:
            logger.warning(f"Skill type '{skill_type}' already registered, overwriting")

        self.registry[skill_type] = skill_class
        logger.info(f"Registered skill: {skill_type} ({skill_class.__name__})")

    def unregister_skill(self, skill_type: str):
        """
        Unregister a skill type.

        Args:
            skill_type: The skill type to remove
        """
        if skill_type in self.registry:
            del self.registry[skill_type]
            logger.info(f"Unregistered skill: {skill_type}")

    def list_available_skills(self) -> List[Dict[str, str]]:
        """
        Get list of all registered skill types.

        Returns:
            List of dicts with skill metadata:
            [{
                "skill_type": "audio_transcript",
                "skill_name": "Audio Transcription",
                "skill_description": "Transcribe audio messages using Whisper",
                "config_schema": {...}
            }, ...]
        """
        skills = []
        for skill_type, skill_class in self.registry.items():
            # Wizard-facing metadata (BaseSkill defaults, overridden per skill).
            # Read via getattr so older skill classes without the attrs still work.
            applies_to = list(getattr(skill_class, "applies_to", ["text", "audio", "hybrid"]))
            auto_enabled_for = list(getattr(skill_class, "auto_enabled_for", []))
            wizard_visible = bool(getattr(skill_class, "wizard_visible", True))

            skills.append({
                "skill_type": skill_type,
                "skill_name": skill_class.skill_name,
                "skill_description": skill_class.skill_description,
                "config_schema": skill_class.get_config_schema(),
                "default_config": skill_class.get_default_config(),
                "wizard_visible": wizard_visible,
                "applies_to": applies_to,
                "auto_enabled_for": auto_enabled_for,
            })
        return skills

    async def get_agent_skills(self, db: Session, agent_id: int) -> List[AgentSkill]:
        """
        Get all enabled skills for a specific agent.

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            List of AgentSkill records (only enabled skills)
        """
        try:
            skills = db.query(AgentSkill)\
                .filter(AgentSkill.agent_id == agent_id)\
                .filter(AgentSkill.is_enabled == True)\
                .order_by(AgentSkill.created_at)\
                .all()

            logger.debug(f"Found {len(skills)} enabled skills for agent {agent_id}")
            return skills

        except Exception as e:
            logger.error(f"Error fetching skills for agent {agent_id}: {e}", exc_info=True)
            return []

    async def get_skill_config(
        self,
        db: Session,
        agent_id: int,
        skill_type: str
    ) -> Optional[Dict]:
        """
        Get configuration for a specific skill.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type identifier

        Returns:
            Skill config dict or None if not found/disabled
        """
        try:
            skill = db.query(AgentSkill)\
                .filter(AgentSkill.agent_id == agent_id)\
                .filter(AgentSkill.skill_type == skill_type)\
                .filter(AgentSkill.is_enabled == True)\
                .first()

            if skill:
                return skill.config or {}
            return None

        except Exception as e:
            logger.error(f"Error fetching skill config: {e}", exc_info=True)
            return None

    @classmethod
    def audit_agent_skill_config_key_collisions(
        cls,
        skill_configs: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Report top-level config key collisions against reserved agent-skill keys.

        This is a prep-only audit helper. It does not mutate data or enforce any
        schema/API contract. The goal is to surface keys that would clash with
        future shared scratchpad/queue fields before Track A persists them.
        """
        collisions: List[Dict[str, Any]] = []
        for skill_type, config in skill_configs.items():
            config_keys = set((config or {}).keys())
            overlapping_keys = sorted(config_keys & cls.RESERVED_AGENT_SKILL_CONFIG_KEYS)
            if overlapping_keys:
                collisions.append({
                    "skill_type": skill_type,
                    "colliding_keys": overlapping_keys,
                })
        return collisions

    async def audit_agent_skill_config_collisions(
        self,
        db: Session,
        agent_id: int,
    ) -> List[Dict[str, Any]]:
        """
        Collect the current enabled skill configs and flag reserved-key overlap.

        This is useful for prep-time audits, but it intentionally does not block
        saves or imply any new persistence/API behavior.
        """
        skills = await self.get_agent_skills(db, agent_id)
        skill_configs = {skill.skill_type: (skill.config or {}) for skill in skills}
        return self.audit_agent_skill_config_key_collisions(skill_configs)

    async def get_skill_tool_definitions(
        self,
        db: Session,
        agent_id: int
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Get tool definitions from skills that are in agentic mode.

        DEPRECATED: Use get_tool_definitions_for_agent() for new code.

        Phase 18.3.8: For skills with is_tool_enabled() returning True,
        collect their tool definitions for LLM function calling.

        This allows skills like ShellSkill to expose their tools to the AI
        when configured in 'agentic' execution_mode.

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            Tuple of (tool_definitions, shell_os_context):
            - tool_definitions: List of OpenAI-compatible tool definitions
            - shell_os_context: OS context string for shell targets (for AI prompt)
        """
        tool_definitions = []
        shell_os_context = ""

        try:
            # Get enabled skills for this agent
            agent_skills = await self.get_agent_skills(db, agent_id)

            for skill_record in agent_skills:
                skill_type = skill_record.skill_type

                if skill_type not in self.registry:
                    continue

                skill_class = self.registry[skill_type]

                # SKILL-002 Fix: Use centralized _create_skill_instance method
                skill_instance = self._create_skill_instance(skill_class, db, agent_id)

                # Check if skill has is_tool_enabled
                if hasattr(skill_instance, 'is_tool_enabled'):
                    config = skill_record.config or {}
                    logger.info(f"[SKILL TOOLS] Checking skill '{skill_type}' for tool mode (execution_mode={getattr(skill_class, 'execution_mode', 'not set')})")

                    # Check if this skill's tool should be exposed to the AI
                    is_enabled = skill_instance.is_tool_enabled(config)
                    logger.info(f"[SKILL TOOLS] Skill '{skill_type}' is_tool_enabled={is_enabled}")
                    if is_enabled:
                        # Multi-tool skills (e.g., OKG with okg_store/okg_recall/okg_forget)
                        if hasattr(skill_instance, 'get_all_mcp_tool_definitions'):
                            all_defs = skill_instance.get_all_mcp_tool_definitions()
                            if len(all_defs) > 1:
                                for mcp_def in all_defs:
                                    tool_def = {
                                        "type": "function",
                                        "function": {
                                            "name": mcp_def["name"],
                                            "description": mcp_def.get("description", ""),
                                            "parameters": mcp_def.get("inputSchema", {"type": "object", "properties": {}})
                                        }
                                    }
                                    tool_definitions.append(tool_def)
                                logger.info(f"Added {len(all_defs)} tools from multi-tool skill '{skill_type}'")
                                continue

                        tool_def = None

                        # Phase 4: Try new MCP format first (get_mcp_tool_definition)
                        # BUG-391 fix: Use skill_instance (not skill_class) so custom skills
                        # have access to self._record for tool definition generation
                        has_mcp = hasattr(skill_instance, 'get_mcp_tool_definition')
                        logger.info(f"[SKILL TOOLS] Skill '{skill_type}' has get_mcp_tool_definition={has_mcp}")
                        if has_mcp:
                            mcp_def = skill_instance.get_mcp_tool_definition()
                            logger.info(f"[SKILL TOOLS] Skill '{skill_type}' MCP definition name: {mcp_def.get('name') if mcp_def else None}")
                            if mcp_def:
                                # Convert MCP to OpenAI format using to_openai_tool()
                                if hasattr(skill_instance, 'to_openai_tool'):
                                    tool_def = skill_instance.to_openai_tool()
                                else:
                                    # Manual conversion if to_openai_tool not available
                                    tool_def = {
                                        "type": "function",
                                        "function": {
                                            "name": mcp_def["name"],
                                            "description": mcp_def.get("description", ""),
                                            "parameters": mcp_def.get("inputSchema", {"type": "object", "properties": {}})
                                        }
                                    }

                        # Fallback to legacy get_tool_definition
                        if not tool_def and hasattr(skill_class, 'get_tool_definition'):
                            tool_def = skill_class.get_tool_definition()
                            if tool_def:
                                # Convert to OpenAI function-calling format if needed
                                if "type" not in tool_def:
                                    tool_def = {
                                        "type": "function",
                                        "function": tool_def
                                    }

                        if tool_def:
                            tool_definitions.append(tool_def)
                            logger.info(f"Added tool definition from skill '{skill_type}' (agentic mode)")

                            # For shell skill, get OS context for targets
                            if skill_type == 'shell':
                                try:
                                    skill_instance.set_db_session(db)
                                    skill_instance._agent_id = agent_id
                                    shell_os_context = skill_instance.get_targets_os_context()
                                    if shell_os_context:
                                        logger.info(f"Retrieved OS context for shell targets: {len(shell_os_context)} chars")
                                except Exception as e:
                                    logger.warning(f"Failed to get shell OS context: {e}")

            if tool_definitions:
                logger.info(f"Collected {len(tool_definitions)} skill tool definitions for agent {agent_id}")

            return tool_definitions, shell_os_context

        except Exception as e:
            logger.error(f"Error getting skill tool definitions: {e}", exc_info=True)
            return [], ""

    # =========================================================================
    # SKILLS-AS-TOOLS: NEW METHODS (Phase 1)
    # =========================================================================

    async def get_tool_definitions_for_agent(
        self,
        db: Session,
        agent_id: int,
        provider: str = "openai"
    ) -> List[Dict[str, Any]]:
        """
        Get tool definitions for skills enabled for this agent.

        Skills-as-Tools: Returns tool definitions in provider-specific format
        for all skills that have is_tool_enabled() == True.

        Args:
            db: Database session
            agent_id: Agent ID
            provider: LLM provider for format selection
                      - "openai", "openrouter", "groq", "ollama", "gemini" → OpenAI format
                      - "anthropic" → Anthropic format (only if using direct API)

        Returns:
            List of tool definitions in provider-specific format
        """
        tools = []

        try:
            agent_skills = await self.get_agent_skills(db, agent_id)

            for skill_record in agent_skills:
                skill_type = skill_record.skill_type
                skill_class = self.registry.get(skill_type)

                if not skill_class:
                    continue

                config = skill_record.config or {}

                # Create instance to check is_tool_enabled
                skill_instance = self._create_skill_instance(skill_class, db, agent_id)
                skill_instance._config = config

                # Skip if tool mode not enabled
                if not skill_instance.is_tool_enabled(config):
                    continue

                # v0.6.0: Multi-tool skills (e.g., OKG with 3 tools)
                if hasattr(skill_class, 'get_all_mcp_tool_definitions'):
                    all_defs = skill_class.get_all_mcp_tool_definitions()
                    for mcp_def in all_defs:
                        if provider == "anthropic":
                            tool_def = {
                                "name": mcp_def["name"],
                                "description": mcp_def["description"],
                                "input_schema": mcp_def["inputSchema"]
                            }
                        else:
                            tool_def = {
                                "type": "function",
                                "function": {
                                    "name": mcp_def["name"],
                                    "description": mcp_def["description"],
                                    "parameters": mcp_def["inputSchema"]
                                }
                            }
                        tools.append(tool_def)
                    logger.debug(f"Added {len(all_defs)} tools from multi-tool skill '{skill_type}'")
                else:
                    # Single-tool skill (standard path)
                    if provider == "anthropic":
                        tool_def = skill_class.to_anthropic_tool()
                    else:
                        tool_def = skill_class.to_openai_tool()

                    if tool_def:
                        tools.append(tool_def)
                        logger.debug(f"Added tool from skill '{skill_type}' for provider '{provider}'")

            if tools:
                logger.info(f"Collected {len(tools)} skill tools for agent {agent_id} (provider: {provider})")

            return tools

        except Exception as e:
            logger.error(f"Error getting tool definitions for agent: {e}", exc_info=True)
            return []

    async def get_mcp_tool_definitions(
        self,
        db: Session,
        agent_id: int
    ) -> List[Dict[str, Any]]:
        """
        Get MCP-format tool definitions for all enabled skills.

        Use this for:
        - MCP server exposure
        - Documentation generation
        - Tool validation

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            List of MCP-compliant tool definitions
        """
        tools = []

        try:
            agent_skills = await self.get_agent_skills(db, agent_id)

            for skill_record in agent_skills:
                skill_type = skill_record.skill_type
                skill_class = self.registry.get(skill_type)

                if not skill_class:
                    continue

                config = skill_record.config or {}

                # Create instance to check is_tool_enabled
                skill_instance = self._create_skill_instance(skill_class, db, agent_id)
                skill_instance._config = config

                # Skip if tool mode not enabled
                if not skill_instance.is_tool_enabled(config):
                    continue

                # v0.6.0: Multi-tool skills
                # BUG-391 fix: Use skill_instance instead of skill_class
                if hasattr(skill_instance, 'get_all_mcp_tool_definitions'):
                    for mcp_def in skill_instance.get_all_mcp_tool_definitions():
                        tools.append(mcp_def)
                else:
                    mcp_def = skill_instance.get_mcp_tool_definition()
                    if mcp_def:
                        tools.append(mcp_def)

            return tools

        except Exception as e:
            logger.error(f"Error getting MCP tool definitions: {e}", exc_info=True)
            return []

    def find_skill_by_tool_name(self, tool_name: str) -> Optional[Type[BaseSkill]]:
        """
        Public method to find a skill class by its tool name.

        Skills-as-Tools (Phase 5): Used by agent_service to route tool calls
        to the appropriate skill.

        Args:
            tool_name: Name from LLM tool call (e.g., 'web_search', 'manage_flows')

        Returns:
            Skill class if found, None otherwise
        """
        return self._find_skill_by_tool_name(tool_name)

    async def execute_tool_call(
        self,
        db: Session,
        agent_id: int,
        tool_name: str,
        arguments: Dict[str, Any],
        message: Optional[InboundMessage] = None,
        sender_key: Optional[str] = None,
        return_full_result: bool = False
    ) -> Union[Optional[str], Optional[SkillResult]]:
        """
        Execute a tool call from LLM.

        Skills-as-Tools: Routes tool calls to the appropriate skill's
        execute_tool() method. Validates arguments against the input schema.

        Args:
            db: Database session
            agent_id: Agent ID
            tool_name: Name of the tool (e.g., 'run_shell_command', 'get_weather')
            arguments: Parsed arguments from LLM tool call
            message: Original inbound message (for context)
            sender_key: Sender identifier for tracking (legacy)
            return_full_result: If True, return full SkillResult instead of just output string

        Returns:
            Tool execution result as string (default), or full SkillResult if return_full_result=True
        """
        try:
            # Find skill by tool name
            skill_class = self._find_skill_by_tool_name(tool_name)

            if not skill_class:
                logger.warning(f"Unknown tool: {tool_name}")
                return f"Error: Unknown tool '{tool_name}'"

            # Get skill config — custom skills use AgentCustomSkill, not AgentSkill
            skill_record = await self._get_skill_record(db, agent_id, skill_class.skill_type)

            if not skill_record or not skill_record.is_enabled:
                # BUG-391 fix: For custom skills, check AgentCustomSkill table
                if skill_class.skill_type.startswith("custom:"):
                    from models import AgentCustomSkill, CustomSkill
                    record = getattr(skill_class, '_custom_skill_record', None)
                    if record:
                        assignment = db.query(AgentCustomSkill).filter(
                            AgentCustomSkill.agent_id == agent_id,
                            AgentCustomSkill.custom_skill_id == record.id,
                            AgentCustomSkill.is_enabled == True
                        ).first()
                        if assignment:
                            # Custom skill is assigned and enabled — proceed with empty config
                            skill_record = None  # Will use empty config below
                        else:
                            return f"Error: Tool '{tool_name}' is not enabled for this agent"
                    else:
                        return f"Error: Tool '{tool_name}' is not enabled for this agent"
                else:
                    return f"Error: Tool '{tool_name}' is not enabled for this agent"

            config = (skill_record.config if skill_record else None) or {}

            # BUG-384: Inject tenant_id and agent_id — handle None values too
            if not config.get('tenant_id') or 'agent_id' not in config:
                from models import Agent as AgentModel
                agent_obj = db.query(AgentModel).filter(AgentModel.id == agent_id).first()
                if agent_obj:
                    config['tenant_id'] = agent_obj.tenant_id
            config['agent_id'] = agent_id
            config['db'] = db

            # BUG-LOG-006 FIX: Propagate A2A comm_depth and parent_session_id from message
            # so agent_communication_skill can enforce depth limits on chained delegations
            if message:
                if hasattr(message, 'metadata') and message.metadata:
                    if 'comm_depth' in message.metadata:
                        config['comm_depth'] = message.metadata['comm_depth']
                    if 'comm_parent_session_id' in message.metadata:
                        config['comm_parent_session_id'] = message.metadata['comm_parent_session_id']

            # Create skill instance (before schema validation so custom skills have self._record)
            skill_instance = self._create_skill_instance(skill_class, db, agent_id)

            # Validate arguments against input schema
            # v0.6.0: Multi-tool skills — find the right schema by tool_name
            # BUG-391 fix: Use skill_instance instead of skill_class
            mcp_def = None
            if hasattr(skill_instance, 'get_all_mcp_tool_definitions'):
                for d in skill_instance.get_all_mcp_tool_definitions():
                    if d.get("name") == tool_name:
                        mcp_def = d
                        break
            if not mcp_def:
                mcp_def = skill_instance.get_mcp_tool_definition()
            if mcp_def and mcp_def.get("inputSchema"):
                validation_error = self._validate_arguments(arguments, mcp_def["inputSchema"])
                if validation_error:
                    return f"Error: Invalid arguments - {validation_error}"
            skill_instance._config = config
            skill_instance.set_db_session(db)
            skill_instance._agent_id = agent_id
            # v0.6.0: For multi-tool skills, tell the instance which tool was invoked
            if hasattr(skill_instance, '_current_tool_name'):
                skill_instance._current_tool_name = tool_name
            # Phase 0.6.0: Propagate token tracker for cost monitoring
            if hasattr(skill_instance, 'set_token_tracker') and self.token_tracker:
                skill_instance.set_token_tracker(self.token_tracker)

            # Create synthetic message if not provided
            if message is None:
                from datetime import datetime
                message = InboundMessage(
                    id=f"tool_call_{tool_name}",
                    sender=sender_key or "tool_caller",
                    sender_key=sender_key or "tool_caller",
                    body="",
                    chat_id="tool_execution",
                    chat_name=None,
                    is_group=False,
                    timestamp=datetime.utcnow(),
                    channel="tool"
                )

            # Phase 8: Emit skill_used event for AI tool-calling path
            tenant_id = config.get('tenant_id')
            if tenant_id:
                emit_skill_used_async(
                    tenant_id=tenant_id,
                    agent_id=agent_id,
                    skill_type=skill_class.skill_type,
                    skill_name=getattr(skill_instance, 'name', skill_class.skill_type)
                )

            # Execute tool
            try:
                import time as _time
                _start = _time.time()
                result = await skill_instance.execute_tool(arguments, message, config)
                _elapsed_ms = int((_time.time() - _start) * 1000)

                # BUG-509: Write CustomSkillExecution history for runtime tool calls
                # so assigned custom-skill invocations (Playground/WhatsApp) show up
                # in execution history just like /api/custom-skills/{id}/test calls.
                try:
                    from agent.skills.custom_skill_adapter import CustomSkillAdapter as _CustomSkillAdapter
                    if isinstance(skill_instance, _CustomSkillAdapter) and getattr(skill_instance, '_record', None):
                        from models import CustomSkillExecution as _CSE
                        _rec = skill_instance._record
                        _exec_row = _CSE(
                            tenant_id=config.get('tenant_id') or _rec.tenant_id,
                            agent_id=agent_id,
                            custom_skill_id=_rec.id,
                            skill_name=_rec.name,
                            input_json=arguments or {},
                            status='completed' if result.success else 'failed',
                            output=(result.output[:4000] if result.output else None) if result.success else None,
                            error=(result.output[:4000] if result.output else None) if not result.success else None,
                            execution_time_ms=_elapsed_ms,
                        )
                        db.add(_exec_row)
                        db.commit()
                except Exception as _hist_err:
                    logger.warning(f"Failed to write CustomSkillExecution history: {_hist_err}")

                if return_full_result:
                    return result
                return result.output if result.success else f"Error: {result.output}"
            except NotImplementedError:
                # SKILL-004 Fix: Use WARNING level to improve visibility of legacy fallback
                logger.warning(
                    f"Skill '{skill_class.skill_type}' doesn't support execute_tool() - "
                    f"using legacy handler. Consider migrating to Skills-as-Tools."
                )
                return await self._legacy_execute_skill_tool(db, agent_id, tool_name, arguments, sender_key)

        except Exception as e:
            logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
            return f"Error executing {tool_name}: {str(e)}"

    def _find_skill_by_tool_name(self, tool_name: str) -> Optional[Type[BaseSkill]]:
        """
        Map tool name to skill class using MCP definition.

        Supports multi-tool skills (e.g., OKG with okg_store/okg_recall/okg_forget)
        via get_all_mcp_tool_definitions().

        Args:
            tool_name: Name from LLM tool call

        Returns:
            Skill class or None if not found
        """
        for skill_class in self.registry.values():
            try:
                # BUG-391 fix: For custom skills, instantiate to get tool definitions
                if getattr(skill_class, 'skill_type', '').startswith('custom:'):
                    record = getattr(skill_class, '_custom_skill_record', None)
                    inst = skill_class(skill_record=record)
                else:
                    inst = skill_class

                # Check multi-tool definitions first (v0.6.0: OKG Term Memory)
                if hasattr(inst, 'get_all_mcp_tool_definitions'):
                    all_defs = inst.get_all_mcp_tool_definitions()
                    if any(d.get("name") == tool_name for d in all_defs):
                        return skill_class

                # Check single MCP definition
                mcp_def = inst.get_mcp_tool_definition()
                if mcp_def and mcp_def.get("name") == tool_name:
                    return skill_class

                # Fallback: Check legacy get_tool_definition
                tool_def = inst.get_tool_definition() if hasattr(inst, 'get_tool_definition') else skill_class.get_tool_definition()
            except Exception:
                continue

            if tool_def:
                # Handle both wrapped and unwrapped formats
                if tool_def.get("type") == "function":
                    if tool_def.get("function", {}).get("name") == tool_name:
                        return skill_class
                elif tool_def.get("name") == tool_name:
                    return skill_class

        # BUG-353 FIX: Custom skills are registered under "custom:{slug}" keys but
        # their tool definitions use "custom_{slug}" names.  The dynamic subclass
        # created in register_custom_skills() has no _record, so
        # get_mcp_tool_definition() returns None.  Resolve via registry key.
        if tool_name.startswith("custom_"):
            custom_key = f"custom:{tool_name[7:]}"
            if custom_key in self.registry:
                return self.registry[custom_key]

        return None

    def _validate_arguments(
        self,
        arguments: Dict[str, Any],
        schema: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate arguments against JSON Schema.

        Basic validation for required fields and types.
        For full JSON Schema validation, consider using jsonschema library.

        Args:
            arguments: Arguments to validate
            schema: JSON Schema to validate against

        Returns:
            Error message if invalid, None if valid
        """
        # Check required fields
        required = schema.get("required", [])
        for field in required:
            if field not in arguments:
                return f"Missing required field: {field}"

        # Basic type validation with coercion for common cases
        properties = schema.get("properties", {})
        for field, value in arguments.items():
            if field not in properties:
                continue  # Allow extra fields

            expected_type = properties[field].get("type")
            if expected_type == "string" and not isinstance(value, str):
                return f"Field '{field}' must be a string"
            if expected_type == "number" and not isinstance(value, (int, float)):
                # Try to convert strings to numbers
                if isinstance(value, str):
                    try:
                        float(value)  # Test if convertible
                        arguments[field] = float(value)
                        continue
                    except ValueError:
                        pass
                return f"Field '{field}' must be a number"
            if expected_type == "integer":
                # Accept int, or strings/floats that can be converted to int
                if isinstance(value, bool):  # bool is subclass of int, reject it
                    return f"Field '{field}' must be an integer"
                if isinstance(value, int):
                    continue
                if isinstance(value, (str, float)):
                    try:
                        arguments[field] = int(float(value))
                        continue
                    except (ValueError, TypeError):
                        pass
                return f"Field '{field}' must be an integer"
            if expected_type == "boolean" and not isinstance(value, bool):
                if isinstance(value, str) and value.lower() in ("true", "false"):
                    arguments[field] = value.lower() == "true"
                else:
                    return f"Field '{field}' must be a boolean"
            if expected_type == "array" and not isinstance(value, list):
                if isinstance(value, str):
                    arguments[field] = [v.strip() for v in value.split(",") if v.strip()] if value else []
                else:
                    return f"Field '{field}' must be an array"
            if expected_type == "object" and not isinstance(value, dict):
                return f"Field '{field}' must be an object"

        return None

    def _create_skill_instance(
        self,
        skill_class: Type[BaseSkill],
        db: Session,
        agent_id: int
    ) -> BaseSkill:
        """
        Create a skill instance with proper initialization.

        Handles special initialization requirements for different skills.

        Args:
            skill_class: Skill class to instantiate
            db: Database session
            agent_id: Agent ID

        Returns:
            Initialized skill instance
        """
        skill_type = skill_class.skill_type

        # Handle skills with special initialization
        if skill_type == "knowledge_sharing":
            return skill_class(db, agent_id)
        elif skill_type == "browser_automation":
            return skill_class(db=db, token_tracker=self.token_tracker)
        elif skill_type == "image_analysis":
            return skill_class(token_tracker=self.token_tracker)
        elif skill_type == "image":
            return skill_class(token_tracker=self.token_tracker)
        elif skill_type == "okg_term_memory":
            return skill_class(db=db, agent_id=agent_id)
        elif skill_type.startswith("custom:"):
            # BUG-391 fix: Dynamic custom skill classes store the DB record as a class
            # attribute (_custom_skill_record) via type(). Pass it to __init__ so that
            # self._record is set and get_mcp_tool_definition() works correctly.
            record = getattr(skill_class, '_custom_skill_record', None)
            return skill_class(skill_record=record)
        else:
            return skill_class()

    async def _get_skill_record(
        self,
        db: Session,
        agent_id: int,
        skill_type: str
    ) -> Optional[AgentSkill]:
        """
        Get the AgentSkill record for a specific skill.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type identifier

        Returns:
            AgentSkill record or None
        """
        try:
            return db.query(AgentSkill)\
                .filter(AgentSkill.agent_id == agent_id)\
                .filter(AgentSkill.skill_type == skill_type)\
                .first()
        except Exception as e:
            logger.error(f"Error getting skill record: {e}")
            return None

    async def _legacy_execute_skill_tool(
        self,
        db: Session,
        agent_id: int,
        tool_name: str,
        arguments: Dict[str, Any],
        sender_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Legacy handler for skills that haven't migrated to execute_tool().

        Preserves backward compatibility with existing tool execution.
        """
        # Map tool names to skill types (legacy mapping)
        tool_to_skill = {
            'run_shell_command': 'shell'
        }

        skill_type = tool_to_skill.get(tool_name)
        if not skill_type:
            return None

        # Handle shell tool execution (legacy)
        if tool_name == 'run_shell_command':
            from agent.tools.shell_tool import run_shell_command

            script = arguments.get('script', '')
            target = arguments.get('target', 'default')
            timeout = arguments.get('timeout', 60)

            result = await run_shell_command(
                script=script,
                db=db,
                agent_id=agent_id,
                target=target,
                timeout=timeout,
                sender_key=sender_key
            )

            return result

        return None

    async def execute_skill_tool(
        self,
        db: Session,
        agent_id: int,
        tool_name: str,
        arguments: Dict[str, Any],
        sender_key: Optional[str] = None
    ) -> Optional[str]:
        """
        Execute a skill-based tool call (legacy method).

        DEPRECATED: New code should use execute_tool_call() which supports
        the Skills-as-Tools architecture with execute_tool() on skill classes.

        Phase 18.3.8: When AI calls a skill tool (like run_shell_command),
        this method routes the call to the appropriate skill.

        Args:
            db: Database session
            agent_id: Agent ID
            tool_name: Name of the tool (e.g., 'run_shell_command')
            arguments: Tool arguments from AI
            sender_key: Sender identifier for tracking

        Returns:
            Tool execution result as string, or None if tool not found
        """
        try:
            # Map tool names to skill types
            tool_to_skill = {
                'run_shell_command': 'shell'
            }

            skill_type = tool_to_skill.get(tool_name)
            if not skill_type:
                logger.warning(f"Unknown skill tool: {tool_name}")
                return None

            # Check if skill is enabled for this agent
            skill_config = await self.get_skill_config(db, agent_id, skill_type)
            if skill_config is None:
                logger.warning(f"Skill '{skill_type}' not enabled for agent {agent_id}")
                return f"L Error: {skill_type} skill is not enabled for this agent"

            # Handle shell tool execution
            if tool_name == 'run_shell_command':
                from agent.tools.shell_tool import run_shell_command

                script = arguments.get('script', '')
                target = arguments.get('target', 'default')
                timeout = arguments.get('timeout', 60)

                result = await run_shell_command(
                    script=script,
                    db=db,
                    agent_id=agent_id,
                    target=target,
                    timeout=timeout,
                    sender_key=sender_key
                )

                return result

            return None

        except Exception as e:
            logger.error(f"Error executing skill tool '{tool_name}': {e}", exc_info=True)
            return f"L Error executing {tool_name}: {str(e)}"

    async def process_message_with_skills(
        self,
        db: Session,
        agent_id: int,
        message: InboundMessage
    ) -> Optional[SkillResult]:
        """
        Try to process message with agent's enabled skills.

        Skills are tried in order until one handles the message.

        Args:
            db: Database session
            agent_id: Agent ID
            message: The inbound message

        Returns:
            SkillResult if a skill handled the message, None otherwise
        """
        try:
            logger.info(f"process_message_with_skills called for agent {agent_id}, media_type={message.media_type}")

            # Track if audio was transcribed (for returning transcript if no other skill handles it)
            saved_transcript_result = None

            # Get enabled skills for this agent
            agent_skills = await self.get_agent_skills(db, agent_id)
            logger.info(f"Found {len(agent_skills)} enabled skills for agent {agent_id}")

            if not agent_skills:
                logger.debug(f"No skills enabled for agent {agent_id}")
                return None

            # Special handling for audio messages: transcribe first, then let other skills process
            if message.media_type and message.media_type.lower().startswith('audio'):
                logger.info("Audio message detected - checking for audio_transcript skill first")

                # Find audio_transcript skill
                audio_skill = next((s for s in agent_skills if s.skill_type == 'audio_transcript'), None)

                if audio_skill and audio_skill.is_enabled:
                    logger.info("Audio transcript skill found and enabled - transcribing first")

                    # Transcribe audio
                    skill_class = self.registry.get('audio_transcript')
                    if skill_class:
                        # Use the same centralized setup path as other skills so
                        # the transcription skill gets DB access and token tracking.
                        skill_instance = self._create_skill_instance(skill_class, db, agent_id)
                        if hasattr(skill_instance, 'set_db_session'):
                            skill_instance.set_db_session(db)
                        if hasattr(skill_instance, 'set_token_tracker') and self.token_tracker:
                            skill_instance.set_token_tracker(self.token_tracker)
                        skill_instance._agent_id = agent_id

                        config = dict(audio_skill.config or {})
                        config['agent_id'] = agent_id

                        from models import Agent
                        agent = db.query(Agent).filter(Agent.id == agent_id).first()
                        if agent:
                            if agent.tenant_id and not config.get('tenant_id'):
                                config['tenant_id'] = agent.tenant_id
                            if agent.provider_instance_id and not config.get('provider_instance_id'):
                                config['provider_instance_id'] = agent.provider_instance_id

                        try:
                            transcript_result = await skill_instance.process(message, config)

                            logger.info(f"DEBUG: transcript_result.success={transcript_result.success}")
                            logger.info(f"DEBUG: transcript_result.processed_content={repr(transcript_result.processed_content)}")
                            logger.info(f"DEBUG: transcript_result.output={transcript_result.output[:100] if transcript_result.output else None}")

                            if transcript_result.success and transcript_result.processed_content:
                                logger.info(f"Transcription successful: {len(transcript_result.processed_content)} chars")
                                logger.info(f"Transcript: {transcript_result.processed_content}")

                                # Update message body with transcribed text
                                message.body = transcript_result.processed_content
                                message.media_type = None  # Clear media type so other skills see it as text

                                logger.info("Message updated with transcript - continuing to other skills")

                                # Save transcript result to return if no other skill handles it
                                saved_transcript_result = transcript_result
                            else:
                                logger.warning(f"Transcription failed or returned no content (success={transcript_result.success}, has_content={bool(transcript_result.processed_content)})")
                                return transcript_result

                        except Exception as e:
                            logger.error(f"Error during audio transcription: {e}", exc_info=True)
                            # Continue to try other skills even if transcription fails

            # Try each skill in order
            for skill_record in agent_skills:
                skill_type = skill_record.skill_type

                # Skip audio_transcript if we already processed it above
                if skill_type == 'audio_transcript':
                    logger.info(f"Skipping audio_transcript (already processed)")
                    continue

                logger.info(f"Checking skill: {skill_type}")

                # Check if skill type is registered
                if skill_type not in self.registry:
                    logger.warning(
                        f"Skill type '{skill_type}' enabled for agent {agent_id} "
                        f"but not registered in manager"
                    )
                    continue

                logger.info(f"Skill '{skill_type}' is registered, creating instance...")
                skill_class = self.registry[skill_type]

                # SKILL-002 Fix: Use centralized _create_skill_instance method
                skill_instance = self._create_skill_instance(skill_class, db, agent_id)

                # Phase 7.4: Set database session for all skills (for API key loading in AI classification)
                if hasattr(skill_instance, 'set_db_session'):
                    skill_instance.set_db_session(db)

                # Phase 0.6.0: Set token tracker for all skills (for LLM cost monitoring)
                if hasattr(skill_instance, 'set_token_tracker') and self.token_tracker:
                    skill_instance.set_token_tracker(self.token_tracker)

                # Phase 6.11.4: Pass agent_id to all skills for Agendador detection
                skill_instance._agent_id = agent_id

                # Phase 7.1: Inject skill configuration for can_handle() to access
                skill_instance._config = skill_record.config or {}

                # Check if skill can handle this message
                try:
                    logger.info(f"Calling can_handle for '{skill_type}'...")
                    can_handle = await skill_instance.can_handle(message)
                    logger.info(f"Skill '{skill_type}' can_handle result: {can_handle}")

                    if not can_handle:
                        logger.debug(
                            f"Skill '{skill_type}' cannot handle message "
                            f"(media_type={message.media_type})"
                        )
                        continue

                    # Skill can handle - process the message
                    logger.info(
                        f"Processing message with skill '{skill_type}' "
                        f"for agent {agent_id}"
                    )

                    # Inject agent_id and tenant_id into config for skills that need database access
                    config = skill_record.config or {}
                    config['agent_id'] = agent_id

                    # BUG-384: Get tenant_id from agent — also handle config with tenant_id=None
                    if not config.get('tenant_id'):
                        from models import Agent
                        agent = db.query(Agent).filter(Agent.id == agent_id).first()
                        if agent:
                            config['tenant_id'] = agent.tenant_id

                    # Phase 8: Emit skill_used event BEFORE processing
                    # so Graph View shows the glow immediately when a skill is activated
                    tenant_id = config.get('tenant_id')
                    if tenant_id:
                        emit_skill_used_async(
                            tenant_id=tenant_id,
                            agent_id=agent_id,
                            skill_type=skill_type,
                            skill_name=getattr(skill_instance, 'name', skill_type)
                        )

                    result = await skill_instance.process(message, config)

                    if result.success:
                        logger.info(
                            f"Skill '{skill_type}' successfully processed message "
                            f"for agent {agent_id}"
                        )
                    else:
                        logger.warning(
                            f"Skill '{skill_type}' processing failed: {result.output}"
                        )

                    # Add skill_type to metadata for tracking
                    if not result.metadata:
                        result.metadata = {}
                    result.metadata['skill_type'] = skill_type

                    return result

                except Exception as e:
                    logger.error(
                        f"Error executing skill '{skill_type}' for agent {agent_id}: {e}",
                        exc_info=True
                    )
                    # Continue to next skill instead of failing completely
                    continue

            # No skill handled the message, but if we transcribed audio, return that
            if saved_transcript_result:
                logger.info("Returning transcript result (no other skill handled the message)")
                return saved_transcript_result

            logger.debug(f"No skill handled message for agent {agent_id}")
            return None

        except Exception as e:
            logger.error(
                f"Error in process_message_with_skills for agent {agent_id}: {e}",
                exc_info=True
            )
            return None

    async def enable_skill(
        self,
        db: Session,
        agent_id: int,
        skill_type: str,
        config: Optional[Dict] = None
    ) -> AgentSkill:
        """
        Enable a skill for an agent.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type to enable
            config: Optional skill configuration

        Returns:
            AgentSkill record

        Raises:
            ValueError: If skill_type is not registered
            ValueError: If skill conflicts with existing skills
        """
        if skill_type not in self.registry:
            raise ValueError(f"Skill type '{skill_type}' is not registered")

        # Phase 7.3: Validate skill conflicts
        self._validate_skill_conflicts(db, agent_id, skill_type, config)

        # Check if skill already exists
        existing = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.skill_type == skill_type)\
            .first()

        if existing:
            # Update existing
            existing.is_enabled = True
            if config is not None:
                existing.config = config
            db.commit()
            logger.info(f"Re-enabled skill '{skill_type}' for agent {agent_id}")
            return existing

        # Create new
        skill_class = self.registry[skill_type]
        default_config = skill_class.get_default_config()

        new_skill = AgentSkill(
            agent_id=agent_id,
            skill_type=skill_type,
            is_enabled=True,
            config=config or default_config
        )

        db.add(new_skill)
        db.commit()
        db.refresh(new_skill)

        logger.info(f"Enabled skill '{skill_type}' for agent {agent_id}")
        return new_skill

    async def disable_skill(
        self,
        db: Session,
        agent_id: int,
        skill_type: str
    ) -> bool:
        """
        Disable a skill for an agent.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type to disable

        Returns:
            True if disabled, False if not found
        """
        skill = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.skill_type == skill_type)\
            .first()

        if skill:
            skill.is_enabled = False
            db.commit()
            logger.info(f"Disabled skill '{skill_type}' for agent {agent_id}")
            return True

        logger.warning(
            f"Cannot disable skill '{skill_type}' for agent {agent_id}: not found"
        )
        return False

    async def update_skill_config(
        self,
        db: Session,
        agent_id: int,
        skill_type: str,
        config: Dict
    ) -> bool:
        """
        Update configuration for a skill.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type
            config: New configuration dict

        Returns:
            True if updated, False if not found

        Raises:
            ValueError: If new config creates skill conflicts
        """
        skill = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.skill_type == skill_type)\
            .first()

        if skill:
            # Phase 7.3: Validate skill conflicts with new config
            self._validate_skill_conflicts(db, agent_id, skill_type, config)

            skill.config = config
            db.commit()
            logger.info(f"Updated config for skill '{skill_type}' (agent {agent_id})")
            return True

        logger.warning(
            f"Cannot update config for skill '{skill_type}' (agent {agent_id}): not found"
        )
        return False

    # SKILL-007 Fix: Extensible conflict rules for skill validation
    SKILL_CONFLICT_RULES = [
        {
            "name": "transcript_only_vs_tts",
            "check": lambda configs: (
                configs.get('audio_transcript', {}).get('response_mode') == 'transcript_only'
                and 'audio_tts' in configs
            ),
            "error": (
                "Cannot enable audio_tts with audio_transcript in 'transcript_only' mode. "
                "Either change audio_transcript to 'conversational' mode or disable audio_tts. "
                "Transcript-only mode sends raw transcripts without AI processing, "
                "which bypasses the TTS response generation."
            )
        },
        # Add new conflict rules here as needed:
        # {
        #     "name": "example_conflict",
        #     "check": lambda configs: ...,
        #     "error": "..."
        # }
    ]

    def _validate_skill_conflicts(
        self,
        db: Session,
        agent_id: int,
        skill_type: str,
        config: Optional[Dict] = None
    ):
        """
        Validate that enabling/configuring a skill doesn't create conflicts.

        Uses SKILL_CONFLICT_RULES for extensible conflict checking.

        Args:
            db: Database session
            agent_id: Agent ID
            skill_type: Skill type being enabled/configured
            config: Skill configuration

        Raises:
            ValueError: If skill creates conflicts with existing skills
        """
        # Get all enabled skills for this agent
        existing_skills = db.query(AgentSkill)\
            .filter(AgentSkill.agent_id == agent_id)\
            .filter(AgentSkill.is_enabled == True)\
            .all()

        # Build a map of skill_type -> config
        skill_configs = {s.skill_type: s.config or {} for s in existing_skills}

        # Add/update the current skill being validated
        if config is not None:
            skill_configs[skill_type] = config

        # Check all conflict rules
        for rule in self.SKILL_CONFLICT_RULES:
            try:
                if rule["check"](skill_configs):
                    raise ValueError(rule["error"])
            except ValueError:
                raise
            except Exception as e:
                logger.warning(f"Error checking conflict rule '{rule['name']}': {e}")


    # =========================================================================
    # PHASE 22: CUSTOM SKILLS FOUNDATION
    # =========================================================================

    def register_custom_skills(self, db, tenant_id: str):
        """
        Load tenant's enabled+clean custom skills into the registry.

        Always refreshes from DB to pick up enable/disable changes.
        Removes stale entries for skills no longer enabled/clean.
        """
        from models import CustomSkill
        from agent.skills.custom_skill_adapter import CustomSkillAdapter

        skills = db.query(CustomSkill).filter(
            CustomSkill.tenant_id == tenant_id,
            CustomSkill.is_enabled == True,
            CustomSkill.scan_status == 'clean'
        ).all()

        active_keys = set()
        for record in skills:
            key = f"custom:{record.slug}"
            active_keys.add(key)
            adapter_class = type(
                f"CustomSkill_{record.slug}",
                (CustomSkillAdapter,),
                {
                    'skill_type': key,
                    'skill_name': record.name,
                    'skill_description': record.description or '',
                    'execution_mode': record.execution_mode,
                    '_custom_skill_record': record,
                }
            )
            self.registry[key] = adapter_class

        # Remove stale custom skill entries (disabled or rejected since last registration)
        stale_keys = [k for k in self.registry if k.startswith("custom:") and k not in active_keys]
        for k in stale_keys:
            del self.registry[k]
            logger.info(f"Unregistered stale custom skill: {k}")

    def get_custom_skill_tool_definitions(self, db, agent_id: int) -> list:
        """
        Get OpenAI-format tool definitions for custom skills assigned to this agent.

        Only includes custom skills that are:
        - Assigned and enabled for this agent
        - Globally enabled on the CustomSkill record
        - Have clean scan status
        - Are in 'tool' or 'hybrid' execution mode

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            List of OpenAI-compatible tool definitions
        """
        from models import AgentCustomSkill, CustomSkill
        from agent.skills.custom_skill_adapter import CustomSkillAdapter

        try:
            assignments = db.query(AgentCustomSkill, CustomSkill).join(
                CustomSkill, AgentCustomSkill.custom_skill_id == CustomSkill.id
            ).filter(
                AgentCustomSkill.agent_id == agent_id,
                AgentCustomSkill.is_enabled == True,
                CustomSkill.is_enabled == True,
                CustomSkill.scan_status == 'clean',
                CustomSkill.execution_mode.in_(['tool', 'hybrid']),
            ).all()

            tool_defs = []
            for _assignment, skill in assignments:
                adapter = CustomSkillAdapter(skill)
                tool_def = adapter.get_mcp_tool_definition()
                if tool_def:
                    tool_defs.append({
                        "type": "function",
                        "function": {
                            "name": tool_def["name"],
                            "description": tool_def.get("description", ""),
                            "parameters": tool_def.get("inputSchema", {"type": "object", "properties": {}})
                        }
                    })

            if tool_defs:
                logger.info(f"Collected {len(tool_defs)} custom skill tool definitions for agent {agent_id}")

            return tool_defs

        except Exception as e:
            logger.error(f"Error getting custom skill tool definitions: {e}", exc_info=True)
            return []

    def get_custom_skill_instructions(self, db, agent_id: int) -> str:
        """
        Get concatenated instructions from passive instruction-type custom skills
        assigned to this agent.

        BUG-509: Only skills with ``execution_mode == 'passive'`` inject their raw
        ``instructions_md`` into the system prompt. Tool/hybrid instruction skills
        are exposed as callable tools instead and execute through the LLM adapter
        at runtime (matching the /api/custom-skills/{id}/test behavior), so their
        raw instructions must NOT be dumped back into the prompt (that is what
        caused the Playground response to leak the instruction template verbatim).

        Args:
            db: Database session
            agent_id: Agent ID

        Returns:
            Concatenated instruction markdown from matching passive custom skills
        """
        from models import AgentCustomSkill, CustomSkill

        assignments = db.query(AgentCustomSkill).join(
            CustomSkill, AgentCustomSkill.custom_skill_id == CustomSkill.id
        ).filter(
            AgentCustomSkill.agent_id == agent_id,
            AgentCustomSkill.is_enabled == True,
            CustomSkill.is_enabled == True,
            CustomSkill.skill_type_variant == 'instruction',
            CustomSkill.execution_mode == 'passive',
            CustomSkill.scan_status == 'clean'
        ).all()

        instructions = []
        for assignment in assignments:
            skill = db.query(CustomSkill).filter(CustomSkill.id == assignment.custom_skill_id).first()
            if skill and skill.instructions_md:
                instructions.append(f"## Custom Skill: {skill.name}\n{skill.instructions_md}")

        return "\n\n".join(instructions)


# Global skill manager instance
_skill_manager: Optional[SkillManager] = None


def get_skill_manager(token_tracker: Optional["TokenTracker"] = None) -> SkillManager:
    """
    Get the global SkillManager instance (singleton pattern).

    Args:
        token_tracker: TokenTracker instance (only used on first call)

    Returns:
        SkillManager instance
    """
    global _skill_manager
    if _skill_manager is None:
        _skill_manager = SkillManager(token_tracker=token_tracker)
    elif token_tracker is not None and _skill_manager.token_tracker is None:
        # Allow setting token_tracker if it wasn't set initially
        _skill_manager.token_tracker = token_tracker
    return _skill_manager
