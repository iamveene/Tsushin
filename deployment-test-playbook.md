# Deployment Test Playbook (Fresh Install)

> Manual QA checklist to validate a fresh Tsushin deployment.
> Run through each section sequentially after a clean install.
> Uses `<tenant_admin_email>` / `<global_admin_email>` placeholders — substitute with the credentials created or revealed during `/setup`.

---

## Prerequisites

| Item | Detail |
|------|--------|
| Tenant admin account | Created in the `/setup` wizard (`<tenant_admin_email>` / `<tenant_admin_password>`) |
| Global admin account | Auto-generated and revealed on the final `/setup` completion screen (`<global_admin_email>` / `<global_admin_password>`) |
| At least one default agent | Seeded automatically by installer |
| Browser | Modern Chromium-based browser |
| VM/server IP | `10.211.55.5` (adjust if different) |
| LLM keys | Gemini, OpenAI, Anthropic for provider coverage; Brave for search coverage |
| Local model runtime | Optional but recommended: Ollama reachable from the backend container |

---

## Audit Profile — Ubuntu VM (`develop` HEAD)

Use this profile when reproducing the 2026-04-07 Ubuntu VM audit:

| Item | Value |
|------|-------|
| Git branch | `develop` |
| Installer mode | Real interactive installer (`python3 install.py`) |
| Backend port | `8081` |
| Frontend port | `3030` |
| Access type | `remote` |
| Public host/IP | `10.211.55.5` |
| SSL mode | HTTP only |
| Setup org name | `Tsushin QA` |
| Setup admin | `test@example.com` / `test123` |
| Default agents | `create_default_agents=true` |
| Evidence folder | `output/playwright/` |

---

## Known Issues & Workarounds

| Bug | Status | Notes |
|-----|--------|-------|
| BUG-201: docker-compose v1 frontend race | **Fixed in current release** — `install.py` now auto-recovers frontend after backend health. If on an older install, workaround: `docker-compose up -d frontend` once backend is healthy. |
| BUG-202: Relative API paths 404 in HTTP-only installs | **Fixed in current release** — `client.ts` now uses absolute `NEXT_PUBLIC_API_URL` for all API calls. |

---

## TC-0: Setup Wizard + Credential Reveal

**Goal:** Confirm a fresh install reaches `/setup`, creates the tenant, and reveals the auto-generated global admin credentials.

### Steps

1. Open `http://<host>:3030/setup`.
2. Complete the wizard with:
   - **Organization:** `Tsushin QA`
   - **Tenant admin email:** `<tenant_admin_email>`
   - **Tenant admin password:** `<tenant_admin_password>`
   - **Create default agents:** enabled
   - **Primary provider:** Gemini
3. Also enter OpenAI and Anthropic keys during setup so the tenant starts with multiple LLM providers available.
4. Finish setup and capture the generated global admin credentials shown on the completion screen.
5. Save a screenshot of the completion state to `output/playwright/`.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | `/setup` loads and submits without error | |
| 2 | Tenant admin account is created successfully | |
| 3 | Completion screen reveals global admin credentials | |
| 4 | Redirect to login or dashboard succeeds after setup | |

---

## TC-1: Infrastructure Health

**Goal:** Confirm all services are up and responding before UI testing.

### Steps

1. From any machine with network access, run:
   ```bash
   curl -s http://<host>:8081/api/health      # expect: {"status": "healthy"}
   curl -s http://<host>:8081/api/readiness   # expect: {"status": "ready"}
   curl -s http://<host>:8081/metrics | head  # expect: Prometheus metrics output
   ```
2. Open `http://<host>:3030` in the browser — the Tsushin login page should load.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | `/api/health` returns `{"status": "healthy"}` (HTTP 200) | |
| 2 | `/api/readiness` returns `{"status": "ready"}` (HTTP 200) | |
| 3 | `/metrics` returns Prometheus-formatted text | |
| 4 | Frontend login page loads at port 3030 | |

---

## TC-2: Auth — Tenant Admin Login

**Goal:** Confirm tenant admin can log in and sees the expected UI.

### Steps

