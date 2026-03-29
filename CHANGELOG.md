# Changelog

All notable changes to Tsushin are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.0] - Unreleased

**Theme:** Security, Streaming, Providers, Public API & UX

### Added

#### Security Event Audit Trail Hardening
- Wired `SECURITY_SENTINEL_BLOCK` audit events on Sentinel prompt blocks (agent_service.py, router.py) and shell command blocks (shell_command_service.py)
- Wired `SECURITY_MEMGUARD_BLOCK` audit events on MemGuard memory poisoning blocks (router.py)
- Wired `SECURITY_SKILL_SCAN` audit events on all custom skill scan results — manual re-scan, auto-scan on create, auto-scan on update (routes_custom_skills.py)
- Wired `SECURITY_PERMISSION_DENIED` audit events on RBAC 403 failures (auth_dependencies.py)
- Added new `TenantAuditActions`: `SECURITY_MEMGUARD_BLOCK`, `SECURITY_SKILL_SCAN`
- All security audit events include severity field (warning for blocks/rejections, info for clean scans)
- Details include: detection_type, threat_score, reason, channel, agent_id, sender context

#### Dedicated Custom Skill Scan Profile (Sentinel)
- New "Custom Skill Scan" system Sentinel profile optimized for scanning admin-authored skill instructions
- Context-aware LLM analysis prompt (`SKILL_SCAN_UNIFIED_PROMPT`) that understands skill instructions are meant to modify agent behavior — won't flag "act as X" or "always recommend Y" as threats
- Disables `agent_takeover`, `poisoning`, and `memory_poisoning` detections (these ARE what skills do by design)
- Keeps `shell_malicious` (skills should never embed dangerous shell commands) and skill-aware `prompt_injection` (meta-attacks targeting the scanner)
- New `analyze_skill_instructions()` method in SentinelService with `_resolve_skill_scan_config()` auto-resolving to the dedicated system profile
- Post-classification detection filter: if LLM classifies as a disabled detection type, overrides to allowed (bug fix benefiting all analysis)
- Separate cache namespace (`unified_skill_scan`) prevents cross-contamination with standard message analysis
- Profile is customizable per tenant via Settings > Sentinel > Custom Skill Scanning section
- Rejected skills are enforced at runtime — `skill_manager.py` filters `scan_status == 'clean'` in 3 locations
- Skills can only become usable again via manual re-scan returning clean (not auto-override)

#### Custom Skill Scan Detail Popover
- Clickable scan status badge on every custom skill card opens a detailed popover
- Popover shows: rejection reason, detection type, threat score (visual bar), Sentinel profile name/scope/mode, and scan timestamp
- "Configure" link in popover navigates directly to Settings > Sentinel for profile customization
- Skills without scan data show "No scan data available" with guidance to run a scan
- Auto-opens popover after re-scan so user sees the result immediately
- Backend enriches `last_scan_result` with profile metadata (name, source, detection mode, scan timestamp)
- Passes `tenant_id` to `SentinelService` for correct hierarchical profile resolution

### Changed

#### Custom Skills UI/UX Improvements
- Scan status badge now shows gray "unknown" for skills without scan data instead of misleading green "clean"
- All timestamps (Updated, Scanned) now show full date + time (e.g., "Mar 29, 2026 at 01:09 PM")
- Separate "Scanned" timestamp displayed in card metadata line alongside "Updated"
- Popover header is color-tinted by status (red for rejected, green for clean, gray for unknown)
- Removed "Icon (emoji)" field from the custom skill create/edit modal

### Removed

#### Weather Skill Deprecation
- Removed Weather skill (OpenWeatherMap integration) from the platform
- Removed `OPENWEATHER_API_KEY` from all environment configuration files
- Cleaned up weather references from backend, frontend, tests, and documentation
- Auto-cleanup of weather skill records and slash commands on startup
- Updated skill count from 21 to 20

### Added

#### Stdio MCP Transport (Custom Skills Phase 5)
- Full Stdio transport implementation for running MCP server binaries inside tenant toolbox containers
- Binary allowlist (`uvx`, `npx`, `node`) with path traversal rejection and shell metacharacter validation
- JSON-RPC 2.0 protocol via stdin with `printf` for safe piping
- Idle watchdog (default 300s) with graceful SIGTERM then SIGKILL shutdown
- Resource limits: `ulimit -v 1048576 -t 60` (1GB virtual memory, 60s CPU time)
- Frontend: dynamic binary allowlist fetched from API, count indicator in UI

