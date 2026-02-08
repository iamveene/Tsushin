import logging
import re
from typing import Dict, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import or_
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AgentRun, MessageCache, Memory, Agent, ContactAgentMapping, Contact, TonePreset, ScheduledEvent, ConversationThread
from .agent_service import AgentService
from .interactive_selection import choose_interactive_option, get_menu_signature
from .acknowledgment import should_acknowledge_status
from .session_reset import should_attempt_session_reset, reset_message_for_attempt
from .contact_service_cached import CachedContactService  # Phase 6.11.3: Cached contact lookups
from scheduler.scheduler_service import SchedulerService  # Phase 6.4 Week 3
# Phase 4.8: Ring buffer memory (SenderMemory) deprecated
# Using Multi-Agent Memory Architecture instead

# Phase 4.8: Multi-Agent Memory Architecture
from .memory.multi_agent_memory import MultiAgentMemoryManager
from mcp_sender import MCPSender
import json

# Phase 5.0: Skills System
from agent.skills import get_skill_manager, InboundMessage
from mcp_reader.media_downloader import MediaDownloader

# Phase 7.2: Token Analytics
from analytics.token_tracker import TokenTracker

# Phase 16: Slash Command Service
from services.slash_command_service import SlashCommandService

# Phase 10.2: Group sender auto-resolution (Option B)
from services.group_sender_resolver import GroupSenderResolver

# Phase 8: Watcher activity events
from services.watcher_activity_service import emit_agent_processing_async

# Shared utilities
from agent.utils import summarize_tool_result
from agent.memory.tool_output_buffer import get_tool_output_buffer


def _determine_agent_run_status(result: Dict) -> str:
    """
    Determine the status of an agent run based on the result.
    Checks both explicit error field and failure indicators in the answer.
    """
    # Check explicit error field
    if result.get("error"):
        return "error"

    # Check for failure indicators in the answer
    answer = (result.get("answer") or "").lower()
    failure_indicators = [
        "command failed",
        "exit code: 1",
        "exit code: 2",
        "exit code:",
        "error:",
        "failed to",
        "exception:",
        "traceback",
        "permission denied",
        "not found",
        "timed out",
        "timeout"
    ]

    if answer and any(indicator in answer for indicator in failure_indicators):
        return "error"

    return "success"