1. Open `http://<host>:3030`.
2. Enter `<tenant_admin_email>` and `<tenant_admin_password>`.
3. Click **Sign In**.
4. Verify:
   - Redirected to the dashboard (no error message).
   - Left sidebar shows: Dashboard, Playground, Agents, Flows, Hub, Settings.
   - No "System" section visible (tenant users should not see it).

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Login succeeds without error | |
| 2 | Dashboard renders with sidebar navigation | |
| 3 | "System" admin section is NOT visible | |

---

## TC-3: Auth — Global Admin Login

**Goal:** Confirm global admin can log in and has access to the System section.

### Steps

1. Log out if currently logged in.
2. Log in with the `<global_admin_email>` / `<global_admin_password>` captured from TC-0.
3. Verify:
   - Sidebar shows a **System** section (or equivalent admin area).
   - Navigate to `/system/tenants` — tenant list renders.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Global admin login succeeds | |
| 2 | System section is visible in sidebar | |
| 3 | `/system/tenants` loads without errors | |

---

## TC-4: Dashboard (Watcher)

**Goal:** Confirm the Dashboard page loads and main sub-tabs render.

### Steps (logged in as tenant admin)

1. Navigate to `/dashboard` (or click **Dashboard** in sidebar).
2. Verify the **Dashboard** tab (overview cards / stats) renders.
3. Click the **Conversations** tab — message history or empty state loads.
4. Click the **Flows** tab — flows view or empty state loads.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Dashboard overview tab renders without errors | |
| 2 | Conversations tab renders | |
| 3 | Flows tab renders | |

---

## TC-5: Agents (Studio)

**Goal:** Confirm agents were seeded and can be viewed/edited.

### Steps (logged in as tenant admin)

1. Navigate to `/agents` (or click **Agents** in sidebar).
2. Verify at least one default agent is listed.
3. Click on an agent to open its detail/configuration page.
4. Verify agent name, model, and configuration fields render without errors.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Agent list page loads | |
| 2 | At least one seeded agent is present | |
| 3 | Agent detail page opens and renders configuration | |

---

## TC-6: Playground — Basic Chat

**Goal:** Confirm the Playground can send a message and receive an AI response (validates LLM connectivity).

### Steps (logged in as tenant admin)

1. Navigate to `/playground`.
2. Select an agent from the sidebar.
3. Start a **new thread**.
4. Type a simple message: `Hello, please respond briefly.`
5. Send the message.
6. Wait up to 30 seconds for a response.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Playground page loads and agent is selectable | |
| 2 | Message sends without a client error | |
| 3 | Agent returns a coherent AI response within 30s | |
| 4 | No "LLM error", "model not found", or API key error in response | |

---

## TC-7: Playground — Memory Inspector

**Goal:** Confirm the Memory Inspector loads and fact CRUD works.

### Steps (logged in as tenant admin)

1. In Playground with an agent selected, open the **Memory** tab in the right inspector panel.
2. Switch to the **Facts** sub-tab.
3. Click **"+ Create New Fact"**, fill in:
   - **Topic:** `personal_info`
   - **Key:** `favorite_color`
   - **Value:** `dark purple`
4. Click **Save**.
5. Verify the fact appears in the list.
6. Hover the fact and delete it — verify it disappears.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Memory Inspector tab opens | |
| 2 | Facts sub-tab renders | |
| 3 | Fact is created and appears in list | |
| 4 | Fact can be deleted | |

---

## TC-8: Flows Page

**Goal:** Confirm the Flows page loads without JavaScript errors.

### Steps (logged in as tenant admin)

1. Navigate to `/flows`.
2. Verify the page renders (flow list or empty state).
3. Open the browser console — no red errors related to Tsushin code.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Flows page loads without crash | |
| 2 | No JavaScript errors in console | |

---

## TC-9: Hub Page

**Goal:** Confirm the Hub / integrations page loads and displays integration cards.

### Steps (logged in as tenant admin)

1. Navigate to `/hub`.
2. Verify integration cards are visible (Google, Asana, etc.).
3. No error toast or blank page.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Hub page loads | |
| 2 | At least one integration card is visible | |

---

## TC-10: Settings Pages

**Goal:** Confirm all Settings sub-pages load without errors.

### Steps (logged in as tenant admin)

Navigate to each settings URL and confirm it renders:

