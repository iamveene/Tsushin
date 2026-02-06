"""
Centralized Contamination Detection Service

Provides a single source of truth for detecting contaminated AI responses.
Contamination includes identity confusion, role reversal, and bot behavior leakage.

This service is GENERIC and works for ANY agent/conversation flow.
Patterns can be extended via:
- Agent.contamination_patterns (JSON field) for agent-specific patterns
- FlowNode.config_json for flow-specific patterns
- Environment variables for system-wide additions
"""

import re
import os
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class ContaminationDetector:
    """
    Centralized contamination detection with configurable patterns.
    Patterns can be extended via database or config without code changes.
    """

    # Base patterns that apply to ALL agents (identity confusion, role reversal)
    # KEEP PATTERNS MINIMAL - Only block actual system errors, not normal conversation
    # Agent-specific patterns should be in Agent.contamination_patterns field
    BASE_PATTERNS = [
        # Identity prefix leakage (agent including its name as prefix)
        r"^@\w+:\s*",  # Starts with @identifier:
        r"^@[a-z]{3,}:",  # Starts with @identifier: with 3+ chars

        # Explicit role confusion statements (agent claiming to be something it's not)
        r"sua função é atuar como um representante",
        r"your role is to act as",
        r"(minha|sua) função é atuar como",
    ]

    def __init__(self, additional_patterns: List[str] = None, db_session=None, agent_id: int = None):
        """
        Initialize detector with optional additional patterns.

        Args:
            additional_patterns: Extra patterns to check (from config, flow, etc.)
            db_session: Database session for loading agent-specific patterns
            agent_id: Agent ID for loading agent-specific patterns
        """
        self.patterns = self.BASE_PATTERNS.copy()

        # Add patterns from environment (comma-separated)
        env_patterns = os.getenv("CONTAMINATION_PATTERNS_EXTRA", "")
        if env_patterns:
            self.patterns.extend([p.strip() for p in env_patterns.split(",") if p.strip()])

        # Add patterns from agent config (if provided)
        if db_session and agent_id:
            try:
                from models import Agent
                agent = db_session.query(Agent).filter(Agent.id == agent_id).first()
                if agent and hasattr(agent, 'contamination_patterns') and agent.contamination_patterns:
                    import json
                    agent_patterns = agent.contamination_patterns
                    if isinstance(agent_patterns, str):
                        agent_patterns = json.loads(agent_patterns)
                    if isinstance(agent_patterns, list):
                        self.patterns.extend(agent_patterns)
                        logger.debug(f"Loaded {len(agent_patterns)} agent-specific contamination patterns")
            except Exception as e:
                logger.warning(f"Could not load agent contamination patterns: {e}")

        # Add caller-provided patterns
        if additional_patterns:
            self.patterns.extend(additional_patterns)

        logger.debug(f"ContaminationDetector initialized with {len(self.patterns)} patterns")

    def check(self, text: str) -> Optional[str]:
        """
        Check text for contamination patterns.

        Args:
            text: The text to check (typically AI response)

        Returns:
            The matched pattern if contaminated, None otherwise
        """
        if not text:
            return None

        text_lower = text.lower()

        for pattern in self.patterns:
            try:
                if re.search(pattern, text_lower, re.IGNORECASE):
                    logger.warning(f"Contamination detected: pattern '{pattern}' matched in text: '{text[:100]}...'")
                    return pattern
            except re.error as e:
                logger.error(f"Invalid regex pattern '{pattern}': {e}")
                continue

        return None

    def is_contaminated(self, text: str) -> bool:
        """
        Simple boolean check for contamination.

        Args:
            text: The text to check

        Returns:
            True if contaminated, False otherwise
        """
        return self.check(text) is not None

    def clean_response(self, text: str) -> str:
        """
        Remove known prefix contamination patterns from response.
        This is a best-effort cleanup, not a replacement for blocking.

        Args:
            text: The text to clean

        Returns:
            Cleaned text with prefixes removed
        """
        if not text:
            return text

        # Strip @AgentName: prefixes (most common contamination)
        cleaned = re.sub(r"^@?\w+:\s*", "", text, flags=re.IGNORECASE).strip()

        if cleaned != text:
            logger.info(f"Cleaned contamination prefix from response: '{text[:50]}...' -> '{cleaned[:50]}...'")

        return cleaned

    def get_pattern_count(self) -> int:
        """Return the number of active patterns."""
        return len(self.patterns)


# Singleton instance for simple usage
_default_detector = None


def get_contamination_detector(additional_patterns: List[str] = None,
                                db_session=None,
                                agent_id: int = None) -> ContaminationDetector:
    """
    Get a ContaminationDetector instance.

    For simple usage without agent-specific patterns, returns a cached singleton.
    For agent-specific detection, creates a new instance.

    Args:
        additional_patterns: Extra patterns to check
        db_session: Database session for agent-specific patterns
        agent_id: Agent ID for agent-specific patterns

    Returns:
        ContaminationDetector instance
    """
    global _default_detector

    # If agent-specific, always create new instance
    if db_session and agent_id:
        return ContaminationDetector(additional_patterns, db_session, agent_id)

    # If additional patterns, create new instance
    if additional_patterns:
        return ContaminationDetector(additional_patterns)

    # Otherwise use cached singleton
    if _default_detector is None:
        _default_detector = ContaminationDetector()

    return _default_detector


def check_contamination(text: str, additional_patterns: List[str] = None) -> Optional[str]:
    """
    Convenience function to check text for contamination.

    Args:
        text: The text to check
        additional_patterns: Extra patterns to check

    Returns:
        Matched pattern if contaminated, None otherwise
    """
    detector = get_contamination_detector(additional_patterns)
    return detector.check(text)


def clean_response(text: str) -> str:
    """
    Convenience function to clean response text.

    Args:
        text: The text to clean

    Returns:
        Cleaned text
    """
    detector = get_contamination_detector()
    return detector.clean_response(text)
