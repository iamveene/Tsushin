# Changelog

All notable changes to Tsushin are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.6.0] - Unreleased

**Theme:** Security, Streaming, Providers, Public API & UX

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

#### Database & Infrastructure
- PostgreSQL 16 migration from SQLite (full schema + Alembic migrations)
- Tsushin kitsune branding: banner on README and login page
- "Think, Secure, Build" slogan rebrand

### Fixed

#### Security
- Reduced Sentinel false positives for educational shell queries and language preferences
- MemGuard false positive reduction: long token regex 20->32, negative lookahead for common words
- Fixed `warn_only` mode handling in MemGuard
- Fixed `detect_only` and `warn_only` modes in Sentinel cache, notifications, and safety nets
- Changed system default Sentinel profile from Moderate (block) to Permissive (detect_only)
- Fixed stale `gemini-2.0-flash-lite` defaults to `2.5-flash-lite`
- Removed hardcoded dev password from `alembic.ini`
- Removed tracked dev artifacts and hardened `.gitignore`

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

#### Backend
- Fixed shadowed local `Contact` import causing `UnboundLocalError` in WebSocket streaming
- Fixed `NoneType len()` error in Playground with improved error handling
- Fixed Google credential save crash and SELinux access denials
- Fixed tone presets visibility and Playground search on PostgreSQL
- Improved shell skill timeout resilience with better errors, auto-retry, and 120s default
- Fixed OAuth token expiration with retry, re-auth, and privacy page
- Fixed API v1 `create_thread` async await and `thread_id` extraction
- Fixed installer port configuration to actually take effect

### Changed

- Bumped version to v0.6.0
- Compacted Watcher "Threats by Type" into inline pill badges
- Added `frontend/lib/` to repo (was excluded by Python gitignore pattern)

---

## [0.5.0] - 2026-02-07

Initial public release. 21 skills, 18 providers, 60+ database tables, 170+ API endpoints, 3 channels.

See `ROADMAP_ARCHIVE_2026-02-07.md` for full implementation details.

### Highlights

- Multi-tenancy with RBAC (50+ permissions), JWT auth, team management
- AI Providers: OpenAI, Anthropic, Google Gemini, Ollama, OpenRouter (100+ models)
- Channels: WhatsApp (MCP containers), Telegram (Bot API), Playground (web)
- 21 Skills: Shell, Browser Automation, Image Gen, Search, Weather, Web Scraping, Email, Scheduler, Flight Search, Audio TTS/Transcription, Adaptive Personality, Knowledge Sharing, Agent Switcher, Flow Engine, Sandboxed Tools, AI Classifier
- Projects system with isolated workspaces and knowledge base
- Conversation threads with message operations (edit, regenerate, branch, bookmark)
- Conversation search (FTS5 + semantic), knowledge extraction (tags, insights)
- Sentinel security agent with real-time threat detection
- Slash commands (cross-channel, multilingual)
- Tone presets, Skills-as-Tools (MCP), Custom Tools Hub (Docker toolbox)
- Contact management, 4-layer memory, ChromaDB vector store
- Docker containerization, interactive installer
