"""
Sentinel Security Service - Phase 20

Core service for AI-powered security analysis.

This service provides:
1. Prompt injection detection
2. Agent takeover detection
3. Poisoning attack detection
4. Malicious shell intent detection

Key features:
- Internal source whitelisting (prevents false positives from persona/tone/skill injections)
- Configuration hierarchy (system -> tenant -> agent)
- Performance caching
- Audit logging for Watcher Security tab
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from sqlalchemy.orm import Session

from models import (
    SentinelConfig,
    SentinelAgentConfig,
    SentinelAnalysisLog,
    SentinelAnalysisCache,
)
from .sentinel_detections import (
    DETECTION_REGISTRY,
    get_default_prompt,
    get_prompt_detection_types,
    get_shell_detection_types,
)
from .sentinel_effective_config import SentinelEffectiveConfig

logger = logging.getLogger(__name__)


@dataclass
class SentinelAnalysisResult:
    """Result of a Sentinel security analysis."""

    is_threat_detected: bool
    threat_score: float  # 0.0-1.0
    threat_reason: Optional[str]
    action: str  # 'allowed', 'blocked', 'warned'
    detection_type: str
    analysis_type: str  # 'prompt', 'tool', 'shell'
    cached: bool = False
    response_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "is_threat_detected": self.is_threat_detected,
            "threat_score": self.threat_score,
            "threat_reason": self.threat_reason,
            "action": self.action,
            "detection_type": self.detection_type,
            "analysis_type": self.analysis_type,
            "cached": self.cached,
            "response_time_ms": self.response_time_ms,
        }


class SentinelService:
    """
    Core Sentinel security analysis service.

    Uses LLM-based semantic analysis to detect security threats.
    Implements source-aware whitelisting to avoid false positives.
    """

    # Internal prompt sources that should NOT trigger detection
    # These are system-injected prompts, not user content
    INTERNAL_SOURCES = [
        "persona_injection",       # Persona system prompts
        "tone_preset_injection",   # Tone/style instructions
        "skill_instruction",       # Skill-specific prompts
        "system_prompt",           # Agent system prompts
        "tool_definition",         # Tool schemas and descriptions
        "context_injection",       # Memory/knowledge context
        "os_context",              # Shell OS context injection
        "flow_instruction",        # Flow step instructions
        "knowledge_context",       # KB retrieval context
        "memory_context",          # Conversation memory context
    ]

    def __init__(self, db: Session, tenant_id: Optional[str] = None):
        """
        Initialize Sentinel service.

        Args:
            db: Database session
            tenant_id: Tenant ID for multi-tenancy (None for system-level)
        """
        self.db = db
        self.tenant_id = tenant_id
        self.logger = logging.getLogger(__name__)

    # =========================================================================
    # Configuration Methods
    # =========================================================================

    def get_system_config(self) -> Optional[SentinelConfig]:
        """Get the system-wide default configuration (tenant_id=NULL)."""
        return self.db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

    def get_tenant_config(self) -> Optional[SentinelConfig]:
        """Get tenant-specific configuration."""
        if not self.tenant_id:
            return None
        return self.db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id == self.tenant_id
        ).first()

    def get_agent_override(self, agent_id: int) -> Optional[SentinelAgentConfig]:
        """Get agent-specific override configuration."""
        return self.db.query(SentinelAgentConfig).filter(
            SentinelAgentConfig.agent_id == agent_id
        ).first()

    def get_effective_config(self, agent_id: Optional[int] = None, skill_type: Optional[str] = None) -> SentinelEffectiveConfig:
        """
        Get the effective security configuration for analysis.

        v1.6.0: Tries profile-based resolution first, falls back to legacy.

        Resolution chain:
        1. Profile resolution (skill -> agent -> tenant -> system default)
        2. Legacy fallback (agent override -> tenant config -> system config)
        3. Hardcoded defaults

        Args:
            agent_id: Optional agent ID for agent/skill-specific config
            skill_type: Optional skill type for skill-level profile resolution

        Returns:
            SentinelEffectiveConfig with resolved settings
        """
        try:
            from .sentinel_profiles_service import SentinelProfilesService
            profiles_service = SentinelProfilesService(self.db, self.tenant_id)
            result = profiles_service.get_effective_config(agent_id, skill_type)
            if result:
                return result
        except Exception as e:
            self.logger.warning(f"Profile resolution failed, using legacy: {e}")

        # Legacy fallback
        legacy_config = self._legacy_get_effective_config(agent_id)
        return SentinelEffectiveConfig.from_legacy_config(legacy_config)

    def _legacy_get_effective_config(self, agent_id: Optional[int] = None) -> SentinelConfig:
        """
        Legacy configuration resolution (pre-v1.6.0).

        Hierarchy:
        1. Agent override (if set)
        2. Tenant config (if set)
        3. System default
        """
        # Start with system config
        system_config = self.get_system_config()
        if not system_config:
            self.logger.warning("No system Sentinel config found, using defaults")
            return self._create_default_config()

        # Layer tenant config
        tenant_config = self.get_tenant_config()

        # Layer agent override
        agent_override = None
        if agent_id:
            agent_override = self.get_agent_override(agent_id)

        # Merge configs (later values override earlier)
        return self._merge_configs(system_config, tenant_config, agent_override)

    def _create_default_config(self) -> SentinelConfig:
        """Create a default in-memory config (not persisted)."""
        return SentinelConfig(
            tenant_id=None,
            is_enabled=True,
            enable_prompt_analysis=True,
            enable_tool_analysis=True,
            enable_shell_analysis=True,
            detect_prompt_injection=True,
            detect_agent_takeover=True,
            detect_poisoning=True,
            detect_shell_malicious_intent=True,
            aggressiveness_level=1,
            llm_provider="gemini",
            llm_model="gemini-2.5-flash-lite",
            llm_max_tokens=256,
            llm_temperature=0.1,
            cache_ttl_seconds=300,
            max_input_chars=5000,
            timeout_seconds=5.0,
            block_on_detection=True,
            log_all_analyses=False,
        )

    def _merge_configs(
        self,
        system_config: SentinelConfig,
        tenant_config: Optional[SentinelConfig],
        agent_override: Optional[SentinelAgentConfig]
    ) -> SentinelConfig:
        """
        Merge configuration hierarchy.

        Creates a new in-memory config with merged values.
        Agent override > Tenant config > System config
        """
        # Start with system config values
        merged = SentinelConfig(
            tenant_id=self.tenant_id,
            is_enabled=system_config.is_enabled,
            enable_prompt_analysis=system_config.enable_prompt_analysis,
            enable_tool_analysis=system_config.enable_tool_analysis,
            enable_shell_analysis=system_config.enable_shell_analysis,
            detect_prompt_injection=system_config.detect_prompt_injection,
            detect_agent_takeover=system_config.detect_agent_takeover,
            detect_poisoning=system_config.detect_poisoning,
            detect_shell_malicious_intent=system_config.detect_shell_malicious_intent,
            aggressiveness_level=system_config.aggressiveness_level,
            llm_provider=system_config.llm_provider,
            llm_model=system_config.llm_model,
            llm_max_tokens=system_config.llm_max_tokens,
            llm_temperature=system_config.llm_temperature,
            prompt_injection_prompt=system_config.prompt_injection_prompt,
            agent_takeover_prompt=system_config.agent_takeover_prompt,
            poisoning_prompt=system_config.poisoning_prompt,
            shell_intent_prompt=system_config.shell_intent_prompt,
            cache_ttl_seconds=system_config.cache_ttl_seconds,
            max_input_chars=system_config.max_input_chars,
            timeout_seconds=system_config.timeout_seconds,
            block_on_detection=system_config.block_on_detection,
            log_all_analyses=system_config.log_all_analyses,
            # Phase 20 Enhancement: Detection mode and slash command toggle
            detection_mode=getattr(system_config, 'detection_mode', 'block'),
            enable_slash_command_analysis=getattr(system_config, 'enable_slash_command_analysis', True),
        )

        # Override with tenant config if present
        if tenant_config:
            merged.is_enabled = tenant_config.is_enabled
            merged.enable_prompt_analysis = tenant_config.enable_prompt_analysis
            merged.enable_tool_analysis = tenant_config.enable_tool_analysis
            merged.enable_shell_analysis = tenant_config.enable_shell_analysis
            merged.detect_prompt_injection = tenant_config.detect_prompt_injection
            merged.detect_agent_takeover = tenant_config.detect_agent_takeover
            merged.detect_poisoning = tenant_config.detect_poisoning
            merged.detect_shell_malicious_intent = tenant_config.detect_shell_malicious_intent
            merged.aggressiveness_level = tenant_config.aggressiveness_level
            merged.llm_provider = tenant_config.llm_provider
            merged.llm_model = tenant_config.llm_model
            merged.llm_max_tokens = tenant_config.llm_max_tokens
            merged.llm_temperature = tenant_config.llm_temperature
            merged.cache_ttl_seconds = tenant_config.cache_ttl_seconds
            merged.timeout_seconds = tenant_config.timeout_seconds
            merged.block_on_detection = tenant_config.block_on_detection
            merged.log_all_analyses = tenant_config.log_all_analyses
            # Phase 20 Enhancement: Detection mode and slash command toggle
            merged.detection_mode = getattr(tenant_config, 'detection_mode', 'block')
            merged.enable_slash_command_analysis = getattr(tenant_config, 'enable_slash_command_analysis', True)
            # Custom prompts (if set)
            if tenant_config.prompt_injection_prompt:
                merged.prompt_injection_prompt = tenant_config.prompt_injection_prompt
            if tenant_config.agent_takeover_prompt:
                merged.agent_takeover_prompt = tenant_config.agent_takeover_prompt
            if tenant_config.poisoning_prompt:
                merged.poisoning_prompt = tenant_config.poisoning_prompt
            if tenant_config.shell_intent_prompt:
                merged.shell_intent_prompt = tenant_config.shell_intent_prompt

        # Override with agent config if present (only non-None values)
        if agent_override:
            if agent_override.is_enabled is not None:
                merged.is_enabled = agent_override.is_enabled
            if agent_override.enable_prompt_analysis is not None:
                merged.enable_prompt_analysis = agent_override.enable_prompt_analysis
            if agent_override.enable_tool_analysis is not None:
                merged.enable_tool_analysis = agent_override.enable_tool_analysis
            if agent_override.enable_shell_analysis is not None:
                merged.enable_shell_analysis = agent_override.enable_shell_analysis
            if agent_override.aggressiveness_level is not None:
                merged.aggressiveness_level = agent_override.aggressiveness_level

        return merged

    # =========================================================================
    # Analysis Methods
    # =========================================================================

    async def analyze_prompt(
        self,
        prompt: str,
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        context: Optional[Dict] = None,
        source: Optional[str] = None,
        message_id: Optional[str] = None,
        skill_context: Optional[str] = None,
        skill_type: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Analyze user prompt for security threats.

        CRITICAL: Only analyzes external/user content. Internal sources are whitelisted.

        Args:
            prompt: The prompt text to analyze
            agent_id: Agent ID for agent-specific config
            sender_key: User identifier for logging
            context: Additional context (unused, for future)
            source: Source of the prompt - if in INTERNAL_SOURCES, skipped
            message_id: Message ID for logging
            skill_context: Formatted skill context string to inject into analysis.
                          Provides context about expected behaviors for enabled skills.

        Returns:
            SentinelAnalysisResult with threat detection results
        """
        start_time = time.time()

        # Check if source is internal (whitelisted)
        if source and source in self.INTERNAL_SOURCES:
            self.logger.debug(f"Skipping analysis for internal source: {source}")
            return SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason=None,
                action="allowed",
                detection_type="none",
                analysis_type="prompt",
                cached=False,
                response_time_ms=int((time.time() - start_time) * 1000),
            )

        # Get effective configuration (skill_type enables skill-level profile resolution)
        config = self.get_effective_config(agent_id, skill_type=skill_type)

        # Check if Sentinel is enabled
        if not config.is_enabled:
            return self._create_allowed_result("prompt", "sentinel_disabled", start_time)

        # Phase 20 Enhancement: Check if slash command analysis is disabled
        # If prompt starts with "/" and enable_slash_command_analysis is False, skip analysis
        enable_slash_analysis = config.enable_slash_command_analysis
        if not enable_slash_analysis and prompt.strip().startswith("/"):
            self.logger.debug("Skipping Sentinel analysis for slash command (toggle disabled)")
            return self._create_allowed_result("prompt", "slash_command_bypass", start_time)

        # Check if prompt analysis is enabled
        if not config.enable_prompt_analysis:
            return self._create_allowed_result("prompt", "prompt_analysis_disabled", start_time)

        # Check aggressiveness level
        if config.aggressiveness_level <= 0:
            return self._create_allowed_result("prompt", "aggressiveness_off", start_time)

        # Truncate prompt for analysis
        truncated_prompt = prompt[:config.max_input_chars]

        # Check if any detection types are enabled
        # If none are enabled, skip analysis entirely
        has_enabled_detection = any(
            config.is_detection_enabled(dt)
            for dt in get_prompt_detection_types()
        )
        if not has_enabled_detection:
            return self._create_allowed_result("prompt", "no_detection_types", start_time)

        # Use unified classification for single-call detection
        # This replaces the multi-call approach with a single LLM call that
        # detects AND classifies threats, reducing token consumption by 67-75%
        return await self._analyze_unified(
            input_content=truncated_prompt,
            analysis_type="prompt",
            config=config,
            sender_key=sender_key,
            message_id=message_id,
            agent_id=agent_id,
            start_time=start_time,
            skill_context=skill_context,
        )

    async def analyze_tool_arguments(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Analyze tool call arguments for malicious patterns.

        Args:
            tool_name: Name of the tool being called
            arguments: Arguments passed to the tool
            agent_id: Agent ID for agent-specific config
            sender_key: User identifier for logging

        Returns:
            SentinelAnalysisResult with threat detection results
        """
        start_time = time.time()

        # Get effective configuration
        config = self.get_effective_config(agent_id)

        # Check if Sentinel is enabled
        if not config.is_enabled or not config.enable_tool_analysis:
            return self._create_allowed_result("tool", "tool_analysis_disabled", start_time)

        if config.aggressiveness_level <= 0:
            return self._create_allowed_result("tool", "aggressiveness_off", start_time)

        # Convert arguments to string for analysis
        args_str = f"Tool: {tool_name}\nArguments: {json.dumps(arguments, default=str)}"
        truncated_args = args_str[:config.max_input_chars]
        input_hash = self._hash_input(truncated_args)

        # Use prompt injection detection on tool arguments
        if config.is_detection_enabled("prompt_injection"):
            result = await self._analyze_single(
                input_content=truncated_args,
                input_hash=input_hash,
                analysis_type="tool",
                detection_type="prompt_injection",
                config=config,
                sender_key=sender_key,
                message_id=None,
                agent_id=agent_id,
                start_time=start_time,
            )

            if result.is_threat_detected:
                return result

        return self._create_allowed_result("tool", "no_threat", start_time)

    async def analyze_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        conversation_context: Optional[List[Dict]] = None,
        skill_context: Optional[str] = None,
        skill_type: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Analyze a tool call for security threats before execution.

        Skills-as-Tools (Phase 3): Comprehensive tool call analysis.

        This method performs multi-layered security checks:
        1. Tool-specific pattern matching (e.g., shell command patterns)
        2. Prompt injection detection in arguments
        3. Behavioral pattern analysis (optional)

        Args:
            tool_name: Name of the tool being called (e.g., "run_shell_command", "search_flights")
            arguments: Arguments passed to the tool
            agent_id: Agent ID for agent-specific config
            sender_key: User identifier for logging
            conversation_context: Optional recent conversation for behavioral analysis
            skill_context: Optional skill security context (from get_sentinel_context())

        Returns:
            SentinelAnalysisResult with threat detection results
        """
        start_time = time.time()

        # Get effective configuration (skill_type enables skill-level profile resolution)
        config = self.get_effective_config(agent_id, skill_type=skill_type)

        # Check if Sentinel is enabled
        if not config.is_enabled or not config.enable_tool_analysis:
            return self._create_allowed_result("tool", "tool_analysis_disabled", start_time)

        if config.aggressiveness_level <= 0:
            return self._create_allowed_result("tool", "aggressiveness_off", start_time)

        # =====================================================================
        # Tool-Specific Analysis
        # =====================================================================

        # Shell command tool requires special handling
        if tool_name == "run_shell_command":
            script = arguments.get("script", "")
            if script:
                # Use existing shell command analysis
                shell_result = await self.analyze_shell_command(
                    command=script,
                    agent_id=agent_id,
                    sender_key=sender_key,
                    skill_type=skill_type or "shell",
                )
                if shell_result.is_threat_detected:
                    self.logger.warning(
                        f"Tool call blocked: {tool_name} - Shell threat detected",
                        extra={"tool": tool_name, "threat": shell_result.threat_reason}
                    )
                    return shell_result

        # Browser automation tools - check for sensitive URL patterns
        if tool_name in ["browser_navigate", "scrape_webpage"]:
            url = arguments.get("url", "")
            if url:
                sensitive_patterns = [
                    "file://",  # Local file access
                    "localhost",  # Internal services
                    "127.0.0.1",
                    "169.254.",  # AWS metadata
                    "metadata.google",  # GCP metadata
                ]
                for pattern in sensitive_patterns:
                    if pattern in url.lower():
                        return SentinelAnalysisResult(
                            is_threat_detected=True,
                            threat_score=0.9,
                            threat_reason=f"Attempt to access sensitive URL pattern: {pattern}",
                            action="blocked",
                            detection_type="ssrf_attempt",
                            analysis_type="tool",
                            response_time_ms=int((time.time() - start_time) * 1000),
                        )

        # =====================================================================
        # General Prompt Injection Analysis
        # =====================================================================

        # Phase 20 Enhancement: Extract target_domain from URL arguments for exception matching
        target_domain = None
        url = arguments.get("url", "") or arguments.get("target_url", "") or arguments.get("endpoint", "")
        if url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(url)
                target_domain = parsed.netloc or None
            except Exception:
                pass

        # Convert arguments to string for analysis
        args_str = f"Tool: {tool_name}\nArguments: {json.dumps(arguments, default=str)}"
        truncated_args = args_str[:config.max_input_chars]
        input_hash = self._hash_input(truncated_args)

        # Detect prompt injection in tool arguments
        if config.is_detection_enabled("prompt_injection"):
            result = await self._analyze_single(
                input_content=truncated_args,
                input_hash=input_hash,
                analysis_type="tool",
                detection_type="prompt_injection",
                config=config,
                sender_key=sender_key,
                message_id=None,
                agent_id=agent_id,
                start_time=start_time,
                skill_context=skill_context,
                tool_name=tool_name,
                target_domain=target_domain,
            )

            if result.is_threat_detected:
                self.logger.warning(
                    f"Tool call blocked: {tool_name} - Prompt injection detected",
                    extra={"tool": tool_name, "threat": result.threat_reason}
                )
                return result

        # =====================================================================
        # Log successful analysis
        # =====================================================================

        self.logger.debug(
            f"Tool call allowed: {tool_name}",
            extra={"tool": tool_name, "agent_id": agent_id}
        )

        return self._create_allowed_result("tool", "no_threat", start_time)

    async def analyze_shell_command(
        self,
        command: str,
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        pattern_result: Optional[Any] = None,
        skill_type: Optional[str] = None,
        skill_context: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Analyze shell command for malicious intent.

        Complements existing ShellSecurityService pattern matching with
        LLM-based semantic analysis.

        Args:
            command: Shell command to analyze
            agent_id: Agent ID for agent-specific config
            sender_key: User identifier for logging
            pattern_result: Result from ShellSecurityService (for context)
            skill_type: Skill type for skill-level profile resolution (defaults to "shell")
            skill_context: Formatted skill context string to inject into analysis

        Returns:
            SentinelAnalysisResult with threat detection results
        """
        start_time = time.time()

        # Get effective configuration (default to "shell" skill for shell commands)
        config = self.get_effective_config(agent_id, skill_type=skill_type or "shell")

        # Check if Sentinel is enabled
        if not config.is_enabled or not config.enable_shell_analysis:
            return self._create_allowed_result("shell", "shell_analysis_disabled", start_time)

        if config.aggressiveness_level <= 0:
            return self._create_allowed_result("shell", "aggressiveness_off", start_time)

        if not config.is_detection_enabled("shell_malicious"):
            return self._create_allowed_result("shell", "shell_intent_disabled", start_time)

        # Truncate command for analysis
        truncated_command = command[:config.max_input_chars]
        input_hash = self._hash_input(truncated_command)

        # Analyze for malicious shell intent
        # Phase 20 Enhancement: Pass tool_name for exception matching
        result = await self._analyze_single(
            input_content=truncated_command,
            input_hash=input_hash,
            analysis_type="shell",
            detection_type="shell_malicious",
            config=config,
            sender_key=sender_key,
            message_id=None,
            agent_id=agent_id,
            start_time=start_time,
            skill_context=skill_context,
            tool_name="run_shell_command",  # For exception matching
        )

        return result

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _analyze_single(
        self,
        input_content: str,
        input_hash: str,
        analysis_type: str,
        detection_type: str,
        config: SentinelEffectiveConfig,
        sender_key: Optional[str],
        message_id: Optional[str],
        agent_id: Optional[int],
        start_time: float,
        skill_context: Optional[str] = None,
        tool_name: Optional[str] = None,
        target_domain: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Perform single detection type analysis.

        Checks detection mode, exceptions, cache, then calls LLM if needed.

        Args:
            skill_context: Optional skill context string to prepend to analysis prompt.
                          Provides context about expected behaviors for enabled skills.
            tool_name: Optional tool name for tool-type exception matching.
            target_domain: Optional domain extracted from URLs for domain-type exceptions.
        """
        # Check detection mode
        detection_mode = config.detection_mode
        if detection_mode == 'off':
            self.logger.debug(f"Detection mode is 'off', skipping {detection_type} analysis")
            return self._create_allowed_result(analysis_type, "detection_off", start_time)

        # Phase 20 Enhancement: Check exceptions BEFORE LLM call
        from services.sentinel_exceptions_service import SentinelExceptionsService
        exc_service = SentinelExceptionsService(self.db, self.tenant_id)
        exception = exc_service.check_exception(
            content=input_content,
            detection_type=detection_type,
            analysis_type=analysis_type,
            agent_id=agent_id,
            tool_name=tool_name,
            target_domain=target_domain,
        )

        if exception:
            # Skip LLM analysis - exception matched
            result = SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason=None,
                action="allowed",
                detection_type=detection_type,
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=int((time.time() - start_time) * 1000),
            )

            # Log with exception info (if logging enabled)
            if config.log_all_analyses:
                self._log_analysis(
                    analysis_type=analysis_type,
                    detection_type=detection_type,
                    input_content=input_content[:500],
                    input_hash=input_hash,
                    result=result,
                    sender_key=sender_key,
                    message_id=message_id,
                    agent_id=agent_id,
                    llm_provider=None,
                    llm_model=None,
                    response_time_ms=result.response_time_ms,
                    exception_applied=True,
                    exception_id=exception.id,
                    exception_name=exception.name,
                    detection_mode_used=detection_mode,
                )

            return result

        # Check cache
        cached_result = self._check_cache(
            input_hash=input_hash,
            analysis_type=analysis_type,
            detection_type=detection_type,
            aggressiveness=config.aggressiveness_level,
        )

        if cached_result:
            self.logger.debug(f"Cache hit for {detection_type}")
            cached_result.response_time_ms = int((time.time() - start_time) * 1000)

            # Phase 20 Enhancement: Apply detection_mode to cached results too
            if cached_result.is_threat_detected:
                if detection_mode == "detect_only":
                    self.logger.info(
                        f"Detect-only mode (cached): Threat detected in {detection_type} but allowing. "
                        f"Reason: {cached_result.threat_reason}"
                    )
                    cached_result.action = "allowed"
                elif detection_mode == "warn_only":
                    self.logger.info(
                        f"Warn-only mode (cached): Threat detected in {detection_type} but allowing with warning. "
                        f"Reason: {cached_result.threat_reason}"
                    )
                    cached_result.action = "warned"

            return cached_result

        # Get analysis prompt
        custom_prompt = self._get_custom_prompt(detection_type, config)
        if custom_prompt:
            analysis_prompt = custom_prompt.format(input=input_content)
        else:
            analysis_prompt = get_default_prompt(detection_type, config.aggressiveness_level)
            if analysis_prompt:
                analysis_prompt = analysis_prompt.format(input=input_content)

        if not analysis_prompt:
            self.logger.warning(f"No prompt available for {detection_type}")
            return self._create_allowed_result(analysis_type, detection_type, start_time)

        # Inject skill context if provided (Phase 20: Skill-aware Sentinel)
        # This gives the LLM context about expected behaviors for enabled skills
        if skill_context:
            analysis_prompt = f"{skill_context}\n\n{analysis_prompt}"
            self.logger.debug(f"Injected skill context into {detection_type} analysis")

        # Call LLM
        try:
            llm_result = await self._call_llm(
                system_prompt="You are a security analyst. Analyze the content for threats. Respond only with valid JSON.",
                user_content=analysis_prompt,
                config=config,
            )
        except Exception as e:
            self.logger.error(f"LLM call failed: {e}", exc_info=True)
            # On LLM failure, allow the content (fail open)
            return self._create_allowed_result(analysis_type, detection_type, start_time)

        # Parse LLM response
        response_time_ms = int((time.time() - start_time) * 1000)
        result = self._parse_llm_response(
            llm_result,
            analysis_type,
            detection_type,
            config,
            response_time_ms,
        )

        # Phase 20 Enhancement: Handle non-blocking detection modes
        # If threat detected but mode is detect_only or warn_only, override action
        if result.is_threat_detected and detection_mode == "detect_only":
            self.logger.info(
                f"Detect-only mode: Threat detected in {detection_type} but allowing. "
                f"Reason: {result.threat_reason}"
            )
            result.action = "allowed"
        elif result.is_threat_detected and detection_mode == "warn_only":
            self.logger.info(
                f"Warn-only mode: Threat detected in {detection_type} but allowing with warning. "
                f"Reason: {result.threat_reason}"
            )
            result.action = "warned"

        # Cache result
        self._save_cache(
            input_hash=input_hash,
            analysis_type=analysis_type,
            detection_type=detection_type,
            aggressiveness=config.aggressiveness_level,
            result=result,
            ttl=config.cache_ttl_seconds,
        )

        # Log analysis
        if result.is_threat_detected or config.log_all_analyses:
            self._log_analysis(
                analysis_type=analysis_type,
                detection_type=detection_type,
                input_content=input_content[:500],  # Truncate for logging
                input_hash=input_hash,
                result=result,
                sender_key=sender_key,
                message_id=message_id,
                agent_id=agent_id,
                llm_provider=config.llm_provider,
                llm_model=config.llm_model,
                response_time_ms=response_time_ms,
                detection_mode_used=detection_mode,
            )

        return result

    async def _call_llm(
        self,
        system_prompt: str,
        user_content: str,
        config: SentinelEffectiveConfig,
    ) -> Dict[str, Any]:
        """
        Call LLM for security analysis.

        Uses AIClient from agent module.
        """
        from agent.ai_client import AIClient

        client = AIClient(
            provider=config.llm_provider,
            model_name=config.llm_model,
            db=self.db,
            temperature=config.llm_temperature,
            max_tokens=config.llm_max_tokens,
            tenant_id=self.tenant_id,
        )

        result = await client.generate(
            system_prompt=system_prompt,
            user_message=user_content,
            operation_type="sentinel_analysis",
        )

        return result

    def _parse_llm_response(
        self,
        llm_result: Dict[str, Any],
        analysis_type: str,
        detection_type: str,
        config: SentinelEffectiveConfig,
        response_time_ms: int,
    ) -> SentinelAnalysisResult:
        """Parse LLM response into SentinelAnalysisResult."""
        answer = llm_result.get("answer", "")

        if not answer:
            # LLM returned empty response, allow content
            return SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason="LLM returned empty response",
                action="allowed",
                detection_type=detection_type,
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

        try:
            # Try to parse JSON from response
            # Handle potential markdown code blocks
            if "```json" in answer:
                answer = answer.split("```json")[1].split("```")[0].strip()
            elif "```" in answer:
                answer = answer.split("```")[1].split("```")[0].strip()

            parsed = json.loads(answer)

            is_threat = parsed.get("threat", False)
            score = float(parsed.get("score", 0.0))
            reason = parsed.get("reason", "")

            # Determine action based on detection_mode
            action = "allowed"
            if is_threat:
                mode = config.detection_mode
                if mode == 'block':
                    action = "blocked"
                elif mode == 'warn_only':
                    action = "warned"
                else:
                    action = "allowed"

            return SentinelAnalysisResult(
                is_threat_detected=is_threat,
                threat_score=score,
                threat_reason=reason if is_threat else None,
                action=action,
                detection_type=detection_type,
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(f"Failed to parse LLM response: {e}, response: {answer[:200]}")
            # On parse failure, allow content (fail open)
            return SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason=f"Failed to parse LLM response: {str(e)}",
                action="allowed",
                detection_type=detection_type,
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

    def _get_custom_prompt(self, detection_type: str, config: SentinelEffectiveConfig) -> Optional[str]:
        """Get custom prompt from config if set."""
        return config.get_custom_prompt(detection_type)

    async def _analyze_unified(
        self,
        input_content: str,
        analysis_type: str,
        config: SentinelEffectiveConfig,
        sender_key: Optional[str],
        message_id: Optional[str],
        agent_id: Optional[int],
        start_time: float,
        skill_context: Optional[str] = None,
    ) -> SentinelAnalysisResult:
        """
        Perform unified threat classification with a single LLM call.

        This replaces the multi-call approach with a single unified prompt that
        detects AND classifies threats, reducing token consumption by 67-75%.

        Returns the most appropriate threat classification or 'none' if safe.
        """
        from .sentinel_detections import get_unified_prompt

        # Check detection mode
        detection_mode = config.detection_mode
        if detection_mode == 'off':
            self.logger.debug("Detection mode is 'off', skipping unified analysis")
            return self._create_allowed_result(analysis_type, "detection_off", start_time)

        input_hash = self._hash_input(input_content)

        # Check cache (using 'unified' as detection_type for cache key)
        cached_result = self._check_cache(
            input_hash=input_hash,
            analysis_type=analysis_type,
            detection_type="unified",
            aggressiveness=config.aggressiveness_level,
        )

        if cached_result:
            self.logger.debug("Cache hit for unified analysis")
            cached_result.response_time_ms = int((time.time() - start_time) * 1000)
            if cached_result.is_threat_detected:
                if detection_mode == "detect_only":
                    cached_result.action = "allowed"
                elif detection_mode == "warn_only":
                    cached_result.action = "warned"
            return cached_result

        # Get unified classification prompt
        analysis_prompt = get_unified_prompt(config.aggressiveness_level)
        if not analysis_prompt:
            return self._create_allowed_result(analysis_type, "no_prompt", start_time)

        analysis_prompt = analysis_prompt.format(input=input_content)

        # Inject skill context if provided
        if skill_context:
            analysis_prompt = f"{skill_context}\n\n{analysis_prompt}"
            self.logger.debug("Injected skill context into unified analysis")

        # Call LLM (single call)
        try:
            llm_result = await self._call_llm(
                system_prompt="You are a security analyst. Classify the threat type. Respond only with valid JSON.",
                user_content=analysis_prompt,
                config=config,
            )
        except Exception as e:
            self.logger.error(f"Unified LLM call failed: {e}", exc_info=True)
            return self._create_allowed_result(analysis_type, "llm_error", start_time)

        # Parse unified response
        response_time_ms = int((time.time() - start_time) * 1000)
        result = self._parse_unified_response(
            llm_result,
            analysis_type,
            config,
            response_time_ms,
        )

        # Handle non-blocking detection modes
        if result.is_threat_detected and detection_mode == "detect_only":
            self.logger.info(
                f"Detect-only mode: {result.detection_type} threat detected but allowing. "
                f"Reason: {result.threat_reason}"
            )
            result.action = "allowed"
        elif result.is_threat_detected and detection_mode == "warn_only":
            self.logger.info(
                f"Warn-only mode: {result.detection_type} threat detected but allowing with warning. "
                f"Reason: {result.threat_reason}"
            )
            result.action = "warned"

        # Cache result
        self._save_cache(
            input_hash=input_hash,
            analysis_type=analysis_type,
            detection_type="unified",
            aggressiveness=config.aggressiveness_level,
            result=result,
            ttl=config.cache_ttl_seconds,
        )

        # Log if threat detected or log_all enabled
        if result.is_threat_detected or config.log_all_analyses:
            self._log_analysis(
                analysis_type=analysis_type,
                detection_type=result.detection_type,
                input_content=input_content[:500],
                input_hash=input_hash,
                result=result,
                sender_key=sender_key,
                message_id=message_id,
                agent_id=agent_id,
                llm_provider=config.llm_provider,
                llm_model=config.llm_model,
                response_time_ms=response_time_ms,
                detection_mode_used=detection_mode,
            )

        return result

    def _parse_unified_response(
        self,
        llm_result: Dict[str, Any],
        analysis_type: str,
        config: SentinelEffectiveConfig,
        response_time_ms: int,
    ) -> SentinelAnalysisResult:
        """
        Parse unified classification LLM response.

        The unified response format is:
        {"threat_type": "none|prompt_injection|agent_takeover|poisoning|shell_malicious", "score": 0.0-1.0, "reason": "..."}
        """
        answer = llm_result.get("answer", "")

        if not answer:
            return SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason="LLM returned empty response",
                action="allowed",
                detection_type="none",
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

        try:
            # Handle markdown code blocks
            if "```json" in answer:
                answer = answer.split("```json")[1].split("```")[0].strip()
            elif "```" in answer:
                answer = answer.split("```")[1].split("```")[0].strip()

            parsed = json.loads(answer)

            threat_type = parsed.get("threat_type", "none").lower()
            score = float(parsed.get("score", 0.0))
            reason = parsed.get("reason", "")

            # Validate threat_type
            valid_types = ["none", "prompt_injection", "agent_takeover", "poisoning", "shell_malicious", "memory_poisoning"]
            if threat_type not in valid_types:
                self.logger.warning(f"Invalid threat_type '{threat_type}', defaulting to 'none'")
                threat_type = "none"

            is_threat = threat_type != "none" and score > 0.3

            action = "allowed"
            if is_threat:
                mode = getattr(config, 'detection_mode', 'block')
                if mode == 'block':
                    action = "blocked"
                elif mode == 'warn_only':
                    action = "warned"
                else:
                    action = "allowed"

            return SentinelAnalysisResult(
                is_threat_detected=is_threat,
                threat_score=score,
                threat_reason=reason if is_threat else None,
                action=action,
                detection_type=threat_type if is_threat else "none",
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(f"Failed to parse unified response: {e}, response: {answer[:200]}")
            return SentinelAnalysisResult(
                is_threat_detected=False,
                threat_score=0.0,
                threat_reason=f"Parse error: {str(e)}",
                action="allowed",
                detection_type="none",
                analysis_type=analysis_type,
                cached=False,
                response_time_ms=response_time_ms,
            )

    async def send_threat_notification(
        self,
        result: SentinelAnalysisResult,
        config: SentinelEffectiveConfig,
        sender_key: Optional[str] = None,
        agent_id: Optional[int] = None,
        mcp_api_url: Optional[str] = None,
        mcp_api_secret: Optional[str] = None,
    ) -> bool:
        """
        Send notification for detected threat to the user who sent the message.

        Sends a WhatsApp notification directly to the user (sender_key) when their
        message is blocked or detected as a threat.

        Args:
            result: The threat analysis result
            config: Sentinel configuration with notification settings
            sender_key: The WhatsApp JID of the user who sent the message (recipient of notification)
            agent_id: The agent that received the message
            mcp_api_url: MCP API URL for sending WhatsApp messages
            mcp_api_secret: MCP API secret for authentication

        Returns:
            True if notification was sent successfully
        """
        # Check if notifications are enabled
        if not config.enable_notifications:
            self.logger.debug("Notifications disabled, skipping")
            return False

        # Check action-specific settings
        if result.action == "blocked" and not config.notification_on_block:
            self.logger.debug("Notification on block disabled, skipping")
            return False
        if result.action in ("allowed", "warned") and not config.notification_on_detect:
            self.logger.debug("Notification on detect/warn disabled, skipping")
            return False

        # The recipient is the sender (the user who sent the blocked message)
        # sender_key is already in WhatsApp JID format (e.g., "5511999999999@s.whatsapp.net")
        if not sender_key:
            self.logger.debug("No sender_key provided, skipping notification")
            return False

        recipient = sender_key

        # Build message from template
        template = config.notification_message_template
        if not template:
            # Default template - user-friendly message explaining why their message was blocked
            template = (
                "🛡️ Security Notice\n\n"
                "Your message was flagged by our security system.\n"
                "Action: {action}\n"
                "Reason: {reason}\n\n"
                "If you believe this is an error, please contact support."
            )

        try:
            message = template.format(
                detection_type=result.detection_type,
                action=result.action,
                sender_key=sender_key or "unknown",
                reason=result.threat_reason or "No reason provided",
                score=f"{result.threat_score:.0%}",
                agent_id=agent_id or "N/A",
            )
        except KeyError as e:
            self.logger.warning(f"Invalid notification template variable: {e}")
            # Fallback to simple message
            message = f"🛡️ Security Notice: Your message was {result.action} for security reasons."

        # Send via MCPSender
        if mcp_api_url:
            try:
                from mcp_sender import MCPSender
                sender = MCPSender(mcp_api_url)
                success, _ = await sender.send_message(
                    recipient,
                    message,
                    api_secret=mcp_api_secret
                )
                if success:
                    self.logger.info(f"Sentinel notification sent to user")
                else:
                    self.logger.warning(f"Failed to send Sentinel notification to user")
                return success
            except Exception as e:
                self.logger.error(f"Failed to send Sentinel notification: {e}")
                return False

        self.logger.debug("No MCP API URL provided, cannot send notification")
        return False

    def _create_allowed_result(
        self,
        analysis_type: str,
        reason: str,
        start_time: float,
    ) -> SentinelAnalysisResult:
        """Create an allowed result (no threat detected)."""
        return SentinelAnalysisResult(
            is_threat_detected=False,
            threat_score=0.0,
            threat_reason=None,
            action="allowed",
            detection_type=reason,
            analysis_type=analysis_type,
            cached=False,
            response_time_ms=int((time.time() - start_time) * 1000),
        )

    def _hash_input(self, content: str) -> str:
        """Generate SHA-256 hash of input content."""
        return hashlib.sha256(content.encode()).hexdigest()

    # =========================================================================
    # Cache Methods
    # =========================================================================

    def _check_cache(
        self,
        input_hash: str,
        analysis_type: str,
        detection_type: str,
        aggressiveness: int,
    ) -> Optional[SentinelAnalysisResult]:
        """Check cache for existing analysis result."""
        try:
            cached = self.db.query(SentinelAnalysisCache).filter(
                SentinelAnalysisCache.tenant_id == (self.tenant_id or "system"),
                SentinelAnalysisCache.input_hash == input_hash,
                SentinelAnalysisCache.analysis_type == analysis_type,
                SentinelAnalysisCache.detection_type == detection_type,
                SentinelAnalysisCache.aggressiveness_level == aggressiveness,
                SentinelAnalysisCache.expires_at > datetime.utcnow(),
            ).first()

            if cached:
                return SentinelAnalysisResult(
                    is_threat_detected=cached.is_threat_detected,
                    threat_score=cached.threat_score or 0.0,
                    threat_reason=cached.threat_reason,
                    action="blocked" if cached.is_threat_detected else "allowed",
                    detection_type=detection_type,
                    analysis_type=analysis_type,
                    cached=True,
                    response_time_ms=0,
                )
        except Exception as e:
            self.logger.warning(f"Cache check failed: {e}")

        return None

    def _save_cache(
        self,
        input_hash: str,
        analysis_type: str,
        detection_type: str,
        aggressiveness: int,
        result: SentinelAnalysisResult,
        ttl: int,
    ) -> None:
        """Save analysis result to cache."""
        try:
            # Delete existing entry if any
            self.db.query(SentinelAnalysisCache).filter(
                SentinelAnalysisCache.tenant_id == (self.tenant_id or "system"),
                SentinelAnalysisCache.input_hash == input_hash,
                SentinelAnalysisCache.analysis_type == analysis_type,
                SentinelAnalysisCache.detection_type == detection_type,
                SentinelAnalysisCache.aggressiveness_level == aggressiveness,
            ).delete()

            # Create new cache entry
            cache_entry = SentinelAnalysisCache(
                tenant_id=self.tenant_id or "system",
                input_hash=input_hash,
                analysis_type=analysis_type,
                detection_type=detection_type,
                aggressiveness_level=aggressiveness,
                is_threat_detected=result.is_threat_detected,
                threat_score=result.threat_score,
                threat_reason=result.threat_reason,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl),
            )
            self.db.add(cache_entry)
            self.db.commit()
        except Exception as e:
            self.logger.warning(f"Cache save failed: {e}")
            self.db.rollback()

    # =========================================================================
    # Logging Methods
    # =========================================================================

    def _log_analysis(
        self,
        analysis_type: str,
        detection_type: str,
        input_content: str,
        input_hash: str,
        result: SentinelAnalysisResult,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None,
        agent_id: Optional[int] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        response_time_ms: int = 0,
        exception_applied: bool = False,
        exception_id: Optional[int] = None,
        exception_name: Optional[str] = None,
        detection_mode_used: Optional[str] = None,
    ) -> SentinelAnalysisLog:
        """Log analysis to audit trail for Watcher Security tab."""
        try:
            log_entry = SentinelAnalysisLog(
                tenant_id=self.tenant_id or "system",
                agent_id=agent_id,
                analysis_type=analysis_type,
                detection_type=detection_type,
                input_content=input_content,
                input_hash=input_hash,
                is_threat_detected=result.is_threat_detected,
                threat_score=result.threat_score,
                threat_reason=result.threat_reason,
                action_taken=result.action,
                llm_provider=llm_provider,
                llm_model=llm_model,
                llm_response_time_ms=response_time_ms,
                sender_key=sender_key,
                message_id=message_id,
                # Phase 20 Enhancement: Exception tracking
                exception_applied=exception_applied,
                exception_id=exception_id,
                exception_name=exception_name,
                detection_mode_used=detection_mode_used,
            )
            self.db.add(log_entry)
            self.db.commit()
            return log_entry
        except Exception as e:
            self.logger.error(f"Failed to log analysis: {e}")
            self.db.rollback()
            return None

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def get_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        threat_only: bool = False,
        detection_type: Optional[str] = None,
        analysis_type: Optional[str] = None,
        agent_id: Optional[int] = None,
    ) -> List[SentinelAnalysisLog]:
        """Get analysis logs for Watcher Security tab."""
        query = self.db.query(SentinelAnalysisLog).filter(
            SentinelAnalysisLog.tenant_id == (self.tenant_id or "system")
        )

        if threat_only:
            query = query.filter(SentinelAnalysisLog.is_threat_detected == True)

        if detection_type:
            query = query.filter(SentinelAnalysisLog.detection_type == detection_type)

        if analysis_type:
            query = query.filter(SentinelAnalysisLog.analysis_type == analysis_type)

        if agent_id:
            query = query.filter(SentinelAnalysisLog.agent_id == agent_id)

        return query.order_by(
            SentinelAnalysisLog.created_at.desc()
        ).offset(offset).limit(limit).all()

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get detection statistics for dashboard."""
        from sqlalchemy import func

        since = datetime.utcnow() - timedelta(days=days)

        query = self.db.query(SentinelAnalysisLog).filter(
            SentinelAnalysisLog.tenant_id == (self.tenant_id or "system"),
            SentinelAnalysisLog.created_at >= since,
        )

        total = query.count()
        threats = query.filter(SentinelAnalysisLog.is_threat_detected == True).count()
        blocked = query.filter(SentinelAnalysisLog.action_taken == "blocked").count()

        # Group by detection type
        by_type = {}
        type_counts = self.db.query(
            SentinelAnalysisLog.detection_type,
            func.count(SentinelAnalysisLog.id),
        ).filter(
            SentinelAnalysisLog.tenant_id == (self.tenant_id or "system"),
            SentinelAnalysisLog.created_at >= since,
            SentinelAnalysisLog.is_threat_detected == True,
        ).group_by(SentinelAnalysisLog.detection_type).all()

        for dtype, count in type_counts:
            by_type[dtype] = count

        return {
            "total_analyses": total,
            "threats_detected": threats,
            "threats_blocked": blocked,
            "detection_rate": round(threats / total * 100, 2) if total > 0 else 0,
            "by_detection_type": by_type,
            "period_days": days,
        }

    def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries. Returns count of deleted entries."""
        try:
            deleted = self.db.query(SentinelAnalysisCache).filter(
                SentinelAnalysisCache.expires_at < datetime.utcnow()
            ).delete()
            self.db.commit()
            return deleted
        except Exception as e:
            self.logger.error(f"Cache cleanup failed: {e}")
            self.db.rollback()
            return 0

    def cleanup_poisoned_memory(self, agent_id: Optional[int] = None) -> Dict[str, int]:
        """
        Phase 21: Remove previously blocked messages from agent memory to prevent poisoning.

        This cleans up messages that were stored BEFORE the pre-memory Sentinel check
        was implemented. It finds all blocked messages from SentinelAnalysisLog and
        removes them from:
        - Memory table (PostgreSQL)
        - FTS5 index (full-text search)
        - ChromaDB would need separate handling based on collection structure

        Args:
            agent_id: Optional agent ID to limit cleanup to specific agent

        Returns:
            Dict with cleanup statistics (memory_deleted, fts_deleted)
        """
        from models import Memory

        stats = {"memory_deleted": 0, "fts_deleted": 0, "blocked_found": 0}

        try:
            # Get all blocked message IDs from Sentinel logs for this tenant
            query = self.db.query(SentinelAnalysisLog).filter(
                SentinelAnalysisLog.tenant_id == (self.tenant_id or "system"),
                SentinelAnalysisLog.action_taken == "blocked",
                SentinelAnalysisLog.message_id.isnot(None)
            )
            if agent_id:
                query = query.filter(SentinelAnalysisLog.agent_id == agent_id)

            blocked_logs = query.all()
            blocked_message_ids = [log.message_id for log in blocked_logs if log.message_id]
            stats["blocked_found"] = len(blocked_message_ids)

            if not blocked_message_ids:
                self.logger.info(f"No blocked messages found for cleanup (tenant={self.tenant_id})")
                return stats

            self.logger.info(f"🧹 Found {len(blocked_message_ids)} blocked messages to clean up")

            # 1. Delete from Memory table
            memory_deleted = self.db.query(Memory).filter(
                Memory.message_id.in_(blocked_message_ids)
            ).delete(synchronize_session=False)
            stats["memory_deleted"] = memory_deleted

            # 2. Delete from FTS5 index
            try:
                from sqlalchemy import text
                # SQLite FTS5 doesn't support IN with named parameters well, so we build the query
                # Use individual deletes for safety
                fts_deleted = 0
                for msg_id in blocked_message_ids:
                    result = self.db.execute(text("""
                        DELETE FROM conversation_search_fts
                        WHERE message_id = :message_id
                    """), {"message_id": msg_id})
                    fts_deleted += result.rowcount
                stats["fts_deleted"] = fts_deleted
            except Exception as e:
                self.logger.warning(f"FTS cleanup failed (may not exist): {e}")

            self.db.commit()
            self.logger.info(f"🧹 Memory cleanup completed: {stats}")
            return stats

        except Exception as e:
            self.logger.error(f"Memory cleanup failed: {e}")
            self.db.rollback()
            return stats
