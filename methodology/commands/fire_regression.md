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
- **api-v1** -- public API endpoints, OAuth2 auth, API clients, rate limiting

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
| api-clients | /settings/api-clients | Client list loads, can create/revoke |
| api-v1 | (use curl/pytest) | API v1 endpoints respond, auth works |

Interact with the feature: click buttons, fill forms, verify responses.

### Step 4: Adjacent Feature Tests

Test 2-3 features that are architecturally adjacent to the changed area:

- If **agents** changed: test playground (uses agents), flows (triggers agents), contacts (assigned to agents)
- If **auth** changed: test settings/team (user management), system/users (admin), settings/roles
- If **playground** changed: test agents (selected in playground), settings/ai-configuration (model selection)
- If **flows** changed: test agents (flow triggers), hub (flow integrations), settings (scheduler config)
- If **hub** changed: test playground (tool usage), agents (skill integrations), settings/integrations
- If **settings** changed: test the specific subsystem (sentinel affects agents, AI config affects playground)
- If **api-v1** changed: test auth flow (OAuth2 + X-API-Key), agent CRUD, chat, resource listing
- If **database** changed: test ALL areas that use the modified tables (including API v1 if api_client/token tables affected)

### Step 5: API Verification

Use the **Public API v1** for fast programmatic verification. The regression test API client credentials are in `.env` (`TSN_API_CLIENT_ID` and `TSN_API_CLIENT_SECRET`).

**Option A: Public API v1 (Preferred — faster, no UI login needed)**

```bash
# Source credentials from .env
source /Users/vinicios/code/tsushin/.env

# Health
curl -sf http://localhost:8081/api/health | python3 -m json.tool

# List agents (direct API key mode — no token exchange needed)
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" \
  http://localhost:8081/api/v1/agents | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Agents: {d[\"meta\"][\"total\"]}')"

# Chat with an agent (quick functional test)
curl -sf -X POST -H "X-API-Key: $TSN_API_CLIENT_SECRET" \
  -H "Content-Type: application/json" \
  http://localhost:8081/api/v1/agents/1/chat \
  -d '{"message":"Reply with exactly: REGRESSION_OK"}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Status: {d[\"status\"]}, Response: {d.get(\"message\",\"\")[:100]}')"

# List resources
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/skills | python3 -c "import sys,json; print(f'Skills: {len(json.load(sys.stdin)[\"data\"])}')"
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/personas | python3 -c "import sys,json; print(f'Personas: {len(json.load(sys.stdin)[\"data\"])}')"
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/tone-presets | python3 -c "import sys,json; print(f'Tone Presets: {len(json.load(sys.stdin)[\"data\"])}')"

# OAuth2 token exchange (validates auth pipeline)
curl -sf -X POST http://localhost:8081/api/v1/oauth/token \
  -d "grant_type=client_credentials&client_id=$TSN_API_CLIENT_ID&client_secret=$TSN_API_CLIENT_SECRET" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Token: OK ({d[\"expires_in\"]}s)')"
```

**Option B: Internal API (legacy — requires UI login token)**

```bash
# Get auth token via login
TOKEN=$(curl -sf -X POST http://localhost:8081/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Agents list (internal endpoint)
curl -sf http://localhost:8081/api/agents \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20

# Playground threads
curl -sf http://localhost:8081/api/playground/threads \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -20
```

**Option C: Pytest E2E suite (comprehensive — runs all 23 tests)**

```bash
# Copy test file and run inside container
docker cp /Users/vinicios/code/tsushin/backend/tests/test_api_v1_e2e.py tsushin-backend:/app/tests/
docker exec tsushin-backend python -m pytest tests/test_api_v1_e2e.py -v --no-cov
```

This runs: OAuth2 exchange, agent listing (Bearer + X-API-Key), permission enforcement, resource listing, rate limit headers, agent chat, client lifecycle (create/rotate/revoke). All 23 tests must pass.

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
