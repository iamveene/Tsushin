"""Regression: recorder relay must not wedge on a slow/stuck client (BUG-788).

The old relay (a) acked each screencast frame only AFTER the per-frame client
send and (b) echoed captured events with a blocking `websocket.send_json` inside
the receive loop. A client that stopped draining (slow link, backgrounded tab,
heavy main-thread work) therefore back-pressured the socket, which stalled the
screencast acks AND blocked the receive loop — so clicks/fills silently stopped
being dispatched to the inner Chromium while the WS still showed "connected".

The fix routes every client-bound message through a single writer task and
enqueues (non-blocking) from the receive loop, and acks frames first. This test
pins the key property: even when the client's `send_json` hangs forever, the
relay still PROCESSES incoming input (dispatches it to CDP) and returns cleanly
on disconnect. Against the old code this test times out.
"""

import asyncio
import json
import types

import pytest

from browser_recorder import cdp_relay


class _HangingWebSocket:
    """A client that accepts a fixed script of inbound messages but never drains
    outbound data — every send_json hangs forever (full back-pressure)."""

    def __init__(self, inbound):
        self._inbound = list(inbound)
        self.send_calls = 0

    async def receive_text(self):
        if self._inbound:
            return self._inbound.pop(0)
        raise cdp_relay.WebSocketDisconnect(code=1000)

    async def send_json(self, payload):
        self.send_calls += 1
        await asyncio.Event().wait()  # never resolves → stuck client


class _FakeCDP:
    def __init__(self):
        self.calls = []

    def on(self, _event, _cb):
        return None

    async def send(self, method, params=None):
        self.calls.append((method, params))
        return {}


class _FakeEvent:
    def __init__(self, kind, payload):
        self.kind = kind
        self.payload = payload
        self.screenshot_b64 = None
        self.recorded_driver = None
        self.ts = 0.0


class _FakePage:
    async def evaluate(self, _script, *_args):
        # Used by _resolve_selector_at / _resolve_focused_*; return a plausible
        # selector so a click resolves to a real-looking node.
        return {"selector": "input#objeto", "meta": {"tag": "input"}}


class _FakeSession:
    def __init__(self):
        self.session_id = "sess-test"
        self.tenant_id = "t1"
        self.cdp = _FakeCDP()
        self.page = _FakePage()
        self.events = []
        self.latest_frame_b64 = None
        self.relay_send = None
        self.last_text_insert_value = None
        self.last_text_insert_at = 0.0

    def append_event(self, kind, payload):
        evt = _FakeEvent(kind, payload)
        self.events.append(evt)
        return evt


@pytest.mark.asyncio
async def test_relay_processes_input_while_client_send_is_stuck():
    session = _FakeSession()
    inbound = [
        json.dumps({"type": "ping"}),
        json.dumps({
            "type": "input.mouse", "action": "down",
            "x": 400, "y": 242, "button": "left", "modifiers": 0,
        }),
    ]
    ws = _HangingWebSocket(inbound)

    # With the fix this returns promptly (disconnect drains the inbound script);
    # the old blocking-echo relay would hang here, tripping the timeout.
    await asyncio.wait_for(cdp_relay.relay(session, ws), timeout=5.0)

    methods = [m for (m, _p) in session.cdp.calls]
    # The mouse-down was dispatched to the inner Chromium despite the stuck client.
    assert "Input.dispatchMouseEvent" in methods, methods
    # And the click was captured into the session ledger.
    assert any(e.kind == "click" for e in session.events), [e.kind for e in session.events]


@pytest.mark.asyncio
async def test_relay_acks_frames_before_client_send():
    """Frame acks must not be gated behind the (stuck) client send: a screencast
    frame delivered while the client is stuck should still be ACKed to Chromium."""
    session = _FakeSession()
    ws = _HangingWebSocket(inbound=[])  # disconnects immediately after setup

    captured = {}

    real_on = session.cdp.on

    def _capture_on(event, cb):
        if event == "Page.screencastFrame":
            captured["cb"] = cb
        return real_on(event, cb)

    session.cdp.on = _capture_on

    async def _drive():
        # Let relay set up (register callback, start screencast), then deliver a
        # frame and confirm it is ACKed even though no client send can complete.
        await asyncio.sleep(0.05)
        cb = captured.get("cb")
        if cb:
            cb({"data": "AAAA", "sessionId": "s1"})
            await asyncio.sleep(0.05)
        # session.events empty + inbound empty → receive_text raises disconnect

    await asyncio.wait_for(asyncio.gather(cdp_relay.relay(session, ws), _drive()), timeout=5.0)

    methods = [m for (m, _p) in session.cdp.calls]
    assert "Page.screencastFrameAck" in methods, methods
    assert session.latest_frame_b64 == "AAAA"