| URL | Expected |
|-----|---------|
| `/settings` | Main settings page |
| `/settings/organization` | Org name, logo settings |
| `/settings/team` | Team members list |
| `/settings/integrations` | Integration toggles |
| `/settings/sentinel` | Security policy settings |
| `/settings/audit-logs` | Audit log entries (or empty state) |
| `/settings/security` | Security config |
| `/settings/roles` | Role management |
| `/settings/api-clients` | API client list |
| `/settings/prompts` | Prompt templates |
| `/settings/ai-configuration` | AI model settings |
| `/settings/model-pricing` | Pricing config |
| `/settings/billing` | Billing info |
| `/settings/filtering` | Content filtering |
| `/settings/system-ai` | System AI config |

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | All 15 settings sub-pages load without a blank screen or crash | |
| 2 | No API 500 errors visible in the UI | |

---

## TC-11: System Admin Pages

**Goal:** Confirm system admin pages are accessible to global admin.

### Steps (logged in as global admin)

Navigate to each URL:

| URL | Expected |
|-----|---------|
| `/system/tenants` | Tenant list |
| `/system/users` | Global user list |
| `/system/plans` | Plan definitions |
| `/system/integrations` | System-level integrations |

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | All 4 system pages load without errors | |
| 2 | At least one tenant is listed on `/system/tenants` | |

---

## TC-12: Browser Automation Skill (CONDITIONAL)

> **SKIP if** no `toolbox` or sandbox container is running on the deployment.

**Goal:** Confirm the Browser Automation skill can navigate a public URL.

### Steps (logged in as tenant admin)

1. In **Studio**, enable **Browser Automation** skill on the test agent.
2. In **Playground**, start a new thread with that agent.
3. Send: `Navigate to https://example.com/ and tell me what you see`
4. Wait for response — agent should report the page title and content.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Agent navigates to example.com successfully | |
| 2 | Agent reports page title/content without provider errors | |

---

## TC-13: Log Review

**Goal:** Confirm no unexpected errors in backend or frontend logs.

### Steps

SSH into the VM and run:

```bash
# Backend error check
docker compose logs backend --tail=200 | grep -iE "ERROR|CRITICAL"

# Frontend error check
docker compose logs frontend --tail=200 | grep -iE "error" | grep -v "sharp"

# Browser console (from TC-6 Playground session)
# Check for red errors in browser DevTools — exclude benign 404s for optional resources
```

Expected: **zero** ERROR or CRITICAL lines in backend logs; no unexpected errors in frontend logs (the `sharp` module warning is known/acceptable).

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Backend logs: zero ERROR/CRITICAL lines | |
| 2 | Frontend logs: zero unexpected errors (sharp warning excluded) | |
| 3 | Browser console: no red Tsushin errors during TC-6 Playground test | |

---

## TC-14: Configure Gemini LLM Provider

**Goal:** Confirm a Gemini provider instance can be created, tested, and assigned to an agent.

### Steps (logged in as tenant admin)

1. Navigate to `/hub` → click the **AI Providers** tab.
2. Click **"+ Add Provider"** → select **Gemini**.
3. Enter:
   - **Instance name:** `Gemini Default`
   - **API key:** *(your Gemini API key)*
4. Click **"Test Connection"** — expect a success message.
5. Toggle **"Set as Default"** → save.
6. Navigate to `/agents` → open the main agent (e.g., **Tsushin**) → **Configuration** tab.
7. Change **Model Provider** to **Gemini** and select a model (e.g., `gemini-2.0-flash`).
8. Save the agent.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Provider instance created without error | |
| 2 | Test Connection returns success | |
| 3 | Agent saved with Gemini as model provider | |

---

## TC-15: Web Search Skill (Brave)

**Goal:** Confirm the Web Search skill returns real search results via Brave API.

### Steps (logged in as tenant admin)

1. Navigate to `/agents` → open the Tsushin agent → **Skills** tab.
2. Enable **Web Search** skill → set provider = **Brave**, enter Brave API key.
3. Save.
4. Navigate to `/playground` → select Tsushin → new thread.
5. Send: `Search for the latest AI news in 2025 and give me 3 highlights`
6. Wait up to 30s for response.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Web Search skill enabled without error | |
| 2 | Agent returns results with real URLs/sources (not hallucinated) | |
| 3 | No "API key invalid" or search provider error in response | |

---

## TC-16: Image Generation in Playground

**Goal:** Confirm the Image skill generates an image from a text prompt.

### Steps (logged in as tenant admin)

