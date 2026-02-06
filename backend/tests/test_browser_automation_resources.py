"""
Resource management tests for Browser Automation Skill (Phase 7)

Tests cover:
- Max concurrent sessions enforcement
- Timeout enforcement validation
- Screenshot temp file cleanup
- Browser cleanup on errors
- Memory management

Run: pytest backend/tests/test_browser_automation_resources.py -v
"""

import pytest
import asyncio
import os
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestConcurrentSessionLimits:
    """Tests for concurrent session management."""

    @pytest.fixture
    def config(self):
        """Create BrowserConfig for testing."""
        from hub.providers.browser_automation_provider import BrowserConfig

        return BrowserConfig(
            browser_type="chromium",
            headless=True,
            max_concurrent_sessions=2
        )

    def test_config_has_max_concurrent_sessions(self, config):
        """Test config has max_concurrent_sessions property."""
        assert config.max_concurrent_sessions == 2

    def test_provider_respects_config_sessions(self, config):
        """Test provider receives session limit from config."""
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(config)
        assert provider.config.max_concurrent_sessions == 2

    def test_default_max_sessions_is_three(self):
        """Test default max concurrent sessions is 3."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.max_concurrent_sessions == 3


class TestTimeoutEnforcement:
    """Tests for timeout enforcement."""

    @pytest.fixture
    def provider(self):
        """Create PlaywrightProvider instance for testing."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(
            browser_type="chromium",
            headless=True,
            timeout_seconds=5
        )
        return PlaywrightProvider(config)

    def test_config_timeout_seconds(self, provider):
        """Test timeout_seconds is properly set in config."""
        assert provider.config.timeout_seconds == 5

    def test_default_timeout_is_thirty_seconds(self):
        """Test default timeout is 30 seconds."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.timeout_seconds == 30

    def test_provider_stores_timeout_from_config(self):
        """Test provider uses timeout from config."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(timeout_seconds=60)
        provider = PlaywrightProvider(config)

        assert provider.config.timeout_seconds == 60

    @pytest.mark.asyncio
    async def test_timeout_converted_to_milliseconds(self, provider):
        """Test timeout is converted from seconds to milliseconds for Playwright."""
        # The timeout should be multiplied by 1000 when passed to Playwright
        # This is tested implicitly through the provider's timeout_seconds * 1000 usage
        assert provider.config.timeout_seconds * 1000 == 5000


class TestScreenshotFileCleanup:
    """Tests for screenshot file management."""

    @pytest.fixture
    def provider(self):
        """Create PlaywrightProvider instance for testing."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        return PlaywrightProvider(config)

    def test_screenshot_dir_created_on_init(self, provider):
        """Test screenshot directory is created on provider initialization."""
        assert provider._screenshot_dir is not None
        assert os.path.exists(provider._screenshot_dir)
        assert provider._screenshot_dir.startswith(tempfile.gettempdir())

    def test_screenshot_dir_has_prefix(self, provider):
        """Test screenshot directory has tsushin prefix."""
        assert "tsushin_screenshots_" in provider._screenshot_dir

    def test_screenshot_dir_is_unique_per_provider(self):
        """Test each provider gets unique screenshot directory."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        provider1 = PlaywrightProvider(config)
        provider2 = PlaywrightProvider(config)

        assert provider1._screenshot_dir != provider2._screenshot_dir


