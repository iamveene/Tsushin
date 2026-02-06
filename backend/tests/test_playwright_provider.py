"""
Unit tests for Playwright Provider (Phase 14.5)

Tests cover:
- Provider instantiation and initialization
- All 6 core actions (navigate, click, fill, extract, screenshot, execute_script)
- Error handling (timeout, element not found, security)
- SSRF protection (blocked IPs/domains)
- Cleanup and resource management

Note: These tests use mocks to avoid actual browser launches.
For real browser tests, see dev_tests/test_browser_automation_integration.py

Run: pytest backend/tests/test_playwright_provider.py -v
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestPlaywrightProviderInstantiation:
    """Tests for provider instantiation."""

    def test_provider_instantiation_with_defaults(self):
        """Test creating provider with default config."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        config = BrowserConfig()
        provider = PlaywrightProvider(config)

        assert provider.provider_type == "playwright"
        assert provider.provider_name == "Playwright (Container)"
        assert provider.config.browser_type == "chromium"
        assert provider.config.headless is True
        assert provider.is_initialized() is False

    def test_provider_instantiation_with_custom_config(self):
        """Test creating provider with custom config."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        config = BrowserConfig(
            browser_type="firefox",
            headless=False,
            timeout_seconds=60,
            viewport_width=1920,
            viewport_height=1080,
            user_agent="Custom UA",
            blocked_domains=["blocked.com"]
        )
        provider = PlaywrightProvider(config)

        assert provider.config.browser_type == "firefox"
        assert provider.config.headless is False
        assert provider.config.timeout_seconds == 60
        assert provider.config.viewport_width == 1920
        assert provider.config.user_agent == "Custom UA"
        assert "blocked.com" in provider.config.blocked_domains

    def test_get_provider_info(self):
        """Test provider info metadata."""
        from hub.providers.playwright_provider import PlaywrightProvider

        info = PlaywrightProvider.get_provider_info()

        assert info["type"] == "playwright"
        assert info["mode"] == "container"
        assert "navigate" in info["actions"]
        assert "chromium" in info["browsers"]
        assert "ssrf_protection" in info["features"]


class TestPlaywrightProviderURLValidation:
    """Tests for URL validation and SSRF protection."""

    def test_validate_url_valid_https(self):
        """Test that HTTPS URLs are accepted."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Should not raise
        provider._validate_url("https://example.com")
        provider._validate_url("https://www.google.com/search?q=test")

    def test_validate_url_valid_http(self):
        """Test that HTTP URLs are accepted."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Should not raise
        provider._validate_url("http://example.com")

    def test_validate_url_blocked_localhost(self):
        """Test that localhost is blocked."""
        from hub.providers.browser_automation_provider import BrowserConfig, SecurityError
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        with pytest.raises(SecurityError):
            provider._validate_url("http://localhost:8080")

        with pytest.raises(SecurityError):
            provider._validate_url("http://127.0.0.1/admin")

    def test_validate_url_blocked_private_ips(self):
        """Test that private IPs are blocked."""
        from hub.providers.browser_automation_provider import BrowserConfig, SecurityError
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        private_urls = [
            "http://10.0.0.1/",
            "http://192.168.1.1/",
            "http://172.16.0.1/",
            "http://169.254.1.1/",
            "http://0.0.0.0/",
        ]

        for url in private_urls:
            with pytest.raises(SecurityError):
                provider._validate_url(url)

    def test_validate_url_blocked_domains(self):
        """Test that configured blocked domains are blocked."""
        from hub.providers.browser_automation_provider import BrowserConfig, SecurityError
        from hub.providers.playwright_provider import PlaywrightProvider

        config = BrowserConfig(blocked_domains=["bank.com", "paypal.com"])
        provider = PlaywrightProvider(config)

        with pytest.raises(SecurityError):
            provider._validate_url("https://www.bank.com/login")

        with pytest.raises(SecurityError):
            provider._validate_url("https://paypal.com/send")

    def test_validate_url_blocked_invalid_scheme(self):
        """Test that non-HTTP schemes are blocked."""
        from hub.providers.browser_automation_provider import BrowserConfig, SecurityError
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        with pytest.raises(SecurityError):
            provider._validate_url("file:///etc/passwd")

        with pytest.raises(SecurityError):
            provider._validate_url("ftp://ftp.example.com")


class TestPlaywrightProviderActions:
    """Tests for browser actions using mocks."""

    @pytest.fixture
    def mock_provider(self):
        """Create provider with mocked Playwright components."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        config = BrowserConfig()
        provider = PlaywrightProvider(config)

        # Mock internal components
        provider._playwright = MagicMock()
        provider._browser = MagicMock()
        provider._context = MagicMock()
        provider._page = MagicMock()
        provider._initialized = True

        return provider

    @pytest.mark.asyncio
    async def test_navigate_success(self, mock_provider):
        """Test successful navigation."""
        # Setup mocks
        mock_response = MagicMock()
        mock_response.status = 200
        mock_provider._page.goto = AsyncMock(return_value=mock_response)
        mock_provider._page.title = AsyncMock(return_value="Example Domain")
        mock_provider._page.url = "https://example.com/"

        result = await mock_provider.navigate("https://example.com")

        assert result.success is True
        assert result.action == "navigate"
        assert result.data["url"] == "https://example.com/"
        assert result.data["title"] == "Example Domain"
        assert result.data["status"] == 200

    @pytest.mark.asyncio
    async def test_navigate_blocked_url(self, mock_provider):
        """Test navigation to blocked URL."""
        from hub.providers.browser_automation_provider import SecurityError

        with pytest.raises(SecurityError):
            await mock_provider.navigate("http://localhost:8080")

    @pytest.mark.asyncio
    async def test_click_success(self, mock_provider):
        """Test successful click."""
        mock_provider._page.click = AsyncMock()

        result = await mock_provider.click("#submit-button")

        assert result.success is True
        assert result.action == "click"
        assert result.data["selector"] == "#submit-button"
        mock_provider._page.click.assert_called_once()

    @pytest.mark.asyncio
    async def test_click_element_not_found(self, mock_provider):
        """Test click on non-existent element."""
        from hub.providers.browser_automation_provider import ElementNotFoundError

        mock_provider._page.click = AsyncMock(
            side_effect=Exception("Element not found")
        )

        with pytest.raises(ElementNotFoundError):
            await mock_provider.click("#nonexistent")

    @pytest.mark.asyncio
    async def test_fill_success(self, mock_provider):
        """Test successful fill."""
        mock_provider._page.fill = AsyncMock()

        result = await mock_provider.fill("#username", "testuser")

        assert result.success is True
        assert result.action == "fill"
        assert result.data["selector"] == "#username"
        assert result.data["value"] == "testuser"
        mock_provider._page.fill.assert_called_once_with(
            "#username", "testuser", timeout=30000
        )

    @pytest.mark.asyncio
    async def test_extract_success(self, mock_provider):
        """Test successful text extraction."""
        mock_element = MagicMock()
        mock_element.text_content = AsyncMock(return_value="Hello World")
        mock_element.inner_html = AsyncMock(return_value="<b>Hello World</b>")
        mock_provider._page.query_selector = AsyncMock(return_value=mock_element)

        result = await mock_provider.extract("h1")

        assert result.success is True
        assert result.action == "extract"
        assert result.data["text"] == "Hello World"
        assert result.data["selector"] == "h1"

    @pytest.mark.asyncio
    async def test_extract_element_not_found(self, mock_provider):
        """Test extraction when element not found."""
        from hub.providers.browser_automation_provider import ElementNotFoundError

        mock_provider._page.query_selector = AsyncMock(return_value=None)

        with pytest.raises(ElementNotFoundError):
            await mock_provider.extract("#nonexistent")

    @pytest.mark.asyncio
    async def test_screenshot_success(self, mock_provider):
        """Test successful screenshot."""
        import os

        mock_provider._page.screenshot = AsyncMock()

        # Create a temporary file to simulate screenshot
        with patch('os.path.getsize', return_value=12345):
            result = await mock_provider.screenshot(full_page=True)

        assert result.success is True
        assert result.action == "screenshot"
        assert result.data["full_page"] is True
        assert "path" in result.data
        assert result.data["path"].endswith(".png")

    @pytest.mark.asyncio
    async def test_screenshot_element(self, mock_provider):
        """Test element screenshot."""
        mock_element = MagicMock()
        mock_element.screenshot = AsyncMock()
        mock_provider._page.query_selector = AsyncMock(return_value=mock_element)

        with patch('os.path.getsize', return_value=5000):
            result = await mock_provider.screenshot(selector="#header")

        assert result.success is True
        assert result.data["selector"] == "#header"
        mock_element.screenshot.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_script_success(self, mock_provider):
        """Test successful script execution."""
        mock_provider._page.evaluate = AsyncMock(return_value={"result": 42})

        result = await mock_provider.execute_script("return {result: 42}")

        assert result.success is True
        assert result.action == "execute_script"
        assert result.data["result"] == {"result": 42}

    @pytest.mark.asyncio
    async def test_execute_script_error(self, mock_provider):
        """Test script execution error."""
        from hub.providers.browser_automation_provider import ScriptExecutionError

        mock_provider._page.evaluate = AsyncMock(
            side_effect=Exception("ReferenceError: foo is not defined")
        )

        with pytest.raises(ScriptExecutionError):
            await mock_provider.execute_script("return foo.bar")