1. In the Tsushin agent → **Skills** tab, enable the **Image** skill.
2. Save.
3. In Playground with Tsushin → new thread.
4. Send: `Generate an image of a futuristic city skyline at night`
5. Wait up to 45s.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Image skill enabled without error | |
| 2 | Agent returns an image (inline or URL) in the response | |
| 3 | No generation error message | |

---

## TC-17: Create ACME Sales Agent + Product Knowledge Base

**Goal:** Confirm a custom agent can be created with a working knowledge base.

### Steps (logged in as tenant admin)

1. Navigate to `/agents` → click **"+ New Agent"**.
2. Configure:
   - **Name:** `ACME Sales`
   - **Model Provider:** Gemini
   - **System Prompt:** `You are the ACME Corp sales assistant. Answer questions about products using only information from your knowledge base. Always include prices and SKUs.`
3. Save the agent.
4. Open the **Knowledge Base** tab for the ACME Sales agent.
5. Upload `acme_products.csv` with this content:
   ```
   Product,Description,Price,SKU
   Laptop Pro X,High-performance 15" laptop with Intel Core i9,1299.00,LPX-001
   UltraMonitor 27",27-inch 4K IPS display with 144Hz refresh rate,349.00,UM27-002
   MechKeyboard,Tenkeyless mechanical keyboard with Cherry MX switches,89.00,MK-003
   ErgoMouse,Ergonomic wireless mouse with 6 programmable buttons,55.00,EM-004
   ProHeadset,Noise-cancelling USB headset with microphone,179.00,PH-005
   ```
6. Wait for processing status → **"completed"**.
7. In Playground with ACME Sales → new thread.
8. Send: `What is the price of the Laptop Pro X?`
9. Expect: price ($1,299) and SKU (LPX-001) in response.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | ACME Sales agent created successfully | |
| 2 | Product catalog CSV uploaded and processed (status = completed) | |
| 3 | Agent returns correct price from KB ($1,299 for Laptop Pro X) | |
| 4 | Agent includes SKU in response | |

---

## TC-18: Configure Agent-to-Agent Communication

**Goal:** Confirm communication permissions can be set between agents.

### Steps (logged in as tenant admin)

1. Navigate to `/agents/communication` (or Agents → Communication tab).
2. Click **"+ Add Permission"**.
3. Configure:
   - **Source Agent:** Tsushin
   - **Target Agent:** ACME Sales
   - **Max Depth:** 2
   - **Rate Limit:** 10 RPM
4. Enable the permission → save.
5. Navigate to Tsushin agent → Skills → enable **Agent Communication** skill (if not already enabled).
6. Save.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Communication permission created without error | |
| 2 | Permission appears in the permissions list | |
| 3 | Agent Communication skill enabled on Tsushin | |

---

## TC-19: E2E Product Price Query via Agent Delegation

**Goal:** Confirm Tsushin can delegate a query to ACME Sales and relay the response to the user.

### Steps (logged in as tenant admin)

1. In Playground → select **Tsushin** → new thread.
2. Send: `Can you check with the ACME Sales agent what the price of the ErgoMouse is?`
3. Wait up to 60s (inter-agent communication + KB lookup + LLM response).
4. After response, navigate to `/agents/communication` → **Sessions** tab.
5. Verify a new session entry exists with:
   - Source: Tsushin
   - Target: ACME Sales
   - Status: completed
   - Depth: 1

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Tsushin returns the correct ErgoMouse price ($55) to the user | |
| 2 | Communication session exists in the Sessions view | |
| 3 | Session status = completed, depth = 1 | |
| 4 | No timeout or "delegation failed" error | |

---

## TC-20: Onboarding Tour + Tenant vs Global RBAC

**Goal:** Confirm first-login onboarding appears for the tenant admin and that tenant/global scopes remain separated.

### Steps

1. Log in as the tenant admin immediately after TC-0.
2. Verify the onboarding tour or Getting Started checklist appears.
3. Confirm tenant pages such as `/dashboard`, `/hub`, `/playground`, and `/settings` are accessible.
4. Attempt to open `/system/tenants` as the tenant admin — expect denial or redirect.
5. Log in as the global admin and confirm `/system/*` pages render while tenant pages still remain accessible as needed.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | First-login onboarding/checklist appears for tenant admin | |
| 2 | Tenant admin can use tenant-scoped pages | |
| 3 | Tenant admin cannot access `/system/*` pages | |
| 4 | Global admin can access `/system/*` pages | |