#### MCP Server Periodic Health Check Service
- Background service checking all active MCP servers every 3 minutes
- Auto-reconnects disconnected servers, respects circuit breaker cooldown for degraded servers
- Records health check results (latency, success, errors) in `MCPServerHealth` table
- Integrated into app startup/shutdown lifecycle

#### Network Egress Hardening for Toolbox Containers
- Explicit DNS configuration (`8.8.8.8`, `8.8.4.4`) prevents internal Docker DNS resolution attacks
- Network import scanning for script-type custom skills via `ShellSecurityService.scan_for_network_imports()`
- Non-blocking advisory warnings stored in `last_scan_result` for scripts with network imports
- K8s runtime support: maps DNS config to `V1PodDNSConfig` with `dns_policy="None"`

#### Syslog Streaming (Audit Log Forwarding)
- Per-tenant syslog forwarding configuration (`tenant_syslog_config` table)
- RFC 5424 structured syslog format with Tsushin-specific structured data element
- TCP, UDP, and TLS (certificate-based encryption) transport protocols
- Background syslog forwarder worker with event queue, batch processing, and per-tenant circuit breaker
- Collapsible "Syslog Forwarding" card on Settings > Audit Logs page
- Server config (host, port, protocol, facility, app name), TLS cert upload, event category filtering
- Test Connection button for verifying syslog server reachability
- API endpoints: `GET/PUT /api/settings/syslog/`, `POST /api/settings/syslog/test`

#### Tenant-Scoped Audit Logging
- New `audit_event` PostgreSQL table with JSONB details, tenant isolation, and composite indexes
- `TenantAuditService` with event recording, querying, stats, CSV export, and retention purge
- `TenantAuditActions` enum with 30+ standardized event types across auth, agents, flows, contacts, settings, security, API clients, custom skills, MCP servers, and team management
- API endpoints: `GET /api/audit-logs` (filtered query), `GET /api/audit-logs/stats` (summary), `GET /api/audit-logs/export` (CSV)
- Audit events wired into all major mutation routes: login/logout, agent CRUD, flow CRUD, contact CRUD, API client management, custom skills, MCP servers, team operations, settings changes, sentinel blocks
- Enhanced Settings > Audit Logs page with stats bar, 5-filter panel (action/severity/channel/date range), expandable event details, and CSV export
- `AuditLogEntry` component with 30+ action-type icons, severity indicators, channel badges, and click-to-filter
- Background audit retention worker (24h cycle, per-tenant configurable retention days)
- `audit.export` RBAC permission for CSV export (owner/admin roles)
- Alembic migration 0010 for audit_event table and tenant.audit_retention_days column

### Fixed

#### BUG-109: Hub Edit Provider Instance Modal Z-Index
- Moved `ProviderInstanceModal` from inside `glass-card overflow-hidden` container to root-level modal section
- Modal now renders outside the CSS stacking context, appearing centered and fully visible
- QA validated via Playwright browser automation

#### BUG-112: Admin Test Endpoints Missing Token Tracking
- Added `TokenTracker` to 4 admin test connection endpoints (Sentinel LLM test, Provider Instance test-connection, Integration test, System AI test)
- LLM costs from test connection calls are now visible in billing analytics

#### BUG-113: Streaming Token Count Estimation
- OpenAI streaming now uses `stream_options={"include_usage": True}` for actual token counts instead of `len(text)//4` estimation
- Gemini streaming captures `usage_metadata` when available for accurate tracking
- Falls back to estimation only when provider doesn't support usage metadata

#### BUG-114: Streaming Token Tracker Integration
- `generate_streaming()` now calls `token_tracker.track_usage()` on "done" chunks, matching the non-streaming `generate()` behavior
- All streaming responses now have proper cost tracking in analytics

#### BUG-115: MCP Tool Description Sentinel Scanning
- MCP tool descriptions from untrusted servers are now scanned by Sentinel before storage
- Trust-level-aware: system/verified servers skip scan, untrusted servers get full analysis
- Description length capped at 1000 characters (Security C-3)

#### BUG-116: OAuth2 Token Response Missing Scope
- Added `scope` field to `TokenResponse` Pydantic model per OAuth2 RFC 6749 §5.1

#### BUG-117: API v1 X-Request-Id Overwritten by Generic Middleware
- Generic `RequestIdMiddleware` now skips `/api/v1/` paths, preserving `req_`-prefixed IDs from rate limiter

