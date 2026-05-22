"""Per-recording Playwright lifecycle.

The recorder uses its own Playwright instance, separate from
`PlaywrightProvider` — the provider is short-lived per-execution, while a
recording needs a long-lived Page with CDP screencast active. Sharing the
provider would create coupling we don't need.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

from playwright.async_api import async_playwright

from .models import RecordingSession

logger = logging.getLogger(__name__)


# Small JS helper injected as page init script. Builds a best-effort CSS
# path for an element at given coordinates. Phase 2 replaces this with the
# full data-* > aria > [name] > nth-child ladder in selector_strategy.py.
_SELECTOR_JS = r"""
(() => {
  if (window.__tsushinRecorderShim) return;
  window.__tsushinRecorderShim = true;
  function cssPath(el) {
    if (!el || el.nodeType !== 1) return null;
    if (el === document.body) return 'body';
    const parts = [];
    while (el && el.nodeType === 1 && el !== document.body) {
      let part = el.tagName.toLowerCase();
      if (el.id) { part += '#' + CSS.escape(el.id); parts.unshift(part); break; }
      const parent = el.parentNode;
      if (parent) {
        const siblings = Array.from(parent.children).filter(s => s.tagName === el.tagName);
        if (siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(el) + 1) + ')';
      }
      parts.unshift(part);
      el = el.parentNode;
    }
    return parts.join(' > ');
  }
  window.__tsushinSelectorAt = (x, y) => {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    const meta = {
      tag: el.tagName.toLowerCase(),
      type: el.getAttribute('type') || null,
      name: el.getAttribute('name') || null,
      id: el.id || null,
      role: el.getAttribute('role') || null,
      'aria-label': el.getAttribute('aria-label') || null,
      'data-testid': el.getAttribute('data-testid') || null,
      'data-qa': el.getAttribute('data-qa') || null,
      'data-cy': el.getAttribute('data-cy') || null,
      placeholder: el.getAttribute('placeholder') || null,
    };
    return { selector: cssPath(el), meta };
  };
})();
"""

# Default viewport — matches the existing BrowserConfig default closely.
_DEFAULT_VIEWPORT = {"width": 1280, "height": 720}


class SessionRegistry:
    """Process-local map of session_id → RecordingSession.

    Single-instance per backend process. Recovery across restarts is out of
    scope — recordings are ephemeral and re-startable.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, RecordingSession] = {}
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: int,
        initial_url: Optional[str] = None,
        viewport: Optional[dict] = None,
    ) -> RecordingSession:
        session_id = uuid.uuid4().hex
        vp = viewport or _DEFAULT_VIEWPORT

        playwright = await async_playwright().start()
        try:
            browser = await playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-setuid-sandbox",
                ],
            )
            context = await browser.new_context(viewport=vp)
            await context.add_init_script(_SELECTOR_JS)
            page = await context.new_page()
            cdp = await context.new_cdp_session(page)

            session = RecordingSession(
                session_id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
                playwright=playwright,
                browser=browser,
                context=context,
                page=page,
                cdp=cdp,
            )

            self._wire_page_events(session)

            if initial_url:
                await page.goto(initial_url)
                session.append_event("navigate", {"url": initial_url})

            async with self._lock:
                self._sessions[session_id] = session

            logger.info(
                "Recorder session %s created (tenant=%s user=%s)",
                session_id, tenant_id, user_id,
            )
            return session

        except Exception:
            # Best-effort teardown if any step above failed
            try:
                await playwright.stop()
            except Exception:
                pass
            raise

    def _wire_page_events(self, session: RecordingSession) -> None:
        """Subscribe to the page-level events the compiler needs.

        Phase 1 captures only what's required to verify the streaming loop —
        navigate + load. Click/fill capture is driven from the WS relay
        layer where we already have coordinates and the JS shim's selector
        lookup.
        """
        page = session.page

        def _on_frame_navigated(frame) -> None:
            # Only top frame; sub-frame nav noise is not actionable here
            if frame == page.main_frame:
                session.append_event("navigate", {"url": frame.url})

        def _on_load() -> None:
            session.append_event("load", {"url": page.url})

        page.on("framenavigated", _on_frame_navigated)
        page.on("load", _on_load)

    async def get(self, session_id: str) -> Optional[RecordingSession]:
        return self._sessions.get(session_id)

    async def count_for_tenant(self, tenant_id: str) -> int:
        return sum(1 for s in self._sessions.values() if s.tenant_id == tenant_id)

    async def teardown(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if not session:
            return False
        # Cancel agentic driver task first if present (Phase 6 will populate)
        if session.agent_task and not session.agent_task.done():
            session.agent_task.cancel()
            try:
                await session.agent_task
            except (asyncio.CancelledError, Exception):
                pass
        # Stop screencast before closing — Chrome complains otherwise
        try:
            await session.cdp.send("Page.stopScreencast")
        except Exception:
            pass
        try:
            await session.cdp.detach()
        except Exception:
            pass
        for closer in (session.context.close, session.browser.close, session.playwright.stop):
            try:
                await closer()
            except Exception as e:  # pragma: no cover — best-effort teardown
                logger.warning("Recorder %s teardown step failed: %s", session_id, e)
        logger.info("Recorder session %s torn down", session_id)
        return True

    async def list_session_ids(self) -> list[str]:
        return list(self._sessions.keys())


_registry: Optional[SessionRegistry] = None


def get_registry() -> SessionRegistry:
    global _registry
    if _registry is None:
        _registry = SessionRegistry()
    return _registry
