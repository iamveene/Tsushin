"""Watcher contract tests for the media-burst regression.

Regression: when an active conversation is in progress and the user sends
a burst of N voice notes (or any media-only messages), the conversation
debounce buffer joined empty bodies and bailed out with `if not
combined_body: return`, silently dropping every message in the burst.
The transcripts produced by ASR were never delivered.

Fix: media-only messages must bypass the debounce window.

Additional cases (2026-05-15): normal-DM audio bursts must preserve per-chat
send order (regression: `asyncio.gather` resolved transcripts in completion
order), and the watcher cursor must not advance past an unprocessed/failed
triggered message — otherwise the next poll silently skips it.
"""
from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

# Allow tests to import backend modules when run from /app
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp_reader.watcher import MCPWatcher  # noqa: E402


def _make_watcher(callback) -> MCPWatcher:
    return MCPWatcher(
        reader=SimpleNamespace(),
        message_filter=SimpleNamespace(),
        on_message_callback=callback,
        whatsapp_conversation_delay_seconds=1.0,
    )


def _media_msg(idx: int) -> dict:
    return {
        "id": f"audio_{idx}",
        "sender": "5527999616279",
        "chat_id": "5527999616279@s.whatsapp.net",
        "is_group": False,
        "channel": "whatsapp",
        "body": "",  # media-only — empty body
        "media_type": "audio/ogg",
        "timestamp": f"2026-05-06 21:43:{26 + idx}",
    }


def _make_poll_watcher(
    callback,
    messages_to_return: list[dict],
    trigger_value: str = "auto",
) -> MCPWatcher:
    reader = SimpleNamespace(get_new_messages=lambda since: list(messages_to_return))
    msg_filter = SimpleNamespace(should_trigger=lambda msg: trigger_value)
    watcher = MCPWatcher(
        reader=reader,
        message_filter=msg_filter,
        on_message_callback=callback,
        whatsapp_conversation_delay_seconds=1.0,
    )
    watcher.last_timestamp = "2026-05-06 21:43:00"
    return watcher


def _normal_audio_msg(idx: int, chat_id: str = "5527999616279@s.whatsapp.net", second: int | None = None) -> dict:
    return {
        "id": f"audio_{chat_id}_{idx}",
        "sender": chat_id.split("@")[0],
        "chat_id": chat_id,
        "is_group": False,
        "channel": "whatsapp",
        "body": "",
        "media_type": "audio/ogg",
        "timestamp": f"2026-05-06 21:43:{(second if second is not None else 26 + idx):02d}",
    }


def test_media_only_conversation_burst_dispatches_each_message():
    """Seven media messages in a conversation must each fire on_message_callback."""
    callback = AsyncMock()
    watcher = _make_watcher(callback)

    async def go():
        for i in range(7):
            await watcher._handle_conversation_message(_media_msg(i), "conversation")

    asyncio.run(go())

    assert callback.await_count == 7, (
        f"expected 7 dispatches for 7 media messages, got {callback.await_count}"
    )
    delivered_ids = [call.args[0]["id"] for call in callback.await_args_list]
    assert delivered_ids == [f"audio_{i}" for i in range(7)]


def test_text_only_conversation_burst_still_debounces():
    """Text messages keep the debounce-then-aggregate behavior unchanged."""
    callback = AsyncMock()
    watcher = _make_watcher(callback)

    async def go():
        for i in range(3):
            text_msg = _media_msg(i)
            text_msg["media_type"] = ""
            text_msg["body"] = f"hello {i}"
            await watcher._handle_conversation_message(text_msg, "conversation")
        # Wait for debounce flush
        await asyncio.sleep(1.5)

    asyncio.run(go())

    assert callback.await_count == 1, (
        f"expected 1 aggregated dispatch for 3 text messages, got {callback.await_count}"
    )
    aggregated = callback.await_args_list[0].args[0]
    assert aggregated["body"] == "hello 0\nhello 1\nhello 2"