#### Test Infrastructure: SQLite to PostgreSQL Migration
- Migrated 9 test files from SQLite in-memory databases to PostgreSQL with transactional rollback
- Fixed SQLAlchemy mapper initialization: `models_rbac` imported before `models` in sentinel tests
- Fixed FK constraint violations: sentinel tests create real agent records, auth tests cascade-delete all child tables
- Fixed MemGuard test mocking: bypasses SQLAlchemy mapper chain with lightweight mock class
- **Result: 218/218 tests passing across 10 test suites (0 failures, 0 errors)**

### Changed

#### Skills Section — Built-in vs Custom Separation & Sandboxed Tools Migration
- Separated built-in and custom skills with labeled section headers ("BUILT-IN SKILLS" / "CUSTOM SKILLS") and subtle divider lines
- Replaced emoji icons on custom skill cards with styled violet SVG icon boxes (WrenchIcon) for visual consistency
- Migrated per-agent Sandboxed Tools configuration from dedicated "Sandboxed Tools" tab into Skills > Sandboxed Tools > Configure modal
- Removed the dedicated "Sandboxed Tools" tab from the agent editor (saves space, reduces clutter)
- New config modal features: teal gradient header with live counter, toggle switches per tool, auto-save on toggle, security warnings for nmap/nuclei
- If Sandboxed Tools skill is not enabled for an agent, no separate config tab wastes space

#### Skills UI Overhaul — "Add Skill" Pattern
- Redesigned Studio > Skills tab to only show enabled/configured skills (instead of listing all available skills)
- Added "Add Skill" button with categorized modal (Communication, Search & Web, Audio & Media, Automation & Tools, Intelligence, Travel)
- Skills are now added as enabled with config modal opening immediately on add
- Each skill card now has a "Remove" action to disable and return to the available pool
- Custom skills integrated into the same Add Skill modal alongside built-in skills
- Search and category filtering in the Add Skill modal
- Consistent card styling with teal gradient theme for all active skills
- Decomposed skill constants into `frontend/components/skills/skill-constants.ts`
- Created reusable `AddSkillModal` component at `frontend/components/skills/AddSkillModal.tsx`

### Security

#### API v1 Security Hardening
- **HIGH:** Added per-IP rate limiting (10 req/min) to OAuth token endpoint — prevents brute-force attacks on client credentials
- **MEDIUM:** Added HTML sanitization validators to Persona name/description fields — prevents stored XSS
- **MEDIUM:** Added HTML sanitization validators to Contact friendly_name/notes fields — prevents stored XSS
- **LOW:** Added E.164 phone number validation (`^\+?[1-9]\d{6,14}$`) to Contact and Config phone fields
- **LOW:** Converted 10 debug `print()` statements in playground routes to structured `logger.debug()` — eliminates info leakage via stdout

#### Slash Command Security Hardening
- **CRITICAL:** Fixed shell RBAC bypass via WhatsApp/Telegram channels — `/shell` permission check was skipped when `user_id=None` (non-playground channels). Now denies execution without authenticated user.
- **HIGH:** Fixed cross-tenant thread manipulation — `/thread end`, `/thread list`, `/thread status` queries now filter by `tenant_id` to prevent tenant A from accessing tenant B's threads.
- **HIGH:** Added agent ownership validation on `/api/commands/execute` — `agent_id` parameter is now verified against the authenticated user's tenant.
- **MEDIUM:** Escaped LIKE wildcards in sandboxed tool lookup — prevents `/tool %` from matching all tools in the tenant.
- **MEDIUM:** Added `shlex.quote()` to sandboxed tool command template rendering — prevents shell metacharacter injection via tool parameters.

### Added

#### API v1 OpenAPI Documentation & Response Models
- Shared v1 schemas module (`api/v1/schemas.py`) with 20+ reusable Pydantic models for pagination, errors, and resource responses
- `response_model=` wired on all 40 v1 endpoints across 7 route files for typed API responses
- `responses=` error documentation (401, 403, 404, 422, 429) on all v1 endpoints
- Enhanced docstrings on all v1 endpoints with descriptions and permission requirements
- `X-API-Version: v1` response header on all v1 responses
- Enhanced FastAPI app description documenting auth methods, rate limiting, pagination, and error format
- Static `docs/openapi.json` export (435 paths, 413 schemas) for version-controlled API spec
- `backend/scripts/export_openapi.py` for OpenAPI spec regeneration

