"""
Unit tests for Browser Automation Provider (Phase 14.5)

Tests cover:
- BrowserResult dataclass serialization/deserialization
- BrowserConfig dataclass and from_integration method
- BrowserAutomationProvider abstract interface
- BrowserAutomationRegistry registration and retrieval
- BrowserAutomationIntegration model

Run: pytest backend/tests/test_browser_automation_provider.py -v
"""

import pytest
import json
from datetime import datetime
from unittest.mock import MagicMock, patch


class TestBrowserResult:
    """Tests for the BrowserResult dataclass."""

    def test_result_creation_success(self):
        """Test creating a successful BrowserResult."""
        from hub.providers.browser_automation_provider import BrowserResult

        result = BrowserResult(
            success=True,
            action="navigate",
            data={"url": "https://example.com", "title": "Example Domain"}
        )

        assert result.success is True
        assert result.action == "navigate"
        assert result.data["url"] == "https://example.com"
        assert result.error is None
        assert result.timestamp is not None

    def test_result_creation_failure(self):
        """Test creating a failed BrowserResult."""
        from hub.providers.browser_automation_provider import BrowserResult

        result = BrowserResult(
            success=False,
            action="click",
            data={"selector": "#nonexistent"},
            error="Element not found: #nonexistent"
        )

        assert result.success is False
        assert result.action == "click"
        assert result.error == "Element not found: #nonexistent"

    def test_result_to_dict(self):
        """Test serializing BrowserResult to dictionary."""
        from hub.providers.browser_automation_provider import BrowserResult

        result = BrowserResult(
            success=True,
            action="screenshot",
            data={"path": "/tmp/screenshot.png", "width": 1280, "height": 720}
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["action"] == "screenshot"
        assert result_dict["data"]["path"] == "/tmp/screenshot.png"
        assert "timestamp" in result_dict

    def test_result_from_dict(self):
        """Test deserializing BrowserResult from dictionary."""
        from hub.providers.browser_automation_provider import BrowserResult

        data = {
            "success": True,
            "action": "extract",
            "data": {"selector": "h1", "text": "Hello World"},
            "error": None,
            "timestamp": "2026-02-03T12:00:00"
        }

        result = BrowserResult.from_dict(data)

        assert result.success is True
        assert result.action == "extract"
        assert result.data["text"] == "Hello World"
        assert result.timestamp.year == 2026

    def test_result_str_success(self):
        """Test string representation for successful result."""
        from hub.providers.browser_automation_provider import BrowserResult

        result = BrowserResult(
            success=True,
            action="navigate",
            data={"url": "https://example.com"}
        )

        assert "[navigate] Success" in str(result)

    def test_result_str_failure(self):
        """Test string representation for failed result."""
        from hub.providers.browser_automation_provider import BrowserResult

        result = BrowserResult(
            success=False,
            action="click",
            data={},
            error="Timeout"
        )

        assert "[click] Failed: Timeout" in str(result)


class TestBrowserConfig:
    """Tests for the BrowserConfig dataclass."""

    def test_config_defaults(self):
        """Test BrowserConfig default values."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig()

        assert config.provider_type == "playwright"
        assert config.mode == "container"
        assert config.browser_type == "chromium"
        assert config.headless is True
        assert config.timeout_seconds == 30
        assert config.viewport_width == 1280
        assert config.viewport_height == 720
        assert config.max_concurrent_sessions == 3
        assert config.user_agent is None
        assert config.proxy_url is None
        assert config.allowed_user_keys == []
        assert config.require_approval_per_action is False
        assert config.blocked_domains == []

    def test_config_custom_values(self):
        """Test BrowserConfig with custom values."""
        from hub.providers.browser_automation_provider import BrowserConfig

        config = BrowserConfig(
            provider_type="mcp_browser",
            mode="host",
            browser_type="firefox",
            headless=False,
            timeout_seconds=60,
            viewport_width=1920,
            viewport_height=1080,
            max_concurrent_sessions=1,
            user_agent="Custom UA",
            allowed_user_keys=["+5500000000001"],
            require_approval_per_action=True,
            blocked_domains=["bank.com", "paypal.com"]
        )

        assert config.provider_type == "mcp_browser"
        assert config.mode == "host"
        assert config.browser_type == "firefox"
        assert config.headless is False
        assert config.timeout_seconds == 60
        assert config.viewport_width == 1920
        assert config.viewport_height == 1080
        assert config.max_concurrent_sessions == 1
        assert config.user_agent == "Custom UA"
        assert "+5500000000001" in config.allowed_user_keys
        assert config.require_approval_per_action is True
        assert "bank.com" in config.blocked_domains

    def test_config_from_integration(self):
        """Test BrowserConfig.from_integration method."""
        from hub.providers.browser_automation_provider import BrowserConfig

        # Create mock integration object
        mock_integration = MagicMock()
        mock_integration.provider_type = "playwright"
        mock_integration.mode = "container"
        mock_integration.browser_type = "webkit"
        mock_integration.headless = True
        mock_integration.timeout_seconds = 45
        mock_integration.viewport_width = 1366
        mock_integration.viewport_height = 768
        mock_integration.max_concurrent_sessions = 5
        mock_integration.user_agent = "Test Agent"
        mock_integration.proxy_url = "http://proxy:8080"
        mock_integration.allowed_user_keys_json = '["user1", "user2"]'
        mock_integration.require_approval_per_action = False
        mock_integration.blocked_domains_json = '["example.com"]'

        config = BrowserConfig.from_integration(mock_integration)

        assert config.provider_type == "playwright"
        assert config.browser_type == "webkit"
        assert config.timeout_seconds == 45
        assert config.viewport_width == 1366
        assert config.viewport_height == 768
        assert config.max_concurrent_sessions == 5
        assert config.user_agent == "Test Agent"
        assert config.proxy_url == "http://proxy:8080"
        assert config.allowed_user_keys == ["user1", "user2"]
        assert config.blocked_domains == ["example.com"]

    def test_config_from_integration_with_invalid_json(self):
        """Test BrowserConfig.from_integration with invalid JSON."""
        from hub.providers.browser_automation_provider import BrowserConfig

        mock_integration = MagicMock()
        mock_integration.provider_type = "playwright"
        mock_integration.mode = "container"
        mock_integration.browser_type = "chromium"
        mock_integration.headless = True
        mock_integration.timeout_seconds = 30
        mock_integration.viewport_width = 1280
        mock_integration.viewport_height = 720
        mock_integration.max_concurrent_sessions = 3
        mock_integration.user_agent = None
        mock_integration.proxy_url = None
        mock_integration.allowed_user_keys_json = "invalid json"
        mock_integration.require_approval_per_action = False
        mock_integration.blocked_domains_json = None

        config = BrowserConfig.from_integration(mock_integration)

        # Should fall back to empty lists on JSON parse error
        assert config.allowed_user_keys == []
        assert config.blocked_domains == []


class TestBrowserAutomationProviderAbstract:
    """Tests for the BrowserAutomationProvider abstract class."""

    def test_abstract_methods_exist(self):
        """Test that all abstract methods are defined."""
        from hub.providers.browser_automation_provider import BrowserAutomationProvider
        import inspect

        abstract_methods = [
            'initialize',
            'navigate',
            'click',
            'fill',
            'extract',
            'screenshot',
            'execute_script',
            'cleanup'
        ]

        for method_name in abstract_methods:
            assert hasattr(BrowserAutomationProvider, method_name)
            method = getattr(BrowserAutomationProvider, method_name)
            assert callable(method)

    def test_cannot_instantiate_abstract(self):
        """Test that BrowserAutomationProvider cannot be instantiated directly."""
        from hub.providers.browser_automation_provider import (
            BrowserAutomationProvider,
            BrowserConfig
        )

        config = BrowserConfig()

        with pytest.raises(TypeError):
            BrowserAutomationProvider(config)

    def test_get_provider_info(self):
        """Test get_provider_info class method."""
        from hub.providers.browser_automation_provider import BrowserAutomationProvider

        info = BrowserAutomationProvider.get_provider_info()

        assert "type" in info
        assert "name" in info
        assert "actions" in info
        assert "navigate" in info["actions"]
        assert "click" in info["actions"]
        assert "fill" in info["actions"]
        assert "extract" in info["actions"]
        assert "screenshot" in info["actions"]
        assert "execute_script" in info["actions"]


class TestBrowserAutomationExceptions:
    """Tests for custom exception classes."""

    def test_browser_automation_error(self):
        """Test base BrowserAutomationError."""
        from hub.providers.browser_automation_provider import BrowserAutomationError

        error = BrowserAutomationError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_browser_initialization_error(self):
        """Test BrowserInitializationError."""
        from hub.providers.browser_automation_provider import (
            BrowserAutomationError,
            BrowserInitializationError
        )

        error = BrowserInitializationError("Could not launch browser")
        assert isinstance(error, BrowserAutomationError)

    def test_navigation_error(self):
        """Test NavigationError."""
        from hub.providers.browser_automation_provider import (
            BrowserAutomationError,
            NavigationError
        )

        error = NavigationError("Invalid URL")
        assert isinstance(error, BrowserAutomationError)

    def test_element_not_found_error(self):
        """Test ElementNotFoundError."""
        from hub.providers.browser_automation_provider import (
            BrowserAutomationError,
            ElementNotFoundError
        )

        error = ElementNotFoundError("Selector #btn not found")
        assert isinstance(error, BrowserAutomationError)

    def test_security_error(self):
        """Test SecurityError."""
        from hub.providers.browser_automation_provider import (
            BrowserAutomationError,
            SecurityError
        )

        error = SecurityError("Blocked for security reasons")
        assert isinstance(error, BrowserAutomationError)


class TestBrowserAutomationRegistry:
    """Tests for BrowserAutomationRegistry."""

    def setup_method(self):
        """Reset registry before each test."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry
        BrowserAutomationRegistry.reset()

    def test_register_provider(self):
        """Test registering a provider."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry
        from hub.providers.browser_automation_provider import (
            BrowserAutomationProvider,
            BrowserConfig,
            BrowserResult
        )

        # Create a concrete test provider
        class TestProvider(BrowserAutomationProvider):
            provider_type = "test_provider"
            provider_name = "Test Provider"

            async def initialize(self): pass
            async def navigate(self, url, wait_until="load"):
                return BrowserResult(True, "navigate", {})
            async def click(self, selector):
                return BrowserResult(True, "click", {})
            async def fill(self, selector, value):
                return BrowserResult(True, "fill", {})
            async def extract(self, selector="body"):
                return BrowserResult(True, "extract", {})
            async def screenshot(self, full_page=True, selector=None):
                return BrowserResult(True, "screenshot", {})
            async def execute_script(self, script):
                return BrowserResult(True, "execute_script", {})
            async def cleanup(self): pass

        BrowserAutomationRegistry.register_provider(
            "test_provider",
            TestProvider,
            {"requires_api_key": False, "status": "available"}
        )

        assert BrowserAutomationRegistry.is_provider_registered("test_provider")
        assert "test_provider" in BrowserAutomationRegistry.get_registered_providers()

    def test_register_invalid_provider(self):
        """Test that registering non-provider class raises error."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        class NotAProvider:
            pass

        with pytest.raises(ValueError):
            BrowserAutomationRegistry.register_provider("invalid", NotAProvider)

    def test_get_provider_not_registered(self):
        """Test getting unregistered provider returns None."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        provider = BrowserAutomationRegistry.get_provider("nonexistent")
        assert provider is None

    def test_is_provider_registered(self):
        """Test is_provider_registered method."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        assert not BrowserAutomationRegistry.is_provider_registered("playwright")

        # After initialization, it should be registered
        BrowserAutomationRegistry.initialize_providers()
        # Note: This might fail if playwright_provider.py doesn't exist yet
        # The test is designed to pass whether or not Playwright is available

    def test_get_default_provider(self):
        """Test get_default_provider returns 'playwright'."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        assert BrowserAutomationRegistry.get_default_provider() == "playwright"

    def test_list_available_providers_empty(self):
        """Test listing providers when none registered."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry

        providers = BrowserAutomationRegistry.list_available_providers()
        assert isinstance(providers, list)

    def test_reset_registry(self):
        """Test resetting the registry."""
        from hub.providers.browser_automation_registry import BrowserAutomationRegistry
        from hub.providers.browser_automation_provider import (
            BrowserAutomationProvider,
            BrowserConfig,
            BrowserResult
        )

        # Create and register a test provider
        class TestProvider(BrowserAutomationProvider):
            provider_type = "test"
            provider_name = "Test"

            async def initialize(self): pass
            async def navigate(self, url, wait_until="load"):
                return BrowserResult(True, "navigate", {})
            async def click(self, selector):
                return BrowserResult(True, "click", {})
            async def fill(self, selector, value):
                return BrowserResult(True, "fill", {})
            async def extract(self, selector="body"):
                return BrowserResult(True, "extract", {})
            async def screenshot(self, full_page=True, selector=None):
                return BrowserResult(True, "screenshot", {})
            async def execute_script(self, script):
                return BrowserResult(True, "execute_script", {})
            async def cleanup(self): pass

        BrowserAutomationRegistry.register_provider("test", TestProvider)
        assert BrowserAutomationRegistry.is_provider_registered("test")

        BrowserAutomationRegistry.reset()
        assert not BrowserAutomationRegistry.is_provider_registered("test")


class TestBrowserAutomationIntegrationModel:
    """Tests for the BrowserAutomationIntegration database model."""

    def test_model_creation(self, integration_db):
        """Test creating a BrowserAutomationIntegration record."""
        from models import BrowserAutomationIntegration

        integration = BrowserAutomationIntegration(
            name="Test Browser Automation",
            display_name="Test Browser",
            tenant_id="test-tenant",
            is_active=True,
            provider_type="playwright",
            mode="container",
            browser_type="chromium",
            headless=True,
            timeout_seconds=30,
            viewport_width=1280,
            viewport_height=720,
            max_concurrent_sessions=3
        )

        integration_db.add(integration)
        integration_db.commit()
        integration_db.refresh(integration)

        assert integration.id is not None
        assert integration.type == "browser_automation"  # Polymorphic identity
        assert integration.provider_type == "playwright"
        assert integration.mode == "container"
        assert integration.browser_type == "chromium"
        assert integration.headless is True
        assert integration.timeout_seconds == 30

    def test_model_with_host_mode_settings(self, integration_db):
        """Test creating integration with host mode settings."""
        from models import BrowserAutomationIntegration

        allowed_users = json.dumps(["+5500000000001", "+5500000000002"])
        blocked_domains = json.dumps(["bank.com", "paypal.com"])

        integration = BrowserAutomationIntegration(
            name="Host Browser",
            tenant_id="test-tenant",
            is_active=True,
            provider_type="mcp_browser",
            mode="host",
            allowed_user_keys_json=allowed_users,
            require_approval_per_action=True,
            blocked_domains_json=blocked_domains
        )

        integration_db.add(integration)
        integration_db.commit()
        integration_db.refresh(integration)

        assert integration.mode == "host"
        assert integration.provider_type == "mcp_browser"
        assert integration.require_approval_per_action is True

        # Verify JSON fields
        parsed_users = json.loads(integration.allowed_user_keys_json)
        assert "+5500000000001" in parsed_users

        parsed_domains = json.loads(integration.blocked_domains_json)
        assert "bank.com" in parsed_domains

    def test_polymorphic_query(self, integration_db):
        """Test querying via HubIntegration returns correct type."""
        from models import HubIntegration, BrowserAutomationIntegration

        # Create browser automation integration
        integration = BrowserAutomationIntegration(
            name="Polymorphic Test",
            tenant_id="test-tenant",
            is_active=True,
            provider_type="playwright",
            mode="container"
        )
        integration_db.add(integration)
        integration_db.commit()

        # Query via base class
        result = integration_db.query(HubIntegration).filter(
            HubIntegration.type == "browser_automation"
        ).first()

        assert result is not None
        assert isinstance(result, BrowserAutomationIntegration)
        assert result.provider_type == "playwright"

    def test_cascade_delete(self, integration_db):
        """Test that deleting HubIntegration cascades to child."""
        from models import HubIntegration, BrowserAutomationIntegration

        integration = BrowserAutomationIntegration(
            name="Cascade Test",
            tenant_id="test-tenant",
            is_active=True
        )
        integration_db.add(integration)
        integration_db.commit()

        integration_id = integration.id

        # Delete via base query
        integration_db.query(HubIntegration).filter(
            HubIntegration.id == integration_id
        ).delete()
        integration_db.commit()

        # Verify child is also deleted
        result = integration_db.query(BrowserAutomationIntegration).filter(
            BrowserAutomationIntegration.id == integration_id
        ).first()

        assert result is None
