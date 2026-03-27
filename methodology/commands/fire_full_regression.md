# /fire_full_regression -- Full Platform Regression Audit

Run a comprehensive regression test across the entire Tsushin platform. This is the nuclear option -- test everything.

Use this when:
- Major refactoring was done
- Database migrations were applied
- Docker configuration changed
- Multiple areas were modified simultaneously
- Before a release merge to main

## Execution Steps

### Phase 1: Infrastructure Health

```bash
# All containers up and healthy
cd /Users/vinicios/code/tsushin && docker compose ps

# Backend health endpoint
curl -sf http://localhost:8081/health | python3 -m json.tool

# PostgreSQL connectivity
docker compose exec postgres pg_isready -U tsushin -d tsushin

# Backend can reach PostgreSQL
docker compose logs --tail=10 backend 2>&1 | grep -i "database"
```

### Phase 2: Authentication Suite

Using Playwright MCP:

1. **Login page** -- Navigate to http://localhost:3030/auth/login
   - Verify form renders (email, password fields, submit button)
   - Log in as test@example.com / test123
   - Verify redirect to dashboard

2. **Signup page** -- Navigate to http://localhost:3030/auth/signup
   - Verify form renders

3. **SSO callback** -- Navigate to http://localhost:3030/auth/sso-callback
   - Verify page loads (may show error without valid SSO state, that is expected)

4. **Forgot password** -- Navigate to http://localhost:3030/auth/forgot-password
   - Verify form renders

5. **API auth:**
   ```bash
   # Login
   TOKEN=$(curl -sf -X POST http://localhost:8081/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"test123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
   echo "Token obtained: ${TOKEN:0:20}..."

   # Verify token works
   curl -sf http://localhost:8081/api/agents \
     -H "Authorization: Bearer $TOKEN" \
     -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
   ```

### Phase 3: Watcher / Dashboard

Using Playwright MCP (logged in):

1. Navigate to http://localhost:3030 (root -- should redirect to dashboard or watcher)
2. Verify dashboard content loads (messages, agent activity, conversations)
3. Check for console errors

### Phase 4: Agents

Using Playwright MCP (logged in):

1. **Agent list** -- Navigate to http://localhost:3030/agents
   - Verify agent cards/list renders
   - Click on an agent to open detail view

2. **Agent detail** -- /agents/[id]
   - Verify agent configuration loads
   - Check tabs/sections render

3. **Studio** -- Navigate to http://localhost:3030/studio
   - Verify agent builder interface loads

4. **Personas** -- Navigate to http://localhost:3030/agents/personas
   - Verify persona list renders

5. **Contacts** -- Navigate to http://localhost:3030/agents/contacts
   - Verify contact list renders

6. **Projects** -- Navigate to http://localhost:3030/agents/projects
   - Verify projects list renders

7. **Security** -- Navigate to http://localhost:3030/agents/security
   - Verify security settings render

8. **API verification:**
   ```bash
   curl -sf http://localhost:8081/api/agents \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Agents: {len(d) if isinstance(d,list) else \"ok\"}')"

   curl -sf http://localhost:8081/api/personas \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/contacts \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
   ```

### Phase 5: Playground

Using Playwright MCP (logged in):

1. **Playground main** -- Navigate to http://localhost:3030/playground
   - Verify chat interface renders
   - Verify agent selector is present
   - Verify message input is functional

2. **Playground projects** -- Navigate to http://localhost:3030/playground/projects
   - Verify projects view renders

3. **API verification:**
   ```bash
   curl -sf http://localhost:8081/api/playground/threads \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/memory \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
   ```

### Phase 6: Flows

Using Playwright MCP (logged in):

1. **Flow list** -- Navigate to http://localhost:3030/flows
   - Verify flow list/cards render
   - Verify create button is present

2. **API verification:**
   ```bash
   curl -sf http://localhost:8081/api/flows \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/scheduler/jobs \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
   ```

### Phase 7: Hub

Using Playwright MCP (logged in):

1. **Hub main** -- Navigate to http://localhost:3030/hub
   - Verify hub page renders with integration cards

