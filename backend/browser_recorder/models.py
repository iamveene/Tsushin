"""Transient (in-memory) data structures for a recording session.

Nothing in this module is persisted to the database. A recording session is
ephemeral — it lives in process memory from `POST /api/recorder/sessions`
until either `DELETE /api/recorder/sessions/{id}` or the TTL janitor reaps
it. The only persistent artifact a recorder produces is the compiled
FlowNode.config_json written into the existing schema when the user clicks
Save in the UI.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    CDPSession,
    Page,
    Playwright,
)


class RecordingDriver(str, Enum):
    HUMAN = "human"
    AGENT = "agent"


@dataclass
class RecordedEvent:
    """A single event captured during a recording.

    Heterogeneous on purpose — `kind` distinguishes the variant and the
    compiler (Phase 2) walks the list converting each into one or more
    selector rows.

    `kind` values produced in Phase 1:
        - "navigate"        : payload = {"url": str}
        - "click"           : payload = {"x": int, "y": int, "selector": str|None, "fallback_selector": str|None}
        - "fill"            : payload = {"selector": str, "value": str, "field_meta": {...}}
        - "key"             : payload = {"key": str, "modifiers": int}
        - "load"            : payload = {"url": str}     # Page.loadEventFired
        - "marker.captcha"  : payload = {"rect": [x,y,w,h], "selector": str|None}
        - "marker.extract"  : payload = {"rect": [x,y,w,h], "selector": str|None, "as": str}
        - "marker.vault"    : payload = {"selector": str, "reference": str (pvh_...)}
    """

    kind: str
    payload: dict[str, Any]
    ts: float = field(default_factory=time.time)


@dataclass
class RecordingSession:
    """Live recording session bound to a single Playwright Chromium instance."""

    session_id: str
    tenant_id: str
    user_id: int

    playwright: Playwright
    browser: Browser
    context: BrowserContext
    page: Page
    cdp: CDPSession

    started_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)

    current_driver: Optional[RecordingDriver] = None
    events: list[RecordedEvent] = field(default_factory=list)

    # Set when an active WebSocket relay is attached. None means nobody is
    # watching the stream right now — the session still records page events
    # (frameNavigated, loadEventFired) so reconnection is transparent.
    relay_send: Optional[Any] = None  # async callable: (dict) -> None

    # Janitor uses this; default 30 min, hard cap 2h enforced at create time
    # (Phase 7 will plug the cap in).
    ttl_seconds: int = 30 * 60

    # Agentic driver (Phase 6) parks its asyncio.Task here so pause/resume can
    # find it. None when human-driven.
    agent_task: Optional[asyncio.Task] = None
    agent_paused: bool = False

    def touch(self) -> None:
        self.last_active_at = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_active_at) > self.ttl_seconds

    def append_event(self, kind: str, payload: dict[str, Any]) -> None:
        self.events.append(RecordedEvent(kind=kind, payload=payload))
        self.touch()
