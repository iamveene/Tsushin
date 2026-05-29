"""WebSocket ↔ CDP relay for a live recording session.

Server → Client (JSON messages):
    {"type": "hello", "session_id": str, "viewport": {"width": int, "height": int}}
    {"type": "frame", "data": <base64 jpeg>, "metadata": {...}}
    {"type": "event", "kind": str, "payload": dict}  # mirrors session.events appends
    {"type": "error", "message": str}

Client → Server:
    {"type": "input.mouse", "action": "move"|"down"|"up"|"wheel",
     "x": int, "y": int, "button": "left"|"middle"|"right",
     "deltaX"?: int, "deltaY"?: int, "modifiers"?: int}
    {"type": "input.key", "action": "down"|"up"|"press",
     "key": str, "code": str, "modifiers"?: int, "text"?: str}
    {"type": "input.text", "text": str}
    {"type": "navigate", "url": str}
    {"type": "marker.captcha", "x": int, "y": int, "width": int, "height": int}
    {"type": "marker.extract", "x": int, "y": int, "width": int, "height": int, "as": str}
    {"type": "marker.vault", "selector": str, "reference": str, "field_meta"?: dict}
    {"type": "ping"}
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from .models import RecordedEvent, RecordingSession

logger = logging.getLogger(__name__)


def _event_envelope(evt: RecordedEvent) -> dict[str, Any]:
    """Build the JSON envelope for a freshly-captured RecordedEvent.

    Carries the screenshot + driver alongside the payload so the StepLedger
    can render real-time thumbnails and the agent/human badge without
    needing a separate fetch.
    """
    return {
        "type": "event",
        "kind": evt.kind,
        "payload": evt.payload,
        "screenshot_b64": evt.screenshot_b64,
        "recorded_driver": evt.recorded_driver,
        "ts": evt.ts,
    }


# Frame stream is best-effort — if the client falls behind we just drop frames
# rather than buffering them. Keeps memory bounded and prevents head-of-line
# blocking when input events queue up.
_SCREENCAST_PARAMS = {
    "format": "jpeg",
    "quality": 60,
    "maxWidth": 1280,
    "maxHeight": 720,
    "everyNthFrame": 1,
}


async def _safe_send(websocket: WebSocket, payload: dict[str, Any]) -> bool:
    try:
        await websocket.send_json(payload)
        return True
    except Exception as e:
        logger.debug("WS send failed (client likely gone): %s", e)
        return False


async def _resolve_selector_at(session: RecordingSession, x: int, y: int) -> dict[str, Any]:
    """Ask the in-page shim what's under (x, y). Returns {'selector', 'meta'} or {}."""
    try:
        return await session.page.evaluate(
            "([x, y]) => window.__tsushinSelectorAt ? window.__tsushinSelectorAt(x, y) : null",
            [x, y],
        ) or {}
    except Exception as e:
        logger.debug("Selector resolve failed at (%s,%s): %s", x, y, e)
        return {}


async def _resolve_focused_selector(session: RecordingSession) -> dict[str, Any]:
    """Resolve the currently focused element's selector + metadata.

    When the user types on the StreamCanvas, the frontend ships an
    `input.text` envelope without a selector — the inner Chromium is the
    only side that knows which element actually owns focus. Without this
    resolution every FILL event compiled to selector=None and the
    compiler fell back to `body` (BUG-768), breaking replay.
    """
    try:
        return await session.page.evaluate(
            "() => window.__tsushinFocusedSelector ? window.__tsushinFocusedSelector() : null"
        ) or {}
    except Exception as e:
        logger.debug("Focused selector resolve failed: %s", e)
        return {}


async def _resolve_focused_value(session: RecordingSession) -> str | None:
    """Read the focused element's current `.value` (BUG-785).

    A `fill` event records the field's FULL value (replace semantics) instead
    of the per-keystroke `Input.insertText` fragment. Under synthetic/automated
    typing the canvas can emit duplicate keystrokes; appending those fragments
    silently amplified the compiled value (e.g. "AD468811215BR" → 37 chars)
    while the StepLedger showed the clean value — a recording that looked
    correct compiled to a broken flow. Reading `document.activeElement.value`
    makes the recorded value match what is actually in the field, so the ledger
    and the compiled flow can never diverge.

    Returns None when the focused node has no string `value` (caller then falls
    back to the envelope text).
    """
    try:
        return await session.page.evaluate(
            "() => { const el = document.activeElement; "
            "return el && typeof el.value === 'string' ? el.value : null; }"
        )
    except Exception as e:
        logger.debug("Focused value resolve failed: %s", e)
        return None


