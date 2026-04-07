# Changelog

All notable changes to the Tsushin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-04-07

### Bug Fixes

#### Release Re-Validation Fixes (BUG-345, BUG-346, BUG-347) — 2026-04-07

- **BUG-345 — API v1 agent creation bypassed tenant `max_agents` cap (HIGH):** The `POST /api/v1/agents` endpoint did not enforce the tenant agent cap, allowing unlimited agent creation through the public API while the standard route correctly returned 409. Added the same `Tenant.max_agents` enforcement from the standard route to the v1 route before contact/agent creation.
- **BUG-346 — Create Agent modal defaulted to Anthropic instead of tenant's default provider (MEDIUM):** The `getSmartDefaults()` function used `providerInstances[0]` (first in list) instead of the instance marked `is_default=true`. Updated to find the default provider instance and use its `available_models[0]` for the model name, with a useEffect to apply defaults when instances load.
- **BUG-347 — Hub API v1 tooling surface non-functional for Gmail/Calendar/Flights (HIGH):** Added `INTEGRATION_CAPABILITIES` matrix to define per-type support for health_check, tools, and tool_execution. Integration summaries and provider listings now include a `capabilities` dict. Health, tool listing, and execution endpoints check capabilities upfront with clear error messages. Added `google_flights` to the providers list. The service factory now handles `google_flights` with an informative error instead of a generic "unsupported type".

#### Post-Sprint Regression Fixes — 2026-04-07

- **BUG-334 follow-up — `skipTour` used `window.confirm()` blocking browser events:** The "Skip Tour" button called `window.confirm()` which blocks all browser events, preventing programmatic dismissal and breaking automated tests. Replaced with direct localStorage persist matching the same pattern used by `dismissTour()` and the Escape key handler. Tour is now immediately dismissed without a confirmation dialog.
- **Perfection audit fixes:** (1) `client.ts` 409 error guard changed from message-string comparison (`!== 'Unexpected end of JSON input'`) to `!(jsonErr instanceof SyntaxError)` — prevents HTML error bodies from surfacing raw SyntaxError text to users; (2) `agent_switcher_skill.py` `_find_agent_by_name()` and `_get_available_agents()` now apply `tenant_id` filter to prevent cross-tenant agent resolution in multi-tenant deployments; (3) `routes_flows.py` `create_flow_v2` endpoint now re-raises `HTTPException` before the generic `except Exception` catch (matching `create_flow` pattern); (4) `GoogleCredentials` TypeScript interface in `settings/integrations/page.tsx` and `settings/security/page.tsx` now includes `configured?: boolean` for type safety.

#### Playground & Flows Bug Fixes (BUG-331, BUG-335, BUG-336, BUG-344) — 2026-04-07

- **BUG-344 — `/api/health` reported stale version v0.5.0 while frontend showed v0.6.0 (LOW):** Changed `SERVICE_VERSION = "0.5.0"` to `SERVICE_VERSION = "0.6.0"` in `backend/settings.py`. The health and readiness endpoints now correctly return `"version": "0.6.0"`, matching the frontend footer.

- **BUG-335 — Playground created a new empty thread on every page load (LOW):** `initializeThreads()` in `frontend/app/playground/page.tsx` only checked if the most-recent thread was empty. If the most-recent thread had messages (normal after any use), a new thread was created on every subsequent page load, accumulating orphan threads. Fixed by searching ALL threads for any with `message_count === 0` (or undefined). A new thread is now only created when every existing thread already has messages. Verified: navigating to Playground 3 times kept the thread count stable.

- **BUG-336 — Flow keyword triggers did not intercept messages in the Playground channel (MEDIUM):** Flows with `execution_method='keyword'` only fired on external channel messages (WhatsApp, Telegram); Playground messages were routed directly to the AI instead. Implemented full end-to-end keyword-trigger support: (1) Added `KEYWORD = "keyword"` to `ExecutionMethod` enum in `schemas.py`; (2) Added `trigger_keywords` JSON column to `FlowDefinition` model with Alembic migration `0028`; (3) Updated `routes_flows.py` to accept/store/return `trigger_keywords` in all create, patch, and response paths; (4) Added `_check_keyword_flow_triggers()` method in `PlaygroundService` — queries active keyword flows for the tenant, matches message text against configured keywords (slash-command prefix match or substring match), and fires matching flows via `FlowEngine.run_flow()`; (5) Injected keyword-trigger check at "STEP 2.5" in both `send_message()` (sync) and `process_message_streaming()` (streaming) paths, returning/yielding a flow acknowledgement before any AI processing; (6) Added keyword UI in Flows page — list badge with hash icon, and keyword textarea in create/edit modals.

- **BUG-331 — Ollama unreachable from Docker backend (binds to 127.0.0.1 by default) (MEDIUM):** Users connecting Ollama to Tsushin got "Cannot connect to Ollama" because the Ollama service binds to `127.0.0.1:11434` by default, which is unreachable from the Docker container. Added a persistent "Docker Networking Note" guidance block in `frontend/app/hub/page.tsx` in the Ollama section, showing the correct Docker gateway URL (`http://172.18.0.1:11434`) and the `OLLAMA_HOST=0.0.0.0:11434` systemd override command. Also added an "Local Ollama (optional)" section to the installer success output in `install.py` with the same step-by-step instructions.

#### Onboarding UX Overhaul — Fragmented Experiences Unified (BUG-318, 319, 320, 321, 322, 323, 325, 334) — 2026-04-07

Eight overlapping onboarding UX bugs resolved in a coordinated fix across `OnboardingContext.tsx`, `OnboardingWizard.tsx`, `WhatsAppWizardContext.tsx`, `GettingStartedChecklist.tsx`, and `LayoutContent.tsx`:

- **BUG-318 — Three sequential onboarding experiences on fresh install (MEDIUM):** Removed the `tsushin:onboarding-complete` event dispatch from `completeTour()` and the auto-launch listener from `WhatsAppWizardContext`. The WhatsApp wizard now only opens when explicitly triggered: via the Getting Started Checklist "Connect a Channel" button (`forceOpenWizard`) or tour step 5 action button (`openWizard`).

- **BUG-319 — Tour step 9 duplicated Getting Started Checklist (LOW):** Removed tour step 9 ("Setup Checklist") entirely. `TOTAL_STEPS` reduced from 9 to 8. New step 8 ("You're All Set!") is a brief completion message pointing users to the Getting Started Checklist on the dashboard. Tour now shows "Step 1 of 8".

- **BUG-320 — Getting Started Checklist visible beneath tour modal (LOW):** `GettingStartedChecklist.tsx` now imports `useOnboarding` and returns `null` immediately when `onboardingState.isActive` is true. Checklist is completely hidden while the tour is running.

- **BUG-321 — Tour step 5 and WhatsApp Wizard covered the same task (MEDIUM):** Tour step 5 action button now calls `openChannelsWizard()` which launches the WhatsApp Setup Wizard directly. When the wizard closes, `tsushin:whatsapp-wizard-closed` event fires and the tour auto-advances to step 6 (Flows).

- **BUG-322 — "Connect a Channel" link couldn't relaunch dismissed wizard (LOW):** Added `forceOpenWizard()` to `WhatsAppWizardContext` that clears `tsushin_whatsapp_wizard_dismissed` before opening. Getting Started Checklist "Connect a Channel" item is now a button calling `forceOpenWizard()` instead of a Link to `/hub?tab=communication`. Hub page also updated to use `forceOpenWizard`.

- **BUG-323 — Tour steps 4 and 5 both navigated to /hub with no context (LOW):** Step 5 now launches the WhatsApp wizard directly via `openChannelsWizard()`. This provides clear channel-specific UX instead of re-showing the generic Hub page.

- **BUG-325 — Tour auto-started on top of open User Guide panel (MEDIUM):** `OnboardingContext` tracks `isUserGuideOpen` via event listeners for `tsushin:open-user-guide` / `tsushin:close-user-guide`. Auto-start skips if User Guide is open (using ref to avoid stale closure race). `LayoutContent.tsx` dispatches `tsushin:close-user-guide` when the panel closes. Tour step 1 "Open User Guide" button is disabled with updated label when the guide is already open.

- **BUG-334 — Tour overlay reappeared on every page navigation (MEDIUM):** Added dedicated `dismissTour()` function that calls `localStorage.setItem('tsushin_onboarding_completed', 'true')` SYNCHRONOUSLY before any React state update. Modal's `onClose` prop and Escape key handler both call `dismissTour()`. A `tourDismissedRef` prevents deferred auto-start from restarting the tour after dismissal. Verified: programmatic Escape key immediately sets localStorage; navigation to `/agents` does not reshow the tour.

#### Settings & Admin Navigation UX (BUG-326, BUG-327, BUG-330) — 2026-04-07

- **BUG-326 — `/settings/filtering` orphaned from Settings hub (MEDIUM):** Added a "Message Filtering" card to the advanced settings section of `frontend/app/settings/page.tsx`. The card includes a filter funnel icon, links to `/settings/filtering`, and requires `org.settings.write` permission. The page (group filters, DM allowlists, keywords, auto-response rules) was previously only discoverable by direct URL.

- **BUG-327 — Global-admin landing page was a placeholder (MEDIUM):** Replaced the placeholder content in `frontend/app/system/integrations/page.tsx` with a proper "System Administration" overview dashboard featuring four navigation cards: Tenant Management, User Management, Plans & Limits, and Platform Integrations. Removed all "This page will contain" placeholder text. Cards use consistent glass-card styling with purple theme.

- **BUG-330 — No admin UI for `max_agents` / tenant plan limits (LOW):** Added an "Edit" modal to `frontend/app/system/tenants/page.tsx`. The modal exposes editable fields for `max_agents`, `max_users`, `max_monthly_requests`, `plan`, and `status`, with current usage stats shown inline. The "View" button in the tenant table is replaced with "Edit". Uses existing backend `PUT /api/tenants/{id}` endpoint which already supports global-admin updates to all plan limit fields.

#### Skills, Memory & Sentinel Bug Fixes (BUG-328, BUG-329, BUG-332, BUG-333, BUG-341) — 2026-04-07

- **BUG-341 — Web search `serpapi` provider key rejected at runtime (MEDIUM):** The skill registry registers SerpAPI under the key `"google"`, but users who configured the skill with `"serpapi"` got a silent failure. Added `PROVIDER_ALIASES = {"serpapi": "google"}` normalization at the start of both `process()` and `execute_tool()` in `search_skill.py` so both provider names work identically at runtime.

- **BUG-333 — Web search skill silently fails with no user guidance when unconfigured (LOW):** When `web_search` skill was enabled but no search API key was configured, the LLM fabricated a misleading "I can't directly search" response. Added three detection points in `search_skill.py` (both `process()` and `execute_tool()`): no available providers, provider not found, or API key not configured — all now return: "Web search is not configured for this agent. Please set up a search provider in the Hub (Settings > Hub > Web Search) and link it to this agent's skill integrations."

- **BUG-329 — Cross-thread memory recall fails in Playground — new thread sees empty memory (MEDIUM):** Each playground thread used a thread-specific sender key (`playground_u{uid}_a{aid}_t{tid}`), so new threads started with empty memory and couldn't recall facts from previous threads. Changed `playground_service.py` to use a stable per-user-per-agent sender key (`playground_u{user_id}_a{agent_id}`) for all threads. Verified: told agent "my favorite number is 42" in thread 26, then started thread 27 and confirmed agent recalled "Yes, I remember! Your favorite number is 42."

- **BUG-328 — Sentinel falsely flags "remember this" as memory poisoning (MEDIUM):** Benign user preference requests ("please remember I prefer dark mode") triggered `memory_poisoning` detection, flooding logs with false-positive warnings. Rewrote all three aggressiveness-level `memory_poisoning` prompts in `sentinel_detections.py` to explicitly distinguish adversarial attacks (credential injection, AI identity override, jailbreak persistence, security bypass) from legitimate user preference storage. Updated unified classification prompts at all levels. Changed detect-only mode threat log from `WARNING` to `DEBUG` in `agent_service.py` to reduce noise.

- **BUG-332 — `CombinedKnowledgeService NOT initialized` WARN fires on every message (LOW):** The `[KB FIX] ❌ CombinedKnowledgeService NOT initialized` log was emitted at `WARN` level on every single agent message for agents without a linked project (the default). Changed `agent_service.py` to log at `DEBUG` when `project_id=None` (expected case) and only log at `WARN` when `project_id` is set but initialization fails.

#### A2A Playground Agent Switching & Flow Type Assignment (BUG-338, BUG-342) — 2026-04-07

- **BUG-338 — A2A agent switching fails in Playground with contact profile error (HIGH):** `AgentSwitcherSkill` required a Contact DB record to complete agent switching but Playground users have no such record (their sender is `playground_user_{id}`). Added `_is_playground_context(message)` helper that detects playground sessions via sender prefix or channel field. Both `process()` and `execute_tool()` now bypass the contact-required check for playground sessions and persist the switch via `UserAgentSession` using the sender_key directly (same approach as slash command service). `ContactAgentMapping` is only updated when a real Contact exists. Verified: `execute_tool()` returns `success=True, "Successfully switched to agent Kokoro"` for playground users.

- **BUG-342 — `POST /api/flows/` ignores `flow_type` parameter (MEDIUM):** The internal `POST /api/flows/` endpoint used `FlowDefinitionCreate` which lacked `flow_type` and `execution_method` fields, causing both to be hardcoded as `"workflow"` and `"immediate"`. Added `flow_type` and `execution_method` optional fields to `FlowDefinitionCreate`. Added `VALID_FLOW_TYPES` and `VALID_EXECUTION_METHODS` constant sets with input validation that returns HTTP 422 for unknown values. Re-raised `HTTPException` before the generic `except Exception` catch so validation errors are no longer silently swallowed as 500s. Verified: `POST /api/flows/` with `"flow_type": "notification"` now returns `"flow_type": "notification"`; unknown types return `422 {"detail": "Invalid flow_type ..."}`.

- **BUG-339 — Create Agent UI form hangs on 409 plan-limit error (HIGH):** When the Create Agent modal received a 409 "Agent limit reached" response, the button remained stuck in "Creating..." indefinitely with no error shown. Added `createError` state to the form — errors are now displayed inline inside the modal. Updated `client.ts` to extract the specific `detail` string from 409 JSON responses before falling back to the generic conflict message, giving users a meaningful error like "Agent limit reached. Your plan allows a maximum of X agents."

- **BUG-340 — Seeded agents (6) exceed free-plan default limit (5) on fresh install (HIGH):** Fresh-install tenants were created with `max_agents=5` but the seed script creates 6 default agents, immediately blocking the user from creating their first custom agent. Increased `max_agents` default to 10 in `models_rbac.py`, `auth_service.py`, and `routes_tenants.py`. Also corrected `max_users` (1→5) and `max_monthly_requests` (1000→10000) model defaults to match realistic free-plan values.

#### Direct Port HTTP Redirect & Hub Fresh-Install 404s (BUG-324, BUG-343) — 2026-04-07