2. **Shell** -- Navigate to http://localhost:3030/hub/shell
   - Verify shell interface renders

3. **Sandboxed tools** -- Navigate to http://localhost:3030/hub/sandboxed-tools
   - Verify tools list renders

4. **Asana** -- Navigate to http://localhost:3030/hub/asana
   - Verify Asana integration page renders

5. **API verification:**
   ```bash
   curl -sf http://localhost:8081/api/hub/integrations \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/sandboxed-tools \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/skills \
     -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
   ```

### Phase 8: Settings

Using Playwright MCP (logged in):

1. **Settings main** -- Navigate to http://localhost:3030/settings
2. **Organization** -- /settings/organization
3. **AI Configuration** -- /settings/ai-configuration
4. **Sentinel** -- /settings/sentinel
5. **Filtering** -- /settings/filtering
6. **Team** -- /settings/team
7. **Roles** -- /settings/roles
8. **Billing** -- /settings/billing
9. **Audit Logs** -- /settings/audit-logs
10. **Integrations** -- /settings/integrations
11. **Model Pricing** -- /settings/model-pricing
12. **Prompts** -- /settings/prompts
13. **Security** -- /settings/security
14. **API Clients** -- /settings/api-clients
   - Verify client list renders
   - Verify create button present (for owner/admin)

For each: verify the page renders without errors.

**API verification:**
```bash
curl -sf http://localhost:8081/api/sentinel/profiles \
  -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

curl -sf http://localhost:8081/api/system-ai/config \
  -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

curl -sf http://localhost:8081/api/team \
  -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"

curl -sf http://localhost:8081/api/prompts \
  -H "Authorization: Bearer $TOKEN" -H "tenantid: <tenant_id>" -o /dev/null -w "%{http_code}"
```

### Phase 9: System (Admin Only)

Log in as testadmin@example.com / admin123, then:

1. **Tenants** -- Navigate to http://localhost:3030/system/tenants
   - Verify tenant list renders

2. **Users** -- Navigate to http://localhost:3030/system/users
   - Verify user list renders

3. **Plans** -- Navigate to http://localhost:3030/system/plans
   - Verify plans page renders

4. **Integrations** -- Navigate to http://localhost:3030/system/integrations
   - Verify system integrations page renders

5. **API verification:**
   ```bash
   ADMIN_TOKEN=$(curl -sf -X POST http://localhost:8081/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"testadmin@example.com","password":"admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

   curl -sf http://localhost:8081/api/tenants \
     -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/global-users \
     -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}"

   curl -sf http://localhost:8081/api/plans \
     -H "Authorization: Bearer $ADMIN_TOKEN" -o /dev/null -w "%{http_code}"
   ```

### Phase 10: Public API v1

The Public API v1 provides a fast way to validate core functionality without browser automation. Credentials are in `.env`.

**10a. Quick validation (X-API-Key mode):**

```bash
source /Users/vinicios/code/tsushin/.env

# Auth pipeline
curl -sf -X POST http://localhost:8081/api/v1/oauth/token \
  -d "grant_type=client_credentials&client_id=$TSN_API_CLIENT_ID&client_secret=$TSN_API_CLIENT_SECRET" \
  | python3 -c "import sys,json; print(f'OAuth2: OK ({json.load(sys.stdin)[\"expires_in\"]}s)')"

# Agent listing
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/agents \
  | python3 -c "import sys,json; print(f'Agents: {json.load(sys.stdin)[\"meta\"][\"total\"]}')"

# Agent chat (functional test)
curl -sf -X POST -H "X-API-Key: $TSN_API_CLIENT_SECRET" -H "Content-Type: application/json" \
  http://localhost:8081/api/v1/agents/1/chat \
  -d '{"message":"Reply with exactly: REGRESSION_OK"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Chat: {d[\"status\"]} ({d.get(\"execution_time_ms\",0)}ms)')"

# Resources
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/skills | python3 -c "import sys,json; print(f'Skills: {len(json.load(sys.stdin)[\"data\"])}')"
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/personas | python3 -c "import sys,json; print(f'Personas: {len(json.load(sys.stdin)[\"data\"])}')"
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/tools | python3 -c "import sys,json; print(f'Tools: {len(json.load(sys.stdin)[\"data\"])}')"
curl -sf -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/tone-presets | python3 -c "import sys,json; print(f'Presets: {len(json.load(sys.stdin)[\"data\"])}')"
```

