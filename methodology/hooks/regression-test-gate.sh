#!/usr/bin/env bash
# ============================================================================
# regression-test-gate.sh -- Regression Gate
# Fires as a PreToolUse hook on Bash commands.
# Detects Docker service restarts and flags that regression testing
# should be performed after the restart.
# ============================================================================

TOOL_INPUT="$1"

# Only activate on docker-related restart/rebuild commands
if ! echo "$TOOL_INPUT" | grep -qE "docker.*(restart|up|build|compose)"; then
    exit 0
fi

# Ignore read-only docker commands (ps, logs, exec for queries)
if echo "$TOOL_INPUT" | grep -qE "docker.*(ps|logs|inspect|images)"; then
    exit 0
fi

# Ignore docker exec commands (not restarts)
if echo "$TOOL_INPUT" | grep -q "docker exec"; then
    exit 0
fi

# This looks like a service restart/rebuild
# Clear any previous regression markers (restart invalidates previous tests)
find /tmp -maxdepth 1 -name "tsushin_regression_ran_*" -mmin +5 -delete 2>/dev/null

echo ""
echo "=== REGRESSION GATE: NOTICE ==="
echo "Docker service restart/rebuild detected."
echo ""
echo "After the services are back up, you should:"
echo "  1. Wait for containers to be healthy: docker compose ps"
echo "  2. Verify backend health: curl http://localhost:8081/health"
echo "  3. Run /fire_regression to validate nothing broke"
echo ""
echo "Proceeding with restart."
echo "================================"

# Exit 0 = allow (this is informational, not blocking)
exit 0