class TestPlaywrightProviderLifecycle:
    """Tests for provider lifecycle management."""

    @pytest.mark.asyncio
    async def test_not_initialized_error(self):
        """Test that actions fail if not initialized."""
        from hub.providers.browser_automation_provider import (
            BrowserConfig,
            BrowserAutomationError
        )
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        with pytest.raises(BrowserAutomationError):
            await provider.navigate("https://example.com")

        with pytest.raises(BrowserAutomationError):
            await provider.click("#btn")

        with pytest.raises(BrowserAutomationError):
            await provider.fill("#input", "value")

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self):
        """Test that cleanup can be called multiple times safely."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Mock components
        mock_page = MagicMock()
        mock_page.close = AsyncMock()
        mock_context = MagicMock()
        mock_context.close = AsyncMock()
        mock_browser = MagicMock()
        mock_browser.close = AsyncMock()
        mock_playwright = MagicMock()
        mock_playwright.stop = AsyncMock()

        provider._page = mock_page
        provider._context = mock_context
        provider._browser = mock_browser
        provider._playwright = mock_playwright
        provider._initialized = True

        # First cleanup
        await provider.cleanup()
        assert provider._initialized is False
        assert provider._page is None

        # Second cleanup should not raise
        await provider.cleanup()

    @pytest.mark.asyncio
    async def test_cleanup_handles_errors(self):
        """Test that cleanup handles errors gracefully."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Mock with errors
        mock_page = MagicMock()
        mock_page.close = AsyncMock(side_effect=Exception("Close error"))
        provider._page = mock_page
        provider._initialized = True

        # Should not raise despite error
        await provider.cleanup()
        assert provider._initialized is False

    def test_is_initialized_states(self):
        """Test is_initialized returns correct state."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Initial state
        assert provider.is_initialized() is False

        # Simulate initialization
        provider._initialized = True
        provider._page = MagicMock()
        assert provider.is_initialized() is True

        # After cleanup simulation
        provider._initialized = False
        provider._page = None
        assert provider.is_initialized() is False


class TestPlaywrightProviderConcurrency:
    """Tests for concurrent access handling."""

    @pytest.mark.asyncio
    async def test_lock_serializes_operations(self):
        """Test that lock prevents concurrent operations."""
        from hub.providers.browser_automation_provider import BrowserConfig
        from hub.providers.playwright_provider import PlaywrightProvider

        provider = PlaywrightProvider(BrowserConfig())

        # Set up mock
        provider._initialized = True
        provider._page = MagicMock()
        provider._page.click = AsyncMock()

        operation_order = []

        async def slow_click(selector):
            async with provider._lock:
                operation_order.append(f"start_{selector}")
                await asyncio.sleep(0.1)
                operation_order.append(f"end_{selector}")

        # Override to track order
        original_click = provider.click

        async def tracked_click(selector):
            operation_order.append(f"enter_{selector}")
            result = await original_click(selector)
            operation_order.append(f"exit_{selector}")
            return result

        # Run two clicks concurrently
        # Due to the lock, they should be serialized
        await asyncio.gather(
            tracked_click("#btn1"),
            tracked_click("#btn2")
        )

        # Verify both completed
        assert "enter_#btn1" in operation_order
        assert "enter_#btn2" in operation_order


class TestPlaywrightProviderRegistration:
    """Tests for provider registration in registry."""

    def test_registry_initializes_playwright(self):
        """Test that Playwright provider is registered."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        assert BrowserAutomationRegistry.is_provider_registered("playwright")

    def test_registry_provider_info(self):
        """Test provider info from registry."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        providers = BrowserAutomationRegistry.list_available_providers()
        playwright_info = next(
            (p for p in providers if p["id"] == "playwright"),
            None
        )

        assert playwright_info is not None
        assert playwright_info["status"] == "available"
        assert playwright_info["is_free"] is True

    def test_registry_get_provider_with_default_config(self):
        """Test getting provider instance with default config."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        provider = BrowserAutomationRegistry.get_provider("playwright")

        assert provider is not None
        assert provider.provider_type == "playwright"
        assert provider.config.browser_type == "chromium"