---

## TC-21: Provider Matrix + Local Ollama

**Goal:** Confirm hosted providers and a local Ollama instance can all be configured and tested on a fresh VM install.

### Steps

1. In `/hub` → **AI Providers**, verify provider instances for Gemini, OpenAI, and Anthropic can be created, tested, and assigned as defaults where needed.
2. Install Ollama on the VM and pull at least one model such as `llama3.2`.
3. In `/hub` → **Local Services**, configure Ollama with `http://host.docker.internal:11434`.
4. If Docker-on-Linux name resolution fails, retry with the bridge fallback (for example `http://172.18.0.1:11434`).
5. Verify models are discovered and an Ollama provider instance can be tested successfully.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Gemini, OpenAI, and Anthropic provider instances save and test successfully | |
| 2 | Ollama health check succeeds from the backend container | |
| 3 | At least one Ollama model is discovered and selectable | |
| 4 | A tenant default provider can be changed without breaking existing agents | |

---

## TC-22: Playground Expanded Coverage

**Goal:** Validate realistic end-user Playground paths beyond basic chat.

### Steps

1. Run a normal text chat with a seeded agent.
2. Generate one image from a text prompt.
3. Upload one document and one image to a thread and confirm the agent can reference them.
4. Open a direct agent conversation and a direct project conversation.
5. Use the command palette or slash commands to run `/status`, `/memory status`, and one `/inject` action.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Text chat succeeds | |
| 2 | Image generation succeeds | |
| 3 | Uploaded file/image context is reflected in the response | |
| 4 | Direct agent and direct project chat both work | |
| 5 | Slash-command execution updates the thread as expected | |

---

## TC-23: Memory Isolation Matrix

**Goal:** Verify `isolated`, `shared`, and `channel_isolated` memory modes behave correctly across threads.

### Steps

1. Create or reuse one disposable agent for each mode: `isolated`, `shared`, and `channel_isolated`.
2. In thread A, store a unique secret phrase for each agent.
3. Open thread B and ask the same agent to recall the phrase.
4. For `shared`, expect recall across threads.
5. For `isolated`, expect no recall across threads.
6. For `channel_isolated`, validate the intended per-channel behavior in Playground and confirm the Memory Inspector / shared-knowledge views match observed chat behavior.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Shared mode recalls facts across threads | |
| 2 | Isolated mode does not leak across threads | |
| 3 | Channel-isolated mode behaves consistently with the configured scope | |
| 4 | Inspector views match runtime chat behavior | |

---

## TC-24: Vector Store Provisioning + Long-Term Recall

**Goal:** Confirm auto-provisioned vector stores work and can be selected as tenant defaults.

### Steps

1. In `/hub` or `/settings/vector-stores`, create one auto-provisioned **Qdrant** instance.
2. Set Qdrant as the tenant default vector store.
3. Keep at least one agent on the built-in ChromaDB path for fallback comparison.
4. Attach Qdrant-backed long-term memory to a test agent.
5. Store a distinctive long-term fact, start a fresh thread, and confirm semantic recall still works.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Qdrant instance provisions and tests healthy | |
| 2 | Tenant default vector store saves successfully | |
| 3 | Qdrant-backed agent recalls long-term information in a later thread | |
| 4 | ChromaDB-backed fallback agent still works | |

---

## TC-25: Sentinel + MemGuard Protections

**Goal:** Validate that prompt injection, memory poisoning, and vector-store poisoning checks are visible and enforced according to policy.

### Steps

1. Confirm Sentinel is enabled in `/settings/sentinel`.
2. Run one benign control prompt.
3. Run one prompt-injection test string.
4. Run one memory-poisoning attempt.
5. Run one vector-retrieval / vector-poisoning-adjacent scenario.
6. Review Watcher Security or Sentinel logs for detections, scores, and actions taken.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Benign prompt is allowed | |
| 2 | Malicious test prompts are detected and logged | |
| 3 | Persistence of poisoned content is blocked or clearly prevented by policy | |
| 4 | Security events are visible in the UI or API logs | |

---

## TC-26: MCP Servers + Custom Skills

**Goal:** Confirm stdio MCP registration, skill creation, and skill invocation paths work end to end.

### Steps

