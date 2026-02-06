"""
Multi-Agent Memory Manager - Phase 4.8
Phase 15: Added project-scoped memory support for Skill Projects

Manages separate memory namespaces for multiple agents.
Each agent gets their own isolated memory instance with agent-scoped keys.

Key features:
- Agent-specific memory isolation (no cross-contamination)
- Lazy loading of memory instances (only create when needed)
- Agent-scoped sender keys: "agent_id:sender_key"
- Separate ChromaDB collections per agent
- Phase 15: Project-scoped memory keys for isolated project conversations
"""

import logging
from typing import Dict, Optional
from sqlalchemy.orm import Session

from .semantic_memory import SemanticMemoryService
from .agent_memory_system import AgentMemorySystem
from ..contact_resolver import ContactResolver


class MultiAgentMemoryManager:
    """
    Manages memory namespaces for multiple agents.

    Each agent maintains separate:
    - Ring buffer (recent messages)
    - Vector store collection (semantic search)
    - Memory persistence (agent-scoped keys)
    """

    def __init__(
        self,
        db_session: Session,
        config: Dict,
        base_chroma_dir: str = "./data/chroma"
    ):
        """
        Initialize multi-agent memory manager.

        Args:
            db_session: Database session for persistence
            config: Configuration dictionary with memory settings
            base_chroma_dir: Base directory for ChromaDB collections
        """
        self.logger = logging.getLogger(__name__)
        self.db = db_session
        self.config = config
        self.base_chroma_dir = base_chroma_dir

        # Agent memory instances (lazy loaded)
        # Phase 4.8 Week 3: Using AgentMemorySystem for full 4-layer memory
        self.agent_memories: Dict[int, AgentMemorySystem] = {}

        # Item 10: Contact resolver for contact-based memory
        self.contact_resolver = ContactResolver(db_session)

        self.logger.info("MultiAgentMemoryManager initialized with contact-based memory support")

    def _fetch_agent_config(self, agent_id: int) -> dict:
        """
        Fetch agent's LLM configuration from database.

        Args:
            agent_id: Agent ID

        Returns:
            Dictionary with agent's model_provider, model_name, and other config
        """
        try:
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                # Return agent's LLM config merged with system config
                agent_config = dict(self.config)  # Start with system config
                agent_config.update({
                    'agent_id': agent.id,
                    'tenant_id': agent.tenant_id,
                    'model_provider': agent.model_provider,
                    'model_name': agent.model_name,
                    'temperature': getattr(agent, 'temperature', None),
                    'max_tokens': getattr(agent, 'max_tokens', None),
                })
                self.logger.info(f"Fetched agent {agent_id} LLM config: provider={agent.model_provider}, model={agent.model_name}")
                return agent_config
        except Exception as e:
            self.logger.error(f"Error fetching agent {agent_id} config: {e}", exc_info=True)

        # Fallback to system config
        self.logger.warning(f"Could not fetch agent {agent_id} config, using system config")
        return self.config

    def get_agent_memory(self, agent_id: int, agent_config: dict = None) -> AgentMemorySystem:
        """
        Get or create memory system for a specific agent.

        Args:
            agent_id: Agent ID
            agent_config: Optional agent-specific configuration (overrides system config)

        Returns:
            AgentMemorySystem instance for this agent (with 4-layer architecture)
        """
        if agent_id not in self.agent_memories:
            # Create agent-specific memory instance
            persist_dir = f"{self.base_chroma_dir}/agent_{agent_id}"

            # If agent_config not provided, fetch from database
            if agent_config is None:
                config_to_use = self._fetch_agent_config(agent_id)
            else:
                config_to_use = agent_config

            memory = AgentMemorySystem(
                agent_id=agent_id,
                db_session=self.db,
                config=config_to_use,
                persist_directory=persist_dir
            )

            self.agent_memories[agent_id] = memory
            memory_size = config_to_use.get("memory_size", 10)
            self.logger.info(f"Created AgentMemorySystem for agent {agent_id} (memory_size={memory_size})")

        return self.agent_memories[agent_id]

    def _get_agent_isolation_mode(self, agent_id: int) -> str:
        """
        Get agent's memory isolation mode from database.

        Args:
            agent_id: Agent ID

        Returns:
            Isolation mode: "isolated" | "shared" | "channel_isolated"
        """
        try:
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if agent and hasattr(agent, 'memory_isolation_mode') and agent.memory_isolation_mode:
                return agent.memory_isolation_mode
        except Exception as e:
            self.logger.warning(f"Error fetching isolation mode for agent {agent_id}: {e}")

        # Default to isolated mode for maximum privacy
        return "isolated"

    def get_memory_key(
        self,
        agent_id: int,
        sender_key: str,
        isolation_mode: str = "isolated",
        chat_id: str = None,
        project_id: Optional[int] = None
    ) -> str:
        """
        Generate memory key based on agent's isolation mode.

        Isolation Modes:
        - isolated: Per-sender memory across all channels (strictest privacy)
          Format: "agent_{id}:sender_{key}"
          Example: "agent_1:sender_5500000000001"

        - shared: Global agent memory (everyone shares)
          Format: "agent_{id}:shared"
          Example: "agent_1:shared"

        - channel_isolated: Per-channel memory (groups separated)
          Format: "agent_{id}:channel_{chat_id}"
          Example: "agent_1:channel_5500000000002-1522245159@g.us"

        Phase 15 - Project Mode:
        - When project_id is provided, uses project-scoped memory
          Format: "project_{project_id}:sender_{key}"
          Example: "project_5:sender_5500000000001"
        - This ensures project conversations are isolated from main agent memory

        Args:
            agent_id: Agent ID
            sender_key: Original sender key (phone/chat_id)
            isolation_mode: "isolated" | "shared" | "channel_isolated"
            chat_id: Chat/group ID (required for channel_isolated mode)
            project_id: Optional project ID for project-scoped memory

        Returns:
            Memory key based on isolation mode or project context
        """
        # Phase 15: Project-scoped memory takes precedence
        if project_id:
            return f"project_{project_id}:sender_{sender_key}"

        if isolation_mode == "shared":
            return f"agent_{agent_id}:shared"
        elif isolation_mode == "channel_isolated":
            # Use chat_id if provided, otherwise fall back to sender_key
            channel_id = chat_id if chat_id else sender_key
            return f"agent_{agent_id}:channel_{channel_id}"
        else:  # isolated (default)
            return f"agent_{agent_id}:sender_{sender_key}"

    def parse_memory_key(self, memory_key: str) -> tuple[int, str]:
        """
        Parse agent-scoped memory key back into components.

        Args:
            memory_key: Agent-scoped key ("agent_id:sender_key")

        Returns:
            Tuple of (agent_id, sender_key)
        """
        parts = memory_key.split(":", 1)
        if len(parts) == 2:
            return int(parts[0]), parts[1]
        else:
            # Fallback for old-format keys (no agent_id)
            self.logger.warning(f"Memory key '{memory_key}' missing agent_id, assuming agent 1")
            return 1, memory_key

    async def add_message(
        self,
        agent_id: int,
        sender_key: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        chat_id: Optional[str] = None,
        whatsapp_id: Optional[str] = None,
        telegram_id: Optional[str] = None,
        telegram_username: Optional[str] = None,  # Phase 10.1.1: Username fallback
        use_contact_mapping: bool = True,
        project_id: Optional[int] = None
    ) -> None:
        """
        Add a message to agent-specific memory with isolation mode and contact mapping support.

        Item 10: Now supports contact-based memory keys for consistent cross-channel memory.
        Phase 15: Now supports project-scoped memory for isolated project conversations.

        Args:
            agent_id: Agent ID
            sender_key: Original sender key (phone/chat_id)
            role: Message role ('user' or 'assistant')
            content: Message content
            message_id: Optional unique message ID
            metadata: Optional additional metadata
            chat_id: Optional chat/group ID (for channel_isolated mode)
            whatsapp_id: Optional WhatsApp ID for contact resolution
            telegram_id: Optional Telegram ID for contact resolution (Phase 10.1.1)
            telegram_username: Optional Telegram username for contact resolution (Phase 10.1.1)
            use_contact_mapping: If True, use contact-based keys; if False, use sender-based keys
            project_id: Optional project ID for project-scoped memory (Phase 15)
        """
        # Add agent_id to metadata
        if metadata is None:
            metadata = {}
        metadata['agent_id'] = agent_id

        # Get agent memory
        memory = self.get_agent_memory(agent_id)

        # Phase 15: Project-scoped memory takes precedence
        if project_id:
            user_id = f"project_{project_id}:sender_{sender_key}"
            metadata['project_id'] = project_id
            self.logger.debug(f"Using project-scoped memory: project_id={project_id}")
        else:
            # Get isolation mode from database
            isolation_mode = self._get_agent_isolation_mode(agent_id)

            # Transform user_id based on isolation mode
            if isolation_mode == "shared":
                # All senders share same memory
                user_id = "shared"
            elif isolation_mode == "channel_isolated":
                # Memory separated by channel/group
                user_id = f"channel_{chat_id if chat_id else sender_key}"
            else:  # isolated (default)
                # Item 10: Contact-based memory (consistent across channels)
                if use_contact_mapping:
                    # Phase 10.2: Get tenant_id from agent for proper contact resolution
                    from models import Agent
                    agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                    tenant_id = agent.tenant_id if agent else "default"

                    self.logger.info(f"[CONTACT RESOLUTION] Attempting to resolve contact: sender={sender_key}, whatsapp={whatsapp_id}, telegram={telegram_id}, tenant={tenant_id}")

                    contact_id = self.contact_resolver.resolve_contact_id(
                        sender_key, whatsapp_id, telegram_id, telegram_username, tenant_id
                    )
                    if contact_id:
                        user_id = f"contact_{contact_id}"
                        metadata['contact_id'] = contact_id
                        self.logger.info(f"✅ Using contact-based memory: contact_id={contact_id} (tenant: {tenant_id})")
                    else:
                        # Fallback to sender-based key
                        user_id = f"sender_{sender_key}"
                        self.logger.warning(f"❌ Contact not found, using sender-based memory: {sender_key} (whatsapp={whatsapp_id}, telegram={telegram_id}, tenant={tenant_id})")
                else:
                    # Legacy sender-based memory
                    user_id = f"sender_{sender_key}"

        await memory.add_message(
            user_id=user_id,
            role=role,
            content=content,
            message_id=message_id,
            metadata=metadata
        )

        mode_desc = f"project {project_id}" if project_id else self._get_agent_isolation_mode(agent_id)
        self.logger.debug(f"Added message to agent {agent_id} memory: {user_id} (mode: {mode_desc})")

    async def get_context(
        self,
        agent_id: int,
        sender_key: str,
        current_message: str,
        max_semantic_results: int = 5,
        similarity_threshold: float = 0.3,
        include_knowledge: bool = True,
        include_shared: bool = True,
        chat_id: Optional[str] = None,
        whatsapp_id: Optional[str] = None,
        telegram_id: Optional[str] = None,  # Phase 10.1.1
        telegram_username: Optional[str] = None,  # Phase 10.1.1
        use_contact_mapping: bool = True,
        project_id: Optional[int] = None
    ) -> Dict:
        """
        Get comprehensive context for agent-specific conversation with isolation mode and contact mapping support.

        Item 10: Now supports contact-based memory retrieval for consistent cross-channel context.
        Phase 15: Now supports project-scoped memory retrieval for isolated project conversations.

        Includes all 4 layers:
        - Layer 1: Working memory (recent messages)
        - Layer 2: Episodic memory (semantic search)
        - Layer 3: Semantic knowledge (learned facts)
        - Layer 4: Shared memory (cross-agent knowledge)

        Args:
            agent_id: Agent ID
            sender_key: Original sender key (phone/chat_id)
            current_message: Current message to find context for
            max_semantic_results: Max semantic search results
            similarity_threshold: Minimum similarity score
            include_knowledge: Include learned facts about user
            include_shared: Include shared memory from other agents
            chat_id: Optional chat/group ID (for channel_isolated mode)
            whatsapp_id: Optional WhatsApp ID for contact resolution
            use_contact_mapping: If True, use contact-based keys; if False, use sender-based keys
            project_id: Optional project ID for project-scoped memory (Phase 15)

        Returns:
            Dictionary with all context layers
        """
        # Get agent memory
        memory = self.get_agent_memory(agent_id)

        # Phase 15: Project-scoped memory takes precedence
        if project_id:
            user_id = f"project_{project_id}:sender_{sender_key}"
            self.logger.debug(f"Retrieving project-scoped context: project_id={project_id}")
        else:
            # Get isolation mode from database
            isolation_mode = self._get_agent_isolation_mode(agent_id)

            # Transform user_id based on isolation mode (same logic as add_message)
            if isolation_mode == "shared":
                user_id = "shared"
            elif isolation_mode == "channel_isolated":
                user_id = f"channel_{chat_id if chat_id else sender_key}"
            else:  # isolated (default)
                # Item 10: Contact-based memory retrieval
                if use_contact_mapping:
                    # Phase 10.2: Get tenant_id from agent for proper contact resolution
                    from models import Agent
                    agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
                    tenant_id = agent.tenant_id if agent else "default"

                    self.logger.info(f"[CONTACT RESOLUTION GET_CONTEXT] sender={sender_key}, whatsapp={whatsapp_id}, telegram={telegram_id}, tenant={tenant_id}")

                    contact_id = self.contact_resolver.resolve_contact_id(
                        sender_key, whatsapp_id, telegram_id, telegram_username, tenant_id
                    )
                    if contact_id:
                        user_id = f"contact_{contact_id}"
                        self.logger.info(f"✅ Retrieving context for contact_id={contact_id} (tenant: {tenant_id})")
                    else:
                        # Fallback to sender-based key
                        user_id = f"sender_{sender_key}"
                        self.logger.warning(f"❌ Contact not found for context, using sender-based: {sender_key} (whatsapp={whatsapp_id}, telegram={telegram_id}, tenant={tenant_id})")
                else:
                    # Legacy sender-based memory
                    user_id = f"sender_{sender_key}"

        context = await memory.get_context(
            user_id=user_id,
            current_message=current_message,
            include_knowledge=include_knowledge,
            include_shared=include_shared  # Phase 4.8 Week 4 complete
        )

        return context

    def clear_agent_memory(self, agent_id: int, sender_key: str) -> None:
        """
        Clear all memory for a specific agent-sender pair.

        Args:
            agent_id: Agent ID
            sender_key: Original sender key (phone/chat_id)
        """
        memory_key = self.get_memory_key(agent_id, sender_key)

        if agent_id in self.agent_memories:
            memory = self.agent_memories[agent_id]
            memory.clear_sender(memory_key)
            self.logger.info(f"Cleared memory for agent {agent_id}, sender {sender_key}")

    def get_stats(self, agent_id: Optional[int] = None) -> Dict:
        """
        Get memory statistics for one or all agents.

        Args:
            agent_id: Optional agent ID (None = all agents)

        Returns:
            Dictionary with statistics
        """
        if agent_id is not None:
            # Stats for specific agent
            if agent_id in self.agent_memories:
                memory = self.agent_memories[agent_id]
                stats = memory.get_stats()
                stats['agent_id'] = agent_id
                return stats
            else:
                return {'agent_id': agent_id, 'status': 'not_loaded'}
        else:
            # Stats for all agents
            all_stats = {
                'total_agents': len(self.agent_memories),
                'agents': {}
            }

            for aid, memory in self.agent_memories.items():
                all_stats['agents'][aid] = memory.get_stats()

            return all_stats