#### Slash Command Webhook Handler
- Implemented the webhook handler for custom slash commands (`handler_type: "webhook"`)
- Async HTTP calls with configurable method, headers, timeout (max 30s), and HMAC-SHA256 signing
- SSRF protection: blocks private/internal IP ranges and localhost
- Response body capped at 64KB

#### Slash Command Help Text in UI
- Inline autocomplete (/) now shows `help_text` for the selected command
- Command palette (Cmd+K) now shows `help_text` for the selected command
- Displayed in a compact monospace format below the command description

### Fixed

#### Playground Markdown Rendering
- AI/system message content in ExpertMode now renders with ReactMarkdown + GFM support
- Previously, slash command responses with markdown (`**bold**`, lists, code blocks) were displayed as raw text
- User messages remain as plain text to avoid unintended formatting

#### Slash Command Fixes
- Fixed `/status` command crash — `Agent.name` attribute error (correct field is `agent_name`)

### Added

#### Sentinel Security Profiles
- Granular security profiles with custom configuration per protection rule
- Profile assignment at tenant, agent, or skill level with hierarchical inheritance
- Profile management UI: create, edit, clone, delete (Settings > Sentinel > Profiles)
- Security graph view with agent/skill hierarchy visualization
- Effective config preview per scope level

#### MemGuard (Memory Poisoning Detection)
- 5th Sentinel detection type: `memory_poisoning` with `applies_to: ["memory"]`
- Layer A: Pre-storage regex pattern matching (EN + PT) blocks poisoned messages before memory write
- Layer B: Fact validation gate blocks credential injection, command patterns, and contradictions
- Integrated with Security Profiles via zero-migration design (detection_overrides inheritance)
- Dedicated MemGuard tab with branded UI in Settings > Sentinel
- 45 unit tests + 103 integration tests

#### Message Queuing System
- Async message queue for all channels (Playground, WhatsApp, Telegram)
- `MessageQueue` table with Alembic migration 0003
- `MessageQueueService` with `SELECT FOR UPDATE SKIP LOCKED` for concurrent processing
- `QueueWorker` asyncio background processor with dead-letter after 3 retries
- Queue API routes and frontend WebSocket queue events
- Playground async/sync modes (`?sync=true`)

#### WebSocket Streaming
- Token-by-token response streaming via `/ws/playground` WebSocket endpoint
- Secure first-message authentication (token in first message, not URL params)
- `PlaygroundWebSocketService` with streaming chunk types: token, thinking, done, error
- `PlaygroundWebSocket` frontend client with auto-reconnect and exponential backoff
- `usePlaygroundWebSocket` React hook for streaming state management
- `StreamingMessage` component with animated typing indicators
- Heartbeat ping/pong (30-second intervals)

#### Groq LLM Provider
- Ultra-fast LLM inference via OpenAI-compatible API (`https://api.groq.com/openai/v1`)
- Models: Llama 3.3 70B Versatile, Llama 3.1 8B Instant, Mixtral 8x7B 32K, Gemma2 9B IT
- Reuses existing `AsyncOpenAI` + `_call_openai()` / `_stream_openai()` pattern
- No new SDK dependency required

#### Grok (xAI) LLM Provider
- xAI's Grok models via OpenAI-compatible API (`https://api.x.ai/v1`)
- Models: Grok 3, Grok 3 Mini, Grok 2
- Same OpenAI-compatible implementation pattern as Groq

#### ElevenLabs TTS
- Full provider implementation replacing the v0.5.0 placeholder
- Premium voice AI synthesis via ElevenLabs API with 5+ premium voices
- Models: eleven_multilingual_v2 (default), eleven_turbo_v2
- Health check via subscription endpoint with character quota tracking
- Async httpx client with comprehensive error handling and cost estimation

#### Settings > Integrations UI
- Provider API key management cards for Groq, Grok, and ElevenLabs
- CRUD operations: Configure, Edit, Remove API keys with masked preview
- Test Connection button per provider with inline success/error results
- Encryption at rest for stored API keys (SEC-001)
- Multi-tenancy key isolation

#### Test Connection Endpoints
- `POST /api/integrations/{provider}/test` endpoint for validating API keys
- ElevenLabs: health check validation via `/v1/user`
- Groq/Grok: minimal AIClient test message
- Pydantic request/response models with provider-specific details

