"""
Phase 5.0 Skills System - Base Classes
Defines abstract base class for all agent skills.

Phase 17: Updated to use system AI configuration instead of hardcoded defaults.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class InboundMessage:
    """
    Represents an incoming message that might trigger a skill.

    Supports multiple channels: WhatsApp, Telegram, Playground, Flow steps.
    """
    id: str
    sender: str
    sender_key: str
    body: str
    chat_id: str
    chat_name: Optional[str]
    is_group: bool
    timestamp: datetime
    media_type: Optional[str] = None  # "audio", "image", "video", "document", None
    media_url: Optional[str] = None
    media_path: Optional[str] = None
    # Phase Skills-as-Tools: Channel information for channel-aware tool behavior
    channel: Optional[str] = None  # "whatsapp", "telegram", "playground", "flow", None


@dataclass
class SkillResult:
    """
    Result from skill execution.
    """
    success: bool
    output: str  # Human-readable output or error message
    metadata: Dict[str, Any]  # Additional data (e.g., transcription duration, file paths)
    processed_content: Optional[str] = None  # Processed text (e.g., transcription for audio)
    media_paths: Optional[List[str]] = None  # Paths to media files to send (screenshots, images, etc.)


class BaseSkill(ABC):
    """
    Abstract base class for all agent skills.

    Each skill must implement:
    - skill_type: Unique identifier (e.g., "audio_transcript", "audio_response")
    - skill_name: Human-readable name
    - skill_description: What the skill does
    - can_handle(): Check if this skill should process the message
    - process(): Execute the skill logic

    Skills-as-Tools (MCP Standard):
    Skills can optionally implement tool mode to be exposed as LLM function calls:
    - get_mcp_tool_definition(): Return MCP-compliant tool definition
    - execute_tool(): Execute the skill as a tool call
    - is_tool_enabled(): Check if tool mode is active
    """

    # Class attributes (must be overridden)
    skill_type: str = "base_skill"
    skill_name: str = "Base Skill"
    skill_description: str = "Base skill class (override this)"

    # Skills-as-Tools: Execution mode (can be overridden by subclass or config)
    # Values: "legacy", "tool", "hybrid", "passive", "special"
    # - "legacy"/"programmatic": Keyword/slash command only (no LLM tool exposure)
    # - "tool"/"agentic": LLM tool call only (no keyword detection)
    # - "hybrid": Both tool and legacy modes supported
    # - "passive": Post-processing hook (e.g., adaptive_personality, knowledge_sharing)
    # - "special": Media-triggered (e.g., audio_transcript)
    execution_mode: str = "legacy"

    def __init__(self):
        """Initialize the skill."""
        self._config: Dict[str, Any] = {}  # Set by skill manager during initialization
        self._db_session = None  # Database session for API key loading (optional)

    def set_db_session(self, db):
        """
        Set database session for skills that need database access.

        Used for:
        - Loading API keys for AI classification
        - Database operations in skill processing

        Args:
            db: SQLAlchemy database session
        """
        self._db_session = db

    @abstractmethod
    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Determine if this skill can handle the given message.

        Args:
            message: Inbound message to evaluate

        Returns:
            True if skill should process this message, False otherwise

        Example:
            async def can_handle(self, message: InboundMessage) -> bool:
                return message.media_type == "audio"
        """
        pass

    @abstractmethod
    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Process the message with this skill.

        Args:
            message: The inbound message to process
            config: Skill-specific configuration from AgentSkill.config

        Returns:
            SkillResult with success status, output, and metadata

        Example:
            async def process(self, message: InboundMessage, config: Dict) -> SkillResult:
                # Download audio
                audio_path = await self._download_audio(message.media_url)

                # Transcribe with Whisper
                transcript = await self._transcribe(audio_path, config)

                return SkillResult(
                    success=True,
                    output=f"Transcription: {transcript}",
                    metadata={"duration": 45.2, "language": "pt-BR"},
                    processed_content=transcript
                )
        """
        pass

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for this skill.

        Returns:
            Dict with default config values

        Example:
            {
                "api_key": None,
                "language": "auto",
                "model": "whisper-1",
                "keywords": ["trigger", "activate"],
                "use_ai_fallback": True,
                "ai_model": "gemini-2.5-flash"
            }
        """
        return {
            # Phase 7.1: Configurable keyword triggers (optional for each skill)
            "keywords": [],  # Empty list = skill doesn't use keyword filtering
            "use_ai_fallback": True,  # Use AI classification when keywords match
            "ai_model": "gemini-2.5-flash-lite"  # Model for intent classification
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration (for UI validation).

        Returns:
            Dict with JSON schema for configuration fields

        Example:
            {
                "type": "object",
                "properties": {
                    "api_key": {"type": "string", "description": "OpenAI API key"},
                    "language": {"type": "string", "enum": ["auto", "en", "pt"], "default": "auto"},
                    "model": {"type": "string", "default": "whisper-1"},
                    "keywords": {"type": "array", "items": {"type": "string"}},
                    "use_ai_fallback": {"type": "boolean"},
                    "ai_model": {"type": "string", "enum": ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gpt-3.5-turbo", "claude-haiku"]}
                },
                "required": ["api_key"]
            }
        """
        return {
            "type": "object",
            "properties": {
                # Phase 7.1: Configurable keyword schema (all skills)
                "keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Keywords that trigger skill detection (case-insensitive pre-filter)",
                    "default": []
                },
                "use_ai_fallback": {
                    "type": "boolean",
                    "description": "Use AI classification when keywords match but intent is unclear",
                    "default": True
                },
                "ai_model": {
                    "type": "string",
                    "enum": ["gemini-2.5-flash", "gpt-3.5-turbo", "claude-haiku"],
                    "description": "AI model for intent classification",
                    "default": "gemini-2.5-flash"
                }
            },
            "required": []
        }

    @classmethod
    def get_sentinel_context(cls) -> Dict[str, Any]:
        """
        Get security context for Sentinel analysis.

        Override this in skills to provide Sentinel with information about
        what this skill is designed to do, so legitimate usage isn't blocked.

        Phase 20: Skill-aware Sentinel security system.

        Returns:
            Dict with:
            - expected_intents: List of expected command descriptions
            - expected_patterns: List of keywords/phrases normal for this skill
            - risk_notes: Security considerations Sentinel should still watch for

        Example:
            @classmethod
            def get_sentinel_context(cls) -> Dict[str, Any]:
                return {
                    "expected_intents": [
                        "Navigate to URLs and websites",
                        "Take screenshots of web pages"
                    ],
                    "expected_patterns": [
                        "go to", "navigate", "screenshot", "http://", "https://"
                    ],
                    "risk_notes": "Still flag credential harvesting and phishing attempts."
                }
        """
        return {
            "expected_intents": [],
            "expected_patterns": [],
            "risk_notes": None
        }

    # =========================================================================
    # SKILLS-AS-TOOLS: EXECUTION MODE CONTROL
    # =========================================================================

    def is_tool_enabled(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if this skill should be exposed as an LLM tool.

        Skills-as-Tools: Determines if the skill appears in the tools list
        sent to the LLM for function calling.

        Args:
            config: Skill configuration (from AgentSkill.config)

        Returns:
            True if tool should be available for AI/agentic use.
            False if only slash command/keyword triggers work.
        """
        config = config or getattr(self, '_config', {}) or {}
        execution_mode = config.get('execution_mode', self.execution_mode)

        # Support both old and new terminology
        if execution_mode in ('tool', 'agentic'):
            return True
        if execution_mode == 'hybrid':
            return True  # Hybrid exposes as tool AND supports legacy
        if execution_mode in ('legacy', 'programmatic', 'passive', 'special'):
            return False

        return False  # Default to not exposing as tool

    def is_legacy_enabled(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if legacy keyword/slash command mode is enabled.

        Args:
            config: Skill configuration

        Returns:
            True if keyword matching and slash commands should work.
        """
        config = config or getattr(self, '_config', {}) or {}
        execution_mode = config.get('execution_mode', self.execution_mode)

        if execution_mode in ('legacy', 'programmatic'):
            return True
        if execution_mode == 'hybrid':
            return True  # Hybrid supports both
        # Tool-only mode doesn't support legacy
        if execution_mode in ('tool', 'agentic'):
            return False

        return True  # Default to legacy enabled for backward compatibility

    # =========================================================================
    # SKILLS-AS-TOOLS: MCP TOOL DEFINITION (Canonical Format)
    # =========================================================================

    @classmethod
    def get_mcp_tool_definition(cls) -> Optional[Dict[str, Any]]:
        """
        Return MCP-compliant tool definition (canonical format).

        Override in subclasses that support tool mode.
        Returns None for passive/special skills (no tool exposure).

        MCP Spec: https://modelcontextprotocol.io/docs/concepts/tools

        Returns:
            Dict with:
            - name: Tool name for LLM to call
            - title: Human-readable name (MCP feature)
            - description: What the tool does
            - inputSchema: JSON Schema for parameters
            - outputSchema: JSON Schema for output (optional)
            - annotations: Tool metadata (destructive, idempotent, audience)

        Example:
            @classmethod
            def get_mcp_tool_definition(cls) -> Dict[str, Any]:
                return {
                    "name": "get_weather",
                    "title": "Weather Lookup",
                    "description": "Get current weather for a location",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"}
                        },
                        "required": ["location"]
                    },
                    "annotations": {
                        "destructive": False,
                        "idempotent": True
                    }
                }
        """
        return None

    @classmethod
    def get_input_schema(cls) -> Dict[str, Any]:
        """
        Return JSON Schema for tool input parameters.

        Override in subclasses to define input parameters.
        Used by get_mcp_tool_definition() for inputSchema.
        """
        return {"type": "object", "properties": {}}

    @classmethod
    def get_output_schema(cls) -> Optional[Dict[str, Any]]:
        """
        Return JSON Schema for structured output (MCP feature).

        Override in subclasses for validated structured responses.
        """
        return None

    # =========================================================================
    # SKILLS-AS-TOOLS: PROVIDER ADAPTERS
    # =========================================================================

    @classmethod
    def to_openai_tool(cls) -> Optional[Dict[str, Any]]:
        """
        Convert MCP definition to OpenAI-compatible format.

        Works with: OpenAI, OpenRouter, Groq, Ollama, Gemini
        """
        mcp = cls.get_mcp_tool_definition()
        if not mcp:
            return None

        return {
            "type": "function",
            "function": {
                "name": mcp["name"],
                "description": mcp["description"],
                "parameters": mcp["inputSchema"]
            }
        }

    @classmethod
    def to_anthropic_tool(cls) -> Optional[Dict[str, Any]]:
        """
        Convert MCP definition to Anthropic tool use format.

        Used when provider is "anthropic" (direct Claude API).

        Anthropic differences from OpenAI:
        - Uses "input_schema" instead of "parameters"
        - No "type": "function" wrapper
        """
        mcp = cls.get_mcp_tool_definition()
        if not mcp:
            return None

        return {
            "name": mcp["name"],
            "description": mcp["description"],
            "input_schema": mcp["inputSchema"]
        }

    @classmethod
    def get_tool_definition(cls) -> Optional[Dict[str, Any]]:
        """
        DEPRECATED: Use get_mcp_tool_definition() or to_openai_tool().

        Returns OpenAI format for backward compatibility with ShellSkill.
        """
        return cls.to_openai_tool()

    # =========================================================================
    # SKILLS-AS-TOOLS: TOOL EXECUTION
    # =========================================================================

    async def execute_tool(
        self,
        arguments: Dict[str, Any],
        message: InboundMessage,
        config: Dict[str, Any]
    ) -> SkillResult:
        """
        Execute skill as a tool call.

        Override in subclasses to implement tool execution.
        The default implementation raises NotImplementedError.

        Args:
            arguments: Parsed arguments from LLM tool call
            message: Original inbound message (for context)
            config: Skill configuration

        Returns:
            SkillResult with tool execution output

        Example:
            async def execute_tool(
                self,
                arguments: Dict[str, Any],
                message: InboundMessage,
                config: Dict[str, Any]
            ) -> SkillResult:
                location = arguments.get("location")
                weather_data = await self._fetch_weather(location)
                return SkillResult(
                    success=True,
                    output=f"Weather in {location}: {weather_data['temp']}°C",
                    metadata={"location": location}
                )
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support tool execution. "
            f"Override execute_tool() to enable tool mode."
        )

    def _keyword_matches(self, message: str, keywords: List[str]) -> bool:
        """
        Check if message contains any of the specified keywords (case-insensitive).

        Phase 7.1: Helper method for keyword pre-filtering.

        Args:
            message: Message text to check
            keywords: List of keywords to match

        Returns:
            True if any keyword found in message

        Example:
            keywords = ["agent", "switch"]
            self._keyword_matches("I want to switch agents", keywords)  # True
            self._keyword_matches("Hello there", keywords)  # False
        """
        if not keywords:
            return False

        message_lower = message.lower()
        return any(keyword.lower() in message_lower for keyword in keywords)

    async def _ai_classify(self, message: str, config: Dict[str, Any]) -> bool:
        """
        Use AI to classify message intent.

        Phase 7.1: Helper method for AI-based intent detection.
        Phase 7.4: Passes database session for API key loading.
        Phase 17: Uses system AI config when no specific model configured.

        Args:
            message: Message text to classify
            config: Skill configuration (may contain ai_model override)

        Returns:
            True if AI classifies message as matching skill intent

        Example:
            config = {}  # Uses system AI config
            result = await self._ai_classify("Can you switch my agent?", config)
        """
        from agent.skills.ai_classifier import get_classifier

        classifier = get_classifier()

        # Phase 17: Use config's ai_model if specified, otherwise None (uses system config)
        ai_model = config.get("ai_model") if config.get("ai_model") else None

        return await classifier.classify_intent(
            message=message,
            skill_name=self.skill_name,
            skill_description=self.skill_description,
            model=ai_model,  # None = use system AI config
            db=self._db_session  # Pass database session for API key loading and system config
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} type={self.skill_type}>"
