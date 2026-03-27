#!/usr/bin/env bash
# ============================================================================
# commit-test-gate.sh -- Commit Gate
# Fires as a PreToolUse hook on Bash commands.
# Checks if the command is a git commit, and if so, verifies that
# regression testing was performed.
# ============================================================================

TOOL_INPUT="$1"

# Only activate on git commit commands
if ! echo "$TOOL_INPUT" | grep -q "git commit"; then
    exit 0
fi

# Ignore commits that are just amending or have --allow-empty
if echo "$TOOL_INPUT" | grep -qE "(--amend|--allow-empty)"; then
    exit 0
fi

# Check for recent regression test evidence
RECENT_MARKERS=$(find /tmp -maxdepth 1 -name "tsushin_regression_ran_*" -mmin -120 2>/dev/null | wc -l)

if [ "$RECENT_MARKERS" -gt 0 ]; then
    echo ""
    echo "=== COMMIT GATE: PASS ==="
    echo "Regression evidence found. Commit allowed."
    echo "========================="
    exit 0
fi

# No regression evidence -- warn but allow
echo ""
echo "=== COMMIT GATE: WARNING ==="
echo "Committing without evidence of regression testing."
echo ""
echo "Recommended before commit:"
echo "  1. Run /fire_regression for the changed area"
echo "  2. At minimum: curl http://localhost:8081/health"
echo "  3. Verify the frontend loads: http://localhost:3030"
echo ""
echo "Proceeding with commit (soft enforcement)."
echo "============================"

# Exit 0 = allow (soft enforcement)
exit 0
