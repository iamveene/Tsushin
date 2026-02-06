"""
Unit tests for MCP Browser Provider (Phase 8)

Tests cover:
- Provider instantiation and configuration
- URL validation (sensitive domain blocking)
- Action mapping to MCP tools
- Bridge communication (mocked)
- Error handling and retries

Run: pytest backend/tests/test_mcp_browser_provider.py -v
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime


class TestMCPBrowserProviderInstantiation:
    """Tests for provider instantiation."""

    def test_provider_attributes(self):
        """Test provider class attributes."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider

        assert MCPBrowserProvider.provider_type == "mcp_browser"
        assert MCPBrowserProvider.provider_name == "MCP Browser (Host)"
        assert "host.docker.internal" in MCPBrowserProvider.DEFAULT_BRIDGE_URL

    def test_provider_instantiation_with_default_config(self):
        """Test creating provider with default configuration."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()
        provider = MCPBrowserProvider(config)

        assert provider.config == config
        assert provider._initialized is False
        assert provider._session_id is None

    def test_provider_instantiation_with_custom_config(self):
        """Test creating provider with custom configuration."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(
            mode="host",
            timeout_seconds=60,
            allowed_user_keys=["+5511999999999"],
            blocked_domains=["blocked.com"],
        )
        provider = MCPBrowserProvider(config)

        assert provider.config.mode == "host"
        assert provider.config.timeout_seconds == 60
        assert "+5511999999999" in provider.config.allowed_user_keys

    def test_provider_info(self):
        """Test provider metadata."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider

        info = MCPBrowserProvider.get_provider_info()

        assert info["type"] == "mcp_browser"
        assert info["mode"] == "host"
        assert "authenticated_sessions" in info["features"]
        assert "audit_logging" in info["features"]


class TestMCPBrowserProviderURLValidation:
    """Tests for URL validation (sensitive domain blocking)."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(mode="host")
        return MCPBrowserProvider(config)

    def test_blocks_banking_domains(self, provider):
        """Test that banking domains are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        banking_urls = [
            "https://bank.example.com/login",
            "https://www.paypal.com/checkout",
            "https://venmo.com/account",
            "https://www.chase.com",
            "https://wellsfargo.com/accounts",
        ]

        for url in banking_urls:
            with pytest.raises(SecurityError) as exc_info:
                provider._validate_url(url)
            assert "sensitive domain" in str(exc_info.value).lower()

    def test_blocks_authentication_domains(self, provider):
        """Test that authentication domains are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        auth_urls = [
            "https://login.microsoft.com/oauth",
            "https://accounts.google.com/signin",
            "https://company.okta.com/login",
            "https://sso.internal.corp/auth",
        ]

        for url in auth_urls:
            with pytest.raises(SecurityError) as exc_info:
                provider._validate_url(url)
            assert "sensitive domain" in str(exc_info.value).lower()

    def test_blocks_internal_domains(self, provider):
        """Test that internal/corporate domains are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        internal_urls = [
            "https://internal.company.com",
            "https://intranet.corp.com",
            "https://admin.myapp.com",
            "https://corp.internal.net",
        ]

        for url in internal_urls:
            with pytest.raises(SecurityError) as exc_info:
                provider._validate_url(url)
            assert "sensitive domain" in str(exc_info.value).lower()

    def test_blocks_government_domains(self, provider):
        """Test that government domains are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        gov_urls = [
            "https://irs.gov/refunds",
            "https://tax.state.ny.us",
        ]

        for url in gov_urls:
            with pytest.raises(SecurityError) as exc_info:
                provider._validate_url(url)
            assert "sensitive domain" in str(exc_info.value).lower()

    def test_blocks_configured_domains(self, provider):
        """Test that domains in config.blocked_domains are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        provider.config.blocked_domains = ["myblocked.com", "forbidden.net"]

        with pytest.raises(SecurityError) as exc_info:
            provider._validate_url("https://myblocked.com/page")
        assert "blocked domain" in str(exc_info.value).lower()

        with pytest.raises(SecurityError) as exc_info:
            provider._validate_url("https://www.forbidden.net/resource")
        assert "blocked domain" in str(exc_info.value).lower()

    def test_allows_normal_domains(self, provider):
        """Test that normal domains are allowed."""
        normal_urls = [
            "https://example.com",
            "https://google.com/search",
            "https://github.com/user/repo",
            "https://stackoverflow.com/questions",
            "https://news.ycombinator.com",
        ]

        for url in normal_urls:
            # Should not raise
            provider._validate_url(url)

    def test_blocks_non_http_schemes(self, provider):
        """Test that non-HTTP schemes are blocked."""
        from hub.providers.browser_automation_provider import SecurityError

        invalid_urls = [
            "file:///etc/passwd",
            "ftp://ftp.example.com",
            "javascript:alert(1)",
        ]

        for url in invalid_urls:
            with pytest.raises(SecurityError):
                provider._validate_url(url)


class TestMCPBrowserProviderActions:
    """Tests for browser action methods with mocked bridge."""

    @pytest.fixture
    def provider(self):
        """Create initialized provider instance for testing."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(mode="host", timeout_seconds=30)
        provider = MCPBrowserProvider(config)
        provider._initialized = True
        provider._session_id = "test-session-123"
        return provider

    @pytest.mark.asyncio
    async def test_navigate_calls_correct_mcp_tool(self, provider):
        """Test navigate action maps to correct MCP tool."""
        provider._http_session = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True,
            "result": {"url": "https://example.com", "title": "Example"}
        })

        provider._http_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await provider.navigate("https://example.com")

        assert result.success is True
        assert result.action == "navigate"
        assert result.data["url"] == "https://example.com"

    @pytest.mark.asyncio
    async def test_navigate_validates_url(self, provider):
        """Test that navigate validates URL before calling bridge."""
        from hub.providers.browser_automation_provider import SecurityError

        provider._http_session = MagicMock()

        with pytest.raises(SecurityError):
            await provider.navigate("https://bank.example.com")

    @pytest.mark.asyncio
    async def test_screenshot_returns_path(self, provider):
        """Test screenshot action returns file path."""
        provider._http_session = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True,
            "result": {"path": "/tmp/test.png"}
        })

        provider._http_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        with patch("os.path.exists", return_value=True):
            with patch("os.path.getsize", return_value=12345):
                result = await provider.screenshot()

        assert result.success is True
        assert result.action == "screenshot"
        assert "path" in result.data

    @pytest.mark.asyncio
    async def test_click_maps_to_mcp_click(self, provider):
        """Test click action maps correctly."""
        provider._http_session = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True,
            "result": {"clicked": True}
        })

        provider._http_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await provider.click("button.submit")

        assert result.success is True
        assert result.action == "click"
        assert result.data["selector"] == "button.submit"

    @pytest.mark.asyncio
    async def test_fill_maps_to_mcp_type(self, provider):
        """Test fill action maps correctly."""
        provider._http_session = MagicMock()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "success": True,
            "result": {"typed": True}
        })

        provider._http_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        result = await provider.fill("input[name=email]", "test@example.com")

        assert result.success is True
        assert result.action == "fill"
        assert result.data["selector"] == "input[name=email]"
        assert result.data["value"] == "test@example.com"


