"""
MCP Browser Automation Provider

Phase 8: Browser Automation Skill - Host Mode Implementation

Host browser automation via MCP HTTP Bridge.
Provides access to user's authenticated browser sessions.

Communication:
    Backend (Docker) --HTTP--> MCP HTTP Bridge (Host) --MCP--> Browser

Supported MCP backends:
    - Playwright MCP (mcp__plugin_playwright_playwright__)
    - Claude in Chrome (mcp__Claude_in_Chrome__)

Security features:
    - Whitelist-based user authorization
    - Sensitive domain blocking
    - Comprehensive audit logging
    - URL sanitization
"""

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from .browser_automation_provider import (
    BrowserAutomationProvider,
    BrowserConfig,
    BrowserResult,
    BrowserAutomationError,
    BrowserInitializationError,
    NavigationError,
    ElementNotFoundError,
    TimeoutError as BrowserTimeoutError,
    ScriptExecutionError,
    SecurityError,
)

logger = logging.getLogger(__name__)


class MCPBrowserProvider(BrowserAutomationProvider):
    """
    MCP-based browser automation provider for host browser control.

    Connects to the user's actual browser via MCP HTTP Bridge,
    enabling access to authenticated sessions (Gmail, dashboards, etc.).

    Security:
        - Only users in allowed_user_keys whitelist can use this provider
        - Sensitive domains (banking, auth) are blocked by default
        - All actions are logged to HostBrowserAuditLog

    Requirements:
        - MCP HTTP Bridge running on host machine
        - User's browser with MCP extension/server active
    """

    provider_type = "mcp_browser"
    provider_name = "MCP Browser (Host)"

    # Default bridge URL (host.docker.internal for Docker -> Host communication)
    DEFAULT_BRIDGE_URL = "http://host.docker.internal:8765"

    # Sensitive domains that require explicit approval
    SENSITIVE_DOMAINS = [
        # Financial
        "bank", "paypal", "venmo", "zelle", "cashapp", "coinbase",
        "chase", "wellsfargo", "bankofamerica", "citibank",
        # Authentication
        "login.microsoft.com", "accounts.google.com", "auth0.com",
        "okta", "sso.", "oauth",
        # Corporate/Internal
        "internal", "intranet", "corp.", "admin.",
        # Government
        "irs.gov", ".gov/", "tax",
        # Healthcare
        "mychart", "portal.health", "epic.com",
    ]

    # MCP tool mapping for different backends
    MCP_TOOLS = {
        "playwright": {
            "navigate": "browser_navigate",
            "click": "browser_click",
            "type": "browser_type",
            "screenshot": "browser_take_screenshot",
            "snapshot": "browser_snapshot",
            "evaluate": "browser_evaluate",
        },
        "claude_in_chrome": {
            "navigate": "navigate",
            "click": "computer",
            "type": "form_input",
            "screenshot": "computer",
            "snapshot": "read_page",
            "evaluate": "javascript_tool",
        }
    }

    def __init__(self, config: BrowserConfig):
        """
        Initialize MCP Browser provider with configuration.

        Args:
            config: BrowserConfig with host mode settings
        """
        super().__init__(config)

        # Bridge configuration
        self._bridge_url = os.getenv("MCP_BRIDGE_URL", self.DEFAULT_BRIDGE_URL)
        self._bridge_api_key = os.getenv("MCP_BRIDGE_API_KEY", "")

        # MCP backend (playwright or claude_in_chrome)
        self._mcp_backend = "playwright"  # Default to Playwright MCP

        # Session state
        self._session_id: Optional[str] = None
        self._tab_id: Optional[int] = None
        self._initialized = False
        self._http_session: Optional[aiohttp.ClientSession] = None

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Shared screenshot directory
        self._screenshot_dir = os.path.join("/tmp", "tsushin_screenshots")
        os.makedirs(self._screenshot_dir, exist_ok=True)

    async def initialize(self) -> None:
        """
        Connect to MCP HTTP Bridge and verify browser availability.

        Raises:
            BrowserInitializationError: If bridge or browser is unavailable
        """
        if self._initialized:
            logger.debug("MCP Browser provider already initialized")
            return

        try:
            logger.info(f"Initializing MCP Browser provider (bridge: {self._bridge_url})")

            # Create HTTP session for bridge communication
            timeout = aiohttp.ClientTimeout(total=self.config.timeout_seconds)
            self._http_session = aiohttp.ClientSession(timeout=timeout)

            # Check bridge connectivity
            await self._check_bridge_health()

            # Generate session ID
            self._session_id = hashlib.md5(
                f"{datetime.utcnow().isoformat() + 'Z'}_{os.getpid()}".encode()
            ).hexdigest()[:16]

            self._initialized = True
            logger.info(f"MCP Browser provider initialized (session: {self._session_id})")

        except aiohttp.ClientError as e:
            logger.error(f"Failed to connect to MCP Bridge: {e}")
            await self.cleanup()
            raise BrowserInitializationError(
                f"Cannot connect to MCP Bridge at {self._bridge_url}. "
                "Ensure the bridge server is running on the host machine."
            )
        except Exception as e:
            logger.error(f"Failed to initialize MCP Browser: {e}")
            await self.cleanup()
            raise BrowserInitializationError(f"MCP Browser initialization failed: {str(e)}")

    async def _check_bridge_health(self) -> bool:
        """
        Check if MCP HTTP Bridge is reachable and healthy.

        Returns:
            True if bridge is healthy

        Raises:
            BrowserInitializationError: If bridge is unavailable
        """
        try:
            async with self._http_session.get(
                f"{self._bridge_url}/health",
                headers=self._get_auth_headers()
            ) as response:
                if response.status != 200:
                    raise BrowserInitializationError(
                        f"MCP Bridge returned status {response.status}"
                    )
                return True
        except aiohttp.ClientConnectorError:
            raise BrowserInitializationError(
                f"Cannot connect to MCP Bridge at {self._bridge_url}. "
                "Is the bridge server running?"
            )

    def _get_auth_headers(self) -> Dict[str, str]:
        """Get authentication headers for bridge requests."""
        headers = {
            "Content-Type": "application/json",
            "X-Session-ID": self._session_id or "unknown",
        }
        if self._bridge_api_key:
            headers["Authorization"] = f"Bearer {self._bridge_api_key}"
        return headers

    async def _call_mcp_tool(
        self,
        tool_name: str,
        params: Dict[str, Any],
        action_type: str,
    ) -> Dict[str, Any]:
        """
        Call MCP tool via HTTP bridge.

        Args:
            tool_name: MCP tool name (e.g., "browser_navigate")
            params: Tool parameters
            action_type: Action type for logging (e.g., "navigate")

        Returns:
            MCP tool response

        Raises:
            BrowserAutomationError: If tool call fails
        """
        if not self._http_session:
            raise BrowserAutomationError("HTTP session not initialized")

        request_data = {
            "tool": tool_name,
            "params": params,
            "session_id": self._session_id,
            "mcp_backend": self._mcp_backend,
        }

        start_time = time.time()

        try:
            async with self._http_session.post(
                f"{self._bridge_url}/mcp/call",
                json=request_data,
                headers=self._get_auth_headers()
            ) as response:
                duration_ms = int((time.time() - start_time) * 1000)

                if response.status != 200:
                    error_text = await response.text()
                    raise BrowserAutomationError(
                        f"MCP tool call failed (status {response.status}): {error_text}"
                    )

                result = await response.json()

                if not result.get("success", False):
                    raise BrowserAutomationError(
                        f"MCP tool returned error: {result.get('error', 'Unknown error')}"
                    )

                logger.debug(
                    f"MCP tool {tool_name} completed in {duration_ms}ms"
                )

                return result.get("result", {})

        except aiohttp.ClientError as e:
            raise BrowserAutomationError(f"Bridge communication error: {str(e)}")

    def _validate_url(self, url: str) -> None:
        """
        Validate URL for host mode security.

        Host mode has stricter validation than container mode because
        it has access to authenticated sessions.

        Args:
            url: URL to validate

        Raises:
            SecurityError: If URL is blocked
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""
            hostname_lower = hostname.lower()

            # Check for sensitive domains
            for sensitive in self.SENSITIVE_DOMAINS:
                if sensitive in hostname_lower:
                    raise SecurityError(
                        f"Host mode blocks sensitive domain pattern: '{sensitive}'. "
                        f"Domain '{hostname}' requires explicit approval."
                    )

            # Check blocked domains from config
            for blocked in self.config.blocked_domains:
                if blocked.lower() in hostname_lower:
                    raise SecurityError(
                        f"Navigation to blocked domain: {blocked}"
                    )

            # Ensure valid scheme
            if parsed.scheme not in ("http", "https"):
                raise SecurityError(
                    f"Only HTTP/HTTPS URLs are allowed, got: {parsed.scheme}"
                )

        except SecurityError:
            raise
        except Exception as e:
            raise NavigationError(f"Invalid URL: {url} - {str(e)}")

    async def navigate(self, url: str, wait_until: str = "load") -> BrowserResult:
        """
        Navigate to a URL in host browser.

        Args:
            url: Target URL
            wait_until: Wait condition

        Returns:
            BrowserResult with url and title
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        self._validate_url(url)

        async with self._lock:
            try:
                logger.info(f"[MCP] Navigating to: {url}")

                tool_name = self.MCP_TOOLS[self._mcp_backend]["navigate"]
                params = {"url": url}

                if self._mcp_backend == "playwright":
                    result = await self._call_mcp_tool(tool_name, params, "navigate")
                else:
                    # Claude in Chrome
                    if self._tab_id:
                        params["tabId"] = self._tab_id
                    result = await self._call_mcp_tool(tool_name, params, "navigate")

                return BrowserResult(
                    success=True,
                    action="navigate",
                    data={
                        "url": result.get("url", url),
                        "title": result.get("title", ""),
                        "mcp_backend": self._mcp_backend,
                    }
                )

            except SecurityError:
                raise
            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower():
                    raise BrowserTimeoutError(f"Navigation timeout: {url}")
                raise NavigationError(f"Navigation failed: {error_msg}")

    async def click(self, selector: str) -> BrowserResult:
        """
        Click an element in host browser.

        Args:
            selector: CSS selector or element reference

        Returns:
            BrowserResult confirming click
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"[MCP] Clicking element: {selector}")

                if self._mcp_backend == "playwright":
                    tool_name = self.MCP_TOOLS["playwright"]["click"]
                    params = {"ref": selector, "element": f"Element: {selector}"}
                else:
                    # Claude in Chrome uses coordinate-based clicks
                    tool_name = self.MCP_TOOLS["claude_in_chrome"]["click"]
                    params = {
                        "action": "click",
                        "ref": selector,
                        "tabId": self._tab_id,
                    }

                await self._call_mcp_tool(tool_name, params, "click")

                return BrowserResult(
                    success=True,
                    action="click",
                    data={"selector": selector}
                )

            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower():
                    raise BrowserTimeoutError(f"Click timeout: {selector}")
                raise ElementNotFoundError(f"Element not found or not clickable: {selector}")

    async def fill(self, selector: str, value: str) -> BrowserResult:
        """
        Fill a form field in host browser.

        Args:
            selector: CSS selector for input
            value: Text value to fill

        Returns:
            BrowserResult confirming fill
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"[MCP] Filling element: {selector}")

                if self._mcp_backend == "playwright":
                    tool_name = self.MCP_TOOLS["playwright"]["type"]
                    params = {
                        "ref": selector,
                        "text": value,
                        "element": f"Input: {selector}",
                    }
                else:
                    tool_name = self.MCP_TOOLS["claude_in_chrome"]["type"]
                    params = {
                        "ref": selector,
                        "value": value,
                        "tabId": self._tab_id,
                    }

                await self._call_mcp_tool(tool_name, params, "fill")

                return BrowserResult(
                    success=True,
                    action="fill",
                    data={
                        "selector": selector,
                        "value": value,
                        "value_length": len(value),
                    }
                )

            except Exception as e:
                error_msg = str(e)
                if "timeout" in error_msg.lower():
                    raise BrowserTimeoutError(f"Fill timeout: {selector}")
                raise ElementNotFoundError(f"Element not found or not fillable: {selector}")

    async def extract(self, selector: str = "body") -> BrowserResult:
        """
        Extract text content from host browser.

        Args:
            selector: CSS selector for target element

        Returns:
            BrowserResult with extracted text
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"[MCP] Extracting content from: {selector}")

                if self._mcp_backend == "playwright":
                    tool_name = self.MCP_TOOLS["playwright"]["snapshot"]
                    params = {}
                else:
                    tool_name = self.MCP_TOOLS["claude_in_chrome"]["snapshot"]
                    params = {"tabId": self._tab_id}

                result = await self._call_mcp_tool(tool_name, params, "extract")

                # Parse accessibility tree or content
                text = result.get("text", result.get("content", ""))

                # Clean up whitespace
                text = " ".join(text.split()) if text else ""

                return BrowserResult(
                    success=True,
                    action="extract",
                    data={
                        "selector": selector,
                        "text": text,
                        "text_length": len(text),
                    }
                )

            except Exception as e:
                raise ElementNotFoundError(f"Extraction failed: {str(e)}")

    async def screenshot(
        self,
        full_page: bool = True,
        selector: Optional[str] = None
    ) -> BrowserResult:
        """
        Capture screenshot from host browser.

        Args:
            full_page: Whether to capture full scrollable page
            selector: Optional element selector

        Returns:
            BrowserResult with screenshot path
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                # Generate unique filename
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"mcp_screenshot_{timestamp}.png"
                filepath = os.path.join(self._screenshot_dir, filename)

                logger.info(f"[MCP] Taking screenshot (full_page={full_page})")

                if self._mcp_backend == "playwright":
                    tool_name = self.MCP_TOOLS["playwright"]["screenshot"]
                    params = {
                        "type": "png",
                        "fullPage": full_page,
                        "filename": filepath,
                    }
                    if selector:
                        params["ref"] = selector
                        params["element"] = f"Element: {selector}"
                else:
                    tool_name = self.MCP_TOOLS["claude_in_chrome"]["screenshot"]
                    params = {
                        "action": "screenshot",
                        "tabId": self._tab_id,
                    }

                result = await self._call_mcp_tool(tool_name, params, "screenshot")

                # Handle different response formats
                actual_path = result.get("path", result.get("filename", filepath))

                # Check if file exists (bridge may save to different location)
                if os.path.exists(actual_path):
                    file_size = os.path.getsize(actual_path)
                else:
                    # File might be at expected filepath
                    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    actual_path = filepath

                logger.info(f"[MCP] Screenshot saved: {actual_path} ({file_size} bytes)")

                return BrowserResult(
                    success=True,
                    action="screenshot",
                    data={
                        "path": actual_path,
                        "filename": filename,
                        "full_page": full_page,
                        "selector": selector,
                        "size_bytes": file_size,
                    }
                )

            except Exception as e:
                raise BrowserAutomationError(f"Screenshot failed: {str(e)}")

    async def execute_script(self, script: str) -> BrowserResult:
        """
        Execute JavaScript in host browser.

        Args:
            script: JavaScript code to execute

        Returns:
            BrowserResult with script result
        """
        if not self._initialized:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"[MCP] Executing script ({len(script)} chars)")

                if self._mcp_backend == "playwright":
                    tool_name = self.MCP_TOOLS["playwright"]["evaluate"]
                    params = {"function": script}
                else:
                    tool_name = self.MCP_TOOLS["claude_in_chrome"]["evaluate"]
                    params = {
                        "action": script,
                        "tabId": self._tab_id,
                    }

                result = await self._call_mcp_tool(tool_name, params, "execute_script")

                return BrowserResult(
                    success=True,
                    action="execute_script",
                    data={
                        "result": result.get("result", result),
                        "script_length": len(script),
                    }
                )

            except Exception as e:
                raise ScriptExecutionError(f"Script execution failed: {str(e)}")

    async def cleanup(self) -> None:
        """
        Disconnect from MCP bridge and cleanup resources.

        Safe to call multiple times (idempotent).
        """
        logger.info("Cleaning up MCP Browser resources")

        try:
            # Close HTTP session
            if self._http_session:
                try:
                    # Notify bridge of session end
                    if self._session_id and not self._http_session.closed:
                        try:
                            await self._http_session.post(
                                f"{self._bridge_url}/mcp/session/end",
                                json={"session_id": self._session_id},
                                headers=self._get_auth_headers()
                            )
                        except Exception:
                            pass  # Best effort

                    await self._http_session.close()
                except Exception:
                    pass
                self._http_session = None

        except Exception as e:
            logger.error(f"Error during MCP cleanup: {e}")

        finally:
            self._initialized = False
            self._session_id = None
            self._tab_id = None
            logger.info("MCP Browser cleanup complete")

    async def get_current_url(self) -> str:
        """Get the current page URL from host browser."""
        if not self._initialized:
            return ""
        try:
            result = await self._call_mcp_tool(
                "browser_snapshot" if self._mcp_backend == "playwright" else "read_page",
                {},
                "get_url"
            )
            return result.get("url", "")
        except Exception:
            return ""

    async def get_page_title(self) -> str:
        """Get the current page title from host browser."""
        if not self._initialized:
            return ""
        try:
            result = await self._call_mcp_tool(
                "browser_snapshot" if self._mcp_backend == "playwright" else "read_page",
                {},
                "get_title"
            )
            return result.get("title", "")
        except Exception:
            return ""

    def is_initialized(self) -> bool:
        """Check if MCP connection is established."""
        return self._initialized and self._http_session is not None

    @classmethod
    def get_provider_info(cls) -> Dict[str, Any]:
        """Get provider metadata."""
        return {
            "type": cls.provider_type,
            "name": cls.provider_name,
            "mode": "host",
            "actions": ["navigate", "click", "fill", "extract", "screenshot", "execute_script"],
            "backends": ["playwright", "claude_in_chrome"],
            "features": [
                "authenticated_sessions",
                "user_cookies",
                "sensitive_domain_blocking",
                "audit_logging",
                "whitelist_authorization"
            ],
            "requirements": [
                "MCP HTTP Bridge on host",
                "Browser with MCP extension/server"
            ]
        }
