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


async def _handle_client_message(
    session: RecordingSession,
    websocket: WebSocket,
    raw: str,
) -> None:
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await _safe_send(websocket, {"type": "error", "message": "invalid json"})
        return

    mtype = msg.get("type")
    cdp = session.cdp
    page = session.page

    if mtype == "ping":
        await _safe_send(websocket, {"type": "pong"})
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
            await _safe_send(websocket, _event_envelope(evt))
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
        await cdp.send("Input.insertText", {"text": text})
        # We don't know the *target* selector unless the client supplied it
        # — Phase 2 collapses key/text streams into one `fill` row using the
        # last focused element. For now record the raw text event.
        selector = msg.get("selector")
        field_meta = msg.get("field_meta")
        evt = session.append_event(
            "fill",
            {"selector": selector, "value": text, "field_meta": field_meta},
        )
        await _safe_send(websocket, _event_envelope(evt))
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
                await _safe_send(websocket, {"type": "error", "message": f"navigate failed: {e}"})
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
        evt = session.append_event(kind, payload)
        await _safe_send(websocket, _event_envelope(evt))
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
            await _safe_send(websocket, {"type": "error", "message": "vault reference must be a pvh_ handle or op:// URI"})
            return
        evt = session.append_event("marker.vault", payload)
        await _safe_send(websocket, _event_envelope(evt))
        return

    await _safe_send(websocket, {"type": "error", "message": f"unknown message type: {mtype}"})


async def relay(session: RecordingSession, websocket: WebSocket) -> None:
    """Pump CDP screencast frames out and dispatch client input until disconnect."""

    cdp = session.cdp
    loop = asyncio.get_running_loop()

    async def _on_screencast_frame(params: dict) -> None:
        # Cache the latest frame on the session so any event captured between
        # now and the next frame can carry it as `screenshot_b64`. This is the
        # primary source of recorded thumbnails for the BrowserGroup UI.
        frame_data = params.get("data")
        if frame_data:
            session.latest_frame_b64 = frame_data
        sent = await _safe_send(websocket, {
            "type": "frame",
            "data": frame_data,
            "metadata": params.get("metadata"),
        })
        # Always ack — even if the WS is gone, so CDP keeps a clean state.
        # Failing to ack stalls the screencast pipeline server-side.
        try:
            await cdp.send("Page.screencastFrameAck", {"sessionId": params.get("sessionId")})
        except Exception:
            pass
        if not sent:
            # Client likely gone; the outer loop will exit on the next receive.
            return

    def _screencast_callback(params: dict) -> None:
        # `cdp.on` fires synchronously from the playwright thread; schedule
        # the async work on the running loop.
        asyncio.ensure_future(_on_screencast_frame(params), loop=loop)

    cdp.on("Page.screencastFrame", _screencast_callback)

    try:
        await cdp.send("Page.startScreencast", _SCREENCAST_PARAMS)
    except Exception as e:
        await _safe_send(websocket, {"type": "error", "message": f"screencast start failed: {e}"})
        return

    await _safe_send(websocket, {
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
        await _safe_send(websocket, _event_envelope(prior))

    session.relay_send = lambda payload: _safe_send(websocket, payload)

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
        try:
            await cdp.send("Page.stopScreencast")
        except Exception:
            pass
        # Don't tear down the session here — the WS may reconnect. Janitor
        # or explicit DELETE handles teardown.
