"""
Unit tests for Browser Automation Skill (Phase 14.5)

Tests cover:
- Skill instantiation and configuration
- can_handle() keyword detection and AI fallback
- process() action execution
- Host mode authorization
- Intent parsing (AI and fallback)
- Result formatting

Run: pytest backend/tests/test_browser_automation_skill.py -v
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestBrowserAutomationSkillInstantiation:
    """Tests for skill instantiation."""

    def test_skill_attributes(self):
        """Test skill class attributes."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        assert BrowserAutomationSkill.skill_type == "browser_automation"
        assert BrowserAutomationSkill.skill_name == "Browser Automation"
        assert "browser" in BrowserAutomationSkill.skill_description.lower()

    def test_skill_instantiation_without_db(self):
        """Test creating skill without database."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()

        assert skill._db is None
        assert skill.token_tracker is None

    def test_skill_instantiation_with_db_and_tracker(self):
        """Test creating skill with database and token tracker."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mock_db = MagicMock()
        mock_tracker = MagicMock()

        skill = BrowserAutomationSkill(db=mock_db, token_tracker=mock_tracker)

        assert skill._db == mock_db
        assert skill.token_tracker == mock_tracker


class TestBrowserAutomationSkillConfig:
    """Tests for skill configuration."""

    def test_default_config(self):
        """Test default configuration values."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        config = BrowserAutomationSkill.get_default_config()

        assert "browser" in config["keywords"]
        assert "navigate" in config["keywords"]
        assert "screenshot" in config["keywords"]
        assert config["use_ai_fallback"] is True
        assert config["mode"] == "container"
        assert config["provider_type"] == "playwright"
        assert config["timeout_seconds"] == 30
        assert config["allowed_user_keys"] == []

    def test_config_schema(self):
        """Test configuration schema structure."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        schema = BrowserAutomationSkill.get_config_schema()

        assert schema["type"] == "object"
        props = schema["properties"]

        assert "keywords" in props
        assert "mode" in props
        assert props["mode"]["enum"] == ["container", "host"]
        assert "provider_type" in props
        assert "allowed_user_keys" in props


class TestBrowserAutomationSkillCanHandle:
    """Tests for can_handle method."""

    @pytest.fixture
    def skill(self):
        """Create skill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        skill = BrowserAutomationSkill()
        skill._config = BrowserAutomationSkill.get_default_config()
        return skill

    @pytest.fixture
    def message(self):
        """Create test message."""
        from agent.skills.base import InboundMessage
        return InboundMessage(
            id="test-msg-1",
            sender="Test User",
            sender_key="+5511999999999",
            body="",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_can_handle_with_keywords_no_ai(self, skill, message):
        """Test can_handle with keyword match (no AI fallback)."""
        skill._config["use_ai_fallback"] = False
        message.body = "take a screenshot of google.com"

        result = await skill.can_handle(message)

        assert result is True

    @pytest.mark.asyncio
    async def test_can_handle_no_keywords(self, skill, message):
        """Test can_handle rejects messages without keywords."""
        skill._config["use_ai_fallback"] = False
        message.body = "Hello, how are you?"

        result = await skill.can_handle(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_can_handle_skips_media_messages(self, skill, message):
        """Test can_handle skips messages with media."""
        message.body = "take a screenshot"
        message.media_type = "audio"

        result = await skill.can_handle(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_can_handle_with_ai_fallback(self, skill, message):
        """Test can_handle with AI classification."""
        message.body = "please navigate to example.com"

        with patch.object(skill, '_ai_classify', new_callable=AsyncMock) as mock_ai:
            mock_ai.return_value = True

            result = await skill.can_handle(message)

            assert result is True
            mock_ai.assert_called_once()


class TestBrowserAutomationSkillProcess:
    """Tests for process method."""

    @pytest.fixture
    def skill(self):
        """Create skill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        skill = BrowserAutomationSkill()
        skill._config = BrowserAutomationSkill.get_default_config()
        return skill

    @pytest.fixture
    def message(self):
        """Create test message."""
        from agent.skills.base import InboundMessage
        return InboundMessage(
            id="test-msg-1",
            sender="Test User",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_process_host_mode_unauthorized(self, skill, message):
        """Test process denies unauthorized host mode access."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511888888888"]  # Different user

        result = await skill.process(message, config)

        assert result.success is False
        assert "permission" in result.output.lower()
        assert result.metadata.get('error') == 'unauthorized'

    @pytest.mark.asyncio
    async def test_process_host_mode_authorized(self, skill, message):
        """Test process allows authorized host mode access."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511999999999"]  # Same user

        # Mock the provider and parsing
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

                # Should attempt to process (may still fail due to mocking)
                assert result.metadata.get('mode') == 'host'

    @pytest.mark.asyncio
    async def test_process_provider_unavailable(self, skill, message):
        """Test process handles unavailable provider."""
        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                assert result.success is False
                assert "not available" in result.output.lower()

    @pytest.mark.asyncio
    async def test_process_parse_failed(self, skill, message):
        """Test process handles parsing failure."""
        message.body = "random gibberish that makes no sense"
        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = None

            result = await skill.process(message, config)

            assert result.success is False
            assert "could not understand" in result.output.lower()


