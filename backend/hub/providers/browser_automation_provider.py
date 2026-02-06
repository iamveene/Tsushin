"""
Browser Automation Provider - Abstract Base Class

Phase 14.5: Browser Automation Skill - Core Infrastructure

This module defines the abstract interface for browser automation providers.
All concrete providers (Playwright, MCP Browser, etc.) must implement this interface.

Supported actions:
1. navigate(url, wait_until) - Navigate to URL with wait conditions
2. click(selector) - Click element by CSS selector
3. fill(selector, value) - Fill form input fields
4. extract(selector) - Extract text content from elements
5. screenshot(full_page, selector) - Capture screenshots
6. execute_script(script) - Execute JavaScript in page context
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class BrowserResult:
    """
    Standardized result from browser automation actions.

    All provider actions return this dataclass for consistent handling.

    Attributes:
        success: Whether the action completed successfully
        action: Name of the action performed (e.g., "navigate", "click")
        data: Action-specific result data
        error: Error message if action failed (None if success)
        timestamp: When the action completed
    """
    success: bool
    action: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for JSON storage/transmission."""
        return {
            'success': self.success,
            'action': self.action,
            'data': self.data,
            'error': self.error,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrowserResult':
        """Deserialize result from JSON."""
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        return cls(
            success=data.get('success', False),
            action=data.get('action', 'unknown'),
            data=data.get('data', {}),
            error=data.get('error'),
            timestamp=timestamp or datetime.utcnow()
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.success:
            return f"[{self.action}] Success: {self.data}"
        return f"[{self.action}] Failed: {self.error}"


@dataclass
class BrowserConfig:
    """
    Configuration for browser automation providers.

    Extracted from BrowserAutomationIntegration model for provider initialization.
    """
    provider_type: str = "playwright"
    mode: str = "container"  # "container" or "host"
    browser_type: str = "chromium"  # "chromium", "firefox", or "webkit"
    headless: bool = True
    timeout_seconds: int = 30
    viewport_width: int = 1280
    viewport_height: int = 720
    max_concurrent_sessions: int = 3
    user_agent: Optional[str] = None
    proxy_url: Optional[str] = None

    # Host mode settings (Phase 8)
    allowed_user_keys: List[str] = field(default_factory=list)
    require_approval_per_action: bool = False

    # Security settings
    blocked_domains: List[str] = field(default_factory=list)

    @classmethod
    def from_integration(cls, integration) -> 'BrowserConfig':
        """Create config from BrowserAutomationIntegration model."""
        import json

        allowed_keys = []
        if hasattr(integration, 'allowed_user_keys_json') and integration.allowed_user_keys_json:
            try:
                allowed_keys = json.loads(integration.allowed_user_keys_json)
            except (json.JSONDecodeError, TypeError):
                allowed_keys = []

        blocked = []
        if hasattr(integration, 'blocked_domains_json') and integration.blocked_domains_json:
            try:
                blocked = json.loads(integration.blocked_domains_json)
            except (json.JSONDecodeError, TypeError):
                blocked = []

        return cls(
            provider_type=getattr(integration, 'provider_type', 'playwright'),
            mode=getattr(integration, 'mode', 'container'),
            browser_type=getattr(integration, 'browser_type', 'chromium'),
            headless=getattr(integration, 'headless', True),
            timeout_seconds=getattr(integration, 'timeout_seconds', 30),
            viewport_width=getattr(integration, 'viewport_width', 1280),
            viewport_height=getattr(integration, 'viewport_height', 720),
            max_concurrent_sessions=getattr(integration, 'max_concurrent_sessions', 3),
            user_agent=getattr(integration, 'user_agent', None),
            proxy_url=getattr(integration, 'proxy_url', None),
            allowed_user_keys=allowed_keys,
            require_approval_per_action=getattr(integration, 'require_approval_per_action', False),
            blocked_domains=blocked
        )


class BrowserAutomationProvider(ABC):
    """
    Abstract base class for browser automation providers.

    All concrete providers must implement the 6 core actions plus lifecycle methods.
    Providers are instantiated per-request and must handle cleanup properly.

    Class Attributes:
        provider_type: Unique identifier for this provider (e.g., "playwright", "mcp_browser")
        provider_name: Human-readable name for display

    Usage:
        provider = PlaywrightProvider(config)
        await provider.initialize()
        try:
            result = await provider.navigate("https://example.com")
            screenshot = await provider.screenshot()
        finally:
            await provider.cleanup()
    """

    provider_type: str = "base"
    provider_name: str = "Base Provider"

    def __init__(self, config: BrowserConfig):
        """
        Initialize provider with configuration.

        Args:
            config: BrowserConfig instance with provider settings
        """
        self.config = config

    @abstractmethod
    async def initialize(self) -> None:
        """
        Launch or connect to browser instance.

        This method must be called before any actions.
        Should handle browser launch, context creation, and page setup.

        Raises:
            BrowserInitializationError: If browser cannot be started
        """
        pass

    @abstractmethod
    async def navigate(self, url: str, wait_until: str = "load") -> BrowserResult:
        """
        Navigate to a URL.

        Args:
            url: Target URL (must be valid HTTP/HTTPS)
            wait_until: Wait condition - "load", "domcontentloaded", or "networkidle"

        Returns:
            BrowserResult with data containing:
                - url: Final URL after any redirects
                - title: Page title

        Raises:
            TimeoutError: If navigation exceeds timeout
            NavigationError: If URL is invalid or blocked
        """
        pass

    @abstractmethod
    async def click(self, selector: str) -> BrowserResult:
        """
        Click an element by CSS selector.

        Args:
            selector: CSS selector for target element

        Returns:
            BrowserResult with data containing:
                - selector: The selector that was clicked

        Raises:
            ElementNotFoundError: If selector doesn't match any element
            TimeoutError: If element doesn't become clickable
        """
        pass

    @abstractmethod
    async def fill(self, selector: str, value: str) -> BrowserResult:
        """
        Fill a form input field.

        Args:
            selector: CSS selector for input element
            value: Text value to fill

        Returns:
            BrowserResult with data containing:
                - selector: The selector that was filled
                - value: The value that was entered

        Raises:
            ElementNotFoundError: If selector doesn't match any element
            InvalidElementError: If element is not fillable
        """
        pass

    @abstractmethod
    async def extract(self, selector: str = "body") -> BrowserResult:
        """
        Extract text content from an element.

        Args:
            selector: CSS selector for target element (defaults to body)

        Returns:
            BrowserResult with data containing:
                - selector: The selector used
                - text: Extracted text content
                - html: Raw HTML (optional)

        Raises:
            ElementNotFoundError: If selector doesn't match any element
        """
        pass

    @abstractmethod
    async def screenshot(
        self,
        full_page: bool = True,
        selector: Optional[str] = None
    ) -> BrowserResult:
        """
        Capture a screenshot of the page or element.

        Args:
            full_page: If True, capture entire scrollable page
            selector: If provided, capture only this element

        Returns:
            BrowserResult with data containing:
                - path: Absolute path to saved PNG file
                - full_page: Whether full page was captured
                - width: Image width in pixels
                - height: Image height in pixels

        Raises:
            ElementNotFoundError: If selector provided but not found
            ScreenshotError: If screenshot capture fails
        """
        pass

    @abstractmethod
    async def execute_script(self, script: str) -> BrowserResult:
        """
        Execute JavaScript in the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            BrowserResult with data containing:
                - result: Return value of the script (JSON-serializable)

        Raises:
            ScriptExecutionError: If JavaScript throws an error
            SecurityError: If script is blocked for security reasons
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Close browser and cleanup all resources.

        This method MUST be called when done with the provider,
        typically in a finally block. Must be idempotent (safe to call multiple times).

        Should cleanup:
            - Page handles
            - Browser contexts
            - Browser process
            - Temporary files
        """
        pass

    # Optional methods with default implementations

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        raise NotImplementedError("Subclass should implement get_current_url()")

    async def get_page_title(self) -> str:
        """Get the current page title."""
        raise NotImplementedError("Subclass should implement get_page_title()")

    def is_initialized(self) -> bool:
        """Check if browser is initialized and ready."""
        return False

    @classmethod
    def get_provider_info(cls) -> Dict[str, Any]:
        """Get provider metadata for registration/display."""
        return {
            'type': cls.provider_type,
            'name': cls.provider_name,
            'actions': ['navigate', 'click', 'fill', 'extract', 'screenshot', 'execute_script']
        }


# Custom exceptions for browser automation

class BrowserAutomationError(Exception):
    """Base exception for browser automation errors."""
    pass


class BrowserInitializationError(BrowserAutomationError):
    """Raised when browser cannot be initialized."""
    pass


class NavigationError(BrowserAutomationError):
    """Raised when navigation fails."""
    pass


class ElementNotFoundError(BrowserAutomationError):
    """Raised when an element selector doesn't match any element."""
    pass


class TimeoutError(BrowserAutomationError):
    """Raised when an operation times out."""
    pass


class ScriptExecutionError(BrowserAutomationError):
    """Raised when JavaScript execution fails."""
    pass


class SecurityError(BrowserAutomationError):
    """Raised when an action is blocked for security reasons."""
    pass
