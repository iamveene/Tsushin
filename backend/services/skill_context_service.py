"""
Skill Context Service for Sentinel Integration - Phase 20

Retrieves enabled skills for an agent and formats their security
context for injection into Sentinel analysis prompts.

This service bridges the Skills system and Sentinel security system,
allowing Sentinel to understand what behaviors are expected for an agent
based on its enabled skills.
"""

from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import logging

from models import AgentSkill

logger = logging.getLogger(__name__)


class SkillContextService:
    """
    Retrieves skill security context for Sentinel analysis.

    Collects sentinel context from enabled skills and formats it
    for injection into LLM-based security analysis prompts.
    """

    # Cache skill context for 5 minutes per agent
    _cache: Dict[int, Tuple[datetime, Dict[str, Any]]] = {}
    _cache_ttl = timedelta(minutes=5)

    def __init__(self, db: Session):
        """
        Initialize service with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    def get_agent_skill_context(self, agent_id: int) -> Dict[str, Any]:
        """
        Get aggregated skill context for an agent.

        Checks cache first, then queries database and skill registry
        to build comprehensive context.

        Args:
            agent_id: Agent ID to get skills for

        Returns:
            Dict with:
            - enabled_skills: List of skill names
            - expected_intents: Combined list of expected intents
            - expected_patterns: Combined list of expected patterns
            - risk_notes: Combined security notes
            - formatted_context: Human-readable context string for LLM
        """
        # Check cache first
        if agent_id in self._cache:
            cached_time, cached_context = self._cache[agent_id]
            if datetime.utcnow() - cached_time < self._cache_ttl:
                logger.debug(f"Using cached skill context for agent {agent_id}")
                return cached_context

        # Compute context and cache it
        context = self._compute_skill_context(agent_id)
        self._cache[agent_id] = (datetime.utcnow(), context)
        return context

    def _compute_skill_context(self, agent_id: int) -> Dict[str, Any]:
        """
        Compute skill context by querying enabled skills and their sentinel contexts.

        Args:
            agent_id: Agent ID

        Returns:
            Aggregated skill context dict
        """
        try:
            # Import skill manager here to avoid circular imports
            from agent.skills import get_skill_manager
            skill_manager = get_skill_manager()

            # Get enabled skills for agent
            skills = self.db.query(AgentSkill).filter(
                AgentSkill.agent_id == agent_id,
                AgentSkill.is_enabled == True
            ).all()

            if not skills:
                logger.debug(f"No enabled skills for agent {agent_id}")
                return self._empty_context()

            enabled_skills = []
            all_intents = []
            all_patterns = []
            all_risk_notes = []

            for skill_record in skills:
                skill_type = skill_record.skill_type

                if skill_type not in skill_manager.registry:
                    logger.warning(f"Skill type '{skill_type}' not in registry")
                    continue

                skill_class = skill_manager.registry[skill_type]
                enabled_skills.append(skill_class.skill_name)

                # Get sentinel context if skill provides it
                if hasattr(skill_class, 'get_sentinel_context'):
                    try:
                        context = skill_class.get_sentinel_context()

                        intents = context.get('expected_intents', [])
                        patterns = context.get('expected_patterns', [])
                        risk_note = context.get('risk_notes')

                        all_intents.extend(intents)
                        all_patterns.extend(patterns)

                        if risk_note:
                            all_risk_notes.append(
                                f"[{skill_class.skill_name}] {risk_note}"
                            )

                        logger.debug(
                            f"Got sentinel context from {skill_class.skill_name}: "
                            f"{len(intents)} intents, {len(patterns)} patterns"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error getting sentinel context from {skill_type}: {e}"
                        )

            # Build formatted context string for LLM injection
            formatted = self._format_context(
                enabled_skills, all_intents, all_patterns, all_risk_notes
            )

            return {
                "enabled_skills": enabled_skills,
                "expected_intents": all_intents,
                "expected_patterns": all_patterns,
                "risk_notes": all_risk_notes,
                "formatted_context": formatted
            }

        except Exception as e:
            logger.error(f"Error getting skill context for agent {agent_id}: {e}")
            return self._empty_context()

    def _format_context(
        self,
        skills: List[str],
        intents: List[str],
        patterns: List[str],
        risk_notes: List[str]
    ) -> str:
        """
        Format skill context for LLM prompt injection.

        Creates a human-readable string that provides context to the
        security analysis LLM about expected agent behaviors.

        Args:
            skills: List of enabled skill names
            intents: List of expected intent descriptions
            patterns: List of expected keywords/phrases
            risk_notes: List of security notes from skills

        Returns:
            Formatted context string for LLM, or empty string if no skills
        """
        if not skills:
            return ""

        lines = [
            "=== AGENT SKILL CONTEXT ===",
            f"This agent has the following skills enabled: {', '.join(skills)}",
            "",
            "Expected behaviors for these skills include:",
        ]

        # Limit intents to avoid prompt bloat (max 15)
        for intent in intents[:15]:
            lines.append(f"- {intent}")

        if patterns:
            lines.append("")
            lines.append("Normal patterns/keywords for these skills:")
            # Limit patterns (max 25)
            lines.append(f"  {', '.join(patterns[:25])}")

        if risk_notes:
            lines.append("")
            lines.append("Security notes (STILL flag these even with skills enabled):")
            for note in risk_notes:
                lines.append(f"- {note}")

        lines.append("")
        lines.append(
            "IMPORTANT: Messages matching expected skill behaviors should NOT be "
            "flagged as threats, but actual attack patterns should still be detected "
            "even if they mention skill-related terms."
        )
        lines.append("=========================")

        return "\n".join(lines)

    def _empty_context(self) -> Dict[str, Any]:
        """Return empty context for agents with no skills."""
        return {
            "enabled_skills": [],
            "expected_intents": [],
            "expected_patterns": [],
            "risk_notes": [],
            "formatted_context": ""
        }

    def invalidate_cache(self, agent_id: int) -> None:
        """
        Invalidate cached context for an agent.

        Call this when agent skills are modified to ensure
        fresh context is fetched.

        Args:
            agent_id: Agent ID to invalidate cache for
        """
        if agent_id in self._cache:
            del self._cache[agent_id]
            logger.debug(f"Invalidated skill context cache for agent {agent_id}")

    @classmethod
    def clear_all_cache(cls) -> None:
        """
        Clear all cached skill contexts.

        Useful for testing or when skill definitions change.
        """
        cls._cache.clear()
        logger.info("Cleared all skill context cache")