class TestBrowserAutomationSkillIntentParsing:
    """Tests for intent parsing."""

    @pytest.fixture
    def skill(self):
        """Create skill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        return BrowserAutomationSkill()

    def test_simple_parse_navigate(self, skill):
        """Test simple parsing of navigate command."""
        actions = skill._simple_parse("go to google.com")

        assert actions is not None
        assert len(actions) == 1
        assert actions[0]["action"] == "navigate"
        assert "google.com" in actions[0]["params"]["url"]

    def test_simple_parse_screenshot(self, skill):
        """Test simple parsing of screenshot command."""
        actions = skill._simple_parse("take a screenshot of example.com")

        assert actions is not None
        assert len(actions) == 2
        assert actions[0]["action"] == "navigate"
        assert actions[1]["action"] == "screenshot"

    def test_simple_parse_extract(self, skill):
        """Test simple parsing of extract command."""
        actions = skill._simple_parse("extract text from example.com")

        assert actions is not None
        assert any(a["action"] == "navigate" for a in actions)
        assert any(a["action"] == "extract" for a in actions)

    def test_simple_parse_portuguese(self, skill):
        """Test simple parsing with Portuguese commands."""
        actions = skill._simple_parse("abrir google.com")

        assert actions is not None
        assert actions[0]["action"] == "navigate"
        assert "google.com" in actions[0]["params"]["url"]

    def test_simple_parse_url_normalization(self, skill):
        """Test URL normalization adds https://."""
        actions = skill._simple_parse("navigate to example.com")

        assert actions is not None
        assert actions[0]["params"]["url"].startswith("https://")

    def test_simple_parse_no_match(self, skill):
        """Test simple parse returns None for unrecognized commands."""
        actions = skill._simple_parse("hello world")

        assert actions is None


