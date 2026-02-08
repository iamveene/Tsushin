"""
Sentinel Effective Config - Phase v1.6.0

Dataclass representing the fully resolved security configuration
for a given scope (tenant/agent/skill). Replaces direct use of
SentinelConfig SQLAlchemy model in analysis methods.

This is the return type of get_effective_config() after v1.6.0.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class SentinelEffectiveConfig:
    """
    Resolved security configuration for analysis.

    Contains all settings needed by SentinelService analysis methods.
    Produced by profile resolution or legacy config conversion.
    """

    # Profile identity
    profile_id: int = -1
    profile_name: str = "Default"
    profile_source: str = "legacy"  # "skill" | "agent" | "tenant" | "system" | "legacy"

    # Global settings
    is_enabled: bool = True
    detection_mode: str = "block"  # 'block' | 'detect_only' | 'off'
    aggressiveness_level: int = 1  # 0=Off, 1=Moderate, 2=Aggressive, 3=Extra

    # Component toggles
    enable_prompt_analysis: bool = True
    enable_tool_analysis: bool = True
    enable_shell_analysis: bool = True
    enable_slash_command_analysis: bool = True

    # LLM configuration
    llm_provider: str = "gemini"
    llm_model: str = "gemini-2.5-flash-lite"
    llm_max_tokens: int = 256
    llm_temperature: float = 0.1

    # Performance
    cache_ttl_seconds: int = 300
    max_input_chars: int = 5000
    timeout_seconds: float = 5.0

    # Actions
    block_on_detection: bool = True
    log_all_analyses: bool = False

    # Notifications
    enable_notifications: bool = True
    notification_on_block: bool = True
    notification_on_detect: bool = False
    notification_recipient: Optional[str] = None
    notification_message_template: Optional[str] = None

    # Per-detection config (resolved from JSON + registry defaults)
    # e.g. {"prompt_injection": {"enabled": True, "custom_prompt": None}, ...}
    detection_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def is_detection_enabled(self, detection_type: str) -> bool:
        """Check if a specific detection type is enabled."""
        return self.detection_config.get(detection_type, {}).get("enabled", True)

    def get_custom_prompt(self, detection_type: str) -> Optional[str]:
        """Get custom prompt for a specific detection type, if set."""
        return self.detection_config.get(detection_type, {}).get("custom_prompt")

    @classmethod
    def from_legacy_config(cls, config) -> "SentinelEffectiveConfig":
        """
        Convert a legacy SentinelConfig model instance to SentinelEffectiveConfig.

        This provides backward compatibility when profile resolution
        is not available or falls back to legacy path.

        Args:
            config: SentinelConfig SQLAlchemy model instance

        Returns:
            SentinelEffectiveConfig with equivalent settings
        """
        # Build detection_config from legacy boolean + prompt columns
        detection_config = {
            "prompt_injection": {
                "enabled": getattr(config, "detect_prompt_injection", True),
                "custom_prompt": getattr(config, "prompt_injection_prompt", None),
            },
            "agent_takeover": {
                "enabled": getattr(config, "detect_agent_takeover", True),
                "custom_prompt": getattr(config, "agent_takeover_prompt", None),
            },
            "poisoning": {
                "enabled": getattr(config, "detect_poisoning", True),
                "custom_prompt": getattr(config, "poisoning_prompt", None),
            },
            "shell_malicious": {
                "enabled": getattr(config, "detect_shell_malicious_intent", True),
                "custom_prompt": getattr(config, "shell_intent_prompt", None),
            },
            "memory_poisoning": {
                "enabled": True,  # No legacy column — default to enabled
                "custom_prompt": None,
            },
        }

        return cls(
            profile_id=-1,
            profile_name="Legacy Config",
            profile_source="legacy",
            # Global settings
            is_enabled=config.is_enabled,
            detection_mode=getattr(config, "detection_mode", "block") or "block",
            aggressiveness_level=config.aggressiveness_level,
            # Component toggles
            enable_prompt_analysis=config.enable_prompt_analysis,
            enable_tool_analysis=config.enable_tool_analysis,
            enable_shell_analysis=config.enable_shell_analysis,
            enable_slash_command_analysis=getattr(config, "enable_slash_command_analysis", True) or True,
            # LLM
            llm_provider=config.llm_provider,
            llm_model=config.llm_model,
            llm_max_tokens=config.llm_max_tokens,
            llm_temperature=config.llm_temperature,
            # Performance
            cache_ttl_seconds=config.cache_ttl_seconds,
            max_input_chars=config.max_input_chars,
            timeout_seconds=config.timeout_seconds,
            # Actions
            block_on_detection=config.block_on_detection,
            log_all_analyses=config.log_all_analyses,
            # Notifications
            enable_notifications=getattr(config, "enable_notifications", True),
            notification_on_block=getattr(config, "notification_on_block", True),
            notification_on_detect=getattr(config, "notification_on_detect", False),
            notification_recipient=getattr(config, "notification_recipient", None),
            notification_message_template=getattr(config, "notification_message_template", None),
            # Detection config
            detection_config=detection_config,
        )