1. Register a stdio MCP server using `uvx mcp-server-fetch`.
2. Verify the server reaches a healthy or discoverable state in the Hub.
3. Create three custom skills:
   - one instruction skill
   - one script skill
   - one MCP-backed skill
4. Run any Sentinel scan available on save.
5. Assign the skills to a test agent and invoke them from Playground.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | MCP server registration succeeds | |
| 2 | Instruction skill can be created, assigned, and invoked | |
| 3 | Script skill can be created, assigned, and invoked | |
| 4 | MCP-backed skill can be discovered and invoked | |

---

## TC-27: Shell Command Center + Sandbox + Slash Commands

**Goal:** Confirm runtime shell integrations, sandboxed tools, and slash-command routing work on a fresh VM install.

### Steps

1. Register a beacon from the VM in **Shell Command Center**.
2. Execute one approved shell command through the shell integration.
3. Execute one sandboxed tool against a safe public target such as `example.com` or `scanme.nmap.org`.
4. In Playground, run `/shell`, `/tools`, `/status`, `/memory status`, and `/inject`.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Beacon registers and checks in successfully | |
| 2 | Approved shell command completes and returns output | |
| 3 | Sandboxed tool executes successfully | |
| 4 | Slash-command routing works for all covered commands | |

---

## TC-28: Public API v1 + Generated Client

**Goal:** Validate API v1 auth modes, sync/async chat, thread access, and one generated client call against the live VM.

### Steps

1. Create API client credentials in `/settings/api-clients`.
2. Use direct API-key auth to call:
   - `GET /api/v1/agents`
   - `GET /api/v1/skills`
   - `GET /api/v1/tools`
3. Use OAuth client-credentials auth to request a bearer token and call `GET /api/v1/flows`.
4. Send one sync chat request and one async chat request, then poll the queue until completion.
5. Fetch the corresponding thread and message history.
6. Download `/openapi.json`, generate a client from the local file, and perform at least one live API call with the generated SDK.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Direct API-key auth succeeds | |
| 2 | OAuth client-credentials auth succeeds | |
| 3 | Sync and async chat both complete successfully | |
| 4 | Thread and message retrieval work for completed chats | |
| 5 | Generated client completes at least one live call | |

---

## TC-29: Flows — Programmatic + Agentic Nodes

**Goal:** Confirm both API-created and UI-executed flows work for the current release scope.

### Steps

1. Create one simple programmatic flow via the API or UI.
2. Create one flow that includes an agentic node or skill/tool-based node.
3. Execute both flows from the UI when possible.
4. Review recent runs on `/flows` and confirm completed vs failed states, logs, and outputs.
5. If using search or notification steps, verify the configured provider/recipient resolution works in the tenant scope.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Programmatic flow can be created and executed | |
| 2 | Agentic flow can be created and executed | |
| 3 | Run history reflects the true result state | |
| 4 | Step outputs or errors are inspectable for debugging | |

---

## TC-30: Projects + Knowledge Base Stability

**Goal:** Validate project-scoped chat, project knowledge uploads, and direct project-to-agent behavior.

### Steps

1. Create a project bound to a specific agent.
2. Start a direct project conversation and confirm the agent responds using that project context.
3. Upload a small project knowledge file.
4. Confirm the upload completes without restarting the backend.
5. Ask the project a question that should use the uploaded knowledge.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Project creation succeeds | |
| 2 | Direct project chat routes to the intended agent | |
| 3 | Project knowledge upload completes successfully | |
| 4 | Backend remains healthy after upload | |
| 5 | Project chat can use uploaded knowledge | |

---

## TC-31: A2A Monitoring + Graph View

**Goal:** Confirm agent-to-agent traffic is visible in both the dedicated communications view and the graph visualization.

### Steps

1. Trigger an A2A conversation such as Tsushin delegating to ACME Sales.
2. Open `/agents/communication` and confirm a completed session is listed with source, target, depth, and status.
3. Open Graph View and verify the interaction appears visually.
4. Save screenshots for both views to `output/playwright/`.

### Pass Criteria

| # | Check | Pass? |
|---|-------|-------|
| 1 | Communication session appears in `/agents/communication` | |
| 2 | Session status and depth are correct | |
| 3 | Graph View reflects the A2A interaction | |
| 4 | Evidence screenshots are captured | |
