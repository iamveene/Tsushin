#!/bin/bash
set -e

echo "=============================================================================="
echo "COMPLETE END-TO-END WHATSAPP MCP SYSTEM TEST"
echo "=============================================================================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS=0
FAIL=0

pass_test() {
    echo -e "${GREEN}✅ PASS${NC}: $1"
    ((PASS++))
}

fail_test() {
    echo -e "${RED}❌ FAIL${NC}: $1"
    ((FAIL++))
}

warn_test() {
    echo -e "${YELLOW}⚠️  WARN${NC}: $1"
}

# Test 1: Database has both instances
echo "TEST 1: Database has both MCP instances"
INSTANCE_COUNT=$(sqlite3 data/agent.db "SELECT COUNT(*) FROM whatsapp_mcp_instance;")
if [ "$INSTANCE_COUNT" -eq 2 ]; then
    pass_test "Database has 2 instances"
else
    fail_test "Database should have 2 instances, found $INSTANCE_COUNT"
fi
echo ""

# Test 2: Containers are running
echo "TEST 2: Docker containers running"
RUNNING_CONTAINERS=$(docker ps | grep mcp | wc -l | tr -d ' ')
if [ "$RUNNING_CONTAINERS" -eq 2 ]; then
    pass_test "2 MCP containers running"
else
    fail_test "Expected 2 containers, found $RUNNING_CONTAINERS"
fi
echo ""

# Test 3: Health endpoints respond
echo "TEST 3: Health endpoints accessible"
if curl -sf http://localhost:8080/api/health > /dev/null; then
    pass_test "Bot MCP health endpoint responding"
else
    fail_test "Bot MCP health endpoint not accessible"
fi

if curl -sf http://localhost:8088/api/health > /dev/null; then
    pass_test "Tester MCP health endpoint responding"
else
    fail_test "Tester MCP health endpoint not accessible"
fi
echo ""

# Test 4: Enhanced health fields present
echo "TEST 4: Enhanced health fields present"
BOT_HEALTH=$(curl -s http://localhost:8080/api/health)
REQUIRED_FIELDS=("authenticated" "connected" "needs_reauth" "is_reconnecting" "reconnect_attempts" "session_age_sec" "last_activity_sec")

for field in "${REQUIRED_FIELDS[@]}"; do
    if echo "$BOT_HEALTH" | grep -q "\"$field\""; then
        pass_test "Bot MCP has field: $field"
    else
        fail_test "Bot MCP missing field: $field"
    fi
done
echo ""

# Test 5: Authentication status
echo "TEST 5: Authentication status"
BOT_AUTH=$(echo "$BOT_HEALTH" | python3 -c "import sys, json; print(json.load(sys.stdin).get('authenticated', False))")
TESTER_AUTH=$(curl -s http://localhost:8088/api/health | python3 -c "import sys, json; print(json.load(sys.stdin).get('authenticated', False))")

if [ "$BOT_AUTH" = "True" ]; then
    pass_test "Bot MCP authenticated"
else
    warn_test "Bot MCP not authenticated yet (needs QR scan)"
fi

if [ "$TESTER_AUTH" = "True" ]; then
    pass_test "Tester MCP authenticated"
else
    fail_test "Tester MCP not authenticated"
fi
echo ""

# Test 6: Keepalive working
echo "TEST 6: Keepalive mechanism"
TESTER_ACTIVITY=$(curl -s http://localhost:8088/api/health | python3 -c "import sys, json; print(json.load(sys.stdin).get('last_activity_sec', 999))")

if [ "$TESTER_ACTIVITY" -lt 35 ]; then
    pass_test "Tester keepalive working (last_activity: ${TESTER_ACTIVITY}s)"
else
    fail_test "Tester keepalive not working (last_activity: ${TESTER_ACTIVITY}s)"
fi
echo ""

# Test 7: Session files exist
echo "TEST 7: Session files exist"
if [ -f "data/tester-mcp/store/whatsapp.db" ]; then
    pass_test "Tester session file exists"
else
    fail_test "Tester session file missing"
fi

BOT_SESSION_DIR=$(sqlite3 data/agent.db "SELECT session_data_path FROM whatsapp_mcp_instance WHERE instance_type='agent' LIMIT 1;" | sed 's|/app/data/|data/|')
if [ -d "$BOT_SESSION_DIR" ]; then
    pass_test "Bot session directory exists: $BOT_SESSION_DIR"
else
    fail_test "Bot session directory missing: $BOT_SESSION_DIR"
fi
echo ""

# Test 8: Message cache cleaned
echo "TEST 8: Message cache cleanup"
CACHE_COUNT=$(sqlite3 data/agent.db "SELECT COUNT(*) FROM message_cache;")
OLD_CACHE=$(sqlite3 data/agent.db "SELECT COUNT(*) FROM message_cache WHERE seen_at < datetime('now', '-7 days');")

echo "  Cache entries: $CACHE_COUNT"
echo "  Old entries (>7 days): $OLD_CACHE"

if [ "$OLD_CACHE" -eq 0 ]; then
    pass_test "No old message cache entries"
else
    warn_test "$OLD_CACHE old entries remain (should clean regularly)"
fi
echo ""

# Test 9: No failed scheduled events
echo "TEST 9: Scheduled events clean"
FAILED_EVENTS=$(sqlite3 data/agent.db "SELECT COUNT(*) FROM scheduled_events WHERE status='FAILED';")

if [ "$FAILED_EVENTS" -eq 0 ]; then
    pass_test "No failed scheduled events"
else
    warn_test "$FAILED_EVENTS failed events (should clean)"
fi
echo ""

# Test 10: Backend can reach MCPs via Docker network
echo "TEST 10: Backend → MCP connectivity"
if docker exec tsushin-backend curl -sf http://tester-mcp:8080/api/health > /dev/null; then
    pass_test "Backend can reach Tester MCP"
else
    fail_test "Backend cannot reach Tester MCP"
fi

BOT_CONTAINER=$(docker ps | grep "mcp-agent" | awk '{print $NF}')
if [ -n "$BOT_CONTAINER" ]; then
    if docker exec tsushin-backend curl -sf http://${BOT_CONTAINER}:8080/api/health > /dev/null; then
        pass_test "Backend can reach Bot MCP"
    else
        fail_test "Backend cannot reach Bot MCP"
    fi
fi
echo ""

# Summary
echo "=============================================================================="
echo "TEST SUMMARY"
echo "=============================================================================="
echo ""
echo -e "${GREEN}PASSED: $PASS${NC}"
echo -e "${RED}FAILED: $FAIL${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
    exit 0
else
    echo -e "${RED}⚠️  SOME TESTS FAILED${NC}"
    exit 1
fi