class AgentRouter:
    def __init__(self, db_session: Session, config: Dict, mcp_reader=None, mcp_instance_id: int = None, telegram_instance_id: int = None):
        self.db = db_session
        self.config = config
        self.contact_mappings = config.get("contact_mappings", {})
        self.logger = logging.getLogger(__name__)

        # Phase 10: Track which MCP instance this router serves for channel-based filtering
        self.mcp_instance_id = mcp_instance_id
        # Phase 10.1.1: Track which Telegram instance this router serves
        self.telegram_instance_id = telegram_instance_id

        # Phase 6.11.3: Initialize CachedContactService for faster lookups
        self.contact_service = CachedContactService(db_session)

        # Phase 7.2: Initialize TokenTracker for usage analytics
        self.token_tracker = TokenTracker(db_session)
        self.logger.info("TokenTracker initialized for analytics")

        # Phase 4.8: Initialize Multi-Agent Memory Manager
        self.logger.info("Initializing Multi-Agent Memory Manager...")
        self.memory_manager = MultiAgentMemoryManager(
            db_session=db_session,
            config=config,
            base_chroma_dir="./data/chroma"
        )
        self.logger.info("Multi-Agent Memory Manager initialized")

        # Phase 4.8: Ring buffer memory deprecated, using Multi-Agent Memory Manager
        # AgentService no longer needs SenderMemory parameter

        # Phase 4.6: Pass database session for API key loading
        # Phase 7.2: Pass token_tracker for usage tracking
        self.agent_service = AgentService(
            config,
            contact_service=self.contact_service,
            db=db_session,
            token_tracker=self.token_tracker
        )
        self.mcp_sender = MCPSender()
        self.mcp_reader = mcp_reader  # For fetching context messages

        # Phase 10.1.1: Initialize TelegramSender if handling Telegram messages
        self.telegram_sender = None
        if telegram_instance_id:
            try:
                from models import TelegramBotInstance
                from services.telegram_bot_service import TelegramBotService
                from telegram_integration.sender import TelegramSender

                bot_instance = db_session.query(TelegramBotInstance).get(telegram_instance_id)
                if bot_instance:
                    telegram_service = TelegramBotService(db_session)
                    token = telegram_service._decrypt_token(
                        bot_instance.bot_token_encrypted,
                        bot_instance.tenant_id
                    )
                    self.telegram_sender = TelegramSender(token)
                    self.logger.info(f"TelegramSender initialized for bot @{bot_instance.bot_username}")
            except Exception as e:
                self.logger.error(f"Failed to initialize TelegramSender: {e}", exc_info=True)

        # Phase 5.0: Initialize SkillManager for audio transcription, TTS, etc.
        # Phase 7.2: Pass token_tracker for usage analytics
        self.skill_manager = get_skill_manager(token_tracker=self.token_tracker)
        self.logger.info(f"SkillManager initialized with {len(self.skill_manager.registry)} skills")

        # Phase 5.0: Initialize MediaDownloader for downloading audio/media files
        self.media_downloader = MediaDownloader()
        self.logger.info("MediaDownloader initialized")

        # Phase 6.4 Week 3: Initialize SchedulerService for conversation detection
        # Item 11.4: Pass memory_manager to SchedulerService for semantic memory in conversations
        self.scheduler_service = SchedulerService(db_session, memory_manager=self.memory_manager)
        self.logger.info("SchedulerService initialized for conversation routing with memory integration")

        # Phase 4.8: Ring buffer memory loading deprecated
        # Memory persistence now handled by Multi-Agent Memory Manager (ChromaDB)

    def get_agent_config(self, agent: Agent) -> Dict:
        """
        Resolve agent-specific configuration with system-level fallback.
        Per-Agent Configuration: Agent-specific values take precedence over system defaults.

        Args:
            agent: Agent model instance

        Returns:
            Dictionary with resolved configuration
        """
        # Start with system config as base
        resolved_config = dict(self.config)

        # Override with agent-specific values (if not NULL)
        if agent.memory_size is not None:
            resolved_config["memory_size"] = agent.memory_size

        # Memory isolation mode (default: "isolated")
        resolved_config["memory_isolation_mode"] = getattr(agent, "memory_isolation_mode", "isolated") or "isolated"

        if agent.trigger_dm_enabled is not None:
            resolved_config["dm_auto_mode"] = agent.trigger_dm_enabled

        if agent.trigger_group_filters is not None:
            resolved_config["group_filters"] = agent.trigger_group_filters

        if agent.trigger_number_filters is not None:
            resolved_config["number_filters"] = agent.trigger_number_filters

        if agent.context_message_count is not None:
            resolved_config["context_message_count"] = agent.context_message_count

        if agent.context_char_limit is not None:
            resolved_config["context_char_limit"] = agent.context_char_limit

        # Semantic Search Configuration (Phase 4.8)
        if hasattr(agent, 'enable_semantic_search'):
            resolved_config["enable_semantic_search"] = agent.enable_semantic_search
        if hasattr(agent, 'semantic_search_results'):
            resolved_config["semantic_search_results"] = agent.semantic_search_results
        if hasattr(agent, 'semantic_similarity_threshold'):
            resolved_config["semantic_similarity_threshold"] = agent.semantic_similarity_threshold
        if hasattr(agent, 'chroma_db_path'):
            resolved_config["chroma_db_path"] = agent.chroma_db_path

        # Agent-specific model config (always per-agent, no fallback needed)
        resolved_config["model_provider"] = agent.model_provider
        resolved_config["model_name"] = agent.model_name
        resolved_config["system_prompt"] = agent.system_prompt
        # Note: enabled_tools deprecated - using Skills system
        resolved_config["keywords"] = agent.keywords or []

        return resolved_config

    def _should_include_tool_context(self, message_text: str, context: Dict) -> bool:
        """
        Detect if the current message is likely a continuation of a tool-related task.

        This prevents tool context from being injected into unrelated conversations
        while allowing follow-up questions about tool results.

        Args:
            message_text: Current user message
            context: Memory context dict containing working_memory

        Returns:
            True if tool context should be included, False otherwise
        """
        try:
            message_lower = message_text.lower()

            # Keywords that suggest user wants to continue with tool context
            tool_continuation_keywords = [
                # Result references
                'result', 'results', 'output', 'findings', 'found',
                # Scan/security related
                'scan', 'vulnerability', 'vulnerabilities', 'security',
                # Explicit references
                'the scan', 'that scan', 'previous', 'last time',
                'what did you find', 'what was found', 'show me',
                # Follow-up indicators
                'more details', 'explain', 'tell me more', 'elaborate',
                # Tool-specific
                'nuclei', 'nmap', 'httpx', 'tool'
            ]

            # Check if message contains continuation keywords
            has_continuation_keyword = any(
                keyword in message_lower
                for keyword in tool_continuation_keywords
            )

            if has_continuation_keyword:
                self.logger.debug(f"Tool continuation keyword detected in message")
                return True

            # Check if there was a recent tool execution in context
            working_memory = context.get('working_memory', [])
            if working_memory:
                # Check last few messages for tool output metadata
                recent_tool_usage = False
                for msg in working_memory[-5:]:  # Last 5 messages
                    metadata = msg.get('metadata', {})
                    if metadata.get('is_tool_output'):
                        recent_tool_usage = True
                        break

                # If there was recent tool usage and message is very short,
                # it might be a follow-up (but not necessarily)
                if recent_tool_usage and len(message_text.split()) <= 5:
                    # Short messages after tool execution might be follow-ups
                    # But we're conservative - only include if keywords present
                    self.logger.debug("Recent tool usage detected but no keywords - excluding tool context")

            return False

        except Exception as e:
            self.logger.warning(f"Error in tool context detection: {e}")
            return False  # Default to not including tool context


    def _get_agent_tenant_id(self, agent_id: int) -> Optional[str]:
        """
        Get tenant_id for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            tenant_id string or None
        """
        from models import Agent

        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            return agent.tenant_id if agent else None
        except Exception as e:
            self.logger.error(f"Error getting tenant_id for agent {agent_id}: {e}")
            return None

    def _get_agent_persona_id(self, agent_id: int) -> Optional[int]:
        """
        Phase 9.3: Get persona_id for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            persona_id integer or None
        """
        from models import Agent

        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            return agent.persona_id if agent else None
        except Exception as e:
            self.logger.error(f"Error getting persona_id for agent {agent_id}: {e}")
            return None

    def _resolve_mcp_api_url(self, agent_id: int) -> str:
        """
        Phase 8: Resolve MCP API URL for an agent based on tenant_id
        Phase 10: Use agent's specific whatsapp_integration_id if set

        Looks up the active WhatsApp MCP instance for the agent.
        Falls back to tenant's first instance or default URL (backward compatibility).

        Args:
            agent_id: Agent ID

        Returns:
            MCP API URL (e.g., http://127.0.0.1:8080/api)
        """
        url, _ = self._resolve_mcp_instance(agent_id)
        return url

    def _resolve_mcp_instance(self, agent_id: int) -> tuple:
        """
        Phase Security-1: Resolve MCP API URL and secret for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Tuple of (mcp_api_url, api_secret)
        """
        from models import WhatsAppMCPInstance

        default_url = "http://127.0.0.1:8080/api"

        try:
            # Get agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                self.logger.warning(f"Agent {agent_id} not found, using default MCP URL")
                return (default_url, None)

            # Phase 10: If agent has specific whatsapp_integration_id, use that
            if agent.whatsapp_integration_id:
                instance = self.db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.id == agent.whatsapp_integration_id,
                    WhatsAppMCPInstance.status.in_(["running", "starting"])
                ).first()

                if instance:
                    self.logger.debug(f"Resolved MCP URL for agent {agent_id} via whatsapp_integration_id: {instance.mcp_api_url}")
                    return (instance.mcp_api_url, instance.api_secret)
                else:
                    self.logger.warning(f"Agent {agent_id}'s whatsapp_integration_id={agent.whatsapp_integration_id} not found or not running")

            # If agent has no tenant_id, fall back to default (backward compatibility)
            if not agent.tenant_id:
                self.logger.debug(f"Agent {agent_id} has no tenant_id, using default MCP URL")
                return (default_url, None)

            # Fallback: Find active AGENT MCP instance for tenant (NOT tester!)
            # CRITICAL: Must filter by instance_type="agent" to prevent sending via tester phone
            instance = self.db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == agent.tenant_id,
                WhatsAppMCPInstance.instance_type == "agent",  # CRITICAL: Only use agent instances!
                WhatsAppMCPInstance.status.in_(["running", "starting"])
            ).first()

            if instance:
                self.logger.debug(f"Resolved MCP URL for agent {agent_id} via tenant: {instance.mcp_api_url}")
                return (instance.mcp_api_url, instance.api_secret)
            else:
                self.logger.warning(f"No active MCP instance for tenant {agent.tenant_id}, using default URL")
                return (default_url, None)

        except Exception as e:
            self.logger.error(f"Error resolving MCP URL for agent {agent_id}: {e}", exc_info=True)
            return (default_url, None)

    def _validate_recipient_for_channel(self, recipient: str, channel: str) -> bool:
        """
        Validate that a recipient identifier is appropriate for the target channel.

        This prevents cross-channel contamination where Telegram IDs are sent to WhatsApp
        or phone numbers are sent to Telegram.

        Args:
            recipient: Recipient identifier (phone number, Telegram ID, etc.)
            channel: Target channel ("whatsapp" or "telegram")

        Returns:
            True if recipient is valid for the channel, False otherwise
        """
        import re

        # Normalize recipient (remove @ suffixes, + prefix)
        normalized = recipient.split('@')[0].lstrip('+')

        if channel == "whatsapp":
            # WhatsApp expects phone numbers (10-15 digits with optional + prefix)
            # Also accepts WhatsApp IDs with @s.whatsapp.net or @lid suffixes
            if '@' in recipient:
                # Already formatted with suffix, assume valid
                return True

            # Check if it's a valid phone number format
            if re.match(r'^\+?\d{10,15}$', recipient):
                return True

            # Telegram IDs are typically 8-10 digits without + prefix
            # If it looks like a Telegram ID (short numeric without +), flag it
            if normalized.isdigit() and len(normalized) <= 10 and not recipient.startswith('+'):
                self.logger.error(
                    f"🚫 BLOCKED: Telegram ID '{recipient}' cannot be used as WhatsApp recipient! "
                    "This would send to an unauthorized/unknown contact."
                )
                return False

            return True

        elif channel == "telegram":
            # Telegram expects numeric chat IDs
            if not normalized.isdigit():
                self.logger.error(
                    f"🚫 BLOCKED: Invalid Telegram recipient '{recipient}' (must be numeric chat ID)"
                )
                return False
            return True

        return True  # Unknown channel, allow (will fail later)

    async def _send_message(
        self,
        recipient: str,
        message_text: str,
        channel: str = "whatsapp",
        agent_id: int = None,
        media_path: str = None
    ) -> bool:
        """
        Phase 10.1.1: Universal message sender supporting WhatsApp and Telegram.
        Cross-channel contamination fix: Validates recipients before sending.

        Args:
            recipient: Chat ID (WhatsApp) or Telegram chat_id
            message_text: Message content
            channel: "whatsapp" or "telegram"
            agent_id: Agent ID for MCP URL resolution (WhatsApp only)
            media_path: Optional media file path (audio, image, etc.)

        Returns:
            True if message sent successfully
        """
        try:
            # CRITICAL: Validate recipient for channel to prevent cross-channel contamination
            if not self._validate_recipient_for_channel(recipient, channel):
                self.logger.error(
                    f"❌ Message blocked: Recipient '{recipient}' is invalid for channel '{channel}'"
                )
                return False

            if channel == "telegram":
                if not self.telegram_sender:
                    self.logger.error("TelegramSender not initialized")
                    return False

                return await self.telegram_sender.send_message(
                    chat_id=int(recipient),
                    message=message_text
                )

            elif channel == "whatsapp":
                # Phase Security-1: Resolve MCP URL and secret for WhatsApp
                mcp_url, api_secret = self._resolve_mcp_instance(agent_id) if agent_id else (None, None)

                # Check connection before sending
                if agent_id and not self._check_mcp_connection(agent_id, mcp_url):
                    self.logger.warning(f"[SKIP] MCP not connected, skipping message to {recipient}")
                    return False

                return await self.mcp_sender.send_message(
                    recipient,
                    message_text,
                    media_path=media_path,
                    api_url=mcp_url,
                    api_secret=api_secret
                )

            else:
                self.logger.error(f"Unknown channel: {channel}")
                return False

        except Exception as e:
            self.logger.error(f"Error sending message via {channel}: {e}", exc_info=True)
            return False

    def _check_mcp_connection(self, agent_id: int, mcp_api_url: str) -> bool:
        """
        Phase 0 (WhatsApp MCP UI Fixes): Check if MCP instance is connected before sending

        Prevents message queue replay by verifying WhatsApp device is authenticated.
        If device is unlinked, messages should NOT be sent to avoid queue buildup.

        Args:
            agent_id: Agent ID (for logging)
            mcp_api_url: MCP API URL to check

        Returns:
            True if connected and ready to send, False otherwise
        """
        import httpx

        try:
            # If no URL provided, assume default is available (backward compatibility)
            if not mcp_api_url or mcp_api_url == "http://127.0.0.1:8080/api":
                # For default URL, skip check (assume always available for backward compat)
                return True

            # Call health endpoint to check connection status
            health_url = f"{mcp_api_url}/health"
            response = httpx.get(health_url, timeout=5.0)

            if response.status_code == 200:
                health_data = response.json()
                connected = health_data.get("connected", False)

                if not connected:
                    self.logger.warning(
                        f"MCP instance for agent {agent_id} is NOT authenticated. "
                        f"Skipping message send to prevent queue buildup. "
                        f"User needs to scan QR code at {mcp_api_url}/qr-code"
                    )
                    return False

                # Connected and authenticated
                return True
            else:
                self.logger.warning(
                    f"MCP health check failed for agent {agent_id}: HTTP {response.status_code}. "
                    f"Skipping message send."
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Failed to check MCP connection for agent {agent_id}: {e}. "
                f"Skipping message send to be safe.",
                exc_info=True
            )
            return False

    def _select_agent(self, message: Dict, trigger_type: str):
        """
        Phase 7.3: Select which agent to use based on:
        -1. Saved agent preference (UserAgentSession) - ABSOLUTE HIGHEST PRIORITY
        0. Agent mention (@agent_name) - HIGHEST PRIORITY (works in both groups and DMs)
        1. Keyword matching in message (any user can invoke any agent via keywords)
        2. Contact-agent mapping (for DMs only, as fallback)
        3. Default agent (fallback for DMs without contact mapping)

        Phase 10: Filter by whatsapp_integration_id when mcp_instance_id is set

        Returns: (agent_config_dict, agent_id, agent_name)
        """
        message_text = message.get("body", "").lower()
        sender = message.get("sender", "")
        is_group = message.get("is_group", False)

        # Phase 10: Helper to check if agent is valid for this MCP instance
        def is_agent_valid_for_channel(agent: Agent) -> bool:
            """Check if agent has current channel enabled and is assigned to the right integration"""
            if not self.mcp_instance_id and not self.telegram_instance_id:
                return True  # No filtering if no instance set (backward compat)

            # Parse enabled channels
            enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                json.loads(agent.enabled_channels) if agent.enabled_channels else ["playground", "whatsapp"]
            )

            # WhatsApp channel check
            if self.mcp_instance_id:
                if "whatsapp" not in enabled_channels:
                    self.logger.debug(f"Agent {agent.id} has WhatsApp disabled, skipping")
                    return False

                if agent.whatsapp_integration_id and agent.whatsapp_integration_id != self.mcp_instance_id:
                    self.logger.debug(f"Agent {agent.id} assigned to different MCP instance ({agent.whatsapp_integration_id}), skipping")
                    return False

            # Phase 10.1.1: Telegram channel check
            if self.telegram_instance_id:
                if "telegram" not in enabled_channels:
                    self.logger.debug(f"Agent {agent.id} has Telegram disabled, skipping")
                    return False

                if agent.telegram_integration_id and agent.telegram_integration_id != self.telegram_instance_id:
                    self.logger.debug(f"Agent {agent.id} assigned to different Telegram instance ({agent.telegram_integration_id}), skipping")
                    return False

            return True

        # Step -1: Check for saved agent preference (agent switcher persistence)
        # This takes absolute priority - once user switches agents, it persists
        from models import UserAgentSession
        sender_key = self._get_sender_key(message)
        try:
            saved_session = self.db.query(UserAgentSession).filter(
                UserAgentSession.user_identifier == sender_key
            ).first()

            if saved_session:
                agent = self.db.query(Agent).filter(Agent.id == saved_session.agent_id).first()
                if agent and agent.is_active and is_agent_valid_for_channel(agent):
                    self.logger.info(f"Using saved agent preference: {agent.id} for {sender_key}")
                    return self._agent_to_config(agent), agent.id, self._get_agent_name(agent)
                else:
                    # Saved agent no longer active or not valid for channel, clear preference
                    self.db.delete(saved_session)
                    self.db.commit()
                    self.logger.warning(f"Cleared invalid agent preference for {sender_key}")
        except Exception as e:
            self.logger.error(f"Error checking agent preference: {e}")

        # Step 0: Check for SPECIFIC agent mention (HIGHEST PRIORITY)
        # Works in BOTH groups and DMs: "@agendador me lembre de X"
        # Example: "@xuculento, bora organizar um churras?" (group)
        # Example: "@agendador me lembre em 5 minutos" (DM)
        if self.contact_service:
            mentioned_agent_contact = self.contact_service.get_mentioned_agent(message.get("body", ""))
            if mentioned_agent_contact:
                # Find the agent associated with this contact
                agent = self.db.query(Agent).filter(
                    Agent.contact_id == mentioned_agent_contact.id,
                    Agent.is_active == True
                ).first()
                if agent and is_agent_valid_for_channel(agent):
                    self.logger.info(f"Agent @{mentioned_agent_contact.friendly_name} mentioned, routing to agent: {agent.id}")
                    return self._agent_to_config(agent), agent.id, self._get_agent_name(agent)

        # Step 1: Check for keyword-based invocation (second priority)
        # Keywords work for any user in both groups and DMs
        # Phase 10: Filter by channel assignment
        active_agents = self.db.query(Agent).filter(Agent.is_active == True).all()
        for agent in active_agents:
            if not is_agent_valid_for_channel(agent):
                continue
            # Parse keywords (handle both list and JSON string)
            keywords = agent.keywords if isinstance(agent.keywords, list) else (json.loads(agent.keywords) if agent.keywords else [])
            for keyword in keywords:
                if keyword.lower() in message_text:
                    self.logger.info(f"Keyword '{keyword}' matched, using agent: {agent.id}")
                    return self._agent_to_config(agent), agent.id, self._get_agent_name(agent)

        # Step 2: Check contact-agent mapping (for DMs only, as fallback after mentions/keywords)
        # NOTE: External bot routing should be configured via ContactAgentMapping in database,
        # NOT hardcoded in code. Use POST /api/contacts + POST /api/contact-agent-mappings
        # CRITICAL FIX 2026-01-08: Also search by WhatsApp ID for contact lookup
        if not is_group:
            # Try to find contact by phone number OR WhatsApp ID
            # Normalize sender to handle WhatsApp IDs (e.g., "193853382488108")
            sender_normalized = sender.split('@')[0].lstrip('+')

            # Method 1: Search by phone number (traditional)
            contact = self.db.query(Contact).filter(
                or_(
                    Contact.phone_number == sender,
                    Contact.phone_number == sender_normalized,
                    Contact.phone_number == f"+{sender_normalized}"
                )
            ).first()

            # Method 2: If not found, search by WhatsApp ID
            if not contact:
                contact = self.db.query(Contact).filter(Contact.whatsapp_id == sender_normalized).first()
                if contact:
                    self.logger.info(f"Contact found by WhatsApp ID: {contact.friendly_name} (ID: {sender_normalized})")

            # If contact found (by either method), check for agent mapping
            if contact:
                mapping = self.db.query(ContactAgentMapping).filter(
                    ContactAgentMapping.contact_id == contact.id
                ).first()
                if mapping:
                    agent = self.db.query(Agent).filter(Agent.id == mapping.agent_id).first()
                    if agent and agent.is_active and is_agent_valid_for_channel(agent):
                        self.logger.info(f"✅ CONTACT MAPPING: {contact.friendly_name} → Agent {agent.id} (priority over default)")
                        return self._agent_to_config(agent), agent.id, self._get_agent_name(agent)
                else:
                    self.logger.info(f"Contact {contact.friendly_name} found but has no agent mapping")

        # FIX: For group messages, ONLY route if mention or keyword matched
        # Don't fall back to default agent for group messages without explicit invocation
        if is_group:
            self.logger.info("Group message with no mention/keyword match - not routing to any agent")
            return None, None, None

        # Step 3: Default agent (fallback for DMs only - LOWEST PRIORITY)
        # Phase 10: Also check channel validity for default agent
        # MONITORING 2026-01-08: Log default agent usage for audit
        default_agent = self.db.query(Agent).filter(Agent.is_default == True).first()
        if default_agent and is_agent_valid_for_channel(default_agent):
            self.logger.warning(f"⚠️ DEFAULT AGENT FALLBACK: Using agent {default_agent.id} for {sender} (no contact mapping, no mention, no keyword)")
            self.logger.warning(f"📊 AUDIT: Sender {sender} | Trigger: {trigger_type} | Default fallback used")
            return self._agent_to_config(default_agent), default_agent.id, self._get_agent_name(default_agent)

        # Fallback to config-based agent (backward compatibility)
        self.logger.warning("No agent found, using config-based agent")
        return self.config, None, self.config.get("agent_name", "Agent")

    def _agent_to_config(self, agent: Agent) -> Dict:
        """Convert Agent model to config dict for AgentService"""
        # Note: enabled_tools deprecated - using Skills system

        # Build system prompt with persona or tone (Phase 5.2)
        system_prompt = agent.system_prompt

        # Check if agent has a persona linked (Phase 5.2)
        if agent.persona_id:
            from models import Persona
            persona = self.db.query(Persona).filter(Persona.id == agent.persona_id).first()
            if persona:
                # Build comprehensive persona injection
                persona_text = self._build_persona_context(persona)
                # Replace {{PERSONA}} placeholder if present, otherwise append
                if "{{PERSONA}}" in system_prompt:
                    system_prompt = system_prompt.replace("{{PERSONA}}", persona_text)
                elif "{{TONE}}" in system_prompt:
                    system_prompt = system_prompt.replace("{{TONE}}", persona_text)
                else:
                    system_prompt = f"{system_prompt}\n\n{persona_text}"
        # Fallback to legacy tone system
        elif agent.tone_preset_id:
            tone_preset = self.db.query(TonePreset).filter(TonePreset.id == agent.tone_preset_id).first()
            if tone_preset:
                system_prompt = system_prompt.replace("{{TONE}}", tone_preset.description)
        elif agent.custom_tone:
            system_prompt = system_prompt.replace("{{TONE}}", agent.custom_tone)

        return {
            "model_provider": agent.model_provider,
            "model_name": agent.model_name,
            "system_prompt": system_prompt,
            "memory_size": self.config.get("memory_size", 10),  # Inherit from config
            "response_template": agent.response_template if hasattr(agent, 'response_template') else "@{agent_name}: {response}"
        }

    def _build_persona_context(self, persona) -> str:
        """Build comprehensive persona context for system prompt injection (Phase 5.2)"""
        parts = []

        # Role and identity
        if persona.role:
            parts.append(f"ROLE: {persona.role}")
            if persona.role_description:
                parts.append(f"{persona.role_description}")

        # Tone and communication style
        if persona.custom_tone:
            parts.append(f"\nCOMMUNICATION STYLE:\n{persona.custom_tone}")
        elif persona.tone_preset_id:
            from models import TonePreset
            tone_preset = self.db.query(TonePreset).filter(TonePreset.id == persona.tone_preset_id).first()
            if tone_preset:
                parts.append(f"\nCOMMUNICATION STYLE:\n{tone_preset.description}")

        # Personality traits
        if persona.personality_traits:
            parts.append(f"\nPERSONALITY TRAITS: {persona.personality_traits}")

        # Guardrails and constraints
        if persona.guardrails:
            parts.append(f"\nGUARDRAILS:\n{persona.guardrails}")

        return "\n".join(parts) if parts else ""

    def _get_agent_name(self, agent: Agent) -> str:
        """Get agent's friendly name from Contact table"""
        contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
        return contact.friendly_name if contact else f"Agent {agent.id}"

    def _find_active_conversation_thread(self, sender: str) -> ConversationThread:
        """
        Phase 8.0: Find active conversation thread for this sender.

        ConversationThread is the new unified way to track multi-turn conversations
        within flow steps.

        Args:
            sender: Phone number or WhatsApp ID of sender (may include @s.whatsapp.net suffix)

        Returns:
            ConversationThread if active conversation found, None otherwise
        """
        try:
            # Normalize sender - extract just the phone number or WhatsApp ID
            # Handle formats like "5500000000001@s.whatsapp.net" or "180216945205454@lid"
            normalized_sender = sender.split('@')[0].lstrip('+')

            # Build list of possible recipient formats to match against
            possible_recipients = [
                sender,                           # Original format
                normalized_sender,                # Just the number/ID (no + prefix)
                f"+{normalized_sender}",          # With + prefix
                f"{normalized_sender}@s.whatsapp.net",  # WhatsApp JID format (personal)
                f"{normalized_sender}@lid"        # WhatsApp Business ID format (used by bots)
            ]

            # Bug Fix 2026-01-07: Check if sender is a WhatsApp Business ID that maps to a contact's phone
            # Enhancement 2026-01-07: Auto-discover WhatsApp IDs for contacts
            # Bug Fix 2026-01-11: Add bidirectional lookup (phone_number -> whatsapp_id)
            # This handles both cases:
            # 1. Thread recipient is phone number but bot replies from WhatsApp ID
            # 2. Thread recipient is WhatsApp ID but user replies from phone number
            try:
                from models import Contact
                # Check if sender matches any contact's whatsapp_id
                contact = self.db.query(Contact).filter(
                    Contact.whatsapp_id == normalized_sender
                ).first()

                # NEW: If no contact found with this WhatsApp ID, try auto-discovery
                if not contact:
                    from services.whatsapp_id_discovery import WhatsAppIDDiscovery
                    discovery = WhatsAppIDDiscovery(time_window_minutes=60)
                    contact = discovery.auto_link_contact(self.db, normalized_sender, self.logger)

                    if contact:
                        self.logger.info(
                            f"🔗 AUTO-DISCOVERED: WhatsApp ID {normalized_sender} → "
                            f"Contact '{contact.friendly_name}' (phone: {contact.phone_number})"
                        )

                if contact and contact.phone_number:
                    # Add contact's phone number to possible recipients
                    contact_phone = contact.phone_number.lstrip('+')
                    additional_formats = [
                        contact.phone_number,
                        contact_phone,
                        f"+{contact_phone}",
                        f"{contact_phone}@s.whatsapp.net",
                        f"{contact_phone}@lid"
                    ]
                    possible_recipients.extend(additional_formats)
                    self.logger.info(f"Sender {normalized_sender} is WhatsApp ID for contact {contact.friendly_name} (phone: {contact.phone_number}) - added phone formats to match")

                # Bug Fix 2026-01-11: REVERSE LOOKUP - Check if sender is a phone number that maps to a WhatsApp ID
                # This handles the case where thread was created with WhatsApp ID but reply comes from phone number
                if not contact:
                    # Check if sender matches any contact's phone_number
                    contact_by_phone = self.db.query(Contact).filter(
                        or_(
                            Contact.phone_number == normalized_sender,
                            Contact.phone_number == f"+{normalized_sender}",
                            Contact.phone_number == sender  # Original format
                        )
                    ).first()

                    if contact_by_phone and contact_by_phone.whatsapp_id:
                        # Add contact's WhatsApp ID to possible recipients
                        whatsapp_id = contact_by_phone.whatsapp_id.lstrip('+')
                        additional_formats = [
                            contact_by_phone.whatsapp_id,
                            whatsapp_id,
                            f"+{whatsapp_id}",
                            f"{whatsapp_id}@s.whatsapp.net",
                            f"{whatsapp_id}@lid"
                        ]
                        possible_recipients.extend(additional_formats)
                        self.logger.info(f"Sender {normalized_sender} is phone number for contact {contact_by_phone.friendly_name} (WhatsApp ID: {contact_by_phone.whatsapp_id}) - added WhatsApp ID formats to match")

            except Exception as e:
                self.logger.debug(f"Contact lookup for thread matching failed: {e}")

            self.logger.debug(f"Looking for thread with recipients: {possible_recipients}")

            # Query for active conversation threads matching any format
            thread = self.db.query(ConversationThread).filter(
                ConversationThread.recipient.in_(possible_recipients),
                ConversationThread.status == 'active'
            ).order_by(ConversationThread.last_activity_at.desc()).first()

            if thread:
                self.logger.info(f"Found active conversation thread (ID={thread.id}) for sender {sender} (matched: {thread.recipient})")
                return thread
            else:
                # Log at INFO level to make debugging easier
                self.logger.info(f"No active conversation thread found for sender {sender} (checked: {possible_recipients})")

            return None

        except Exception as e:
            self.logger.error(f"Error finding active conversation thread: {e}", exc_info=True)
            return None

    def _should_block_post_completion(self, sender: str) -> bool:
        import os as os_module

        post_completion_block_seconds = int(os_module.getenv("POST_COMPLETION_BLOCK_SECONDS", "300"))
        sender_normalized = sender.split('@')[0]

        recent_completed = self.db.query(ConversationThread).filter(
            ConversationThread.recipient.contains(sender_normalized),
            ConversationThread.status.in_(['completed', 'goal_achieved', 'timeout']),
            ConversationThread.completed_at >= datetime.utcnow() - timedelta(seconds=post_completion_block_seconds)
        ).order_by(ConversationThread.completed_at.desc()).first()

        if not recent_completed:
            return False

        seconds_ago = int((datetime.utcnow() - recent_completed.completed_at).total_seconds())

        is_loop_closure = recent_completed.goal_summary and "FORCED CLOSURE" in recent_completed.goal_summary
        if is_loop_closure:
            loop_block_seconds = int(os_module.getenv("LOOP_CLOSURE_BLOCK_SECONDS", "1800"))
            if seconds_ago < loop_block_seconds:
                self.logger.warning(
                    f"[LOOP PREVENTION BLOCK] Thread {recent_completed.id} was force-closed {seconds_ago}s ago. "
                    f"Blocking all messages from {sender} for {loop_block_seconds}s to protect API quota."
                )
                return True

        self.logger.warning(
            f"[POST-COMPLETION BLOCK] Ignoring message from {sender} - "
            f"Thread {recent_completed.id} completed {seconds_ago}s ago (window: {post_completion_block_seconds}s)"
        )
        return True

    def _detect_conversation_stagnation(self, thread: ConversationThread) -> bool:
        """
        Detect if conversation is stuck in a loop with no progress.

        Prevents bot-to-bot infinite loops by detecting repetitive patterns.

        FIX 5: Enhanced to detect similar (not just identical) responses and
        external bot repetition patterns.

        Returns True if:
        - Same user message repeated 2+ times (lowered from 3)
        - Similar agent responses repeated 3+ times (using similarity check)
        - External bot asks the same question repeatedly
        - More than 5 turns with no new information exchanged

        Args:
            thread: ConversationThread to analyze

        Returns:
            bool: True if conversation is stagnant and should be stopped
        """
        try:
            if not thread or not thread.conversation_history:
                return False

            # FIX 5: Lowered threshold - need at least 4 messages to detect patterns
            if len(thread.conversation_history) < 4:
                return False

            # Analyze recent conversation (last 8 messages for better pattern detection)
            recent = thread.conversation_history[-8:]

            # Extract messages by role
            user_messages = [m['content'].lower().strip() for m in recent if m.get('role') == 'user']
            agent_messages = [m['content'].lower().strip() for m in recent if m.get('role') == 'agent']

            # FIX 5: Check for repeated user messages (external bot sending same thing)
            # Lowered threshold from 3 to 2
            if len(user_messages) >= 2:
                last_two_user = user_messages[-2:]
                if len(set(last_two_user)) == 1:  # Both are identical
                    self.logger.warning(f"Thread {thread.id}: User message repeated 2 times: '{last_two_user[0][:50]}...'")
                    return True

            # FIX 5: Check for SIMILAR agent responses (not just identical)
            # This catches cases where agent responds slightly differently but with same structure
            if len(agent_messages) >= 3:
                last_three_agent = agent_messages[-3:]

                # Check for identical responses
                if len(set(last_three_agent)) == 1:
                    self.logger.warning(f"Thread {thread.id}: Agent response repeated 3 times: '{last_three_agent[0][:50]}...'")
                    return True

                # Check for similar responses (e.g., all start with "Compreendido" or "@movl:")
                similar_starts = []
                for msg in last_three_agent:
                    # Extract first 30 chars as signature
                    signature = msg[:30]
                    similar_starts.append(signature)

                # If all 3 have the same signature, likely a loop
                if len(set(similar_starts)) == 1:
                    self.logger.warning(f"Thread {thread.id}: Agent responses have similar structure (loop detected): '{similar_starts[0]}...'")
                    return True

            # FIX 5: Detect external bot "Há mais algo que eu possa fazer por você?" loop
            # This specific pattern was the main culprit in the JT flow
            external_bot_loop_patterns = [
                "há mais algo que eu possa fazer",
                "anything else i can help",
                "algo mais",
                "something else",
                "outras dúvidas",
                "other questions",
            ]

            import re
            user_loop_count = 0
            for user_msg in user_messages[-4:]:  # Check last 4 user messages
                if any(pattern in user_msg for pattern in external_bot_loop_patterns):
                    user_loop_count += 1

            if user_loop_count >= 2:
                self.logger.warning(f"Thread {thread.id}: External bot asking same question {user_loop_count} times")
                return True

            # Check for alternating identical exchanges (A->B->A->B->A->B pattern)
            if len(user_messages) >= 2 and len(agent_messages) >= 2:
                # Check if user is sending same thing repeatedly AND agent responding with same thing
                recent_user_unique = len(set(user_messages[-2:]))
                recent_agent_unique = len(set(agent_messages[-2:]))

                if recent_user_unique == 1 and recent_agent_unique == 1 and len(recent) >= 4:
                    self.logger.warning(f"Thread {thread.id}: Alternating loop detected (same user question, same agent answer)")
                    return True

            return False

        except Exception as e:
            self.logger.error(f"Error detecting conversation stagnation: {e}", exc_info=True)
            return False

    def _find_active_conversation(self, sender: str) -> ScheduledEvent:
        """
        Phase 6.4 Week 3: Find active conversation for this sender (legacy).

        Note: This is the legacy method using ScheduledEvent.
        Phase 8.0 prefers ConversationThread but this remains for backward compatibility.

        Args:
            sender: Phone number or WhatsApp ID of sender

        Returns:
            ScheduledEvent if active conversation found, None otherwise
        """
        try:
            # Query for active conversation events
            active_conversations = self.db.query(ScheduledEvent).filter(
                ScheduledEvent.event_type == 'CONVERSATION',
                ScheduledEvent.status == 'ACTIVE'
            ).all()

            # Check each conversation's payload for matching recipient
            for conversation in active_conversations:
                try:
                    payload = json.loads(conversation.payload)
                    if payload.get('recipient') == sender:
                        self.logger.info(f"Found active conversation (ID={conversation.id}) for sender {sender}")
                        return conversation
                except json.JSONDecodeError:
                    continue

            return None

        except Exception as e:
            self.logger.error(f"Error finding active conversation: {e}", exc_info=True)
            return None

    async def route_message(self, message: Dict, trigger_type: str):
        """
        Process a message through the agent and save the run.
        Phase 4.5: Now supports keyword-based agent selection and contact-agent mapping.
        """
        sender_key = self._get_sender_key(message)
        message_text = message.get("body", "")
        message_timestamp = message.get("timestamp", 0)
        sender_name = message.get("sender_name", "Unknown")

        # Phase 4.2: Identify sender using ContactService
        sender = message.get("sender", "")
        if self.contact_service and sender:
            contact = self.contact_service.identify_sender(sender)
            if contact:
                sender_name = contact.friendly_name

        self.logger.info(f"Routing message from {sender_key} (trigger: {trigger_type})")

        # SAFETY CHECK 1: Age check
        # Warn if message is older than 1 hour (3600 seconds)
        # This helps detect if we are processing historical messages
        current_time = datetime.utcnow().timestamp()
        if isinstance(message_timestamp, (int, float)) and message_timestamp > 0:
             # Normalize timestamp (some are in ms)
            ts = message_timestamp if message_timestamp < 10000000000 else message_timestamp / 1000
            age_seconds = current_time - ts
            if age_seconds > 3600:
                self.logger.warning(f"[SAFETY WARN] Processing old message! Age: {int(age_seconds)}s from {sender_key}")

        # SAFETY CHECK 2: Prevent self-replies (agent replying to itself)
        # This prevents infinite loops where the agent's own outgoing messages trigger responses.
        # Note: The QA/tester phone sending TO the agent is a valid test scenario and should NOT be blocked.
        # The dm_auto_mode=False setting on the tester instance already prevents the tester from auto-replying.
        agent_phone = getattr(self, '_agent_phone_number', None)
        if agent_phone and agent_phone in sender_key:
            self.logger.warning(f"[SAFETY BLOCK] Preventing self-reply (agent's own message from {sender_key})")
            return

        # Cache the message
        self._cache_message(message, matched=True)

        # Phase 10.2 Option B: Auto-resolve group message senders to existing contacts
        # This runs early to ensure channel mappings are created before any other processing
        is_group = message.get("is_group", False)
        if is_group and sender:
            try:
                # Get tenant_id for contact resolution
                tenant_id = "default"
                if self.mcp_instance_id:
                    from models import WhatsAppMCPInstance
                    mcp_instance = self.db.query(WhatsAppMCPInstance).get(self.mcp_instance_id)
                    if mcp_instance:
                        tenant_id = mcp_instance.tenant_id

                # Attempt auto-resolution
                resolver = GroupSenderResolver(self.db)
                resolved_contact = resolver.auto_resolve_group_sender(
                    sender=sender,
                    sender_name=sender_name,
                    tenant_id=tenant_id,
                    chat_id=message.get("chat_id")
                )

                if resolved_contact:
                    # Update sender_name to resolved contact's friendly_name
                    sender_name = resolved_contact.friendly_name
                    self.logger.info(
                        f"[GROUP_RESOLVER] Resolved sender to contact: {sender_name}"
                    )
            except Exception as e:
                self.logger.warning(f"[GROUP_RESOLVER] Auto-resolution failed: {e}")
                # Continue processing - this is non-critical

        # Phase 16: Detect and execute slash commands BEFORE any other processing
        # This allows users to use /commands in WhatsApp, not just the playground
        if message_text.startswith('/'):
            slash_result = await self._handle_slash_command(
                sender_key=sender_key,
                message_text=message_text,
                message=message,
                trigger_type=trigger_type
            )
            if slash_result and slash_result.get("handled"):
                self.logger.info(f"[SLASH] Command handled: {message_text[:50]}")
                return

        # Phase 8.0: Check for active conversation thread FIRST (highest priority)
        active_thread = self._find_active_conversation_thread(sender)

        # Post-completion blocking - configurable window to prevent loops
        # Default: 300 seconds (5 minutes), configurable via POST_COMPLETION_BLOCK_SECONDS env var
        # ALSO check for force-closed threads (loop prevention) which get a LONGER block period
        if not active_thread and self._should_block_post_completion(sender):
            return

        if active_thread:
            # BUG FIX 2026-01-11: Check for thread timeout (30 min inactivity for immediate conversations)
            # This prevents stale threads from hijacking future messages
            timeout_minutes = 30
            if active_thread.last_activity_at:
                time_since_activity = datetime.utcnow() - active_thread.last_activity_at
                if time_since_activity > timedelta(minutes=timeout_minutes):
                    self.logger.warning(f"[TIMEOUT] Thread {active_thread.id} timed out after {timeout_minutes} min inactivity")
                    active_thread.status = 'timeout'
                    active_thread.completed_at = datetime.utcnow()
                    active_thread.goal_summary = f'Thread timed out after {timeout_minutes} minutes of inactivity'
                    self.db.commit()
                    active_thread = None  # Allow normal processing

            # BUG FIX 2026-01-11: Check for scheduling intent breakout
            # If user sends a clear scheduling request during a thread, process it via skills instead
            scheduling_breakout_keywords = [
                'me lembre', 'lembre-me', 'lembrar', 'remind me', 'reminder',
                'agendar', 'schedule', 'agendamento', 'scheduling'
            ]
            should_breakout = any(kw in message_text.lower() for kw in scheduling_breakout_keywords)

            if active_thread and should_breakout:
                self.logger.info(f"[SCHEDULER BREAKOUT] Detected scheduling intent in thread {active_thread.id}, processing via skills")
                # Clear active_thread to allow normal skill processing
                # We'll continue the thread after, if the scheduler doesn't handle it
                active_thread_backup = active_thread
                active_thread = None

        if active_thread:
            self.logger.info(f"[CONVERSATION THREAD] Routing message to conversation thread handler (Thread ID={active_thread.id})")

            # Check for conversation stagnation (bot-to-bot loop prevention)
            # FIX 5: Lowered threshold from turn 5 to turn 3 for earlier loop detection
            if active_thread.current_turn >= 3:  # Start checking after turn 3
                if self._detect_conversation_stagnation(active_thread):
                    self.logger.warning(f"[STAGNATION] Conversation stagnation detected for thread {active_thread.id}, stopping conversation")
                    active_thread.status = 'completed'
                    active_thread.goal_achieved = False
                    active_thread.goal_summary = "Conversation stopped due to lack of progress (bot-to-bot loop detected)"
                    active_thread.completed_at = datetime.utcnow()
                    self.db.commit()

                    # Send a final message to notify the user
                    recipient = message.get("chat_id") or sender
                    thread_agent_id = active_thread.agent_id
                    channel = message.get("channel", "whatsapp")

                    final_msg = "Desculpe, parece que estamos tendo dificuldades para avançar. Encerrando esta conversa."
                    await self._send_message(
                        recipient=recipient,
                        message_text=final_msg,
                        channel=channel,
                        agent_id=thread_agent_id
                    )

                    self.logger.info(f"[STAGNATION] Thread {active_thread.id} marked as completed due to stagnation")
                    return

            # Get agent_id from thread
            thread_agent_id = active_thread.agent_id

            # Phase 8: Emit activity start event for watcher graph view
            thread_tenant_id = self._get_agent_tenant_id(thread_agent_id)
            if thread_tenant_id:
                emit_agent_processing_async(
                    tenant_id=thread_tenant_id,
                    agent_id=thread_agent_id,
                    status="start",
                    sender_key=sender_key,
                    channel=message.get("channel", "whatsapp")
                )

            # Process audio transcription if needed
            if thread_agent_id and message.get("media_type"):
                self.logger.info(f"Audio message detected in conversation thread, transcribing...")
                processed_text, skip_ai, skill_output, skill_type, _ = await self._process_with_skills(thread_agent_id, message)
                if processed_text != message_text:
                    self.logger.info(f"[SUCCESS] Audio transcribed for thread: {len(processed_text)} chars")
                    message_text = processed_text

            # Process reply through the thread
            result = await self._process_conversation_thread_reply(
                thread=active_thread,
                sender=sender,
                message_content=message_text,
                message_id=message.get("id")
            )

            # Send reply if needed
            if result.get('should_reply') and result.get('reply_content'):
                # Bug Fix 2026-01-11: Always reply to thread's original recipient, not message source
                # This prevents replies from going to groups when user replies from a group
                recipient = active_thread.recipient
                channel = message.get("channel", "whatsapp")

                # CRITICAL FIX 2026-01-18: Strip agent identity prefix BEFORE sending
                reply_text = result['reply_content']
                reply_text = re.sub(r"^@?\w+:\s*", "", reply_text, flags=re.IGNORECASE).strip()

                self.logger.info(f"[THREAD REPLY] Sending to {recipient}: '{reply_text[:80]}...'")

                success = await self._send_message(
                    recipient=recipient,
                    message_text=reply_text,
                    channel=channel,
                    agent_id=thread_agent_id
                )
                if success:
                    self.logger.info(f"[SUCCESS] Thread reply sent to {recipient} via {channel}")
                else:
                    self.logger.error(f"[ERROR] Failed to send thread reply to {recipient} via {channel}")

            # Phase 8: Emit activity end event for watcher graph view
            if thread_tenant_id:
                emit_agent_processing_async(
                    tenant_id=thread_tenant_id,
                    agent_id=thread_agent_id,
                    status="end",
                    sender_key=sender_key,
                    channel=message.get("channel", "whatsapp")
                )

            self.logger.info("[SUCCESS] Message processed by conversation thread handler, skipping normal flow")
            return

        # Phase 6.4 Week 3: Check for active conversation (legacy ScheduledEvent)
        active_conversation = self._find_active_conversation(sender)
        if active_conversation:
            self.logger.info(f"[CONVERSATION] Routing message to active conversation handler (Event ID={active_conversation.id})")

            # Get agent_id from conversation payload
            try:
                conversation_payload = json.loads(active_conversation.payload)
                conversation_agent_id = conversation_payload.get('agent_id')
            except:
                conversation_agent_id = None
                self.logger.warning("Could not extract agent_id from conversation payload")

            # Phase 8: Emit activity start event for watcher graph view
            conv_tenant_id = self._get_agent_tenant_id(conversation_agent_id) if conversation_agent_id else None
            if conv_tenant_id:
                emit_agent_processing_async(
                    tenant_id=conv_tenant_id,
                    agent_id=conversation_agent_id,
                    status="start",
                    sender_key=sender_key,
                    channel=message.get("channel", "whatsapp")
                )

            # IMPORTANT: Process audio transcription BEFORE sending to conversation handler
            if conversation_agent_id and message.get("media_type"):
                self.logger.info(f"Audio message detected in conversation, transcribing...")
                processed_text, skip_ai, skill_output, skill_type, _ = await self._process_with_skills(conversation_agent_id, message)
                if processed_text != message_text:
                    self.logger.info(f"[SUCCESS] Audio transcribed for conversation: {len(processed_text)} chars")
                    message_text = processed_text

            # Process conversation reply (AWAIT the async method)
            result = await self.scheduler_service.process_conversation_reply(
                event_id=active_conversation.id,
                sender=sender,
                message_content=message_text
            )

            # Send reply if needed
            if result.get('should_reply') and result.get('reply_content'):
                recipient = message.get("chat_id") or sender
                channel = message.get("channel", "whatsapp")

                success = await self._send_message(
                    recipient=recipient,
                    message_text=result['reply_content'],
                    channel=channel,
                    agent_id=conversation_agent_id
                )
                if success:
                    self.logger.info(f"[SUCCESS] Conversation reply sent to {recipient} via {channel}")
                else:
                    self.logger.error(f"[ERROR] Failed to send conversation reply to {recipient} via {channel}")

            # Phase 8: Emit activity end event for watcher graph view
            if conv_tenant_id:
                emit_agent_processing_async(
                    tenant_id=conv_tenant_id,
                    agent_id=conversation_agent_id,
                    status="end",
                    sender_key=sender_key,
                    channel=message.get("channel", "whatsapp")
                )

            # Skip normal agent processing - conversation handled
            self.logger.info("[SUCCESS] Message processed by conversation handler, skipping normal flow")
            return

        # Check for maintenance mode
        if self.config.get("maintenance_mode", False):
            maintenance_message = self.config.get("maintenance_message", "[MAINTENANCE] The bot is currently under maintenance. Please try again later.")
            self.logger.info(f"Maintenance mode active, sending maintenance message")

            # Send maintenance message directly without AI processing
            recipient = message.get("chat_id", "")
            channel = message.get("channel", "whatsapp")
            await self._send_message(
                recipient=recipient,
                message_text=maintenance_message,
                channel=channel,
                agent_id=None
            )
            return

        # Phase 10: Group Handler Check - prevent duplicate responses from multiple MCP instances
        # When multiple phone numbers are in the same group, only the designated group handler responds
        is_group = message.get("is_group", False)
        if is_group and self.mcp_instance_id:
            from models import WhatsAppMCPInstance
            mcp_instance = self.db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.id == self.mcp_instance_id
            ).first()

            if mcp_instance and not mcp_instance.is_group_handler:
                self.logger.info(
                    f"[GROUP DEDUP] Skipping group message - MCP instance {self.mcp_instance_id} "
                    f"({mcp_instance.phone_number}) is not the group handler for this tenant"
                )
                return

        # Phase 4.5: Select appropriate agent
        agent_config, agent_id, agent_name = self._select_agent(message, trigger_type)

        # FIX: If no agent selected (e.g., group message without mention/keyword), skip processing
        if agent_config is None or agent_id is None:
            self.logger.info(f"No agent selected for this message - skipping processing")
            return

        self.logger.info(f"Selected agent: {agent_name} (ID: {agent_id})")

        # Phase 8: Emit activity start event early (covers both skill-handled and AI paths)
        agent_tenant_id_early = self._get_agent_tenant_id(agent_id)
        if agent_tenant_id_early:
            emit_agent_processing_async(
                tenant_id=agent_tenant_id_early,
                agent_id=agent_id,
                status="start",
                sender_key=sender_key,
                channel=message.get("channel", "whatsapp")
            )

        # Phase 15: Skill Projects - Check for project commands and sessions
        # This must happen BEFORE skills processing to intercept project commands
        project_result = await self._handle_project_commands(
            agent_id=agent_id,
            sender_key=sender_key,
            message_text=message_text,
            message=message,
            trigger_type=trigger_type
        )

        # Phase 15: Track project context for memory scoping
        current_project_id = None
        current_project_name = None

        if project_result:
            # Project command or message was handled
            if project_result.get("handled"):
                return
            # Update message_text if it was modified (e.g., project context added)
            if project_result.get("modified_message"):
                message_text = project_result["modified_message"]
            # Track project context for memory scoping
            current_project_id = project_result.get("project_id")
            current_project_name = project_result.get("project_name")
            if current_project_id:
                self.logger.info(f"[PROJECT] Processing message in project context: {current_project_name} (ID: {current_project_id})")

        # Phase 5.0: Process message with skills (e.g., audio transcription) BEFORE AI processing
        processed_message_text, skip_ai, skill_output, processed_skill_type, skill_media_paths = await self._process_with_skills(agent_id, message)
        if processed_message_text != message_text:
            self.logger.info(f"Message processed by skills: {len(message_text)} -> {len(processed_message_text)} chars")
            message_text = processed_message_text

        # If skill requested to skip AI (e.g., transcript_only mode), send skill output directly
        if skip_ai and skill_output:
            self.logger.info("Skill requested to skip AI processing, sending output directly")
            recipient = message.get("chat_id") or message.get("sender")
            channel = message.get("channel", "whatsapp")

            # Phase 14.5: Send skill media files (screenshots, images) if available
            if skill_media_paths:
                self.logger.info(f"Skill produced {len(skill_media_paths)} media files to send")
                for media_path in skill_media_paths:
                    media_success = await self._send_message(
                        recipient=recipient,
                        message_text="",  # Empty caption for image
                        channel=channel,
                        agent_id=agent_id,
                        media_path=media_path
                    )
                    if media_success:
                        self.logger.info(f"Media sent to {channel}: {media_path}")
                    else:
                        self.logger.error(f"Failed to send media to {channel}: {media_path}")

                    # Cleanup temporary file after sending (with delay for upload)
                    try:
                        import os
                        import asyncio
                        await asyncio.sleep(3)  # Wait for upload to complete
                        if os.path.exists(media_path):
                            os.unlink(media_path)
                            self.logger.info(f"Cleaned up temporary media file: {media_path}")
                    except Exception as cleanup_error:
                        self.logger.warning(f"Failed to clean up media file: {cleanup_error}")

            # Phase 10.1.1: Use channel-aware sending for skill responses
            success = await self._send_message(
                recipient=recipient,
                message_text=skill_output,
                channel=channel,
                agent_id=agent_id
            )

            if success:
                self.logger.info(f"Response sent to {channel}: {recipient}")
            else:
                self.logger.error(f"Failed to send skill response to {channel}: {recipient}")

            # Note: We don't save agent_run here since no AI processing occurred
            # The skill handled everything

            # Phase 8: Emit activity end event for skill-handled path
            if agent_tenant_id_early:
                emit_agent_processing_async(
                    tenant_id=agent_tenant_id_early,
                    agent_id=agent_id,
                    status="end",
                    sender_key=sender_key,
                    channel=message.get("channel", "whatsapp")
                )
            return

        # Phase 5.0: If skill produced output but didn't request skip_ai, include it in context for AI
        # This allows the AI to incorporate skill results into its response with personality
        if skill_output and not skip_ai:
            self.logger.info(f"Including skill output in AI context ({len(skill_output)} chars)")
            # Format skill output clearly so AI understands it should use this data
            skill_context = f"""IMPORTANT: A skill has already executed and returned results. Use these results to answer the user's request.

SKILL RESULTS:
{skill_output}

USER'S ORIGINAL REQUEST:
{message_text}

INSTRUCTIONS: Present the skill results above in your response with your personality. The user asked: "{message_text}". The skill has already found the answer - present it to them now."""
            message_text = skill_context

        # CRITICAL SAFETY CHECK: Prevent empty messages from reaching AI
        # Empty messages can cause AI hallucination and unintended tool execution
        if not message_text or message_text.strip() == "":
            self.logger.error(f"[SAFETY] Empty message detected for agent {agent_id}, blocking AI processing")
            error_message = "❌ Sorry, I couldn't process your message. If you sent an audio message, there was an issue with the audio transcription. Please try sending a text message or resending the audio."
            recipient = message.get("chat_id") or message.get("sender")
            channel = message.get("channel", "whatsapp")

            await self._send_message(
                recipient=recipient,
                message_text=error_message,
                channel=channel,
                agent_id=agent_id
            )
            return

        # Translate contact IDs to names in message text
        translated_message = self._translate_contact_ids(message_text)

        # Get is_group flag and chat_id
        is_group = message.get("is_group", False)
        chat_id = message.get("chat_id") if is_group else None  # Only use chat_id for groups

        # Phase 21: Sentinel Security Analysis BEFORE memory storage
        # This prevents memory poisoning from blocked messages in WhatsApp/Telegram channels
        tenant_id = self._get_agent_tenant_id(agent_id)
        if tenant_id:
            try:
                from services.sentinel_service import SentinelService
                sentinel = SentinelService(self.db, tenant_id)

                sentinel_result = await sentinel.analyze_prompt(
                    prompt=message_text,
                    agent_id=agent_id,
                    sender_key=sender_key,
                    source=None,  # User message - no internal source tag
                )

                if sentinel_result.is_threat_detected and sentinel_result.action == "blocked":
                    self.logger.warning(
                        f"🛡️ SENTINEL (WhatsApp/Telegram): Blocking message BEFORE memory storage - "
                        f"{sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Send blocked response and return early (no memory storage = no poisoning)
                    blocked_response = sentinel_result.threat_reason or "Message blocked for security reasons."
                    recipient = message.get("chat_id") or message.get("sender")
                    channel = message.get("channel", "whatsapp")
                    await self._send_message(
                        recipient=recipient,
                        message_text=blocked_response,
                        channel=channel,
                        agent_id=agent_id
                    )
                    return
                elif sentinel_result.is_threat_detected:
                    # detect_only mode: threat detected but allowed - will proceed to store message
                    self.logger.info(
                        f"🛡️ SENTINEL (detect_only): Threat detected but allowing - "
                        f"{sentinel_result.detection_type}"
                    )
            except Exception as e:
                self.logger.warning(f"Sentinel pre-check failed, allowing message: {e}")

        # Phase 4.8: Add to agent-scoped memory (with automatic fact extraction)
        # Item 10: Contact-based memory support with WhatsApp ID resolution
        # Phase 10.1.1: Telegram ID support for cross-channel memory
        # Phase 15: Project-scoped memory when in project context
        message_id = message.get("id")
        telegram_id = message.get("telegram_id")  # Phase 10.1.1
        await self.memory_manager.add_message(
            agent_id=agent_id,
            sender_key=sender_key,
            role="user",
            content=message_text,
            message_id=message_id,
            metadata={
                "sender_name": sender_name,
                "is_group": is_group,
                "project_id": current_project_id,  # Phase 15: Track project in metadata
                "project_name": current_project_name
            },
            chat_id=chat_id,  # For channel_isolated mode
            whatsapp_id=sender,  # Item 10: For contact resolution
            telegram_id=telegram_id,  # Phase 10.1.1: Telegram contact resolution
            use_contact_mapping=True,  # Item 10: Enable contact-based memory
            project_id=current_project_id  # Phase 15: Project-scoped memory
        )

        # Add context based on message type
        if is_group:
            self.logger.info(f"Group message detected from {sender_name}")

            # Build chronological context (last N messages)
            context_prefix = self._build_group_context(message)

            # Phase 4.8: Add semantic search results from agent-scoped memory
            # Item 10: Now with contact-based memory support
            # Phase 15: Project-scoped memory when in project context
            semantic_context = ""
            if self.config.get("enable_semantic_search", False):
                self.logger.info("Semantic search enabled for group message")
                context = await self.memory_manager.get_context(
                    agent_id=agent_id,
                    sender_key=sender_key,
                    current_message=message_text,
                    max_semantic_results=self.config.get("semantic_search_results", 5),
                    similarity_threshold=self.config.get("semantic_similarity_threshold", 0.3),
                    include_knowledge=True,  # Include learned facts
                    include_shared=self.config.get("enable_shared_memory", True),  # Phase 4.8 Week 4
                    chat_id=chat_id,  # For channel_isolated mode
                    whatsapp_id=sender,  # Item 10: For contact resolution
                    telegram_id=telegram_id,  # Phase 10.2: Telegram contact resolution
                    use_contact_mapping=True,  # Item 10: Enable contact-based memory
                    project_id=current_project_id  # Phase 15: Project-scoped memory
                )
                # Format context for display (Phase 4.8 Week 3: pass sender_key for adaptive personality)
                # Fix: Use freshness detection to determine if tool context should be included
                agent_memory = self.memory_manager.get_agent_memory(agent_id)
                include_tool_context = self._should_include_tool_context(message_text, context)
                semantic_context = agent_memory.format_context_for_prompt(
                    context,
                    user_id=sender_key,
                    include_tool_outputs=include_tool_context
                )
                self.logger.info(f"Semantic context generated: {len(semantic_context)} chars (tool_context={include_tool_context})")

            # Combine all contexts
            parts = []
            if context_prefix:
                parts.append(context_prefix)
            if semantic_context and semantic_context != "No previous context":
                parts.append(semantic_context)

            if parts:
                full_context = "\n\n".join(parts)
                translated_message = f"{full_context}\n\n[Current message from {sender_name}]: {translated_message}"
                self.logger.info(f"Group context added: {len(full_context)} chars")
            else:
                self.logger.warning("No context available - sending message without context")
                translated_message = f"[Message from {sender_name}]: {translated_message}"
        else:
            # Phase 4.8: Direct message - add semantic context from agent-scoped memory
            # Item 10: Now with contact-based memory support
            # Phase 15: Project-scoped memory when in project context
            if self.config.get("enable_semantic_search", False):
                context = await self.memory_manager.get_context(
                    agent_id=agent_id,
                    sender_key=sender_key,
                    current_message=message_text,
                    max_semantic_results=self.config.get("semantic_search_results", 5),
                    similarity_threshold=self.config.get("semantic_similarity_threshold", 0.3),
                    include_knowledge=True,  # Include learned facts
                    include_shared=self.config.get("enable_shared_memory", True),  # Phase 4.8 Week 4
                    whatsapp_id=sender,  # Item 10: For contact resolution
                    telegram_id=telegram_id,  # Phase 10.2: Telegram contact resolution
                    use_contact_mapping=True,  # Item 10: Enable contact-based memory
                    project_id=current_project_id  # Phase 15: Project-scoped memory
                )
                # Format and prepend semantic context (Phase 4.8 Week 3: pass sender_key for adaptive personality)
                # Fix: Use freshness detection to determine if tool context should be included
                agent_memory = self.memory_manager.get_agent_memory(agent_id)
                include_tool_context = self._should_include_tool_context(message_text, context)
                context_str = agent_memory.format_context_for_prompt(
                    context,
                    user_id=sender_key,
                    include_tool_outputs=include_tool_context
                )
                if context_str and context_str != "[No previous context]":
                    translated_message = f"{context_str}\n\n[Current message from {sender_name}]: {translated_message}"
                else:
                    translated_message = f"[Message from {sender_name}]: {translated_message}"
            else:
                translated_message = f"[Message from {sender_name}]: {translated_message}"

        # Layer 5: Selective tool output injection
        # - Always show lightweight reference (what tools are available)
        # - Inject full output only when user explicitly requests it (via /inject or natural language)
        tool_buffer = get_tool_output_buffer()
        tool_buffer.increment_message_count(agent_id, sender_key)
        tool_context = tool_buffer.get_context_for_injection(agent_id, sender_key, message_text)
        if tool_context:
            translated_message = f"{tool_context}\n\n{translated_message}"
            self.logger.info(f"Injected Layer 5 tool context ({len(tool_context)} chars)")

        # Phase 4.5: Create AgentService with selected agent's config
        # Note: Each invocation gets fresh config from selected agent
        # Phase 4.6: Pass database session for API key loading
        # Phase 5.0: Pass agent_id for knowledge base access
        # Phase 4.8: Ring buffer memory deprecated, removed from AgentService
        # Phase 7.2: Pass token_tracker for usage tracking
        # Phase: Custom Tools Hub - Get tenant_id and create callback for long-running tools
        # Phase 9.3: Get persona_id for custom tool discovery
        agent_tenant_id = self._get_agent_tenant_id(agent_id)
        agent_persona_id = self._get_agent_persona_id(agent_id)

        # Create callback for long-running tool notifications
        # Capture channel from message context for proper routing
        callback_channel = message.get("channel", "whatsapp")
        async def on_tool_complete(recipient: str, message_text: str):
            """Send follow-up message when long-running tool completes"""
            await self._send_message(
                recipient=recipient,
                message_text=message_text,
                channel=callback_channel,
                agent_id=agent_id
            )

        temp_agent_service = AgentService(
            agent_config,
            contact_service=self.contact_service,
            db=self.db,
            agent_id=agent_id,
            token_tracker=self.token_tracker,
            tenant_id=agent_tenant_id,
            persona_id=agent_persona_id,
            on_tool_complete_callback=on_tool_complete
        )

        # Phase 7.2: Create agent_run record first to get ID for token tracking
        # We'll update it with results later
        from models import AgentRun as AgentRunModel
        agent_run = AgentRunModel(
            agent_id=agent_id,
            triggered_by=trigger_type,
            sender_key=sender_key,
            input_preview=message_text[:200],
            status="processing"
        )
        self.db.add(agent_run)
        self.db.commit()
        self.db.refresh(agent_run)
        agent_run_id = agent_run.id

        # Phase 8: Note - activity start event is emitted earlier (after agent selection)
        # to cover both skill-handled and AI processing paths

        # Process through agent with translated message
        # Phase 5.0: Pass original message_text for knowledge base search (better semantic matching)
        # Phase 7.2: Pass agent_run_id and message_id for token tracking
        result = await temp_agent_service.process_message(
            sender_key,
            translated_message,
            original_query=message_text,
            agent_run_id=agent_run_id,
            message_id=None  # Will be set if available
        )

        # Phase 4.8: Add assistant response to agent-scoped memory (triggers fact extraction)
        # Item 10: Contact-based memory support
        # Fix: Add is_tool_output metadata to prevent tool context bleeding into new conversations
        if result.get('answer'):
            # Build metadata for memory storage
            memory_metadata = {}
            memory_content = result['answer']

            if result.get('tool_used'):
                memory_metadata['is_tool_output'] = True
                memory_metadata['tool_used'] = result.get('tool_used')

                # Layer 5: Store FULL tool output in ephemeral buffer for follow-up interactions
                # This enables agentic analysis of tool results without polluting long-term memory
                tool_name = result.get('tool_used', 'unknown')
                # Extract command name from tool_used (format: "custom:tool_name" or "tool_name.command")
                command_name = "execute"
                if ':' in tool_name:
                    tool_name = tool_name.split(':')[1]
                if '.' in tool_name:
                    parts = tool_name.split('.')
                    tool_name = parts[0]
                    command_name = parts[1] if len(parts) > 1 else "execute"

                execution_id = tool_buffer.add_tool_output(
                    agent_id=agent_id,
                    sender_key=sender_key,
                    tool_name=tool_name,
                    command_name=command_name,
                    output=result['answer']
                )
                self.logger.info(f"Stored tool output in Layer 5 buffer: #{execution_id} {tool_name}.{command_name}")
                memory_metadata['execution_id'] = execution_id

                # Fix: Store summarized tool result to prevent context bleeding
                # The full result goes to the user, but memory gets a concise summary
                memory_content = summarize_tool_result(
                    result['answer'],
                    result.get('tool_used', 'unknown')
                )
                self.logger.debug(f"Tool result summarized for memory: {memory_content}")

            await self.memory_manager.add_message(
                agent_id=agent_id,
                sender_key=sender_key,
                role="assistant",
                content=memory_content,  # Fix: Use summarized content for tool outputs
                message_id=None,  # Assistant messages don't have IDs
                metadata=memory_metadata,  # Fix: Include tool metadata
                chat_id=chat_id,  # For channel_isolated mode
                whatsapp_id=sender,  # Item 10: For contact resolution
                telegram_id=telegram_id,  # Phase 10.2: Telegram contact resolution
                use_contact_mapping=True  # Item 10: Enable contact-based memory
            )

            # Task 3: Call post_response_hook for knowledge_sharing skill
            await self._invoke_post_response_hooks(
                agent_id=agent_id,
                user_message=message_text,
                agent_response=result['answer'],
                context={
                    "sender_key": sender_key,
                    "sender_name": sender_name,
                    "is_group": is_group,
                    "chat_id": chat_id
                },
                ai_client=temp_agent_service.ai_client
            )

        # Save agent run
        self._save_agent_run(
            sender_key=sender_key,
            trigger_type=trigger_type,
            input_text=message_text,
            result=result,
            agent_id=agent_id,  # Phase 4.5: Track which agent was used
            skill_type=processed_skill_type,  # Phase 6.x: Track which skill processed this
            agent_config=agent_config,  # Pass agent config for correct model tracking
            agent_run_id=agent_run_id  # Phase 7.2: Update existing run
        )

        # Phase 4.8: Memory persistence now handled by Multi-Agent Memory Manager
        # Ring buffer _save_memory() deprecated

        response_text = result.get('answer', '')
        if response_text:
            self.logger.info(f"Agent response: {response_text[:100]}")
        else:
            self.logger.warning("No response generated (AI call may have failed)")

        # Send response back to WhatsApp
        if response_text and not result.get('error'):
            # Format response using agent's response template
            response_template = agent_config.get("response_template", "@{agent_name}: {response}")
            formatted_response = response_template.format(
                agent_name=agent_name,
                response=response_text
            )

            recipient = message.get("chat_id", "")  # Use chat_id for reply

            # Phase 7.3: Check if agent has TTS skill enabled
            audio_path = None
            try:
                tts_skill_config = await self.skill_manager.get_skill_config(
                    db=self.db,
                    agent_id=agent_id,
                    skill_type="audio_tts"
                )

                # Note: Use 'is not None' because empty config {} is valid but falsy
                if tts_skill_config is not None:
                    self.logger.info("TTS skill enabled for this agent, converting response to audio")

                    # Get TTS skill instance
                    from agent.skills.audio_tts_skill import AudioTTSSkill
                    tts_skill = AudioTTSSkill(token_tracker=self.token_tracker)
                    # TTS-001 Fix: Set db_session so provider can access API keys from database
                    tts_skill.set_db_session(self.db)

                    # Process response through TTS
                    tts_result = await tts_skill.process_response(
                        response_text=formatted_response,
                        config=tts_skill_config,
                        agent_id=agent_id,
                        sender_key=sender_key,
                        message_id=message.get("id")
                    )

                    if tts_result.success and tts_result.metadata.get("audio_path"):
                        audio_path = tts_result.metadata["audio_path"]
                        self.logger.info(f"TTS audio generated: {audio_path}")
                    else:
                        self.logger.warning(f"TTS generation failed: {tts_result.output}")
                        # Fall back to text response

            except Exception as tts_error:
                self.logger.error(f"Error processing TTS: {tts_error}", exc_info=True)
                # Fall back to text response

            # Send response (audio or text)
            # Phase 10.1.1: Detect channel and send via appropriate method
            channel = message.get("channel", "whatsapp")

            # CRITICAL FIX 2026-01-18: Strip agent identity prefix BEFORE sending (normal message path)
            formatted_response = re.sub(r"^@?\w+:\s*", "", formatted_response, flags=re.IGNORECASE).strip()

            # ImageSkill: Send generated images BEFORE text response
            tool_media_paths = result.get('media_paths')
            if tool_media_paths:
                self.logger.info(f"Sending {len(tool_media_paths)} media files from tool execution")
                for media_path in tool_media_paths:
                    media_success = await self._send_message(
                        recipient=recipient,
                        message_text="",  # Empty caption for image
                        channel=channel,
                        agent_id=agent_id,
                        media_path=media_path
                    )
                    if media_success:
                        self.logger.info(f"Media sent to {channel}: {media_path}")
                    else:
                        self.logger.error(f"Failed to send media to {channel}: {media_path}")

                    # Cleanup temporary file after sending (with delay for upload)
                    try:
                        import asyncio
                        await asyncio.sleep(3)  # Wait for upload to complete
                        if os.path.exists(media_path):
                            os.unlink(media_path)
                            self.logger.info(f"Cleaned up temporary media file: {media_path}")
                    except Exception as cleanup_error:
                        self.logger.warning(f"Failed to clean up media file: {cleanup_error}")

            success = await self._send_message(
                recipient=recipient,
                message_text=formatted_response,
                channel=channel,
                agent_id=agent_id,
                media_path=audio_path
            )

            if success:
                if audio_path:
                    self.logger.info(f"Audio response sent to {channel}: {recipient}")
                else:
                    self.logger.info(f"Response sent to {channel}: {recipient}")
            else:
                self.logger.error(f"Failed to send response to {channel}: {recipient}")

            # Clean up temporary audio file after sending
            # CRITICAL: Delay cleanup to prevent race condition!
            # WhatsApp MCP needs time to fully upload the audio file
            if audio_path:
                try:
                    import os
                    import asyncio
                    # VOICE-003 Fix: Configurable cleanup delay (default 5 seconds)
                    cleanup_delay = float(os.getenv("TTS_CLEANUP_DELAY_SECONDS", "5"))
                    await asyncio.sleep(cleanup_delay)
                    if os.path.exists(audio_path):
                        os.unlink(audio_path)
                        self.logger.info(f"Cleaned up temporary audio file: {audio_path}")
                except Exception as cleanup_error:
                    self.logger.warning(f"Failed to clean up audio file: {cleanup_error}")

        # Phase 8: Emit activity end event for watcher graph view (non-blocking)
        emit_agent_processing_async(
            tenant_id=agent_tenant_id,
            agent_id=agent_id,
            status="end",
            sender_key=sender_key,
            channel=message.get("channel", "whatsapp")
        )

    def _get_sender_key(self, message: Dict) -> str:
        """Generate sender key (chat_id for groups, sender for direct)"""
        if message.get("is_group"):
            return message.get("chat_id", "")
        else:
            return message.get("sender", "")

    def _cache_message(self, message: Dict, matched: bool):
        """
        Cache message to local database.
        Phase 10.2: Resolves sender_name via ContactChannelMappingService for consistent contact display.
        HIGH-012: Now stores tenant_id for multi-tenant message isolation.
        """
        # Check if already cached
        existing = self.db.query(MessageCache).filter_by(source_id=message["id"]).first()
        if existing:
            return

        # Phase 10.2: Resolve sender_name via contact mapping
        sender_name = message.get("sender_name")
        channel = message.get("channel")
        sender = message.get("sender")

        # Get tenant_id for contact resolution
        tenant_id = "default"
        if self.telegram_instance_id:
            from models import TelegramBotInstance
            bot_instance = self.db.query(TelegramBotInstance).get(self.telegram_instance_id)
            if bot_instance:
                tenant_id = bot_instance.tenant_id
        elif self.mcp_instance_id:
            from models import WhatsAppMCPInstance
            mcp_instance = self.db.query(WhatsAppMCPInstance).get(self.mcp_instance_id)
            if mcp_instance:
                tenant_id = mcp_instance.tenant_id

        # Try to resolve contact via channel mapping
        if sender and channel:
            try:
                from services.contact_channel_mapping_service import ContactChannelMappingService
                mapping_service = ContactChannelMappingService(self.db)

                # Determine channel identifier based on channel type
                channel_identifier = None
                channel_type = None

                if channel == "telegram":
                    # For Telegram, sender is the telegram user ID
                    channel_identifier = sender.lstrip("+")
                    channel_type = "telegram"
                elif channel == "whatsapp":
                    # For WhatsApp, try phone number first (with normalization)
                    channel_identifier = sender.lstrip("+")
                    channel_type = "phone"

                    # Also try whatsapp_id if available in message
                    whatsapp_id = message.get("whatsapp_id")
                    if whatsapp_id:
                        contact = mapping_service.get_contact_by_channel("whatsapp", whatsapp_id.lstrip("+"), tenant_id)
                        if contact and contact.is_active:
                            sender_name = contact.friendly_name
                            self.logger.debug(f"Resolved sender via WhatsApp ID mapping: {sender_name}")
                            channel_identifier = None  # Skip phone lookup below

                # Try channel mapping resolution if not yet resolved
                if channel_identifier and channel_type:
                    contact = mapping_service.get_contact_by_channel(channel_type, channel_identifier, tenant_id)
                    if contact and contact.is_active:
                        sender_name = contact.friendly_name
                        self.logger.debug(f"Resolved sender via {channel_type} mapping: {sender_name} (contact_id: {contact.id})")
                    else:
                        self.logger.debug(f"No contact mapping found for {channel_type}: {channel_identifier} (tenant: {tenant_id})")

            except Exception as e:
                self.logger.warning(f"Failed to resolve sender via contact mapping: {e}")
                # Fall back to raw sender_name from message

        cached = MessageCache(
            source_id=message["id"],
            chat_id=message.get("chat_id", ""),
            chat_name=message.get("chat_name"),
            sender=message.get("sender"),
            sender_name=sender_name,  # Now resolved via contact mapping
            body=message.get("body", ""),
            timestamp=message.get("timestamp", 0),
            is_group=bool(message.get("is_group", 0)),
            matched_filter=matched,
            channel=message.get("channel"),  # Phase 10.1.1: Track channel for analytics
            tenant_id=tenant_id  # HIGH-012: Multi-tenant message isolation
        )
        self.db.add(cached)
        self.db.commit()

    def _save_agent_run(self, sender_key: str, trigger_type: str, input_text: str, result: Dict, agent_id=None, skill_type=None, agent_config=None, agent_run_id=None):
        """
        Save agent execution details.
        Phase 4.5: Now tracks agent_id to know which agent handled the request.
        Phase 6.x: Now tracks skill_type for skill usage monitoring.
        Phase 7.2: Updates existing agent_run if agent_run_id provided
        """
        # Get model from agent config if provided, otherwise fallback to global config
        if agent_config:
            # Just use model_name directly for consistency (e.g., "gemini-2.5-flash", not "gemini/gemini-2.5-flash")
            model_used = agent_config.get("model_name", "gemini-2.5-flash")
        else:
            model_used = self.config.get("model_name", "gemini-2.5-flash")

        # Centralized contamination check BEFORE saving (applies to both update and create paths)
        answer = result.get("answer") or ""
        if answer:
            from .contamination_detector import get_contamination_detector
            detector = get_contamination_detector(db_session=self.db, agent_id=agent_id)
            contamination_pattern = detector.check(answer)
            if contamination_pattern:
                self.logger.error(f"ROUTER BLOCKING: Contamination in answer! Pattern: {contamination_pattern}, Answer: {answer[:200]}...")
                answer = "⚠️ Erro: Resposta contaminada bloqueada"
                result["answer"] = answer
                result["error"] = f"Contamination detected: {contamination_pattern}"

        if agent_run_id:
            # Phase 7.2: Update existing agent_run
            agent_run = self.db.query(AgentRun).filter(AgentRun.id == agent_run_id).first()
            if agent_run:
                agent_run.skill_type = skill_type
                agent_run.tool_used = result.get("tool_used")
                agent_run.tool_result = result.get("tool_result")
                agent_run.model_used = result.get("model_used", model_used)
                agent_run.token_usage_json = result.get("tokens")
                agent_run.output_preview = (result.get("answer") or "")[:500]
                agent_run.status = _determine_agent_run_status(result)
                agent_run.error_text = result.get("error") or agent_run.error_text
                agent_run.execution_time_ms = result.get("execution_time_ms")
                self.db.commit()
            else:
                self.logger.warning(f"AgentRun {agent_run_id} not found, creating new")
                # Fallback to creating new if not found
                agent_run_id = None

        if not agent_run_id:
            # Create new agent_run (legacy behavior)
            agent_run = AgentRun(
                agent_id=agent_id,  # Phase 4.5: Track which agent was used
                triggered_by=trigger_type,
                sender_key=sender_key,
                input_preview=input_text[:200],
                skill_type=skill_type,  # Track which skill processed this message
                tool_used=result.get("tool_used"),
                tool_result=result.get("tool_result"),  # Store raw tool response
                model_used=result.get("model_used", model_used),  # Use agent's configured model
                token_usage_json=result.get("tokens"),
                output_preview=(result.get("answer") or "")[:500],
                status=_determine_agent_run_status(result),
                error_text=result.get("error"),
                execution_time_ms=result.get("execution_time_ms")
            )
            self.db.add(agent_run)
            self.db.commit()

        # Phase 6.11.2: Broadcast agent run completion via WebSocket (fire-and-forget)
        try:
            import asyncio
            from app import app
            if hasattr(app.state, 'ws_manager'):
                # Use create_task for fire-and-forget broadcast (don't block commit)
                asyncio.create_task(app.state.ws_manager.broadcast({
                    "type": "agent_run_complete",
                    "data": {
                        "agent_id": agent_id,
                        "run_id": agent_run.id,
                        "status": agent_run.status,
                        "timestamp": datetime.utcnow().isoformat() + 'Z'
                    }
                }))
        except Exception as e:
            self.logger.error(f"Error broadcasting agent run: {e}", exc_info=True)

    # Phase 4.8: _save_memory() method deprecated
    # Ring buffer memory persistence now handled by Multi-Agent Memory Manager (ChromaDB)

    def _translate_contact_ids(self, message_text: str) -> str:
        """
        Translate contact IDs (like @123456789012345) to friendly names (like @Alice)
        """
        if not self.contact_mappings:
            return message_text

        translated = message_text
        for contact_id, contact_name in self.contact_mappings.items():
            # Replace @contact_id with @contact_name
            translated = translated.replace(f"@{contact_id}", f"@{contact_name}")

        return translated

    def _build_group_context(self, current_message: Dict) -> str:
        """
        Build context from recent group messages based on config.
        Returns formatted context string or empty string if no context available.
        """
        self.logger.info("=" * 80)
        self.logger.info("BUILDING GROUP CONTEXT")

        if not self.mcp_reader:
            self.logger.warning("No mcp_reader available - cannot fetch group context")
            return ""

        context_count = self.config.get("context_message_count", 5)
        context_char_limit = self.config.get("context_char_limit", 1000)

        self.logger.info(f"Context config: count={context_count}, char_limit={context_char_limit}")

        if context_count <= 0:
            self.logger.info("Context disabled (count=0)")
            return ""

        try:
            chat_id = current_message.get("chat_id")
            current_timestamp = current_message.get("timestamp")

            self.logger.info(f"Current message: chat_id={chat_id}, timestamp={current_timestamp}")

            if not chat_id or not current_timestamp:
                self.logger.warning("Missing chat_id or timestamp - cannot fetch context")
                return ""

            # Fetch recent messages from the same chat (before current message)
            # Using mcp_reader's get_recent_messages method
            from mcp_reader.sqlite_reader import MCPDatabaseReader
            if isinstance(self.mcp_reader, MCPDatabaseReader):
                self.logger.info(f"Fetching context: chat_id={chat_id}, timestamp<{current_timestamp}, limit={context_count}")

                # Use the new get_recent_messages method
                messages = self.mcp_reader.get_recent_messages(chat_id, current_timestamp, context_count)

                self.logger.info(f"Found {len(messages)} context messages")

                if not messages:
                    self.logger.info("No context messages found")
                    return ""

                # Build context string - process NEWEST first to prioritize recent messages
                # FIX: Changed from reversed(messages) to messages to ensure recent context
                # is included before hitting char limit
                context_lines = []
                total_chars = 0

                # Process messages in DESC order (newest first) to prioritize recent context
                for msg in messages:  # Already in DESC order from get_recent_messages()
                    timestamp = msg["timestamp"]
                    sender = msg.get("sender", "")
                    sender_name = msg["sender_name"]
                    body = msg["body"]

                    # Phase 4.8: Add to vector store via memory_manager if semantic search is enabled
                    # Note: This is for historical context messages, not the current message
                    # We skip this for now as it's handled by memory_manager.add_message elsewhere

                    # Phase 4.2: Use Contact Service to identify sender by their friendly name
                    display_name = sender_name  # Default to WhatsApp name
                    if self.contact_service and sender:
                        contact = self.contact_service.identify_sender(sender)
                        if contact:
                            display_name = contact.friendly_name

                    line = f"[{timestamp}] {display_name}: {body}"
                    line_length = len(line)

                    # Check char limit
                    if total_chars + line_length > context_char_limit:
                        # Truncate the line to fit
                        remaining = context_char_limit - total_chars
                        if remaining > 50:  # Only add if we have at least 50 chars space
                            line = line[:remaining] + "..."
                            context_lines.append(line)
                        break

                    context_lines.append(line)
                    total_chars += line_length + 1  # +1 for newline

                if context_lines:
                    # Reverse lines to show chronological order (oldest to newest)
                    context_lines_chronological = list(reversed(context_lines))
                    context_result = "Recent conversation:\n" + "\n".join(context_lines_chronological)
                    self.logger.info(f"Built group context with {len(context_lines)} messages, {total_chars} chars")
                    return context_result
                else:
                    self.logger.info("No context lines built (char limit too small?)")
            else:
                self.logger.warning("mcp_reader is not MCPDatabaseReader instance")

        except Exception as e:
            self.logger.error(f"Error building group context: {e}", exc_info=True)

        return ""

    async def _process_conversation_thread_reply(
        self,
        thread: ConversationThread,
        sender: str,
        message_content: str,
        message_id: Optional[str] = None
    ) -> Dict:
        """
        Phase 8.0: Process a reply to an active conversation thread.

        Args:
            thread: Active ConversationThread
            sender: Sender phone/ID
            message_content: Message text
            message_id: Optional message identifier for deduplication

        Returns:
            Dict with should_reply, reply_content, status, etc.
        """
        try:
            # CRITICAL: Loop prevention safeguards to protect API quota
            # 1. Absolute max turns - force close threads that run too long
            ABSOLUTE_MAX_TURNS = int(os.getenv("THREAD_ABSOLUTE_MAX_TURNS", "25"))
            if thread.current_turn >= ABSOLUTE_MAX_TURNS:
                self.logger.error(
                    f"[LOOP PREVENTION] Thread {thread.id} hit ABSOLUTE max turns ({ABSOLUTE_MAX_TURNS}). "
                    f"Force-closing to protect API quota."
                )
                thread.status = 'completed'
                thread.completed_at = datetime.utcnow()
                thread.goal_achieved = False
                thread.goal_summary = f"FORCED CLOSURE: Exceeded {ABSOLUTE_MAX_TURNS} turns (loop prevention)"
                self.db.commit()
                return {
                    "should_reply": False,
                    "reply_content": None,
                    "status": "loop_prevention_max_turns",
                    "thread_status": "completed"
                }

            # 2. Rate limiting - max messages per minute within a thread
            MAX_MESSAGES_PER_MINUTE = int(os.getenv("THREAD_MAX_MESSAGES_PER_MINUTE", "15"))
            if thread.conversation_history:
                from datetime import datetime as dt
                one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
                recent_messages = [
                    m for m in thread.conversation_history
                    if m.get('timestamp') and dt.fromisoformat(m['timestamp'].replace('Z', '+00:00').replace('+00:00', '')) > one_minute_ago
                ]
                if len(recent_messages) >= MAX_MESSAGES_PER_MINUTE:
                    self.logger.error(
                        f"[LOOP PREVENTION] Thread {thread.id} rate limited: "
                        f"{len(recent_messages)} messages in last minute (max: {MAX_MESSAGES_PER_MINUTE}). "
                        f"Force-closing to protect API quota."
                    )
                    thread.status = 'completed'
                    thread.completed_at = datetime.utcnow()
                    thread.goal_achieved = False
                    thread.goal_summary = f"FORCED CLOSURE: Rate limit exceeded ({len(recent_messages)} msgs/min)"
                    self.db.commit()
                    return {
                        "should_reply": False,
                        "reply_content": None,
                        "status": "loop_prevention_rate_limit",
                        "thread_status": "completed"
                    }

            # 3. Thread duration limit - force close threads running too long
            THREAD_MAX_DURATION_MINUTES = int(os.getenv("THREAD_MAX_DURATION_MINUTES", "30"))
            if thread.created_at:
                thread_duration = datetime.utcnow() - thread.created_at
                if thread_duration > timedelta(minutes=THREAD_MAX_DURATION_MINUTES):
                    self.logger.error(
                        f"[LOOP PREVENTION] Thread {thread.id} exceeded max duration "
                        f"({int(thread_duration.total_seconds() / 60)} min > {THREAD_MAX_DURATION_MINUTES} min). "
                        f"Force-closing to protect API quota."
                    )
                    thread.status = 'completed'
                    thread.completed_at = datetime.utcnow()
                    thread.goal_achieved = False
                    thread.goal_summary = f"FORCED CLOSURE: Exceeded {THREAD_MAX_DURATION_MINUTES} min duration"
                    self.db.commit()
                    return {
                        "should_reply": False,
                        "reply_content": None,
                        "status": "loop_prevention_duration",
                        "thread_status": "completed"
                    }

            # FIX 6: Detect external bot session end patterns
            # If external bot has closed the session, mark thread as completed and don't respond
            # CRITICAL: Only check after turn 3+ to avoid catching closure of PREVIOUS session
            import re
            message_lower = message_content.lower()
            session_ended = False

            # Only check for session end after turn 3 (to avoid catching previous session closure)
            if thread.current_turn >= 3:
                session_end_patterns = [
                    r"vamos encerrar o diálogo",
                    r"encerrar a sessão",
                    r"avaliação do serviço",
                    r"foi um prazer ajudar (você|vocês)",  # Past tense only, not "será"
                    r"agradecemos (sua confiança|por entrar em contato)",
                    r"até a próxima",
                    r"session (closed|ended|terminated)",
                    r"conversation (closed|ended|terminated)",
                    r"thank you for (contacting|calling)",
                ]
                session_ended = any(re.search(pattern, message_lower) for pattern in session_end_patterns)

            if session_ended:
                self.logger.info(f"Thread {thread.id}: External bot session end detected in message: '{message_content[:100]}...'")
                thread.status = 'completed'
                thread.completed_at = datetime.utcnow()
                thread.goal_achieved = True
                thread.goal_summary = "External bot closed the session"

                # Add user message to history before completing
                history = thread.conversation_history or []
                history.append({
                    "role": "user",
                    "content": message_content,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                thread.conversation_history = history
                thread.current_turn += 1

                self.db.commit()

                return {
                    "should_reply": False,
                    "reply_content": None,
                    "status": "session_ended",
                    "thread_status": "completed",
                    "goal_achieved": True
                }

            # Ensure we have latest thread state from DB before processing
            # This prevents history overwrites when messages arrive rapidly
            self.db.expire(thread)
            self.db.refresh(thread)

            # Add user message to history
            history = thread.conversation_history or []
            if message_id:
                existing_ids = {msg.get("message_id") for msg in history if msg.get("message_id")}
                if message_id in existing_ids:
                    self.logger.info(f"Thread {thread.id}: Duplicate message_id {message_id} - skipping")
                    return {
                        "should_reply": False,
                        "reply_content": None,
                        "status": "duplicate_message",
                        "thread_status": thread.status
                    }
            history.append({
                "role": "user",
                "content": message_content,
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "message_id": message_id
            })
            thread.conversation_history = history
            thread.current_turn += 1
            thread.last_activity_at = datetime.utcnow()
            self.db.commit()

            # Check turn limit
            if thread.current_turn >= thread.max_turns:
                thread.status = 'completed'
                thread.completed_at = datetime.utcnow()
                thread.goal_summary = f"Max turns ({thread.max_turns}) reached"
                self.db.commit()

                self.logger.info(f"Thread {thread.id} reached max turns, marking as completed")

                return {
                    "should_reply": False,
                    "reply_content": None,
                    "status": "max_turns_reached",
                    "thread_status": "completed"
                }

            context_data = thread.context_data or {}
            reset_attempts = context_data.get("session_reset_attempts", 0)
            if thread.current_turn <= 2 and reset_attempts < 2 and should_attempt_session_reset(message_content):
                reset_message = reset_message_for_attempt(reset_attempts)
                context_data["session_reset_attempts"] = reset_attempts + 1
                thread.context_data = context_data
                self.logger.info(
                    f"Thread {thread.id}: Mid-session detected, sending reset '{reset_message}'"
                )
                history.append({
                    "role": "agent",
                    "content": reset_message,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                thread.conversation_history = history
                thread.last_activity_at = datetime.utcnow()
                self.db.commit()

                return {
                    "should_reply": True,
                    "reply_content": reset_message,
                    "status": "session_reset",
                    "thread_status": thread.status,
                    "current_turn": thread.current_turn,
                    "goal_achieved": thread.goal_achieved
                }

            menu_signature = get_menu_signature(message_content)
            context_data = thread.context_data or {}
            last_menu_signature = context_data.get("last_menu_signature")
            last_menu_selection = context_data.get("last_menu_selection")
            last_selection = None
            if menu_signature and menu_signature == last_menu_signature:
                last_selection = last_menu_selection

            interactive_selection = choose_interactive_option(
                message_content=message_content,
                objective=thread.objective or "",
                last_selection=last_selection
            )
            if interactive_selection:
                self.logger.info(
                    f"Thread {thread.id}: Interactive menu detected, selecting '{interactive_selection}'"
                )
                if menu_signature:
                    context_data["last_menu_signature"] = menu_signature
                    context_data["last_menu_selection"] = interactive_selection
                    thread.context_data = context_data
                history.append({
                    "role": "agent",
                    "content": interactive_selection,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                thread.conversation_history = history
                thread.last_activity_at = datetime.utcnow()
                self.db.commit()

                return {
                    "should_reply": True,
                    "reply_content": interactive_selection,
                    "status": "interactive_selection",
                    "thread_status": thread.status,
                    "current_turn": thread.current_turn,
                    "goal_achieved": thread.goal_achieved
                }

            if should_acknowledge_status(message_content):
                acknowledgment = "Perfeito, obrigado!"
                self.logger.info(
                    f"Thread {thread.id}: Status update detected, sending acknowledgment"
                )
                history.append({
                    "role": "agent",
                    "content": acknowledgment,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                thread.conversation_history = history
                thread.last_activity_at = datetime.utcnow()
                self.db.commit()

                return {
                    "should_reply": True,
                    "reply_content": acknowledgment,
                    "status": "status_acknowledgment",
                    "thread_status": thread.status,
                    "current_turn": thread.current_turn,
                    "goal_achieved": thread.goal_achieved
                }

            # Get agent for this conversation
            agent = self.db.query(Agent).filter(Agent.id == thread.agent_id).first()
            if not agent:
                self.logger.error(f"Agent {thread.agent_id} not found for thread {thread.id}")
                return {
                    "should_reply": False,
                    "reply_content": None,
                    "status": "error",
                    "error": "Agent not found"
                }

            # Get agent config and create service
            agent_config = self._agent_to_config(agent)

            # Inject conversation objective into system prompt
            # This ensures the agent stays focused on the conversation goal
            # FIX 3: Enhanced identity enforcement to prevent contamination
            # FIX 2: Explicit anti-echo instructions
            # PHASE C: Generic mid-conversation detection and adaptation
            if thread.objective:
                # Generic mid-conversation indicators (works for any external bot)
                # These patterns indicate the external bot expects continuation, not a new conversation
                MID_CONVERSATION_INDICATORS = [
                    r"há mais algo",
                    r"anything else",
                    r"posso ajudar com mais",
                    r"can I help with anything else",
                    r"deseja (consultar|verificar) outr",
                    r"would you like to",
                    r"voltando ao menu",
                    r"returning to menu",
                    r"mais alguma (coisa|dúvida|pergunta)",
                    r"any other (question|request)",
                    r"alguma outra coisa",
                    r"need anything else",
                ]

                mid_conversation_detected = False
                if len(history) >= 1:
                    # Check first message from external bot for mid-conversation indicators
                    first_msg = history[0].get("content", "").lower() if history else ""
                    for indicator in MID_CONVERSATION_INDICATORS:
                        if re.search(indicator, first_msg, re.IGNORECASE):
                            mid_conversation_detected = True
                            self.logger.info(f"Thread {thread.id}: Mid-conversation detected via indicator: {indicator}")
                            break

                mid_conversation_instruction = ""
                if mid_conversation_detected:
                    mid_conversation_instruction = """
⚠️ MID-CONVERSATION DETECTED:
The external bot has an active session from a previous interaction.
First, reset to main menu by responding "menu" or "Menu" or "0".
Then proceed with the normal objective flow.
"""

                objective_instruction = f"""
---
CRITICAL IDENTITY RULES:
- You are an AI assistant acting ON BEHALF OF a user/customer
- You are CONTACTING another service's bot to get information
- You are NOT a customer service representative
- You are NOT "@movl" or any bot identifier
- NEVER prefix your messages with identifiers like "@movl:", "@bot:", or similar
- NEVER act as customer service - you ARE the customer
- NEVER offer menus, star ratings, or customer service options to the external bot
- NEVER ask "how can I help you?" or similar customer service phrases
- Your ONLY job is to navigate the external bot's menus to achieve the objective below

RESPONSE DISCIPLINE (applies to ALL external bot conversations):
- When the external bot provides information you requested, respond with a BRIEF acknowledgment
- Examples of good acknowledgments: "Perfeito, obrigado!", "Got it, thanks!", "Ok", "Entendido"
- NEVER echo, summarize, narrate, or restate the information the bot just gave you
- Your job is to RECEIVE and RECORD information, not to narrate it back
- The information will be captured in the conversation history automatically
- If the bot provides tracking status, delivery date, etc. - just acknowledge with "Obrigado!" or similar

INTERACTIVE SELECTION (applies to ALL external bot menus/lists):
- When presented with a numbered menu (e.g., "Press 1 for X, Press 2 for Y"), respond ONLY with the number
- When presented with a selection list with text options, respond with the EXACT text of your choice
- When the bot sends JSON with "type":"list" or "type":"buttons", extract option titles from "rows" or "buttons" and reply ONLY with the chosen title
- If your target option is not in the list, select the "Other" / "Outro" / "None of the above" option
- NEVER explain your selection - just send the option (number or text)
- NEVER include reasoning, tool_code, or commentary when selecting

SERVICE EVALUATION (applies to ALL external bot conversations):
- If asked to rate the service, choose the most positive text option (e.g., "Excelente", "Ótimo", "Muito bom")
- Avoid star symbols or numeric star ratings unless the menu forces numbers

{mid_conversation_instruction}

CONVERSATION OBJECTIVE: {thread.objective}

You MUST stay focused on this objective throughout the conversation.
Respond concisely and directly to the external bot's questions.
When asked for information (tracking code, CPF, etc.), provide ONLY that information.

Current turn: {thread.current_turn} of {thread.max_turns}
---
"""
                agent_config["system_prompt"] = objective_instruction + agent_config["system_prompt"]

            # Inject persona if specified in thread
            if thread.persona_id:
                from models import Persona
                persona = self.db.query(Persona).filter(Persona.id == thread.persona_id).first()
                if persona:
                    persona_text = self._build_persona_context(persona)
                    if "{{PERSONA}}" in agent_config["system_prompt"]:
                        agent_config["system_prompt"] = agent_config["system_prompt"].replace("{{PERSONA}}", persona_text)
                    else:
                        agent_config["system_prompt"] = f"{agent_config['system_prompt']}\n\n{persona_text}"

            # Create agent service
            # Phase 9.3: Pass tenant_id and persona_id for custom tool discovery
            thread_tenant_id = self._get_agent_tenant_id(thread.agent_id)
            thread_persona_id = thread.persona_id or self._get_agent_persona_id(thread.agent_id)

            temp_agent_service = AgentService(
                agent_config,
                contact_service=self.contact_service,
                db=self.db,
                agent_id=thread.agent_id,
                token_tracker=self.token_tracker,
                tenant_id=thread_tenant_id,
                persona_id=thread_persona_id
            )

            # Process message through agent
            # Build conversation context for the AI
            conversation_context = "Previous conversation:\n"
            for msg in history[:-1]:  # All except the current message (last 10)
                role = "Agent" if msg["role"] == "agent" else "User"
                conversation_context += f"{role}: {msg['content']}\n"

            # Format message with conversation history
            formatted_message = f"{conversation_context}\nUser: {message_content}"

            result = await temp_agent_service.process_message(
                sender,
                formatted_message,
                original_query=message_content
            )

            ai_reply = result.get("answer", "")

            if ai_reply:
                # Centralized contamination detection - MUST HAPPEN BEFORE SENDING
                from .contamination_detector import get_contamination_detector

                self.logger.info(f"Thread {thread.id}: Checking AI response for contamination: '{ai_reply[:80]}...'")

                # Use centralized ContaminationDetector for consistent pattern matching
                detector = get_contamination_detector(db_session=self.db, agent_id=thread.agent_id)
                contamination_found = detector.check(ai_reply)

                if contamination_found:
                    self.logger.error(
                        f"Thread {thread.id}: CONTAMINATION DETECTED! Pattern '{contamination_found}' found in response! "
                        f"Response: '{ai_reply[:300]}...'"
                    )

                    # Force-stop the conversation immediately
                    thread.status = 'completed'
                    thread.completed_at = datetime.utcnow()
                    thread.goal_achieved = False
                    thread.goal_summary = f"CONTAMINATION DETECTED: {contamination_found}"
                    self.db.commit()

                    return {
                        "should_reply": False,
                        "reply_content": None,
                        "status": "contamination_detected",
                        "thread_status": "completed",
                        "goal_achieved": False,
                        "error": f"Contamination pattern '{contamination_found}' detected - conversation terminated"
                    }

                # Clean response using centralized cleaner (strips @AgentName: prefixes)
                ai_reply = detector.clean_response(ai_reply)

                self.logger.info(f"Thread {thread.id}: Response clean, using: '{ai_reply[:80]}...')")

                # Add AI response to history
                history.append({
                    "role": "agent",
                    "content": ai_reply,
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                })
                thread.conversation_history = history

                # Check for goal completion in both user message and agent response
                # Bug Fix 2026-01-07: Use word boundaries to avoid false positives (e.g. "feito" in "Perfeito")
                # FIX 4: Enhanced goal detection for data retrieval patterns
                user_completion_keywords = [
                    # English
                    r"\bthank you\b", r"\bthanks\b", r"\bbye\b", r"\bgoodbye\b", r"\bok done\b",
                    r"\bthat's all\b", r"\bnothing else\b",
                    # Portuguese
                    r"\bobrigado\b", r"\bobrigada\b", r"\bvaleu\b", r"\btchau\b", r"\baté mais\b",
                    r"\bera só isso\b", r"\bsó isso\b", r"\bpronto\b", r"\bfeito\b"
                    # Removed: "certo, segue", "aqui está", "segue aí", "tá aqui" - too generic
                ]
                agent_completion_keywords = [
                    # English
                    r"\bcompleted\b", r"\bfinished\b", r"\ball done\b", r"\bthat's everything\b",
                    r"\bthank you for\b", r"\bthanks for participating\b", r"\bwas great talking\b",
                    r"\bhave a great day\b", r"\btake care\b",
                    # Portuguese
                    r"\bcompletou\b", r"\bconcluído\b", r"\bconcluida\b", r"\bfinalizado\b", r"\bfinalizada\b",
                    r"\bpesquisa completa\b", r"\btodas as perguntas\b", r"\btudo certo\b",
                    r"\bobrigado por\b", r"\bfoi ótimo conversar\b", r"\btenha um ótimo dia\b",
                    r"\brecebi\b", r"\banotado\b", r"\bregistrado\b", r"\brecebido\b"
                ]

                # FIX 4: Data retrieval success patterns (for tracking, shipment, status queries)
                # FIX 2026-01-17 PHASE B: Require COMPLETE information, not just acknowledgment
                data_retrieval_patterns = [
                    # Shipment/delivery tracking - require status AND date
                    r"(em trânsito|in transit).*prevista? (para|until).*202\d",
                    r"prevista? (para|until).*202\d.*(em trânsito|in transit)",
                    r"status.*delivered.*\d{4}-\d{2}-\d{2}",
                    r"entregue.*em.*\d{2}/\d{2}/202\d",
                    # Flight status with complete info
                    r"(flight|voo).*\b(on time|no horário).*gate\s*\d+",
                    r"departure.*\d{1,2}:\d{2}.*gate",
                    # REMOVED: Premature triggers that fire before actual data
                    # r"de acordo com as informações",  # Too early - just acknowledges request
                    # r"encontrei (seu|o|a)",  # Too early - just found record
                    # r"código de rastreio.*\d{10,}",  # Too early - just echoing number back
                ]

                ai_reply_lower = ai_reply.lower()
                message_lower = message_content.lower()

                # Check if user indicates they're done or providing requested info
                import re
                user_done = any(re.search(pattern, message_lower) for pattern in user_completion_keywords)

                # Also check if user is providing a code/number after "segue" or similar
                user_providing_info = bool(re.search(r'(segue|aqui|pronto|certo)[^\d]*\d{6,}', message_lower))

                # Check if agent indicates conversation objective is complete
                agent_done = any(re.search(pattern, ai_reply_lower) for pattern in agent_completion_keywords)

                # FIX 4: Check if external bot provided the requested data (tracking info, status, etc.)
                data_received = any(re.search(pattern, message_lower, re.IGNORECASE) for pattern in data_retrieval_patterns)

                if ((user_done or user_providing_info or agent_done or data_received) and thread.current_turn >= 2):
                    thread.status = 'completed'
                    thread.goal_achieved = True
                    thread.completed_at = datetime.utcnow()
                    if data_received:
                        thread.goal_summary = "Data successfully retrieved from external bot"
                    elif agent_done:
                        thread.goal_summary = "Conversation objective achieved"
                    elif user_providing_info:
                        thread.goal_summary = "User provided requested information"
                    else:
                        thread.goal_summary = "User indicated completion"
                    self.logger.info(f"Thread {thread.id} completed: {'data received' if data_received else 'agent signaled' if agent_done else 'user signaled' if user_done else 'user provided info'}")

                self.db.commit()

                return {
                    "should_reply": True,
                    "reply_content": ai_reply,
                    "status": "success",
                    "thread_status": thread.status,
                    "current_turn": thread.current_turn,
                    "goal_achieved": thread.goal_achieved
                }
            else:
                self.logger.warning(f"No AI response generated for thread {thread.id}")
                self.db.commit()
                return {
                    "should_reply": False,
                    "reply_content": None,
                    "status": "no_response"
                }

        except Exception as e:
            self.logger.error(f"Error processing thread reply: {e}", exc_info=True)
            return {
                "should_reply": False,
                "reply_content": None,
                "status": "error",
                "error": str(e)
            }

    async def _invoke_post_response_hooks(
        self,
        agent_id: int,
        user_message: str,
        agent_response: str,
        context: Dict,
        ai_client
    ):
        """
        Task 3: Invoke post_response_hook for skills that support it.

        Post-response hooks run AFTER the agent generates a response.
        Example: KnowledgeSharingSkill extracts facts and shares to Layer 4.

        Args:
            agent_id: Agent ID
            user_message: User's message text
            agent_response: Agent's response text
            context: Conversation context (sender, chat_id, etc.)
            ai_client: AI client for fact extraction
        """
        try:
            # Get enabled skills for this agent
            agent_skills = await self.skill_manager.get_agent_skills(self.db, agent_id)

            for skill_record in agent_skills:
                skill_type = skill_record.skill_type

                # Check if skill has post_response_hook
                if skill_type not in self.skill_manager.registry:
                    continue

                skill_class = self.skill_manager.registry[skill_type]

                # Instantiate skill (with parameters if needed)
                if skill_type == "knowledge_sharing":
                    skill_instance = skill_class(self.db, agent_id)
                else:
                    skill_instance = skill_class()

                # Check if skill has post_response_hook method
                if hasattr(skill_instance, 'post_response_hook'):
                    self.logger.info(f"Calling post_response_hook for skill '{skill_type}'")

                    config = skill_record.config or {}

                    try:
                        hook_result = await skill_instance.post_response_hook(
                            user_message=user_message,
                            agent_response=agent_response,
                            context=context,
                            config=config,
                            ai_client=ai_client
                        )

                        self.logger.info(f"Post-response hook completed for '{skill_type}': {hook_result}")

                    except Exception as e:
                        self.logger.error(f"Error in post_response_hook for '{skill_type}': {e}", exc_info=True)

        except Exception as e:
            self.logger.error(f"Error invoking post_response_hooks: {e}", exc_info=True)

    async def _handle_project_commands(
        self,
        agent_id: int,
        sender_key: str,
        message_text: str,
        message: Dict,
        trigger_type: str
    ) -> Optional[Dict]:
        """
        Phase 15: Skill Projects - Handle project commands and sessions.

        This method checks for project commands and handles them appropriately.
        If the user is in a project session, it processes the message with
        project-scoped memory and knowledge base.

        Command flow:
        1. Check for project commands (enter, exit, list, help)
        2. If command found, execute and return result
        3. Check if user is in project session
        4. If in project, process with project context
        5. Return None to continue normal processing

        Args:
            agent_id: Selected agent ID
            sender_key: Normalized sender key
            message_text: Message text
            message: Full message dict
            trigger_type: Trigger type (dm, group, etc.)

        Returns:
            Dict with handling status, or None to continue normal flow
        """
        from services.project_command_service import ProjectCommandService
        from models import Project, UserProjectSession, ProjectConversation, AgentProjectAccess

        try:
            # Get tenant_id for this agent
            tenant_id = self._get_agent_tenant_id(agent_id)
            if not tenant_id:
                self.logger.debug("No tenant_id for agent, skipping project commands")
                return None

            # Determine channel from message
            # CRITICAL: Respect original channel (telegram, whatsapp) to prevent cross-channel contamination
            channel = message.get("channel", "whatsapp")
            is_group = message.get("is_group", False)

            # Override channel display for specific contexts (but preserve underlying channel)
            if is_group and channel == "whatsapp":
                channel = "whatsapp_group"
            elif trigger_type == "playground":
                channel = "playground"

            # Initialize project command service
            project_command_service = ProjectCommandService(self.db)

            # Step 1: Check for project commands
            command_result = await project_command_service.detect_command(tenant_id, message_text)

            if command_result:
                command_type, command_data = command_result
                self.logger.info(f"[PROJECT] Detected command: {command_type}")

                # Handle command based on type
                if command_type == "enter":
                    project_name = command_data.get("project_name", "")
                    result = await project_command_service.execute_enter(
                        tenant_id=tenant_id,
                        sender_key=sender_key,
                        agent_id=agent_id,
                        channel=channel,
                        project_identifier=project_name,
                        response_template=command_data.get("response_template")
                    )

                    # Send response
                    await self._send_project_response(message, agent_id, result.get("message", ""))
                    return {"handled": True, "result": result}

                elif command_type == "exit":
                    result = await project_command_service.execute_exit(
                        tenant_id=tenant_id,
                        sender_key=sender_key,
                        agent_id=agent_id,
                        channel=channel,
                        response_template=command_data.get("response_template")
                    )

                    await self._send_project_response(message, agent_id, result.get("message", ""))
                    return {"handled": True, "result": result}

                elif command_type == "list":
                    result = await project_command_service.execute_list(
                        tenant_id=tenant_id,
                        sender_key=sender_key,
                        agent_id=agent_id,
                        response_template=command_data.get("response_template")
                    )

                    await self._send_project_response(message, agent_id, result.get("message", ""))
                    return {"handled": True, "result": result}

                elif command_type == "help":
                    result = await project_command_service.execute_help(
                        response_template=command_data.get("response_template")
                    )

                    await self._send_project_response(message, agent_id, result.get("message", ""))
                    return {"handled": True, "result": result}

                elif command_type == "upload":
                    # Handle upload command - need media attachment
                    media_type = message.get("media_type")
                    if media_type:
                        # Download and process the file
                        # This will be handled by the normal flow with project context
                        self.logger.info("[PROJECT] Upload command with media - will be processed with project context")
                    else:
                        # No media attached
                        await self._send_project_response(
                            message, agent_id,
                            "📎 Please send a file with your message to add it to the project."
                        )
                        return {"handled": True}

            # Step 2: Check if user is in a project session
            session = await project_command_service.get_session(
                tenant_id=tenant_id,
                sender_key=sender_key,
                agent_id=agent_id,
                channel=channel
            )

            if session and session.project_id:
                self.logger.info(f"[PROJECT] User {sender_key} is in project {session.project_id}")

                # Handle media uploads in project context
                media_type = message.get("media_type")
                if media_type and media_type.startswith("document"):
                    # Document upload in project mode
                    self.logger.info(f"[PROJECT] Document upload detected in project {session.project_id}")
                    # This would need media download logic similar to audio
                    # For now, return handled and let user know
                    await self._send_project_response(
                        message, agent_id,
                        "📎 Document received. Processing and adding to project..."
                    )
                    # TODO: Implement actual document processing
                    return {"handled": True}

                # Get project info
                project = self.db.query(Project).filter(Project.id == session.project_id).first()
                if project:
                    # Get project context from knowledge base
                    project_context = await project_command_service.get_project_context(
                        project_id=session.project_id,
                        query=message_text,
                        max_results=5
                    )

                    # Add project context to message
                    if project_context:
                        modified_message = f"{project_context}\n\n[User message in project '{project.name}']: {message_text}"
                    else:
                        modified_message = f"[User message in project '{project.name}']: {message_text}"

                    # Save message to project conversation
                    if session.conversation_id:
                        conversation = self.db.query(ProjectConversation).filter(
                            ProjectConversation.id == session.conversation_id
                        ).first()
                        if conversation:
                            messages = conversation.messages_json or []
                            messages.append({
                                "role": "user",
                                "content": message_text,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            })
                            conversation.messages_json = messages
                            self.db.commit()

                    # Return with modified message and project_id for memory scoping
                    return {
                        "handled": False,
                        "modified_message": modified_message,
                        "project_id": session.project_id,
                        "project_name": project.name,
                        "conversation_id": session.conversation_id
                    }

            # No command or session - continue normal flow
            return None

        except Exception as e:
            self.logger.error(f"Error handling project commands: {e}", exc_info=True)
            return None

    async def _send_project_response(self, message: Dict, agent_id: int, response_text: str):
        """
        Phase 15: Send a project command response via appropriate channel.

        Args:
            message: Original message dict
            agent_id: Agent ID
            response_text: Response text to send
        """
        try:
            recipient = message.get("chat_id") or message.get("sender")
            channel = message.get("channel", "whatsapp")

            # Send response
            success = await self._send_message(
                recipient=recipient,
                message_text=response_text,
                channel=channel,
                agent_id=agent_id
            )
            if success:
                self.logger.info(f"[PROJECT] Response sent to {recipient} via {channel}")
            else:
                self.logger.error(f"[PROJECT] Failed to send response to {recipient} via {channel}")

        except Exception as e:
            self.logger.error(f"Error sending project response: {e}", exc_info=True)

    async def _handle_slash_command(
        self,
        sender_key: str,
        message_text: str,
        message: Dict,
        trigger_type: str
    ) -> Optional[Dict]:
        """
        Phase 16: Handle slash commands across all channels (WhatsApp, Playground, etc).

        Slash commands provide quick access to common actions:
        - /invoke <agent> - Switch to different agent
        - /project enter <name> - Enter project context
        - /project exit - Exit project
        - /memory clear - Clear conversation memory
        - /commands - List available commands
        - /help [command] - Get help

        Args:
            sender_key: Normalized sender key
            message_text: Full message text starting with /
            message: Original message dict
            trigger_type: Channel type (dm, group, etc.)

        Returns:
            Dict with handled=True if command was executed, None otherwise
        """
        try:
            # Determine channel
            # CRITICAL: Respect original channel (telegram, whatsapp) to prevent cross-channel contamination
            channel = message.get("channel", "whatsapp")
            is_group = message.get("is_group", False)

            # Override channel display for specific contexts (but preserve underlying channel)
            if is_group and channel == "whatsapp":
                channel = "whatsapp_group"
            elif trigger_type == "playground":
                channel = "playground"

            # Get agent for this user (for agent-specific commands)
            # First, try to get from saved session
            from models import UserAgentSession
            sender = message.get("sender", "")

            agent_id = None
            try:
                saved_session = self.db.query(UserAgentSession).filter(
                    UserAgentSession.user_identifier == sender_key
                ).first()
                if saved_session:
                    agent_id = saved_session.agent_id
            except Exception:
                pass

            # If no saved session, try to get default agent
            if not agent_id:
                default_agent = self.db.query(Agent).filter(Agent.is_default == True).first()
                if default_agent:
                    agent_id = default_agent.id

            # Get tenant_id from agent
            tenant_id = "_system"  # Default to system commands
            if agent_id:
                agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                if agent and agent.tenant_id:
                    tenant_id = agent.tenant_id

            # Initialize slash command service
            slash_service = SlashCommandService(self.db)

            # Detect command
            command_info = slash_service.detect_command(message_text, tenant_id)

            if not command_info:
                # Not a recognized command
                return None

            self.logger.info(f"[SLASH] Detected command: {command_info.get('command_name')}")

            # Execute the command
            result = await slash_service.execute_command(
                message=message_text,
                tenant_id=tenant_id,
                agent_id=agent_id or 0,
                sender_key=sender_key,
                channel=channel,
                user_id=None  # Could be resolved from contact mapping if needed
            )

            # Layer 5: Store tool output in ephemeral buffer for follow-up interactions
            # This enables agentic analysis of tool results via WhatsApp
            if result.get("action") in ("tool_executed", "tool_running") and result.get("message"):
                tool_buffer = get_tool_output_buffer()
                tool_name = result.get("tool_name", "unknown")
                command_name = result.get("command_name", "execute")
                execution_id = tool_buffer.add_tool_output(
                    agent_id=agent_id or 0,
                    sender_key=sender_key,
                    tool_name=tool_name,
                    command_name=command_name,
                    output=result["message"]
                )
                self.logger.info(f"[SLASH] Stored tool output in Layer 5 buffer: #{execution_id} {tool_name}.{command_name} for {sender_key}")

            # Send response if there's a message
            if result.get("message"):
                recipient = message.get("chat_id") or message.get("sender")
                channel = message.get("channel", "whatsapp")

                success = await self._send_message(
                    recipient=recipient,
                    message_text=result["message"],
                    channel=channel,
                    agent_id=agent_id
                )
                if success:
                    self.logger.info(f"[SLASH] Response sent to {recipient} via {channel}")
                else:
                    self.logger.error(f"[SLASH] Failed to send response to {recipient} via {channel}")

            # Handle special actions from command execution
            if result.get("action") == "switch_agent" and result.get("data", {}).get("agent_id"):
                # Save agent preference
                new_agent_id = result["data"]["agent_id"]
                try:
                    existing = self.db.query(UserAgentSession).filter(
                        UserAgentSession.user_identifier == sender_key
                    ).first()
                    if existing:
                        existing.agent_id = new_agent_id
                    else:
                        from models import UserAgentSession
                        session = UserAgentSession(
                            user_identifier=sender_key,
                            agent_id=new_agent_id
                        )
                        self.db.add(session)
                    self.db.commit()
                    self.logger.info(f"[SLASH] Agent preference saved: {new_agent_id} for {sender_key}")
                except Exception as e:
                    self.logger.error(f"[SLASH] Error saving agent preference: {e}")

            return {"handled": True, "result": result}

        except Exception as e:
            self.logger.error(f"Error handling slash command: {e}", exc_info=True)
            return None

    async def _process_with_skills(self, agent_id: int, message: Dict) -> str:
        """
        Phase 5.0: Process message with enabled skills before AI processing.

        Skills are checked for ALL messages (text and media).
        Each skill has its own can_handle() logic to decide if it should process.

        Examples:
        - AudioTranscriptSkill: Only handles media_type="audio"
        - SchedulerSkill: Handles any text with scheduling keywords (works on transcribed audio too)
        - SchedulerQuerySkill: Handles any text with query keywords

        Args:
            agent_id: Agent ID to check for enabled skills
            message: Message dict from MCP database

        Returns:
            Tuple of (processed_message_text, skip_ai_flag, skill_output, skill_type, media_paths)
        """
        try:
            message_body = message.get("body", "")
            media_type = message.get("media_type")

            # Download media file if needed (for audio transcription)
            media_path = message.get("media_path")
            if media_type:
                self.logger.info(f"Processing message with media type: {media_type}")

            if media_type and self.media_downloader.is_audio_message(media_type) and not media_path:
                # Download audio file from WhatsApp MCP
                message_id = message.get("id")
                chat_jid = message.get("chat_jid")

                if message_id and chat_jid:
                    # Resolve the correct MCP URL and secret for this agent (multi-tenant support)
                    mcp_url, api_secret = self._resolve_mcp_instance(agent_id)
                    self.logger.info(f"Downloading audio file for message {message_id} via {mcp_url}")
                    media_path = await self.media_downloader.download_media(message_id, chat_jid, mcp_url, api_secret)

                    if not media_path:
                        self.logger.warning("Failed to download audio file, continuing without transcription")
                        # Continue without transcription - message_body will be empty for audio
                else:
                    self.logger.warning("Missing message_id or chat_jid for media download, continuing without transcription")

            # Download image media if needed (for image editing skill)
            if media_type and self.media_downloader.is_image_message(media_type) and not media_path:
                message_id = message.get("id")
                chat_jid = message.get("chat_jid")

                if message_id and chat_jid:
                    # Resolve MCP URL and secret for authenticated download
                    mcp_url, api_secret = self._resolve_mcp_instance(agent_id)
                    self.logger.info(f"Downloading image file for message {message_id} via {mcp_url}")
                    media_path = await self.media_downloader.download_media(message_id, chat_jid, mcp_url, api_secret)

                    if not media_path:
                        self.logger.warning("Failed to download image file")
                else:
                    self.logger.warning("Missing message_id or chat_jid for image download")

            # Create InboundMessage for skill processing
            inbound_message = InboundMessage(
                id=message.get("id", "unknown"),
                sender=message.get("sender", ""),
                sender_key=self._get_sender_key(message),
                body=message_body,
                chat_id=message.get("chat_id", ""),
                chat_name=message.get("chat_name"),
                is_group=message.get("is_group", False),
                timestamp=datetime.utcnow(),
                media_type=media_type,
                media_url=message.get("media_url"),
                media_path=media_path,  # Use downloaded path
                channel=message.get("channel", "whatsapp")  # Skills-as-Tools: channel info
            )

            # Try to process with skills
            skill_result = await self.skill_manager.process_message_with_skills(
                db=self.db,
                agent_id=agent_id,
                message=inbound_message
            )

            if skill_result and skill_result.success:
                self.logger.info(f"Skill processed message successfully: {skill_result.output[:100]}")

                # Extract skill_type from metadata
                skill_type = skill_result.metadata.get("skill_type") if skill_result.metadata else None

                # Check if skill requested to skip AI processing
                skip_ai = skill_result.metadata.get("skip_ai", False) if skill_result.metadata else False

                # Extract media_paths for image delivery (e.g., screenshots)
                media_paths = skill_result.media_paths

                if skip_ai:
                    # Return: (message_text, skip_ai_flag, skill_output, skill_type, media_paths)
                    return (message_body, True, skill_result.output, skill_type, media_paths)
                elif skill_result.processed_content:
                    # Return: (transcribed_text, no_skip, None, skill_type, media_paths)
                    return (skill_result.processed_content, False, None, skill_type, media_paths)
                else:
                    # Skill succeeded but wants AI to format the response
                    # Return skill output so it can be included in AI context
                    return (message_body, False, skill_result.output, skill_type, media_paths)

            elif skill_result and not skill_result.success:
                self.logger.warning(f"[ERROR] Skill processing failed: {skill_result.output}")

            # No skill handled it or processing failed, return original
            return (message_body, False, None, None, None)

        except Exception as e:
            self.logger.error(f"Error processing message with skills: {e}", exc_info=True)
            # On error, return original message text
            return (message.get("body", ""), False, None, None, None)
