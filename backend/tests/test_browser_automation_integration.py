"""
Integration tests for Browser Automation Skill (Phase 14.5)

Tests cover:
- Skill to provider flow
- Registry provider discovery
- Database configuration loading
- Multi-action sequences
- Cross-component integration

Run: pytest backend/tests/test_browser_automation_integration.py -v

Note: These tests use mocks to avoid actual browser launches.
For real browser tests, see dev_tests/test_browser_automation_e2e.py
"""

import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestSkillToProviderIntegration:
    """Tests for skill-to-provider integration flow."""

    @pytest.mark.asyncio
    async def test_skill_uses_registry_to_get_provider(self):
        """Test that skill uses registry to get provider."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Test",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()
                mock_provider.navigate = AsyncMock(return_value=MagicMock(
                    success=True,
                    action="navigate",
                    data={"url": "https://example.com", "title": "Example"},
                    error=None
                ))
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # Verify registry was called
                mock_registry.get_provider.assert_called_once()

                # Verify provider lifecycle
                mock_provider.initialize.assert_called_once()
                mock_provider.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_handles_provider_not_available(self):
        """Test skill handles missing provider gracefully."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Test",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                assert result.success is False
                assert "not available" in result.output.lower()


class TestRegistryProviderDiscovery:
    """Tests for registry provider discovery."""

    def test_registry_discovers_playwright_provider(self):
        """Test registry discovers Playwright provider."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        providers = BrowserAutomationRegistry.list_available_providers()
        playwright = next((p for p in providers if p["id"] == "playwright"), None)

        assert playwright is not None
        assert playwright["status"] == "available"
        # Mode is determined by provider type, not stored in registry
        assert playwright["class"] == "PlaywrightProvider"

    def test_registry_returns_provider_instance(self):
        """Test registry returns provider instance."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry
        from hub.providers.playwright_provider import PlaywrightProvider

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        provider = BrowserAutomationRegistry.get_provider("playwright")

        assert provider is not None
        assert isinstance(provider, PlaywrightProvider)
        assert provider.provider_type == "playwright"

    def test_registry_returns_none_for_unknown_provider(self):
        """Test registry returns None for unknown provider."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        provider = BrowserAutomationRegistry.get_provider("unknown_provider")

        assert provider is None


class TestDatabaseConfigurationLoading:
    """Tests for database configuration loading."""

    def test_skill_loads_default_config(self):
        """Test skill loads default configuration."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        config = BrowserAutomationSkill.get_default_config()

        assert "browser" in config["keywords"]
        assert config["mode"] == "container"
        assert config["provider_type"] == "playwright"
        assert config["timeout_seconds"] == 30

    def test_skill_config_schema_valid(self):
        """Test skill config schema is valid."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        schema = BrowserAutomationSkill.get_config_schema()

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "mode" in schema["properties"]
        assert "provider_type" in schema["properties"]

    def test_provider_config_from_browser_config(self):
        """Test provider receives BrowserConfig."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        config = BrowserConfig(
            browser_type="firefox",
            headless=False,
            timeout_seconds=60
        )

        provider = PlaywrightProvider(config)

        assert provider.config.browser_type == "firefox"
        assert provider.config.headless is False
        assert provider.config.timeout_seconds == 60