#### Public API v1
- Programmatic REST API for external applications to interact with Tsushin agents
- OAuth2 Client Credentials: `POST /api/v1/oauth/token` (client_id + secret -> 1h JWT)
- Direct API Key mode: `X-API-Key` header (skip token exchange)
- Agent CRUD: `GET/POST/PUT/DELETE /api/v1/agents` with pagination, filtering
- Agent Chat: `POST /api/v1/agents/{id}/chat` (sync + async modes)
- Thread Management: list, get, delete conversation threads
- Resource Listing: skills, tools, personas, security-profiles, tone-presets
- Profile Assignment: assign skills, personas, security profiles to agents
- Client Management UI: Settings > API Clients (create, rotate, revoke)
- Rate Limiting: per-client RPM with `X-RateLimit-*` headers
- Request Audit: `X-Request-Id` + `api_request_log` table
- 5 API roles: `api_agent_only`, `api_readonly`, `api_member`, `api_admin`, `api_owner`
- 3 new DB tables + Alembic migration 0004
- 3 new RBAC permissions (`api_clients.read/write/delete`)
- Regression test client seeded in `.env` (`TSN_API_CLIENT_ID`/`SECRET`)

#### Agent Studio (Visual Agent Builder)
- New Agent Studio tab in Watcher with React Flow canvas
- Visual agent building: central agent node with attachable profile nodes
- Palette panel with categories: Persona, Channels, Skills, Sandboxed Tools, Security Profiles, Knowledge Base, Memory
- Drag-and-drop from palette to canvas with ghost images and category-colored glows
- Batch builder-data and atomic builder-save endpoints
- Tree layout with grouped/expandable nodes
- Inline config editing with slide-out panels
- Builder save, node interactions, avatars, auto-expand on drop

#### Agent Builder: Remove Attached Items
- Hover-reveal X button on each detachable node (channels, skills, tools, personas, security profiles, knowledge docs)
- Memory node protected from removal (mandatory)
- Keyboard Delete key support with memory node guard
- Warning toast when removing last channel
- Automatic layout reflow after removal, group node auto-collapse when empty

#### Active Chain Edge Glow (Graph View)
- Edge glow color matched to target node type: cyan (channel->agent), blue (agent chain), teal (skill), violet (KB)
- Pulse animation synchronized with node glow (1.5s cycle)
- Coordinated fade-out with 3s post-processing fade
- SVG `filter: drop-shadow()` for glow effect on edge paths

#### SSL/HTTPS Encryption
- Caddy reverse proxy with 3 SSL modes: Let's Encrypt, manual certs, self-signed (`tls internal`)
- `docker-compose.ssl.yml` override with Caddy service
- Installer prompts: SSL mode selection, domain, email, cert paths, DNS validation, port checks
- Caddyfile generation per mode, self-signed cert generation via openssl
- `ProxyHeadersMiddleware` for real client IP behind proxy
- HTTP->HTTPS redirect (308), WSS auto-detection
- Backup/restore support for `caddy/` directory

#### GKE Readiness (Cloud-Native Infrastructure)
- `/api/readiness` endpoint — checks PostgreSQL connectivity for Kubernetes readiness gates
- `/metrics` endpoint — Prometheus metrics (`http_requests_total`, `http_request_duration_seconds`, `tsn_service_info`)
- `TSN_LOG_FORMAT` setting — toggle between text (default) and JSON structured logging
- `TSN_METRICS_ENABLED` setting — enable/disable Prometheus metrics endpoint
- `TSN_CONTAINER_RUNTIME` setting — pluggable container backend (docker/kubernetes)
- `TSN_SECRET_BACKEND` setting — pluggable secret provider (env/gcp)
- Request ID middleware — generates UUID per request, `X-Request-Id` correlation header
- `ContainerRuntime` abstraction layer with `DockerRuntime` (default) and full `K8sRuntime` implementation
- `K8sRuntime` — full Kubernetes container backend mapping Docker operations to K8s Deployments, Services, and exec API
- `SecretProvider` abstraction layer with `EnvSecretProvider` (default) and full `GCPSecretProvider` implementation
- `GCPSecretProvider` — Google Secret Manager backend with thread-safe TTL cache, parallel warm-up, and three-tier fallback (GCP → env → default)
- `TSN_K8S_NAMESPACE` and `TSN_K8S_IMAGE_PULL_POLICY` settings for K8s deployment configuration
- `TSN_GCP_PROJECT_ID`, `TSN_GCP_SECRET_PREFIX`, `TSN_GCP_SECRET_CACHE_TTL`, `TSN_GCP_SECRET_VERSION` settings for GCP Secret Manager
- Watcher catchup cap (`TSN_WATCHER_MAX_CATCHUP_SECONDS`) to prevent stale message replay after container rebuilds
- Helm chart for GKE deployment (`k8s/tsushin/`) with 16 templates
- CI/CD pipeline for GKE (`.github/workflows/gke-deploy.yml`)
- Cloud SQL Proxy sidecar configuration
- Network policies, HPA, managed TLS, WebSocket ingress support

