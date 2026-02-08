"""
Playground Service
Handles user interactions with agents through the UI Playground interface.
Maintains consistency with WhatsApp message processing.
"""

import logging
from typing import Dict, List, Optional, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime

from agent.utils import summarize_tool_result
from agent.memory.tool_output_buffer import get_tool_output_buffer
# Phase 8: Watcher Activity Events
from services.watcher_activity_service import emit_agent_processing_async

logger = logging.getLogger(__name__)


class PlaygroundService:
    """
    Service for handling Playground chat interactions.

    Key responsibilities:
    - Resolve user identity to contact/sender_key
    - Invoke agents using existing AgentService for consistency
    - Store messages via MultiAgentMemoryManager
    - Support audio transcription (prepared for v2)

    IMPORTANT: Maintains same order of operations as WhatsApp (router.py):
    1. Add user message to memory FIRST
    2. Get context (which now includes the new message)
    3. Process with agent
    4. Add agent response to memory
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

        # Phase 7.2: Initialize token tracker for usage tracking
        from analytics.token_tracker import TokenTracker
        self.token_tracker = TokenTracker(db)

    def resolve_user_identity(self, user_id: int) -> Optional[str]:
        """
        Resolve RBAC user to sender_key for memory consistency.

        Flow:
        1. Check UserContactMapping for user_id
        2. If mapped, get Contact and return phone_number or whatsapp_id
        3. If not mapped, return generic identifier

        Args:
            user_id: RBAC user ID

        Returns:
            sender_key (phone number or contact identifier) or None
        """
        from models import UserContactMapping, Contact

        try:
            # Check if user is mapped to a contact
            mapping = self.db.query(UserContactMapping).filter(
                UserContactMapping.user_id == user_id
            ).first()

            if mapping:
                # Get the contact
                contact = self.db.query(Contact).filter(
                    Contact.id == mapping.contact_id
                ).first()

                if contact:
                    # Prefer phone_number, fallback to whatsapp_id, then contact_id
                    sender_key = (
                        contact.phone_number or
                        contact.whatsapp_id or
                        f"contact_{contact.id}"
                    )
                    self.logger.info(f"User {user_id} mapped to contact '{contact.friendly_name}' (sender_key: {sender_key})")
                    return sender_key

            # No mapping found, use generic identifier
            sender_key = f"playground_user_{user_id}"
            self.logger.info(f"User {user_id} not mapped to contact, using generic sender_key: {sender_key}")
            return sender_key

        except Exception as e:
            self.logger.error(f"Error resolving user identity for user {user_id}: {e}", exc_info=True)
            return f"playground_user_{user_id}"

    async def send_message(
        self,
        user_id: int,
        agent_id: int,
        message_text: str,
        thread_id: Optional[int] = None,
        media_type: Optional[str] = None,
        media_data: Optional[bytes] = None,
        skip_user_message: bool = False,
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message to an agent from the playground.

        CRITICAL: Follows WhatsApp order (router.py):
        1. Add user message to memory FIRST (unless skip_user_message=True)
        2. Get context (includes new message)
        3. Process with agent
        4. Add agent response

        HIGH-011 Defense-in-depth: tenant_id validation at service layer.
        API layer should already validate, but we check here as well.

        Args:
            user_id: RBAC user ID
            agent_id: Agent ID to interact with
            message_text: User message content
            thread_id: Optional thread ID for proper message isolation
            media_type: Optional media type (e.g., 'audio/ogg') for v2
            media_data: Optional media bytes for v2
            skip_user_message: If True, skip adding user message (for regeneration)
            tenant_id: Optional tenant ID for defense-in-depth validation

        Returns:
            Dict with agent response and metadata
        """
        from models import Agent, Contact, UserContactMapping
        from agent.agent_service import AgentService
        from agent.memory.multi_agent_memory import MultiAgentMemoryManager

        try:
            # FIX 2026-01-30: Thread isolation takes priority for Playground
            # Previously, contact-based sender_key took priority which caused ALL threads
            # to share the same memory (breaking thread isolation)
            # Now: thread_id > contact-based > generic user key
            if thread_id:
                # Phase 14.1: Use thread-specific sender_key for thread isolation
                sender_key = f"playground_u{user_id}_a{agent_id}_t{thread_id}"
                self.logger.info(f"Using thread-specific sender_key: {sender_key}")
            else:
                # Fallback for backward compatibility - check contact mapping
                user_contact_mapping = self.db.query(UserContactMapping).filter(
                    UserContactMapping.user_id == user_id
                ).first()

                if user_contact_mapping:
                    contact = self.db.query(Contact).filter(Contact.id == user_contact_mapping.contact_id).first()
                    if contact and contact.phone_number:
                        sender_key = contact.phone_number
                        self.logger.info(f"Using contact-based sender_key (no thread): {sender_key}")
                    elif contact and contact.whatsapp_id:
                        sender_key = contact.whatsapp_id
                        self.logger.info(f"Using contact whatsapp_id sender_key (no thread): {sender_key}")
                    else:
                        sender_key = f"playground_user_{user_id}"
                        self.logger.warning(f"Contact has no phone/whatsapp, using user-based key")
                else:
                    sender_key = self.resolve_user_identity(user_id)
                    self.logger.warning(f"No thread_id or contact mapping, using generic sender_key: {sender_key}")

            if not sender_key:
                return {
                    "error": "Failed to resolve user identity",
                    "status": "error"
                }

            # Get agent configuration with optional tenant validation (HIGH-011 defense-in-depth)
            query = self.db.query(Agent).filter(Agent.id == agent_id)
            if tenant_id:
                query = query.filter(Agent.tenant_id == tenant_id)
            agent = query.first()
            if not agent or not agent.is_active:
                return {
                    "error": f"Agent {agent_id} not found or inactive",
                    "status": "error"
                }

            # Phase 10: Check if playground channel is enabled for this agent
            import json as json_module
            enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                json_module.loads(agent.enabled_channels) if agent.enabled_channels else ["playground", "whatsapp"]
            )
            if "playground" not in enabled_channels:
                return {
                    "error": f"Agent {agent_id} does not have Playground channel enabled",
                    "status": "error"
                }

            # Get agent name from contact
            contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent_id}"

            # BUG-013 Fix: Load user's playground settings for model configuration
            from models import PlaygroundUserSettings
            user_settings = self.db.query(PlaygroundUserSettings).filter(
                PlaygroundUserSettings.user_id == user_id,
                PlaygroundUserSettings.tenant_id == agent.tenant_id
            ).first()

            # Extract model settings from user preferences
            temperature = None
            max_tokens = None
            model_override = None
            if user_settings and user_settings.settings_json:
                model_settings = user_settings.settings_json.get("modelSettings", {})
                # Settings are stored per-agent: { agentId: { temperature, maxTokens, modelOverride } }
                agent_settings = model_settings.get(str(agent_id), {})
                temperature = agent_settings.get("temperature")
                max_tokens = agent_settings.get("maxTokens")
                model_override = agent_settings.get("modelOverride")  # Session model override
                self.logger.info(f"Loaded user model settings for agent {agent_id}: temp={temperature}, max_tokens={max_tokens}, model_override={model_override}")

            # Determine which model to use (override or agent default)
            effective_model = model_override if model_override else agent.model_name

            # ENHANCED LOGGING: Confirm model selection
            self.logger.info(f"[MODEL SELECTION] Agent default: {agent.model_name}")
            self.logger.info(f"[MODEL SELECTION] User override: {model_override if model_override else 'None'}")
            self.logger.info(f"[MODEL SELECTION] Effective model: {effective_model}")
            self.logger.info(f"[MODEL SELECTION] Provider: {agent.model_provider}")

            if model_override and model_override != agent.model_name:
                self.logger.info(f"✅ Using model override: {model_override} (agent default: {agent.model_name})")

            # Build agent configuration dictionary
            config_dict = {
                "agent_id": agent.id,
                "agent_name": agent_name,
                "model_provider": agent.model_provider,
                "model_name": effective_model,  # Use effective model (override or default)
                "system_prompt": agent.system_prompt,
                "memory_size": agent.memory_size or 1000,
                "enabled_tools": [],  # Deprecated: tools migrated to Skills system
                "response_template": agent.response_template,
                "enable_semantic_search": agent.enable_semantic_search,
                "context_message_count": agent.context_message_count or 10,
                "memory_isolation_mode": agent.memory_isolation_mode or "isolated",
                # BUG-013 Fix: Pass model settings from playground user preferences
                "temperature": temperature,
                "max_tokens": max_tokens,
                "semantic_search_results": agent.semantic_search_results or 10,
                "semantic_similarity_threshold": agent.semantic_similarity_threshold or 0.5,
                # Fact extraction configuration (auto-enabled for all conversations)
                "auto_extract_facts": True,
                "fact_extraction_threshold": 3,  # Lower threshold for playground (faster testing)
            }

            # Initialize memory manager
            memory_manager = MultiAgentMemoryManager(self.db, config_dict)

            # STEP 0: Sentinel Security Analysis BEFORE memory storage
            # Phase 21: This prevents memory poisoning from blocked messages
            # The message must be analyzed BEFORE storing to memory, otherwise
            # malicious content pollutes the agent's memory even if blocked
            if not skip_user_message and agent.tenant_id:
                try:
                    from services.sentinel_service import SentinelService
                    sentinel = SentinelService(self.db, agent.tenant_id)

                    sentinel_result = await sentinel.analyze_prompt(
                        prompt=message_text,
                        agent_id=agent_id,
                        sender_key=sender_key,
                        source=None,  # User message - no internal source tag
                    )

                    if sentinel_result.is_threat_detected:
                        if sentinel_result.action == "blocked":
                            self.logger.warning(
                                f"🛡️ SENTINEL: Blocking message BEFORE memory storage - "
                                f"{sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                            )
                            # Return early with blocked response (no memory storage = no poisoning)
                            return {
                                "status": "blocked",
                                "message": sentinel_result.threat_reason or "Message blocked for security reasons.",
                                "agent_name": agent_name,
                                "security_blocked": True,
                                "threat_type": sentinel_result.detection_type,
                                "timestamp": datetime.utcnow().isoformat() + "Z"
                            }
                        # detect_only mode: threat detected but allowed - will proceed to store message
                        self.logger.info(
                            f"🛡️ SENTINEL (detect_only): Threat detected but allowing - "
                            f"{sentinel_result.detection_type}"
                        )
                except Exception as e:
                    self.logger.warning(f"Sentinel pre-check failed, allowing message: {e}")

            # STEP 1: Add user message to memory FIRST (WhatsApp consistency)
            # This ensures the message is in context for agent processing
            # Skip if skip_user_message=True (for regeneration after edit)
            message_id = f"msg_user_{user_id}_{int(datetime.utcnow().timestamp() * 1000)}"
            if not skip_user_message:
                await memory_manager.add_message(
                    agent_id=agent_id,
                    sender_key=sender_key,
                    role="user",
                    content=message_text,
                    chat_id=f"playground_{user_id}",
                    message_id=message_id,
                    metadata={
                        "source": "playground",
                        "agent_id": agent_id,
                        "user_id": user_id
                    }
                )
                self.logger.info(f"Added user message to memory before processing (WhatsApp consistency)")
            else:
                self.logger.info(f"Skipping user message add (regeneration mode)")

            # Phase 14.5: Index user message in FTS5 for conversation search
            # Skip if skip_user_message=True (for regeneration after edit)
            if not skip_user_message:
                try:
                    # Look up or get thread_id for this conversation (if not provided)
                    from models import ConversationThread
                    fts_thread_id = thread_id
                    if not fts_thread_id:
                        thread = self.db.query(ConversationThread).filter(
                            ConversationThread.user_id == user_id,
                            ConversationThread.agent_id == agent_id,
                            ConversationThread.thread_type == "playground",
                            ConversationThread.is_archived == False,
                            ConversationThread.status == "active"
                        ).order_by(ConversationThread.id.desc()).first()

                        fts_thread_id = thread.id if thread else None

                    # Insert into FTS5 table
                    self.db.execute(text("""
                        INSERT INTO conversation_search_fts
                        (thread_id, message_id, role, content, timestamp, tenant_id, user_id, agent_id)
                        VALUES (:thread_id, :message_id, :role, :content, :timestamp, :tenant_id, :user_id, :agent_id)
                    """), {
                        "thread_id": fts_thread_id,
                        "message_id": message_id,
                        "role": "user",
                        "content": message_text,
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "tenant_id": agent.tenant_id,
                        "user_id": user_id,
                        "agent_id": agent_id
                    })
                    self.db.commit()
                    self.logger.debug(f"Indexed user message in FTS5 (thread_id={fts_thread_id})")
                except Exception as e:
                    self.logger.warning(f"Failed to index user message in FTS5: {e}")

            # STEP 2: Get FULL 4-layer memory context (Phase 9.2 - WhatsApp parity)
            # Layer 1: Working memory (recent messages)
            # Layer 2: Episodic memory (semantic search of past conversations)
            # Layer 3: Semantic knowledge (learned facts about user)
            # Layer 4: Shared memory (cross-agent knowledge pool)
            memory_context = await memory_manager.get_context(
                agent_id=agent_id,
                sender_key=sender_key,
                current_message=message_text,
                max_semantic_results=config_dict.get("semantic_search_results", 5),
                similarity_threshold=config_dict.get("semantic_similarity_threshold", 0.3),
                include_knowledge=True,  # Layer 3: Include learned facts about user
                include_shared=True,  # Layer 4: Include cross-agent shared knowledge
                chat_id=f"playground_{user_id}",
                use_contact_mapping=True
            )

            # Build full message with context using format_context_for_prompt()
            # This is the same method used by WhatsApp router for consistent behavior
            full_message = message_text

            if config_dict.get("enable_semantic_search", False) and memory_context:
                agent_memory = memory_manager.get_agent_memory(agent_id)
                context_str = agent_memory.format_context_for_prompt(memory_context, user_id=sender_key)
                if context_str and context_str != "[No previous context]":
                    full_message = f"{context_str}\n\n[Current message from Playground]: {message_text}"
                    self.logger.info(f"Injected full 4-layer memory context ({len(context_str)} chars)")
                else:
                    full_message = f"[Message from Playground]: {message_text}"
            else:
                # Fallback: simple context for agents without semantic search
                if memory_context and memory_context.get("working_memory"):
                    context_str = "\n".join([
                        f"[{msg['role'].upper()}] {msg['content']}"
                        for msg in memory_context["working_memory"][-5:]
                    ])
                    full_message = f"Recent conversation:\n{context_str}\n\n[Current message]: {message_text}"

            # Layer 5: Selective tool output injection
            # - Always show lightweight reference (what tools are available)
            # - Inject full output only when user explicitly requests it (via /inject or natural language)
            tool_buffer = get_tool_output_buffer()
            tool_buffer.increment_message_count(agent_id, sender_key)
            tool_context = tool_buffer.get_context_for_injection(agent_id, sender_key, message_text)
            if tool_context:
                full_message = f"{tool_context}\n\n{full_message}"
                self.logger.info(f"Injected Layer 5 tool context ({len(tool_context)} chars)")

            # STEP 3: Process with skills FIRST (if agent has skills enabled)
            from agent.skills.skill_manager import SkillManager
            from agent.skills.base import InboundMessage, SkillResult

            skill_result = None
            skills_processed = False

            # Create InboundMessage for skill processing
            inbound_msg = InboundMessage(
                id=f"playground_{user_id}_{datetime.utcnow().timestamp()}",
                sender=f"playground_user_{user_id}",
                sender_key=sender_key,
                body=message_text,
                chat_id=f"playground_{user_id}",
                chat_name="Playground",
                is_group=False,
                timestamp=datetime.utcnow(),
                media_type=media_type,
                media_url=None,
                media_path=None,
                channel="playground"  # Skills-as-Tools: playground channel
            )

            # Try to process with skills
            from agent.skills.skill_manager import get_skill_manager
            skill_manager = get_skill_manager()
            try:
                skill_result = await skill_manager.process_message_with_skills(
                    self.db,
                    agent_id,
                    inbound_msg
                )

                if skill_result and skill_result.success:
                    self.logger.info(f"Message processed by skill, output: {skill_result.output[:100]}...")
                    skills_processed = True

                    # Store skill output in memory
                    await memory_manager.add_message(
                        agent_id=agent_id,
                        sender_key=sender_key,
                        role="assistant",
                        content=skill_result.output,
                        chat_id=f"playground_{user_id}",
                        message_id=f"msg_skill_{agent_id}_{int(datetime.utcnow().timestamp() * 1000)}",
                        metadata=skill_result.metadata
                    )

                    # Return skill result directly
                    return {
                        "status": "success",
                        "message": skill_result.output,
                        "agent_name": agent_name,
                        "tool_used": f"skill:{inbound_msg.sender}",  # Skill identifier
                        "execution_time": None,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }

            except Exception as e:
                self.logger.warning(f"Skill processing failed: {e}", exc_info=True)

            # STEP 4: If no skill handled it, process with AgentService (AI)
            # Phase 9.3: Pass tenant_id and persona_id for custom tool discovery
            # Phase 16: Check if user is in project context and pass project_id
            project_id = None
            try:
                from models import UserProjectSession, AgentProjectAccess
                # BUGFIX: Project sessions use generic sender_key format (playground_user_{id})
                # but send_message uses thread-specific format (playground_u{id}_a{id}_t{id})
                # Need to check using the generic format
                generic_sender_key = f"playground_user_{user_id}"

                # Phase 1: Comprehensive logging for diagnosis
                self.logger.info(f"[KB FIX] Session lookup parameters:")
                self.logger.info(f"  - tenant_id: {agent.tenant_id}")
                self.logger.info(f"  - sender_key: {generic_sender_key}")
                self.logger.info(f"  - agent_id: {agent_id}")
                self.logger.info(f"  - channel: playground")

                # Query all sessions for debugging
                all_sessions = self.db.query(UserProjectSession).filter(
                    UserProjectSession.sender_key == generic_sender_key,
                    UserProjectSession.channel == "playground"
                ).all()
                self.logger.info(f"[KB FIX] Found {len(all_sessions)} total sessions for this user/channel")
                for sess in all_sessions:
                    self.logger.info(f"  - Session: agent_id={sess.agent_id}, project_id={sess.project_id}, tenant_id={sess.tenant_id}")

                # Phase 2: Fixed logic - try to find session for this specific agent first
                project_session = self.db.query(UserProjectSession).filter(
                    UserProjectSession.tenant_id == agent.tenant_id,
                    UserProjectSession.sender_key == generic_sender_key,
                    UserProjectSession.agent_id == agent_id,
                    UserProjectSession.channel == "playground",
                    UserProjectSession.project_id.isnot(None)  # Only active project sessions
                ).first()

                # If not found, check if user is in a project with ANY agent (cross-agent access)
                if not project_session:
                    self.logger.info(f"[KB FIX] No session found for agent {agent_id}, checking for any project session")
                    project_session = self.db.query(UserProjectSession).filter(
                        UserProjectSession.tenant_id == agent.tenant_id,
                        UserProjectSession.sender_key == generic_sender_key,
                        UserProjectSession.channel == "playground",
                        UserProjectSession.project_id.isnot(None)
                    ).first()

                    if project_session:
                        # Verify agent has access to this project
                        access = self.db.query(AgentProjectAccess).filter(
                            AgentProjectAccess.agent_id == agent_id,
                            AgentProjectAccess.project_id == project_session.project_id
                        ).first()

                        if not access:
                            self.logger.warning(f"[KB FIX] Agent {agent_id} doesn't have access to project {project_session.project_id}")
                            project_session = None
                        else:
                            self.logger.info(f"[KB FIX] ✅ Cross-agent access granted: agent {agent_id} can access project {project_session.project_id}")

                if project_session:
                    project_id = project_session.project_id
                    self.logger.info(f"[KB FIX] ✅ User in project context: project_id={project_id}")
                else:
                    self.logger.info(f"[KB FIX] ❌ No project session found for user")
            except Exception as e:
                import traceback
                self.logger.error(f"[KB FIX] Error checking project context: {e}")
                self.logger.error(f"[KB FIX] Traceback: {traceback.format_exc()}")

            agent_service = AgentService(
                config_dict,
                contact_service=None,
                db=self.db,
                agent_id=agent_id,
                token_tracker=self.token_tracker,  # Phase 7.2: Track token usage
                tenant_id=agent.tenant_id,
                persona_id=agent.persona_id,
                project_id=project_id,  # Phase 16: Pass project context
                user_id=user_id  # Phase 16: Pass user_id for combined KB
            )

            # Process message through agent
            # Phase 8: Emit activity start event (non-blocking)
            emit_agent_processing_async(
                tenant_id=agent.tenant_id,
                agent_id=agent_id,
                status="start",
                sender_key=sender_key,
                channel="playground"
            )

            result = await agent_service.process_message(
                sender_key=sender_key,
                message_text=full_message,
                original_query=message_text
            )

            # Phase 8: Emit activity end event (non-blocking)
            emit_agent_processing_async(
                tenant_id=agent.tenant_id,
                agent_id=agent_id,
                status="end",
                sender_key=sender_key,
                channel="playground"
            )

            # STEP 5: Store agent response in memory
            # Skip storing security-blocked messages to prevent memory contamination
            # (blocked messages can influence AI to generate similar responses in detect_only mode)
            if result.get("answer") and not result.get("security_blocked"):
                # Build metadata for memory storage
                memory_metadata = {
                    "source": "playground",
                    "agent_id": agent_id
                }
                memory_content = result["answer"]  # Always store FULL content for UI display

                # Include KB usage tracking if available
                if result.get('kb_used'):
                    memory_metadata['kb_used'] = result.get('kb_used')

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

                    # Generate summary for metadata (used for AI context, not for UI display)
                    # The full content is stored for UI, but metadata includes summary for context building
                    tool_summary = summarize_tool_result(
                        result['answer'],
                        result.get('tool_used', 'unknown')
                    )
                    memory_metadata['tool_summary'] = tool_summary
                    logger.debug(f"Tool result summary stored in metadata: {tool_summary}")

                agent_message_id = f"msg_agent_{agent_id}_{int(datetime.utcnow().timestamp() * 1000)}"
                await memory_manager.add_message(
                    agent_id=agent_id,
                    sender_key=sender_key,
                    role="assistant",
                    content=memory_content,  # Store FULL content for UI display
                    chat_id=f"playground_{user_id}",
                    message_id=agent_message_id,
                    metadata=memory_metadata  # Include tool metadata and KB usage
                )

                # Phase 14.5: Index agent response in FTS5 for conversation search
                try:
                    # Look up or get thread_id for this conversation
                    from models import ConversationThread
                    thread = self.db.query(ConversationThread).filter(
                        ConversationThread.user_id == user_id,
                        ConversationThread.agent_id == agent_id,
                        ConversationThread.thread_type == "playground",
                        ConversationThread.is_archived == False,
                        ConversationThread.status == "active"
                    ).order_by(ConversationThread.id.desc()).first()

                    thread_id = thread.id if thread else None

                    # Insert into FTS5 table
                    self.db.execute(text("""
                        INSERT INTO conversation_search_fts
                        (thread_id, message_id, role, content, timestamp, tenant_id, user_id, agent_id)
                        VALUES (:thread_id, :message_id, :role, :content, :timestamp, :tenant_id, :user_id, :agent_id)
                    """), {
                        "thread_id": thread_id,
                        "message_id": agent_message_id,
                        "role": "assistant",
                        "content": result["answer"],
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "tenant_id": agent.tenant_id,
                        "user_id": user_id,
                        "agent_id": agent_id
                    })
                    self.db.commit()
                    self.logger.debug(f"Indexed agent response in FTS5 (thread_id={thread_id})")
                except Exception as e:
                    self.logger.warning(f"Failed to index agent response in FTS5: {e}")

            # STEP 6: Invoke post-response hooks (e.g., knowledge sharing)
            if result.get("answer"):
                self.logger.info(f"Invoking post-response hooks for agent {agent_id}")
                try:
                    await self._invoke_post_response_hooks(
                        agent_id=agent_id,
                        user_message=message_text,
                        agent_response=result["answer"],
                        context={
                            "sender_key": sender_key,
                            "sender_name": f"Playground User {user_id}",
                            "is_group": False,
                            "chat_id": f"playground_{user_id}"
                        },
                        ai_client=agent_service.ai_client
                    )
                    self.logger.info(f"Post-response hooks completed for agent {agent_id}")
                except Exception as e:
                    self.logger.error(f"Error in post-response hooks: {e}", exc_info=True)

            return {
                "status": "success",
                "message": result.get("answer", ""),
                "tool_used": result.get("tool_used"),
                "execution_time": result.get("execution_time"),
                "agent_name": agent_name,
                "kb_used": result.get("kb_used", []),  # KB usage tracking
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            self.logger.error(f"Error sending message to agent {agent_id}: {e}", exc_info=True)
            return {
                "error": str(e),
                "status": "error",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    async def process_message_streaming(
        self,
        user_id: int,
        agent_id: int,
        message_text: str,
        thread_id: Optional[int] = None,
        tenant_id: Optional[str] = None
    ):
        """
        Process message with streaming response (Phase 14.9).
        HIGH-011 Defense-in-depth: tenant_id validation at service layer.

        Yields streaming chunks as they arrive from LLM.
        Similar flow to send_message() but streams tokens instead of returning full response.

        Args:
            user_id: RBAC user ID
            agent_id: Agent ID to interact with
            message_text: User message content
            thread_id: Optional thread ID for proper message isolation
            tenant_id: Optional tenant ID for defense-in-depth validation

        Yields:
            {"type": "token", "content": str} - Token chunks
            {"type": "done", "message_id": int, "token_usage": dict} - Final metadata
            {"type": "error", "error": str} - Error occurred
        """
        from models import Agent, Contact, UserContactMapping
        from agent.agent_service import AgentService
        from agent.memory.multi_agent_memory import MultiAgentMemoryManager

        try:
            # FIX 2026-01-30: Thread isolation takes priority for Playground (streaming)
            # Same logic as send_message() - thread_id > contact-based > generic user key
            if thread_id:
                # Phase 14.1: Use thread-specific sender_key for thread isolation
                sender_key = f"playground_u{user_id}_a{agent_id}_t{thread_id}"
                self.logger.info(f"[STREAMING] Using thread-specific sender_key: {sender_key}")
            else:
                # Fallback for backward compatibility - check contact mapping
                user_contact_mapping = self.db.query(UserContactMapping).filter(
                    UserContactMapping.user_id == user_id
                ).first()

                if user_contact_mapping:
                    contact = self.db.query(Contact).filter(Contact.id == user_contact_mapping.contact_id).first()
                    if contact and contact.phone_number:
                        sender_key = contact.phone_number
                        self.logger.info(f"[STREAMING] Using contact-based sender_key (no thread): {sender_key}")
                    elif contact and contact.whatsapp_id:
                        sender_key = contact.whatsapp_id
                        self.logger.info(f"[STREAMING] Using contact whatsapp_id sender_key (no thread): {sender_key}")
                    else:
                        sender_key = f"playground_user_{user_id}"
                        self.logger.warning(f"[STREAMING] Contact has no phone/whatsapp, using user-based key")
                else:
                    sender_key = self.resolve_user_identity(user_id)
                    self.logger.warning(f"[STREAMING] No thread_id or contact mapping, using generic sender_key: {sender_key}")

            if not sender_key:
                yield {"type": "error", "error": "Failed to resolve user identity"}
                return

            # Get agent configuration (HIGH-011 defense-in-depth)
            query = self.db.query(Agent).filter(Agent.id == agent_id)
            if tenant_id:
                query = query.filter(Agent.tenant_id == tenant_id)
            agent = query.first()
            if not agent or not agent.is_active:
                yield {"type": "error", "error": f"Agent {agent_id} not found or inactive"}
                return

            # Check if playground channel is enabled
            import json as json_module
            enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                json_module.loads(agent.enabled_channels) if agent.enabled_channels else ["playground", "whatsapp"]
            )
            if "playground" not in enabled_channels:
                yield {"type": "error", "error": f"Agent {agent_id} does not have Playground channel enabled"}
                return

            # Get agent name from contact
            contact = self.db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent_id}"

            # =========================================================================
            # Phase 18.3: Slash Command Detection (BEFORE any AI processing)
            # This enables /shell, /invoke, /commands, etc. to work in Playground
            # =========================================================================
            if message_text.strip().startswith("/"):
                from services.slash_command_service import SlashCommandService

                slash_service = SlashCommandService(self.db)
                command_info = slash_service.detect_command(message_text.strip(), agent.tenant_id)

                if command_info:
                    self.logger.info(f"[STREAMING] Detected slash command: {command_info['command']['command_name']}")

                    # Execute the slash command
                    slash_result = await slash_service.execute_command(
                        message=message_text.strip(),
                        tenant_id=agent.tenant_id,
                        agent_id=agent_id,
                        sender_key=sender_key,
                        channel="playground",
                        user_id=user_id
                    )

                    # Get the command response message
                    cmd_response = slash_result.get("message", "Command executed.")

                    self.logger.info(f"[STREAMING] Slash command result: {slash_result.get('status')}")

                    # Stream the command response
                    chunk_size = 20
                    for i in range(0, len(cmd_response), chunk_size):
                        chunk_text = cmd_response[i:i+chunk_size]
                        yield {"type": "token", "content": chunk_text}

                    # Send done with any special action data (e.g., agent switch)
                    done_data = {
                        "type": "done",
                        "message_id": f"cmd_{datetime.utcnow().timestamp()}",
                        "thread_id": thread_id,
                        "agent_name": agent_name,
                        "slash_command": True,
                        "action": slash_result.get("action"),
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }

                    # Include action data for frontend handling (e.g., switch_agent)
                    if slash_result.get("data"):
                        done_data["data"] = slash_result.get("data")
                    if slash_result.get("agent_id"):
                        done_data["agent_id"] = slash_result.get("agent_id")

                    yield done_data
                    return  # Slash command handled, don't process with AI

            # Load user's playground settings for model configuration
            from models import PlaygroundUserSettings
            user_settings = self.db.query(PlaygroundUserSettings).filter(
                PlaygroundUserSettings.user_id == user_id,
                PlaygroundUserSettings.tenant_id == agent.tenant_id
            ).first()

            temperature = None
            max_tokens = None
            model_override = None
            if user_settings and user_settings.settings_json:
                model_settings = user_settings.settings_json.get("modelSettings", {})
                agent_settings = model_settings.get(str(agent_id), {})
                temperature = agent_settings.get("temperature")
                max_tokens = agent_settings.get("maxTokens")
                model_override = agent_settings.get("modelOverride")

            # Determine which model to use
            effective_model = model_override if model_override else agent.model_name

            # Build agent configuration dictionary
            config_dict = {
                "agent_id": agent.id,
                "agent_name": agent_name,
                "model_provider": agent.model_provider,
                "model_name": effective_model,
                "system_prompt": agent.system_prompt,
                "memory_size": agent.memory_size or 1000,
                "enabled_tools": [],
                "response_template": agent.response_template,
                "enable_semantic_search": agent.enable_semantic_search,
                "context_message_count": agent.context_message_count or 10,
                "memory_isolation_mode": agent.memory_isolation_mode or "isolated",
                "temperature": temperature,
                "max_tokens": max_tokens,
                "semantic_search_results": agent.semantic_search_results or 10,
                "semantic_similarity_threshold": agent.semantic_similarity_threshold or 0.5,
            }

            # Initialize memory manager
            memory_manager = MultiAgentMemoryManager(self.db, config_dict)

            # STEP 1: Add user message to memory FIRST
            message_id = f"msg_user_{user_id}_{int(datetime.utcnow().timestamp() * 1000)}"
            await memory_manager.add_message(
                agent_id=agent_id,
                sender_key=sender_key,
                role="user",
                content=message_text,
                chat_id=f"playground_{user_id}",
                message_id=message_id,
                metadata={
                    "source": "playground",
                    "agent_id": agent_id,
                    "user_id": user_id
                }
            )

            # Index in FTS5
            try:
                self.db.execute(text("""
                    INSERT INTO conversation_search_fts
                    (thread_id, message_id, role, content, timestamp, tenant_id, user_id, agent_id)
                    VALUES (:thread_id, :message_id, :role, :content, :timestamp, :tenant_id, :user_id, :agent_id)
                """), {
                    "thread_id": thread_id,
                    "message_id": message_id,
                    "role": "user",
                    "content": message_text,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "tenant_id": agent.tenant_id,
                    "user_id": user_id,
                    "agent_id": agent_id
                })
                self.db.commit()
            except Exception as e:
                self.logger.warning(f"Failed to index user message in FTS5: {e}")

            # STEP 2: Get memory context
            memory_context = await memory_manager.get_context(
                agent_id=agent_id,
                sender_key=sender_key,
                current_message=message_text,
                max_semantic_results=config_dict.get("semantic_search_results", 5),
                similarity_threshold=config_dict.get("semantic_similarity_threshold", 0.3),
                include_knowledge=True,
                include_shared=True,
                chat_id=f"playground_{user_id}",
                use_contact_mapping=True
            )

            # Build full message with context
            full_message = message_text
            if config_dict.get("enable_semantic_search", False) and memory_context:
                agent_memory = memory_manager.get_agent_memory(agent_id)
                context_str = agent_memory.format_context_for_prompt(memory_context, user_id=sender_key)
                if context_str and context_str != "[No previous context]":
                    full_message = f"{context_str}\n\n[Current message from Playground]: {message_text}"
                else:
                    full_message = f"[Message from Playground]: {message_text}"

            # Layer 5: Tool output context
            tool_buffer = get_tool_output_buffer()
            tool_buffer.increment_message_count(agent_id, sender_key)
            tool_context = tool_buffer.get_context_for_injection(agent_id, sender_key, message_text)
            if tool_context:
                full_message = f"{tool_context}\n\n{full_message}"

            # STEP 3: Try to process with skills FIRST (before AI)
            # Phase 8: Emit activity start event for streaming
            emit_agent_processing_async(
                tenant_id=agent.tenant_id,
                agent_id=agent_id,
                status="start",
                sender_key=sender_key,
                channel="playground"
            )

            from agent.skills.skill_manager import get_skill_manager
            from agent.skills.base import InboundMessage
            skill_manager = get_skill_manager()

            inbound_msg = InboundMessage(
                id=message_id,
                sender=sender_key,
                sender_key=sender_key,
                body=message_text,
                chat_id=f"playground_{user_id}",
                chat_name=None,
                is_group=False,
                timestamp=datetime.utcnow(),
                media_type=None,
                media_url=None,
                media_path=None,
                channel="playground"  # Skills-as-Tools: playground streaming
            )

            try:
                skill_result = await skill_manager.process_message_with_skills(
                    self.db,
                    agent_id,
                    inbound_msg
                )

                if skill_result and skill_result.success:
                    self.logger.info(f"[STREAMING] Message processed by skill: {skill_result.output[:100]}...")

                    # Stream the skill response
                    skill_output = skill_result.output
                    for char in skill_output:
                        yield {"type": "token", "content": char}

                    # Store skill output in memory
                    await memory_manager.add_message(
                        agent_id=agent_id,
                        sender_key=sender_key,
                        role="assistant",
                        content=skill_output,
                        chat_id=f"playground_{user_id}",
                        message_id=f"msg_skill_{agent_id}_{int(datetime.utcnow().timestamp() * 1000)}",
                        metadata=skill_result.metadata
                    )

                    # Index in FTS5
                    try:
                        self.db.execute(text("""
                            INSERT INTO conversation_search_fts
                            (thread_id, message_id, role, content, timestamp, tenant_id, user_id, agent_id)
                            VALUES (:thread_id, :message_id, :role, :content, :timestamp, :tenant_id, :user_id, :agent_id)
                        """), {
                            "thread_id": thread_id,
                            "message_id": f"msg_skill_{agent_id}",
                            "role": "assistant",
                            "content": skill_output,
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "tenant_id": agent.tenant_id,
                            "user_id": user_id,
                            "agent_id": agent_id
                        })
                        self.db.commit()
                    except Exception as e:
                        self.logger.warning(f"Failed to index skill response in FTS5: {e}")

                    # Phase 8: Emit activity end event (skill-only path)
                    emit_agent_processing_async(
                        tenant_id=agent.tenant_id,
                        agent_id=agent_id,
                        status="end",
                        sender_key=sender_key,
                        channel="playground"
                    )

                    # Return done
                    yield {
                        "type": "done",
                        "message_id": message_id,
                        "thread_id": thread_id,
                        "timestamp": datetime.utcnow().isoformat() + "Z"
                    }
                    return  # Skill handled it, don't process with AI

            except Exception as e:
                self.logger.warning(f"Skill processing failed in streaming: {e}", exc_info=True)

            # STEP 4: If no skill handled it, create agent service and process with AI
            # BUG FIX 2026-01-29: Use the non-streaming send_message() to get proper
            # custom tool prompts, model identity guard, and all other enhancements.
            # The streaming path was bypassing agent_service.process_message() which
            # contains all the critical system prompt enhancements.

            self.logger.info(f"[STREAMING] Processing message for agent {agent_id} with proper system prompt enhancements")

            # Use the regular send_message which goes through proper AgentService.process_message()
            response = await self.send_message(
                user_id=user_id,
                agent_id=agent_id,
                message_text=message_text,
                thread_id=thread_id,
                skip_user_message=True  # Already added user message above
            )

            if response.get("status") == "error":
                yield {"type": "error", "error": response.get("error", "Unknown error")}
                return

            # Simulate streaming by yielding the response in chunks
            # This maintains the WebSocket streaming protocol while using the properly enhanced agent
            full_response = response.get("message", "")
            accumulated_response = ""
            token_usage = None

            # Stream the response character-by-character (or in small chunks for performance)
            chunk_size = 20  # Characters per chunk for natural streaming feel
            for i in range(0, len(full_response), chunk_size):
                chunk_text = full_response[i:i+chunk_size]
                accumulated_response += chunk_text
                yield {"type": "token", "content": chunk_text}

            # STEP 5: Send completion metadata (send_message already stored in memory and FTS5)
            yield {
                "type": "done",
                "message_id": response.get("message_id"),
                "thread_id": thread_id,
                "token_usage": response.get("token_usage"),
                "agent_name": agent_name,
                "tool_used": response.get("tool_used"),
                "kb_used": response.get("kb_used", []),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

        except Exception as e:
            self.logger.error(f"Error in streaming message: {e}", exc_info=True)
            # Phase 8: Emit activity end event on error (if agent was loaded)
            if 'agent' in locals():
                emit_agent_processing_async(
                    tenant_id=agent.tenant_id,
                    agent_id=agent_id,
                    status="end",
                    sender_key=sender_key if 'sender_key' in locals() else None,
                    channel="playground"
                )
            yield {"type": "error", "error": str(e)}

    async def _invoke_post_response_hooks(
        self,
        agent_id: int,
        user_message: str,
        agent_response: str,
        context: Dict,
        ai_client
    ):
        """
        Invoke post_response_hook for skills that support it.

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
            from agent.skills.skill_manager import SkillManager

            skill_manager = SkillManager()

            # Get enabled skills for this agent
            agent_skills = await skill_manager.get_agent_skills(self.db, agent_id)

            for skill_record in agent_skills:
                skill_type = skill_record.skill_type

                # Check if skill has post_response_hook
                if skill_type not in skill_manager.registry:
                    continue

                skill_class = skill_manager.registry[skill_type]

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

            # BUG-002 Fix: Also extract facts for project context
            await self._extract_project_facts(
                agent_id=agent_id,
                sender_key=context.get("sender_key"),
                user_message=user_message,
                agent_response=agent_response
            )

        except Exception as e:
            self.logger.error(f"Error invoking post_response_hooks: {e}", exc_info=True)

    async def _extract_project_facts(
        self,
        agent_id: int,
        sender_key: str,
        user_message: str,
        agent_response: str
    ):
        """
        BUG-002 Fix: Extract and store facts when user is in a project context.

        Checks if user is in an active project session and extracts facts
        to the project_fact_memory table instead of agent-level facts.

        Args:
            agent_id: Agent ID
            sender_key: User's sender key
            user_message: User's message text
            agent_response: Agent's response text
        """
        from models import UserProjectSession, Project, Agent
        from services.project_memory_service import ProjectMemoryService
        from agent.memory.fact_extractor import FactExtractor

        try:
            # Get agent to find tenant_id
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return

            # Check if user is in a project session (playground channel)
            session = self.db.query(UserProjectSession).filter(
                UserProjectSession.tenant_id == agent.tenant_id,
                UserProjectSession.sender_key == sender_key,
                UserProjectSession.agent_id == agent_id,
                UserProjectSession.channel == "playground"
            ).first()

            if not session or not session.project_id:
                self.logger.debug(f"User {sender_key} not in project context, skipping project fact extraction")
                return

            # Get project and check if factual memory is enabled
            project = self.db.query(Project).filter(Project.id == session.project_id).first()
            if not project or not project.enable_factual_memory:
                self.logger.debug(f"Project {session.project_id} has factual memory disabled")
                return

            self.logger.info(f"Extracting facts for project {project.name} (ID: {project.id})")

            # Build conversation for fact extraction
            conversation = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": agent_response}
            ]

            # Check if we should extract facts
            # Use agent's provider/model for fact extraction instead of hardcoded Gemini
            fact_extractor = FactExtractor(
                provider=agent.model_provider,
                model_name=agent.model_name,
                db=self.db
            )
            if not fact_extractor.should_extract_facts(conversation, min_user_messages=1):
                return

            # Extract facts using AI
            facts = await fact_extractor.extract_facts(
                conversation=conversation,
                user_id=sender_key,
                agent_id=agent_id
            )

            if not facts:
                self.logger.debug("No facts extracted from conversation")
                return

            # Store facts to project_fact_memory via ProjectMemoryService
            memory_service = ProjectMemoryService(self.db)
            stored_count = 0

            for fact in facts:
                result = await memory_service.add_fact(
                    project_id=project.id,
                    topic=fact.get("topic", "general"),
                    key=fact.get("key", "unknown"),
                    value=fact.get("value", ""),
                    sender_key=sender_key,
                    confidence=fact.get("confidence", 0.8),
                    source="conversation"
                )

                if result.get("status") == "success":
                    stored_count += 1

            if stored_count > 0:
                self.logger.info(f"Stored {stored_count} facts to project {project.name}")

        except Exception as e:
            self.logger.error(f"Error extracting project facts: {e}", exc_info=True)

    async def get_conversation_history(
        self,
        user_id: int,
        agent_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get conversation history between user and agent.

        Args:
            user_id: RBAC user ID
            agent_id: Agent ID
            limit: Maximum number of messages to return

        Returns:
            List of messages with role, content, timestamp
        """
        from agent.memory.multi_agent_memory import MultiAgentMemoryManager

        try:
            # Resolve user identity
            sender_key = self.resolve_user_identity(user_id)
            if not sender_key:
                return []

            # Build a minimal config for memory manager
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return []

            config_dict = {
                "memory_size": agent.memory_size or 1000,
                "enable_semantic_search": agent.enable_semantic_search,
                "semantic_search_results": agent.semantic_search_results or 10,
                "semantic_similarity_threshold": agent.semantic_similarity_threshold or 0.5,
            }

            # Initialize memory manager
            memory_manager = MultiAgentMemoryManager(self.db, config_dict)

            # Get conversation context (working memory contains the message history)
            context = await memory_manager.get_context(
                agent_id=agent_id,
                sender_key=sender_key,
                current_message="",
                chat_id=f"playground_{user_id}",
                include_knowledge=False,  # Don't need facts for history display
                include_shared=False  # Don't need shared memory for history display
            )

            # Use working_memory key (Layer 1 - recent messages)
            if not context or not context.get("working_memory"):
                return []

            # Format messages for frontend
            messages = []
            for msg in context["working_memory"][-limit:]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"],
                    "timestamp": msg.get("timestamp", datetime.utcnow().isoformat() + "Z"),
                    "message_id": msg.get("message_id"),
                    "is_bookmarked": msg.get("is_bookmarked", False),
                    "is_edited": msg.get("is_edited", False),
                    "edited_at": msg.get("edited_at"),
                    "bookmarked_at": msg.get("bookmarked_at"),
                    "original_content": msg.get("original_content")
                })

            return messages

        except Exception as e:
            self.logger.error(f"Error getting conversation history: {e}", exc_info=True)
            return []

    async def clear_conversation_history(
        self,
        user_id: int,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Clear conversation history between user and agent.

        Args:
            user_id: RBAC user ID
            agent_id: Agent ID

        Returns:
            Success status
        """
        from agent.memory.multi_agent_memory import MultiAgentMemoryManager

        try:
            # Resolve user identity
            sender_key = self.resolve_user_identity(user_id)
            if not sender_key:
                return {"success": False, "error": "Failed to resolve user identity"}

            # Build a minimal config for memory manager
            from models import Agent
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                return {"success": False, "error": "Agent not found"}

            config_dict = {
                "memory_size": agent.memory_size or 1000,
                "enable_semantic_search": agent.enable_semantic_search,
            }

            # Initialize memory manager
            memory_manager = MultiAgentMemoryManager(self.db, config_dict)

            # Clear memory for this conversation
            memory_manager.clear_agent_memory(
                agent_id=agent_id,
                sender_key=sender_key
            )
            success = True

            return {
                "success": success,
                "message": "Conversation history cleared" if success else "Failed to clear history"
            }

        except Exception as e:
            self.logger.error(f"Error clearing conversation history: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def process_audio(
        self,
        user_id: int,
        agent_id: int,
        audio_data: bytes,
        audio_format: str = "webm",
        tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process audio message: transcribe and send to agent.

        Phase 14.0: Audio Messages on Playground UI
        HIGH-011 Defense-in-depth: tenant_id validation at service layer.

        Flow:
        1. Save audio to temp file
        2. Check if agent has audio_transcript skill enabled
        3. Transcribe using Whisper API
        4. Send transcribed text to agent
        5. Return response (with optional TTS audio if agent has audio_tts skill)

        Args:
            user_id: RBAC user ID
            agent_id: Agent ID
            audio_data: Audio file bytes
            audio_format: Audio format (webm, ogg, mp3, wav, etc.)
            tenant_id: Optional tenant ID for defense-in-depth validation

        Returns:
            Dict with transcript, response, and optional audio_url
        """
        import os
        import uuid
        import tempfile
        from models import Agent, AgentSkill
        from agent.skills.audio_transcript import AudioTranscriptSkill
        from agent.skills.base import InboundMessage

        try:
            # Resolve user identity
            sender_key = self.resolve_user_identity(user_id)
            if not sender_key:
                return {
                    "status": "error",
                    "error": "Failed to resolve user identity"
                }

            # Get agent and check if it exists and is active (HIGH-011 defense-in-depth)
            query = self.db.query(Agent).filter(Agent.id == agent_id)
            if tenant_id:
                query = query.filter(Agent.tenant_id == tenant_id)
            agent = query.first()
            if not agent or not agent.is_active:
                return {
                    "status": "error",
                    "error": f"Agent {agent_id} not found or inactive"
                }

            # Check if agent has audio_transcript skill enabled
            audio_skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "audio_transcript",
                AgentSkill.is_enabled == True
            ).first()

            if not audio_skill:
                return {
                    "status": "error",
                    "error": "This agent does not have audio transcription enabled"
                }

            # Save audio to temp file
            temp_dir = os.path.join(tempfile.gettempdir(), "tsushin_audio")
            os.makedirs(temp_dir, exist_ok=True)

            audio_id = str(uuid.uuid4())
            audio_filename = f"{audio_id}.{audio_format}"
            audio_path = os.path.join(temp_dir, audio_filename)

            with open(audio_path, "wb") as f:
                f.write(audio_data)

            self.logger.info(f"Saved audio to {audio_path} ({len(audio_data)} bytes)")

            # Create InboundMessage for skill processing
            inbound_msg = InboundMessage(
                id=f"playground_audio_{user_id}_{datetime.utcnow().timestamp()}",
                sender=f"playground_user_{user_id}",
                sender_key=sender_key,
                body="",  # Will be filled with transcript
                chat_id=f"playground_{user_id}",
                chat_name="Playground",
                is_group=False,
                timestamp=datetime.utcnow(),
                media_type=f"audio/{audio_format}",
                media_url=None,
                media_path=audio_path,
                channel="playground"  # Skills-as-Tools: audio transcription in playground
            )

            # Initialize and run transcription skill
            skill_instance = AudioTranscriptSkill()
            skill_config = audio_skill.config or {}
            skill_config['agent_id'] = agent_id

            transcript_result = await skill_instance.process(inbound_msg, skill_config)

            if not transcript_result.success:
                # Clean up temp file
                try:
                    os.remove(audio_path)
                except:
                    pass
                return {
                    "status": "error",
                    "error": transcript_result.output or "Transcription failed"
                }

            # Get transcript text
            transcript = transcript_result.processed_content or ""
            if not transcript and transcript_result.output:
                # Extract transcript from output if processed_content is empty
                transcript = transcript_result.output.replace("📝 Transcript:\n\n", "").replace("🎤 Audio transcribed:\n\n", "")

            if not transcript:
                # Clean up temp file
                try:
                    os.remove(audio_path)
                except:
                    pass
                return {
                    "status": "error",
                    "error": "Transcription returned empty text"
                }

            self.logger.info(f"Transcript: {transcript[:100]}...")

            # Clean up temp audio file
            try:
                os.remove(audio_path)
            except:
                pass

            # Check response mode
            response_mode = skill_config.get("response_mode", "conversational")

            if response_mode == "transcript_only":
                # Return only the transcript, don't send to agent
                return {
                    "status": "success",
                    "transcript": transcript,
                    "message": f"📝 {transcript}",
                    "response_mode": "transcript_only",
                    "timestamp": datetime.utcnow().isoformat() + "Z"
                }

            # Send transcribed text to agent for response
            response = await self.send_message(
                user_id=user_id,
                agent_id=agent_id,
                message_text=transcript
            )

            # Check if agent has TTS skill for audio response
            tts_skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "audio_tts",
                AgentSkill.is_enabled == True
            ).first()

            result = {
                "status": response.get("status", "success"),
                "transcript": transcript,
                "message": response.get("message", ""),
                "response_mode": "conversational",
                "timestamp": response.get("timestamp", datetime.utcnow().isoformat() + "Z")
            }

            # If TTS is enabled, generate audio response
            if tts_skill and response.get("message"):
                try:
                    audio_response = await self._generate_tts_response(
                        agent_id=agent_id,
                        text=response.get("message", ""),
                        tts_config=tts_skill.config or {}
                    )
                    if audio_response:
                        result["audio_url"] = audio_response.get("audio_url")
                        result["audio_duration"] = audio_response.get("duration")
                except Exception as e:
                    self.logger.warning(f"TTS generation failed: {e}")

            return result

        except Exception as e:
            self.logger.error(f"Error processing audio: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

    async def _generate_tts_response(
        self,
        agent_id: int,
        text: str,
        tts_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Generate TTS audio from text response.

        Phase 14.1: TTS Audio Responses

        Args:
            agent_id: Agent ID
            text: Text to convert to audio
            tts_config: TTS skill configuration

        Returns:
            Dict with audio_url and duration, or None if failed
        """
        import os
        import uuid
        from agent.skills.audio_tts_skill import AudioTTSSkill

        try:
            skill_instance = AudioTTSSkill()

            result = await skill_instance.process_response(
                response_text=text,
                config=tts_config,
                agent_id=agent_id
            )

            if result.success and result.metadata:
                audio_path = result.metadata.get("audio_path")
                if audio_path and os.path.exists(audio_path):
                    # Generate audio ID for serving
                    audio_id = str(uuid.uuid4())

                    # Store audio path mapping (in-memory for now, could use Redis/DB)
                    if not hasattr(self, '_audio_cache'):
                        self._audio_cache = {}
                    self._audio_cache[audio_id] = audio_path

                    return {
                        "audio_url": f"/api/playground/audio/{audio_id}",
                        "duration": result.metadata.get("duration", 0),
                        "audio_id": audio_id
                    }

            return None

        except Exception as e:
            self.logger.error(f"TTS generation error: {e}", exc_info=True)
            return None

    def get_audio_path(self, audio_id: str) -> Optional[str]:
        """
        Get audio file path by ID.

        Args:
            audio_id: Audio file ID

        Returns:
            File path or None if not found
        """
        if not hasattr(self, '_audio_cache'):
            self._audio_cache = {}
        return self._audio_cache.get(audio_id)

    async def check_agent_audio_capabilities(self, agent_id: int) -> Dict[str, Any]:
        """
        Check what audio capabilities an agent has.

        Phase 14.0: Used by frontend to determine if mic button should be enabled.

        Args:
            agent_id: Agent ID to check

        Returns:
            Dict with has_transcript, has_tts, transcript_mode
        """
        from models import AgentSkill

        try:
            # Check for audio_transcript skill
            transcript_skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "audio_transcript",
                AgentSkill.is_enabled == True
            ).first()

            # Check for audio_tts skill
            tts_skill = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == "audio_tts",
                AgentSkill.is_enabled == True
            ).first()

            result = {
                "has_transcript": transcript_skill is not None,
                "has_tts": tts_skill is not None,
                "transcript_mode": "conversational"
            }

            if transcript_skill and transcript_skill.config:
                result["transcript_mode"] = transcript_skill.config.get("response_mode", "conversational")

            return result

        except Exception as e:
            self.logger.error(f"Error checking audio capabilities: {e}")
            return {
                "has_transcript": False,
                "has_tts": False,
                "transcript_mode": "conversational"
            }
