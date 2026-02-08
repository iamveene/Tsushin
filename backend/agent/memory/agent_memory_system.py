"""
Agent Memory System - Phase 4.8

Comprehensive 4-layer memory architecture for individual agents:

Layer 1: Working Memory - Ring buffer (last N messages, fast access)
Layer 2: Long-Term Episodic Memory - Unlimited conversation history with semantic search
Layer 3: Semantic Knowledge Base - Learned facts about users
Layer 4: Shared Memory Pool - Cross-agent knowledge (accessed via manager)

Each agent maintains their own isolated memory system.
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from .semantic_memory import SemanticMemoryService
from .fact_extractor import FactExtractor
from .knowledge_service import KnowledgeService
from .shared_memory_pool import SharedMemoryPool


class AgentMemorySystem:
    """
    Complete memory system for a single agent.

    Coordinates all memory layers and provides unified interface
    for storing and retrieving information.
    """

    def __init__(
        self,
        agent_id: int,
        db_session: Session,
        config: Dict,
        persist_directory: str
    ):
        """
        Initialize agent memory system.

        Args:
            agent_id: Agent ID
            db_session: Database session for persistence
            config: Configuration dictionary
            persist_directory: Directory for vector store persistence
        """
        self.logger = logging.getLogger(__name__)
        self.agent_id = agent_id
        self.db = db_session
        self.config = config

        # Layer 1 + 2: Working memory + Episodic memory (via SemanticMemoryService)
        self.semantic_memory = SemanticMemoryService(
            persist_directory=persist_directory,
            max_ring_buffer_size=config.get("memory_size", 10),
            enable_semantic=config.get("enable_semantic_search", False)
        )

        # Layer 3: Semantic Knowledge Base (facts about users)
        # Stored in database, accessed via helper methods
        self.knowledge_cache: Dict[str, Dict] = {}  # user_id -> {topic: {key: value}}
        self.knowledge_service = KnowledgeService(db_session)
        # Initialize FactExtractor with agent's provider/model for consistency
        self.fact_extractor = FactExtractor(
            provider=config.get("model_provider"),
            model_name=config.get("model_name"),
            db=db_session
        )

        # Layer 4: Shared Memory Pool (cross-agent knowledge)
        self.shared_memory_pool = SharedMemoryPool(db_session)

        # Fact extraction configuration
        self.auto_extract_facts = config.get("auto_extract_facts", True)
        self.extraction_threshold = config.get("fact_extraction_threshold", 5)  # messages

        # Load existing memory from database on startup
        self._load_memory_from_db()

        self.logger.info(f"AgentMemorySystem initialized for agent {agent_id}")

    def _load_memory_from_db(self) -> None:
        """
        Load persisted memory from the database into the ring buffer.

        This ensures memory survives container restarts.
        """
        from models import Memory

        try:
            # Load all memory records for this agent
            memory_records = self.db.query(Memory).filter(
                Memory.agent_id == self.agent_id
            ).all()

            loaded_count = 0
            for record in memory_records:
                sender_key = record.sender_key
                messages = record.messages_json

                if messages:
                    # Deserialize messages into ring buffer
                    self.semantic_memory.ring_buffer.deserialize(sender_key, messages)
                    loaded_count += 1

            if loaded_count > 0:
                self.logger.info(f"Loaded memory for {loaded_count} conversations from database")

        except Exception as e:
            self.logger.error(f"Failed to load memory from database: {e}")

    async def add_message(
        self,
        user_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Add a message to agent memory (Layer 1 + 2).

        Args:
            user_id: User identifier (sender_key)
            role: Message role ('user' or 'assistant')
            content: Message content
            message_id: Optional unique message ID
            metadata: Optional additional metadata
        """
        # Add agent_id to metadata
        if metadata is None:
            metadata = {}
        metadata['agent_id'] = self.agent_id

        # Add to working memory + episodic memory
        self.semantic_memory.add_message(
            sender_key=user_id,
            role=role,
            content=content,
            message_id=message_id,
            metadata=metadata
        )

        self.logger.debug(f"Agent {self.agent_id}: Added {role} message from {user_id}")

        # Persist to database (Memory table) for stats and conversation inspection
        self._persist_memory_to_db(user_id)

        # Trigger fact extraction if enabled and threshold met
        if self.auto_extract_facts and role == 'assistant':
            await self._maybe_extract_facts(user_id)

    async def get_context(
        self,
        user_id: str,
        current_message: str,
        include_knowledge: bool = True,
        include_shared: bool = False
    ) -> Dict:
        """
        Get comprehensive context for responding to a message.

        Combines:
        - Layer 1: Recent messages (working memory)
        - Layer 2: Semantically relevant past messages
        - Layer 3: Known facts about the user (optional)
        - Layer 4: Shared knowledge from other agents (optional)

        Args:
            user_id: User identifier
            current_message: Current message to respond to
            include_knowledge: Include learned facts about user
            include_shared: Include shared memory from other agents

        Returns:
            Dictionary with all context layers
        """
        context = {
            'working_memory': [],       # Recent messages
            'episodic_memories': [],    # Relevant past conversations
            'semantic_facts': {},       # Known user information
            'shared_knowledge': []      # Cross-agent knowledge
        }

        # Layer 1 + 2: Get hybrid context from semantic memory
        memory_context = self.semantic_memory.get_context(
            sender_key=user_id,
            current_message=current_message,
            max_semantic_results=self.config.get("semantic_search_results", 5),
            similarity_threshold=self.config.get("semantic_similarity_threshold", 0.3)
        )

        context['working_memory'] = memory_context.get('recent_messages', [])
        context['episodic_memories'] = memory_context.get('semantic_messages', [])

        # Layer 3: Get semantic knowledge about user
        if include_knowledge:
            facts = self._get_user_facts(user_id)
            context['semantic_facts'] = facts

        # Layer 4: Shared memory (cross-agent knowledge)
        if include_shared:
            shared_knowledge = self.shared_memory_pool.get_accessible_knowledge(
                agent_id=self.agent_id,
                limit=self.config.get("shared_memory_results", 5)
            )
            context['shared_knowledge'] = shared_knowledge

        return context

    def _get_user_facts(self, user_id: str) -> Dict:
        """
        Get learned facts about a user from semantic knowledge base (Layer 3).

        Args:
            user_id: User identifier

        Returns:
            Dictionary of facts organized by topic
        """
        # Check cache first
        if user_id in self.knowledge_cache:
            return self.knowledge_cache[user_id]

        # Query database
        from models import SemanticKnowledge

        facts_by_topic = {}

        try:
            results = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == self.agent_id,
                SemanticKnowledge.user_id == user_id
            ).all()

            for fact in results:
                topic = fact.topic
                if topic not in facts_by_topic:
                    facts_by_topic[topic] = {}

                facts_by_topic[topic][fact.key] = {
                    'value': fact.value,
                    'confidence': fact.confidence,
                    'learned_at': fact.learned_at.isoformat() if fact.learned_at else None
                }

            # Cache the results
            self.knowledge_cache[user_id] = facts_by_topic

        except Exception as e:
            self.logger.error(f"Failed to load user facts: {e}")

        return facts_by_topic

    async def learn_fact(
        self,
        user_id: str,
        topic: str,
        key: str,
        value: str,
        confidence: float = 1.0
    ) -> bool:
        """
        Learn a new fact about a user (Layer 3).

        Args:
            user_id: User identifier
            topic: Fact topic/category (e.g., 'preferences', 'personal_info')
            key: Fact key (e.g., 'favorite_color', 'job')
            value: Fact value
            confidence: Confidence score (0.0-1.0)

        Returns:
            True if successful
        """
        from models import SemanticKnowledge
        from sqlalchemy import insert, update

        try:
            # Check if fact already exists
            existing = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == self.agent_id,
                SemanticKnowledge.user_id == user_id,
                SemanticKnowledge.topic == topic,
                SemanticKnowledge.key == key
            ).first()

            if existing:
                # Update existing fact
                existing.value = value
                existing.confidence = confidence
                existing.updated_at = datetime.utcnow()
                self.logger.debug(f"Updated fact: {topic}.{key} = {value}")
            else:
                # Insert new fact
                new_fact = SemanticKnowledge(
                    agent_id=self.agent_id,
                    user_id=user_id,
                    topic=topic,
                    key=key,
                    value=value,
                    confidence=confidence
                )
                self.db.add(new_fact)
                self.logger.debug(f"Learned fact: {topic}.{key} = {value}")

            self.db.commit()

            # Invalidate cache
            if user_id in self.knowledge_cache:
                del self.knowledge_cache[user_id]

            return True

        except Exception as e:
            self.logger.error(f"Failed to learn fact: {e}")
            self.db.rollback()
            return False

    def format_context_for_prompt(
        self,
        context: Dict,
        max_chars: int = 50000,
        user_id: Optional[str] = None,
        include_tool_outputs: bool = False
    ) -> str:
        """
        Format context dictionary into a string for inclusion in AI prompt.

        Args:
            context: Context dictionary from get_context()
            max_chars: Maximum characters to include (default 50k to stay within model limits)
            user_id: Optional user ID for adaptive personality injection
            include_tool_outputs: If False, exclude messages marked as tool outputs to prevent
                                  tool context bleeding into unrelated conversations (default: False)

        Returns:
            Formatted string for prompt (truncated if necessary)
        """
        lines = []
        current_chars = 0
        skipped_tool_outputs = 0

        # Check if adaptive_personality skill is enabled for this agent
        adaptive_personality_enabled = False
        if user_id:
            try:
                from models import AgentSkill
                skill = self.db.query(AgentSkill).filter(
                    AgentSkill.agent_id == self.agent_id,
                    AgentSkill.skill_type == "adaptive_personality",
                    AgentSkill.is_enabled == True
                ).first()
                adaptive_personality_enabled = (skill is not None)
            except Exception as e:
                self.logger.warning(f"Could not check adaptive_personality skill: {e}")

        # Working Memory (recent conversation) - limit to last 20 messages
        if context['working_memory']:
            lines.append("=== Recent Conversation ===")
            current_chars += len(lines[-1])

            # Take only the last 20 messages to avoid massive context
            recent_msgs = context['working_memory'][-20:] if len(context['working_memory']) > 20 else context['working_memory']

            for msg in recent_msgs:
                # Fix: Skip tool output messages unless explicitly requested
                # This prevents tool execution context from bleeding into unrelated conversations
                msg_metadata = msg.get('metadata', {})
                if not include_tool_outputs and msg_metadata.get('is_tool_output'):
                    skipped_tool_outputs += 1
                    self.logger.debug(f"Skipping tool output message from context (tool: {msg_metadata.get('tool_used', 'unknown')})")
                    continue

                role = msg['role'].upper()
                content = msg['content']
                sender_info = msg.get('sender_name', '')

                if sender_info:
                    line = f"[{role} - {sender_info}] {content}"
                else:
                    line = f"[{role}] {content}"

                # Check if adding this line would exceed limit
                if current_chars + len(line) > max_chars:
                    lines.append("... [context truncated to stay within limits]")
                    break

                lines.append(line)
                current_chars += len(line)

        if skipped_tool_outputs > 0:
            self.logger.info(f"Filtered out {skipped_tool_outputs} tool output message(s) from context")

        # Episodic Memory (relevant past messages)
        if context['episodic_memories']:
            lines.append("\n=== Relevant Past Messages ===")
            for msg in context['episodic_memories']:
                similarity = msg.get('similarity', 0)
                content = msg['content']
                sender_info = msg.get('sender_name', '')
                if sender_info:
                    lines.append(f"[PAST - {similarity:.0%} - {sender_info}] {content}")
                else:
                    lines.append(f"[PAST - {similarity:.0%}] {content}")

        # Semantic Knowledge (learned facts)
        if context['semantic_facts']:
            lines.append("\n=== What I Know About This User ===")
            for topic, facts in context['semantic_facts'].items():
                # Skip communication style topics if adaptive personality is enabled
                # (they'll be formatted specially below)
                if adaptive_personality_enabled and topic in ['communication_style', 'inside_jokes', 'linguistic_patterns']:
                    continue

                lines.append(f"[{topic.upper()}]")
                for key, data in facts.items():
                    value = data['value']
                    confidence = data.get('confidence', 1.0)
                    lines.append(f"  - {key}: {value} (confidence: {confidence:.0%})")

        # Adaptive Personality Context (Phase 4.8 Week 3)
        if adaptive_personality_enabled and user_id:
            try:
                style_prompt = self.knowledge_service.format_communication_style_prompt(
                    agent_id=self.agent_id,
                    user_id=user_id,
                    min_confidence=0.7
                )
                if style_prompt:
                    lines.append("\n" + style_prompt)
            except Exception as e:
                self.logger.error(f"Failed to inject adaptive personality context: {e}")

        # Shared Knowledge (cross-agent)
        if context['shared_knowledge']:
            lines.append("\n=== Shared Knowledge (From Other Agents) ===")
            for item in context['shared_knowledge']:
                content = item.get('content', '')
                topic = item.get('topic', 'general')
                shared_by = item.get('shared_by_agent', 'unknown')
                lines.append(f"  [{topic.upper()} - Agent {shared_by}] {content}")

        return "\n".join(lines) if lines else "[No previous context]"

    def _persist_memory_to_db(self, user_id: str) -> None:
        """
        Persist the current ring buffer state for a user to the Memory table.

        This enables:
        - Memory statistics in the UI
        - Conversation inspection and management
        - Memory persistence across container restarts

        Args:
            user_id: User identifier (sender_key)
        """
        from models import Memory

        try:
            # Get current messages from ring buffer
            messages = self.semantic_memory.ring_buffer.get_messages(user_id)

            if not messages:
                return

            # Check if memory record exists for this agent+sender
            memory_record = self.db.query(Memory).filter(
                Memory.agent_id == self.agent_id,
                Memory.sender_key == user_id
            ).first()

            if memory_record:
                # Update existing record
                memory_record.messages_json = messages
                memory_record.updated_at = datetime.utcnow()
            else:
                # Create new record
                memory_record = Memory(
                    agent_id=self.agent_id,
                    sender_key=user_id,
                    messages_json=messages
                )
                self.db.add(memory_record)

            self.db.commit()
            self.logger.debug(f"Persisted {len(messages)} messages for agent {self.agent_id}, user {user_id}")

        except Exception as e:
            self.logger.error(f"Failed to persist memory to database: {e}")
            self.db.rollback()

    def clear_user_memory(self, user_id: str, clear_facts: bool = False) -> None:
        """
        Clear memory for a specific user.

        Args:
            user_id: User identifier
            clear_facts: If True, also clear learned facts (Layer 3)
        """
        from models import Memory, SemanticKnowledge

        # Clear working memory + episodic memory (in-memory)
        self.semantic_memory.clear_sender(user_id)

        # Clear from database (Memory table)
        try:
            self.db.query(Memory).filter(
                Memory.agent_id == self.agent_id,
                Memory.sender_key == user_id
            ).delete()
            self.db.commit()
            self.logger.info(f"Cleared memory for agent {self.agent_id}, user {user_id}")
        except Exception as e:
            self.logger.error(f"Failed to clear memory from database: {e}")
            self.db.rollback()

        # Optionally clear learned facts
        if clear_facts:
            try:
                self.db.query(SemanticKnowledge).filter(
                    SemanticKnowledge.agent_id == self.agent_id,
                    SemanticKnowledge.user_id == user_id
                ).delete()
                self.db.commit()

                # Invalidate cache
                if user_id in self.knowledge_cache:
                    del self.knowledge_cache[user_id]

                self.logger.info(f"Cleared all facts for user {user_id}")

            except Exception as e:
                self.logger.error(f"Failed to clear facts: {e}")
                self.db.rollback()

    def get_stats(self) -> Dict:
        """
        Get memory statistics for this agent.

        Returns:
            Dictionary with statistics
        """
        stats = {
            'agent_id': self.agent_id,
            'working_memory': self.semantic_memory.get_stats(),
            'knowledge_facts_cached': len(self.knowledge_cache)
        }

        # Count total facts in database
        from models import SemanticKnowledge

        try:
            fact_count = self.db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == self.agent_id
            ).count()
            stats['knowledge_facts_total'] = fact_count
        except Exception as e:
            self.logger.error(f"Failed to count facts: {e}")
            stats['knowledge_facts_total'] = 0

        return stats

    async def _maybe_extract_facts(self, user_id: str) -> None:
        """
        Trigger fact extraction if conversation is substantial enough.

        Args:
            user_id: User identifier
        """
        try:
            # Get recent conversation from working memory
            context = self.semantic_memory.get_context(
                sender_key=user_id,
                current_message="",
                max_semantic_results=0  # Only need recent messages
            )

            conversation = context.get('recent_messages', [])

            # Check if extraction should be attempted (Phase 4.8 Week 3: pass agent_id and db for adaptive_personality)
            if not self.fact_extractor.should_extract_facts(
                conversation,
                min_user_messages=self.extraction_threshold,
                agent_id=self.agent_id,
                db_session=self.db
            ):
                return

            self.logger.info(f"Extracting facts from conversation with {user_id}")

            # Extract facts
            facts = await self.fact_extractor.extract_facts(
                conversation=conversation,
                user_id=user_id,
                agent_id=self.agent_id
            )

            # MemGuard Layer B: Validate facts before storage
            if facts:
                facts = self._validate_facts_memguard(facts, user_id)

            # Store extracted facts
            for fact in facts:
                success = self.knowledge_service.store_fact(
                    agent_id=self.agent_id,
                    user_id=user_id,
                    topic=fact['topic'],
                    key=fact['key'],
                    value=fact['value'],
                    confidence=fact['confidence']
                )

                if success:
                    # Invalidate cache for this user
                    if user_id in self.knowledge_cache:
                        del self.knowledge_cache[user_id]

            if facts:
                self.logger.info(f"Extracted and stored {len(facts)} facts for {user_id}")

        except Exception as e:
            self.logger.error(f"Fact extraction failed: {e}")

    def _get_tenant_id(self) -> Optional[str]:
        """Get tenant_id for this agent from the database."""
        try:
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == self.agent_id).first()
            return agent.tenant_id if agent else None
        except Exception as e:
            self.logger.error(f"Failed to get tenant_id for agent {self.agent_id}: {e}")
            return None

    def _validate_facts_memguard(self, facts: List[Dict], user_id: str) -> List[Dict]:
        """
        MemGuard Layer B: Validate extracted facts before storage.

        Runs fact validation through MemGuardService to catch:
        - Credential-like values
        - Command patterns in instruction facts
        - Suspicious overrides of established facts

        Fail-open: returns all facts if validation errors occur.

        Args:
            facts: List of extracted fact dicts
            user_id: User identifier

        Returns:
            Filtered list of validated facts
        """
        try:
            tenant_id = self._get_tenant_id()
            if not tenant_id:
                return facts  # Can't validate without tenant context

            from services.sentinel_service import SentinelService
            sentinel = SentinelService(self.db, tenant_id)
            effective_config = sentinel.get_effective_config(self.agent_id)

            memguard_enabled = effective_config.detection_config.get(
                "memory_poisoning", {}
            ).get("enabled", True)

            if not memguard_enabled:
                return facts

            from services.memguard_service import MemGuardService
            memguard = MemGuardService(self.db, tenant_id)

            detection_mode = getattr(effective_config, "detection_mode", "block")

            # Batch-fetch existing facts once (not per-fact)
            existing_facts = self.knowledge_service.get_user_facts(
                agent_id=self.agent_id,
                user_id=user_id
            )

            validated_facts = []
            blocked_count = 0
            flagged_count = 0

            for fact in facts:
                validation = memguard.validate_fact(
                    fact=fact,
                    existing_facts=existing_facts,
                    agent_id=self.agent_id,
                    user_id=user_id,
                    detection_mode=detection_mode,
                )

                if validation.is_valid:
                    validated_facts.append(fact)
                    if validation.flagged:
                        flagged_count += 1
                        self.logger.info(
                            f"🛡️ MEMGUARD Layer B (detect_only): Flagged fact allowed - "
                            f"topic={fact.get('topic')}, key={fact.get('key')}: {validation.reason}"
                        )
                else:
                    blocked_count += 1
                    self.logger.warning(
                        f"🛡️ MEMGUARD Layer B: Blocked fact - "
                        f"topic={fact.get('topic')}, key={fact.get('key')}: {validation.reason}"
                    )

            if blocked_count > 0:
                self.logger.info(
                    f"🛡️ MEMGUARD Layer B: {blocked_count}/{len(facts)} facts blocked for {user_id}"
                )
            if flagged_count > 0:
                self.logger.info(
                    f"🛡️ MEMGUARD Layer B: {flagged_count}/{len(facts)} facts flagged (allowed) for {user_id}"
                )

            return validated_facts

        except Exception as e:
            self.logger.warning(f"MemGuard Layer B validation failed, allowing all facts: {e}")
            return facts

    async def extract_facts_now(self, user_id: str) -> List[Dict]:
        """
        Manually trigger fact extraction for a user conversation.

        Args:
            user_id: User identifier

        Returns:
            List of extracted facts
        """
        try:
            # Get full conversation from working memory
            context = self.semantic_memory.get_context(
                sender_key=user_id,
                current_message="",
                max_semantic_results=0
            )

            conversation = context.get('recent_messages', [])

            if not conversation:
                self.logger.warning(f"No conversation history for {user_id}")
                return []

            # Extract facts
            facts = await self.fact_extractor.extract_facts(
                conversation=conversation,
                user_id=user_id,
                agent_id=self.agent_id
            )

            # Store extracted facts
            for fact in facts:
                self.knowledge_service.store_fact(
                    agent_id=self.agent_id,
                    user_id=user_id,
                    topic=fact['topic'],
                    key=fact['key'],
                    value=fact['value'],
                    confidence=fact['confidence']
                )

            # Invalidate cache
            if user_id in self.knowledge_cache:
                del self.knowledge_cache[user_id]

            self.logger.info(f"Manual extraction: {len(facts)} facts for {user_id}")
            return facts

        except Exception as e:
            self.logger.error(f"Manual fact extraction failed: {e}")
            return []
