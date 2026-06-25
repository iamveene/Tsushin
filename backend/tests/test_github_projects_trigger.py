"""Unit tests for the GitHub Projects v2 trigger diff engine.

These tests are pure — no PAT, no GraphQL, no DB. They feed synthetic board
snapshots into the module-level pure functions and assert the exact
``card_added`` / ``card_assigned`` / ``card_moved`` events, dedupe keys, and the
critical "first poll seeds silently" rule.
"""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from channels.github_projects.trigger import (  # noqa: E402
    BoardEvent,
    build_snapshot,
    compose_message,
    compute_board_events,
    dedupe_key,
)


def _item(node_id, *, status=None, assignees=None, title="Card", url="https://x/1",
          content_type="ISSUE", updated_at="2026-06-25T12:00:00Z", archived=False):
    return {
        "item_node_id": node_id,
        "content_type": content_type,
        "title": title,
        "url": url,
        "status_value": status,
        "assignees": assignees or [],
        "updated_at": updated_at,
        "is_archived": archived,
    }


# --------------------------------------------------------------------------- build_snapshot

def test_build_snapshot_keys_by_node_id_and_sorts_assignees():
    snap = build_snapshot([_item("A", status="Ready", assignees=["zoe", "amy"])])
    assert set(snap.keys()) == {"A"}
    assert snap["A"]["status"] == "Ready"
    assert snap["A"]["assignees"] == ["amy", "zoe"]  # sorted, deduped


def test_build_snapshot_drops_archived_and_idless():
    snap = build_snapshot([
        _item("A", status="Ready"),
        _item("B", status="Done", archived=True),
        _item(None, status="Ready"),
    ])
    assert set(snap.keys()) == {"A"}


# --------------------------------------------------------------------------- first poll

def test_first_poll_seeds_silently():
    current = build_snapshot([_item("A", status="Ready"), _item("B", status="Done")])
    assert compute_board_events({}, current, is_first_poll=True) == []


# --------------------------------------------------------------------------- card_added

def test_card_added_for_new_item():
    stored = build_snapshot([_item("A", status="Ready")])
    current = build_snapshot([_item("A", status="Ready"), _item("B", status="Backlog", title="New")])
    events = compute_board_events(stored, current, is_first_poll=False)
    assert len(events) == 1
    assert events[0].kind == "card_added"
    assert events[0].item_node_id == "B"
    assert events[0].status == "Backlog"
    assert events[0].title == "New"


def test_new_card_with_assignee_emits_only_added():
    # A brand-new card created with an assignee should NOT double-notify.
    stored = build_snapshot([_item("A", status="Ready")])
    current = build_snapshot([
        _item("A", status="Ready"),
        _item("B", status="Ready", assignees=["vini"]),
    ])
    events = compute_board_events(stored, current, is_first_poll=False)
    kinds = [e.kind for e in events]
    assert kinds == ["card_added"]
    assert events[0].item_node_id == "B"


# --------------------------------------------------------------------------- card_moved

def test_card_moved_carries_from_and_to():
    stored = build_snapshot([_item("A", status="Ready")])
    current = build_snapshot([_item("A", status="In progress")])
    events = compute_board_events(stored, current, is_first_poll=False)
    assert len(events) == 1
    e = events[0]
    assert e.kind == "card_moved"
    assert e.from_status == "Ready"
    assert e.to_status == "In progress"


def test_status_cleared_is_a_move():
    stored = build_snapshot([_item("A", status="Done")])
    current = build_snapshot([_item("A", status=None)])
    events = compute_board_events(stored, current, is_first_poll=False)
    assert [e.kind for e in events] == ["card_moved"]
    assert events[0].from_status == "Done"
    assert events[0].to_status is None


# --------------------------------------------------------------------------- card_assigned

def test_card_assigned_for_each_new_assignee():
    stored = build_snapshot([_item("A", status="Ready", assignees=["amy"])])
    current = build_snapshot([_item("A", status="Ready", assignees=["amy", "vini", "zoe"])])
    events = compute_board_events(stored, current, is_first_poll=False)
    assigned = [e for e in events if e.kind == "card_assigned"]
    assert {e.assignee for e in assigned} == {"vini", "zoe"}
    assert all(e.kind == "card_assigned" for e in events)


def test_removing_assignee_emits_nothing():
    stored = build_snapshot([_item("A", status="Ready", assignees=["amy", "vini"])])
    current = build_snapshot([_item("A", status="Ready", assignees=["amy"])])
    assert compute_board_events(stored, current, is_first_poll=False) == []


# --------------------------------------------------------------------------- combined / no-op

def test_no_change_is_noop():
    stored = build_snapshot([_item("A", status="Ready", assignees=["amy"])])
    current = build_snapshot([_item("A", status="Ready", assignees=["amy"])])
    assert compute_board_events(stored, current, is_first_poll=False) == []


def test_move_and_assign_same_poll_emit_both():
    stored = build_snapshot([_item("A", status="Ready", assignees=[])])
    current = build_snapshot([_item("A", status="In review", assignees=["vini"])])
    events = compute_board_events(stored, current, is_first_poll=False)
    kinds = sorted(e.kind for e in events)
    assert kinds == ["card_assigned", "card_moved"]


# --------------------------------------------------------------------------- dedupe keys

def test_dedupe_keys_are_stable_and_distinct():
    added = BoardEvent(kind="card_added", item_node_id="PVTI_1")
    assigned = BoardEvent(kind="card_assigned", item_node_id="PVTI_1", assignee="vini")
    moved = BoardEvent(
        kind="card_moved", item_node_id="PVTI_1",
        from_status="Ready", to_status="Done", updated_at="2026-06-25T12:00:00Z",
    )
    assert dedupe_key(added) == "gh_proj_added:PVTI_1"
    assert dedupe_key(assigned) == "gh_proj_assigned:PVTI_1:vini"
    assert dedupe_key(moved) == "gh_proj_moved:PVTI_1:Ready->Done:2026-06-25T12:00:00Z"
    # All distinct
    assert len({dedupe_key(added), dedupe_key(assigned), dedupe_key(moved)}) == 3


# --------------------------------------------------------------------------- message composition

def test_compose_messages_per_kind():
    board = "ByteSiege"
    added = compose_message(
        BoardEvent(kind="card_added", item_node_id="A", title="Ship it", url="https://x/1", status="Ready"),
        board,
    )
    assert added.startswith("🆕 New card on ByteSiege:")
    assert '"Ship it"' in added and "(in Ready)" in added and "https://x/1" in added

    assigned = compose_message(
        BoardEvent(kind="card_assigned", item_node_id="A", title="Ship it", url="https://x/1", assignee="vini"),
        board,
    )
    assert assigned.startswith("👤")
    assert "assigned to vini" in assigned and "ByteSiege" in assigned

    moved = compose_message(
        BoardEvent(
            kind="card_moved", item_node_id="A", title="Ship it", url="https://x/1",
            from_status="Ready", to_status="In review", updated_at="2026-06-25T12:34:00Z",
        ),
        board,
    )
    assert moved.startswith("🔀")
    assert "Ready → In review" in moved and "2026-06-25 12:34 UTC" in moved


def test_compose_message_handles_missing_url_and_status():
    msg = compose_message(BoardEvent(kind="card_added", item_node_id="A", title="T", url=None, status=None), "B")
    assert "no status" in msg
    assert msg.rstrip().endswith(".")  # no trailing url fragment


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
