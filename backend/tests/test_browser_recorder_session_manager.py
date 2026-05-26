"""Unit tests for the recorder SessionRegistry concurrency invariants.

These tests don't spawn real Playwright — they exercise the locking and
slot-reservation logic directly. The bug we're guarding against: two
concurrent `create()` calls used to both pass the per-tenant cap check
before either had inserted into `_sessions`, blowing past the cap.

Also: after `Discard`, the freed slot must be reusable immediately.
"""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from browser_recorder.models import RecordingSession  # noqa: E402
from browser_recorder.session_manager import SessionRegistry  # noqa: E402


def _fake_session(tenant_id: str, session_id: str = "sess-x") -> RecordingSession:
    """Build a RecordingSession with mocked Playwright internals."""
    return RecordingSession(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=1,
        playwright=MagicMock(stop=AsyncMock()),
        browser=MagicMock(close=AsyncMock()),
        context=MagicMock(close=AsyncMock()),
        page=MagicMock(),
        cdp=MagicMock(send=AsyncMock(), detach=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_count_for_tenant_is_lock_safe():
    """count_for_tenant must hold the lock to avoid mid-iteration mutation."""
    reg = SessionRegistry()
    reg._sessions["a"] = _fake_session("t1", "a")
    reg._sessions["b"] = _fake_session("t1", "b")
    reg._sessions["c"] = _fake_session("t2", "c")
    assert await reg.count_for_tenant("t1") == 2
    assert await reg.count_for_tenant("t2") == 1


@pytest.mark.asyncio
async def test_teardown_frees_slot_immediately():
    """After teardown pops the session, the slot must be reusable."""
    reg = SessionRegistry()
    reg._sessions["a"] = _fake_session("t1", "a")
    reg._sessions["b"] = _fake_session("t1", "b")
    assert await reg.count_for_tenant("t1") == 2

    ok = await reg.teardown("a")
    assert ok is True
    # The popped session's cleanup is awaited inside teardown — by the
    # time it returns, _sessions no longer holds the entry.
    assert "a" not in reg._sessions
    assert await reg.count_for_tenant("t1") == 1


@pytest.mark.asyncio
async def test_teardown_returns_false_for_unknown_session():
    reg = SessionRegistry()
    assert await reg.teardown("nope") is False


@pytest.mark.asyncio
async def test_pending_slot_reservation_blocks_third_create(monkeypatch):
    """Two in-flight creates + a third must be rejected.

    Simulate the race directly: stamp two pending slots, then try a
    third — the cap check inside create() should raise.
    """
    reg = SessionRegistry()
    # Reserve both slots manually as if two concurrent POSTs grabbed them.
    reg._pending_by_tenant["t1"] = SessionRegistry.MAX_PER_TENANT

    # Patch async_playwright so the test never tries to spawn a real one.
    monkeypatch.setattr(
        "browser_recorder.session_manager.async_playwright",
        lambda: MagicMock(start=AsyncMock(return_value=MagicMock())),
    )

    with pytest.raises(RuntimeError, match="max"):
        await reg.create(tenant_id="t1", user_id=1)


@pytest.mark.asyncio
async def test_release_pending_decrements_and_cleans():
    reg = SessionRegistry()
    reg._pending_by_tenant["t1"] = 2
    async with reg._lock:
        reg._release_pending("t1")
        assert reg._pending_by_tenant["t1"] == 1
        reg._release_pending("t1")
        # When the counter hits zero, the key is removed so we don't
        # accumulate stale tenant keys over time.
        assert "t1" not in reg._pending_by_tenant


@pytest.mark.asyncio
async def test_reap_expired_pops_under_lock():
    reg = SessionRegistry()
    sess = _fake_session("t1", "old")
    sess.last_active_at = 0  # ancient
    reg._sessions["old"] = sess
    reg._sessions["fresh"] = _fake_session("t1", "fresh")

    count = await reg.reap_expired()
    assert count == 1
    assert "old" not in reg._sessions
    assert "fresh" in reg._sessions
