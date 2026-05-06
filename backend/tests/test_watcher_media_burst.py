"""Watcher contract tests for the media-burst regression.

Regression: when an active conversation is in progress and the user sends
a burst of N voice notes (or any media-only messages), the conversation
debounce buffer joined empty bodies and bailed out with `if not
combined_body: return`, silently dropping every message in the burst.
The transcripts produced by ASR were never delivered.

Fix: media-only messages must bypass the debounce window.
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
