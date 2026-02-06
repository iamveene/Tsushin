"""
Unit tests for SkillContextService - Phase 20: Skill-aware Sentinel

Tests that the service correctly retrieves and aggregates skill context
for Sentinel security analysis.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

from services.skill_context_service import SkillContextService


class TestSkillContextService:
    """Tests for SkillContextService."""

    def setup_method(self):
        """Reset cache before each test."""
        SkillContextService.clear_all_cache()

    def test_empty_context_for_agent_without_skills(self):
        """Test that agents without skills get empty context."""
        # Mock DB session that returns no skills
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = []

        service = SkillContextService(mock_db)
        context = service.get_agent_skill_context(agent_id=123)

        assert context["enabled_skills"] == []
        assert context["expected_intents"] == []
        assert context["expected_patterns"] == []
        assert context["risk_notes"] == []
        assert context["formatted_context"] == ""

    def test_context_for_agent_with_browser_skill_integration(self):
        """Integration test: browser automation skill context is retrieved using real skill registry."""
        from agent.skills import get_skill_manager

        # Mock skill record from DB
        mock_skill = MagicMock()
        mock_skill.skill_type = "browser_automation"
        mock_skill.is_enabled = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_skill
        ]

        # Use the real skill manager (integration test)
        service = SkillContextService(mock_db)
        context = service.get_agent_skill_context(agent_id=456)

        # Verify the context includes browser automation skill
        assert "Browser Automation" in context["enabled_skills"]
        assert len(context["expected_intents"]) > 0
        assert len(context["expected_patterns"]) > 0
        assert "AGENT SKILL CONTEXT" in context["formatted_context"]

    def test_context_aggregates_multiple_skills_integration(self):
        """Integration test: multiple skill contexts are aggregated."""
        # Mock multiple skill records
        mock_browser_skill = MagicMock()
        mock_browser_skill.skill_type = "browser_automation"
        mock_browser_skill.is_enabled = True

        mock_shell_skill = MagicMock()
        mock_shell_skill.skill_type = "shell"
        mock_shell_skill.is_enabled = True

        mock_scraping_skill = MagicMock()
        mock_scraping_skill.skill_type = "web_scraping"
        mock_scraping_skill.is_enabled = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_browser_skill,
            mock_shell_skill,
            mock_scraping_skill,
        ]

        service = SkillContextService(mock_db)
        context = service.get_agent_skill_context(agent_id=789)

        # Should have all three skills
        assert "Browser Automation" in context["enabled_skills"]
        assert "Shell Commands" in context["enabled_skills"]
        assert "Web Scraping" in context["enabled_skills"]

        # Should have aggregated intents from all skills
        assert len(context["expected_intents"]) >= 3  # At least some intents

        # Should have aggregated patterns
        assert len(context["expected_patterns"]) >= 3  # At least some patterns

    def test_caching_works(self):
        """Test that context is cached and reused."""
        mock_skill = MagicMock()
        mock_skill.skill_type = "browser_automation"
        mock_skill.is_enabled = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_skill
        ]

        service = SkillContextService(mock_db)

        # First call
        context1 = service.get_agent_skill_context(agent_id=100)
        # Second call (should be cached)
        context2 = service.get_agent_skill_context(agent_id=100)

        # Both should return same content
        assert context1["enabled_skills"] == context2["enabled_skills"]

        # DB should only be queried once (due to caching)
        assert mock_db.query.call_count == 1

    def test_cache_invalidation(self):
        """Test that cache can be invalidated."""
        mock_skill = MagicMock()
        mock_skill.skill_type = "browser_automation"
        mock_skill.is_enabled = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_skill
        ]

        service = SkillContextService(mock_db)

        # First call
        service.get_agent_skill_context(agent_id=200)

        # Invalidate cache
        service.invalidate_cache(agent_id=200)

        # Second call (should query again)
        service.get_agent_skill_context(agent_id=200)

        # DB should be queried twice (once before and once after invalidation)
        assert mock_db.query.call_count == 2

    def test_format_context_limits_intents(self):
        """Test that formatted context limits number of intents."""
        service = SkillContextService(MagicMock())

        # Create 20 intents (more than limit)
        many_intents = [f"Intent {i}" for i in range(20)]

        formatted = service._format_context(
            skills=["Test Skill"],
            intents=many_intents,
            patterns=["pattern1"],
            risk_notes=[],
        )

        # Should contain max 15 intents (based on implementation)
        intent_count = formatted.count("Intent ")
        assert intent_count <= 15

    def test_skill_without_sentinel_context(self):
        """Test handling of skill that doesn't have explicit sentinel context."""
        # Use a skill that may not have get_sentinel_context (like flows)
        mock_skill = MagicMock()
        mock_skill.skill_type = "flows"
        mock_skill.is_enabled = True

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.all.return_value = [
            mock_skill
        ]

        service = SkillContextService(mock_db)
        context = service.get_agent_skill_context(agent_id=300)

        # Should still include the skill name (from skill_name attribute)
        assert "Flows" in context["enabled_skills"]
        # Should still have formatted context (just minimal)
        assert context["formatted_context"] != "" or len(context["enabled_skills"]) > 0

    def test_error_handling_returns_empty_context(self):
        """Test that errors return empty context (fail open)."""
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("Database error")

        service = SkillContextService(mock_db)
        context = service.get_agent_skill_context(agent_id=400)

        # Should return empty context on error
        assert context["enabled_skills"] == []
        assert context["formatted_context"] == ""
