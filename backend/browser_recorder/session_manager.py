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
  function metaOf(el) {
    if (!el || el.nodeType !== 1) return null;
    return {
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
  }
  window.__tsushinSelectorAt = (x, y) => {
    const el = document.elementFromPoint(x, y);
    if (!el) return null;
    return { selector: cssPath(el), meta: metaOf(el) };
  };
  window.__tsushinFocusedSelector = () => {
    // Resolve the currently focused element. Falls through iframes via
    // shadowRoot when possible. Returns null when focus is on body — the
    // recorder's input.text path treats that as "no useful selector" so
    // the compiler can refuse to emit a body-fill row (BUG-768).
    let el = document.activeElement;
    while (el && el.shadowRoot && el.shadowRoot.activeElement) {
      el = el.shadowRoot.activeElement;
    }
    if (!el || el === document.body || el === document.documentElement) return null;
    return { selector: cssPath(el), meta: metaOf(el) };
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
        # In-flight create() count per tenant. Reserves a slot inside the
        # lock so two concurrent POSTs can't both pass the cap check
        # before either has inserted its session.
        self._pending_by_tenant: dict[str, int] = {}
        self._lock = asyncio.Lock()

    # Max concurrent recordings per tenant. Anti-abuse + bounds the
    # screencast bandwidth/CPU load. Override via env if a future workload
    # genuinely needs more.
    MAX_PER_TENANT = 2

    def _release_pending(self, tenant_id: str) -> None:
        """Decrement the in-flight create() counter. Caller holds the lock."""
        remaining = self._pending_by_tenant.get(tenant_id, 0) - 1
        if remaining > 0:
            self._pending_by_tenant[tenant_id] = remaining
        else:
            self._pending_by_tenant.pop(tenant_id, None)

    async def create(
        self,
        *,
        tenant_id: str,
        user_id: int,
        initial_url: Optional[str] = None,
        viewport: Optional[dict] = None,
    ) -> RecordingSession:
        # Reserve a slot atomically before doing any slow setup. Two
        # concurrent POSTs used to both pass the count check before either
        # one inserted, blowing past the cap.
        expired_to_cleanup: list[RecordingSession] = []
        async with self._lock:
            # Sweep expired inline so a slow janitor cycle can't
            # artificially block new recordings. We pop now, teardown
            # off-lock below.
            for sid in list(self._sessions.keys()):
                sess = self._sessions[sid]
                if sess.tenant_id == tenant_id and sess.is_expired():
                    expired_to_cleanup.append(self._sessions.pop(sid))

            active = sum(1 for s in self._sessions.values() if s.tenant_id == tenant_id)
            pending = self._pending_by_tenant.get(tenant_id, 0)
            if active + pending >= self.MAX_PER_TENANT:
                raise RuntimeError(
                    f"Tenant has {active + pending} active recordings (max {self.MAX_PER_TENANT}). "
                    "Discard one before starting another."
                )
            self._pending_by_tenant[tenant_id] = pending + 1

        # Tear down any expired sessions in the background so this
        # request isn't blocked by their cleanup.
        for sess in expired_to_cleanup:
            asyncio.create_task(self._cleanup_session_object(sess))

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
                # Use domcontentloaded (not the default 'load') so the goto
                # returns as soon as the DOM is parsed — many real sites
                # (e.g. Correios) keep loading ads/analytics for 30s+ after
                # the page is usable, which would otherwise block the
                # recorder from streaming for the full default timeout.
                # 45s timeout gives slow connections breathing room.
                await page.goto(initial_url, wait_until="domcontentloaded", timeout=45000)
                session.append_event("navigate", {"url": initial_url})

            async with self._lock:
                self._sessions[session_id] = session
                self._release_pending(tenant_id)

            logger.info(
                "Recorder session %s created (tenant=%s user=%s)",
                session_id, tenant_id, user_id,
            )
            return session

        except Exception:
            async with self._lock:
                self._release_pending(tenant_id)
            # Best-effort teardown if any step above failed
            try:
                await playwright.stop()
            except Exception:
                pass
            raise

    def _wire_page_events(self, session: RecordingSession) -> None:
        """Subscribe to the page-level events the compiler needs.

        Captures top-frame navigations and load events into the session
        and — when a WebSocket relay is currently attached — also
        forwards them to the frontend so the StepLedger updates in real
        time. Click/fill capture is driven from the WS relay layer where
        we already have coordinates and the JS shim's selector lookup.
        """
        page = session.page
        loop = asyncio.get_running_loop()

        def _emit(kind: str, payload: dict) -> None:
            evt = session.append_event(kind, payload)
            if session.relay_send is not None:
                # relay_send is an async lambda; schedule on the running loop.
                # Envelope mirrors cdp_relay._event_envelope so the frontend
                # ledger receives screenshot/driver context for every event,
                # regardless of which source captured it.
                envelope = {
                    "type": "event",
                    "kind": evt.kind,
                    "payload": evt.payload,
                    "screenshot_b64": evt.screenshot_b64,
                    "recorded_driver": evt.recorded_driver,
                    "ts": evt.ts,
                }
                asyncio.ensure_future(
                    session.relay_send(envelope),
                    loop=loop,
                )

        def _on_frame_navigated(frame) -> None:
            if frame == page.main_frame:
                _emit("navigate", {"url": frame.url})

        def _on_load() -> None:
            _emit("load", {"url": page.url})

        page.on("framenavigated", _on_frame_navigated)
        page.on("load", _on_load)

    async def get(self, session_id: str) -> Optional[RecordingSession]:
        return self._sessions.get(session_id)

    async def count_for_tenant(self, tenant_id: str) -> int:
        async with self._lock:
            return sum(1 for s in self._sessions.values() if s.tenant_id == tenant_id)

    async def reap_expired(self) -> int:
        """Tear down every session past its TTL. Returns number reaped."""
        async with self._lock:
            expired = [
                sid for sid, sess in self._sessions.items() if sess.is_expired()
            ]
            sessions_to_cleanup = [self._sessions.pop(sid) for sid in expired]
        count = 0
        for sess in sessions_to_cleanup:
            try:
                await self._cleanup_session_object(sess)
                count += 1
            except Exception as e:
                logger.warning("Janitor teardown failed for %s: %s", sess.session_id, e)
        return count

    # Per-step cap on teardown coroutines. A busy Playwright session can
    # take many seconds to close its context cleanly — we don't want a
    # DELETE request to hang on the client for that long. Each step gets
    # a short budget; if it overruns, we log and move on. The OS reclaims
    # the underlying Chromium process when its parent dies.
    TEARDOWN_STEP_TIMEOUT = 5.0

    async def teardown(self, session_id: str) -> bool:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if not session:
            return False
        await self._cleanup_session_object(session)
        return True

    async def _cleanup_session_object(self, session: RecordingSession) -> None:
        """Tear down a session that's already been popped from _sessions.

        Slot in _sessions has already been freed by the caller, so a
        concurrent create() can immediately reuse the cap budget. This is
        what closes the "Discard then start new" race that used to leak
        409 errors back to the user.
        """
        session_id = session.session_id
        # Cancel agentic driver task first if present (Phase 6 wires this).
        if session.agent_task and not session.agent_task.done():
            session.agent_task.cancel()
            try:
                await asyncio.wait_for(session.agent_task, timeout=self.TEARDOWN_STEP_TIMEOUT)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

        async def _with_timeout(coro_fn, label: str) -> None:
            try:
                await asyncio.wait_for(coro_fn(), timeout=self.TEARDOWN_STEP_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning(
                    "Recorder %s teardown step '%s' exceeded %ss budget — moving on",
                    session_id, label, self.TEARDOWN_STEP_TIMEOUT,
                )
            except Exception as e:
                logger.warning("Recorder %s teardown step '%s' failed: %s", session_id, label, e)

        # Stop the screencast first so Chrome doesn't try to deliver frames
        # into a tearing-down CDP session.
        await _with_timeout(
            lambda: session.cdp.send("Page.stopScreencast"),
            "stopScreencast",
        )
        await _with_timeout(session.cdp.detach, "cdp.detach")
        await _with_timeout(session.context.close, "context.close")
        await _with_timeout(session.browser.close, "browser.close")
        await _with_timeout(session.playwright.stop, "playwright.stop")

        logger.info("Recorder session %s torn down", session_id)

    async def list_session_ids(self) -> list[str]:
        return list(self._sessions.keys())


_registry: Optional[SessionRegistry] = None
_janitor_task: Optional[asyncio.Task] = None


def get_registry() -> SessionRegistry:
    global _registry
    if _registry is None:
        _registry = SessionRegistry()
    return _registry


async def _janitor_loop(interval_seconds: int = 60) -> None:
    """Reap expired recordings every minute.

    Intentionally fire-and-forget — process restart loses all live
    recordings anyway (they're in-memory), so persistence is not a goal.
    """
    registry = get_registry()
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            count = await registry.reap_expired()
            if count:
                logger.info("Recorder janitor reaped %d expired session(s)", count)
        except asyncio.CancelledError:
            logger.info("Recorder janitor cancelled")
            raise
        except Exception as e:  # pragma: no cover — defence in depth
            logger.exception("Recorder janitor error: %s", e)


def start_janitor() -> None:
    """Spawn the background janitor on a running event loop."""
    global _janitor_task
    if _janitor_task and not _janitor_task.done():
        return
    _janitor_task = asyncio.create_task(_janitor_loop(), name="recorder-janitor")


async def stop_janitor() -> None:
    global _janitor_task
    if _janitor_task and not _janitor_task.done():
        _janitor_task.cancel()
        try:
            await _janitor_task
        except (asyncio.CancelledError, Exception):
            pass
    _janitor_task = None