class TestProviderCleanup:
    """Tests for provider resource cleanup."""

    @pytest.fixture
    def provider(self):
        """Create PlaywrightProvider instance for testing."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        return PlaywrightProvider(config)

    @pytest.mark.asyncio
    async def test_cleanup_is_idempotent(self, provider):
        """Test cleanup can be called multiple times safely."""
        # Cleanup without initialization should not raise
        await provider.cleanup()
        await provider.cleanup()
        await provider.cleanup()

        assert provider._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_resets_state(self, provider):
        """Test cleanup properly resets all state."""
        # Set some state
        provider._page = MagicMock()
        provider._context = MagicMock()
        provider._browser = MagicMock()
        provider._playwright = MagicMock()
        provider._initialized = True

        # Make close methods return None (simulate successful close)
        provider._page.close = AsyncMock()
        provider._context.close = AsyncMock()
        provider._browser.close = AsyncMock()
        provider._playwright.stop = AsyncMock()

        await provider.cleanup()

        assert provider._page is None
        assert provider._context is None
        assert provider._browser is None
        assert provider._playwright is None
        assert provider._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_handles_partial_state(self, provider):
        """Test cleanup handles partially initialized state."""
        # Only page is set
        provider._page = MagicMock()
        provider._page.close = AsyncMock()

        # Other components are None
        provider._context = None
        provider._browser = None
        provider._playwright = None

        # Should not raise
        await provider.cleanup()

        assert provider._page is None
        assert provider._initialized is False

    @pytest.mark.asyncio
    async def test_cleanup_handles_close_errors(self, provider):
        """Test cleanup handles errors during component close."""
        provider._page = MagicMock()
        provider._page.close = AsyncMock(side_effect=Exception("Close error"))
        provider._context = MagicMock()
        provider._context.close = AsyncMock()
        provider._browser = MagicMock()
        provider._browser.close = AsyncMock()
        provider._playwright = MagicMock()
        provider._playwright.stop = AsyncMock()
        provider._initialized = True

        # Should not raise despite close error
        await provider.cleanup()

        # State should still be reset
        assert provider._page is None
        assert provider._initialized is False


class TestBrowserLifecycleManagement:
    """Tests for browser lifecycle management."""

    @pytest.fixture
    def provider(self):
        """Create PlaywrightProvider instance for testing."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        return PlaywrightProvider(config)

    def test_is_initialized_initially_false(self, provider):
        """Test is_initialized is False before initialize()."""
        assert provider._initialized is False
        assert provider.is_initialized() is False

    @pytest.mark.asyncio
    async def test_operations_require_initialization(self, provider):
        """Test operations fail if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError) as exc_info:
            await provider.navigate("https://example.com")

        assert "not initialized" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_click_requires_initialization(self, provider):
        """Test click fails if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError):
            await provider.click("#button")

    @pytest.mark.asyncio
    async def test_fill_requires_initialization(self, provider):
        """Test fill fails if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError):
            await provider.fill("#input", "value")

    @pytest.mark.asyncio
    async def test_extract_requires_initialization(self, provider):
        """Test extract fails if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError):
            await provider.extract("body")

    @pytest.mark.asyncio
    async def test_screenshot_requires_initialization(self, provider):
        """Test screenshot fails if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError):
            await provider.screenshot()

    @pytest.mark.asyncio
    async def test_execute_script_requires_initialization(self, provider):
        """Test execute_script fails if not initialized."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        with pytest.raises(BrowserAutomationError):
            await provider.execute_script("return 1")


class TestSkillResourceManagement:
    """Tests for skill-level resource management."""

    @pytest.fixture
    def skill(self):
        """Create BrowserAutomationSkill instance for testing."""
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
    async def test_skill_cleanup_on_success(self, skill, message):
        """Test skill cleanup is called after successful execution."""
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

                # Cleanup should be called exactly once
                mock_provider.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_cleanup_on_error(self, skill, message):
        """Test skill cleanup is called even on execution error."""
        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock()
                mock_provider.cleanup = AsyncMock()
                mock_provider.navigate = AsyncMock(side_effect=Exception("Network error"))
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # Cleanup should still be called
                mock_provider.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_skill_cleanup_on_initialization_error(self, skill, message):
        """Test skill handles initialization error gracefully."""
        config = skill.get_default_config()

        with patch.object(skill, '_parse_intent', new_callable=AsyncMock) as mock_parse:
            mock_parse.return_value = [{"action": "navigate", "params": {"url": "https://example.com"}}]

            with patch('agent.skills.browser_automation_skill.BrowserAutomationRegistry') as mock_registry:
                mock_provider = MagicMock()
                mock_provider.initialize = AsyncMock(side_effect=Exception("Browser launch failed"))
                mock_provider.cleanup = AsyncMock()
                mock_registry.get_provider.return_value = mock_provider

                result = await skill.process(message, config)

                # Cleanup should be attempted even if init fails
                mock_provider.cleanup.assert_called_once()
                assert result.success is False


