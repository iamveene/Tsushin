# /fire_regression -- Targeted Regression Test

Run a targeted regression test against Tsushin. Focus on the area that changed, then expand outward to adjacent features.

## Execution Steps

### Step 1: Identify Changes

Determine what changed since the last known-good state:

```bash
# What files changed?
cd /Users/vinicios/code/tsushin && git diff --name-only HEAD~1

# Categorize by layer
# Backend: backend/**
# Frontend: frontend/**
# Database: **/migrations/**, **/models.py, **/schemas.py
# Docker: docker-compose.yml, **/Dockerfile
# Config: *.json, *.yaml, *.toml
```

Identify the affected area(s):
- **auth** -- login, signup, SSO, JWT, roles
- **agents** -- agent CRUD, builder, skills, personas, contacts
- **playground** -- chat, search, memory, threads, projects
- **flows** -- flow definitions, execution, scheduling
- **hub** -- integrations, shell, sandboxed tools, toolbox
- **settings** -- config, AI settings, sentinel, roles, billing, audit
- **system** -- tenants, users (admin only)
- **watcher** -- dashboard, messages, conversations
- **whatsapp** -- MCP bridge, message routing, group handling

### Step 2: Smoke Test (always run)

These must pass regardless of what changed:

1. **Backend health:**
   ```bash
   curl -sf http://localhost:8081/health
   ```

2. **Frontend loads:**
   Navigate to http://localhost:3030/auth/login using Playwright MCP. Confirm the login page renders.

3. **Login works:**
   Log in as test@example.com / test123. Confirm redirect to dashboard/watcher.

4. **Dashboard loads:**
   Verify the main watcher/dashboard page renders with no console errors.

### Step 3: Feature Test (targeted at changed area)

Navigate to the specific area that changed using Playwright MCP:

| Area | URL | What to verify |
|------|-----|---------------|
| auth | /auth/login, /auth/signup | Form renders, login succeeds |
| agents | /agents | Agent list loads, can open an agent |
| studio | /studio | Agent builder/studio loads |
| playground | /playground | Chat interface renders, can send message |
| flows | /flows | Flow list loads, can view a flow |
| hub | /hub | Hub page loads, integrations visible |
| hub/shell | /hub/shell | Shell interface renders |
| hub/sandboxed-tools | /hub/sandboxed-tools | Tools list loads |
| settings | /settings | Settings page loads |
| settings/sentinel | /settings/sentinel | Sentinel config renders |
| settings/ai-configuration | /settings/ai-configuration | AI config loads |
| settings/team | /settings/team | Team management loads |
| settings/roles | /settings/roles | Roles page renders |
| settings/billing | /settings/billing | Billing page renders |
| settings/audit-logs | /settings/audit-logs | Audit log loads |
| system | /system/tenants | Admin: tenant list loads |
| system/users | /system/users | Admin: user list loads |

Interact with the feature: click buttons, fill forms, verify responses.

### Step 4: Adjacent Feature Tests

Test 2-3 features that are architecturally adjacent to the changed area:

- If **agents** changed: test playground (uses agents), flows (triggers agents), contacts (assigned to agents)
- If **auth** changed: test settings/team (user management), system/users (admin), settings/roles
- If **playground** changed: test agents (selected in playground), settings/ai-configuration (model selection)
- If **flows** changed: test agents (flow triggers), hub (flow integrations), settings (scheduler config)
- If **hub** changed: test playground (tool usage), agents (skill integrations), settings/integrations
- If **settings** changed: test the specific subsystem (sentinel affects agents, AI config affects playground)
- If **database** changed: test ALL areas that use the modified tables

### Step 5: API Verification

Curl key endpoints related to the changed area:

```bash
# Get auth token
TOKEN=$(curl -sf -X POST http://localhost:8081/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Health
curl -sf http://localhost:8081/health | python3 -m json.tool

# Agents list
curl -sf http://localhost:8081/api/agents \
  -H "Authorization: Bearer $TOKEN" \
  -H "tenantid: <tenant_id>" | python3 -m json.tool | head -20

# Playground threads
curl -sf http://localhost:8081/api/playground/threads \
  -H "Authorization: Bearer $TOKEN" \
  -H "tenantid: <tenant_id>" | python3 -m json.tool | head -20

# Flows list
curl -sf http://localhost:8081/api/flows \
  -H "Authorization: Bearer $TOKEN" \
  -H "tenantid: <tenant_id>" | python3 -m json.tool | head -20
```

Adapt the endpoints based on what changed. Always include `tenantid` header for tenant-scoped endpoints.

### Step 6: Service Health Check

```bash
# All containers running?
cd /Users/vinicios/code/tsushin && docker compose ps

# Backend logs -- any errors?
docker compose logs --tail=50 backend 2>&1 | grep -i -E "error|exception|traceback|critical"

# Frontend logs -- any build errors?
docker compose logs --tail=30 frontend 2>&1 | grep -i -E "error|failed"

# PostgreSQL -- healthy?
docker compose exec postgres pg_isready -U tsushin -d tsushin
```

### Step 7: Report and Remediate

Compile results:
- List of tests run and their pass/fail status
- Any errors found in logs
- Any UI elements that failed to render
- Any API endpoints that returned errors

**Auto-trigger /fire_remediation** with the test results to update BUGS.md.

## Output Format

```
=== REGRESSION TEST REPORT ===
Area tested: <area>
Trigger: <what changed>
Date: <date>

SMOKE TESTS:
  [PASS/FAIL] Backend health
  [PASS/FAIL] Frontend loads
  [PASS/FAIL] Login works
  [PASS/FAIL] Dashboard loads

FEATURE TESTS:
  [PASS/FAIL] <specific test 1>
  [PASS/FAIL] <specific test 2>

ADJACENT TESTS:
  [PASS/FAIL] <adjacent feature 1>
  [PASS/FAIL] <adjacent feature 2>

API TESTS:
  [PASS/FAIL] <endpoint 1>
  [PASS/FAIL] <endpoint 2>

SERVICE HEALTH:
  [PASS/FAIL] All containers healthy
  [PASS/FAIL] No backend errors
  [PASS/FAIL] No frontend errors
  [PASS/FAIL] PostgreSQL responsive

RESULT: <PASS / FAIL (N issues)>
===
```

If any test fails, do NOT mark the implementation as complete. Return to fixing.