#### Smart UX Features (Playground)
- Auto-save drafts to localStorage per thread with 500ms debounce, restored on thread switch
- Smart paste: auto-detects JSON and code blocks, wraps in markdown fences on paste

#### Slash Command Permissions per Contact
- Per-contact `slash_commands_enabled` override (null = use tenant default)
- Tenant-level `slash_commands_default_policy`: `enabled_for_known`, `enabled_for_all`, `disabled`
- Resolution order: contact override > tenant policy > system default
- Unknown senders denied by default; 3-state UI toggle in Contacts management

#### WhatsApp Group Slash Commands via Agent Mention
- `@agentname /tool nmap quick_scan target=x` in group chats now triggers slash command execution
- Mention resolved to agent, slash command extracted and dispatched with agent context
- Works across WhatsApp and Telegram groups; response sent to group thread

#### Public API v1 Expansion (Flows, Hub, Studio)
- 22 new API endpoints: Flows CRUD + execution + runs (13), Hub integrations + tools (6), Studio builder (3)
- Flow execution returns HTTP 202 with run_id for async polling
- Provider-agnostic Hub facade with service-factory dispatch
- Studio agent clone endpoint for duplicating agent configurations
- `hub.read` and `hub.write` permissions added to API role scopes
- OpenAPI metadata: title "Tsushin Platform API", tagged endpoint groups, Swagger UI at `/docs`
- Total v1 endpoints: 32

#### Platform Hardening (2026-03-29)
- Flow Agentic Summarization for raw text — SummarizationStepHandler now supports summarizing `raw_output` from tool/skill steps (Path B), not just `ConversationThread` objects. Enables flows like "Nmap scan -> AI summary -> Notification" to work end-to-end.
- MCP Server Auto-Connect on startup — active MCP servers automatically connect when the backend starts, eliminating manual reconnection after container restarts
- Kokoro TTS health check fallback — falls back to `/v1/audio/voices` when `/health` returns ConnectError
- Playground thread LIKE-based fallback — sender_key resolution now uses LIKE patterns when exact matches fail, improving thread loading for older conversations
- Google OAuth HTTPS — redirect URI updated to `https://localhost/api/hub/google/oauth/callback` via Caddy proxy; app published to production mode (tokens no longer expire every 7 days)
- Telegram agent linking — default agent linked to Telegram bot instance with `telegram` added to `enabled_channels`

#### Database & Infrastructure
- PostgreSQL 16 migration from SQLite (full schema + Alembic migrations)
- Tsushin kitsune branding: banner on README and login page
- "Think, Secure, Build" slogan rebrand

### Fixed

#### Security (v0.6.1 Audit — 21 bugs resolved)

##### SSRF & Input Validation
- BUG-065: Added SSRF validation for `ollama_base_url` with DNS-resolution-based IP checking via new shared `ssrf_validator.py` module
- BUG-066: Replaced string-prefix SSRF checks in scraper, Playwright, and MCP browser providers with post-DNS-resolution validation — fixes DNS rebinding, incorrect 172.x range, and missing IPv6/metadata checks
- BUG-063: Added package name regex validation and `shlex.quote` to toolbox `install_package` — prevents shell command injection
- BUG-064: Changed workspace directory permissions from `0o777` to `0o750` with proper `chown`
- BUG-068: Expanded Sentinel SSRF detection from 2 tools/5 patterns to 12 tools/34 patterns with defense-in-depth URL argument checking

