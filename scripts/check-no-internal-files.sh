#!/usr/bin/env bash
# Block internal/never-push files from being committed.
# Runs as a pre-commit hook (.pre-commit-config.yaml -> block-internal-files).
#
# What it blocks (at any directory depth):
#   - CLAUDE.md, AGENTS.md, BUGS.md, BUGS_*.md, BUGS-*.md
#   - ROADMAP.md, ROADMAP_*.md
#   - *_bugs.md, *_BUGS.md, wave_*_bugs.md
#   - *-playbook.md, *_playbook.md, PLAYBOOK.md
#   - Anything under .private/
#
# Exits non-zero if any staged path matches.

set -euo pipefail

# pre-commit passes staged filenames as args; if invoked manually with no args,
# fall back to scanning everything currently staged.
if [ "$#" -eq 0 ]; then
  mapfile -t files < <(git diff --cached --name-only --diff-filter=ACMR)
else
  files=("$@")
fi

if [ "${#files[@]}" -eq 0 ]; then
  exit 0
fi

bad=()
for f in "${files[@]}"; do
  base="$(basename -- "$f")"
  case "$f" in
    .private/*|*/.private/*)
      bad+=("$f  (under .private/)") ;;
  esac
  case "$base" in
    CLAUDE.md|AGENTS.md|BUGS.md|ROADMAP.md|PLAYBOOK.md|DEPLOYMENT-TEST-PLAYBOOK.md|deployment-test-playbook.md)
      bad+=("$f  (internal file: $base)") ;;
    BUGS_*.md|BUGS-*.md|ROADMAP_*.md|ROADMAP-*.md)
      bad+=("$f  (internal file: $base)") ;;
    *_bugs.md|*_BUGS.md|wave_*_bugs.md)
      bad+=("$f  (bug-tracker pattern: $base)") ;;
    *-playbook.md|*_playbook.md)
      bad+=("$f  (playbook pattern: $base)") ;;
  esac
done

if [ "${#bad[@]}" -gt 0 ]; then
  echo "" >&2
  echo "ERROR: refusing to commit — internal/never-push files detected:" >&2
  printf '  - %s\n' "${bad[@]}" >&2
  echo "" >&2
  echo "These files are gitignored as internal-only. If you really need to commit one," >&2
  echo "rename it or move it out of .private/, but the default answer is NO." >&2
  echo "Bypassing this guard with --no-verify is forbidden by repo policy." >&2
  exit 1
fi

exit 0
