"""
Browser Automation Provider - Abstract Base Class

Phase 14.5: Browser Automation Skill - Core Infrastructure
Phase 35:   Enhanced actions, session persistence, multi-tab, vision, error recovery

This module defines the abstract interface for browser automation providers.
All concrete providers (Playwright, MCP Browser, etc.) must implement this interface.

Supported actions (Phase 35b expansion):
 1. navigate(url, wait_until)        - Navigate to URL with wait conditions
 2. click(selector)                  - Click element by CSS selector
 3. fill(selector, value)            - Fill form input fields
 4. extract(selector)                - Extract text content from elements
 5. screenshot(full_page, selector)  - Capture screenshots
 6. execute_script(script)           - Execute JavaScript in page context
 7. scroll(selector, x, y)           - Scroll page or element
 8. select_option(selector, value)   - Select dropdown option
 9. hover(selector)                  - Hover over element
10. wait_for(selector, state, timeout_ms) - Wait for element state
11. go_back()                        - Navigate back in history
12. go_forward()                     - Navigate forward in history
13. get_attribute(selector, attribute) - Read element attribute
14. get_page_url()                   - Get current page URL
15. type_text(selector, text, delay_ms) - Type text character-by-character
16. open_tab(url)                    - Open new browser tab (35c)
17. switch_tab(tab_id)               - Switch active tab (35c)
18. close_tab(tab_id)                - Close a tab (35c)
19. list_tabs()                      - List all open tabs (35c)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime


# ---------------------------------------------------------------------------
# 35f: Structured error codes and classification
# ---------------------------------------------------------------------------

class BrowserErrorCode(str, Enum):
    """Structured error codes for browser automation failures."""
    NAVIGATION_TIMEOUT   = "navigation_timeout"
    ELEMENT_NOT_FOUND    = "element_not_found"
    PAGE_LOAD_FAILED     = "page_load_failed"
    SECURITY_BLOCKED     = "security_blocked"
    BROWSER_CRASH        = "browser_crash"
    SELECTOR_INVALID     = "selector_invalid"
    NETWORK_ERROR        = "network_error"
    SESSION_EXPIRED      = "session_expired"
    TAB_NOT_FOUND        = "tab_not_found"
    MAX_SESSIONS         = "max_sessions"
    UNKNOWN              = "unknown"


_ERROR_SUGGESTIONS: Dict[BrowserErrorCode, List[str]] = {
    BrowserErrorCode.NAVIGATION_TIMEOUT: [
        "Try wait_until='domcontentloaded' instead of 'load' for slow sites",
        "The site may be slow — consider increasing timeout_seconds",
    ],
    BrowserErrorCode.ELEMENT_NOT_FOUND: [
        "Verify the CSS selector — use extract() to inspect the page DOM first",
        "Try a broader selector (e.g., 'button' instead of '#specific-id')",
        "The element may not be visible yet — use wait_for(selector) before interacting",
    ],
    BrowserErrorCode.SECURITY_BLOCKED: [
        "Private IP addresses and internal hostnames are blocked for security",
        "Only public HTTP/HTTPS URLs are permitted",
    ],
    BrowserErrorCode.PAGE_LOAD_FAILED: [
        "Check that the URL is correct and publicly accessible",
        "Ensure the URL starts with http:// or https://",
    ],
    BrowserErrorCode.BROWSER_CRASH: [
        "The browser process crashed — retry the action to launch a fresh instance",
    ],
    BrowserErrorCode.SESSION_EXPIRED: [
        "The browser session expired due to idle timeout — the next request will open a fresh session",
    ],
    BrowserErrorCode.TAB_NOT_FOUND: [
        "Use list_tabs() to see available tab IDs",
    ],
    BrowserErrorCode.MAX_SESSIONS: [
        "Close an existing browser session before opening a new one",
    ],
    BrowserErrorCode.NETWORK_ERROR: [
        "The site may be temporarily unreachable — retry in a few seconds",
    ],
    BrowserErrorCode.UNKNOWN: [
        "Check the action parameters and retry",
    ],
}


def classify_error(exception: Exception, action: str) -> Tuple[BrowserErrorCode, List[str]]:
    """Map an exception to a structured error code + actionable suggestions."""
    msg = str(exception).lower()

    nav_actions = ("navigate", "go_back", "go_forward")
    element_actions = ("click", "fill", "hover", "select_option", "type_text", "wait_for", "get_attribute", "extract", "scroll")

    if isinstance(exception, SecurityError):
        code = BrowserErrorCode.SECURITY_BLOCKED
    elif isinstance(exception, (TimeoutError, )):
        code = BrowserErrorCode.NAVIGATION_TIMEOUT if action in nav_actions else BrowserErrorCode.ELEMENT_NOT_FOUND
    elif "timeout" in msg or "waiting for locator" in msg or "waiting for selector" in msg:
        code = BrowserErrorCode.NAVIGATION_TIMEOUT if action in nav_actions else BrowserErrorCode.ELEMENT_NOT_FOUND
    elif isinstance(exception, ElementNotFoundError) or "not found" in msg or "no element" in msg:
        code = BrowserErrorCode.ELEMENT_NOT_FOUND
    elif action in element_actions and ("locator" in msg or "selector" in msg or "resolved to" in msg or "not clickable" in msg or "not fillable" in msg):
        code = BrowserErrorCode.ELEMENT_NOT_FOUND
    elif isinstance(exception, NavigationError) or "net::" in msg or "err_" in msg:
        code = BrowserErrorCode.PAGE_LOAD_FAILED
    elif "crash" in msg or "target closed" in msg or "browser has been closed" in msg:
        code = BrowserErrorCode.BROWSER_CRASH
    elif isinstance(exception, BrowserInitializationError):
        code = BrowserErrorCode.BROWSER_CRASH
    else:
        # Default: if it's an element action, assume element issue
        code = BrowserErrorCode.ELEMENT_NOT_FOUND if action in element_actions else BrowserErrorCode.UNKNOWN

    return code, list(_ERROR_SUGGESTIONS.get(code, _ERROR_SUGGESTIONS[BrowserErrorCode.UNKNOWN]))


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
        error_code: Structured error classification (35f)
        suggestions: Actionable hints for the LLM to self-correct (35f)
        timestamp: When the action completed
    """
    success: bool
    action: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[BrowserErrorCode] = None
    suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize result for JSON storage/transmission."""
        return {
            'success': self.success,
            'action': self.action,
            'data': self.data,
            'error': self.error,
            'error_code': self.error_code.value if self.error_code else None,
            'suggestions': self.suggestions,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BrowserResult':
        """Deserialize result from JSON."""
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        error_code_val = data.get('error_code')
        error_code = BrowserErrorCode(error_code_val) if error_code_val else None
        return cls(
            success=data.get('success', False),
            action=data.get('action', 'unknown'),
            data=data.get('data', {}),
            error=data.get('error'),
            error_code=error_code,
            suggestions=data.get('suggestions', []),
            timestamp=timestamp or datetime.utcnow()
        )

    def __str__(self) -> str:
        """Human-readable string representation."""
        if self.success:
            return f"[{self.action}] Success: {self.data}"
        code_str = f" [{self.error_code.value}]" if self.error_code else ""
        return f"[{self.action}] Failed{code_str}: {self.error}"


@dataclass
class BrowserConfig:
    """
    Configuration for browser automation providers.

    Extracted from BrowserAutomationIntegration model for provider initialization.
    """
    provider_type: str = "playwright"
    mode: str = "container"
    browser_type: str = "chromium"  # "chromium", "firefox", or "webkit"
    headless: bool = True
    timeout_seconds: int = 30
    viewport_width: int = 1280
    viewport_height: int = 720
    max_concurrent_sessions: int = 3
    user_agent: Optional[str] = None
    proxy_url: Optional[str] = None

    # Security settings
    blocked_domains: List[str] = field(default_factory=list)

    # Session persistence (Phase 35a)
    session_persistence: bool = False
    session_ttl_seconds: int = 300

    # CDP mode
    cdp_url: str = "http://host.docker.internal:9222"

    @classmethod
    def from_integration(cls, integration) -> 'BrowserConfig':
        """Create config from BrowserAutomationIntegration model."""
        import json

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
            blocked_domains=blocked,
            session_persistence=getattr(integration, 'session_persistence', False),
            session_ttl_seconds=getattr(integration, 'session_ttl_seconds', 300),
            cdp_url=getattr(integration, 'cdp_url', 'http://host.docker.internal:9222'),
        )


class BrowserAutomationProvider(ABC):
    """
    Abstract base class for browser automation providers.

    All concrete providers must implement the 6 core actions plus lifecycle methods.
    Providers are instantiated per-request and must handle cleanup properly.

    Class Attributes:
        provider_type: Unique identifier for this provider (e.g., "playwright")
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

    # -----------------------------------------------------------------------
    # 35b: Rich action set (9 new actions)
    # -----------------------------------------------------------------------

    @abstractmethod
    async def scroll(self, selector: str = "body", x: int = 0, y: int = 300) -> BrowserResult:
        """Scroll page or element by (x, y) pixels."""
        pass

    @abstractmethod
    async def select_option(self, selector: str, value: str) -> BrowserResult:
        """Select a dropdown option by value."""
        pass

    @abstractmethod
    async def hover(self, selector: str) -> BrowserResult:
        """Hover over an element (triggers tooltips, menus)."""
        pass

    @abstractmethod
    async def wait_for(self, selector: str, state: str = "visible", timeout_ms: Optional[int] = None) -> BrowserResult:
        """Wait for element to reach a state: visible, hidden, attached, detached."""
        pass

    @abstractmethod
    async def go_back(self) -> BrowserResult:
        """Navigate back in browser history."""
        pass

    @abstractmethod
    async def go_forward(self) -> BrowserResult:
        """Navigate forward in browser history."""
        pass

    @abstractmethod
    async def get_attribute(self, selector: str, attribute: str) -> BrowserResult:
        """Read an attribute value from an element."""
        pass

    @abstractmethod
    async def get_page_url(self) -> BrowserResult:
        """Get current page URL as a BrowserResult."""
        pass

    @abstractmethod
    async def type_text(self, selector: str, text: str, delay_ms: int = 0) -> BrowserResult:
        """Type text character-by-character (triggers autocomplete/reactive inputs)."""
        pass

    # -----------------------------------------------------------------------
    # 35c: Multi-tab support (4 new actions)
    # -----------------------------------------------------------------------

    @abstractmethod
    async def open_tab(self, url: Optional[str] = None) -> BrowserResult:
        """Open a new browser tab, optionally navigating to url."""
        pass

    @abstractmethod
    async def switch_tab(self, tab_id: str) -> BrowserResult:
        """Switch active page context to specified tab."""
        pass

    @abstractmethod
    async def close_tab(self, tab_id: str) -> BrowserResult:
        """Close a tab by ID (cannot close last tab)."""
        pass

    @abstractmethod
    async def list_tabs(self) -> BrowserResult:
        """List all open tabs with their URLs."""
        pass

    # -----------------------------------------------------------------------
    # Optional methods with default implementations
    # -----------------------------------------------------------------------

    async def get_current_url(self) -> str:
        """Get the current page URL (legacy — prefer get_page_url() action)."""
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
            'actions': [
                'navigate', 'click', 'fill', 'extract', 'screenshot', 'execute_script',
                'scroll', 'select_option', 'hover', 'wait_for', 'go_back', 'go_forward',
                'get_attribute', 'get_page_url', 'type_text',
                'open_tab', 'switch_tab', 'close_tab', 'list_tabs',
            ],
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
