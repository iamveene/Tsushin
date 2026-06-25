"""Unit tests for the GitHub commits trigger diff/compose engine.

These tests are pure — no PAT, no REST, no DB. They feed synthetic GitHub
commit dicts (newest-first, as the REST API returns) into the module-level pure
functions and assert the new-commit diff, oldest-first ordering, the
"first poll seeds silently" rule, message composition, and dedupe keys.
"""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from channels.github_commits.trigger import (  # noqa: E402
    commit_author,
    commit_summary,
    compose_message,
    compute_new_commits,
    dedupe_key,
    short_sha,
)


def _commit(sha, *, message="Did a thing", login="iamveene", name="Vinicios",
            date="2026-06-25T12:00:00Z", html_url=None):
    return {
        "sha": sha,
        "html_url": html_url or f"https://github.com/iamveene/asm-platform/commit/{sha}",
        "commit": {"message": message, "author": {"name": name, "date": date}},
        "author": ({"login": login} if login else None),
    }


# --------------------------------------------------------------------------- first poll

def test_first_poll_seeds_silently():
    commits = [_commit("aaa"), _commit("bbb")]
    assert compute_new_commits(None, commits, is_first_poll=True) == []


# --------------------------------------------------------------------------- diff

def test_new_commits_returned_oldest_first_and_stop_at_cursor():
    # GitHub returns newest-first: c3, c2, c1(seen)
    commits = [_commit("c3"), _commit("c2"), _commit("c1")]
    new = compute_new_commits("c1", commits, is_first_poll=False)
    assert [c["sha"] for c in new] == ["c2", "c3"]  # oldest-first, c1 excluded


def test_no_new_commits_when_cursor_is_head():
    commits = [_commit("c3"), _commit("c2")]
    assert compute_new_commits("c3", commits, is_first_poll=False) == []


def test_cursor_fell_off_page_treats_all_as_new():
    # stored sha not present in the fetched page (big batch / force-push)
    commits = [_commit("z3"), _commit("z2"), _commit("z1")]
    new = compute_new_commits("old-sha-not-here", commits, is_first_poll=False)
    assert [c["sha"] for c in new] == ["z1", "z2", "z3"]


def test_empty_page_yields_no_events():
    assert compute_new_commits("c1", [], is_first_poll=False) == []


# --------------------------------------------------------------------------- compose

def test_compose_message_with_branch_and_login():
    msg = compose_message(_commit("abc1234def", message="Fix auth refresh"), "iamveene/asm-platform", "develop")
    assert "iamveene/asm-platform@develop" in msg
    assert '"Fix auth refresh"' in msg
    assert "iamveene" in msg
    assert "abc1234" in msg  # short sha (7)
    assert msg.startswith("🔨")


def test_compose_message_first_line_only():
    c = _commit("deadbeef", message="Title line\n\nlong body paragraph\nmore")
    assert '"Title line"' in compose_message(c, "o/r", "develop")


def test_compose_message_without_branch_uses_repo_only():
    msg = compose_message(_commit("abc1234"), "o/r", None)
    assert "o/r" in msg and "@" not in msg.split('"')[0]


def test_compose_message_no_url_suffix_when_missing():
    c = _commit("abc1234", html_url="")
    c["html_url"] = ""
    assert compose_message(c, "o/r", "develop").endswith(").")


# --------------------------------------------------------------------------- helpers

def test_commit_author_prefers_login_then_name():
    assert commit_author(_commit("a", login="gh-login", name="Git Name")) == "gh-login"
    assert commit_author(_commit("a", login=None, name="Git Name")) == "Git Name"
    assert commit_author({"sha": "a", "commit": {}}) == "unknown"


def test_commit_summary_handles_empty():
    assert commit_summary({"sha": "a", "commit": {"message": "   "}}) == "(no message)"
    assert commit_summary({"sha": "a", "commit": {}}) == "(no message)"


def test_short_sha_and_dedupe_key():
    assert short_sha("abcdef1234567") == "abcdef1"
    assert short_sha(None) == "???????"
    assert dedupe_key(7, "abc") == "gh_commit:7:abc"
    assert dedupe_key(7, None) == "gh_commit:7:unknown"