##### Authentication & Authorization
- BUG-072: Added `deleted_at` filter to login and `get_user_by_id` queries — soft-deleted users can no longer authenticate
- BUG-073: Added null-guard for `password_hash` before `verify_password` — SSO users no longer cause 500 on password login
- BUG-076: Added `is_active` check to `auth_routes.get_current_user` — disabled accounts blocked from `/me` and `/logout`
- BUG-071: Password reset and invitation tokens now stored as SHA-256 hashes instead of plaintext
- BUG-070: API client creation validates that requested scopes are a subset of creator's permissions — prevents privilege escalation
- BUG-074: Replaced wildcard `ProxyHeadersMiddleware(trusted_hosts=["*"])` with configurable `TSN_TRUSTED_PROXY_HOSTS` (default `127.0.0.1,::1`)

##### Multi-Tenancy Isolation
- BUG-069: Scoped default agent create/update/delete operations to caller's tenant — prevents cross-tenant data corruption
- BUG-082: Removed `Agent.tenant_id.is_(None)` from analytics queries — tenants no longer see NULL-tenant agents
- BUG-083: Rewrote `conversation_search_service` to join through Agent table — fixes non-existent `Memory.tenant_id` column reference
- BUG-067: Restricted global-scoped URL config fields to global admin only (interim fix for Config singleton)

##### RBAC Permission Gates
- BUG-075: Added `require_permission("org.settings.read")` to Sentinel GET /config/agent/{id}, GET /logs, GET /stats
- BUG-077: Added `shell.read` permission gate to Hub Shell page
- BUG-078: Added `tools.read` permission gate to Hub Sandboxed Tools page
- BUG-079: Added `org.settings.read` permission gates to 5 settings pages (Sentinel, Security, AI Configuration, Model Pricing, Integrations)

##### Data Integrity
- BUG-080: Hard user delete now clears FK references (UserInvitation, GlobalAdminAuditLog, PasswordResetToken) before deletion
- BUG-081: Fixed inverted tenant_id logic in SSO config endpoints — uses `tenant_context.tenant_id` consistently

##### Previous Security Fixes
- Reduced Sentinel false positives for educational shell queries and language preferences
- MemGuard false positive reduction: long token regex 20->32, negative lookahead for common words
- Fixed `warn_only` mode handling in MemGuard
- Fixed `detect_only` and `warn_only` modes in Sentinel cache, notifications, and safety nets
- Changed system default Sentinel profile from Moderate (block) to Permissive (detect_only)
- Fixed stale `gemini-2.0-flash-lite` defaults to `2.5-flash-lite`
- Removed hardcoded dev password from `alembic.ini`
- Removed tracked dev artifacts and hardened `.gitignore`
- Fixed Helm chart missing `POSTGRES_PASSWORD` in secrets — pod would fail `InvalidPodSpec` on GKE
- Fixed `TSN_GCP_PROJECT_ID` not injected into pod — backend would crash with `KeyError` at startup
- Fixed `commit_container` hard error in K8s mode — now gracefully falls back to DB-only package tracking
- Fixed hardcoded `v0.6.0` image tag in CI — now derived from `Chart.yaml appVersion`
- Shell injection prevention in `K8sRuntime` exec commands via `shlex.quote`
- Thread-safe exec exit code cache with `Lock` in `K8sRuntime`
- PVC cleanup on container removal in `K8sRuntime` to prevent resource leaks
- GCP warm-up no longer caches `None` values on failure (forces retry on next access)

#### UI & UX
- Full UI cosmetic assessment and remediation across all pages
- Migrated core components, login, auth pages, system admin pages, and agent managers to Tsushin design tokens
- Migrated Agent Detail page to Tsushin design tokens (BUG-005)
- Matched login page background to banner color
- Resolved 16+ cosmetic bugs across two assessment rounds
- Fixed Channels tab not persisting toggles: changed to auto-save on toggle (consistent with Skills tab behavior)

#### Agent Studio
- Fixed builder edge routing and child node drag behavior
- Fixed node drag and interaction blocking issues
- Made group nodes selectable for hover and click
- Persisted persona and channel changes in builder save
- Replaced dagre with manual tree layout for proper TB hierarchy
- Replaced smoothstep curves with straight edges
- Fixed builder validation, logging, and tenant isolation

#### Sentinel
- Fixed `skill_context` in router and false positives with `detection_mode`
- Fixed `threat_reason` field usage (was referencing non-existent `response_message`)
- Showed all skill nodes in security graph with expand/collapse
- Hidden inactive agents in security graph by default
- Removed duplicated sentinel settings from MemGuard tab