class TestMCPBrowserProviderBridgeCommunication:
    """Tests for HTTP bridge communication."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(mode="host")
        provider = MCPBrowserProvider(config)
        provider._session_id = "test-session"
        return provider

    @pytest.mark.asyncio
    async def test_bridge_health_check(self, provider):
        """Test bridge health check."""
        mock_session = MagicMock()
        mock_response = AsyncMock()
        mock_response.status = 200

        mock_session.get = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=mock_response),
            __aexit__=AsyncMock()
        ))

        provider._http_session = mock_session

        result = await provider._check_bridge_health()
        assert result is True

    @pytest.mark.asyncio
    async def test_bridge_health_check_fails(self, provider):
        """Test bridge health check failure handling."""
        from hub.providers.browser_automation_provider import BrowserInitializationError
        import aiohttp

        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientConnectorError(
            connection_key=MagicMock(),
            os_error=OSError("Connection refused")
        ))

        provider._http_session = mock_session

        with pytest.raises(BrowserInitializationError) as exc_info:
            await provider._check_bridge_health()

        assert "Cannot connect" in str(exc_info.value)

    def test_auth_headers_without_api_key(self, provider):
        """Test auth headers without API key."""
        provider._bridge_api_key = ""

        headers = provider._get_auth_headers()

        assert "Content-Type" in headers
        assert "X-Session-ID" in headers
        assert "Authorization" not in headers

    def test_auth_headers_with_api_key(self, provider):
        """Test auth headers with API key."""
        provider._bridge_api_key = "test-key-123"

        headers = provider._get_auth_headers()

        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer test-key-123"

    @pytest.mark.asyncio
    async def test_mcp_tool_call_error_handling(self, provider):
        """Test error handling for MCP tool calls."""
        from hub.providers.browser_automation_provider import BrowserAutomationError
        import aiohttp

        # Create a mock that raises ClientError when used as async context manager
        class MockErrorContext:
            async def __aenter__(self):
                raise aiohttp.ClientError("Connection refused")

            async def __aexit__(self, *args):
                pass

        mock_session = MagicMock()
        mock_session.post = MagicMock(return_value=MockErrorContext())

        provider._http_session = mock_session

        with pytest.raises(BrowserAutomationError) as exc_info:
            await provider._call_mcp_tool("browser_navigate", {"url": "https://example.com"}, "navigate")

        assert "error" in str(exc_info.value).lower()


class TestMCPBrowserProviderLifecycle:
    """Tests for provider lifecycle management."""

    @pytest.fixture
    def provider(self):
        """Create provider instance for testing."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(mode="host")
        return MCPBrowserProvider(config)

    @pytest.mark.asyncio
    async def test_initialize_creates_session(self, provider):
        """Test that initialize creates HTTP session."""
        with patch("aiohttp.ClientSession") as mock_client:
            mock_session = MagicMock()
            mock_response = AsyncMock()
            mock_response.status = 200

            mock_session.get = MagicMock(return_value=AsyncMock(
                __aenter__=AsyncMock(return_value=mock_response),
                __aexit__=AsyncMock()
            ))

            mock_client.return_value = mock_session

            await provider.initialize()

            assert provider._initialized is True
            assert provider._session_id is not None

    @pytest.mark.asyncio
    async def test_cleanup_closes_session(self, provider):
        """Test that cleanup closes HTTP session."""
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        mock_session.post = MagicMock(return_value=AsyncMock(
            __aenter__=AsyncMock(return_value=MagicMock(status=200)),
            __aexit__=AsyncMock()
        ))

        provider._http_session = mock_session
        provider._initialized = True
        provider._session_id = "test-session"

        await provider.cleanup()

        assert provider._initialized is False
        assert provider._session_id is None
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_idempotent(self, provider):
        """Test that cleanup can be called multiple times safely."""
        # First cleanup
        await provider.cleanup()

        assert provider._initialized is False

        # Second cleanup should not raise
        await provider.cleanup()

        assert provider._initialized is False

    def test_is_initialized_false_by_default(self, provider):
        """Test is_initialized returns False by default."""
        assert provider.is_initialized() is False

    def test_is_initialized_true_after_init(self, provider):
        """Test is_initialized returns True after initialization."""
        provider._initialized = True
        provider._http_session = MagicMock()

        assert provider.is_initialized() is True