**10b. Full E2E test suite (23 tests):**

```bash
docker cp /Users/vinicios/code/tsushin/backend/tests/test_api_v1_e2e.py tsushin-backend:/app/tests/
docker exec tsushin-backend python -m pytest tests/test_api_v1_e2e.py -v --no-cov
```

Covers: OAuth2 exchange, agent listing (Bearer + X-API-Key), permission enforcement, resource listing, rate limit headers, sync chat, client lifecycle (create/rotate/revoke). All 23 must pass.

**10c. UI: Settings > API Clients:**

Using Playwright MCP:
1. Navigate to http://localhost:3030/settings/api-clients
2. Verify client list renders
3. Verify create/rotate/revoke buttons present (for owner/admin)

### Phase 11: API Endpoint Sweep

Hit every major API endpoint and verify non-error responses:

```bash
ENDPOINTS=(
  "GET /health"
  "GET /api/agents"
  "GET /api/personas"
  "GET /api/contacts"
  "GET /api/playground/threads"
  "GET /api/memory"
  "GET /api/flows"
  "GET /api/scheduler/jobs"
  "GET /api/hub/integrations"
  "GET /api/sandboxed-tools"
  "GET /api/skills"
  "GET /api/skill-integrations"
  "GET /api/sentinel/profiles"
  "GET /api/sentinel/exceptions"
  "GET /api/system-ai/config"
  "GET /api/team"
  "GET /api/prompts"
  "GET /api/knowledge"
  "GET /api/projects"
  "GET /api/commands"
  "GET /api/cache/stats"
  "GET /api/model-pricing"
  "GET /api/mcp-instances"
  "GET /api/sso/config"
  "GET /api/analytics/overview"
  "GET /api/clients"
  "GET /api/v1/agents"
  "GET /api/v1/skills"
  "GET /api/v1/personas"
  "GET /api/v1/tone-presets"
  "GET /api/v1/tools"
)
```

For each endpoint, verify HTTP status is 200 or an expected non-error code (401 for unauthenticated is acceptable for protected endpoints).

### Phase 12: Log Review

```bash
# Backend errors in last 200 lines
docker compose logs --tail=200 backend 2>&1 | grep -i -c -E "error|exception|traceback|critical"

# Frontend build errors
docker compose logs --tail=100 frontend 2>&1 | grep -i -c -E "error|failed|unhandled"

# PostgreSQL issues
docker compose logs --tail=50 postgres 2>&1 | grep -i -c -E "error|fatal|panic"
```

### Phase 13: Report and Remediate

Compile all results into the regression test report format (see /fire_regression for format).

**Auto-trigger /fire_remediation** with all test results.

## Output Format

```
=== FULL REGRESSION REPORT ===
Date: <date>
Trigger: Full platform audit

INFRASTRUCTURE: <PASS/FAIL>
AUTHENTICATION: <PASS/FAIL> (<N>/<total> tests passed)
WATCHER: <PASS/FAIL>
AGENTS: <PASS/FAIL> (<N>/<total> tests passed)
PLAYGROUND: <PASS/FAIL> (<N>/<total> tests passed)
FLOWS: <PASS/FAIL> (<N>/<total> tests passed)
HUB: <PASS/FAIL> (<N>/<total> tests passed)
SETTINGS: <PASS/FAIL> (<N>/<total> tests passed)
SYSTEM: <PASS/FAIL> (<N>/<total> tests passed)
API SWEEP: <PASS/FAIL> (<N>/<total> endpoints OK)
LOG REVIEW: <PASS/FAIL> (<N> errors found)

OVERALL: <PASS / FAIL (N issues across M areas)>
===
```