async def _handle_client_message(
    session: RecordingSession,
    websocket: WebSocket,
    raw: str,
) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await session.relay_send({"type": "error", "message": "invalid json"})
        return

    mtype = msg.get("type")
    cdp = session.cdp
    page = session.page

    if mtype == "ping":
        await session.relay_send({"type": "pong"})
        return

    if mtype == "input.mouse":
        action = msg.get("action")
        cdp_type = {
            "move": "mouseMoved",
            "down": "mousePressed",
            "up": "mouseReleased",
            "wheel": "mouseWheel",
        }.get(action)
        if not cdp_type:
            return
        params = {
            "type": cdp_type,
            "x": int(msg.get("x", 0)),
            "y": int(msg.get("y", 0)),
            "button": msg.get("button", "none") if cdp_type != "mouseMoved" else "none",
            "clickCount": 1 if cdp_type in ("mousePressed", "mouseReleased") else 0,
            "modifiers": int(msg.get("modifiers", 0)),
        }
        if cdp_type == "mouseWheel":
            params["deltaX"] = int(msg.get("deltaX", 0))
            params["deltaY"] = int(msg.get("deltaY", 0))
        await cdp.send("Input.dispatchMouseEvent", params)

        # Capture a click event for the ledger when the mouse-down lands on
        # an element — this is the "primary signal" the compiler converts
        # into a click selector row.
        if cdp_type == "mousePressed":
            sel = await _resolve_selector_at(session, params["x"], params["y"])
            evt = session.append_event(
                "click",
                {
                    "x": params["x"],
                    "y": params["y"],
                    "selector": (sel or {}).get("selector"),
                    "meta": (sel or {}).get("meta"),
                },
            )
            await session.relay_send(_event_envelope(evt))
        return

    if mtype == "input.key":
        action = msg.get("action", "press")
        cdp_action = {
            "down": "keyDown",
            "up": "keyUp",
            "press": "char",  # 'press' is a high-level convenience: send a char
        }.get(action, "keyDown")
        params: dict[str, Any] = {
            "type": cdp_action,
            "modifiers": int(msg.get("modifiers", 0)),
        }
        if "key" in msg:
            params["key"] = msg["key"]
        if "code" in msg:
            params["code"] = msg["code"]
        if "text" in msg:
            params["text"] = msg["text"]
        await cdp.send("Input.dispatchKeyEvent", params)
        return

    if mtype == "input.text":
        # `Input.insertText` is the most reliable way to populate a focused
        # input with a known value — bypasses IME, modifier state, etc.
        text = str(msg.get("text", ""))
        if not text:
            return
        # BUG-778: the FRONTEND now suppresses OS-level keystroke
        # amplification before sending input.text (StreamCanvas's
        # handleKeyDown drops repeats of the same key within 30ms). The
        # backend keeps a very tight 8ms backstop in case an in-process
        # caller (e.g. scripted clients) double-sends, but never wider
        # than that — real consecutive same-char typing is >50ms apart
        # and tracking codes legitimately contain "88"/"11"/etc.
        import time as _time
        now = _time.time()
        if (
            session.last_text_insert_value == text
            and now - session.last_text_insert_at < 0.008
        ):
            session.last_text_insert_at = now
            return
        session.last_text_insert_at = now
        session.last_text_insert_value = text
        await cdp.send("Input.insertText", {"text": text})
        # Resolve the focused element selector on the inner Chromium side
        # so the compiled fill row points at a real input, not `body`.
        # Frontend may supply a selector explicitly (e.g., from scripted
        # callers); prefer that, otherwise ask the page shim.
        selector = msg.get("selector")
        field_meta = msg.get("field_meta")
        if not selector:
            focused = await _resolve_focused_selector(session)
            if focused:
                selector = focused.get("selector")
                if not field_meta:
                    field_meta = focused.get("meta")
        # BUG-785: record the focused field's ACTUAL value (replace semantics),
        # not the per-envelope fragment — see _resolve_focused_value. Falls back
        # to the envelope text when the focused node exposes no string value.
        field_value = await _resolve_focused_value(session)
        value = field_value if field_value is not None else text
        evt = session.append_event(
            "fill",
            {"selector": selector, "value": value, "field_meta": field_meta},
        )
        await session.relay_send(_event_envelope(evt))
        return

    if mtype == "navigate":
        url = str(msg.get("url", "")).strip()
        if url:
            try:
                # Same domcontentloaded reasoning as session_manager.create —
                # real sites keep loading analytics/ads long after the
                # page is usable, and we shouldn't block the relay loop on
                # those resources.
                await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception as e:
                await session.relay_send({"type": "error", "message": f"navigate failed: {e}"})
            # framenavigated handler appends the event
        return

    if mtype in ("marker.captcha", "marker.extract"):
        kind = mtype
        x, y = int(msg.get("x", 0)), int(msg.get("y", 0))
        # Center of the marked rect — good enough to resolve a DOM node
        cx = x + int(msg.get("width", 0)) // 2
        cy = y + int(msg.get("height", 0)) // 2
        sel = await _resolve_selector_at(session, cx, cy)
        payload = {
            "rect": [x, y, int(msg.get("width", 0)), int(msg.get("height", 0))],
            "selector": (sel or {}).get("selector"),
            "meta": (sel or {}).get("meta"),
        }
        if mtype == "marker.extract":
            payload["as"] = str(msg.get("as", "")).strip() or "captured_value"
            # "timeline" routes the compiler to a structured execute_script
            # parser (event list + dedupe key) instead of a plain innerText
            # extract — see event_compiler.compile_events_into_nodes.
            capture_kind = str(msg.get("capture_kind", "")).strip()
            if capture_kind:
                payload["capture_kind"] = capture_kind
        evt = session.append_event(kind, payload)
        await session.relay_send(_event_envelope(evt))
        return

    if mtype == "marker.vault":
        payload = {
            "selector": str(msg.get("selector", "")),
            "reference": str(msg.get("reference", "")),
            "field_meta": msg.get("field_meta"),
        }
        # Accept either short-lived in-memory handles (`pvh_`) or
        # canonical vault op:// URIs — the runtime resolver tries `pvh_`
        # first and falls back to PasswordVaultService lookup, so both
        # are valid persistence shapes for browser_secret_references.
        ref = payload["reference"]
        if not (ref.startswith("pvh_") or ref.startswith("op://")):
            await session.relay_send({"type": "error", "message": "vault reference must be a pvh_ handle or op:// URI"})
            return
        evt = session.append_event("marker.vault", payload)
        await session.relay_send(_event_envelope(evt))
        return

    await session.relay_send({"type": "error", "message": f"unknown message type: {mtype}"})