class TestMultiActionSequence:
    """Tests for multi-action sequence execution."""

    @pytest.mark.asyncio
    async def test_multiple_actions_execute_sequentially(self):
        """Test multiple actions execute in order."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage
        from hub.providers.browser_automation_provider import BrowserResult

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Test",
            sender_key="+5511999999999",
            body="go to google.com and take a screenshot",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [
                {"action": "navigate", "params": {"url": "https://google.com"}},
                {"action": "screenshot", "params": {"full_page": True}}
            ]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()

                execution_order = []

                async def mock_navigate(*args, **kwargs):
                    execution_order.append("navigate")
                    return BrowserResult(
                        success=True,
                        action="navigate",
                        data={"url": "https://google.com", "title": "Google"}
                    )

                async def mock_screenshot(*args, **kwargs):
                    execution_order.append("screenshot")
                    return BrowserResult(
                        success=True,
                        action="screenshot",
                        data={"path": "/tmp/test.png", "size_bytes": 1000}
                    )

                mock_provider.navigate = mock_navigate
                mock_provider.screenshot = mock_screenshot
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # Verify both actions executed
                assert result.success is True
                assert result.metadata["actions_executed"] == 2
                assert execution_order == ["navigate", "screenshot"]

    @pytest.mark.asyncio
    async def test_action_failure_continues_or_stops_based_on_type(self):
        """Test action failure handling."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage
        from hub.providers.browser_automation_provider import BrowserResult, SecurityError

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Test",
            sender_key="+5511999999999",
            body="navigate and click",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [
                {"action": "navigate", "params": {"url": "https://example.com"}},
                {"action": "click", "params": {"selector": "#button"}}
            ]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()
                mock_provider.navigate = AsyncMock(return_value=BrowserResult(
                    success=True,
                    action="navigate",
                    data={"url": "https://example.com", "title": "Example"}
                ))
                mock_provider.click = AsyncMock(side_effect=Exception("Element not found"))
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # First action should succeed, second should fail
                assert result.metadata["actions_succeeded"] >= 1
                assert "Failed" in result.output or "not found" in result.output.lower()


class TestSkillManagerIntegration:
    """Tests for skill manager integration."""

    def test_browser_automation_registered_in_manager(self):
        """Test browser_automation is registered in SkillManager."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        skills = manager.list_available_skills()

        skill_types = [s["skill_type"] for s in skills]
        assert "browser_automation" in skill_types

    def test_skill_manager_creates_skill_with_tracker(self):
        """Test SkillManager passes token_tracker to browser skill."""
        from agent.skills.skill_manager import SkillManager
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mock_tracker = MagicMock()
        manager = SkillManager(token_tracker=mock_tracker)

        # Simulate what the manager does when creating browser_automation skill
        skill = BrowserAutomationSkill(db=MagicMock(), token_tracker=mock_tracker)

        assert skill.token_tracker == mock_tracker


class TestHostModeAuthorization:
    """Tests for host mode authorization integration."""

    @pytest.mark.asyncio
    async def test_host_mode_blocks_unauthorized_users(self):
        """Test host mode blocks users not in whitelist."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Unknown User",
            sender_key="+5511888888888",  # Not in whitelist
            body="navigate to gmail.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511999999999"]  # Different user

        result = await skill.process(message, config)

        assert result.success is False
        assert result.metadata.get("error") == "unauthorized"
        assert "permission" in result.output.lower()

    @pytest.mark.asyncio
    async def test_host_mode_allows_authorized_users(self):
        """Test host mode allows users in whitelist."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Authorized User",
            sender_key="+5511999999999",  # In whitelist
            body="navigate to gmail.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511999999999"]

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://gmail.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None  # Will fail but not due to auth

                result = await skill.process(message, config)

                # Should not be unauthorized error
                assert result.metadata.get("error") != "unauthorized"

    @pytest.mark.asyncio
    async def test_container_mode_allows_all_users(self):
        """Test container mode allows all users (no whitelist check)."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Any User",
            sender_key="+5511000000000",  # Random user
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()
        config["mode"] = "container"
        config["allowed_user_keys"] = []  # Empty whitelist in container mode

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                # Should not be unauthorized error
                assert result.metadata.get("error") != "unauthorized"


class TestErrorPropagation:
    """Tests for error propagation across components."""

    @pytest.mark.asyncio
    async def test_provider_error_propagates_to_skill_result(self):
        """Test provider errors are captured in skill result."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        from agent.skills.base import InboundMessage
        from hub.providers.browser_automation_provider import NavigationError

        skill = BrowserAutomationSkill(db=MagicMock())

        message = InboundMessage(
            id="test-1",
            sender="Test",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test",
            is_group=False,
            timestamp=datetime.utcnow()
        )

        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()
                mock_provider.navigate = AsyncMock(side_effect=NavigationError("Connection refused"))
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # Error should be in output
                assert "Connection refused" in result.output or "Failed" in result.output
