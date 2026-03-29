"""
CDP Browser Automation Provider

Connects to a Chrome instance running on the host via Chrome DevTools Protocol.
Inherits all 19 action methods from PlaywrightProvider — only initialization
and cleanup differ (connect vs launch, disconnect vs kill).

Usage:
    The user must start Chrome with --remote-debugging-port:
        google-chrome --remote-debugging-port=9222

    macOS:
        /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222

    The agent then accesses the user's authenticated sessions (cookies,
    localStorage, active logins) through the CDP connection.
"""

import asyncio
import logging
from typing import Optional

from playwright.async_api import async_playwright, Playwright, Browser, BrowserContext, Page

from .browser_automation_provider import (
    BrowserConfig,
    BrowserInitializationError,
    BrowserAutomationError,
)
from .playwright_provider import PlaywrightProvider

logger = logging.getLogger(__name__)


class CDPProvider(PlaywrightProvider):
    """
    CDP-based browser automation provider.

    Connects to a running Chrome on the host machine via connect_over_cdp().
    All 19 action methods are inherited from PlaywrightProvider unchanged —
    they operate on self._page which is a standard Playwright Page regardless
    of connection mode.

    Key differences from PlaywrightProvider:
    - initialize(): connects to existing Chrome instead of launching one
    - cleanup(): disconnects without killing Chrome (user's browser stays open)
    """

    provider_type = "cdp"
    provider_name = "CDP Host Browser"

    async def initialize(self) -> None:
        """
        Connect to a running Chrome via CDP.

        Attaches to existing browser contexts and pages when available.
        Creates a new context/page only if none exist.

        Raises:
            BrowserInitializationError: If Chrome is not reachable at the CDP URL.
        """
        if self._initialized:
            logger.debug("CDPProvider already initialized")
            return

        from utils.cdp_url_validator import validate_cdp_url, CDPURLError

        cdp_url = self.config.cdp_url
        try:
            validate_cdp_url(cdp_url)
        except CDPURLError as e:
            raise BrowserInitializationError(f"Invalid CDP URL: {e}")

        try:
            logger.info(f"CDPProvider: connecting to Chrome at {cdp_url}")
            self._playwright = await async_playwright().start()

            # Resolve WebSocket URL from Chrome's /json/version endpoint.
            # Chrome blocks non-localhost Host headers on /json/version,
            # and Playwright's connect_over_cdp tries that endpoint internally.
            # By resolving the WS URL ourselves (with Host header override),
            # we bypass this restriction.
            ws_url = await self._resolve_ws_url(cdp_url)
            if ws_url:
                logger.info(f"CDPProvider: using resolved WS URL")
                self._browser = await asyncio.wait_for(
                    self._playwright.chromium.connect_over_cdp(ws_url),
                    timeout=10,
                )
            else:
                # Fallback to HTTP — works when Chrome is on localhost
                self._browser = await asyncio.wait_for(
                    self._playwright.chromium.connect_over_cdp(cdp_url),
                    timeout=10,
                )

            # Attach to existing context or create a fresh one
            existing_contexts = self._browser.contexts
            if existing_contexts:
                self._context = existing_contexts[0]
            else:
                self._context = await self._browser.new_context(
                    viewport={
                        "width": self.config.viewport_width,
                        "height": self.config.viewport_height,
                    }
                )

            # Attach to existing pages or create one
            existing_pages = self._context.pages
            if existing_pages:
                self._page = existing_pages[0]
            else:
                self._page = await self._context.new_page()

            self._page.set_default_timeout(self.config.timeout_seconds * 1000)

            # Register all existing tabs
            self._pages = {}
            self._active_tab_id = "tab_0"
            for i, page in enumerate(self._context.pages):
                tab_id = f"tab_{i}"
                self._pages[tab_id] = page
            if not self._pages:
                self._pages["tab_0"] = self._page

            self._initialized = True
            logger.info(
                f"CDPProvider: connected to Chrome, {len(self._pages)} tab(s) found"
            )

        except BrowserInitializationError:
            raise
        except asyncio.TimeoutError:
            await self.cleanup()
            raise BrowserInitializationError(
                f"Timed out connecting to Chrome at {cdp_url}. "
                "Ensure Chrome is running with --remote-debugging-port=9222."
            )
        except Exception as e:
            logger.error(f"CDPProvider: connection failed: {e}")
            await self.cleanup()
            raise BrowserInitializationError(
                f"Could not connect to Chrome at {cdp_url}. "
                f"Ensure Chrome is running with --remote-debugging-port=9222. "
                f"Error: {str(e)}"
            )

    async def cleanup(self) -> None:
        """
        Disconnect from Chrome without closing it.

        The user's Chrome process stays running with all tabs intact.
        Only the Playwright connection is torn down.
        """
        logger.info("CDPProvider: disconnecting from host Chrome")
        try:
            # Clear tab registry — do NOT close pages (they belong to the user)
            self._pages.clear()
            self._active_tab_id = None
            self._page = None
            self._context = None

            # Disconnect from Chrome (Playwright's close() on CDP = disconnect only)
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None

            # Stop the Playwright helper subprocess
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

        except Exception as e:
            logger.error(f"CDPProvider: cleanup error: {e}")
        finally:
            self._initialized = False
            logger.info("CDPProvider: disconnected")

    @staticmethod
    async def _resolve_ws_url(cdp_url: str) -> Optional[str]:
        """
        Fetch the WebSocket debugger URL from Chrome's /json/version endpoint.

        Chrome's HTTP CDP endpoint can return 500 when accessed from Docker,
        but the direct WebSocket URL works. This method fetches the WS URL
        and replaces the host to match the original cdp_url.
        """
        import aiohttp
        from urllib.parse import urlparse

        parsed = urlparse(cdp_url)
        version_url = f"{parsed.scheme}://{parsed.hostname}:{parsed.port}/json/version"
        try:
            # Chrome blocks CDP requests where Host header isn't localhost or IP.
            # Override Host header when connecting via host.docker.internal.
            headers = {}
            if "host.docker.internal" in version_url:
                headers["Host"] = f"localhost:{parsed.port or 9222}"

            async with aiohttp.ClientSession() as session:
                async with session.get(version_url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        ws_url = data.get("webSocketDebuggerUrl", "")
                        if ws_url:
                            # Replace the host in ws_url with our cdp_url host
                            # Chrome reports ws://127.0.0.1:9222/... but we need
                            # ws://host.docker.internal:9222/... from Docker
                            ws_parsed = urlparse(ws_url)
                            fixed_ws = ws_url.replace(
                                f"{ws_parsed.hostname}:{ws_parsed.port}",
                                f"{parsed.hostname}:{parsed.port}",
                            )
                            logger.info(f"CDPProvider: resolved WS URL: {fixed_ws}")
                            return fixed_ws
        except Exception as e:
            logger.debug(f"CDPProvider: could not resolve WS URL from {version_url}: {e}")
        return None

    @classmethod
    def get_provider_info(cls) -> dict:
        """Get provider metadata."""
        return {
            "type": cls.provider_type,
            "name": cls.provider_name,
            "mode": "cdp",
            "actions": [
                "navigate", "click", "fill", "extract", "screenshot", "execute_script",
                "scroll", "select_option", "hover", "wait_for", "go_back", "go_forward",
                "get_attribute", "get_page_url", "type_text",
                "open_tab", "switch_tab", "close_tab", "list_tabs",
            ],
            "browsers": ["chromium"],
            "features": [
                "authenticated_sessions",
                "user_cookies",
                "viewport_control",
                "ssrf_protection",
                "session_persistence",
                "multi_tab",
                "structured_errors",
            ],
        }