- **BUG-324 — HTTP direct port redirects to HTTPS (HIGH):** Added Next.js middleware (`frontend/middleware.ts`) that issues a 301 redirect from any HTTP direct-port access (`http://<host>:3030`) to `https://localhost`. When `NEXT_PUBLIC_API_URL=https://localhost`, visiting the app over HTTP caused CORS failures and mixed-content blocks because the browser page (HTTP) was calling an API on a different HTTPS origin. The middleware skips the redirect for Docker internal health checks (`127.0.0.1` host) so the container health check remains green. All other HTTP-to-direct-port requests are redirected to the canonical HTTPS URL.
- **BUG-343 — Hub 404 console errors on fresh install (MEDIUM):** Two-part fix. (1) Slack/Discord 404s (`GET /api/integrations/slack/`, `GET /api/integrations/discord/`) were already resolved in commit `2ad1c1f` by updating route paths to match the Phase 23 backend structure. (2) Google credentials 404 on fresh install fixed by changing `GET /api/hub/google/credentials` to return `200 {"configured": false}` instead of HTTP 404 when no Google OAuth credentials are configured for the tenant. The `GoogleCredentialsResponse` Pydantic model now includes a `configured` boolean field. All three frontend consumers (`hub/page.tsx`, `settings/integrations/page.tsx`, `settings/security/page.tsx`) updated to check `data.configured === false` and treat it as null (unconfigured). Verified: Hub page loads with 0 console errors and all integration API calls return 200.

#### Onboarding Tour Navigation Takeover (BUG-337) — 2026-04-07

- **BUG-337 — Onboarding tour redirects Watcher/Flows/Settings on fresh install (CRITICAL):** The onboarding `navigateToStep()` function in `OnboardingContext.tsx` called `router.push()` automatically whenever the user clicked Next/Previous in the wizard, forcibly navigating away from pages the user had intentionally opened. This made `/` (Watcher/Dashboard), `/flows`, and `/settings/integrations` inaccessible on fresh installs where the tour was active. Removed the entire `navigateToStep()` function and all `router.push()` calls from `nextStep()`, `previousStep()`, and `goToStep()`. Wizard step advancement now only increments the step counter. Action buttons within individual steps (e.g., "Set Up Channels in Hub") remain as opt-in navigation, giving users full control. Also removed the now-unused `useRouter` import.

### Bug Fixes (BUG-309 through BUG-317 — Ship-Gate + Security Audit Sprint)

- **BUG-309:** Added RBAC permission checks (`hub.read`/`hub.write`) to all 14 Google integration routes, preventing privilege escalation from member to integration admin.
- **BUG-310:** Secured legacy `/ws` WebSocket endpoint with JWT authentication and tenant-scoped connection tracking. Replaced global `broadcast()` with `broadcast_to_tenant()` to eliminate cross-tenant information disclosure.
- **BUG-311:** Discord interaction signature verification now uses per-integration `public_key` stored in the database instead of a global environment variable, ensuring multi-tenant isolation.
- **BUG-312:** Slack HTTP Events `url_verification` handshake now works correctly — `app_id` stored per-integration for reliable resolution, `signing_secret` required when `mode="http"`. New CRUD API at `/api/slack/integrations/`.
- **BUG-313:** Discord inbound interactions are now fully configurable via the integration API — `public_key` is a required field on create. New CRUD API at `/api/discord/integrations/` and inbound webhook at `/api/channels/discord/{id}/interactions`.
- **BUG-314:** Tenant `max_agents` plan limits are now enforced on agent creation in both standard and v2 API routes, returning HTTP 409 when the limit is reached.
- **BUG-315:** Fixed Playwright browser path in Docker container — set `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers` so the non-root `tsushin` user can find Chromium at runtime.
- **BUG-316:** Normalized Google Flights date parameters with 3-layer defense (dataclass stripping, provider regex+validation, format fallback parsing) to prevent SerpApi 400 errors from quoted date strings.
- **BUG-317:** Fixed skill test endpoint to apply persisted config, database session, and agent context to skill instances before calling `can_handle()`, eliminating false-negatives for config-driven skills like `web_search`.

### Security