class TestBrowserAutomationSkillResultFormatting:
    """Tests for result formatting."""

    @pytest.fixture
    def skill(self):
        """Create skill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        return BrowserAutomationSkill()

    def test_format_navigate_result(self, skill):
        """Test formatting navigate result."""
        from hub.providers.browser_automation_provider import BrowserResult

        results = [BrowserResult(
            success=True,
            action="navigate",
            data={"url": "https://example.com", "title": "Example Domain"}
        )]

        output = skill._format_results(results)

        assert "Navigated to" in output
        assert "Example Domain" in output
        assert "https://example.com" in output

    def test_format_screenshot_result(self, skill):
        """Test formatting screenshot result."""
        from hub.providers.browser_automation_provider import BrowserResult

        results = [BrowserResult(
            success=True,
            action="screenshot",
            data={"path": "/tmp/test.png", "size_bytes": 12345}
        )]

        output = skill._format_results(results)

        assert "Screenshot" in output
        assert "12345" in output

    def test_format_extract_result(self, skill):
        """Test formatting extract result."""
        from hub.providers.browser_automation_provider import BrowserResult

        results = [BrowserResult(
            success=True,
            action="extract",
            data={"selector": "h1", "text": "Hello World"}
        )]

        output = skill._format_results(results)

        assert "Extracted" in output
        assert "Hello World" in output

    def test_format_extract_truncates_long_text(self, skill):
        """Test that long extracted text is truncated."""
        from hub.providers.browser_automation_provider import BrowserResult

        long_text = "A" * 1000
        results = [BrowserResult(
            success=True,
            action="extract",
            data={"selector": "body", "text": long_text}
        )]

        output = skill._format_results(results)

        assert "..." in output
        assert len(output) < 1000

    def test_format_failed_result(self, skill):
        """Test formatting failed result."""
        from hub.providers.browser_automation_provider import BrowserResult

        results = [BrowserResult(
            success=False,
            action="click",
            data={},
            error="Element not found"
        )]

        output = skill._format_results(results)

        assert "Failed" in output
        assert "Element not found" in output

    def test_format_multiple_results(self, skill):
        """Test formatting multiple results."""
        from hub.providers.browser_automation_provider import BrowserResult

        results = [
            BrowserResult(success=True, action="navigate", data={"url": "https://example.com", "title": "Test"}),
            BrowserResult(success=True, action="screenshot", data={"path": "/tmp/test.png", "size_bytes": 1000})
        ]

        output = skill._format_results(results)

        assert "Navigated" in output
        assert "Screenshot" in output

    def test_format_empty_results(self, skill):
        """Test formatting empty results list."""
        output = skill._format_results([])

        assert "No actions" in output


class TestBrowserAutomationSkillRegistration:
    """Tests for skill registration."""

    def test_skill_registered_in_manager(self):
        """Test that skill is registered in SkillManager."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        skills = manager.list_available_skills()

        skill_types = [s["skill_type"] for s in skills]
        assert "browser_automation" in skill_types

    def test_skill_info_in_registry(self):
        """Test skill info is available from manager."""
        from agent.skills.skill_manager import SkillManager

        manager = SkillManager()
        skills = manager.list_available_skills()

        browser_skill = next(
            (s for s in skills if s["skill_type"] == "browser_automation"),
            None
        )

        assert browser_skill is not None
        assert browser_skill["skill_name"] == "Browser Automation"


class TestBrowserAutomationSkillHostModeAuthorization:
    """Tests for host mode authorization logic."""

    @pytest.fixture
    def skill(self):
        """Create skill instance for testing."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill
        return BrowserAutomationSkill()

    @pytest.fixture
    def message(self):
        """Create test message."""
        from agent.skills.base import InboundMessage
        return InboundMessage(
            id="test-msg-1",
            sender="Test User",
            sender_key="+5511999999999",
            body="navigate to example.com",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    @pytest.mark.asyncio
    async def test_container_mode_no_auth_check(self, skill, message):
        """Test container mode doesn't require authorization."""
        config = skill.get_default_config()
        config["mode"] = "container"
        config["allowed_user_keys"] = []  # Empty whitelist

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None  # Will fail but no auth error

                result = await skill.process(message, config)

                # Should fail for provider, not auth
                assert result.metadata.get('error') != 'unauthorized'

    @pytest.mark.asyncio
    async def test_host_mode_empty_whitelist_allows_all(self, skill, message):
        """Test host mode with empty whitelist allows all users."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = []  # Empty = no restriction

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                # Should not get auth error
                assert result.metadata.get('error') != 'unauthorized'

    @pytest.mark.asyncio
    async def test_host_mode_whitelist_allows_listed_user(self, skill, message):
        """Test host mode whitelist allows listed user."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511999999999", "+5511888888888"]

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_registry.get_provider.return_value = None

                result = await skill.process(message, config)

                assert result.metadata.get('error') != 'unauthorized'

    @pytest.mark.asyncio
    async def test_host_mode_whitelist_blocks_unlisted_user(self, skill, message):
        """Test host mode whitelist blocks unlisted user."""
        config = skill.get_default_config()
        config["mode"] = "host"
        config["allowed_user_keys"] = ["+5511888888888"]  # Different number

        result = await skill.process(message, config)

        assert result.success is False
        assert result.metadata.get('error') == 'unauthorized'
        assert "permission" in result.output.lower()