async def relay(session: RecordingSession, websocket: WebSocket) -> None:
    """Pump CDP screencast frames out and dispatch client input until disconnect.

    Relay hardening (BUG-788): a slow or momentarily-blocked client (long-RTT
    link, a backgrounded tab whose rAF is throttled, or heavy main-thread work
    such as `canvas.toDataURL`) must never wedge the session. The previous relay
    (a) gated the screencast ack behind the per-frame client send — so a slow
    client stalled Chromium's frame production — and (b) spawned an unbounded
    `websocket.send_json` task per frame with no single-writer discipline, so
    frame sends and the receive loop's event echoes raced on one Starlette
    WebSocket (concurrent `send_json` corrupts/wedges the connection). The
    symptom was a relay that looked "connected" (WS open) but stopped streaming
    frames AND silently stopped processing all clicks/fills.

    This version:
      * ACKs every screencast frame to Chromium IMMEDIATELY, before any client
        send, so the screencast pipeline is never gated on client drain.
      * Routes every client-bound message through a SINGLE writer task — the
        only place `websocket.send_json` is called — eliminating concurrent
        sends.
      * Treats frames as LOSSY (keeps only the latest; drops intermediates) and
        control/event messages as an ordered must-deliver queue.
      * NEVER blocks the receive loop on a client send (it only enqueues), so
        input is dispatched to the inner Chromium regardless of client speed.
    """

    cdp = session.cdp
    loop = asyncio.get_running_loop()

    # Outbound plumbing for the single-writer model.
    control: deque[dict[str, Any]] = deque()  # ordered, must-deliver
    latest_frame: dict[str, Any] = {"v": None}  # lossy: only the newest frame
    send_wake = asyncio.Event()
    closed = {"v": False}

    def _wake() -> None:
        if not send_wake.is_set():
            send_wake.set()

    async def _enqueue_client(payload: dict[str, Any]) -> None:
        # Non-blocking: queue a control/event message and wake the writer. The
        # receive loop and page-event emitters use this so they never block on
        # a slow socket.
        control.append(payload)
        _wake()

    async def _sender() -> None:
        # The ONLY coroutine that calls websocket.send_json. Drains control
        # messages first (ordered), then sends the latest frame (lossy).
        while not closed["v"]:
            await send_wake.wait()
            send_wake.clear()
            while control or latest_frame["v"] is not None:
                if control:
                    payload = control.popleft()
                else:
                    payload = latest_frame["v"]
                    latest_frame["v"] = None
                try:
                    await websocket.send_json(payload)
                except Exception as e:
                    logger.debug("Recorder WS send failed (client gone?): %s", e)
                    closed["v"] = True
                    return

    sender_task = asyncio.create_task(_sender())

    async def _on_screencast_frame(params: dict) -> None:
        # Cache the latest frame on the session so any event captured between
        # now and the next frame can carry it as `screenshot_b64`. This is the
        # primary source of recorded thumbnails for the BrowserGroup UI.
        frame_data = params.get("data")
        if frame_data:
            session.latest_frame_b64 = frame_data
        # ACK FIRST — never gate Chromium's screencast on the client drain. A
        # missing/late ack stalls the screencast pipeline server-side.
        try:
            await cdp.send("Page.screencastFrameAck", {"sessionId": params.get("sessionId")})
        except Exception:
            pass
        # Lossy: overwrite the latest-frame slot. If the client hasn't drained
        # the previous frame yet, the intermediate frame is simply dropped —
        # bounds memory and prevents a send pile-up.
        latest_frame["v"] = {
            "type": "frame",
            "data": frame_data,
            "metadata": params.get("metadata"),
        }
        _wake()

    def _screencast_callback(params: dict) -> None:
        # `cdp.on` fires synchronously from the playwright thread; schedule
        # the async work on the running loop.
        asyncio.ensure_future(_on_screencast_frame(params), loop=loop)

    cdp.on("Page.screencastFrame", _screencast_callback)

    try:
        await cdp.send("Page.startScreencast", _SCREENCAST_PARAMS)
    except Exception as e:
        closed["v"] = True
        sender_task.cancel()
        try:
            await sender_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await websocket.send_json({"type": "error", "message": f"screencast start failed: {e}"})
        except Exception:
            pass
        return

    await _enqueue_client({
        "type": "hello",
        "session_id": session.session_id,
        "viewport": {
            "width": _SCREENCAST_PARAMS["maxWidth"],
            "height": _SCREENCAST_PARAMS["maxHeight"],
        },
    })

    # Replay any events that fired before this WS connected (initial
    # navigate from create(), reconnect-after-blip, etc.) so the
    # StepLedger doesn't show a stale-feeling zero count.
    for prior in list(session.events):
        await _enqueue_client(_event_envelope(prior))

    # `relay_send` is the single-writer enqueue (async, non-blocking). Page-event
    # emitters (_wire_page_events) and _handle_client_message both route through
    # it, so nothing else ever touches websocket.send_json directly.
    session.relay_send = _enqueue_client

    try:
        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("Recorder WS disconnect (session=%s)", session.session_id)
                break
            await _handle_client_message(session, websocket, raw)
    finally:
        session.relay_send = None
        closed["v"] = True
        _wake()
        sender_task.cancel()
        try:
            await sender_task
        except (asyncio.CancelledError, Exception):
            pass
        try:
            await cdp.send("Page.stopScreencast")
        except Exception:
            pass
        # Don't tear down the session here — the WS may reconnect. Janitor
        # or explicit DELETE handles teardown.