- **Next.js 16 upgrade (PR [#5](https://github.com/iamveene/Tsushin/pull/5) revival, originally by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Upgraded frontend from Next.js 14.2.33 to 16.2.2, React 18.2.0 to 19.2.0, ESLint 8 to 9 (flat config). Resolves CVE-2025-29927, CVE-2024-34351, CVE-2024-46982, CVE-2024-51479. Applied fixes for Google Fonts Docker build failure (--webpack flag), removed unnecessary monorepo boilerplate from next.config.mjs, migrated ESLint to flat config (eslint.config.mjs), updated TypeScript JSX mode to react-jsx. Removed stale pnpm-lock.yaml and added it to .dockerignore.

### Community Contributions

- **WhatsApp contact name enrichment (PR [#6](https://github.com/iamveene/Tsushin/pull/6) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Improved WhatsApp DM contact name resolution across all layers. The Go MCP bridge now uses a richer fallback chain (FullName → PushName → FirstName → BusinessName → message PushName → sender) and detects raw numeric identifiers to force re-resolution. The API reader reuses human-readable `chat_name` as `sender_name` for DMs when contact mappings miss. The messages API endpoint enriches responses via `CachedContactService`, replacing raw @lid identifiers with friendly names in both `sender_name` and `chat_name` columns.
- **WhatsApp LID contact agent routing (PR [#8](https://github.com/iamveene/Tsushin/pull/8) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Fixed DM routing for contacts using WhatsApp LID identifiers. Extracted contact resolution into `_resolve_direct_message_contact()` with a richer fallback chain: `CachedContactService` → chat_id metadata → fuzzy name matching → WhatsApp auto-discovery. The auto-discovery service now records newly observed LID aliases as `ContactChannelMapping` entries instead of discarding them, ensuring contact-agent mappings are preserved across identifier changes.
- **Sanitize leaked tool-call markup (PR [#9](https://github.com/iamveene/Tsushin/pull/9) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Local/Ollama models sometimes emit pseudo `[TOOL_CALL]` markup instead of plain replies. Added `_sanitize_unexecuted_tool_output()` to `AgentService` that extracts the user-facing message from `action: respond` blocks and strips unresolved fenced tool blocks before delivery.
- **AgentSwitcher contact resolution for WhatsApp aliases (PR [#10](https://github.com/iamveene/Tsushin/pull/10) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** `AgentSwitcherSkill._identify_sender()` now uses `ContactService` with `sender_key` and `chat_name` parameters for consistent contact resolution. Falls back through channel mappings, fuzzy name matching, and WhatsApp auto-discovery — matching the main router's resolution strategy.

### Improvements

#### Setup Wizard & Onboarding Tour Enhancements (2026-04-06)

- **System AI auto-assigned during initial setup:** The setup wizard now creates a ProviderInstance for the primary AI provider and automatically assigns it as the System AI. Previously, System AI had to be manually configured in the Hub after setup, leaving system operations (intent classification, skill routing, flow processing) without a provider until manually configured.
- **Onboarding tour updated with mandatory configuration guidance:** Revised all 9 tour steps to cover mandatory setup requirements. The tour now points users to the User Guide (accessible via ? button), explains that System AI is auto-configured, highlights communication channel setup as a required step with actionable buttons, and ends with a setup checklist summarizing completed and pending configuration items.
- **Communication Channels step made actionable:** The tour's Channels step now navigates to the Hub and includes a "Set Up Channels in Hub" action button, making it clear that connecting WhatsApp/Telegram is required for agents to communicate outside the Playground.

#### Dynamic Ollama Model Discovery (2026-04-06)

- **Ollama models now fetched dynamically from running instance:** Replaced all hardcoded Ollama model lists across 6 files (3 backend, 3 frontend) with dynamic discovery from the configured Ollama instance via `/api/tags`. Agent creation, agent configuration manager, playground config panel, Sentinel LLM providers, token tracker, and model pricing routes now all reflect the actual models available on the user's Ollama instance. Hub already showed dynamic models — now the agent creation and configuration selectors are consistent with it. Ollama models are automatically treated as free ($0) in pricing/cost tracking without needing to be individually listed.
- **SSRF validation now sends vendor context for Ollama URL validation:** The provider instance creation modal was blocking `host.docker.internal` URLs for Ollama because the frontend URL validation didn't pass the `vendor` parameter to the backend. Fixed `validateProviderUrl()` to pass the current vendor so Ollama/custom providers correctly allow Docker internal hostnames.
- **Ollama "Manage Instance" button on Hub Local Services card:** Added a "Manage Instance" link to the Ollama card in the Hub's Local Services section, allowing users to open the full provider instance edit modal to modify URL, API key, models, and other settings directly from the card.

### Bug fixes

#### Provider Instance Test Connection — Deprecated Model Fix (2026-04-06)

- **BUG-308 — Test connection uses deprecated/wrong model (HIGH):** The "Test Connection" button on provider instances ignored the user-selected model and fell back to hardcoded model IDs. For Anthropic, the fallback was `claude-3-5-haiku-20241022` (deprecated), causing a 404 error. Fixed by: passing the user's selected model from the frontend to both test connection endpoints (raw and saved), adding model priority chain (request > saved > fallback), and updating all hardcoded fallbacks to current models. Also updated all model selector lists, pricing tables, and discovery fallbacks across the platform to include Claude 4.6 series (Opus, Sonnet, Haiku) and removed deprecated Claude 3 Haiku / 3.5 Haiku entries.

#### Provider Instance Validation (2026-04-06)

- **BUG-305 — Provider instance model required validation:** Provider instances could be created without any models, making them unusable. Added frontend validation (disabled save button, red required asterisk, auto-add of typed model text on save) and backend validation (HTTP 400 if `available_models` is empty).

#### Data Loss Prevention & Custom Skills UX (2026-04-06)

- **BUG-302 — Database volume protection (CRITICAL):** PostgreSQL named volume `tsushin-postgres-data` was destroyed and recreated, wiping all tenant-created custom skills and MCP server configurations. Added explicit "Database Volume Protection" section to `CLAUDE.md` listing forbidden commands (`docker-compose down -v`, `docker volume rm`, `docker system prune --volumes`) with safe alternatives. Created `backend/scripts/backup_db.sh` for periodic pg_dump backups with automatic retention of the last 10 backups.
- **BUG-303 — Agent custom skills inline management:** The "Manage Custom Skills" button in the agent config Custom Skills tab redirected to the studio page instead of providing inline management. Replaced with an inline "Create Custom Skill" form for instruction-based skills (creates + auto-assigns to agent), a secondary "Custom Skills Studio" link for advanced types, and a persistent "New Skill" button in the header.

#### Bug Fixes (E2E validated 2026-04-06)

- **Summarization source_step field mapping:** `SummarizationStepHandler` now resolves `output` and `message` fields from slash_command/skill steps (previously only checked `raw_output`)
- **Summarization tenant_id:** Both summarization paths (conversation + raw text) now pass `tenant_id` to `AIClient` for proper API key resolution
- **Gate tenant_id:** Agentic gate handler passes `tenant_id` to `AIClient` for API key resolution
- **WhatsApp MCP registration:** Flow notification steps now resolve MCP URL from registered `WhatsAppMCPInstance` records
- **WhatsApp reliability hardening:** Added instance metadata reconciliation for stale `container_id` / path / URL state, health-check fallback from `container_id` to `container_name`, startup watcher preference for API-reader bootstrap, tenant-safe auto-binding metadata for Graph/Studio, Hub QR degraded-state recovery actions, and a dedicated QA Tester status surface. The tester Docker health probe now targets `GET /api/health`, and both WhatsApp bridges use supervised reconnect loops plus logout-triggered QR regeneration instead of one-shot reconnect attempts.
- **Systemic tenant_id audit (11 instances across 6 files):** Fixed remaining `tenant_id` resolution gaps found via full-codebase audit. **AIClient instantiation** (8 fixes): `SchedulerService` (5 methods: `_analyze_conversation`, `_generate_agent_reply`, `_generate_opening_message`, `_generate_closing_message`, `provide_conversation_guidance`), `ConversationKnowledgeService._call_agent_llm`, `AISummaryService.__init__`, `FactExtractor._get_ai_client` — all now pass `tenant_id` for proper per-tenant API key resolution. **Router cross-tenant agent queries** (3 fixes): `_select_agent` keyword match, default agent fallback, and slash-command default agent now filter by `Agent.tenant_id` to prevent cross-tenant routing. Updated all callers (6 files) to thread `tenant_id` through constructor chains.

### Implementations

#### System AI Configuration Simplification

- **Provider-instance-based System AI config:** The AI Configuration settings page (`/settings/ai-configuration`) now points to an existing Provider Instance from the Hub instead of maintaining its own duplicated provider/model lists. Added `system_ai_provider_instance_id` FK column to Config table (migration 0027). The backend resolves vendor, API key, and base URL from the linked ProviderInstance at runtime, with legacy fallback to the old `system_ai_provider`/`system_ai_model` columns. The frontend was rewritten to show a card selector of active Provider Instances with model picker from the instance's `available_models`, eliminating the hardcoded model catalog that went stale. Manual model entry is supported for instances with no discovered models.

#### Flow Execution UX

- **Async flow execution with live progress modal:** The `POST /api/flows/{flow_id}/execute` endpoint now returns immediately (HTTP 202) with a pending FlowRun, executing steps in a background task. The frontend ViewRunModal opens instantly on click and polls every 2s for live updates — showing a progress bar, per-step status with execution times, a pulsing "Live" header indicator, and a remaining-steps counter. Previously the modal only appeared after the entire flow finished executing, leaving users with no feedback.

#### UX Friction Reduction

- **WhatsApp Instance Creation Mode Selector:** Clicking "+ Create WhatsApp Instance" now opens a selection modal with two options: Guided Setup (8-step wizard, recommended) and Advanced Setup (manual form). Removes the previously hard-to-notice standalone "Setup Wizard" button. Empty state consolidated to a single button that also opens the selector.
- **WhatsApp Wizard Welcome Auto-Fit:** Moved "Let's Get Started" button to a pinned modal footer so it's always visible. Added `autoHeight` prop to Modal component for flexible sizing (`max-h-[calc(100vh-2rem)]`).
- **WhatsApp Setup Wizard (7→8 steps):** Added "About You" step (Step 3) that collects the user's name and phone number, auto-creates a contact with DM Trigger enabled, and links it to the bound agent. Step 2 now includes an optional "Instance Name" field that auto-creates a bot contact. Steps 4-5 (DM/Group settings) have Simple/Advanced mode toggle for progressive disclosure. Step 8 (Confirmation) shows enhanced summary with green/amber indicators for completed/skipped items.
- **Image Analysis skill:** Added a dedicated multimodal image-analysis skill for inbound media. It uses Gemini vision models to describe screenshots/photos, answer captioned image questions, and hand off edit-style captions back to the image editing skill instead of double-handling them.
- **Getting Started Checklist:** New dashboard widget on the Watcher page showing 5 setup milestones (Configure Agent, Connect Channel, Add Contacts, Test in Playground, Create Flow) with progress bar, action links, and dismiss button. Auto-hides when all items are complete.
- **Hub Integration Summary Banner:** Compact status strip above the Hub tab bar showing connection counts for AI Providers, WhatsApp, Telegram, Slack, Discord, and Webhooks with colored dots. Clickable to switch tabs.
- **WhatsApp Instance Display Name:** New `display_name` column on WhatsApp instances. Shown as primary title on Hub cards with phone number as subtitle. Passed via wizard's Instance Name field.
- **Settings Progressive Disclosure:** Settings page now groups cards into "Essential" (Organization, Team Members, System AI, Integrations) always visible, and "Advanced" (8 more) collapsed by default with persistent preference.
- **Agent Creation Smart Defaults:** 4 system prompt template buttons (General Assistant, Customer Support, Sales Outreach, Technical Support) above the textarea. Model provider auto-populates from first configured provider instance. InfoTooltip on model provider field.
- **Playground Default Agent:** Auto-selects the agent marked `is_default` instead of always picking the first in the list.
- **Empty States Standardization:** New `no-contacts` EmptyState variant with address-book SVG. Applied to Agents and Contacts pages, replacing ad-hoc inline empty markup.
- **Backend:** Added `is_default` to PlaygroundAgentInfo API response. Fixed `dm_auto_mode` default from `False` to `True` in MCPInstanceResponse schema.

#### Documentation

- **DOC-001:** Comprehensive documentation overhaul of `DOCUMENTATION.md` — full accuracy audit against codebase
- **DOC-002:** Document 11 missing slash commands: email (6), search, shell, thread (3) — total now 37 commands
- **DOC-003:** Add §26.1 usage examples for all 37 slash commands organized by category
- **DOC-004:** Add channel configuration reference tables — WhatsApp (`group_keywords`, `is_group_handler`, `api_secret`), Slack (`dm_policy`, `allowed_channels`), Discord (`dm_policy`, `allowed_guilds`, `guild_channel_config`)
- **DOC-005:** Add E2E setup guides for all 5 external channels (WhatsApp, Telegram, Slack, Discord, Webhook)
- **DOC-006:** Document per-agent trigger/context override fields (`trigger_dm_enabled`, `trigger_group_filters`, `trigger_number_filters`, `context_message_count`, `context_char_limit`) in §7.3
- **DOC-007:** Expand §9.3 custom skills with subsections for Instruction, Script, and MCP Server variants including creation examples and resource quotas
- **DOC-008:** Expand §9.4 sandboxed tools with full command/parameter tables from all 9 YAML manifests
- **DOC-009:** Formalize FlowRun and FlowNodeRun status lifecycle enums in §13.5
- **DOC-010:** Add OKG merge mode reference table (`replace`, `prepend`, `merge`) in §10.3
- **DOC-011:** Add §16.4 contact usage examples (multi-channel mapping, system user linking, per-contact agent assignment)
- **DOC-012:** Update README.md feature highlights and documentation map to reflect new content
- **DOC-013:** Rename `documentation.md` → `DOCUMENTATION.md` (uppercase convention for all root MD files)
- **DOC-014:** Create `USER_GUIDE.md` — practical user-facing guide covering getting started, channels setup, agents, skills, flows, scheduler, contacts, playground, security, settings, slash commands, API, and audit

### Implementations

#### Added

- **Gate Node Step Type** — New conditional flow control node with two modes:
  - *Programmatic* (zero LLM cost): 15+ operators for numeric, string, regex, existence, and count conditions with AND/OR logic
  - *Agentic* (AI-driven): LLM evaluates pass/fail using natural language criteria
  - Configurable on-fail actions: silent skip or send notification
  - Full UI in flow builder: mode toggle, dynamic condition builder, operator dropdowns
  - Step output variables: `gate_result`, `gate_mode`, `conditions_evaluated`, `reasoning`
- **Zero-Cost Inbox Monitor Template** — Fully programmatic email monitoring (Gmail poll → gate → WhatsApp delivery) with zero AI token cost. "Zero AI Cost" badge in template wizard
- **Smart Email Filter Template** — AI-powered email filtering (Gmail poll → agentic gate → summarization → delivery). Gate criteria configurable (financial, project-specific, etc.)

### Bug fixes

#### Security

- **BUG-SEC-008 (CRITICAL):** Block privilege escalation in `update_client` — non-`api_owner` callers can no longer elevate to `api_owner` role
- **BUG-LOG-020 (CRITICAL):** Sentinel fail-closed on exceptions — security analysis now blocks content when Sentinel crashes instead of silently bypassing
- **BUG-SEC-010:** Revoke existing JWT tokens on API client secret rotation
- **BUG-SEC-016:** Pass `tenant_id` to `check_commands` in shell skill — per-tenant command policies now enforced
- **BUG-SEC-019:** Add magic bytes file type validation for uploads (PDF, DOCX, XLSX, images) — no longer extension-only
- **BUG-278:** Bump Next.js 14.1.0 → 14.2.33 — patches CVE-2025-29927, CVE-2024-34351, CVE-2024-46982, CVE-2024-51479

#### Fixed

- **BUG-299:** Fix agent detail 500 — add missing `parse_enabled_channels` import in `routes_agents.py`
- **BUG-300:** Fix agent list returning null for `enabled_channels` and all integration IDs — add channel/vector-store fields to list endpoint dict builder
- **BUG-301:** Remove duplicate `apply_agent_whatsapp_binding_policy` import in `routes_studio.py`
- **BUG-298:** Pass `tenant_id` to `AgentService` in `AgentRouter.__init__`
- **BUG-293:** Circuit breaker state now persisted to DB on transitions — survives backend restarts
- **BUG-LOG-004:** Tenant-scoped project knowledge chunk queries (defense-in-depth)
- **BUG-LOG-006:** A2A `comm_depth` now injected into skill config — depth limit functional
- **BUG-LOG-007:** Stale flow runs cleaned up on engine startup — no more stuck "running" state
- **BUG-LOG-010:** DB-level unique constraint on `flow_node_run.idempotency_key` (migration 0026)
- **BUG-LOG-011:** `cancel_run` now interrupts in-flight steps via 5s polling loop
- **BUG-LOG-012:** `ContactAgentMapping` now has `tenant_id` column (migration 0025) — prevents cross-tenant agent assignment
- **BUG-LOG-018:** Anonymous contact creation uses SHA-256 instead of Python `hash()` — deterministic IDs across restarts

#### v0.6.0 Comprehensive Audit Remediation (2026-04-06)
99-finding security and quality audit across 11 teams, 51 fixes applied in 41 files.

**Security & Auth (Group A):**
- Add authentication to 3 public Sentinel endpoints (LLM providers, models, detection-types)
- Add RBAC guards to Sentinel exception, prompts, and channel health endpoints
- Seed 6 missing RBAC permissions (channel_health, agent_communication, vector_stores)
- SSRF-validate browser proxy URL and alert webhook URL
- Fix X-Forwarded-For header bypass on webhook IP allowlist
- Validate global admin password minimum length in setup wizard

**Tenant Isolation (Group B):**
- SharedMemoryPool update/delete/share now enforce tenant_id filters
- VectorStoreRegistry cache keyed by (instance_id, tenant_id) — prevents cross-tenant access
- SkillContextService cache keyed by tenant_id:agent_id — prevents cross-tenant pollution
- SentinelEffectiveConfig returns deep copy from cache — prevents exemption bleed

**Sentinel & Detection (Group C):**
- Replace stale hardcoded valid_types with dynamic DETECTION_REGISTRY derivation — restores vector_store_poisoning, agent_escalation, browser_ssrf detection
- Fix BUG-279: cleanup_poisoned_memory now logs error (Memory model has no message_id column)

**Channels & Circuit Breaker (Group D):**
- Circuit breaker: implement half_open_max_failures, extract try_recover() from should_probe()
- Prevent duplicate Slack/Discord workspace registration (HTTP 409)
- SSRF-validate channel alert dispatcher webhook URLs
- Fix Slack adapter deprecated asyncio.get_event_loop() → get_running_loop()
- Bump aiohttp floor to >=3.10.11 (CVE-2024-52304, CVE-2024-23334)
- Fix pinecone-client → pinecone package name

**Memory, OKG & A2A (Group E):**
- Clamp decay_lambda, apply_decay_to_score, and mmr_lambda to valid ranges
- Add user_id check to OKG forget ownership validation
- Fix missing await on A2A vector store search
- Align OKG _compute_decay unknown-timestamp fallback with temporal_decay.py

**Browser Automation (Group F):**
- Per-tenant browser session cap (prevents cross-tenant DoS)
- Thread-safe singleton creation with double-checked locking
- Fix open_tab TOCTOU race and page leak on navigation failure
- extract()/screenshot() return BrowserResult instead of raising exceptions
- go_back()/go_forward() handle None response (no history)
- Cleanup loop releases lock before provider.cleanup()

**Skills, Flows & Build (Group G):**
- Fix critical NameError: router.py tenant_id → self.tenant_id on DM messages
- Scope flow stale cleanup to flow_definition_id (prevents cross-tenant damage)
- Remove nuclei from Dockerfile (BUG-278 — runs in toolbox container)
- Replace hardcoded agent ID 7 with config flag in scheduler_skill
- Fix VectorStoreInstance nullable mismatches vs migration definitions

### Implementations

#### WhatsApp Post-Install Setup Wizard + Inline Helpers (2026-04-05)
Guided 7-step wizard that walks non-technical users through the full WhatsApp onboarding flow end-to-end, replacing the previous "figure it out across 3 pages" experience.

- **Setup Wizard** (`frontend/components/whatsapp-wizard/`): Step 1 Welcome → Step 2 Create instance + inline QR scan with live polling → Step 3 DM Auto Mode + number allowlist → Step 4 Group filters + trigger keywords → Step 5 Contact creation with DM Trigger toggle → Step 6 Agent-to-channel binding → Step 7 Summary with next-steps guidance.
- **Auto-launch**: Fires after the main onboarding tour completes if no WhatsApp instances exist. Uses `tsushin:onboarding-complete` CustomEvent from `OnboardingContext` — no coupling between contexts.
- **Manual triggers**: "Setup Wizard" button in Hub WhatsApp section header (always visible), plus "Guided Setup" / "Manual Setup" split CTA in the empty state.
- **Reusable `InfoTooltip` component** (`frontend/components/ui/InfoTooltip.tsx`): Click-to-toggle popover with title + body text, click-outside/Escape dismiss, dark-mode aware.
- **6 inline helpers placed**: Hub filters modal (Group Filters, Number Filters, Group Keywords, DM Auto Mode), Contacts page (DM Trigger checkbox), Agent Channels (WhatsApp Integration heading).
- **Self-contained state**: `WhatsAppWizardContext` manages wizard lifecycle and accumulated data independently from `OnboardingContext`. Each step calls real APIs immediately — partial setup is usable if the user exits mid-flow.

#### Flow Creation Wizard — Pre-built Hybrid Automations (2026-04-05)
New "From Template" button on `/flows` opens a 3-step wizard (pick → configure → preview) for instantiating common hybrid (programmatic + agentic) flows in one click. Showcases the platform's hybrid value prop: deterministic/cheap programmatic fetch steps gate into agentic summarization steps, avoiding LLM spend when there's no data.

- **5 templates shipped**: Daily Email Digest, Weekly Calendar Summary, Summarize on Demand, Proactive Watcher, New-Contact Welcome.
- **Architecture**: `backend/services/flow_template_seeding.py` defines templates as code (pure `build(params, tenant_id) → FlowCreate` functions); `GET /api/flows/templates` and `POST /api/flows/templates/{id}/instantiate` endpoints in `routes_flows.py`. No new DB primitives — reuses existing FlowDefinition/FlowNode step types and `on_failure="skip"` as the conditional-gate mechanism.
- **Security hardening**: `_validate_template_params` enforces required/options/min/max from each template's declarative schema, with numeric clamping (e.g. `max_emails` clamped to 1–100 server-side regardless of client input). `_validate_tenant_refs` verifies every `agent_id`, `persona_id`, and sandboxed `tool_name` referenced in the generated flow belongs to the caller's tenant — blocks cross-tenant resource leaks at instantiate time (422 response). Option whitelists enforced on select/channel params.
- **Scheduling correctness**: `_first_scheduled_at` uses pytz to compute UTC-naive `scheduled_at` from the user's wall-clock HH:MM in their chosen timezone (verified: 08:00 São Paulo → 11:00 UTC).
- **Frontend**: `CreateFromTemplateModal.tsx` dynamically renders parameter forms from each template's `params_schema`. Matches existing design system (slate-800 shell, teal/cyan accents, rounded-2xl, backdrop-blur).

#### Changed

##### WhatsApp filter typeahead + Studio Contacts UX overhaul (2026-04-05, branch `wpp`)
Replaced free-text entry in Hub > Communications > WhatsApp "Message Filters" (Group Filters + DM Allowlist) with live-autocomplete dropdowns, and streamlined the Studio > Contacts add/edit workflow so users no longer have to manage WhatsApp IDs or click resolve buttons.

**Hub filter typeahead**
- New `TypeaheadChipInput` component (`frontend/components/hub/TypeaheadChipInput.tsx`) with 250 ms debounce, arrow-key nav, free-text fallback, chip × removal.
- New WhatsApp MCP endpoints (`backend/whatsapp-mcp/main.go`): `GET /api/groups` lists joined groups from the local chats store; `GET /api/contacts` merges the whatsmeow address book with DM chats, with `?q=` substring/phone-prefix filter.
- New backend proxy routes (`backend/api/routes_mcp_instances.py`): `GET /api/mcp/instances/{id}/wa/groups` and `…/wa/contacts`, tenant-scoped via `context.can_access_resource`, using `MCPAuthService` Bearer auth.
- Frontend: `api.searchWhatsAppGroups()` / `searchWhatsAppContacts()` and the typeahead wired into both Group Filters and DM Allowlist fields in `hub/page.tsx`.

**Studio > Contacts**
- Removed "Resolve All WhatsApp" header button and per-row "Resolve WA" button — resolution is now silent/automatic.
- Removed manual "WhatsApp ID" text field from the add/edit form (users no longer need to know this value).
- Added "Default Agent" dropdown to the contact add/edit form (only for `role=user`); creates/updates/deletes a `ContactAgentMapping` on save.
- Helper text under Phone Number: *"WhatsApp ID will be auto-detected from the phone number after saving."*
- Contacts page schedules a `loadData()` refresh 2.5 s after create/update to surface server-side resolution without manual reload.

### Bug fixes

#### WhatsApp proactive resolver missing Bearer auth (2026-04-05, branch `wpp`)
`services/whatsapp_proactive_resolver.py` was calling the MCP `/check-numbers` endpoint without an `Authorization` header, causing auto-resolution to fail with **HTTP 401** after Phase Security-1 enabled `MCP_API_SECRET` enforcement. Both single-number and batch resolution paths now pull the instance's `api_secret` via `get_auth_headers()` and include the Bearer token. Verified end-to-end: creating a contact with phone `+5527998701042` auto-populates `whatsapp_id=5527998701042` within ~2 s.

### Implementations

#### Performance
##### Backend image optimization — dependency hygiene + opt-out flags (2026-04-05)
Follow-up to commit `c2402bd` (CPU-only torch). Removed declared-but-unused dependencies, deduped conflicting pytest declarations, split test deps into a dev-only tier, removed system packages that belong in the `toolbox` sandbox container, and added opt-out ARG flags for heavy optional assets. Default image preserves every existing feature; new lean build variant drops ~2.05 GB.

**Dependency removals & reshuffling:**
- **Removed `slack-bolt>=1.20.0`** from `backend/requirements-app.txt` — declared but zero imports. Slack adapter uses `slack-sdk` exclusively (verified in `backend/channels/slack/adapter.py` and `backend/api/routes_slack.py`).
- **Removed duplicate pytest stack** from production tiers: `pytest`, `pytest-asyncio` deleted from `requirements-base.txt`; `pytest`, `pytest-asyncio`, `pytest-cov` deleted from `requirements-phase4.txt`. Conflicting version floors (`>=7.4.4` vs `>=7.4.0`) resolved.
- **New `backend/requirements-dev.txt`** — unified dev/CI testing deps (pytest, pytest-asyncio, pytest-cov), NOT installed in the production Docker image. Run locally: `pip install -r backend/requirements-dev.txt`.
- **Moved `docker>=7.0.0`** from `requirements-base.txt` → `requirements-app.txt` with accurate usage comment (Phase 8 MCP container lifecycle via `services/container_runtime.py`).
- **Bumped `google-generativeai>=0.4.0` → `>=0.8.0`** — ancient floor (Jan 2024) replaced with current floor.

**System packages:**
- **Removed `nmap` and `whois`** from `backend/Dockerfile` apt install — sandboxed tools run in the per-tenant `toolbox` container (`backend/containers/Dockerfile.toolbox`), not in the backend image. Backend Python code references them only as string tokens for routing.

**New Docker build flags (both default=true, zero behavior change by default):**
- **`INSTALL_PLAYWRIGHT=true`** — gates `playwright install chromium` (~1.1 GB Chromium binary) and Chromium system libs (libnss3, libatk, libcups2, etc.). Set `false` if the deployment does not use browser automation skills.
- **`INSTALL_FFMPEG=true`** — gates ffmpeg (~250 MB). Required by Kokoro TTS for WAV→Opus conversion (`backend/hub/providers/kokoro_tts_provider.py:457`). Set `false` if TTS is not used.

**Example lean build:**
```bash
docker build --build-arg INSTALL_PLAYWRIGHT=false --build-arg INSTALL_FFMPEG=false \
  -t tsushin-backend:lean backend/
```

**Measured results (multi-arch arm64 image):**

| Variant | Image Size | vs Baseline | Notes |
|---------|-----------|-------------|-------|
| Baseline (pre-c2402bd) | 4.89 GB | — | Before CPU-only torch fix landed |
| Default (after this change) | 4.84 GB | −50 MB | Playwright + ffmpeg still installed |
| Lean (both flags false) | 2.79 GB | **−2.10 GB (−43%)** | No Chromium, no ffmpeg |

Build time (no-cache, BuildKit pip mounts intact): ~3m 23s for default rebuild.

**Verified end-to-end:** backend health + readiness endpoints return 200; API v1 `/agents` sweep returns 200; `slack_sdk`/`docker`/`google.generativeai`/`playwright`/`ffmpeg`/`sentence-transformers` all importable; `import pytest` + `import slack_bolt` correctly raise `ModuleNotFoundError` in production image; torch remains `2.11.0+cpu` (no CUDA regression); Kokoro TTS provider imports; Slack adapter imports; per-tenant toolbox container still reachable with nmap + dig available.

### Bug fixes
#### BUG-275 — Global refresh button did not reliably update lists across pages (2026-04-05)
The header global refresh button dispatches a `tsushin:refresh` CustomEvent that pages subscribe to in `useEffect`. Audit found 9 pages registered the listener with empty deps `[]`, capturing the FIRST render's `loadData` closure — the listener kept calling that stale closure forever, so loaders executed with initial state values instead of current state.

- **New hook** `frontend/hooks/useGlobalRefresh.ts` uses a ref-of-callback pattern so the listener ALWAYS invokes the latest callback. Eliminates stale-closure bugs once and for all.
- **Migrated 9 pages/components**: `flows`, `hub`, `agents`, `agents/contacts`, `agents/personas`, `hub/sandboxed-tools`, `settings/organization`, `watcher/ConversationsTab`, `watcher/DashboardTab`, `watcher/FlowsTab`.
- **Pagination snapback** on Flows: when a delete drops the total below the current page's offset, the page auto-corrects to the last non-empty page without clobbering the list in between.
- **Validated** via Playwright: clicking refresh on flows/agents/contacts/settings/hub fires a fresh `GET` on every click, zero stale data.

#### BUG-LOG-015 — Memory table now has tenant_id for DB-level isolation (2026-04-05)
Previously the `Memory` table enforced tenant isolation only via `agent_id` — every query site had to remember to scope by `agent_ids ∈ tenant's agents`. A missed site would be a cross-tenant leak. This change enforces isolation at the row level.

- **Alembic migration 0024** adds `tenant_id VARCHAR(50) NOT NULL` with backfill from `Agent.tenant_id`, deletes orphan rows (28 in dev DB), and adds composite index `(tenant_id, agent_id, sender_key)`.
- **Write paths** populate tenant_id on every INSERT: `agent_memory_system.save_to_db` (via lazy-caching `_get_tenant_id` helper — deduplicated with the pre-existing MemGuard helper), `playground_message_service.branch_conversation`.
- **Read paths simplified**: `conversation_knowledge_service._get_thread_messages`, `conversation_search_service._search_like`, and `routes.py` stats now filter Memory directly on `tenant_id`, replacing the Agent-JOIN and tenant-agent-id-IN-list patterns.
- **Validated**: 422 rows backfilled with correct tenant_id, 0 NULLs; live chat test creates Memory rows with tenant_id populated; backend starts clean with `alembic upgrade head 0023 → 0024`.

#### /flows double-fire on global refresh (BUG-275 follow-up, 2026-04-05)
Perfection QA caught that `frontend/app/flows/page.tsx` still used the raw `addEventListener('tsushin:refresh')` pattern INSIDE the `useEffect([currentPage, pageSize])` that loaded data. Every pagination change re-attached the listener, and on refresh click the page's three loader GETs (`flows/`, `flows/runs`, `conversations/active`) fired twice. Migrated flows/page.tsx to the `useGlobalRefresh` hook with an empty-deps mount registration — single subscription per mount.

#### BUG-276 — Force-delete of flows with completed runs blocked by conversation_thread FK (2026-04-05)
Three stress-test flows (IDs 140/139/123) could not be force-deleted. Root cause: conversation_thread rows 596/597/598 had `status='timeout'` referencing FlowNodeRun IDs — the force-delete path only nullified `flow_step_run_id` for threads with `status='active'`, so non-active threads kept the FK reference and blocked the FlowNodeRun cascade, rolling the transaction back under a generic 500.

- **Fix** in `backend/api/routes_flows.py` delete_flow: after the state transition on `status='active'` threads, widen the nullification to `flow_step_run_id = NULL` for ALL statuses referencing the flow's step runs. History preserved on threads, FK cleared, cascade proceeds.
- **Observability**: included `{e}` in the `logger.exception` format string so future delete failures surface the DB constraint name.
- **Validated**: all three stuck flows deleted successfully (HTTP 204); threads retained `status='timeout'` with `flow_step_run_id=NULL`; zero dangling FKs. UI round-trip confirmed.

#### BUG-277 — WhatsApp agent silent-drop regression (2026-04-05)
Two compounding regressions silently broke the WhatsApp agent: the bot would receive DMs into its MCP container but never route them through the agent or respond. Watcher logs showed neither `Found N new messages` nor any Gemini call, leaving the user to believe the bot had hung.

- **`backend/app.py` — `CachedContactService` missing `tenant_id`**: after V060-CHN-006 made the service fail-closed when `tenant_id` is unset, every `identify_sender()` lookup returned `None`. The MessageFilter relies on `contact.is_dm_trigger` to decide whether to wake the agent on DMs; with every contact lookup returning `None`, DMs fell through to `dm_auto_mode` (`False`) and the watcher silently advanced `last_timestamp` without routing. Fixed by creating a per-tenant `CachedContactService` scoped to `instance.tenant_id`, cached in `app.state.contact_services` (dict keyed by tenant). Same fix applied to the Telegram callback path, which now passes `bot_instance.tenant_id`.
- **`backend/agent/router.py` — `UnboundLocalError: cannot access local variable 'os'`**: two redundant `import os` statements inside `route_message()` made `os` a function-local name across the entire 1200-line function, shadowing the module-level import. The CB-queue check at line 1297 (`elif os.getenv("TSN_CB_QUEUE_ENABLED", ...)`) runs before those inner imports and crashed with `UnboundLocalError` on every message. Fixed by deleting the two redundant inner imports; the module-level `import os` at the top of `router.py` is used everywhere.

Validated with a tester → bot → Gemini → tester WhatsApp round-trip: bot responded with `"Olá, Vini! Tudo bem por aqui também. CUSTOM_SKILL_ACTIVE. Como posso te ajudar com este teste pós correção?"` and the tester instance received the response.

#### v0.6.0 Critical Remediation — 11 Audit Findings (2026-04-05)
Coordinated fix sweep for 11 CRITICAL/HIGH findings from the v0.6.0 audit, grouped into 5 remediation domains. Each fix programmatically verified; full regression (infrastructure + auth + API v1 sweep + tenant endpoint sweep + agent chat + 6-screen browser QA) passed zero new errors.

**Group A — Auth & Security Hardening** (commits 2327bb6 + 829877b)
- `V060-API-004`: `/api/v1/*` UI-JWT path now enforces password-reset invalidation (`password_changed_at` vs `token.iat`), parity with SEC-001/BUG-134 UI path. Missing `iat` claim rejected with 401, closing a JWT-stripping bypass. Same hardening backported to `auth_dependencies.py`.
- `V060-HLT-005`: `PUT /api/channel-health/alerts/config` now SSRF-validates the webhook URL via `utils.ssrf_validator.validate_url()`. Blocks `file://`, cloud metadata IPs (`169.254.169.254`, etc.), localhost, private ranges, and non-http(s) schemes. `HTTPException` re-raise prevents 400→500 downgrade.
- `V060-SKL-002`: MCP server create/update now require HTTPS whenever `auth_type != 'none'` (bearer/header/api_key). Prevents plaintext transmission of credentials over HTTP; rejects downgrade attempts on existing HTTPS+auth configs.

**Group B — Tenant Isolation + Queue Safety** (commits 7971b4e + 1e5e241)
- `V060-CHN-006`: `CachedContactService` and base `ContactService` now accept `tenant_id` and filter `Contact`/`ContactChannelMapping` queries by tenant. Cache keys prefixed per tenant. Fail-closed on missing tenant_id. `AgentRouter` threads tenant_id to CachedContactService from all 6 call sites (queue_worker, watcher_manager, routes.py, app.py). Follow-up extends to `SchedulerService` (12 sites) and `FlowEngine._resolve_contact_to_phone` — closes cross-tenant leaks in scheduled messages and flow recipient resolution.
- `V060-HLT-003`: `QueueWorker._poll_and_dispatch` now consults `ChannelHealthService.is_circuit_open()` for whatsapp/telegram channels before dispatching. When CB is OPEN, dispatch is deferred (item remains pending, no retry burn, no 500ms re-enqueue spiral). Router's CB-enqueue guard skipped when `trigger_type=='queue'`. Instance-id resolution now uses agent's explicit `whatsapp_integration_id`/`telegram_integration_id` FK instead of tenant-wide `.first()`.

**Group C — Slack/Discord Channel Integration** (commit e1c1949)
- `V060-CHN-001`: `AgentRouter` now registers `SlackChannelAdapter` and `DiscordChannelAdapter` with the channel registry when a tenant has exactly one active integration (or when explicit integration_id is passed). Bot tokens decrypted via `TokenEncryption` + per-channel encryption key, matching existing routes_slack/routes_discord patterns.
- `V060-CHN-002`: New public router `backend/api/routes_channel_webhooks.py` exposes two unauthenticated endpoints gated by cryptographic signature verification:
  - `POST /api/slack/events` — HMAC-SHA256 verification against `signing_secret_encrypted`, 5-minute timestamp skew for replay protection, `url_verification` challenge handled.
  - `POST /api/discord/interactions` — Ed25519 verification via PyNaCl, type-1 PING handshake, type-5 deferred response.
  - Verified events enqueue to `message_queue` with channel='slack'/'discord'; QueueWorker's new `_process_slack_message`/`_process_discord_message` handlers instantiate AgentRouter with tenant_id + integration_id threaded through.
- **Dep added:** `PyNaCl>=1.5.0` for Ed25519 signature verification.

**Group D — Memory (OKG) + Provider Wiring** (commit 36d694c)
- `V060-MEM-001`: `ProviderBridgeStore._records_to_dicts` now preserves the full metadata dict under a nested `'metadata'` key. OKG recall post-filter reads `record.get('metadata',{}).get('is_okg')` and was seeing `{}` for every record — so every OKG record was skipped, making OKG recall return zero results with any external vector store. Flat spread retained for backwards compat.
- `V060-PRV-001`: `AIClient.__init__` now accepts an optional `api_key` kwarg that bypasses DB/env lookup. Raw test-connection in first-time-setup wizard (tenant with no provider key) previously failed at AIClient construction with "No API key found" before the route handler could apply the user's credential. Now the raw key is passed directly.
- `V060-PRV-002`: Saved-instance test-connection now passes the instance's own decrypted api_key to AIClient (falling back to tenant key only when instance has none). Previously the resolved api_key was never applied, so a valid tenant key masked a broken instance key and produced a false success.

**Group E — Custom Skill Security** (commit cc0de12)
- `V060-SKL-001`: New `_scan_skill_content()` helper concatenates `instructions_md` + `script_content` into a single analyzable blob and submits to `SentinelService.analyze_skill_instructions`. Both `create_custom_skill` and `update_custom_skill` now invoke this helper whenever either field is present/changed. Previously script-type skills with empty instructions landed as `scan_status='clean'` without Sentinel ever seeing the code — an attacker could upload a script that reads `OPENAI_API_KEY` + `/etc/passwd` and exfiltrates via HTTP and it would auto-enable in the agent sandbox. The network-import advisory is retained as an augmenting signal, no longer the primary defense.

### Implementations

#### Added

#### Webhook-as-a-Channel (v0.6.0)
- **New first-class channel type** alongside WhatsApp/Telegram/Slack/Discord/Playground. Bidirectional HTTP integration for CRMs, Zapier, custom apps, ticketing systems.
- **Inbound endpoint**: `POST /api/webhooks/{id}/inbound` (public, HMAC-gated). Accepts `X-Tsushin-Signature: sha256=<hex>` (HMAC-SHA256 over `timestamp + "." + body`) and `X-Tsushin-Timestamp` (±5 min replay window). Cryptographically authenticated, no bearer token.
- **Outbound callbacks**: agent replies POSTed back to customer-provided callback URL (optional, enabled per integration). SSRF-validated on create via existing `utils.ssrf_validator`. HMAC-signed. 10s timeout, no redirects, 64 KB response cap.
- **Defense-in-depth**: per-webhook rate limit (default 30 rpm), optional CIDR IP allowlist, configurable payload size cap (default 1 MB), generic 403 on auth failures (no detail leak).
- **Management API** (`/api/webhook-integrations`, tenant-scoped via `filter_by_tenant`): POST create (returns plaintext secret ONCE), GET list/detail (masked `whsec_XXXX…` preview only), PATCH update, POST rotate-secret (returns new plaintext once, invalidates old), DELETE.
- **Encryption at rest**: `webhook_encryption_key` in Config + Fernet per-tenant workspace key derivation via `TokenEncryption`. New `get_webhook_encryption_key()` helper in `encryption_key_service`.
- **Agent binding**: `Agent.webhook_integration_id` FK (one webhook → one agent). `enabled_channels` accepts `"webhook"`. `AgentRouter` registers `WebhookChannelAdapter` per instance; `_is_agent_valid_for_channel` enforces binding.
- **Queue dispatch**: `QueueWorker._process_webhook_message` normalizes payload into channel-agnostic message dict, routes through AgentRouter with `webhook_instance_id`, persists LLM result for `GET /api/v1/queue/{id}` polling.
- **Security tested**: 13-point adversarial suite verifies HMAC verify, missing/wrong signature, replay, nonexistent webhook, oversized payload, rate limit, SSRF, unauthenticated access, secret rotation. All passing.
- **UI integration**: Hub → Communication section ("Webhook Integrations" cards with Rotate Secret + Delete), `WebhookSetupModal` two-phase flow (form → secret reveal with copy-to-clipboard + signing instructions), Agent Channels tab toggle + radio selector, Studio/Graph channel nodes (cyan palette, reuses existing `isGlowing`/`isFading` animations identical to WhatsApp/Telegram), Flows step targeting, ChannelHealthTab, dashboard distribution chart color.
- **Alembic 0023**: `webhook_integration` table + `agent.webhook_integration_id` FK + `config.webhook_encryption_key`.
- **Graph View integration**: webhook channels now render as first-class nodes alongside WhatsApp/Telegram/Playground (cyan palette, integration name as subtitle). `/api/v2/agents/graph-preview` exposes `channels.webhook[]` with `WebhookChannelInfo` schema + `agent.webhook_integration_id`; `useGraphData.ts` creates webhook→agent edges; `GraphCanvas.getChannelType()` recognizes `channel-webhook-*` so the existing edge-glow/fade activity pipeline fires identically to other channels on inbound message activity.
- **RBAC**: `integrations.webhook.{read,write}` permission scopes (owner/admin/member get write, readonly gets read). All 6 webhook CRUD routes gated by `require_permission()` matching the Slack/Discord pattern.
- **Tenant binding validation**: `routes_agents.py` create/update handlers validate that the supplied `webhook_integration_id` resolves to a WebhookIntegration in the caller's tenant before persisting the FK, closing a cross-tenant binding gap.
- **Emergency stop integration**: webhook inbound endpoint honors `Config.emergency_stop` and returns 503 at ingress (before enqueueing) when the global stop is active. Circuit breaker queuing in `AgentRouter` also maps `webhook_instance_id` for deferred-message tenant/agent resolution.

#### Live Provider Model Discovery (v0.6.1)
- **Self-updating model dropdowns**: `/setup` and the provider-instance modal now auto-refresh their model lists against the provider's real `/models` endpoint whenever a user pastes an API key — no more hand-maintained Gemini/OpenAI/etc. lists going stale when Google or OpenAI ship new models.
- **New endpoint** `POST /api/provider-instances/discover-models-raw`: accepts `{vendor, api_key, base_url?}`, performs a single outbound request to the provider, returns the live model list. API key is used once and never stored.
- **Gemini live discovery**: backend calls Google's `/v1beta/models` with pagination, filters to `generateContent`-capable models, strips the `models/` prefix. Works on both saved instances (Auto-detect button) and pre-save (as the user types their key).
- **Unified static fallback**: the previously-inlined `KNOWN_MODELS` dict in `discover_models` was replaced by a module-level `PREDEFINED_MODELS` registry consumed by the new public `GET /api/provider-instances/predefined-models` endpoint — used as a suggestion fallback when no API key is available yet.
- **Supported vendors for live pre-save discovery**: gemini, openai, groq, grok, deepseek, openrouter. Anthropic keeps the static list (no public `/models` endpoint).
- **Refreshed Gemini static fallback**: added Gemini 3.x preview IDs (`gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`) and 2.5 stable (`gemini-2.5-flash-lite`) for the "no key entered yet" case.
- **Datalist UX**: instance-modal model input now uses a `<datalist>` bound to the current vendor, so users get vendor-specific autocomplete while retaining free-text entry for custom IDs.

#### Flows Bulk Actions & Page Size Selector (v0.6.1)
- **Bulk actions bar**: Multi-select flows to Enable, Disable, or Delete them in bulk. Bar appears above the table when rows are selected with selection count and Clear selection link.
- **Page size selector**: Per-page dropdown (10/25/50/100) added to the pagination footer, replacing the hardcoded 25-per-page limit. Changing page size resets to page 1 and clears any selection.
- **Force-delete fallback**: Bulk delete detects flows with existing runs and prompts once to force-delete the affected set.

#### OKG Term Memory Skill (v0.6.0)
- **Ontological Knowledge Graph skill**: New `okg_term_memory` skill providing structured long-term memory with typed metadata (subject/relation/type/confidence). First multi-tool skill in Tsushin.
- **Three LLM-callable tools**: `okg_store` (store memory with ontological metadata), `okg_recall` (search by query + metadata filters with temporal decay), `okg_forget` (delete by doc_id).
- **Auto-capture hook**: Post-response FactExtractor integration auto-stores durable facts from conversations with `source=auto_capture`.
- **Auto-recall (Layer 5)**: `OKGContextInjector` hooks into `AgentMemorySystem.get_context()` to inject relevant OKG memories as XML-tagged `<long_term_memory>` blocks. HTML-escaped content prevents prompt injection.
- **SkillManager multi-tool support**: `get_all_mcp_tool_definitions()`, `_current_tool_name` dispatch, multi-tool schema validation. All existing single-tool skills unaffected.
- **OKGMemoryAuditLog table**: Full audit trail of store/recall/forget/auto_capture operations with MemGuard block tracking.

#### MemGuard Vector Store Defense (v0.6.0)
- **New pattern categories**: `embedding_manipulation` (weight 0.80) detects raw float arrays, metadata overrides, distance manipulation. `cross_tenant_leak` (weight 0.75) detects tenant metadata smuggling and namespace confusion.
- **Batch poisoning detection**: `detect_batch_poisoning()` with configurable thresholds (max 50 docs / 60s window / 0.95 similarity). Immediate block for batches exceeding max_batch_write_size.
- **Post-retrieval scanning (Layer C)**: `validate_retrieved_content()` scans retrieved vector store results at lower threshold (0.5 vs 0.7) and verifies tenant_id metadata isolation.
- **Per-store security config**: `VectorStoreInstance.security_config` JSON column with configurable thresholds, rate limits, and cross-tenant check toggle.
- **Rate limiter**: `VectorStoreRateLimiter` singleton with sliding-window enforcement for reads (per agent) and writes (per tenant).
- **Bridge security hooks**: `ProviderBridgeStore` accepts optional `security_context` for automatic post-retrieval MemGuard validation.

#### Sentinel Vector Store Detection (v0.6.0)
- **New detection type**: `vector_store_poisoning` in DETECTION_REGISTRY with `applies_to: ["vector_store"]`, severity "high", default enabled.
- **LLM prompts**: 3 aggressiveness levels for vector store content analysis (instruction-bearing docs, embedding manipulation, batch saturation, cross-tenant leakage).
- **Unified classification update**: `vector_store_poisoning` added to all 3 UNIFIED_CLASSIFICATION_PROMPT levels with proper priority ordering.
- **Schema**: `detect_vector_store_poisoning` toggle on SentinelConfig, `vector_store_poisoning_prompt` custom prompt, `vector_store_access_enabled` + `vector_store_allowed_configs` on SentinelAgentConfig.
- **Frontend**: Toggle in Sentinel Settings General tab, Layer C card in MemGuard tab, prompt editor in Prompts tab.
- **Seed defaults**: System config seeds with `detect_vector_store_poisoning=True`.


#### Vector Store Auto-Provisioning
- **One-click container deployment**: Auto-provision Docker containers for Qdrant and MongoDB directly from the Hub UI. Toggle "Auto-Provision" during creation to have Tsushin spawn, configure, and health-check a container automatically.
- **Container lifecycle management**: Start, stop, restart auto-provisioned containers from the Vector Store card. Container status (running/stopped/error) displayed with real-time indicators.
- **Port allocation**: Dedicated port range 6300-6399 for vector store containers (separate from MCP 8080-8180).
- **Named volumes**: Data persists across container restarts via Docker named volumes (`tsushin-vs-{vendor}-{tenant}-{id}`).
- **Resource limits**: Configurable memory limits (512MB/1GB/2GB/4GB) per container.

#### Default Vector Store Settings Page
- **Global tenant default**: New Settings > Vector Stores page with dropdown selector to choose the tenant-wide default vector store. Replaces the confusing per-instance `is_default` toggle.
- **Three-tier resolution**: Agent override > Tenant default (Settings) > ChromaDB (built-in). Agents without an explicit vector store assignment now use the tenant default.
- **Settings API**: `GET/PUT /api/settings/vector-stores/default` for managing the default selection.

#### MongoDB Local Mode for Vector Stores
- **Local cosine similarity fallback**: MongoDB adapter now supports self-hosted MongoDB 7.0+ without Atlas Vector Search. Toggle "Local Mode" in the UI to use Python-side cosine similarity instead of Atlas `$vectorSearch` aggregation.
- **Registry integration**: `use_native_search` config option passed from `extra_config` through the provider registry.
- **UI toggle**: MongoAtlasConfigForm has a "Local Mode" toggle that sets `use_native_search: false`.

#### A2A Communication Memory Enrichment
- **Cross-agent memory retrieval**: When Agent A asks Agent B via A2A communication, Agent B's vector store is now searched for relevant memories and injected into the A2A prompt context. This enables agents to recall facts from their external vector stores (Qdrant, MongoDB) during inter-agent conversations.
- **disable_skills flag**: Target agents in A2A calls no longer have access to skills/tools, preventing recursive tool invocations. Pure LLM-only responses using memory context.

#### Dynamic Vector Store Vendor Labels
- **MongoDB vs Atlas badges**: Vector Store cards in the Hub UI now show "MongoDB" badge for local mode instances and "Atlas" for native Atlas Vector Search instances.
- **Vendor dropdown**: Changed from "MongoDB Atlas" to "MongoDB" in the vendor selector.

### Fixed
- **Agent API response**: `vector_store_instance_id` and `vector_store_mode` fields were missing from the `GET /api/agents/{id}` response.
- **A2A memory search**: Use `get_shared_embedding_service()` singleton instead of creating a new `EmbeddingService()` per call (prevents model reload).
- **MongoDB adapter async safety**: Local cosine search methods now run in `asyncio.to_thread()` to prevent blocking the event loop.
- **MongoDB adapter memory**: Added projection to `_local_cosine_search_with_embeddings` to prevent loading entire documents into memory.
- **Frontend toggle**: Fixed Local Mode toggle treating `undefined` as local mode on first click.

---

## [0.6.0] - 2026-04-01

### Implementations

#### Temporal Memory Decay Frontend (Item 37)

- **Agent Studio decay configuration**: New "Temporal Decay" section in Agent Builder Memory Config with enable toggle, decay rate slider (0.001-1.0), archive threshold slider (0-1.0), and MMR diversity slider (0-1.0). Decay fields persisted via builder save endpoint with float validation and rounding.
- **Memory Inspector freshness badges**: Per-fact colored dots (green=fresh, yellow=fading, orange=stale, gray=archived) with decay factor percentage. Freshness distribution summary bar when decay is enabled.
- **Archive decayed facts**: Dry-run preview with fact count, then confirm to archive. Clears on agent/thread switch to prevent wrong-context operations.

#### Channel Health Tab in Watcher (Item 38)

- **New Watcher tab**: "Channel Health" tab with summary bar (total, healthy, unhealthy, open circuits), instance cards grid with circuit breaker state visualization, and per-instance Probe/Reset actions.
- **Event history**: Expandable per-instance event timeline showing circuit breaker state transitions with timestamps and reasons.
- **Alert configuration**: Collapsible panel with webhook URL, email recipients, cooldown settings, and enable/disable toggle.
- **8 API client methods**: Full frontend integration with all channel health backend endpoints.

#### Test Connection on Provider Instance Create (Item 27b)

- **New backend endpoint**: `POST /api/provider-instances/test-connection` accepts raw credentials (vendor, base_url, api_key) without requiring a saved instance. SSRF validation on base_url, falls back to tenant-level API key.
- **Create mode button**: Test Connection button now visible during instance creation (previously edit-only). Disabled when no API key entered (except Ollama).

#### Inline Screenshots in Playground (Item 35)

- **Multi-image support**: Backend now returns all `media_paths` images (previously only first). New `image_urls` array in response alongside backward-compatible `image_url`.
- **Image grid + lightbox**: Multiple images render in a 2-column grid. Click any image to open full-screen lightbox overlay with close on backdrop click or Escape key.

#### Message Queuing on Circuit Breaker OPEN (Item 38)

- **Router circuit breaker check**: `route_message()` now checks channel circuit breaker state before processing. If the channel's circuit breaker is OPEN, messages are enqueued via `MessageQueueService` instead of being processed immediately. Guarded by `TSN_CB_QUEUE_ENABLED` env var (default: true). Fail-safe: if enqueue fails, falls through to normal processing.

#### Changed

- **Docker env passthrough**: Added `GROQ_API_KEY`, `GROK_API_KEY`, `ELEVENLABS_API_KEY` to docker-compose.yml backend environment.
- **Docker Compose v2 required**: Installer no longer supports `docker-compose` v1. Reverts the BUG-271 `DOCKER_BUILDKIT=0` workaround (installer would force-disable BuildKit for v1 compatibility). The backend Dockerfile now requires BuildKit for pip/nuclei cache mounts. Docker Compose v2 (`docker compose`) is bundled with Docker Desktop ≥20.10 and is the CLAUDE.md convention. Installer errors out with a clear upgrade message if only v1 is detected.

#### Backend Container Build Optimization (2026-04-04)

- **Backend image size: 11.5 GB → 4.89 GB (-58%)**. Full `--no-cache` build time: 14m22s → 3m59s (-72%). Layer export: 93s → 32s (-66%).
- **Root cause**: `sentence-transformers` → default `torch` wheel was pulling ~4.3 GB of NVIDIA/CUDA/triton binaries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `triton`, etc.) that never execute — embeddings run on CPU via `asyncio.to_thread()`.
- **Fix**: Install torch from the CPU-only index (`https://download.pytorch.org/whl/cpu`) as a dedicated step before `requirements-phase4.txt`. Saves 4.3 GB of unused CUDA runtime per image.
- **BuildKit cache mounts**: Added `# syntax=docker/dockerfile:1.4` + `--mount=type=cache,target=/root/.cache/pip` to all pip install steps and the nuclei download. Wheels persist across `--no-cache` rebuilds.
- **Tiered requirements**: Split `requirements.txt` into `requirements-base.txt` (stable core: fastapi, sqlalchemy, pydantic, security deps), `requirements-app.txt` (volatile integrations: anthropic, openai, google-*, slack, discord, telegram), and `requirements-optional.txt` (kubernetes, gcp-secret-manager, qdrant, pinecone, pymongo). Iterative rebuilds only invalidate the changed tier + below.
- **Optional deps build arg**: New `INSTALL_OPTIONAL_DEPS` ARG (default: `true`). Local dev can build with `--build-arg INSTALL_OPTIONAL_DEPS=false` to skip K8s/GCP/vector clients (~50 MB saved). All five optional deps are lazy-imported at runtime, so disabling is safe as long as the corresponding feature isn't activated.
- **Nuclei download cache**: Cached across builds, saving ~5-10s per full rebuild.
- **Updated references**: `.github/workflows/gke-deploy.yml` and `ops/manage_servers.py` now reference the tiered requirements files.

### Bug fixes

#### Pre-Release Security Audit (2026-04-03)

- **Error detail leaking**: Sanitized 40 `HTTPException(500, detail=str(e))` calls across 10 API route files (`routes_scheduler`, `routes_skills`, `routes_memory`, `routes_custom_skills`, `routes_hub`, `routes_skill_integrations`, `routes_google`, `routes_telegram_instances`, `routes_provider_instances`, `routes_knowledge_base`). All now return generic context-appropriate messages instead of raw Python exception strings. Added missing `logger.error()` calls for 3 Telegram instance routes.
- **Dev/debug scripts in git**: Removed 13 internal development scripts from git tracking (`check_*.py`, `debug_*.py`, `fix_shell_wait.py`, `e2e_test_results.txt`). Added gitignore patterns to prevent re-tracking.
- **Inconsistent tenant isolation**: Standardized `list_runs` endpoint in `routes_flows.py` to use `filter_by_tenant()` instead of manual `tenant_id` check, matching all other flow endpoints.

#### Installer Refactor & Security Hardening (2026-04-03)

- **(BUG-269) XSS token theft via localStorage**: SEC-005 Phase 3 — removed all `localStorage` JWT token storage from the frontend. Auth now relies entirely on the httpOnly `tsushin_session` cookie. Backend WebSocket handlers (playground + watcher) updated to authenticate from cookie without requiring first-message token. Setup wizard and SSO exchange endpoints now set the httpOnly cookie. All auth fetch calls include `credentials: 'include'`.
- **(BUG-270) CORS origin wrong for remote HTTP installs**: Installer set `TSN_CORS_ORIGINS` to `http://localhost:3030` for remote installs, blocking all API calls from the actual IP. Fixed by using the public host for `frontend_url` and CORS origins.
- **(BUG-271) docker-compose v1 ContainerConfig error**: BuildKit images lack the `ContainerConfig` key that docker-compose v1 expects on container recreate. Installer now sets `DOCKER_BUILDKIT=0` for both `run_docker_compose()` and `build_additional_images()` when using docker-compose v1.
- **(BUG-272) Setup wizard loses API key if "Add" not clicked**: Users who typed an API key but clicked "Complete Setup" without clicking "Add" lost the key. `handleSubmit` now auto-includes any uncommitted key from the text field.

#### Installer Redesign (2026-04-03)

- **Infrastructure-only installer**: Removed all 7 API key prompts and 8 tenant/admin credential prompts from the installer. User/org creation and AI provider configuration are now handled exclusively by the `/setup` UI wizard after install.
- **`--defaults` mode simplified**: No longer generates random passwords or bootstraps users. Just sets up `.env`, Docker containers, and SSL — then directs user to `/setup`.
- **argparse with `--help`**: Added proper CLI flags: `--defaults`, `--http`, `--domain`, `--email`, `--port`, `--frontend-port` with validation and usage examples.
- **Let's Encrypt via Caddy**: SSL is handled by Caddy with built-in ACME support (no certbot needed). `--domain` flag requires `--email` for Let's Encrypt notifications.

#### Async Embeddings Migration (2026-04-02)

- **Event loop blocking**: Migrated all 12 sync `embed_text()` / `embed_batch_chunked()` call sites to async variants (`embed_text_async()`, `embed_batch_chunked_async()`) using `asyncio.to_thread()`. Health checks and WebSocket connections no longer stall during embedding-heavy agent processing.
- **SentenceTransformer singleton consolidation**: Removed 4 services that bypassed the shared `EmbeddingService` singleton and instantiated their own `SentenceTransformer` model (combined_knowledge_service, project_memory_service, playground_document_service, project_service). All embedding calls now route through `get_shared_embedding_service()`.
- **Thread-safe singleton**: Added double-checked locking with `threading.Lock` to `get_shared_embedding_service()` to prevent race conditions from concurrent `asyncio.to_thread()` calls.
- **Dockerfile workers**: Reverted `--workers 2` to `--workers 1` — async embeddings eliminate the need for a second worker, halving model memory usage.

#### Fresh Install QA (2026-04-02)

**Install Flow (3 fixes):**
- **(BUG-248) /setup page**: Created frontend setup wizard at `/setup` for first-run account creation. Login page auto-redirects to `/setup` when database is empty. Added `GET /api/auth/setup-status` endpoint.
- **(BUG-249) --defaults auto-bootstrap**: `python3 install.py --defaults` now creates tenant + admin with random credentials and displays them post-install.
- **(BUG-250) .local email validation**: Patched `email-validator` to allow `.local` TLD for dev environments.

**Installer Security (1 fix):**
- **(BUG-256) HTTPS default**: Self-signed HTTPS is now the default for localhost installs, Let's Encrypt for remote. HTTP requires explicit opt-in with plaintext credential warning. `TSN_CORS_ORIGINS` and `TSN_SSL_MODE` auto-configured in `.env`.

**UI/UX (6 fixes):**
- **(BUG-251) Tenant display name**: Header shows tenant name instead of raw ID slug (`tenant_2026...`).
- **(BUG-252) Markdown rendering**: Playground renders markdown in agent responses (bold, bullets, code blocks) via ReactMarkdown.
- **(BUG-253) Thread titles**: Smarter auto-naming strips greetings and extracts topic instead of truncating first 50 chars.
- **(BUG-254) Console noise**: Expected 401 errors downgraded to `console.debug`, verbose playground logs gated behind `NODE_ENV`.
- **(BUG-255) Tour highlighting**: Onboarding tour now highlights target UI elements with pulsing teal outline.
- **(BUG-257) Tour content**: Updated with current AI providers, channel setup guidance, Sentinel security, and API v1 access.

#### Google SSO Enrollment Fixes (2026-04-01)

- **(BUG-246) Soft delete locks SSO re-enrollment**: Team member removal now uses hard delete instead of soft delete. Soft delete left `google_id` linked to a deactivated record, permanently blocking re-enrollment. SSO lookups now also filter `deleted_at` as defense-in-depth. Comprehensive FK cleanup across 12+ tables on user removal.
- **(BUG-247) Avatar URL exceeds column length**: Google profile avatar URLs can exceed 800 characters. `avatar_url` column changed from `VARCHAR(500)` to `TEXT`. Generic SSO error handler now surfaces actual error detail instead of opaque "Authentication failed".

### Changed

#### Google SSO Auto-Provisioning UI (2026-04-01)

- Auto-provision defaults to **off** (pre-registration required). Users must be added via Team > Invite before signing in with Google SSO.
- Added contextual disclaimer in Settings > Security explaining enrollment behavior for both modes (auto-provision on vs off).
- Updated "How Google Sign-In Works" info section with complete enrollment flow documentation.

#### Critical/High Bug Remediation Sprint (2026-03-31)

**Security (5 fixes):**
- **(SEC-005) httpOnly Cookie Auth — Phase 1 + Phase 2**: Phase 1: Backend sets `tsushin_session` httpOnly cookie on login/signup/invite-accept. `auth_dependencies.py` checks cookie first, Bearer token as fallback. WebSocket accepts cookie auth from upgrade request. Logout endpoint clears cookie. Phase 2: Migrated all 19 frontend files (~84 fetch calls) from manual `localStorage.getItem('tsushin_auth_token')` to centralized `authenticatedFetch()`. Removed all `getAuthHeaders()` helpers. Token only read in 3 intentional locations (AuthContext lifecycle, authenticatedFetch fallback, WebSocket auth).
- **(SEC-010) API Client JWT Revocation on Secret Rotation**: Added `secret_rotated_at` column to `ApiClient`. JWT claim includes rotation timestamp. `_resolve_api_client_jwt` rejects tokens issued before last rotation. DB migration included.
- **(SEC-019) File Upload Magic Bytes Validation**: PDF and DOCX uploads validated via `filetype` library magic bytes check. ZIP bomb protection for DOCX with 100MB uncompressed size limit. Extension-only validation for text formats (txt/csv/json).
- **(LOG-020) Sentinel Configurable Fail Behavior**: Sentinel pre-check exception handling now supports `sentinel_fail_behavior` config field (`"open"` | `"closed"`). Fail-closed blocks message and logs structured error instead of silently allowing.
- **CORS Hardening**: Replaced wildcard `"*"` with origin reflection (`allow_origin_regex=".*"`) for `credentials: true` support. Restricted `allow_methods` and `allow_headers` from `"*"` to explicit lists. Exception handlers updated to match.

**Multi-Tenancy Isolation (6 fixes):**
- **(LOG-002) Cross-Tenant Subflow Execution**: `SubflowStepHandler` validates target flow belongs to same tenant before execution. `run_flow()` accepts optional `tenant_id` filter.
- **(LOG-003) Cross-Tenant Memory Query Leakage**: `_get_thread_messages()` in `conversation_knowledge_service.py` now scopes Memory queries by agent_ids belonging to the caller's tenant.
- **(LOG-004) Cross-Tenant Document Chunk IDOR**: `get_project_knowledge_chunks()` verifies `doc_id` belongs to the verified `project_id` before returning chunks.
- **(LOG-012) ContactAgentMapping Tenant Isolation**: Added `tenant_id` column with DB migration + backfill from agent's tenant. Router contact lookup scoped by MCP instance's tenant.
- **(LOG-014) Cross-Tenant Agent-to-Project Assignment**: `update_project_agents()` validates each `agent_id` belongs to the caller's tenant before creating `AgentProjectAccess` records.
- **(LOG-018) Anonymous Contact Hash Fallback**: Replaced `hash(sender) % 1000000` phantom ID fallback with re-raise. Callers use sender-string-based memory key.

**Flow Engine (3 fixes):**
- **(LOG-007) Stale Flow Run Recovery**: `run_flow()` resets "running" flows older than 1 hour to "failed" on startup. `on_failure=continue` with failed steps now reports `"completed_with_errors"` instead of `"completed"`.
- **(LOG-010) Step Idempotency TOCTOU**: SELECT FOR UPDATE with `skip_locked=True` + IntegrityError handling prevents concurrent step execution race.
- **(LOG-011) Flow Cancellation**: `db.refresh(flow_run)` between steps detects external cancellation and breaks the execution loop.

**Logic (2 fixes):**
- **(LOG-006) A2A Depth Limit Enforcement**: `SkillManager.execute_tool_call()` propagates `comm_depth` and `comm_parent_session_id` from message metadata into skill config for chained delegation depth tracking.
- **Already fixed (validated):** SEC-001 (admin password reset JWT invalidation), SEC-008 (update_client privilege escalation check), SEC-016 (shell queue_command tenant policies).

---

## [0.6.0-rc1] - 2026-03-30

### Added

#### AI Providers
- **Groq LLM Provider**: Ultra-fast LLM inference via OpenAI-compatible API. Models: Llama 3.3 70B Versatile, Llama 3.1 8B Instant, Mixtral 8x7B 32K, Gemma2 9B IT. Full streaming support.
- **Grok (xAI) LLM Provider**: xAI's Grok models via OpenAI-compatible API. Models: Grok 3, Grok 3 Mini, Grok 2. Full streaming support.
- **DeepSeek LLM Provider**: Full backend + Hub integration. Models: DeepSeek-V3, DeepSeek-R1 (reasoning). OpenAI-compatible endpoint.
- **ElevenLabs TTS (complete implementation)**: Premium voice AI synthesis. Dynamic voice list from API, 29+ languages, emotional tone control, character-based usage tracking, health check via subscription endpoint.
- **OpenAI-Compatible URL Rebase & Multi-Instance Providers**: Configure custom OpenAI-compatible base URLs for LiteLLM, vLLM, LocalAI, Azure OpenAI, or any proxy. Multiple named instances of the same vendor with independent API keys and model lists. Agent-level instance selection via dropdown.
- **Settings > Integrations UI**: Branded provider cards for Groq, Grok, ElevenLabs, and DeepSeek. Configure/Edit/Remove modals, Test Connection with inline results, encryption at rest, multi-tenancy key isolation.
- **Test Connection Endpoints**: `POST /api/integrations/{service}/test` for all providers. Provider-specific validation (ElevenLabs via `/v1/user`, Groq/Grok via minimal test message).
- **Hub AI Providers UX Cleanup**: ElevenLabs added to vendor lists and instance modal. Grok/Groq now have distinct icons. API key precedence indicator (legacy vs instance key).
- **Vertex AI Provider (Phase 1+2)**: Google Cloud Model Garden integration. Phase 1: Gemini models via Vertex AI endpoint (us-east5 region). Phase 2: Claude models via Google Cloud (Anthropic-on-Vertex). Service account auth with Application Default Credentials. Region-aware endpoint routing. Full streaming support. Hub integration with Vertex AI provider card.
- **Hub Local Services Management**: Kokoro TTS start/stop/status controls via Docker API. Ollama auto-create/enable/disable toggle, inline URL editing, test connection, model refresh. Ollama removed from Provider Instances vendor list (only in Local Services).

#### Security
- **Sentinel Security Profiles**: Granular security profiles with custom configuration per protection rule. Hierarchical inheritance at tenant → agent → skill level — lower-level overrides inherit from higher. Full CRUD UI in Settings > Sentinel > Profiles (create/edit/clone/delete). Tenant-level assignment in General tab, agent-level in Agents > Security modal, skill-level via SkillSecurityPanel. Hierarchy visualization tab.
- **MemGuard — Memory Poisoning Detection**: Fifth Sentinel detection type (`memory_poisoning`). Layer A: pre-storage regex pattern matching (EN + PT) blocks poisoned messages. Layer B: fact validation gate blocks credential injection, command patterns, and contradictions before SemanticKnowledge writes. Zero-migration integration via `detection_overrides` inheritance in Security Profiles. Dedicated MemGuard tab in Sentinel settings with branded UI.
- **Custom Skill Scanning — Dedicated Sentinel Profile**: Context-aware LLM prompt that understands skill instructions modify behavior by design. "Custom Skill Scanning" card in Settings > Sentinel > General with profile picker. Scan detail popover showing rejection reason, detection type, threat score, and profile. Gray "unknown" badge for unscanned skills. Auto-open popover after re-scan. Rejected skills cannot be used by agents until re-scanned clean.
- **SSRF Protection for Browser Automation**: Comprehensive Server-Side Request Forgery protection for the browser automation skill. New `browser_ssrf` Sentinel detection type with LLM-based intent analysis at 3 aggressiveness levels. DNS-resolution-based URL validation blocks private IPs, cloud metadata, Docker/Kubernetes internals, CGNAT ranges, and loopback addresses. Per-tenant URL allowlist/blocklist in BrowserConfig. Sentinel `analyze_browser_url()` pre-navigation check integrated into both legacy and MCP tool paths. Browser SSRF toggle in Sentinel settings UI (critical severity, enabled by default). Automatic DB migration for existing installations.
- **API v1 Security Hardening & OpenAPI Documentation**: OAuth token endpoint rate limiting (10 req/min per IP). HTML sanitization validators on Persona, Contact, and Agent fields (stored XSS prevention). Phone number E.164 validation. Shared v1 schemas module with 20+ reusable Pydantic models. `response_model=` wired on all 40 v1 endpoints. Error documentation (401/403/404/422/429) on all endpoints. `X-API-Version: v1` response header. Static `docs/openapi.json` export (435 paths, 413 schemas).
- **Slash Command Hardening**: sender_key spoofing fix (always derive from JWT), email cache cross-user isolation (keyed by agent_id + sender_key), agent-level sandboxed tool authorization check, pattern cache language scoping, permission_required field enforcement warning.

#### Custom Skills & MCP Integration
- **Custom Skills — Phase 1: Instruction Skills**: Tenant-authored instruction-based skills that inject domain knowledge and behavioral rules into agent system prompts. DB migration with `custom_skill`, `custom_skill_version`, `agent_custom_skill`, `custom_skill_execution` tables. `CustomSkillAdapter(BaseSkill)` for instruction injection. CRUD API with full tenant isolation. Full Settings > Custom Skills UI (library list, skill cards, form modal with Definition/Trigger/Instructions sections). New RBAC permissions: `skills.custom.create/read/execute/delete`.
- **Custom Skills — Phase 2: Script Skills + Container Hardening**: Tenant-authored Python/Bash/Node.js scripts executed inside per-tenant toolbox containers. Container security hardening: `no-new-privileges:true`, `cap_drop=["ALL"]`, `pids_limit=256`. `CustomSkillDeployService` with SHA-256 hash checking and auto-redeploy. Static network import scan. `/deploy`, `/scan`, `/test` endpoints. Script editor UI (language selector, parameters builder, timeout setting).
- **Custom Skills — Phase 3: Agent Assignment + Flow Integration**: Wire custom skills into agent configuration and flow builder. Agent custom skill assignment endpoints. `AssignCustomSkillModal`, `SkillConfigForm` (schema-driven form renderer). Custom Skills section in agent skills manager. Custom skills in flow builder skill picker under "Custom Skills" separator.
- **Custom Skills — Phase 4: MCP Server Integration**: External MCP servers as tool providers. Transport abstraction: `SSETransport` (generalized from AsanaMCPClient), `StreamableHTTPTransport`. `MCPConnectionManager` singleton with per-tenant connection pools (limit 10), background health checks (60s), exponential backoff reconnect. `MCPDispatcher` routing by namespaced tool name (`{server}__{tool}`). `MCPSentinelGate` with trust-level-based I/O scanning. Tool description pre-storage Sentinel scan. Hub MCP Servers tab with server cards, tool browser, log viewer.
- **Custom Skills — Phase 5: Stdio Transport + Network Hardening**: Stdio MCP servers running inside tenant containers. `StdioTransport` with JSON-RPC 2.0. Binary allowlist (uvx, npx, node) validated at config time. Path traversal rejection. `idle_timeout_sec` watchdog (300s). Process resource limits: `ulimit -v 1048576 -t 60`. DNS egress policy (explicit 8.8.8.8/8.8.4.4). MCP Server Periodic Health Check Service with 3-min interval and circuit breaker sync.
- **MCP Server → Custom Skill UI Wiring**: "MCP Server" as a third skill type in Custom Skills modal. MCP Server dropdown from Hub-configured servers, tool selector with discovered tools, auto-fill from tool metadata. Hub MCP Servers "Create Skill" shortcut button.

#### Channels
- **Channel Abstraction Layer**: Formal channel abstraction layer decoupling agent logic from transport-specific code. `ChannelAdapter` ABC, `ChannelRegistry`, `InboundMessage`/`SendResult`/`HealthResult` types. `WhatsAppChannelAdapter`, `TelegramChannelAdapter`, `PlaygroundChannelAdapter`. Router `_send_message()` dispatches via registry.
- **Slack Channel Integration**: Full Slack workspace integration via Socket Mode (no public URL required). Bot Token + App Token auth stored Fernet-encrypted per tenant. Message threading, rich Block Kit formatting. DM policy (open/allowlist/disabled), channel allowlist. Reconnection with exponential backoff (2s → 30s max, 12 attempts). Non-recoverable error detection (token_revoked, invalid_auth). Hub Channels section: Slack card with connect/disconnect and workspace name.
- **Discord Channel Integration**: Full Discord bot integration via Gateway API v10. Bot token Fernet-encrypted per tenant. Guild/channel allowlists, DM policies, thread support, embed support, slash command bridge (`/tsushin <command>`), emergency stop. Message deduplication TTL cache. Gateway supervisor for non-recoverable errors (4014, token revoked). Hub Channels section: Discord card with connect/disconnect and bot name.
- **Telegram Channel for Flow Steps**: Telegram as available channel for flow notification/message steps. `_resolve_telegram_sender()` helper. chat_id recipient validation. Multi-recipient support in MessageStepHandler. Removed "Coming Soon" badge in flow channel options.
- **Multi-Channel Contact Identity — Slack & Discord**: Contact resolution across Slack and Discord via `ContactChannelMapping`. `ensure_contact_from_slack()` and `ensure_contact_from_discord()` auto-create contacts from messages. Channel badges in contact list (Slack purple, Discord indigo). "Channel Identities" management section in edit modal — view/add/remove channel mappings for all 6 channel types.
- **Channel Health Monitor with Circuit Breakers**: Unified health monitoring for all channels. 30s background probe loop. `CircuitBreaker` state machine: CLOSED → OPEN → HALF_OPEN. WhatsApp, Telegram, Slack, Discord probes. State transition handler: DB persist, audit event, WebSocket emit, Prometheus metric, alert dispatch. Webhook alert system with per-instance cooldown. 4 new Prometheus metrics. 7 REST API endpoints for health status, history, manual probe, circuit reset, and alert config.

#### Messaging & Queuing
- **Message Queuing System**: Async message queue for all channels (WhatsApp, Telegram, Playground). `MessageQueue` table with SELECT FOR UPDATE SKIP LOCKED for concurrent safety. Dead-letter queue after 3 retries. Ordered delivery guarantees. Playground async/sync modes (`?sync=true`). Frontend WebSocket queue events. QueueWorker asyncio background processor.
- **WebSocket Streaming**: Token-by-token response streaming via WebSocket. `/ws/playground` endpoint with secure first-message auth. Animated typing indicators via `StreamingMessage` component. `PlaygroundWebSocket` client with auto-reconnect and exponential backoff. Heartbeat ping/pong (30s intervals). Queue event integration.

#### Browser Automation Enhancements
- **Session Persistence**: `BrowserSessionManager` keyed by `(tenant_id, agent_id, sender_key)`. Reuse existing browser/page across conversation turns. Idle timeout (300s configurable). Background cleanup task. `session_ttl_seconds` column added to browser_automation_integration.
- **Rich Action Set**: 19 total actions including: scroll (page/element/to_element), select_option, hover, wait_for, go_back, go_forward, get_attribute, get_url, type (character-by-character with delay), open_tab, switch_tab, close_tab, list_tabs.
- **Multi-Tab Support**: Full browser tab lifecycle management. Tabs tracked per session. Max tabs configurable via BrowserConfig.
- **CDP Host Browser Mode**: Connect to Chrome running on the host machine via DevTools Protocol (`http://host.docker.internal:9222`). Allows agents to use authenticated browser sessions.
- **Structured Error Feedback**: `BrowserActionError` with `error_type` (element_not_found/timeout/navigation_failed/security_blocked), actionable `suggestion` per error type, current page URL and title in error context.

#### Platform & Infrastructure
- **Public API v1**: Full programmatic REST API for external applications. OAuth2 Client Credentials (`POST /api/v1/oauth/token`) and Direct API Key (`X-API-Key` header). 40 endpoints across 7 route files: Agent CRUD, Chat (sync + async + SSE), Thread management, resource listing (skills/tools/personas/security-profiles/tone-presets), profile assignment, Flows (13 endpoints), Hub (6 endpoints), Studio (3 endpoints). Per-client RPM rate limiting with `X-RateLimit-*` headers. Request audit log (`api_request_log` table). 5 API roles: api_agent_only, api_readonly, api_member, api_admin, api_owner. Settings > API Clients management page (create/rotate/revoke). Swagger UI at `/docs`. 44/44 E2E tests passing.
- **GKE Readiness — Cloud-Native Infrastructure**: `/api/readiness` endpoint for Kubernetes readiness gates. Prometheus `/metrics` endpoint (`http_requests_total`, `http_request_duration_seconds`, `tsn_service_info`). `TSN_LOG_FORMAT` toggle (text/JSON structured logging). `ContainerRuntime` abstraction with `DockerRuntime` (default) and full `K8sRuntime` (maps Docker ops to K8s Deployments/Services/exec API). `SecretProvider` abstraction with `EnvSecretProvider` and `GCPSecretProvider` (Secret Manager with TTL cache). Helm chart (`k8s/tsushin/`) with 16 templates. CI/CD pipeline for GKE (`gke-deploy.yml`, manual trigger). Network policies, HPA, managed TLS, WebSocket ingress support.
- **SSL Encryption During Installation**: Caddy reverse proxy with 3 SSL modes: Let's Encrypt (auto-enrollment), manual certificates, and self-signed (`tls internal`). `docker-compose.ssl.yml` override. Installer prompts for domain, SSL mode, certificate paths. `ProxyHeadersMiddleware` for real client IP. HTTP→HTTPS redirect (308). WSS auto-detection.
- **Audit Logs — Tenant-Scoped Event Capture**: `AuditEvent` PostgreSQL model with JSONB details, tenant isolation, composite indexes. 30+ event types via `TenantAuditActions` enum (auth, agents, flows, contacts, settings, security, api_clients, skills, mcp, team). `TenantAuditService` with export, stats, and per-tenant retention. Background retention worker (24h daemon, per-tenant configurable). Enhanced audit logs page: stats bar, 5-filter panel, CSV export, 30+ event icons, expandable detail rows, severity dots, click-to-filter.
- **Syslog Streaming for Audit Events**: RFC 5424 syslog forwarding via TCP, UDP, or TLS to external syslog servers. `TenantSyslogConfig` with Fernet-encrypted TLS certs. Per-tenant circuit breaker (5 failures → 60s cooldown). Event category filtering (10 categories). Syslog Forwarding card in Settings > Audit Logs with server config, TLS section, test connection.
- **PostgreSQL Migration**: Full migration from SQLite to PostgreSQL 16 as primary database. Alembic migrations, all queries updated for PostgreSQL compatibility, tone presets visibility and playground search fixed.
- **Flows server-side pagination**: Flows list page now uses server-side pagination to efficiently handle large numbers of flows.

#### Agent Studio & UX
- **Agent Studio — Visual Agent Builder**: React Flow canvas in Watcher for visual agent building. Palette panel with 7 profile categories: Persona, Channels, Skills, Sandboxed Tools, Security Profiles, Knowledge Base, Memory. Drag-and-drop with ghost images and category-colored group node glows. Avatars, expandable nodes, tree layout, inline config editing via slide-out panels. Batch builder endpoints. Remove attached items: hover-reveal X button, keyboard Delete, warning toast for last channel removal.
- **Active Chain Edge Glow (Graph View)**: Edges connecting active nodes glow during real-time processing. Edge glow color matches target node type: cyan (channel→agent), blue (agent chain), teal (skill), violet (KB). Pulse animation synchronized with node glow. Fade-out coordinated with 3s post-processing fade.
- **Flow Step Variable Reference Panel**: Collapsible `{x} Variable Reference` panel below template textareas. 4 sections: Previous Steps (with type-specific output field chips), Helper Functions (11 helpers), Conditionals (if/else with operators), Flow Context (global variables). `TemplateTextarea` wrapper with cursor-position-aware variable insertion. `CursorSafeInput`/`CursorSafeTextarea` components prevent cursor position loss on re-renders across 22+ text fields.
- **Smart UX Features**: Auto-save drafts (debounced localStorage per thread). Smart paste auto-detects JSON and code blocks and wraps them in markdown fences. `useDraftSave` hook and `formatPastedContent` utility.
- **WhatsApp Group Slash Commands via Agent Mention**: Trigger slash commands in WhatsApp groups by mentioning the agent: `@agentname /tool nmap quick_scan target=scanme.nmap.org`. All existing slash command types supported.
- **Granular Slash Command Permissions per Contact**: Per-contact slash command access control. `slash_commands_enabled` column on Contact, `slash_commands_default_policy` on Tenant. Hierarchical resolution: tenant default → per-contact override. 3-state dropdown UI in Contacts page. Applies across all channels.
- **Agent-to-Agent Communication**: Agents within the same tenant can communicate directly. 3 actions: `ask` (sync Q&A), `list_agents` (discover capabilities), `delegate` (full handoff with context). Permission management (per-pair grants), rate limiting (per-pair + global), loop detection (parent_session_id chain), depth limiting (default 3). Sentinel `agent_escalation` detection type. "Communication" tab in Agent Studio with session log, permissions CRUD, statistics dashboard.
- **Billing Structure Audit & Cost Tracking**: Token tracking propagated to all 13 previously-missing AIClient call sites across skills and services (FlowsSkill, SchedulerSkill, SearchSkill, BrowserAutomationSkill, FlightSearchSkill, SchedulerService, FactExtractor, ConversationKnowledgeService, AISummaryService, SentinelService). OpenAI streaming uses `stream_options={"include_usage": True}` for actual token counts. Gemini streaming captures `usage_metadata`. Fixed Gemini token estimation.
- **Permission Matrix Update**: All 170+ endpoints audited. Scheduler permissions seeded (entire scheduler was returning 403). Frontend `billing.manage` → `billing.write` mismatch fixed. Sentinel profile read endpoints secured. Knowledge base RBAC guards added. Slack/Discord integration permissions seeded.

#### Memory
- **Temporal Memory Decay with MMR Reranking**: Exponential decay (`e^(-λ × days)`) applied at retrieval time — older memories receive lower relevance scores. MMR reranking for result diversity. Auto-archive facts below configurable threshold. Freshness labels: fresh/fading/stale/archived. Applied to Layer 2 (Episodic/ChromaDB), Layer 3 (Semantic Knowledge), and Layer 4 (Shared Pool). `memory_decay_enabled`, `memory_decay_lambda`, `memory_decay_archive_threshold`, `memory_decay_mmr_lambda` fields on Agent. `last_accessed_at` tracking on SemanticKnowledge and SharedMemory.

#### Image Generation
- **Image generation for Playground channel**: Generated images from the `generate_image` tool are rendered inline in Playground chat messages. Images can be clicked to open in a new tab.
- **Image generation for Telegram channel**: Generated images sent as photos via the Telegram Bot API with optional captions.
- **Image serving endpoint**: New `GET /api/playground/images/{image_id}` endpoint serves generated images to the Playground frontend.
- **WebSocket image delivery**: Image URLs propagated through the WebSocket streaming pipeline for real-time image display.

#### Other
- `ROADMAP.md` for tracking planned features and releases.
- `CHANGELOG.md` for documenting changes across releases.

---

### Changed
- **Legacy keyword triggering deprecated**: All hybrid skills are now tool-only execution mode. Web scraping skill deprecated and replaced by browser_automation skill.
- **Weather skill removed**: Deprecated and fully removed from backend, frontend, Hub, and README.
- **iOS-style toggle switches**: All enable/disable toggles across the entire platform unified to a consistent iOS-style `ToggleSwitch` component.
- **Agent list performance**: N+1 API calls reduced from 92 requests (~2 per agent for skills) to ~6 requests for a 46-agent list. Agent cards now use `skills_count` from the list response.
- **Sandboxed Tools config moved to Skills modal**: Dedicated Sandboxed Tools tab removed; config integrated into the Skills modal for a cleaner UI.
- **Skills UI overhaul**: Separate sections for built-in and custom skills, emoji icons removed, "Add Skill" pattern added.
- **Design system migration**: Auth pages and Agent Detail page migrated to Tsushin design system tokens. Login page updated with Tsushin kitsune banner.
- **Watcher Threats by Type**: Compacted from separate cards to inline pill badges for a denser, more scannable layout.
- **Sentinel default profile**: System default changed from Moderate (block) to Permissive (detect_only) to reduce false positives on fresh installs.
- **ImageSkill default config**: `enabled_channels` now includes `"telegram"` in addition to `"whatsapp"` and `"playground"`.
- **TelegramSender**: Added `send_photo()` method for sending images via the Telegram Bot API.
- **PlaygroundService**: Skill results and agent service results now propagate `media_paths` as cached `image_url` values in both regular and streaming response paths.
- **PlaygroundWebSocketService**: `done` events now include `image_url` field when images are generated.
- **PlaygroundChatResponse**: Added `image_url` field to the API response model.
- **PlaygroundMessage**: Added `image_url` field to the message model (both backend and frontend).
- **ExpertMode component**: Message bubbles now render generated images with responsive sizing and click-to-open behavior.

---

### Fixed

#### UI/UX QA Audit (BUG-121 to BUG-130)
- **(BUG-121) Onboarding tour auto-navigates users away**: Removed race condition; tour only activates via explicit `startTour()` call.
- **(BUG-122) Tour appears on unauthenticated pages**: Added `usePathname()` guard — returns null on `/auth/*` routes.
- **(BUG-123) Agent list makes 92 API calls for 46 agents (N+1)**: Removed per-agent skills fetch; use `skills_count` from list response. Reduced to ~6 requests.
- **(BUG-124) System Admin pages fail with mixed content on HTTPS**: Browser-side `API_URL` changed to empty string (relative paths via proxy). Added trailing slashes to admin endpoints to prevent FastAPI 307 redirects.
- **(BUG-125) Sandboxed Tools "Access Denied" for Owner role**: Created `tools.read` permission, assigned to all roles.
- **(BUG-126) No "System" navigation link for Global Admin users**: Added conditional System nav item visible only when `isGlobalAdmin`.
- **(BUG-127) Messages sender column shows "-" for all rows**: Fixed sender column display logic.
- **(BUG-128) Footer shows copyright year "2025" instead of "2026"**: Updated copyright year.
- **(BUG-129) Agent list stale refs cause navigation to wrong pages**: Fixed stale reference issues in agent list.
- **(BUG-130) Organization usage shows 720% over plan limit with no warning**: Added over-limit warning display.

#### Security Audit (BUG-131 to BUG-145)
- **(BUG-131) Password reset token exposed in API response body**: Removed `reset_token` from response model. Uniform message regardless of email existence.
- **(BUG-132) Path traversal via unsanitized tenant_id in workspace path construction**: Added regex validation for tenant_id; `Path.resolve()` + bounds check applied.
- **(BUG-133) Gemini prompt injection via merged system+user prompt**: Fixed by using `system_instruction` parameter in `GenerativeModel` constructor at the API protocol level.
- **(BUG-134) JWT tokens not invalidated after password change**: Added `password_changed_at` claim comparison on every authenticated request.
- **(BUG-135) Docker socket mounted in backend container (container escape risk)**: Documented `docker-socket-proxy` requirement for production.
- **(BUG-136) SSRF bypass via HTTP redirect in webhook handler**: Replaced custom check with `validate_url()` from `ssrf_validator`. Added `follow_redirects=False`.
- **(BUG-137) SSO `redirect_after` allows open redirect**: Added validation that `redirect_after` is a relative path only.
- **(BUG-138) `require_global_admin` dependency doesn't return user object**: Added `return current_user`; updated call sites.
- **(BUG-139) Container `workdir` parameter accepts arbitrary paths**: Added regex pattern constraint restricting to paths under `/workspace`.
- **(BUG-140 to BUG-143) Four implementation review bugs**: Local get_current_user bypass, and related auth/CORS issues fixed.
- **(BUG-144) React hooks violation**: Fixed conditional hook usage in playground component.
- **(BUG-145) CORS gap**: Fixed missing CORS headers on specific endpoints.

#### Slash Command Hardening (BUG-147 to BUG-149)
- **(BUG-147) sender_key spoofing on /api/commands/execute**: Always derive sender_key from authenticated JWT. Never accept from request body.
- **(BUG-148) Email cache cross-user data leakage**: Cache key changed from `agent_id` to `(agent_id, sender_key)` tuple.
- **(BUG-149) Agent-level sandboxed tool authorization bypass**: Added `AgentSandboxedTool` authorization check before execution.

#### RBAC Permission Matrix Audit (BUG-150 to BUG-153)
- **(BUG-150) Scheduler permissions not seeded — entire scheduler API returns 403**: Added 4 scheduler permissions to `seed_rbac_defaults` with proper role assignments.
- **(BUG-151) Billing page inaccessible — billing.manage vs billing.write mismatch**: Frontend permission check corrected to `billing.write`.
- **(BUG-152) Sentinel profile read endpoints missing RBAC**: Added `org.settings.read` guard to 5 read endpoints.
- **(BUG-153) Knowledge base routes missing RBAC**: Added `knowledge.read/write/delete` guards to all 8 endpoints.

#### Channel Abstraction Code Review (BUG-154 to BUG-155)
- **(BUG-154) WhatsApp channel adapter behavioral regression**: Mirrored original router logic — allow sends for None/default URL, check only `connected` flag.
- **(BUG-155) Telegram adapter health_check crash on non-dict response**: Added `isinstance(me, dict)` guard with `getattr` fallback.

#### v0.6.0 Perfection Team Audit — 45 Bugs (BUG-156 to BUG-200)

**Critical (11):**
- **(BUG-156) Custom skill script_entrypoint shell injection**: Added regex validation on save; `shlex.quote()` at execution.
- **(BUG-157) TSUSHIN_INPUT env var unquoted shell injection**: Applied `shlex.quote()` around the JSON string.
- **(BUG-158) stdio_binary allowlist bypass via PUT update endpoint**: Added same allowlist + path traversal + metacharacter checks from POST to PUT endpoint.
- **(BUG-159) Anthropic AsyncAnthropic coroutine passed to asyncio.to_thread**: Replaced `asyncio.to_thread(...)` with `await self.client.messages.create(...)`.
- **(BUG-160) Provider instance API key encryption identifier mismatch**: Unified encryption identifiers; routes now delegate to `ProviderInstanceService._encrypt_key/_decrypt_key`.
- **(BUG-161) Missing permission on /sentinel/cleanup-poisoned-memory**: Added `require_permission("org.settings.write")`.
- **(BUG-162) Unauthenticated /metrics endpoint exposes telemetry**: Added IP allowlist / bearer token check to Prometheus endpoint.
- **(BUG-163) thread_id not validated for tenant ownership in API v1 chat**: Added thread ownership validation before passing to service layer.
- **(BUG-164) Discord media upload sends invalid JSON via repr()**: Replaced `repr()` with `json.dumps({"content": text or ""})`.
- **(BUG-165) Discord media upload file handle never closed**: Added context manager `with open(media_path, "rb") as f:`.
- **(BUG-166) WebSocket onMessageComplete stale closure**: Changed to read from `activeThreadIdRef.current`; functional `setMessages(prev => ...)`.

**High (21):**
- **(BUG-167) Cross-tenant SentinelProfile access via user-controlled ID**: Added `(is_system == True) | (tenant_id == self.tenant_id)` filter.
- **(BUG-168) OpenRouter discover-models SSRF — no URL validation**: Added `validate_url(base_url)` before HTTP call.
- **(BUG-169) SlashCommandService._pattern_cache never invalidated**: Added TTL and invalidation on command write operations.
- **(BUG-170) NameError in Ollama SSRF rejection path**: Fixed bare `logger` reference to `self.logger`.
- **(BUG-171) BrowserAutomationSkill token tracker attribute mismatch**: Fixed `self._token_tracker` → `self.token_tracker`.
- **(BUG-172) AgentCustomSkill assignment update missing tenant isolation**: Added `CustomSkill.tenant_id == ctx.tenant_id` filter; return 404 if skill gone.
- **(BUG-173) StdioTransport.list_tools() always returns empty list**: Implemented JSON-RPC `tools/list` via stdin.
- **(BUG-174) MCPDiscoveredTool listing missing tenant_id filter**: Added `.filter(MCPDiscoveredTool.tenant_id == ctx.tenant_id)`.
- **(BUG-175) Slack WebClient blocking I/O in async methods**: Replaced with `AsyncWebClient`.
- **(BUG-176) Channel alert cooldown key missing tenant_id**: Added `tenant_id` to key: `(tenant_id, channel_type, instance_id)`.
- **(BUG-177) Phase 21 @agent /command uses wrong tenant's permission policy**: Added `agent.tenant_id == self._router_tenant_id` validation.
- **(BUG-178) WhatsApp adapter blocking httpx.get() in async send_message**: Replaced with `httpx.AsyncClient` with `await`.
- **(BUG-179) Agent comm skill always passes depth=0 — depth limit ineffective**: Fixed `depth` and `parent_session_id` forwarding from calling context.
- **(BUG-180) API v1 sender_key computed but never passed to service**: Passed `sender_key` to `send_message()` and `process_message_streaming()`.
- **(BUG-181) API v1 list_agents loads all agents into memory**: Pushed search filter to DB `ilike`, applied `offset`/`limit` in SQL.
- **(BUG-182) HSTS header missing from all Caddyfile SSL modes**: Added `Strict-Transport-Security` header to all SSL mode templates.
- **(BUG-183) Syslog TLS temp file descriptors leak**: Added `os.close(cert_fd)` and `os.close(key_fd)` to `finally` block.
- **(BUG-184) Flow step agent_id/persona_id not validated for tenant isolation**: Added tenant ownership check on `agent_id`/`persona_id` in flow step create/update.
- **(BUG-185) Playground fetchAvailableTools/Agents hardcoded HTTP URL**: Replaced raw `fetch()` calls with `api.*` methods from `client.ts`.
- **(BUG-186) Dead API_URL constant in contacts page with unsafe fallback**: Removed unused `API_URL` constant.
- **(BUG-187) Agent Studio updateNodeConfig doesn't set isDirty**: Added `next.isDirty = true` in all three node type branches.

**Medium (13):**
- **(BUG-188) system_prompt/keywords missing HTML sanitization in API v1**: Added `@field_validator("system_prompt")` with `strip_html_tags`.
- **(BUG-189) MemGuard warn_only mode doesn't send threat notification**: Added `send_threat_notification` call analogous to Sentinel's warned path.
- **(BUG-190) _scan_instructions silently returns clean on any exception**: Changed to return `scan_status='pending'` on LLM outage.
- **(BUG-191) Grok test model grok-3-mini not in PROVIDER_MODELS**: Updated test model to `grok-3`.
- **(BUG-192) validate-url endpoint rejects valid private IPs for local providers**: Consistent private IP handling with create/update endpoints.
- **(BUG-193) Custom skill deploy service entrypoint path injection**: Applied same validation as BUG-156 fix.
- **(BUG-194) Custom skill assignment update crashes on deleted skill**: Added None check; returns 404 if skill deleted.
- **(BUG-195) Network import scan only covers Python — misses bash/nodejs**: Added language-aware patterns for bash (`nc`, `ncat`, `/dev/tcp`) and Node.js (`require('http')`, etc.).
- **(BUG-196) Rate limiter _windows dict grows without bound**: Added periodic eviction of keys with empty lists after expiry pruning.
- **(BUG-197) Audit retention worker no per-tenant rollback on failure**: Wrapped each tenant purge in per-iteration `try/except` with `session.rollback()`.
- **(BUG-198) API client update allows role escalation without permission check**: Added `updater_permissions` parameter and scope subset check to `update_client`.
- **(BUG-199) Readiness probe _engine may be None on cold path**: Added null-check; returns 503 with engine-not-initialized message.
- **(BUG-200) CursorSafeTextarea in flows missing blur-flush**: Added `onValueChange(localValue)` in `onBlur` handler.

#### Other Fixes
- **Flow step cursor position loss and pending edits lost on save**: `CursorSafeInput`/`CursorSafeTextarea` components created with local state that only syncs from parent when not focused. Flush-on-unmount added so pending edits are not lost when modal closes.
- **Flow step Notification field mapping mismatch**: Fixed `content` vs `message_template` field read/write inconsistency.
- **Flow step backend schema missing fields**: `FlowStepConfig` Pydantic model now includes all fields for skill, summarization, and slash_command step types.
- **[object Object] error toast in Studio**: `handleApiError` now properly extracts Pydantic validation error arrays. All ~200 API methods in `client.ts` now use `handleApiError` for consistent error display.
- **Contact form "external" role 422 error**: Contact form now supports the `external` role.
- **Agent Studio builder save**: Persona and channel changes now persist correctly on builder save.
- **Playground NoneType len() error**: Resolved and improved error handling.
- **Google credential save crash**: Preserved `tenant_id` for admins to fix credential encryption failures.
- **Browser skill session manager wiring**: Session manager properly wired, structured errors fixed, value leak resolved.

#### VM Fresh Install Regression
- **RBAC seeding crash loop on first boot**: Added orphan-permissions guard at the start of `seed_rbac_defaults` — if permissions exist but no roles exist, permissions are cleared before re-seeding. Prevents `UniqueViolation` crash-restart loop on the first backend startup.
- **Global admin login returns 500 — NULL tenant_id in audit logging**: Added early-return guard in `log_tenant_event()` when `tenant_id is None`. Global admins have no tenant affiliation; their actions are handled by `GlobalAdminAuditService` separately.
- **(BUG-201) Installer leaves frontend unhealthy — docker-compose v1 health dependency race**: Installer now waits for backend to become healthy before starting the frontend container, working around docker-compose v1.29.2 `service_healthy` condition race on Ubuntu 24.04.
- **(BUG-202) Browser API calls use relative paths incompatible with HTTP-only installs**: Fixed `client.ts` API URL resolution so installations without Caddy proxy (SSL disabled) work correctly. Relative `/api/*` paths now resolve against the correct origin.

---

## [0.5.0-beta] - 2026-02-01

### Added
- Initial beta release
- Multi-agent architecture with intelligent routing
- Skills-as-Tools system with MCP compliance
- 16 built-in skills
- WhatsApp channel via MCP bridge
- Telegram channel integration
- Playground web interface with WebSocket streaming
- 4-layer memory system
- Knowledge base with document ingestion
- RBAC with multi-tenant support
- Watcher dashboard with analytics
- Sentinel security system