def test_mixed_conversation_burst_dispatches_media_immediately_and_buffers_text():
    """Media bypasses debounce; text in same burst still aggregates after delay."""
    callback = AsyncMock()
    watcher = _make_watcher(callback)

    async def go():
        await watcher._handle_conversation_message(_media_msg(0), "conversation")
        text_msg = _media_msg(1)
        text_msg["media_type"] = ""
        text_msg["body"] = "follow-up"
        await watcher._handle_conversation_message(text_msg, "conversation")
        await watcher._handle_conversation_message(_media_msg(2), "conversation")
        await asyncio.sleep(1.5)

    asyncio.run(go())

    # 1 audio + 1 text-aggregate + 1 audio = 3 dispatches
    assert callback.await_count == 3
    delivered_kinds = [
        "media" if c.args[0].get("media_type") else "text"
        for c in callback.await_args_list
    ]
    assert delivered_kinds == ["media", "media", "text"]


def test_normal_dm_audio_burst_preserves_order_per_chat():
    """6 audios from the same DM sender must be dispatched in send order.

    Regression: ``asyncio.gather(*normal_tasks)`` resolved tasks in completion
    order, so transcripts arrived shuffled when ASR latency varied.
    """
    seen: list[str] = []

    async def slow_then_fast_callback(msg, trigger_type):
        # Simulate variable transcription latency: earlier audios take longer.
        # Without per-chat FIFO, the gather path would deliver audio_5 first.
        idx = int(msg["id"].rsplit("_", 1)[-1])
        await asyncio.sleep(0.05 * (6 - idx))
        seen.append(msg["id"])

    msgs = [_normal_audio_msg(i, second=20 + i) for i in range(6)]
    watcher = _make_poll_watcher(slow_then_fast_callback, msgs, trigger_value="auto")

    asyncio.run(watcher._poll_messages())

    expected = [f"audio_5527999616279@s.whatsapp.net_{i}" for i in range(6)]
    assert seen == expected, (
        f"expected per-chat FIFO order, got {seen}"
    )
    # Cursor lands one second before seen_max_ts so any same-second siblings
    # written to the DB after this poll still get fetched on the next poll.
    # Already-processed messages are filtered by ``processed_message_ids``.
    from datetime import datetime, timedelta

    last_ts = msgs[-1]["timestamp"]
    expected_cursor = (
        datetime.fromisoformat(last_ts) - timedelta(seconds=1)
    ).strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
    assert watcher.last_timestamp == expected_cursor, (
        f"cursor {watcher.last_timestamp!r} != expected {expected_cursor!r}"
    )


def test_normal_dm_audio_burst_parallel_across_chats_preserves_per_chat_order():
    """Two senders sending audios in parallel: each chat's order preserved,
    different chats may interleave."""
    seen: list[str] = []

    async def cb(msg, trigger_type):
        # Make the "older chat" slower so we'd see ordering breakage if drains
        # weren't per-chat FIFO.
        if msg["chat_id"].startswith("111"):
            await asyncio.sleep(0.06)
        else:
            await asyncio.sleep(0.01)
        seen.append(msg["id"])

    chat_a = "1111111111@s.whatsapp.net"
    chat_b = "2222222222@s.whatsapp.net"
    msgs = [
        _normal_audio_msg(0, chat_id=chat_a, second=20),
        _normal_audio_msg(0, chat_id=chat_b, second=21),
        _normal_audio_msg(1, chat_id=chat_a, second=22),
        _normal_audio_msg(1, chat_id=chat_b, second=23),
        _normal_audio_msg(2, chat_id=chat_a, second=24),
        _normal_audio_msg(2, chat_id=chat_b, second=25),
    ]
    watcher = _make_poll_watcher(cb, msgs, trigger_value="auto")

    asyncio.run(watcher._poll_messages())

    chat_a_seen = [m for m in seen if chat_a in m]
    chat_b_seen = [m for m in seen if chat_b in m]
    assert chat_a_seen == [
        f"audio_{chat_a}_0",
        f"audio_{chat_a}_1",
        f"audio_{chat_a}_2",
    ]
    assert chat_b_seen == [
        f"audio_{chat_b}_0",
        f"audio_{chat_b}_1",
        f"audio_{chat_b}_2",
    ]
    assert len(seen) == 6


