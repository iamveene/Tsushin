# Changelog

All notable changes to the Tsushin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-03-30

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