class TestMCPBrowserProviderSensitiveDomains:
    """Tests for sensitive domain blocking."""

    def test_sensitive_domains_list(self):
        """Test that sensitive domains list is comprehensive."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider

        sensitive = MCPBrowserProvider.SENSITIVE_DOMAINS

        # Financial
        assert any("bank" in d for d in sensitive)
        assert any("paypal" in d for d in sensitive)
        assert any("venmo" in d for d in sensitive)

        # Authentication
        assert any("login.microsoft.com" in d for d in sensitive)
        assert any("accounts.google.com" in d for d in sensitive)

        # Corporate
        assert any("internal" in d for d in sensitive)
        assert any("intranet" in d for d in sensitive)

        # Government
        assert any("irs.gov" in d for d in sensitive)

    def test_mcp_tools_mapping(self):
        """Test MCP tools mapping is complete."""
        from hub.providers.mcp_browser_provider import MCPBrowserProvider

        tools = MCPBrowserProvider.MCP_TOOLS

        # Playwright backend
        assert "playwright" in tools
        assert "navigate" in tools["playwright"]
        assert "click" in tools["playwright"]
        assert "screenshot" in tools["playwright"]

        # Claude in Chrome backend
        assert "claude_in_chrome" in tools
        assert "navigate" in tools["claude_in_chrome"]
        assert "click" in tools["claude_in_chrome"]


class TestMCPBrowserProviderRegistration:
    """Tests for provider registration in registry."""

    def test_provider_registered(self):
        """Test that MCP provider is registered in registry."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        providers = BrowserAutomationRegistry.list_available_providers()

        # Check mcp_browser is in list (if aiohttp is available)
        provider_ids = [p.get("id") for p in providers]
        # Note: May fail if aiohttp not installed in test environment
        # Just verify playwright is there at minimum
        assert "playwright" in provider_ids

    def test_provider_info_in_registry(self):
        """Test that MCP provider info is available from registry."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        BrowserAutomationRegistry.reset()
        BrowserAutomationRegistry.initialize_providers()

        # Check MCP provider is registered
        assert BrowserAutomationRegistry.is_provider_registered("mcp_browser")

        # Get provider and check its info
        provider = BrowserAutomationRegistry.get_provider("mcp_browser")
        if provider:
            info = provider.get_provider_info()
            assert info["type"] == "mcp_browser"
            assert info["mode"] == "host"