def test_last_timestamp_not_advanced_past_failed_triggered_message():
    """A failing audio in the burst must leave the cursor before it, so the
    next poll re-fetches the message instead of silently skipping it."""
    fail_id = "audio_5527999616279@s.whatsapp.net_2"

    async def cb(msg, trigger_type):
        if msg["id"] == fail_id:
            raise RuntimeError("simulated ASR failure")

    msgs = [_normal_audio_msg(i, second=20 + i) for i in range(4)]
    watcher = _make_poll_watcher(cb, msgs, trigger_value="auto")

    asyncio.run(watcher._poll_messages())

    # Cursor must land BEFORE the failed message so get_new_messages re-fetches it.
    assert watcher.last_timestamp < msgs[2]["timestamp"], (
        f"cursor {watcher.last_timestamp} advanced past failed message ts {msgs[2]['timestamp']}"
    )
    # Failed message must NOT be in processed_message_ids — it's retriable.
    assert fail_id not in watcher.processed_message_ids
    # Earlier successful messages should be remembered so they don't re-dispatch.
    assert msgs[0]["id"] in watcher.processed_message_ids
    assert msgs[1]["id"] in watcher.processed_message_ids
    # Per-chat FIFO: msg index 3 must NOT have been processed because we
    # stopped draining the chat at the failure.
    assert msgs[3]["id"] not in watcher.processed_message_ids


def test_cursor_rolls_back_to_capture_same_second_ties():
    """Cursor must not silently skip same-second-ties that arrive in a later poll.

    Regression (prod 2026-05-15): a 6-audio burst landed with timestamps
    17:40:21..24 — three of the six shared timestamp 17:40:22. The watcher
    processed audios with ts 17:40:21 and one of the 17:40:22 ties in poll 1,
    then advanced ``last_timestamp`` to 17:40:22. The next poll's reader
    filter ``ts > '17:40:22'`` excluded the remaining two ties, so audios #3
    and #4 were silently dropped. Fix: when nothing is unprocessed in this
    batch, land at ``seen_max_ts - 1 second`` so a future poll picks up any
    same-second siblings that hadn't been written yet. Already-handled
    messages are filtered by ``processed_message_ids``.
    """
    seen_ids: list[str] = []

    async def cb(msg, trigger_type):
        seen_ids.append(msg["id"])

    # Poll 1: only the first two messages are visible in the DB
    # (msg_a and msg_b, both at second=22)
    msg_a = _normal_audio_msg(0, second=22)
    msg_b = _normal_audio_msg(1, second=22)
    msg_b["id"] = "audio_5527999616279@s.whatsapp.net_1"
    poll1_msgs = [msg_a, msg_b]

    # Poll 2: a third message c also has second=22 (a tie that didn't land
    # in poll 1) plus a later message d at second=23.
    msg_c = _normal_audio_msg(2, second=22)
    msg_c["id"] = "audio_5527999616279@s.whatsapp.net_2"
    msg_d = _normal_audio_msg(3, second=23)

    state = {"call": 0}

    def reader_get(_since):
        state["call"] += 1
        if state["call"] == 1:
            return list(poll1_msgs)
        # On the second poll we return whatever has timestamp > last_timestamp
        # — emulating the SQLite reader's behavior with second granularity.
        from datetime import datetime
        try:
            cutoff = datetime.fromisoformat(_since.replace("+00:00", ""))
        except Exception:
            return [msg_a, msg_b, msg_c, msg_d]
        out = []
        for m in [msg_a, msg_b, msg_c, msg_d]:
            try:
                mt = datetime.fromisoformat(m["timestamp"])
            except Exception:
                continue
            if mt > cutoff:
                out.append(m)
        return out

    reader = SimpleNamespace(get_new_messages=reader_get)
    msg_filter = SimpleNamespace(should_trigger=lambda msg: "auto")
    watcher = MCPWatcher(
        reader=reader,
        message_filter=msg_filter,
        on_message_callback=cb,
        whatsapp_conversation_delay_seconds=1.0,
    )
    watcher.last_timestamp = "2026-05-06 21:43:00"

    async def go():
        await watcher._poll_messages()
        # After poll 1, the cursor should have rolled back from second=22 to
        # second=21 — so poll 2's reader will still return msg_c.
        await watcher._poll_messages()

    asyncio.run(go())

    delivered = sorted(seen_ids)
    expected = sorted([msg_a["id"], msg_b["id"], msg_c["id"], msg_d["id"]])
    assert delivered == expected, (
        f"tied messages dropped — delivered={delivered}, expected={expected}"
    )