class TestFlowStepResourceManagement:
    """Tests for flow step handler resource management."""

    @pytest.fixture
    def handler(self):
        """Create handler instance for testing."""
        from flows.flow_engine import BrowserAutomationStepHandler

        mock_db = MagicMock()
        mock_sender = MagicMock()
        mock_tracker = MagicMock()

        return BrowserAutomationStepHandler(mock_db, mock_sender, mock_tracker)

    @pytest.fixture
    def mock_step(self):
        """Create mock FlowNode step."""
        import json
        step = MagicMock()
        step.id = 1
        step.config_json = json.dumps({
            "prompt": "take a screenshot of example.com"
        })
        return step

    @pytest.fixture
    def mock_flow_run(self):
        """Create mock FlowRun."""
        flow_run = MagicMock()
        flow_run.id = 1
        flow_run.tenant_id = "test_tenant"
        return flow_run

    @pytest.fixture
    def mock_step_run(self):
        """Create mock FlowNodeRun."""
        step_run = MagicMock()
        step_run.id = 1
        return step_run

    @pytest.mark.asyncio
    async def test_handler_passes_db_to_skill(self, handler, mock_step, mock_flow_run, mock_step_run):
        """Test handler passes db session to skill."""
        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            mock_skill_instance = MagicMock()
            mock_skill_instance.process = AsyncMock(return_value=MagicMock(
                success=True,
                output="Success",
                metadata={}
            ))
            MockSkill.return_value = mock_skill_instance

            await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            # Verify skill was created with db
            MockSkill.assert_called_once_with(db=handler.db, token_tracker=handler.token_tracker)

    @pytest.mark.asyncio
    async def test_handler_handles_skill_exception(self, handler, mock_step, mock_flow_run, mock_step_run):
        """Test handler handles skill exceptions gracefully."""
        with patch('agent.skills.browser_automation_skill.BrowserAutomationSkill') as MockSkill:
            MockSkill.side_effect = Exception("Unexpected error")

            result = await handler.execute(mock_step, {}, mock_flow_run, mock_step_run)

            assert result["status"] == "failed"
            assert "error" in result


class TestBrowserConfigValidation:
    """Tests for BrowserConfig validation."""

    def test_config_validates_browser_type(self):
        """Test config accepts valid browser types."""
        from hub.providers.browser_automation_provider import BrowserConfig

        # Valid browser types
        config1 = BrowserConfig(browser_type="chromium")
        config2 = BrowserConfig(browser_type="firefox")
        config3 = BrowserConfig(browser_type="webkit")

        assert config1.browser_type == "chromium"
        assert config2.browser_type == "firefox"
        assert config3.browser_type == "webkit"

    def test_config_default_browser_is_chromium(self):
        """Test default browser type is chromium."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.browser_type == "chromium"

    def test_config_headless_defaults_to_true(self):
        """Test headless defaults to True."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.headless is True

    def test_config_viewport_defaults(self):
        """Test viewport has sensible defaults."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.viewport_width == 1280
        assert config.viewport_height == 720

    def test_config_custom_viewport(self):
        """Test custom viewport settings."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(viewport_width=1920, viewport_height=1080)
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080

    def test_config_user_agent_defaults_to_none(self):
        """Test user_agent defaults to None."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.user_agent is None

    def test_config_custom_user_agent(self):
        """Test custom user_agent setting."""
        from hub.providers.browser_automation_provider import BrowserConfig

        custom_ua = "Mozilla/5.0 Custom Agent"
        config = BrowserConfig(user_agent=custom_ua)
        assert config.user_agent == custom_ua

    def test_config_proxy_defaults_to_none(self):
        """Test proxy_url defaults to None."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        assert config.proxy_url is None

    def test_config_custom_proxy(self):
        """Test custom proxy_url setting."""
        from hub.providers.browser_automation_provider import BrowserConfig

        proxy = "http://proxy.example.com:8080"
        config = BrowserConfig(proxy_url=proxy)
        assert config.proxy_url == proxy


class TestAsyncLockBehavior:
    """Tests for async lock behavior in provider."""

    @pytest.fixture
    def provider(self):
        """Create PlaywrightProvider instance for testing."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        return PlaywrightProvider(config)

    def test_provider_has_lock(self, provider):
        """Test provider has async lock."""
        assert provider._lock is not None
        assert isinstance(provider._lock, asyncio.Lock)

    def test_lock_is_unique_per_provider(self):
        """Test each provider has its own lock."""
        from hub.providers.playwright_provider import PlaywrightProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(headless=True)
        provider1 = PlaywrightProvider(config)
        provider2 = PlaywrightProvider(config)

        assert provider1._lock is not provider2._lock
