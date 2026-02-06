import logging
import time
import re
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from .ai_client import AIClient
# Phase 4.8: Ring buffer memory (SenderMemory) deprecated
# Memory now managed by Multi-Agent Memory Manager in router

# Legacy tools removed - migrated to Skills system:
# - SearchTool → SearchSkill (web_search) with SearchProviderRegistry
# - WeatherTool → WeatherSkill
# - WebScrapingSkill → WebScrapingSkill
# - FlightSearchTool → FlightSearchSkill with FlightProviderRegistry

from .tools.sandboxed_tool_wrapper import SandboxedToolWrapper
from .knowledge.knowledge_service import KnowledgeService
from .skills import get_skill_manager
# Phase 8: Watcher Activity Events
from services.watcher_activity_service import emit_kb_used_async

class AgentService:
    """Agent service that processes messages with AI and memory"""

    def __init__(
        self,
        config: Dict,
        contact_service=None,
        db: Optional[Session] = None,
        agent_id: Optional[int] = None,
        token_tracker=None,
        tenant_id: Optional[str] = None,
        persona_id: Optional[int] = None,
        on_tool_complete_callback=None,
        project_id: Optional[int] = None,
        user_id: Optional[int] = None
    ):
        """
        Initialize Agent Service.

        Args:
            config: Agent configuration dict
            contact_service: Contact service for managing contacts (Phase 4.2)
            db: Database session for loading API keys (Phase 4.6)
            agent_id: Agent ID for knowledge base lookup (Phase 5.0)
            token_tracker: TokenTracker instance for usage tracking (Phase 7.2)
            tenant_id: Tenant ID for container-based tool execution
            persona_id: Persona ID for persona-based custom tool discovery (Phase 9.3)
            on_tool_complete_callback: Async callback(recipient, message) for long-running tool notifications
            project_id: Project ID if in project context (Phase 16)
            user_id: User ID for combined KB (Phase 16)

        Note: Ring buffer memory deprecated - use Multi-Agent Memory Manager instead
        Note: Legacy tools (search, weather, scraping) migrated to Skills system
        """
        self.config = config
        self.contact_service = contact_service  # Phase 4.2
        self.db = db  # Phase 4.6
        self.agent_id = agent_id  # Phase 5.0
        self.token_tracker = token_tracker  # Phase 7.2
        self.tenant_id = tenant_id
        self.persona_id = persona_id  # Phase 9.3
        self.on_tool_complete_callback = on_tool_complete_callback
        self.project_id = project_id  # Phase 16: Project context
        self.user_id = user_id  # Phase 16: User context for combined KB
        self.logger = logging.getLogger(__name__)

        # Phase 5.0: Initialize knowledge service if agent_id and db provided
        self.knowledge_service = None
        if db and agent_id:
            self.knowledge_service = KnowledgeService(db)

        # Phase 16: Initialize combined knowledge service if in project context
        self.combined_knowledge_service = None
        self.logger.info(f"[KB FIX] AgentService init: project_id={project_id}, user_id={user_id}, tenant_id={tenant_id}, agent_id={agent_id}")

        if db and project_id:
            from services.combined_knowledge_service import CombinedKnowledgeService
            self.combined_knowledge_service = CombinedKnowledgeService(db)
            self.logger.info(f"[KB FIX] ✅ CombinedKnowledgeService INITIALIZED for project {project_id}")
        else:
            self.logger.warning(f"[KB FIX] ❌ CombinedKnowledgeService NOT initialized: db={db is not None}, project_id={project_id}")

        # Phase 6.1: Initialize sandboxed tools wrapper if db provided
        # Phase: Custom Tools Hub - Added tenant_id and callback for container/long-running support
        # Phase 9.3: Added persona_id for persona-based tool discovery
        # Skills-as-Tools Phase 6: Renamed from CustomToolWrapper to SandboxedToolWrapper
        # Gate on sandboxed_tools skill being enabled for this agent
        self.sandboxed_tools = None
        if db and agent_id:
            from models import AgentSkill
            sandboxed_tools_skill = db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.skill_type == 'sandboxed_tools',
                AgentSkill.is_enabled == True
            ).first()
            if sandboxed_tools_skill:
                self.sandboxed_tools = SandboxedToolWrapper(
                    db,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    persona_id=persona_id,
                    on_complete_callback=on_tool_complete_callback
                )
                self.logger.info(f"SandboxedToolWrapper initialized: agent_id={agent_id}, tenant_id={tenant_id}, persona_id={persona_id}")
            else:
                self.logger.info(f"Sandboxed tools skill not enabled for agent {agent_id}, skipping SandboxedToolWrapper")

        # Initialize AI client (Phase 4.6: with database session for API key loading)
        # Phase 7.2: Pass token_tracker for usage tracking
        # BUG-013 Fix: Pass temperature and max_tokens from config (playground settings)
        # Pass tenant_id for tenant-specific API key loading
        self.ai_client = AIClient(
            provider=config.get("model_provider", "gemini"),
            model_name=config.get("model_name", "gemini-2.5-pro"),
            db=db,
            token_tracker=token_tracker,
            temperature=config.get("temperature"),
            max_tokens=config.get("max_tokens"),
            tenant_id=tenant_id
        )

        # Legacy tools removed - now handled by Skills system:
        # - web_search skill (SearchSkill with Brave provider)
        # - weather skill (WeatherSkill)
        # - web_scraping skill (WebScrapingSkill)
        # Skills are processed by SkillManager in router.py before reaching AgentService

    def _build_skill_tools_prompt(self, skill_tools: list) -> str:
        """
        Build system prompt section for non-shell skill tools (Phase 4).

        Creates tool documentation for skills like manage_flows, manage_reminders, etc.
        These tools use the [TOOL_CALL] format for invocation.

        Args:
            skill_tools: List of tool definitions in OpenAI format

        Returns:
            Formatted prompt string with tool documentation
        """
        if not skill_tools:
            return ""

        # Filter out shell tool (already handled separately)
        non_shell_tools = [
            t for t in skill_tools
            if t.get('function', {}).get('name') not in ('run_shell_command', 'shell')
        ]

        if not non_shell_tools:
            return ""

        prompt_parts = ["\n## Additional Skill Tools\n"]
        prompt_parts.append("You have access to the following additional tools:\n")

        for tool in non_shell_tools:
            func = tool.get('function', {})
            name = func.get('name', 'unknown')
            desc = func.get('description', 'No description')
            params = func.get('parameters', {})
            properties = params.get('properties', {})
            required = params.get('required', [])

            prompt_parts.append(f"\n### {name}")
            prompt_parts.append(f"{desc}\n")

            if properties:
                prompt_parts.append("**Parameters:**")
                for param_name, param_info in properties.items():
                    param_type = param_info.get('type', 'string')
                    param_desc = param_info.get('description', '')
                    req_marker = " (required)" if param_name in required else ""
                    enum_vals = param_info.get('enum', [])
                    enum_str = f" [values: {', '.join(enum_vals)}]" if enum_vals else ""
                    prompt_parts.append(f"- `{param_name}` ({param_type}{req_marker}){enum_str}: {param_desc}")

            # Add example usage
            prompt_parts.append(f"\n**Usage format:**")
            prompt_parts.append("```")
            prompt_parts.append("[TOOL_CALL]")
            prompt_parts.append(f"tool_name: {name}")
            prompt_parts.append(f"command_name: {name}")
            prompt_parts.append("parameters:")
            for param_name in required:
                prompt_parts.append(f"  {param_name}: <value>")
            prompt_parts.append("[/TOOL_CALL]")
            prompt_parts.append("```\n")

        prompt_parts.append("\n**IMPORTANT:** When using these tools, output the [TOOL_CALL] block immediately. Do NOT just describe what you will do - execute the tool!")

        return "\n".join(prompt_parts)

    def _strip_reasoning_tags(self, text: str) -> str:
        """
        Strip reasoning/thinking tags and internal information from AI response.

        CRITICAL FIX 2026-01-08: Enhanced to prevent information leakage of:
        - Reasoning/thinking processes
        - Tool descriptions and commands
        - Internal objectives and system information
        - Extended context that should remain internal

        Some reasoning models (like DeepSeek R1) output their thinking process
        in various tag formats. This should be removed before sending to users.

        Args:
            text: Raw AI response potentially containing thinking tags and internal info

        Returns:
            Cleaned text with all internal information removed
        """
        if not text:
            return text

        # Remove reasoning blocks in various formats
        # Format 1: <think>...</think> (DeepSeek R1)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)

        # Format 2: <reasoning>...</reasoning>
        cleaned = re.sub(r'<reasoning>.*?</reasoning>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)

        # Format 3: [REASONING]...[/REASONING] or [INTERNAL]...[/INTERNAL]
        cleaned = re.sub(r'\[(?:REASONING|INTERNAL|THINKING)\].*?\[/(?:REASONING|INTERNAL|THINKING)\]', '', cleaned, flags=re.DOTALL | re.IGNORECASE)

        # Format 4: Markdown headings for thinking/reasoning
        # Remove lines starting with ## Thinking:, **Reasoning:**, etc.
        cleaned = re.sub(r'^[#*\s]*(?:Thinking|Reasoning|Internal|Objective|Tools Available|My Plan):.*?(?=\n\n|\n[#*]|$)', '', cleaned, flags=re.MULTILINE | re.DOTALL | re.IGNORECASE)

        # Remove orphaned tags
        cleaned = re.sub(r'</(?:think|reasoning|thinking)>', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'<(?:think|reasoning|thinking)>', '', cleaned, flags=re.IGNORECASE)

        # SECURITY FIX: Remove tool call blocks that leaked (should have been processed)
        # These look like: ```tool:toolname\ncommand:...\nparam:...```
        cleaned = re.sub(r'```tool:.*?```', '', cleaned, flags=re.DOTALL)

        # Clean up extra whitespace and multiple newlines
        cleaned = re.sub(r'\n\n\n+', '\n\n', cleaned)
        cleaned = cleaned.strip()

        return cleaned

    def _strip_internal_context(self, text: str) -> str:
        """
        Strip internal context markers that should never be shown to users.

        SECURITY FIX 2026-01-11: Prevent leakage of internal memory context markers.

        Some LLMs (especially lighter models) may echo back the input prompt context
        including internal markers like [PAST - XX%], === What I Know About This User ===,
        learned facts, shared knowledge, etc. This is a serious privacy violation.

        Args:
            text: AI response potentially containing internal context markers

        Returns:
            Cleaned text with internal context markers removed
        """
        if not text:
            return text

        original_text = text

        # Pattern 1: Remove [PAST - XX%] relevance score lines
        # Example: [PAST - 100%] voce que me chamou
        text = re.sub(r'\[PAST - \d+%\].*?(?=\n|$)', '', text, flags=re.MULTILINE)

        # Pattern 2: Remove section headers
        text = re.sub(r'=== Relevant Past Messages ===', '', text, flags=re.IGNORECASE)
        text = re.sub(r'=== What I Know About This User ===', '', text, flags=re.IGNORECASE)
        text = re.sub(r'=== Shared Knowledge.*?===', '', text, flags=re.IGNORECASE | re.DOTALL)

        # Pattern 3: Remove fact category headers
        text = re.sub(r'\[COMMUNICATION_STYLE\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[INSTRUCTIONS\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[LINGUISTIC_PATTERNS\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PERSONAL_INFO\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PREFERENCES\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[FACTUAL_INFORMATION\]', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\[PERSONAL_INFORMATION\]', '', text, flags=re.IGNORECASE)

        # Pattern 4: Remove fact entries with confidence scores
        # Example: - favorite_color: PURPLE (confidence: 95%)
        text = re.sub(r'^\s*-\s+\w+:\s+.+?\(confidence:\s+\d+%\)\s*$', '', text, flags=re.MULTILINE)

        # Pattern 5: Remove [Current message from X]: prefix
        text = re.sub(r'\[Current message from .+?\]:\s*', '', text, flags=re.IGNORECASE)

        # Pattern 6: Remove lines that look like shared knowledge entries
        # Example: [FACTUAL_INFORMATION - Agent 1] The agent is available to help the user.
        text = re.sub(r'^\s*\[\w+ - Agent \d+\].*?(?=\n|$)', '', text, flags=re.MULTILINE)

        # Clean up excessive whitespace and newlines
        text = re.sub(r'\n\n\n+', '\n\n', text)
        text = text.strip()

        # Log warning if internal context was detected and stripped
        if text != original_text:
            self.logger.warning(f"🚨 SECURITY: Stripped internal context markers from AI response (model: {self.config.get('model_name', 'unknown')})")
            self.logger.debug(f"Original length: {len(original_text)}, Cleaned length: {len(text)}")

        return text

    def _filter_sensitive_content(self, text: str) -> str:
        """
        Filter out sensitive/internal information that should never be exposed to users.

        SECURITY FIX 2026-01-08: Prevent leakage of system internals to external contacts.
        SECURITY FIX 2026-01-11: Enhanced with internal context pattern detection.

        This is a safety net in case reasoning stripping misses something or
        the AI hallucinates internal system details.

        Args:
            text: AI response text

        Returns:
            Filtered text with sensitive content warnings replaced
        """
        if not text:
            return text

        # List of sensitive keywords that indicate information leakage
        sensitive_patterns = [
            r'\btool:\s*\w+',  # Tool call syntax
            r'\bcommand:\s*\w+',  # Command syntax
            r'\bobjective:\s*',  # Internal objectives
            r'\bsystem_prompt',  # System prompt references
            r'\benabled_tools',  # Tool configuration
            r'\bskill_type:\s*',  # Skill types
            r'\bdb\.query\(',  # Database queries
            r'\bself\.\w+\(',  # Python self references
            r'\bbackend/',  # File paths
            r'\bmodel_provider',  # Model configuration
            r'\bagent_id:\s*\d+',  # Agent IDs
            r'\bcontext_data:',  # Internal context
            # SECURITY FIX 2026-01-11: Internal context leak patterns (fallback protection)
            r'\[PAST - \d+%\]',  # Memory relevance scores
            r'=== What I Know About',  # User facts section header
            r'=== Shared Knowledge',  # Shared memory section header
            r'\[COMMUNICATION_STYLE\]',  # Fact category headers
            r'\[INSTRUCTIONS\]',
            r'\[LINGUISTIC_PATTERNS\]',
            r'\[PERSONAL_INFO\]',
            r'\[PREFERENCES\]',
            r'confidence: \d+%',  # Confidence scores in facts
        ]

        # Check if text contains sensitive patterns
        text_lower = text.lower()
        for pattern in sensitive_patterns:
            if re.search(pattern, text_lower, re.IGNORECASE):
                self.logger.warning(f"🚨 SECURITY: Blocked response containing sensitive pattern: {pattern}")
                # Return a safe, generic response instead
                return "Desculpe, não posso fornecer essa informação no momento. Como posso ajudá-lo de outra forma?"

        return text

    async def process_message(
        self,
        sender_key: str,
        message_text: str,
        original_query: Optional[str] = None,
        agent_run_id: Optional[int] = None,
        message_id: Optional[str] = None
    ) -> Dict:
        """
        Process a message through the agent.

        Args:
            sender_key: Identifier for the sender
            message_text: Full message with context (for AI processing)
            original_query: Original user query without context (for knowledge base search)
            agent_run_id: Agent run ID for token tracking (Phase 7.2)
            message_id: MCP message ID for token tracking (Phase 7.2)

        Returns dict with: answer, tool_used, tokens, execution_time, error

        Note: Legacy tool detection removed. Skills (web_search, weather, web_scraping)
        are now processed by SkillManager in router.py before reaching this method.
        """
        start_time = time.time()
        tool_used = None
        tool_result = None

        self.logger.info(f"Processing message from {sender_key}")
        self.logger.info(f"Message text: {message_text[:200]}")

        # Phase 20: Sentinel Security Agent - Analyze user message for threats
        # Only analyze if db and tenant_id are available
        if self.db and self.tenant_id:
            try:
                from services.sentinel_service import SentinelService
                from services.skill_context_service import SkillContextService
                sentinel = SentinelService(self.db, self.tenant_id)

                # Phase 20: Get skill context for this agent
                # This provides Sentinel with information about expected behaviors
                # for enabled skills (e.g., browser automation, shell commands)
                skill_context_str = None
                if self.agent_id:
                    try:
                        skill_ctx_service = SkillContextService(self.db)
                        skill_ctx = skill_ctx_service.get_agent_skill_context(self.agent_id)
                        skill_context_str = skill_ctx.get('formatted_context')
                        if skill_context_str:
                            self.logger.debug(
                                f"Loaded skill context for agent {self.agent_id}: "
                                f"{skill_ctx.get('enabled_skills', [])}"
                            )
                    except Exception as skill_e:
                        self.logger.warning(f"Failed to load skill context: {skill_e}")

                # Analyze user message (source=None means external/user content)
                # Note: System prompts and context are analyzed separately with appropriate source tags
                sentinel_result = await sentinel.analyze_prompt(
                    prompt=original_query or message_text,
                    agent_id=self.agent_id,
                    sender_key=sender_key,
                    source=None,  # User message - no internal source tag
                    message_id=message_id,
                    skill_context=skill_context_str,  # Provide skill context
                )

                if sentinel_result.is_threat_detected and sentinel_result.action == "blocked":
                    self.logger.warning(
                        f"🛡️ SENTINEL: Message blocked - {sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Send notification to the user who sent the blocked message
                    try:
                        config = sentinel.get_effective_config(self.agent_id)
                        mcp_api_url = self.config.get("mcp_api_url") if self.config else None
                        mcp_api_secret = self.config.get("mcp_api_secret") if self.config else None
                        await sentinel.send_threat_notification(
                            result=sentinel_result,
                            config=config,
                            sender_key=sender_key,
                            agent_id=self.agent_id,
                            mcp_api_url=mcp_api_url,
                            mcp_api_secret=mcp_api_secret,
                        )
                    except Exception as notif_e:
                        self.logger.warning(f"Failed to send Sentinel notification: {notif_e}")
                    return {
                        "answer": f"🛡️ Your message was blocked by security measures: {sentinel_result.threat_reason}",
                        "tool_used": None,
                        "tokens": 0,
                        "execution_time": time.time() - start_time,
                        "error": None,
                        "security_blocked": True,
                        "security_reason": sentinel_result.threat_reason,
                        "security_detection_type": sentinel_result.detection_type,
                    }
                elif sentinel_result.is_threat_detected and sentinel_result.action == "warned":
                    self.logger.warning(
                        f"⚠️ SENTINEL: Message flagged (warning) - {sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Continue processing but log the warning
                elif sentinel_result.is_threat_detected and sentinel_result.action == "allowed":
                    # detect_only mode: threat detected but allowed through
                    self.logger.warning(
                        f"⚠️ SENTINEL: Threat detected (detect-only) - {sentinel_result.detection_type}: {sentinel_result.threat_reason}"
                    )
                    # Send notification for detected-but-allowed message
                    try:
                        config = sentinel.get_effective_config(self.agent_id)
                        mcp_api_url = self.config.get("mcp_api_url") if self.config else None
                        mcp_api_secret = self.config.get("mcp_api_secret") if self.config else None
                        await sentinel.send_threat_notification(
                            result=sentinel_result,
                            config=config,
                            sender_key=sender_key,
                            agent_id=self.agent_id,
                            mcp_api_url=mcp_api_url,
                            mcp_api_secret=mcp_api_secret,
                        )
                    except Exception as notif_e:
                        self.logger.warning(f"Failed to send Sentinel notification: {notif_e}")
            except Exception as e:
                # Fail open - don't block messages if Sentinel fails
                self.logger.error(f"Sentinel analysis failed: {e}", exc_info=True)

        # Use original query for knowledge base search if provided
        search_query = original_query if original_query else message_text

        # Legacy tool detection removed - skills now handle search, weather, scraping
        # via SkillManager in router.py

        # Phase 4.8: Memory context now provided by Multi-Agent Memory Manager
        # Ring buffer deprecated - context passed via message_text parameter from router

        # Phase 16: Search knowledge base - use combined if in project context
        # Use original_query (without context) for better semantic matching
        knowledge_context = None
        knowledge_results = []  # Track KB usage for response metadata

        if self.combined_knowledge_service and self.project_id:
            # Phase 16: Use CombinedKnowledgeService for agent + project KB
            self.logger.info(f"Searching combined KB (agent+project) with query: {search_query[:100]}")
            try:
                self.logger.info(f"[KB BADGE] RIGHT BEFORE await call")
                formatted_context, knowledge_results = await self.combined_knowledge_service.get_context_for_message(
                    query=search_query,
                    agent_id=self.agent_id,
                    project_id=self.project_id,
                    tenant_id=self.tenant_id,
                    user_id=self.user_id,
                    max_results=5
                )
                self.logger.info(f"[KB BADGE] RIGHT AFTER await call")
                self.logger.info(f"[KB BADGE] Combined KB search completed: {len(knowledge_results)} results")
                if knowledge_results:
                    self.logger.info(f"Found {len(knowledge_results)} relevant chunks from combined KB")
                    knowledge_context = formatted_context

                    # Phase 8: Emit KB used event for Graph View real-time activity
                    if self.tenant_id and self.agent_id:
                        doc_ids = set(r.get('document_id') or r.get('id', 0) for r in knowledge_results)
                        emit_kb_used_async(
                            tenant_id=self.tenant_id,
                            agent_id=self.agent_id,
                            doc_count=len(doc_ids),
                            chunk_count=len(knowledge_results)
                        )
                else:
                    self.logger.warning(f"[KB BADGE] Combined KB search returned ZERO results!")
            except Exception as e:
                import traceback
                self.logger.error(f"[KB BADGE] ERROR searching combined knowledge base: {e}")
                self.logger.error(f"[KB BADGE] Full traceback: {traceback.format_exc()}")
        elif self.knowledge_service and self.agent_id:
            # Original: Use agent-only KB
            try:
                self.logger.info(f"Searching agent KB with query: {search_query[:100]}")
                knowledge_results = self.knowledge_service.search_knowledge(
                    agent_id=self.agent_id,
                    query=search_query,
                    max_results=3,  # Top 3 most relevant chunks
                    similarity_threshold=0.3  # Lower threshold for better recall
                )
                if knowledge_results:
                    self.logger.info(f"Found {len(knowledge_results)} relevant knowledge chunks")
                    knowledge_context = self._format_knowledge_context(knowledge_results)

                    # Phase 8: Emit KB used event for Graph View real-time activity
                    if self.tenant_id and self.agent_id:
                        doc_ids = set(r.get('document_id') or r.get('id', 0) for r in knowledge_results)
                        emit_kb_used_async(
                            tenant_id=self.tenant_id,
                            agent_id=self.agent_id,
                            doc_count=len(doc_ids),
                            chunk_count=len(knowledge_results)
                        )
            except Exception as e:
                self.logger.warning(f"Error searching knowledge base: {e}")

        # Build context with tool result and knowledge (memory context already in message_text)
        context = self._build_context([], message_text, tool_result, knowledge_context)

        # Get system prompt and add current date
        system_prompt = self.config.get("system_prompt", "You are a helpful assistant.")

        # CRITICAL FIX: Add model identity protection
        # Prevents agents from claiming to be specific models (stops hallucination)
        model_identity_guard = """
IMPORTANT - Model Identity & Language:
- You are an AI assistant. When asked about your identity or capabilities:
- Say you are "an AI assistant" or describe your PURPOSE (e.g., "customer support assistant")
- Do NOT claim to know your specific model name (GPT, Claude, Gemini, T5, Llama, etc.)
- Do NOT make up model names or versions
- If asked directly, say: "I'm an AI assistant powered by advanced language models"
- Focus on what you CAN DO, not what model you are

CRITICAL - Language Matching (HIGHEST PRIORITY):
- ALWAYS respond in the SAME LANGUAGE as the user's CURRENT message
- This rule OVERRIDES any language preferences in memory or context
- If the user writes in English NOW, respond ONLY in English
- If the user writes in Portuguese NOW, respond ONLY in Portuguese
- If the user writes in Spanish NOW, respond ONLY in Spanish
- IGNORE any learned language preferences - match the CURRENT message language
- Do NOT greet in a different language than the user's message
"""

        # Add current date/time context
        from datetime import datetime
        current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "October 01, 2025"
        current_time = datetime.now().strftime("%H:%M")
        system_prompt_with_date = f"{model_identity_guard}\n\n{system_prompt}\n\nIMPORTANT: Today's date is {current_date} and current time is {current_time}. When users ask for 'today' or 'now', they are referring to this date."

        # Phase 4.2: Add contact information to system prompt
        # IMPORTANT: Pass agent_id to prevent personality contamination between agents
        if self.contact_service:
            contact_context = self.contact_service.format_contacts_for_context(agent_id=self.agent_id)
            system_prompt_with_date = f"{system_prompt_with_date}\n\n{contact_context}"

        # Phase 6.1: Add custom tools to system prompt
        ollama_tools = None
        if self.sandboxed_tools:
            sandboxed_tools_prompt = self.sandboxed_tools.get_tool_system_prompts()
            self.logger.info(f"[SANDBOXED TOOLS] sandboxed_tools_prompt generated: {len(sandboxed_tools_prompt) if sandboxed_tools_prompt else 0} chars")
            if sandboxed_tools_prompt:
                self.logger.info(f"[SANDBOXED TOOLS] Adding {len(sandboxed_tools_prompt)} chars of tool prompts to system prompt")
                # Log first 500 chars for debugging
                self.logger.debug(f"[SANDBOXED TOOLS] Prompt preview: {sandboxed_tools_prompt[:500]}...")
                system_prompt_with_date = f"{system_prompt_with_date}\n\n{sandboxed_tools_prompt}"
                # CRITICAL FIX 2026-01-29: Force the AI to output tool calls, not just acknowledge
                # The AI (especially Gemini) tends to say "I will execute..." instead of actually outputting the tool call
                system_prompt_with_date += """

MANDATORY TOOL EXECUTION RULES

You have access to custom tools. When the user asks you to use a tool or run a command:

1. DO NOT just acknowledge or describe what you will do
2. DO NOT say "I will execute..." or "Proceeding with..." or "Compreendido..."
3. IMMEDIATELY output the tool call block in your response

REQUIRED FORMAT - Use this EXACT format:
[TOOL_CALL]
tool_name: <name_of_tool>
command_name: <command_to_run>
parameters:
  <param1>: <value1>
  <param2>: <value2>
[/TOOL_CALL]

EXAMPLE - If user says "run nmap quick_scan on scanme.nmap.org":

WRONG RESPONSE (do NOT do this):
"Compreendido. Procederei com a execução do escaneamento..."

CORRECT RESPONSE (do THIS):
[TOOL_CALL]
tool_name: nmap
command_name: quick_scan
parameters:
  target: scanme.nmap.org
  output_file: scan_results.txt
[/TOOL_CALL]

The system will automatically execute the tool and return the results.
You can add a brief message AFTER the tool call block if needed.
========================================"""
            else:
                self.logger.warning(f"[SANDBOXED TOOLS] No custom tools prompt generated (no tools enabled or available)")

            # Generate Ollama-compatible tools for native tool calling
            if self.ai_client.provider == "ollama":
                ollama_tools = self.sandboxed_tools.get_ollama_tools()

        # Phase 18.3.8: Add skill-based tools (like shell) if in agentic mode
        skill_manager = get_skill_manager()
        skill_tools = []
        shell_os_context = ""
        if self.db and self.agent_id:
            try:
                skill_tools, shell_os_context = await skill_manager.get_skill_tool_definitions(self.db, self.agent_id)
                if skill_tools:
                    self.logger.info(f"[SKILL TOOLS] Found {len(skill_tools)} skill tools for agent {self.agent_id}")

                    # Build shell tool prompt with OS-aware commands
                    shell_tool_prompt = """

## Shell Command Tool (run_shell_command)

You have access to execute shell commands on remote hosts. When the user asks you to check system status, run commands, or interact with servers, you should use the run_shell_command tool.
"""
                    # Add OS context if available
                    if shell_os_context:
                        self.logger.info(f"[SKILL TOOLS] Injecting OS context into shell prompt")
                        shell_tool_prompt += f"""
### Available Targets and Operating Systems:
{shell_os_context}

CRITICAL: You MUST use OS-appropriate commands for each target!

**macOS (Darwin) Commands:**
- CPU/Processes: `ps aux | head -20` or `top -l 1 | head -15`
- Memory: `vm_stat` or `top -l 1 | head -10`
- Disk: `df -h`
- Network: `netstat -an | head -20` or `lsof -i | head -20`
- System info: `sw_vers && uname -a`

**Linux Commands:**
- CPU: `top -bn1 | head -20`
- Memory: `free -h` or `cat /proc/meminfo | head -10`
- Disk: `df -h`
- Network: `ss -tulpn` or `netstat -tulpn`
- System info: `cat /etc/os-release && uname -a`

**Windows (PowerShell) Commands:**
- Processes: `Get-Process | Select-Object -First 20`
- Memory: `Get-WmiObject Win32_OperatingSystem | Select FreePhysicalMemory`
- Disk: `Get-PSDrive -PSProvider FileSystem`
- System info: `Get-ComputerInfo | Select CsName, WindowsVersion`

WARNING: NEVER use Linux-specific commands on macOS!
- WRONG on macOS: `top -bn1`, `free -h`, `cat /proc/meminfo`
- CORRECT on macOS: `top -l 1`, `vm_stat`, `sysctl hw.memsize`
"""
                    else:
                        shell_tool_prompt += """
Note: Target OS information is not available. Use portable commands when possible (like `df -h`, `hostname`, `pwd`), or ask the user about the target system.
"""

                    shell_tool_prompt += """
REQUIRED FORMAT for shell commands:
[TOOL_CALL]
tool_name: shell
command_name: run_shell_command
parameters:
  script: <the shell command to run>
  target: default
  timeout: 60
[/TOOL_CALL]

EXAMPLES:

User: "check disk usage"
[TOOL_CALL]
tool_name: shell
command_name: run_shell_command
parameters:
  script: df -h
  target: default
  timeout: 60
[/TOOL_CALL]

User: "what's the hostname?"
[TOOL_CALL]
tool_name: shell
command_name: run_shell_command
parameters:
  script: hostname
  target: default
  timeout: 30
[/TOOL_CALL]

IMPORTANT: When the user asks for system information, server status, file listings, or any shell command execution, use this tool immediately. Do NOT just describe the command - execute it!
"""
                    system_prompt_with_date = f"{system_prompt_with_date}\n{shell_tool_prompt}"

                    # Phase 4: Add prompts for other skill tools
                    non_shell_tools_prompt = self._build_skill_tools_prompt(skill_tools)
                    if non_shell_tools_prompt:
                        system_prompt_with_date = f"{system_prompt_with_date}\n{non_shell_tools_prompt}"

                    # Add to ollama_tools if using Ollama
                    if ollama_tools is not None:
                        ollama_tools.extend(skill_tools)
                    elif skill_tools:
                        ollama_tools = skill_tools
            except Exception as e:
                self.logger.warning(f"[SKILL TOOLS] Error getting skill tools: {e}")

        try:
            # Call AI (Phase 7.2: Pass tracking parameters)
            result = await self.ai_client.generate(
                system_prompt_with_date,
                context,
                operation_type="message_processing",
                agent_id=self.agent_id,
                agent_run_id=agent_run_id,
                sender_key=sender_key,
                message_id=message_id,
                tools=ollama_tools
            )

            execution_time = int((time.time() - start_time) * 1000)

            if result["error"]:
                return {
                    "answer": None,
                    "tool_used": tool_used,
                    "tool_result": tool_result,  # Include raw tool response
                    "tokens": None,
                    "execution_time_ms": execution_time,
                    "kb_used": [],  # Empty list on error
                    "error": result["error"]
                }

            # Phase 6.1: Check if AI response contains custom tool call
            # Strip reasoning tags from AI response (e.g., DeepSeek R1 <think> blocks)
            ai_response = self._strip_reasoning_tags(result["answer"])

            # SECURITY FIX 2026-01-11: Strip internal context markers (memory leaks)
            if ai_response:
                ai_response = self._strip_internal_context(ai_response)

            # SECURITY FIX 2026-01-08: Filter out responses with internal information leaks
            if ai_response:
                ai_response = self._filter_sensitive_content(ai_response)

            # Check for tool call patterns - support multiple formats:
            # 1. Standard: ```tool:nmap (with backticks)
            # 2. Simple: tool:nmap (without backticks, used by some Ollama models)
            # 3. JSON: ```json {"name":"nmap","parameters":{...}} (used by MFDoom/deepseek-v2-tool-calling)
            # 4. [TOOL_CALL]...[/TOOL_CALL] (used by custom tool system prompts)
            has_backtick_format = "```tool:" in ai_response if ai_response else False
            has_simple_format = re.search(r'(?:^|\n)tool:', ai_response) is not None if ai_response else False
            has_json_format = "```json" in ai_response and '"name"' in ai_response if ai_response else False
            has_tool_call_format = "[TOOL_CALL]" in ai_response and "[/TOOL_CALL]" in ai_response if ai_response else False
            self.logger.debug(f"Tool detection: backtick={has_backtick_format}, simple={has_simple_format}, json={has_json_format}, tool_call={has_tool_call_format}")

            if has_backtick_format or has_simple_format or has_json_format or has_tool_call_format:
                self.logger.info("Tool call detected in AI response")

                # Try to parse the tool call
                tool_call = None
                if self.sandboxed_tools:
                    tool_call = self.sandboxed_tools.parse_tool_call(ai_response)

                if tool_call:
                    tool_name = tool_call.get('tool_name', '')
                    command_name = tool_call.get('command_name', '')
                    parameters = tool_call.get('parameters', {})

                    self.logger.info(f"Parsed tool call: tool={tool_name}, command={command_name}, params={parameters}")

                    # Phase 5: Check if this is a skill-based tool
                    # Skills-as-Tools: Route ALL skill tools through skill_manager, not just shell
                    is_shell_tool = tool_name == 'shell' or command_name == 'run_shell_command'

                    # For shell tool, LLM may call it as "shell" but MCP def uses "run_shell_command"
                    effective_tool_name = 'run_shell_command' if is_shell_tool else tool_name
                    skill_class = skill_manager.find_skill_by_tool_name(effective_tool_name) if skill_tools else None

                    if skill_class and skill_tools:
                        # Phase 5: Execute skill-based tool via skill manager
                        self.logger.info(f"[SKILL TOOL] Executing skill tool '{tool_name}' via skill_manager")

                        if is_shell_tool:
                            # Shell tool needs special parameter handling
                            script = parameters.get('script', '')
                            target = parameters.get('target', 'default')
                            timeout = int(parameters.get('timeout', 60))

                            if script:
                                tool_execution_result = await skill_manager.execute_tool_call(
                                    db=self.db,
                                    agent_id=self.agent_id,
                                    tool_name='run_shell_command',
                                    arguments={'script': script, 'target': target, 'timeout': timeout},
                                    sender_key=sender_key
                                )
                            else:
                                self.logger.warning("Shell tool call missing 'script' parameter")
                                tool_execution_result = None
                        else:
                            # Check if this tool produces media (like generate_image)
                            media_producing_tools = {'generate_image'}
                            needs_full_result = tool_name in media_producing_tools

                            # All other skill tools (web_search, get_weather, manage_flows, etc.)
                            skill_result = await skill_manager.execute_tool_call(
                                db=self.db,
                                agent_id=self.agent_id,
                                tool_name=tool_name,
                                arguments=parameters,
                                sender_key=sender_key,
                                return_full_result=needs_full_result
                            )

                            # Handle media-producing tools
                            if needs_full_result and skill_result:
                                from agent.skills.base import SkillResult
                                if isinstance(skill_result, SkillResult):
                                    tool_execution_result = skill_result.output if skill_result.success else f"Error: {skill_result.output}"
                                    # Store media paths for later sending
                                    if skill_result.media_paths:
                                        if not hasattr(self, '_pending_media_paths'):
                                            self._pending_media_paths = []
                                        self._pending_media_paths.extend(skill_result.media_paths)
                                        self.logger.info(f"Queued {len(skill_result.media_paths)} media files for sending")
                                else:
                                    tool_execution_result = skill_result
                            else:
                                tool_execution_result = skill_result

                        if tool_execution_result:
                            # Replace tool call block with result
                            if has_tool_call_format and "[TOOL_CALL]" in ai_response:
                                start = ai_response.find("[TOOL_CALL]")
                                end = ai_response.find("[/TOOL_CALL]") + len("[/TOOL_CALL]")
                                if end > start:
                                    ai_response = ai_response[:start] + tool_execution_result + ai_response[end:]
                            else:
                                ai_response = tool_execution_result

                            tool_used = f"skill:{tool_name}"
                            tool_result = tool_execution_result

                    elif self.sandboxed_tools:
                        # Execute custom tool (non-shell)
                        self.logger.info(f"Executing custom tool: {tool_call}")
                        # Pass sender_key as recipient for WhatsApp follow-up notifications
                        tool_execution_result = await self.sandboxed_tools.execute_tool_call(
                            tool_call,
                            agent_run_id=agent_run_id,
                            recipient=sender_key
                        )

                        if tool_execution_result:
                            # Update response with tool result - handle different formats
                            if has_tool_call_format and "[TOOL_CALL]" in ai_response:
                                # Replace [TOOL_CALL]...[/TOOL_CALL] block with tool result
                                start = ai_response.find("[TOOL_CALL]")
                                end = ai_response.find("[/TOOL_CALL]") + len("[/TOOL_CALL]")
                                if end > start:
                                    ai_response = ai_response[:start] + tool_execution_result + ai_response[end:]
                            elif has_backtick_format and "```tool:" in ai_response:
                                start = ai_response.find("```tool:")
                                end = ai_response.find("```", start + 8) + 3
                                if end > start:
                                    ai_response = ai_response[:start] + tool_execution_result + ai_response[end:]
                            elif has_json_format and "```json" in ai_response:
                                start = ai_response.find("```json")
                                end = ai_response.find("```", start + 7) + 3
                                if end > start:
                                    ai_response = ai_response[:start] + tool_execution_result + ai_response[end:]
                            elif has_simple_format:
                                # For simple format, append the result instead of replacing
                                ai_response = tool_execution_result

                            tool_used = f"custom:{tool_call['tool_name']}"
                            tool_result = tool_execution_result

            # Phase 4.8: Memory management moved to Multi-Agent Memory Manager in router
            # Ring buffer deprecated

            # Centralized contamination detection (uses ContaminationDetector service)
            from .contamination_detector import get_contamination_detector
            detector = get_contamination_detector(db_session=self.db, agent_id=self.agent_id)
            contamination_pattern = detector.check(ai_response)

            if contamination_pattern:
                self.logger.error(
                    f"CONTAMINATION DETECTED in AI response! Pattern: '{contamination_pattern}', "
                    f"Response: '{ai_response[:200]}...'"
                )
                # Return error instead of contaminated response
                return {
                    "answer": "⚠️ Erro interno: Resposta contaminada detectada e bloqueada.",
                    "tool_used": None,
                    "tool_result": None,
                    "tokens": result["token_usage"] if result else None,
                    "execution_time_ms": execution_time,
                    "kb_used": [],
                    "error": f"Contamination detected: {contamination_pattern}"
                }

            # Format KB usage metadata for response
            kb_used = []
            if knowledge_results:
                for kr in knowledge_results:
                    kb_item = {
                        "document_name": kr.get("document_name", "Unknown"),
                        "similarity": round(kr.get("similarity", 0.0), 2),
                        "chunk_index": kr.get("chunk_index", 0)
                    }
                    # Phase 16: Include source attribution for combined KB
                    if kr.get("source_type"):
                        kb_item["source_type"] = kr.get("source_type")
                    if kr.get("project_name"):
                        kb_item["project_name"] = kr.get("project_name")
                    kb_used.append(kb_item)

            # Collect pending media paths from tool executions
            media_paths = getattr(self, '_pending_media_paths', None)
            if media_paths:
                self._pending_media_paths = []  # Clear for next request

            return {
                "answer": ai_response,
                "tool_used": tool_used,
                "tool_result": tool_result,  # Include raw tool response
                "tokens": result["token_usage"],
                "execution_time_ms": execution_time,
                "kb_used": kb_used,  # KB usage tracking
                "media_paths": media_paths,  # Media files from skill tools (e.g., generate_image)
                "error": None
            }

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            self.logger.error(f"Error processing message: {e}", exc_info=True)
            return {
                "answer": None,
                "tool_used": tool_used,
                "tokens": None,
                "execution_time_ms": execution_time,
                "kb_used": [],  # Empty list on error
                "error": str(e)
            }

    def _build_context(self, memory_messages: List[Dict], current_message: str, tool_result: Optional[str] = None, knowledge_context: Optional[str] = None) -> str:
        """Build context string with memory, tool result, knowledge, and current message"""
        context_parts = []

        if memory_messages:
            context_parts.append("Recent conversation history:")
            for msg in memory_messages[-5:]:  # Last 5 messages
                role = msg["role"].capitalize()
                content = msg["content"]
                context_parts.append(f"{role}: {content}")
            context_parts.append("")

        # Phase 5.0: Add knowledge base context if available
        if knowledge_context:
            context_parts.append(knowledge_context)
            context_parts.append("")

        # Add tool result if available (truncated to prevent massive context)
        if tool_result:
            MAX_TOOL_RESULT_CHARS = 10000  # 10k chars max for tool results
            truncated_result = tool_result if len(tool_result) <= MAX_TOOL_RESULT_CHARS else (
                tool_result[:MAX_TOOL_RESULT_CHARS] + f"\n\n[... truncated {len(tool_result) - MAX_TOOL_RESULT_CHARS} chars ...]"
            )

            context_parts.append("Tool Result:")
            context_parts.append(truncated_result)
            context_parts.append("")
            context_parts.append("Please use the tool result above to answer the user's question.")
            context_parts.append("")

        context_parts.append(f"Current message: {current_message}")

        return "\n".join(context_parts)

    def _format_knowledge_context(self, knowledge_results: List[Dict]) -> str:
        """
        Format knowledge base search results for context injection.

        Args:
            knowledge_results: List of knowledge chunks from search

        Returns:
            Formatted context string
        """
        if not knowledge_results:
            return None

        context_parts = ["📚 Relevant knowledge from your knowledge base:"]
        context_parts.append("")

        for i, result in enumerate(knowledge_results, 1):
            doc_name = result.get("document_name", "Unknown")
            content = result.get("content", "")
            similarity = result.get("similarity", 0.0)

            context_parts.append(f"[Knowledge {i} - from {doc_name} (relevance: {similarity:.0%})]")
            context_parts.append(content)
            context_parts.append("")

        context_parts.append("Use the knowledge above to answer the question if relevant. If the knowledge doesn't help answer the question, rely on your general knowledge.")

        return "\n".join(context_parts)