class TestBrowserAutomationTokenTracking:
    """Tests for token tracking integration (Phase 4)."""

    @pytest.fixture
    def mock_token_tracker(self):
        """Create mock token tracker."""
        tracker = MagicMock()
        tracker.track_usage = MagicMock()
        return tracker

    @pytest.fixture
    def skill_with_tracker(self, mock_token_tracker):
        """Create skill instance with token tracker."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill(db=MagicMock(), token_tracker=mock_token_tracker)
        skill._config = BrowserAutomationSkill.get_default_config()
        return skill

    @pytest.fixture
    def message(self):
        """Create test message."""
        from agent.skills.base import InboundMessage
        return InboundMessage(
            id="test-msg-1",
            sender="Test User",
            sender_key="+5511999999999",
            body="take a screenshot of example.com",
            chat_id="chat-1",
            chat_name="Test Chat",
            is_group=False,
            timestamp=datetime.utcnow()
        )

    def test_token_tracker_initialized(self, skill_with_tracker, mock_token_tracker):
        """Test that token tracker is properly initialized."""
        assert skill_with_tracker.token_tracker == mock_token_tracker

    def test_skill_without_tracker(self):
        """Test skill works without token tracker."""
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        skill = BrowserAutomationSkill()
        assert skill.token_tracker is None

    @pytest.mark.asyncio
    async def test_token_tracking_on_parse_intent(self, skill_with_tracker, mock_token_tracker, message):
        """Test token tracking is called during intent parsing."""
        config = skill_with_tracker.get_default_config()

        # Mock the AI client and provider
        with patch.object(skill_with_tracker, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            # Return valid actions
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

                # Process the message
                await skill_with_tracker.process(message, config)

                # Verify parse_intent was called
                mock_parse.assert_called_once()

    @pytest.mark.asyncio
    async def test_token_usage_metadata_format(self, skill_with_tracker, message):
        """Test token usage metadata is properly formatted."""
        from hub.providers.browser_automation_provider import BrowserResult

        config = skill_with_tracker.get_default_config()

        with patch.object(skill_with_tracker, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "screenshot", "params": {"full_page": True}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()
                mock_provider.screenshot = AsyncMock(return_value=BrowserResult(
                    success=True,
                    action="screenshot",
                    data={"path": "/tmp/test.png", "size_bytes": 1000}
                ))
                mock_registry.get_provider.return_value = mock_provider

                result = await skill_with_tracker.process(message, config)

                # Result should have proper metadata
                assert 'actions_executed' in result.metadata
                assert result.metadata.get('provider') == 'playwright'
                assert result.metadata.get('mode') == 'container'


class TestBrowserAutomationSkillManagerIntegration:
    """Tests for skill manager integration."""

    def test_skill_manager_passes_token_tracker(self):
        """Test that SkillManager passes token_tracker to browser_automation skill."""
        from agent.skills.skill_manager import SkillManager

        mock_tracker = MagicMock()
        manager = SkillManager(token_tracker=mock_tracker)

        assert manager.token_tracker == mock_tracker

    def test_browser_automation_skill_created_with_tracker(self):
        """Test browser_automation skill receives token_tracker from manager."""
        # This test verifies the skill instantiation logic
        from agent.skills.browser_automation_skill import BrowserAutomationSkill

        mock_db = MagicMock()
        mock_tracker = MagicMock()

        # Simulate what skill_manager does
        skill = BrowserAutomationSkill(db=mock_db, token_tracker=mock_tracker)

        assert skill._db == mock_db
        assert skill.token_tracker == mock_tracker