#### Billing & Cost Tracking (BUG-110, BUG-111)
- BUG-110: Fixed 13 AIClient call sites silently dropping `token_tracker` — skill classification, flow intent parsing, scheduler operations, fact extraction, search/browser/flight parsing, sentinel analysis, and persona summaries now properly tracked in TokenUsage table
- BUG-111: Fixed Gemini token estimation using `len(text)//4` — now reads actual `response.usage_metadata` (prompt_token_count, candidates_token_count) when available
- Added `set_token_tracker()` to BaseSkill with automatic propagation via SkillManager to all skills
- Added debug-level guardrail log in AIClient when instantiated without `token_tracker` for future gap detection
- SchedulerService background worker now creates TokenTracker for cost tracking of unattended scheduled conversations
- MultiAgentMemoryManager and FactExtractor now receive and propagate token_tracker through the full memory pipeline

#### Platform Hardening (BUG-105 to BUG-108)
- BUG-105: Fixed flow SummarizationStepHandler nested dict lookup — `input_data.get("step_1.thread_id")` changed to proper `input_data.get("step_1", {}).get("thread_id")`. Template `{{step_2.summary}}` now resolves correctly.
- BUG-106: Fixed playground "Failed to Load Conversation" — threads with sender_key format mismatches now return empty messages with warning instead of error
- BUG-107: Fixed MCP servers always showing "disconnected" — added auto-connect background task on startup
- BUG-108: Fixed Kokoro TTS "Cannot connect" false positive — added `/v1/audio/voices` fallback endpoint

#### Backend
- Fixed shadowed local `Contact` import causing `UnboundLocalError` in WebSocket streaming
- Fixed `NoneType len()` error in Playground with improved error handling
- Fixed Google credential save crash and SELinux access denials
- Fixed tone presets visibility and Playground search on PostgreSQL
- Improved shell skill timeout resilience with better errors, auto-retry, and 120s default
- Fixed OAuth token expiration with retry, re-auth, and privacy page
- Fixed API v1 `create_thread` async await and `thread_id` extraction
- Fixed installer port configuration to actually take effect
- Fixed Alembic migrations 0003/0004 DuplicateTable on fresh PostgreSQL installs (idempotent table creation)
- Fixed Hub provider cards for Groq/Grok/ElevenLabs showing "Coming Soon" instead of "Available"

### Changed

- Bumped version to v0.6.0
- `ToolboxContainerService` refactored to use `ContainerRuntime` interface
- `MCPContainerManager` refactored to use `ContainerRuntime` interface
- `settings.py` now routes secret retrieval through `SecretProvider`
- `auth_utils.py` `JWT_SECRET_KEY` now uses `SecretProvider` instead of direct `os.getenv()`
- GKE deploy workflow changed to manual-only trigger until GCP infrastructure is configured
- `tsushin-network` is now an external Docker network — survives `docker-compose down` to preserve MCP/WhatsApp sessions. Existing installs must run `docker network create tsushin-network` or re-run `install.py`.
- Pre-commit YAML check now excludes Helm template directory
- Compacted Watcher "Threats by Type" into inline pill badges
- Added `frontend/lib/` to repo (was excluded by Python gitignore pattern)

---

## [0.5.0] - 2026-02-07

Initial public release. 20 skills, 18 providers, 60+ database tables, 170+ API endpoints, 3 channels.

See `ROADMAP_ARCHIVE_2026-02-07.md` for full implementation details.

### Highlights

- Multi-tenancy with RBAC (50+ permissions), JWT auth, team management
- AI Providers: OpenAI, Anthropic, Google Gemini, Ollama, OpenRouter (100+ models)
- Channels: WhatsApp (MCP containers), Telegram (Bot API), Playground (web)
- 20 Skills: Shell, Browser Automation, Image Gen, Search, Web Scraping, Email, Scheduler, Flight Search, Audio TTS/Transcription, Adaptive Personality, Knowledge Sharing, Agent Switcher, Flow Engine, Sandboxed Tools, AI Classifier
- Projects system with isolated workspaces and knowledge base
- Conversation threads with message operations (edit, regenerate, branch, bookmark)
- Conversation search (FTS5 + semantic), knowledge extraction (tags, insights)
- Sentinel security agent with real-time threat detection
- Slash commands (cross-channel, multilingual)
- Tone presets, Skills-as-Tools (MCP), Custom Tools Hub (Docker toolbox)
- Contact management, 4-layer memory, ChromaDB vector store
- Docker containerization, interactive installer
