#!/usr/bin/env python3
"""Enforce the public-repo path allowlist.

Reads .github/path-allowlist.txt (gitignore-style globs of ALLOWED paths) and
fails if any tracked file is outside the allowlist.

This is the bulletproof guard that prevents internal files (CLAUDE.md, BUGS.md,
QA evidence dumps, dev test scripts, audit reports, .private/ leakage, etc.)
from being committed or pushed to the public repo. It does not depend on any
human, AI agent, or contributor following instructions — if a tracked path is
not explicitly allowed, this script exits non-zero and the commit/CI fails.

Run modes:
  - Pre-commit: invoked via .pre-commit-config.yaml; receives staged filenames.
  - CI:        invoked via .github/workflows/path-allowlist.yml; scans the
               full tracked tree (`git ls-files`).
  - Manual:    `python3 scripts/check-path-allowlist.py` scans the full tree.

Implementation note: uses a pure-Python gitignore-style matcher so the script
runs anywhere Python 3 is available, with no third-party dependencies (avoids
PEP 668 friction on homebrew/distro Pythons).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWLIST_FILE = REPO_ROOT / ".github" / "path-allowlist.txt"


def compile_pattern(pat: str) -> re.Pattern[str]:
    """Translate a gitignore-style pattern into an anchored regex.

    Supports: `*` (no slash), `**` (any depth), `**/` (optional any-depth
    prefix), `?`, leading `/` anchor (treated as root-anchored, which is
    already the default here), and trailing `/` (directory match — expanded
    to `/**`). Character classes (`[abc]`) are not used by this allowlist,
    so they are intentionally not implemented.
    """
    if pat.startswith("/"):
        pat = pat[1:]
    if pat.endswith("/"):
        pat = pat + "**"

    rx_parts: list[str] = []
    i = 0
    n = len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if i + 1 < n and pat[i + 1] == "*":
                # `**`
                if i + 2 < n and pat[i + 2] == "/":
                    rx_parts.append("(?:.*/)?")
                    i += 3
                    continue
                rx_parts.append(".*")
                i += 2
                continue
            rx_parts.append("[^/]*")
            i += 1
        elif c == "?":
            rx_parts.append("[^/]")
            i += 1
        else:
            rx_parts.append(re.escape(c))
            i += 1

    return re.compile("^" + "".join(rx_parts) + "$")


def load_patterns() -> list[tuple[bool, re.Pattern[str]]]:
    """Return ordered (is_negation, regex) tuples from the allowlist file."""
    if not ALLOWLIST_FILE.exists():
        sys.stderr.write(f"ERROR: allowlist not found at {ALLOWLIST_FILE}\n")
        sys.exit(2)
    out: list[tuple[bool, re.Pattern[str]]] = []
    for raw in ALLOWLIST_FILE.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        neg = line.startswith("!")
        if neg:
            line = line[1:]
        out.append((neg, compile_pattern(line)))
    return out


def is_allowed(path: str, patterns: list[tuple[bool, re.Pattern[str]]]) -> bool:
    """Apply gitignore-style 'last match wins' semantics."""
    allowed = False
    for neg, rx in patterns:
        if rx.match(path):
            allowed = not neg
    return allowed


def list_tracked_files() -> list[str]:
    """Return all tracked paths in the repo, relative to REPO_ROOT."""
    out = subprocess.check_output(
        ["git", "-C", str(REPO_ROOT), "ls-files"], text=True
    )
    return [line for line in out.splitlines() if line]


def filter_to_tracked(paths: list[str]) -> list[str]:
    if not paths:
        return []
    tracked = set(list_tracked_files())
    return [p for p in paths if p in tracked]


def main() -> int:
    patterns = load_patterns()

    if len(sys.argv) > 1:
        candidate_paths = filter_to_tracked(sys.argv[1:])
    else:
        candidate_paths = list_tracked_files()

    violations = sorted(p for p in candidate_paths if not is_allowed(p, patterns))

    if violations:
        sys.stderr.write(
            "\nERROR: tracked files outside the public-repo allowlist:\n"
        )
        for v in violations[:50]:
            sys.stderr.write(f"  - {v}\n")
        if len(violations) > 50:
            sys.stderr.write(f"  ... and {len(violations) - 50} more\n")
        sys.stderr.write(
            "\n"
            "These paths are NOT in .github/path-allowlist.txt. Either:\n"
            "  (a) Move the file under .private/ (or another untracked location)\n"
            "      because it contains internal/QA/audit/test/dev material.\n"
            "  (b) If it really is needed by users to install or run Tsushin,\n"
            "      add a deliberate pattern to .github/path-allowlist.txt in\n"
            "      this same change so it gets reviewed.\n"
            "\n"
            "Bypassing this guard with --no-verify or by editing the workflow\n"
            "is forbidden by repo policy.\n"
        )
        return 1

    if not sys.argv[1:]:
        total = len(candidate_paths)
        sys.stdout.write(
            f"OK: all {total} tracked files match the public-repo allowlist.\n"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
