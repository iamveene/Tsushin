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
    BrowserInitializationError,
    NavigationError,
    ElementNotFoundError,
    TimeoutError as BrowserTimeoutError,
    ScriptExecutionError,
    SecurityError
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
                context_options["proxy"] = {"server": self.config.proxy_url}

            self._context = await self._browser.new_context(**context_options)
            self._page = await self._context.new_page()

            # Set default timeout
            self._page.set_default_timeout(self.config.timeout_seconds * 1000)

            self._initialized = True
            logger.info("Playwright browser initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Playwright: {e}")
            await self.cleanup()
            raise BrowserInitializationError(f"Could not launch browser: {str(e)}")

    def _validate_url(self, url: str) -> None:
        """
        Validate URL for security (SSRF prevention).

        Args:
            url: URL to validate

        Raises:
            SecurityError: If URL targets blocked resources
        """
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or ""

            # Check for blocked IP ranges
            for blocked in self.BLOCKED_IP_RANGES:
                if hostname.lower().startswith(blocked.lower()) or hostname.lower() == blocked.lower():
                    raise SecurityError(
                        f"Navigation to private/local addresses is blocked: {hostname}"
                    )

            # Check blocked domains from config
            for blocked_domain in self.config.blocked_domains:
                if blocked_domain.lower() in hostname.lower():
                    raise SecurityError(
                        f"Navigation to blocked domain: {blocked_domain}"
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

            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg or "timeout" in error_msg:
                    raise BrowserTimeoutError(f"Navigation timeout: {url}")
                raise NavigationError(f"Navigation failed: {error_msg}")

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
                error_msg = str(e)
                if "Timeout" in error_msg or "timeout" in error_msg:
                    raise BrowserTimeoutError(f"Click timeout: {selector}")
                raise ElementNotFoundError(f"Element not found or not clickable: {selector}")

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
                        "value": value,
                        "value_length": len(value)
                    }
                )

            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg or "timeout" in error_msg:
                    raise BrowserTimeoutError(f"Fill timeout: {selector}")
                raise ElementNotFoundError(f"Element not found or not fillable: {selector}")

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

            except ElementNotFoundError:
                raise
            except Exception as e:
                raise ElementNotFoundError(f"Extraction failed: {str(e)}")

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

            except ElementNotFoundError:
                raise
            except Exception as e:
                raise BrowserAutomationError(f"Screenshot failed: {str(e)}")

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

    async def cleanup(self) -> None:
        """
        Close browser and cleanup all resources.

        Safe to call multiple times (idempotent).
        """
        logger.info("Cleaning up Playwright resources")

        try:
            if self._page:
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
            "actions": ["navigate", "click", "fill", "extract", "screenshot", "execute_script"],
            "browsers": ["chromium", "firefox", "webkit"],
            "features": [
                "headless_mode",
                "viewport_control",
                "user_agent_override",
                "proxy_support",
                "ssrf_protection"
            ]
        }
