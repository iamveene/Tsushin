"""
Phase 4.8 Week 3: Adaptive Personality Skill

Automatically learns and adapts to sender's communication style:
- Detects slangs, frequently used words, tone preferences
- Learns internal jokes and their contexts
- Captures linguistic patterns (grammar style, emoji usage)
- Injects learned patterns into agent's personality

This is an optional skill that enhances fact extraction with communication
pattern detection. When enabled, the agent will mirror the sender's style.
"""

import logging
from typing import Dict, Any
from agent.skills.base import BaseSkill, InboundMessage, SkillResult


class AdaptivePersonalitySkill(BaseSkill):
    """
    Adaptive Personality Skill - Learns sender's communication style.

    This skill doesn't process messages directly but signals to the fact
    extraction system to capture communication patterns with higher priority.

    The actual personality adaptation happens through:
    1. Enhanced fact extraction (captures slangs, tone, jokes)
    2. Knowledge service injection (adds style context to prompts)
    3. Agent response generation (uses injected style facts)
    """

    skill_type = "adaptive_personality"
    skill_name = "Adaptive Personality"
    skill_description = (
        "Learn and adapt to sender's communication style including slangs, "
        "frequently used words, internal jokes, and linguistic patterns. "
        "Makes the agent mirror the sender's personality."
    )
    execution_mode = "passive"  # Post-processing hook for fact extraction

    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger(__name__)

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        This skill doesn't directly handle messages.
        It's a passive skill that influences fact extraction behavior.

        Returns False because processing happens in fact_extractor and
        knowledge_service, not as a pre-processing step.
        """
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Not used for adaptive personality (passive skill).

        The actual work happens in:
        - fact_extractor.py: Enhanced to capture communication patterns
        - knowledge_service.py: Injects style facts into agent context
        """
        return SkillResult(
            success=True,
            output="Adaptive personality is a passive skill (no direct processing)",
            metadata={"passive": True}
        )

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Default configuration for adaptive personality.

        Returns:
            Dict with default settings:
            - detection_threshold: How many times a pattern must appear (default: 3)
            - style_categories: Which patterns to capture (default: all)
            - adaptation_strength: How strongly to mirror style (0.0-1.0, default: 0.7)
        """
        return {
            "detection_threshold": 3,  # Pattern must appear 3+ times
            "style_categories": [
                "slangs",
                "frequently_used_words",
                "emoji_patterns",
                "greeting_style",
                "tone_preference"
            ],
            "adaptation_strength": 0.7,  # 70% adaptation, 30% original personality
            "learn_inside_jokes": True,
            "mirror_formality": True  # Match formal vs casual tone
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        JSON schema for configuration validation.

        Returns:
            Schema for UI form generation and validation
        """
        return {
            "type": "object",
            "properties": {
                "detection_threshold": {
                    "type": "integer",
                    "minimum": 2,
                    "maximum": 10,
                    "default": 3,
                    "description": "How many times a pattern must appear to be learned"
                },
                "style_categories": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "slangs",
                            "frequently_used_words",
                            "emoji_patterns",
                            "greeting_style",
                            "tone_preference"
                        ]
                    },
                    "default": [
                        "slangs",
                        "frequently_used_words",
                        "emoji_patterns",
                        "greeting_style",
                        "tone_preference"
                    ],
                    "description": "Which communication patterns to capture"
                },
                "adaptation_strength": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "default": 0.7,
                    "description": "How strongly to mirror sender's style (0=none, 1=full mirroring)"
                },
                "learn_inside_jokes": {
                    "type": "boolean",
                    "default": True,
                    "description": "Learn and use sender's inside jokes and references"
                },
                "mirror_formality": {
                    "type": "boolean",
                    "default": True,
                    "description": "Match sender's formal vs casual communication style"
                }
            },
            "required": []
        }
