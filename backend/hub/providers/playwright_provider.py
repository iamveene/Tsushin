"""
Playwright Browser Automation Provider

Phase 14.5: Browser Automation Skill - Playwright Implementation

Container-mode browser automation using Microsoft Playwright.
Provides secure, isolated browser automation for public websites.

Supported actions:
1. navigate(url, wait_until) - Navigate to URL
2. click(selector) - Click element by CSS selector
3. fill(selector, value) - Fill form input fields
4. extract(selector) - Extract text content from elements
5. screenshot(full_page, selector) - Capture screenshots
6. execute_script(script) - Execute JavaScript in page context
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser, BrowserContext, Playwright

from .browser_automation_provider import (
    BrowserAutomationProvider,
    BrowserConfig,
    BrowserResult,
    BrowserAutomationError,
    BrowserErrorCode,
    BrowserInitializationError,
    NavigationError,
    ElementNotFoundError,
    TimeoutError as BrowserTimeoutError,
    ScriptExecutionError,
    SecurityError,
    classify_error,
)

logger = logging.getLogger(__name__)


class PlaywrightProvider(BrowserAutomationProvider):
    """
    Playwright-based browser automation provider.

    Runs in container mode - launches a headless browser inside Docker
    for secure, isolated automation of public websites.

    Thread-safe: Uses async lock for concurrent operations.
    Resource-managed: Proper cleanup on errors.

    Example:
        config = BrowserConfig(browser_type="chromium", headless=True)
        provider = PlaywrightProvider(config)
        await provider.initialize()
        try:
            result = await provider.navigate("https://example.com")
            screenshot = await provider.screenshot()
        finally:
            await provider.cleanup()
    """

    provider_type = "playwright"
    provider_name = "Playwright (Container)"

    # Private IP ranges to block for SSRF prevention
    BLOCKED_IP_RANGES = [
        "localhost",
        "127.",
        "10.",
        "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.",
        "172.24.", "172.25.", "172.26.", "172.27.",
        "172.28.", "172.29.", "172.30.", "172.31.",
        "192.168.",
        "169.254.",  # Link-local
        "0.0.0.0",
        "::1",  # IPv6 localhost
    ]

    def __init__(self, config: BrowserConfig):
        """
        Initialize Playwright provider with configuration.

        Args:
            config: BrowserConfig with browser settings
        """
        super().__init__(config)
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        # 35c: Multi-tab tracking
        self._pages: dict[str, Page] = {}
        self._active_tab_id: Optional[str] = None
        # Use shared Docker volume for screenshots (accessible by MCP containers)
        # Same pattern as TTS audio files in /tmp/tsushin_audio
        shared_screenshot_dir = os.path.join(tempfile.gettempdir(), "tsushin_screenshots")
        os.makedirs(shared_screenshot_dir, exist_ok=True)
        self._screenshot_dir = shared_screenshot_dir

    async def initialize(self) -> None:
        """
        Launch browser instance.

        Starts Playwright and launches configured browser type.
        Sets up browser context with viewport and user agent.

        Raises:
            BrowserInitializationError: If browser cannot be launched
        """
        if self._initialized:
            logger.debug("Playwright provider already initialized")
            return

        try:
            logger.info(f"Initializing Playwright with {self.config.browser_type} (headless={self.config.headless})")

            self._playwright = await async_playwright().start()

            # Select browser type
            browser_types = {
                "chromium": self._playwright.chromium,
                "firefox": self._playwright.firefox,
                "webkit": self._playwright.webkit
            }
            browser_type = browser_types.get(self.config.browser_type, self._playwright.chromium)

            # Launch arguments for Docker compatibility
            launch_args = [
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-setuid-sandbox"
            ]

            self._browser = await browser_type.launch(
                headless=self.config.headless,
                args=launch_args
            )

            # Create browser context with settings
            context_options = {
                "viewport": {
                    "width": self.config.viewport_width,
                    "height": self.config.viewport_height
                }
            }

            if self.config.user_agent:
                context_options["user_agent"] = self.config.user_agent

            if self.config.proxy_url:
                # Validate proxy URL against SSRF (1A-02)
                from utils.ssrf_validator import validate_url
                try:
                    validate_url(self.config.proxy_url)
                except Exception as e:
                    raise BrowserInitializationError(f"Proxy URL failed SSRF validation: {e}")
                context_options["proxy"] = {"server": self.config.proxy_url}

            self._context = await self._browser.new_context(**context_options)
            self._page = await self._context.new_page()

            # Set default timeout
            self._page.set_default_timeout(self.config.timeout_seconds * 1000)

            # 35c: Register initial tab
            self._pages = {"tab_0": self._page}
            self._active_tab_id = "tab_0"

            self._initialized = True
            logger.info("Playwright browser initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            await self.cleanup()
            raise BrowserInitializationError(f"Could not launch browser: {str(e)}")

    def _validate_url(self, url: str) -> None:
        """Validate URL against SSRF using shared validator with tenant allowlist/blocklist."""
        from utils.ssrf_validator import validate_url, SSRFValidationError
        try:
            validate_url(
                url,
                allowed_domains=self.config.allowed_domains or None,
                blocked_domains=self.config.blocked_domains or None,
            )
        except SSRFValidationError as e:
            logger.warning(f"SSRF validation blocked URL: {url} — {e}")
            raise SecurityError(str(e))

    async def navigate(self, url: str, wait_until: str = "load") -> BrowserResult:
        """
        Navigate to a URL.

        Args:
            url: Target URL (must be HTTP/HTTPS)
            wait_until: Wait condition - "load", "domcontentloaded", or "networkidle"

        Returns:
            BrowserResult with url and title

        Raises:
            NavigationError: If navigation fails
            SecurityError: If URL is blocked
            BrowserTimeoutError: If navigation times out
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        self._validate_url(url)

        async with self._lock:
            try:
                logger.info(f"Navigating to: {url}")

                response = await self._page.goto(
                    url,
                    wait_until=wait_until,
                    timeout=self.config.timeout_seconds * 1000
                )

                title = await self._page.title()
                final_url = self._page.url

                status = response.status if response else None

                logger.info(f"Navigation complete: {final_url} (status={status})")

                return BrowserResult(
                    success=True,
                    action="navigate",
                    data={
                        "url": final_url,
                        "title": title,
                        "status": status
                    }
                )

            except SecurityError:
                raise
            except Exception as e:
                code, suggestions = classify_error(e, "navigate")
                return BrowserResult(
                    success=False, action="navigate", error=str(e),
                    error_code=code, suggestions=suggestions,
                )

    async def click(self, selector: str) -> BrowserResult:
        """
        Click an element by CSS selector.

        Args:
            selector: CSS selector for target element

        Returns:
            BrowserResult confirming click

        Raises:
            ElementNotFoundError: If selector doesn't match
            BrowserTimeoutError: If element doesn't become clickable
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"Clicking element: {selector}")

                await self._page.click(
                    selector,
                    timeout=self.config.timeout_seconds * 1000
                )

                logger.info(f"Click successful: {selector}")

                return BrowserResult(
                    success=True,
                    action="click",
                    data={"selector": selector}
                )

            except Exception as e:
                code, suggestions = classify_error(e, "click")
                return BrowserResult(
                    success=False, action="click", error=f"Element not found or not clickable: {selector}",
                    error_code=code, suggestions=suggestions,
                )

    async def fill(self, selector: str, value: str) -> BrowserResult:
        """
        Fill a form input field.

        Args:
            selector: CSS selector for input element
            value: Text value to fill

        Returns:
            BrowserResult confirming fill

        Raises:
            ElementNotFoundError: If selector doesn't match
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"Filling element: {selector}")

                await self._page.fill(
                    selector,
                    value,
                    timeout=self.config.timeout_seconds * 1000
                )

                logger.info(f"Fill successful: {selector}")

                return BrowserResult(
                    success=True,
                    action="fill",
                    data={
                        "selector": selector,
                        "value_length": len(value)
                    }
                )

            except Exception as e:
                code, suggestions = classify_error(e, "fill")
                return BrowserResult(
                    success=False, action="fill", error=f"Element not found or not fillable: {selector}",
                    error_code=code, suggestions=suggestions,
                )

    async def extract(self, selector: str = "body") -> BrowserResult:
        """
        Extract text content from an element.

        Args:
            selector: CSS selector for target element (defaults to body)

        Returns:
            BrowserResult with extracted text

        Raises:
            ElementNotFoundError: If selector doesn't match
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"Extracting content from: {selector}")

                element = await self._page.query_selector(selector)

                if not element:
                    raise ElementNotFoundError(f"Element not found: {selector}")

                text = await element.text_content()
                inner_html = await element.inner_html()

                # Clean up whitespace
                text = " ".join(text.split()) if text else ""

                logger.info(f"Extraction complete: {len(text)} characters")

                return BrowserResult(
                    success=True,
                    action="extract",
                    data={
                        "selector": selector,
                        "text": text,
                        "html_length": len(inner_html) if inner_html else 0
                    }
                )

            except Exception as e:
                code, suggestions = classify_error(e, "extract")
                return BrowserResult(
                    success=False, action="extract", error=f"Extraction failed: {str(e)}",
                    error_code=code, suggestions=suggestions,
                )

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
            BrowserResult with path to saved PNG file

        Raises:
            ElementNotFoundError: If selector provided but not found
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                # Generate unique filename
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
                filename = f"screenshot_{timestamp}.png"
                filepath = os.path.join(self._screenshot_dir, filename)

                if selector:
                    logger.info(f"Taking element screenshot: {selector}")
                    element = await self._page.query_selector(selector)

                    if not element:
                        raise ElementNotFoundError(f"Element not found: {selector}")

                    await element.screenshot(path=filepath, type="png")
                else:
                    logger.info(f"Taking page screenshot (full_page={full_page})")
                    await self._page.screenshot(
                        path=filepath,
                        full_page=full_page,
                        type="png"
                    )

                # Get file size
                file_size = os.path.getsize(filepath)

                logger.info(f"Screenshot saved: {filepath} ({file_size} bytes)")

                return BrowserResult(
                    success=True,
                    action="screenshot",
                    data={
                        "path": filepath,
                        "filename": filename,
                        "full_page": full_page,
                        "selector": selector,
                        "size_bytes": file_size
                    }
                )

            except Exception as e:
                code, suggestions = classify_error(e, "screenshot")
                return BrowserResult(
                    success=False, action="screenshot", error=f"Screenshot failed: {str(e)}",
                    error_code=code, suggestions=suggestions,
                )

    async def execute_script(self, script: str) -> BrowserResult:
        """
        Execute JavaScript in the page context.

        Args:
            script: JavaScript code to execute

        Returns:
            BrowserResult with script return value

        Raises:
            ScriptExecutionError: If JavaScript throws an error
        """
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")

        async with self._lock:
            try:
                logger.info(f"Executing script ({len(script)} chars)")

                result = await self._page.evaluate(script)

                logger.info("Script execution complete")

                return BrowserResult(
                    success=True,
                    action="execute_script",
                    data={
                        "result": result,
                        "script_length": len(script)
                    }
                )

            except Exception as e:
                raise ScriptExecutionError(f"Script execution failed: {str(e)}")

    # -------------------------------------------------------------------
    # 35b: Rich action set
    # -------------------------------------------------------------------

    async def scroll(self, selector: str = "body", x: int = 0, y: int = 300) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info(f"Scrolling {selector} by ({x}, {y})")
                await self._page.evaluate(
                    "(args) => { const el = args.sel === 'body' ? window : document.querySelector(args.sel); "
                    "if (el === window) { window.scrollBy(args.x, args.y); } "
                    "else if (el) { el.scrollBy(args.x, args.y); } }",
                    {"sel": selector, "x": x, "y": y}
                )
                return BrowserResult(success=True, action="scroll", data={"selector": selector, "x": x, "y": y})
            except Exception as e:
                code, suggestions = classify_error(e, "scroll")
                return BrowserResult(success=False, action="scroll", error=str(e), error_code=code, suggestions=suggestions)

    async def select_option(self, selector: str, value: str) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info(f"Selecting option '{value}' in {selector}")
                selected = await self._page.select_option(selector, value, timeout=self.config.timeout_seconds * 1000)
                return BrowserResult(success=True, action="select_option", data={"selector": selector, "value": value, "selected": selected})
            except Exception as e:
                code, suggestions = classify_error(e, "select_option")
                return BrowserResult(success=False, action="select_option", error=str(e), error_code=code, suggestions=suggestions)

    async def hover(self, selector: str) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info(f"Hovering over: {selector}")
                await self._page.hover(selector, timeout=self.config.timeout_seconds * 1000)
                return BrowserResult(success=True, action="hover", data={"selector": selector})
            except Exception as e:
                code, suggestions = classify_error(e, "hover")
                return BrowserResult(success=False, action="hover", error=str(e), error_code=code, suggestions=suggestions)

    async def wait_for(self, selector: str, state: str = "visible", timeout_ms: Optional[int] = None) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                to = timeout_ms or (self.config.timeout_seconds * 1000)
                logger.info(f"Waiting for {selector} to be {state}")
                await self._page.wait_for_selector(selector, state=state, timeout=to)
                return BrowserResult(success=True, action="wait_for", data={"selector": selector, "state": state})
            except Exception as e:
                code, suggestions = classify_error(e, "wait_for")
                return BrowserResult(success=False, action="wait_for", error=str(e), error_code=code, suggestions=suggestions)

    async def go_back(self) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info("Navigating back")
                response = await self._page.go_back(timeout=self.config.timeout_seconds * 1000, wait_until="load")
                if response is None:
                    return BrowserResult(
                        success=False, action="go_back",
                        error="No previous page in history",
                        error_code=BrowserErrorCode.PAGE_LOAD_FAILED,
                        suggestions=["Navigate to a page first before going back"],
                    )
                url = self._page.url
                title = await self._page.title()
                return BrowserResult(success=True, action="go_back", data={"url": url, "title": title})
            except Exception as e:
                code, suggestions = classify_error(e, "go_back")
                return BrowserResult(success=False, action="go_back", error=str(e), error_code=code, suggestions=suggestions)

    async def go_forward(self) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info("Navigating forward")
                response = await self._page.go_forward(timeout=self.config.timeout_seconds * 1000, wait_until="load")
                if response is None:
                    return BrowserResult(
                        success=False, action="go_forward",
                        error="No forward page in history",
                        error_code=BrowserErrorCode.PAGE_LOAD_FAILED,
                        suggestions=["Go back first before navigating forward"],
                    )
                url = self._page.url
                title = await self._page.title()
                return BrowserResult(success=True, action="go_forward", data={"url": url, "title": title})
            except Exception as e:
                code, suggestions = classify_error(e, "go_forward")
                return BrowserResult(success=False, action="go_forward", error=str(e), error_code=code, suggestions=suggestions)

    async def get_attribute(self, selector: str, attribute: str) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info(f"Getting attribute '{attribute}' from {selector}")
                value = await self._page.get_attribute(selector, attribute, timeout=self.config.timeout_seconds * 1000)
                return BrowserResult(success=True, action="get_attribute", data={"selector": selector, "attribute": attribute, "value": value})
            except Exception as e:
                code, suggestions = classify_error(e, "get_attribute")
                return BrowserResult(success=False, action="get_attribute", error=str(e), error_code=code, suggestions=suggestions)

    async def get_page_url(self) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        url = self._page.url
        return BrowserResult(success=True, action="get_page_url", data={"url": url})

    async def type_text(self, selector: str, text: str, delay_ms: int = 0) -> BrowserResult:
        if not self._initialized or not self._page:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            try:
                logger.info(f"Typing {len(text)} chars into {selector} (delay={delay_ms}ms)")
                await self._page.type(selector, text, delay=delay_ms, timeout=self.config.timeout_seconds * 1000)
                return BrowserResult(success=True, action="type_text", data={"selector": selector, "chars": len(text)})
            except Exception as e:
                code, suggestions = classify_error(e, "type_text")
                return BrowserResult(success=False, action="type_text", error=str(e), error_code=code, suggestions=suggestions)

    # -------------------------------------------------------------------
    # 35c: Multi-tab support
    # -------------------------------------------------------------------

    async def open_tab(self, url: Optional[str] = None) -> BrowserResult:
        if not self._initialized or not self._context:
            raise BrowserAutomationError("Browser not initialized. Call initialize() first.")
        async with self._lock:
            # 2A-02: Tab-count guard inside lock to prevent TOCTOU race
            max_tabs = self.config.max_concurrent_sessions  # reuse as tab cap
            if len(self._pages) >= max_tabs:
                return BrowserResult(
                    success=False, action="open_tab", error=f"Maximum {max_tabs} tabs reached",
                    error_code=BrowserErrorCode.MAX_SESSIONS,
                    suggestions=[f"Close an existing tab first (you have {len(self._pages)})"],
                )
            # Save previous state for rollback on failure (2A-03)
            prev_page = self._page
            prev_tab_id = self._active_tab_id
            new_page = None
            tab_id = None
            try:
                new_page = await self._context.new_page()
                new_page.set_default_timeout(self.config.timeout_seconds * 1000)
                tab_id = f"tab_{len(self._pages)}"
                # Ensure unique tab_id
                counter = len(self._pages)
                while tab_id in self._pages:
                    counter += 1
                    tab_id = f"tab_{counter}"
                # Navigate BEFORE registering (2A-03: avoid leak on nav failure)
                data = {"tab_id": tab_id}
                if url:
                    self._validate_url(url)
                    await new_page.goto(url, wait_until="load", timeout=self.config.timeout_seconds * 1000)
                    data["url"] = new_page.url
                    data["title"] = await new_page.title()
                # All operations succeeded — register page and switch
                self._pages[tab_id] = new_page
                self._page = new_page
                self._active_tab_id = tab_id
                data["tabs"] = list(self._pages.keys())
                logger.info(f"Opened new tab {tab_id}")
                return BrowserResult(success=True, action="open_tab", data=data)
            except SecurityError:
                # Close leaked page before re-raising
                if new_page:
                    try:
                        await new_page.close()
                    except Exception:
                        pass
                self._page = prev_page
                self._active_tab_id = prev_tab_id
                raise
            except Exception as e:
                # 2A-03: Close leaked page and restore previous state
                if new_page:
                    try:
                        await new_page.close()
                    except Exception:
                        pass
                self._page = prev_page
                self._active_tab_id = prev_tab_id
                code, suggestions = classify_error(e, "open_tab")
                return BrowserResult(success=False, action="open_tab", error=str(e), error_code=code, suggestions=suggestions)

    async def switch_tab(self, tab_id: str) -> BrowserResult:
        if tab_id not in self._pages:
            return BrowserResult(
                success=False, action="switch_tab", error=f"Tab '{tab_id}' not found",
                error_code=BrowserErrorCode.TAB_NOT_FOUND,
                suggestions=[f"Available tabs: {list(self._pages.keys())}"],
            )
        self._page = self._pages[tab_id]
        self._active_tab_id = tab_id
        url = self._page.url
        logger.info(f"Switched to tab {tab_id} ({url})")
        return BrowserResult(success=True, action="switch_tab", data={"tab_id": tab_id, "url": url})

    async def close_tab(self, tab_id: str) -> BrowserResult:
        if tab_id not in self._pages:
            return BrowserResult(
                success=False, action="close_tab", error=f"Tab '{tab_id}' not found",
                error_code=BrowserErrorCode.TAB_NOT_FOUND,
                suggestions=[f"Available tabs: {list(self._pages.keys())}"],
            )
        if len(self._pages) <= 1:
            return BrowserResult(
                success=False, action="close_tab", error="Cannot close the last tab",
                suggestions=["Use close_browser to end the entire session instead"],
            )
        async with self._lock:
            page = self._pages.pop(tab_id)
            try:
                await page.close()
            except Exception:
                pass
            if self._active_tab_id == tab_id:
                last_key = list(self._pages.keys())[-1]
                self._page = self._pages[last_key]
                self._active_tab_id = last_key
            logger.info(f"Closed tab {tab_id}")
            return BrowserResult(success=True, action="close_tab", data={"closed_tab": tab_id, "active_tab": self._active_tab_id, "tabs": list(self._pages.keys())})

    async def list_tabs(self) -> BrowserResult:
        tabs = []
        for tid, page in self._pages.items():
            tabs.append({"tab_id": tid, "url": page.url, "active": tid == self._active_tab_id})
        return BrowserResult(success=True, action="list_tabs", data={"tabs": tabs, "count": len(tabs)})

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    async def cleanup(self) -> None:
        """
        Close browser and cleanup all resources.

        Safe to call multiple times (idempotent).
        """
        logger.info("Cleaning up Playwright resources")

        try:
            # 35c: Close all tracked tabs
            for tid, page in list(self._pages.items()):
                try:
                    await page.close()
                except Exception:
                    pass
            self._pages.clear()
            self._active_tab_id = None

            if self._page:
                # _page may already be closed via _pages cleanup
                try:
                    await self._page.close()
                except Exception:
                    pass
                self._page = None

            if self._context:
                try:
                    await self._context.close()
                except Exception:
                    pass
                self._context = None

            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

        finally:
            self._initialized = False
            logger.info("Playwright cleanup complete")

    async def get_current_url(self) -> str:
        """Get the current page URL."""
        if not self._page:
            return ""
        return self._page.url

    async def get_page_title(self) -> str:
        """Get the current page title."""
        if not self._page:
            return ""
        return await self._page.title()

    def is_initialized(self) -> bool:
        """Check if browser is initialized and ready."""
        return self._initialized and self._page is not None

    @classmethod
    def get_provider_info(cls) -> dict:
        """Get provider metadata."""
        return {
            "type": cls.provider_type,
            "name": cls.provider_name,
            "mode": "container",
            "actions": [
                "navigate", "click", "fill", "extract", "screenshot", "execute_script",
                "scroll", "select_option", "hover", "wait_for", "go_back", "go_forward",
                "get_attribute", "get_page_url", "type_text",
                "open_tab", "switch_tab", "close_tab", "list_tabs",
            ],
            "browsers": ["chromium", "firefox", "webkit"],
            "features": [
                "headless_mode",
                "viewport_control",
                "user_agent_override",
                "proxy_support",
                "ssrf_protection",
                "session_persistence",
                "multi_tab",
                "structured_errors",
            ]
        }
