#!/usr/bin/env bash
# ============================================================================
# e2e-test-gate.sh -- Stop Gate
# Fires when Claude is about to stop (conversation ending or task "done").
# Checks whether regression testing was performed during this session.
# ============================================================================

# This hook runs as a "Stop" hook. It receives no arguments.
# It checks for evidence that /fire_regression was run by looking for
# regression report markers in the conversation context.

# Soft enforcement: output a warning message if no evidence found.
# The hook returns exit code 0 (allow) always, but the message serves
# as a reminder that will appear in the conversation.

MARKER_FILE="/tmp/tsushin_regression_ran_$$"

# Check if regression was run in this session (parent process tree)
# We look for our session marker files (created by fire_regression runs)
RECENT_MARKERS=$(find /tmp -maxdepth 1 -name "tsushin_regression_ran_*" -mmin -120 2>/dev/null | wc -l)

if [ "$RECENT_MARKERS" -gt 0 ]; then
    # Regression was run recently
    echo ""
    echo "=== E2E TEST GATE: PASS ==="
    echo "Regression testing evidence found. Proceeding."
    echo "==========================="
    exit 0
fi

# No evidence of regression testing
echo ""
echo "=== E2E TEST GATE: WARNING ==="
echo "No evidence of regression testing found in this session."
echo ""
echo "Before marking this task as complete, you should:"
echo "  1. Run /fire_regression to test the changed area"
echo "  2. Verify all smoke tests pass (health, login, dashboard)"
echo "  3. Check service health: docker compose ps"
echo ""
echo "If you already tested manually, acknowledge by confirming"
echo "that testing was performed."
echo "================================"

# Exit 0 = allow (soft enforcement, not blocking)
exit 0
