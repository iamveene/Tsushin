# Tsushin — Comprehensive Documentation

**Tsushin** (通信 — Japanese for "Communication") is a multi-tenant, self-hostable agentic messaging platform that unifies AI agent orchestration, conversational channels (WhatsApp, Telegram, Slack, Discord, Webhook, Playground), multi-layer semantic memory, workflow automation (Flows), AI-powered security (Sentinel), and observability.

This document is the exhaustive reference for configuring, deploying, operating, and using every feature of the platform. For a condensed overview, see the root [README](../README.md).

> **Version:** v0.6.0 (`README.md`, `backend/settings.py`).
> **License:** MIT. **Author:** Marcos Vinicios Penha ([@iamveene](https://github.com/iamveene)).

---

## Table of Contents

1. [Introduction & Audience](#1-introduction--audience)
2. [Architecture Overview](#2-architecture-overview)
3. [Quick Start](#3-quick-start)
4. [Deployment & Operations](#4-deployment--operations)
5. [System Configuration](#5-system-configuration)
6. [Authentication & Access](#6-authentication--access)
7. [Agents](#7-agents)
8. [Personas & Tone Presets](#8-personas--tone-presets)
9. [Skills](#9-skills)
10. [Memory & Knowledge](#10-memory--knowledge)
11. [Vector Stores](#11-vector-stores)
12. [Security — Sentinel](#12-security--sentinel)
13. [Flows](#13-flows)
14. [Scheduler & Triggers](#14-scheduler--triggers)
15. [Channels](#15-channels)
16. [Contacts & Channel Mapping](#16-contacts--channel-mapping)
17. [Projects (Studio)](#17-projects-studio)
18. [Playground](#18-playground)
19. [LLM Providers](#19-llm-providers)
20. [Hub Integrations](#20-hub-integrations)
21. [Settings — UI Taxonomy](#21-settings--ui-taxonomy)
22. [System Admin (Global Admin Only)](#22-system-admin-global-admin-only)
23. [Audit Logging & Compliance](#23-audit-logging--compliance)
24. [Observability](#24-observability)
25. [Public API v1](#25-public-api-v1)
26. [Slash Commands](#26-slash-commands-system-wide-catalog)
27. [CLI & Tester MCP](#27-cli--tester-mcp)
28. [Troubleshooting](#28-troubleshooting)
29. [Appendix A — Complete Environment Variable Reference](#29-appendix-a-complete-environment-variable-reference)
30. [Appendix B — Permission Scopes](#30-appendix-b-permission-scopes)
31. [Appendix C — Glossary](#31-appendix-c-glossary)

---

## 1. Introduction & Audience

**Tsushin** (通信 — Japanese for "Communication") is a multi-tenant, agentic messaging framework that unifies AI agent orchestration, conversational channels (WhatsApp, Telegram, Slack, Discord, HTTP Webhook, Playground), a multi-layer semantic memory system, workflow automation ("Flows"), AI-powered security (Sentinel), and observability under a single self-hostable platform.

Source: `README.md`, `backend/settings.py`, and the README version badge.

**Audience for this document:**

| Role | What this doc gives you |
|------|-------------------------|
| **Platform operators / SREs** | Container topology, env-var reference, deployment modes (Docker Compose, GKE Helm), health probes, Prometheus metrics, troubleshooting. |
| **Tenant admins** | RBAC roles and permissions, SSO configuration, audit/syslog streaming, API-client management. |
| **Application developers** | Public API v1 reference, OAuth2 client-credentials + direct API-key auth, rate limiting, webhook integration. |
| **Security engineers** | Sentinel profiles, permission scopes, HMAC-signed webhooks, envelope-encrypted secrets, docker-socket-proxy isolation. |

Version under documentation: **v0.6.0** in both the README and backend settings.

---

## 2. Architecture Overview

### 2.1 Container topology (Docker Compose)

Tsushin ships as a Docker Compose stack defined in `docker-compose.yml`. The core services:

| Service | Image / Build | Port | Purpose | Source |
|---------|---------------|------|---------|--------|
| `tsushin-postgres` | `postgres:16-alpine` | 5432 (internal) | Relational database — tenants, users, agents, flows, events, audit logs. | `docker-compose.yml:22-38` |
| `tsushin-docker-proxy` | `tecnativa/docker-socket-proxy:latest` | 2375 (internal) | Restricts the Docker API surface to reduce container-escape risk. Backend talks to `tcp://docker-socket-proxy:2375` rather than mounting the raw socket. | `docker-compose.yml:43-75` |
| `tsushin-backend` | Built from `./backend/Dockerfile` | `${TSN_APP_PORT:-8081}` | FastAPI app. Agents, flows, memory, skills, channels, API v1, WebSockets. | `docker-compose.yml:80-168` |
| `tsushin-frontend` | Built from `./frontend/Dockerfile` | `${FRONTEND_PORT:-3030}` | Next.js 16 UI (Watcher, Hub, Studio, Playground, Settings). | `docker-compose.yml:173-195` |
| *(removed v0.7.0)* `kokoro-tts` | — | — | Stack-level Kokoro service removed. Kokoro runs as per-tenant auto-provisioned containers managed by `KokoroContainerManager`, configured via Hub → Kokoro TTS → Setup with Wizard. See §20.6. | `models.py` (`TTSInstance`), `backend/services/kokoro_container_manager.py` |

**Network:** All services attach to the **external** bridge network `tsushin-network`. The network is declared `external: true`, so `docker compose down` does not remove it. That matters because MCP WhatsApp bot containers (spawned dynamically by `ToolboxContainerService` / `MCPContainerManager`) also join this network. Create the network once with `docker network create tsushin-network`; `install.py` handles this automatically. Source: `docker-compose.yml:229-237`.

**Multi-stack note:** When SSL/Caddy is enabled, proxy upstreams must target stack-scoped container names (for example `tsushin-frontend:3030`, `tsushin-backend:8081`) rather than generic Docker aliases like `frontend` / `backend`. On the shared `tsushin-network`, generic aliases can resolve to another running Tsushin stack.

**Browser → backend request path (v0.6.1):** the Next.js frontend proxies `/api/*` and `/ws/*` to the backend via `rewrites()` declared at `frontend/next.config.mjs`. The destination is read at request time from the `BACKEND_INTERNAL_URL` env var (defaults to `http://backend:8081`, the compose service DNS). This keeps every browser request same-origin with the frontend, so the httpOnly `tsushin_session` cookie (domain-scoped to the frontend) rides along automatically — including the Watcher activity WebSocket at `/ws/watcher/activity`. Replaces the v0.6.0 pattern of baking an absolute `NEXT_PUBLIC_API_URL` into the build, which dropped the cookie on cross-origin access.

**Persistent data:**

| Volume / bind | Container path | Contents |
|---|---|---|
| Docker named volume `tsushin-postgres-data` | `/var/lib/postgresql/data` | PostgreSQL relational data |
| bind `./backend/data` | `/app/data` | ChromaDB vectors, workspaces, backups, legacy SQLite rollback |
| bind `./logs/backend` | `/app/logs` | Structured application logs |
| `tsushin-audio` / `-screenshots` / `-images` | `/tmp/tsushin_*` | Shared with MCP sidecar containers (TTS, browser-automation, image-skill) |

Source: `docker-compose.yml:89-101, 242-259`.

### 2.2 Data flow (from README ASCII diagram)

```
Frontend (Next.js)  <--REST/WebSocket-->  Backend (FastAPI + PG 16)  <-->  RBAC Layer
                                                 |
                                  +--------------+--------------+
                                  |              |              |
                                CORE            HUB           STUDIO
                             (Agents,      (Providers,     (Personas,
                              Skills,       Channels,       Contacts,
                              Sentinel)     Tool APIs,      Projects,
                                            TTS)            Tone Presets)
                                  |
                           +------+------+
                           |             |
                         FLOWS         MEMORY            WATCHER
                       (4 types,    (Working,         (Dashboard,
                        7 steps)     Episodic,         Conversations,
                                     Semantic,         Flows, Billing,
                                     Shared)           Security, Graph)

              SANDBOXED TOOLS (per-tenant Docker)  |  CHANNELS (WA/TG/Slack/Discord/Webhook/Playground)
```

Source: `README.md` (Architecture section).

### 2.3 Dynamically-managed MCP containers

Tsushin spawns per-tenant containers outside the compose stack, all joining `tsushin-network`:

* **WhatsApp MCP bots** — one container per connected WhatsApp number, built from the `mcp-agent-tenant` image, managed by `services/mcp_container_manager.py`.
* **Tester surface** — QA bridge status exposed through `/api/mcp/instances/tester/*`; the backend prefers a legacy/compose tester container when present and otherwise falls back to the tenant's active runtime tester instance.
* **Toolbox containers** — per-tenant sandboxes for "Sandboxed Tools" (nmap, dig, nuclei, etc.), managed by `services/toolbox_container_service.py` with base image built from `backend/containers/Dockerfile.toolbox`.

Source: `docker-compose.yml:12-14`, `backend/services/toolbox_container_service.py:114`, `backend/services/mcp_container_manager.py:234`.

### 2.4 v0.7.0 Phase 0 foundation

v0.7.0 Phase 0 prepares the shared surfaces that later trigger, continuous-agent, Whisper/Speaches, and policy tracks build on.

* **Migration slots** — `docs/internal/v0.7.0-migration-slots.md` reserves `0045-0058` so parallel release tracks do not collide; Track D's tenant-default ASR follow-up uses `0059` after the readiness audit found Track F already owns `0049`.
* **Queue durability** — `message_queue.message_type` distinguishes `inbound_message`, `trigger_event`, and `continuous_task`; Phase 0 keeps `agent_id` and `sender_key` non-null.
* **Trigger-event dedupe** — `channel_event_dedupe` stores tenant-scoped idempotency outcomes with audit-style retention.
* **Container ports** — `backend/services/container_runtime.py` owns inclusive `PORT_RANGES` for dynamically managed services, including Whisper/Speaches on `6400-6499` and SearXNG on `6500-6599`.
* **Track D ASR completion** — `backend/models.py` now includes `ASRInstance`, `backend/models_rbac.py` adds `Tenant.default_asr_instance_id` (migration `0059`, intentionally after Track A `0051` because Track F owns `0049`), and `backend/services/whisper_instance_service.py`, `backend/services/whisper_container_manager.py`, and `backend/api/routes_asr_instances.py` provide the tenant-scoped Whisper/Speaches lifecycle plus `/api/settings/asr/default`. `audio_transcript.py` now resolves `audio_transcript.config.asr_mode` (`openai` / `tenant_default` / `instance`) so agents can stay on OpenAI Whisper, follow the tenant default, or pin a specific local ASR instance. Frontend delivery includes `/settings/asr`, the Audio Agents Wizard, the regular Agent Wizard audio step, and Agent Skills Manager.
* **Sentinel detection defaults** — `continuous_agent_action_approval` is registered as a first-class detection type and exposed through `/api/sentinel/detection-types`. Alembic `0055` widens Sentinel detection-type log/cache columns to 64 characters so this long detection id can be cached and audited without truncation.
* **Visual regression baseline** — `npm --prefix frontend run test:visual` runs the committed frontend entrypoint screenshots; runtime traces and reports stay under `.private/qa/v0.7.0/`.
* **Phase 0.5 fixture gate** — `backend/tests/test_phase0_5_fixtures.py` validates the committed ASR clips, while `backend/dev_tests/export_gmail_oauth_fixture.py` and `backend/tests/test_gmail_oauth_fixture.py` share the canonical `backend/tests/fixtures/gmail_oauth.enc` path, fail closed on missing decryption material, require a real Gmail integration re-authorized with both `gmail.readonly` and `gmail.send`, let the Hub Gmail re-authorize action request that send scope without a curl-only workaround, and resolve the Google token-encryption key from the live config store when env-only lookup is unavailable. Phase 3.1 draft validation later adds the stricter `gmail.compose` requirement because Gmail drafts are not covered by `gmail.send` alone.

### 2.5 v0.7.0 Wave 1 checkpoint (Track A backend + Track F0 prep)

The first Wave 1 merge on `release/0.7.0` is intentionally a backend-first checkpoint, not the full release feature set.

* **Entry-point split** — `backend/channels/base.py` now defines `EntryPoint` / `Channel`, `backend/channels/trigger.py` adds `Trigger`, and `backend/channels/registry.py` plus `backend/channels/dispatch.py` distinguish conversational send paths from trigger callbacks.
* **Webhook is now cataloged as a trigger** — `backend/channels/catalog.py` exposes separate `CHANNEL_CATALOG` and `TRIGGER_CATALOG`; `GET /api/channels` no longer lists webhook while `GET /api/triggers` does, and canonical webhook CRUD lives under `/api/triggers/webhook/*`.
* **Default-agent v2 foundation** — Alembic `0046` adds per-instance `default_agent_id` columns plus `user_channel_default_agent`, and `backend/services/default_agent_service.py` centralizes channel-vs-trigger resolution while preserving legacy reverse-FK bindings as fallback during the migration window.
* **Hub communication split** — the Hub Communication page now renders dedicated **Communication Channels** and **Webhook Triggers** sections, and the guided `+ Add Channel` launcher excludes webhook.
* **Phase 6 prep-only hardening** — `backend/agent/agent_service.py` now routes tool-call parsing through one boundary, and `backend/agent/skills/skill_manager.py` audits reserved config keys ahead of scratchpad / queue metadata work. No agentic-loop schema/API changes have landed yet.

### 2.6 v0.7.0 Wave 1 checkpoint (Track G Gmail send foundation)

The first Gmail-send slice is also merged on `release/0.7.0`, but it is still a checkpoint rather than the full Phase 3 email-trigger flow.

* **Outbound Gmail operations** — `backend/hub/google/gmail_service.py`, `backend/services/email_command_service.py`, and `backend/agent/skills/gmail_skill.py` now support send, reply, and draft actions in addition to read/search/list operations.
* **Fail-closed outbound scopes** — send/reply now require a Gmail send-compatible scope (`gmail.send`, `gmail.compose`, `gmail.modify`, or `mail.google.com/`), while draft creation requires a draft-compatible scope (`gmail.compose`, `gmail.modify`, or `mail.google.com/`). Older read-only OAuth tokens stay readable but cannot send until the tenant reauthorizes.
* **Hub/API reauth contract** — Gmail reauthorization surfaces request `include_send_scope=true`, which now adds both `gmail.send` and `gmail.compose`, so the upgrade path for full outbound send + draft support is explicit in both API and UI flows.
* **User-facing capability copy** — the Gmail setup wizard and `/email info` output now distinguish between "send/reply only" and full "send + draft" readiness instead of assuming `gmail.send` covers every outbound action.
* **Regression coverage** — `backend/tests/test_gmail_send_phase3_checkpoint.py` covers send, reply, draft, and scope-gating behavior. `backend/tests/test_gmail_send_phase3_live_gate.py` is an opt-in root-only live proof that stays skipped unless `TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1` is set; once enabled, it fails if the fixture lacks a draft-compatible Gmail scope. The fixture was reauthorized with `gmail.compose` for `mv@archsec.io` during the Phase 3 exit gate, and the live proof now covers direct send, direct reply, `GmailSkill` send, and draft creation. The optional agent-chat/API proof still requires `TSN_RUN_GMAIL_AGENT_CHAT_LIVE_GATE=1` plus API endpoint/token/agent env vars.

### 2.7 v0.7.0 Wave 1 checkpoint (Track A Phase 1 control plane)

Track A Phase 1 now has the routing-control surfaces needed before continuous-agent work can stack on top.

* **Persisted email trigger rows** — Alembic `0051` adds `EmailChannelInstance`, and Alembic `0061` adds `trigger_criteria` so Gmail-backed trigger rows persist the same criteria/query/definition envelope used by Jira and the other trigger types. `backend/api/routes_email_triggers.py` exposes CRUD, test-query, poll-now, triage, and managed notification endpoints for rows with a trigger name, Gmail integration, per-trigger `default_agent_id`, optional Gmail search query, poll interval, and active/paused status.
* **Default-agent control plane** — `backend/api/routes_default_agents.py` plus `/settings/default-agents` expose tenant defaults, per-instance channel defaults, per-instance trigger defaults, and per-user channel overrides while keeping resolution centralized in `backend/services/default_agent_service.py`.
* **Hub trigger launcher** — `frontend/components/ui/Wizard.tsx`, `frontend/components/triggers/TriggerWizard.tsx`, and `frontend/components/triggers/EmailTriggerWizard.tsx` add a real Trigger setup path under Hub → Communication. Email is now trigger-only; Gmail account resources continue to live under Hub → Productivity.
* **Agent Studio cleanup** — `/agents` no longer edits the tenant default inline. It shows the current default agent as a read-only indicator and links to `/settings/default-agents`.
* **Drift protection** — `backend/tests/test_wizard_drift.py` now cross-checks the Trigger wizard fallback against `TRIGGER_CATALOG`, in addition to the existing channel/productivity/provider guards.

### 2.8 v0.7.0 Track A2 Continuous-Agent Control Plane

Track A2 is a backend-first contract checkpoint. It adds the schema and read surfaces that later Email/Jira/GitHub/Schedule trigger tracks and Track C UI consume.

* **Migrations** — Alembic `0047_add_continuous_agent_models.py` intentionally revises current release head `0059`, and `0050_add_channel_event_rule.py` revises `0047`, keeping one linear chain while preserving Track A2's allocated revision IDs.
* **Models** — `delivery_policy`, `budget_policy`, `continuous_agent`, `continuous_subscription`, `wake_event`, `continuous_run`, and `channel_event_rule` are tenant-scoped. `continuous_run.wake_event_ids` and `continuous_run.agentic_scratchpad` are JSONB in `0047`; Track F later adds scratchpad only to `conversation_thread`.
* **Read-only APIs** — this checkpoint exposes `GET /api/continuous-agents`, `GET /api/continuous-agents/{id}`, `GET /api/continuous-runs`, `GET /api/continuous-runs/{id}`, `GET /api/wake-events`, and `GET /api/wake-events/{id}`. Write endpoints for continuous agents/runs/wake events are intentionally deferred. Pagination shape is `items`, `total`, `limit`, `offset`.
* **Auth and permissions** — continuous-agent list/detail uses session cookie, UI Bearer JWT, OAuth2 API-client Bearer JWT, or `X-API-Key` via the shared auth stack. `/api/continuous-agents*` requires `agents.read`; `/api/continuous-runs*` and `/api/wake-events*` require `watcher.read`. The standard `api_readonly`, `api_member`, `api_admin`, and `api_owner` client roles include `watcher.read` for these read surfaces. Missing tenant context fails closed with `403`; cross-tenant detail access returns `403`.
* **Payload contract** — `wake_event` stores no inline payload in A2. Trigger adapters must redact/store payloads separately and set `payload_ref` to an opaque local path under `backend/data/wake_events/` or a future blob key. There is no payload fetch endpoint in A2.
* **Status enums** — `continuous_agent.status`: `active`, `paused`, `disabled`, `error`; `continuous_subscription.status`: `active`, `paused`, `disabled`, `error`; `wake_event.status`: `pending`, `claimed`, `processed`, `filtered`, `failed`; `continuous_run.status`: `queued`, `running`, `succeeded`, `failed`, `cancelled`, `skipped`; `delivery_policy.importance_threshold`: `low`, `normal`, `high`; `budget_policy.on_exhaustion`: `pause`, `degrade_to_hybrid`, `notify_only`; `continuous_agent.execution_mode`: `autonomous`, `hybrid`, `notify_only`.
* **Routing rules** — channel routing rules use the generic route shape `/api/channels/{channel_type}/{instance_id}/routing-rules` with list/create/get/update/delete for conversational channels (`whatsapp`, `telegram`, `slack`, `discord`). The plan's Slack example maps directly to `POST /api/channels/slack/{id}/routing-rules`. The API validates both channel instance ownership and target-agent ownership before writes. Trigger details remain per-type APIs such as `/api/triggers/email` and `/api/triggers/webhook` in A2.
* **Budget/Sentinel/Watcher hooks** — `ContinuousBudgetLimiter` extends the shared sliding-window limiter with a `budget_kind` dimension and returns `pause`, `degrade_to_hybrid`, or `notify_only` decisions. Gmail send/reply/draft checks Sentinel's `continuous_agent_action_approval` detection only when an explicit continuous-agent context is present. `WatcherActivityService` now emits `type=continuous_run`, `run_type=continuous` events for later UI badging.

### 2.9 v0.7.0 Wave 3A Track C/F checkpoint

Wave 3A connects the stable A2 read contracts to UI surfaces and lands the first real Track F agentic-loop core without enabling broad write-side continuous-agent workflows yet.

* **Track F migrations** — Alembic `0049` adds `conversation_thread.agentic_scratchpad` and the five `agent_skill` tool-result toggles: `auto_inject_results`, `skip_ai_on_data_fetch`, `max_result_bytes`, `max_results_retained`, and `max_turns_lookback`. Alembic `0057` adds `Config.platform_min_agentic_rounds` / `platform_max_agentic_rounds`; Alembic `0058` adds `Agent.max_agentic_rounds` and `max_agentic_loop_bytes`. The default `max_agentic_rounds` is `1` to preserve single-shot behavior unless a caller opts into additional rounds.
* **Structured DATA reuse** — tool results can be retained in thread scratchpad form, bounded by per-skill byte/count/lookback controls, and injected into follow-up prompts as structured DATA. The follow-up detector recognizes common English and Portuguese references while fresh-fetch phrases still force a new tool call.
* **API v1 scratchpad contract** — async queue polling returns a top-level `agentic_scratchpad` only when `GET /api/v1/queue/{queue_id}?include_scratchpad=true` is used. Nested `result.agentic_scratchpad` is redacted regardless of the flag so older clients do not accidentally receive internal loop traces.
* **Movl follow-up behavior** — the Gmail follow-up path now answers from the prior structured DATA block when the user asks a referential question such as which prior email is most important. The second turn records no fresh Gmail tool call and preserves the prior scratchpad.
* **Track C read-only pages** — `/continuous-agents`, `/continuous-agents/{id}`, `/hub/wake-events`, `/hub/triggers/email/{id}`, and `/hub/triggers/webhook/{id}` read from existing A2/trigger APIs. Wake-event UI displays payload references and does not expose inline payload JSON.
* **Hub routing rules** — Hub Communication exposes routing-rule management only for conversational channels (`whatsapp`, `telegram`, `slack`, `discord`). Email and webhook remain trigger-detail surfaces, not channel routing-rule surfaces.
* **Watcher and onboarding** — Watcher activity accepts `type=continuous_run`, and the 16-step onboarding tour now includes a "Triggers & Continuous Agents" step before the finale with a CTA into Hub Communication's Triggers section.

### 2.10 v0.7.0 Track B Trigger Dispatch Foundation

Track B starts with a no-migration dispatch foundation before Jira, Schedule, and GitHub adapter tables are introduced.

* **Shared dispatch contract** — trigger adapters normalize events into a common dispatch input with `trigger_type`, `instance_id`, `event_type`, `dedupe_key`, `occurred_at`, payload, importance, and optional sender/source metadata. `TriggerEvent.event_type` is explicit while `trigger_type` remains available for existing trigger contracts.
* **Tenant authority** — dispatch always resolves the tenant from persisted trigger instance rows such as `webhook_integration` or `email_channel_instance`. External payloads never provide tenant authority, and cross-tenant instance or agent references fail closed.
* **Dedupe ledger** — dispatch records accepted outcomes in `channel_event_dedupe`. A duplicate unique key returns deterministic duplicate behavior without creating a second wake event.
* **Wake evidence** — matching active `continuous_subscription` rows produce `wake_event` rows and queued `continuous_run` rows. Wake payload content stays out of row; dispatch stores a redacted JSON payload under `backend/data/wake_events/` and exposes only `payload_ref`.
* **Webhook compatibility** — signed webhook inbound requests keep returning `202` with `{status, queue_id, poll_url}` for the existing direct queue-to-agent path. The dispatch foundation can dual-write wake/run evidence for continuous-agent subscribers without replacing the direct queue behavior.
* **Breadth handoff** — the dispatch foundation is now consumed by Jira, Schedule, GitHub, and Webhook criteria in Track B breadth. `continuous_task` queue dispatch remains reserved until intentionally implemented.

### 2.11 v0.7.0 Track B Trigger Breadth

Track B breadth turns the dispatch foundation into user-facing trigger adapter rows and Hub UI. It establishes the Jira/Schedule/GitHub CRUD contracts, criteria surfaces, and normalization tests; live Jira polling plus the managed WhatsApp notifier are finalized in the release sign-off slice described below.

* **Migrations** — `0052_add_jira_trigger_and_webhook_criteria.py` revises `0058`, `0053_add_schedule_trigger_instance.py` revises `0052`, and `0054_add_github_trigger_instance.py` revises `0053`.
* **Trigger rows** — `JiraChannelInstance`, `ScheduleChannelInstance`, and `GitHubChannelInstance` store tenant-scoped source config, encrypted credentials/secrets where applicable, default-agent references, health snapshots, cursors, and active/paused state.
* **Webhook criteria** — Webhook trigger rows now carry optional `trigger_criteria`. JSONPath matchers are evaluated before subscription matching; failed criteria write `filtered_out` dedupe evidence and do not create wake/run rows.
* **Runtime adapters** — Jira has the persisted trigger row, JQL test-query, encrypted credential handling, and issue normalization contract; Schedule polls due cron rows without creating legacy `ScheduledEvent` duplicates; GitHub validates `X-Hub-Signature-256` deliveries before dispatching through `TriggerDispatchService`.
* **Hub UI** — Hub → Communication now supports Email, Webhook, Jira, Schedule, and GitHub trigger setup. Jira/Schedule/GitHub have compact creation flows, cards, `/hub/triggers/{type}/{id}` detail pages, criteria tabs, recent wake-event tabs, and wake-event filters. Webhook setup/edit/detail flows share the same criteria builder and can test JSONPath criteria against a sample payload before saving.

### 2.11.1 v0.7.0 Jira Trigger Finalization

The final Jira release contract completes the gap left by Track B breadth: Jira triggers are not just saved and tested in the UI; active rows are polled against Jira Cloud JQL on their configured interval, matching issues are dispatched through `TriggerDispatchService`, and duplicates are suppressed so the same issue creates at most one wake/run.

* **Placement** — Jira setup and detail remain under Hub → Communication → Triggers. Jira is an event trigger, not a conversational channel; WhatsApp remains the outbound communication channel used by the managed notifier.
* **Credentials** — Jira site URL, auth email, and API token are captured through the Hub setup/edit/test-query flow. Tokens are stored encrypted and API reads return only a masked preview. Documentation, QA artifacts, browser traces, and logs must not include plaintext Jira tokens.
* **Polling and dedupe** — the poll loop fetches matching JQL results, normalizes issue payloads, dispatches wake evidence, updates cursor/activity state, and records a deterministic dedupe key per issue so repeated polls and later ticket updates do not double-fire.
* **Managed WhatsApp notifier** — the release includes a managed notifier path for Jira issue events. It sends one WhatsApp notification per deduped Jira issue through a tenant-owned WhatsApp instance to an operator-provided recipient, and fails closed when the recipient is omitted or the selected channel is missing, paused, or not owned by the tenant.
* **Validation evidence** — release QA includes targeted backend coverage for live Jira polling and once-per-issue dedupe, tenant/credential safety checks, notifier success and failure paths, browser coverage for Hub Jira setup/detail plus wake-event evidence, and a live poll-now duplicate-suppression smoke.

### 2.12 v0.7.0 Phase 3 Email Trigger/Triage Checkpoint

Phase 3 now has a runtime checkpoint plus live exit-gate evidence on the release branch. Live Gmail evidence is scoped to the allowed fixture accounts `mv@archsec.io` and `movl2007@gmail.com`; the current committed fixture uses `mv@archsec.io`.

* **Gmail outbound** — `GmailService`, `EmailCommandService`, and `gmail_skill` support send/reply/draft operations with fail-closed scope checks. Send/reply accept Gmail send-compatible scopes; draft creation requires `gmail.compose`, `gmail.modify`, or `mail.google.com/`.
* **Email trigger control plane** — `EmailChannelInstance` and `/api/triggers/email` CRUD persist Gmail-backed trigger rows with search query, shared trigger criteria, poll interval, active/paused state, and default-agent routing.
* **Runtime polling** — `backend/channels/email/trigger.py` polls active Gmail-backed Email triggers, fetches message deltas through Gmail list/search APIs, normalizes payloads, advances a stable cursor, rejects missing/foreign/inactive Gmail integrations, and dispatches wake events through `TriggerDispatchService`.
* **Managed triage and notification actions** — `POST /api/triggers/email/{id}/triage-subscription` creates/reuses a system-owned continuous agent/subscription for draft-based triage. `POST /api/triggers/email/{id}/notification-subscription` creates/reuses a system-owned Email WhatsApp notifier with an explicit operator-provided recipient in `continuous_subscription.action_config = { action_type: "whatsapp_notification", channel: "whatsapp", recipient_phone }`; omitted recipients fail closed before subscription creation. Both actions consume the same `email.message.received` wake evidence; triage creates Gmail drafts through `GmailSkill`, while the notifier sends deterministic WhatsApp summaries and marks the `ContinuousRun` plus `WakeEvent` succeeded/failed.
* **MemGuard hook** — trigger dispatch now runs a Sentinel-config-gated heuristic pre-check over redacted payload text. Matches record the dedupe outcome as `blocked_by_security` and emit no wake event or continuous run.
* **Hub UI** — the Email trigger setup/detail flow includes source matching, persisted criteria JSON, saved query tests with sample messages, manual poll-now, recent wake events, managed WhatsApp notification setup, managed triage setup, and clear draft-scope messaging when `gmail.compose` is missing.
* **Evidence** — see `docs/qa/v0.7.0/phase-3-email-trigger-triage-summary.md` for the exit evidence and remaining risks. The opt-in live proof is `backend/tests/test_email_trigger_phase3_live_gate.py`; it remains skipped by default and, when enabled, proves live poll/dedupe, one wake/run, managed draft creation, and Sentinel/MemGuard block behavior.

### 2.13 v0.7.0 Phase 8 UI polish and control-plane UX

Phase 8 finishes the v0.7.0 trigger/control-plane UX pass and keeps user guidance aligned with the channel-vs-trigger split.

* **Trigger criteria registry** — Email, Webhook, Jira, Schedule, and GitHub trigger setup/detail surfaces use trigger-aware helper controls while preserving raw JSON editing. Webhook keeps the JSONPath payload tester on the detail page.
* **Wake-event API/UI** — `GET /api/wake-events` accepts `occurred_after` and `occurred_before` alongside existing `status`, `channel_type`, and `channel_instance_id` filters. `GET /api/wake-events/{id}/payload` returns only the already-redacted payload behind `payload_ref`, with tenant ownership and safe-path validation. `/hub/wake-events` adds date filters, selectable rows, and a payload/cause drawer.
* **Routing-rule reorder** — `POST /api/channels/{channel_type}/{instance_id}/routing-rules/reorder` accepts `{ "rule_ids": [...] }`, validates every rule belongs to the current tenant/channel/instance, and returns the refreshed rule page. Hub Communication exposes modal create/edit/delete plus reorder controls for conversational channels only.
* **Watcher wake polish** — continuous-agent detail/read-only watcher views show wake-event causes, subscription badges, and failure colors for trigger-origin runs.
* **Wizard retrofit** — Slack, Discord, WhatsApp, and MCP setup flows now share the common `<Wizard>` shell without changing their backend create/test contracts.
* **Onboarding count and copy** — `frontend/contexts/OnboardingContext.tsx` remains at `TOTAL_STEPS = 16`. `frontend/components/OnboardingWizard.tsx` presents conversational channels separately from event triggers, keeps Webhook out of channel setup copy, and sends the Triggers & Continuous Agents CTA to `/hub?tab=communication`, where the Hub Triggers section is marked with `data-testid="hub-triggers-section"`.
* **Webhook deprecation** — v0.7.0 intentionally has no Webhook deprecation banner/header path; Webhook moved directly to the Trigger catalog and Hub Triggers UI.
* **Kokoro successor path** — legacy `/api/services/kokoro/{start,stop,status}` callers receive HTTP 410 and a `Link: </api/tts-instances>; rel="successor-version"` successor header. Hub copy points users to per-tenant Kokoro instances rather than the removed stack-level compose service.
* **Phase 3 docs reconciliation** — Phase 3.1 docs now distinguish the completed Gmail send/reply/draft and Email poll/triage/MemGuard live gates from the remaining optional API-agent proof and Ubuntu fresh-install sudo handoff.
* **Evidence** — see `docs/qa/v0.7.0/phase-8-ui-polish-summary.md`. Fresh-install Ubuntu VM validation remains a Phase 9 blocker until sudo access is available.

---

## 3. Quick Start

### 3.1 Prerequisites

* Docker Engine 20.10+ and Docker Compose V2
* Python 3.8+ with pip (installer only)
* Git
* At least 4 GB RAM available
* A domain name (only if deploying with Let's Encrypt SSL)

Sources: `README.md:17-22`, `docs/docker.md:33-36`.

### 3.2 Clone and install

```bash
git clone https://github.com/iamveene/Tsushin.git
cd Tsushin

# Interactive install (prompts for ports, access type, SSL)
python3 install.py

# Unattended with self-signed HTTPS, auto-detected IP
python3 install.py --defaults

# Unattended with Let's Encrypt (public domain required)
python3 install.py --defaults --domain app.example.com --email you@example.com

# Unattended with Let's Encrypt STAGING (for testing — avoids production rate limits)
python3 install.py --defaults --domain app.example.com --email you@example.com --le-staging

# Unattended HTTP-only (dev/test only — insecure)
python3 install.py --defaults --http

# Custom ports
python3 install.py --port 9090 --frontend-port 3031
```

Source: `README.md:29-48`, `install.py:38-96`. `--http` and `--domain` are mutually exclusive and both require `--defaults`; `--le-staging` requires `--domain`.

#### SSL/TLS modes and troubleshooting

The installer supports four SSL modes, all served through Caddy. Let's Encrypt issuance and renewal is handled by Caddy's built-in ACME client — no separate certbot container is involved.

| Mode | When to use | Cert location |
|---|---|---|
| `disabled` | Local dev behind a VPN, or isolated test harnesses. Ports 80/443 are NOT bound; frontend/backend are exposed on the configured ports. | n/a |
| `selfsigned` | Default for `--defaults` installs without `--domain`. Works on IP-address hosts (e.g., LAN VMs at `10.211.55.5`). Browsers will show a security warning until the cert is trusted. | `caddy/<stack>/certs/selfsigned.{crt,key}` |
| `letsencrypt` | Public-facing deployment with a real domain pointing at this server. Requires ports 80 and 443 reachable from the internet. | Caddy-managed in the `caddy-data` volume |
| `manual` | You already have a cert issued by your own CA or a public CA. Supports an optional chain/intermediate bundle. | `caddy/<stack>/certs/{cert,key}.pem` |

**Self-signed on IP-address hosts.** When the domain passed to the installer is an IPv4/IPv6 literal, the generated certificate's `subjectAltName` now uses the `IP:` entry type (`IP:10.211.55.5`). Emitting `DNS:10.211.55.5` is invalid per RFC 5280 and causes browsers to show `NET::ERR_CERT_COMMON_NAME_INVALID`. The Caddyfile's `default_sni` also falls back to `localhost` for IP installs because Caddy rejects IP literals as SNI values.

**Let's Encrypt pre-flight.** Before writing the Caddyfile, the installer (a) resolves the domain via DNS, (b) optionally fetches the server's public IP via `api.ipify.org` and compares it against the resolved IPs, and (c) performs a plain HTTP HEAD on port 80 (the ACME HTTP-01 challenge path). Mismatches and unreachable hosts surface as warnings — valid configurations behind Cloudflare proxy / CDN / NAT can still proceed.

**LE rate-limit recovery.** Production LE limits each account+hostname pair to 5 failed validations per hour. If you hit this limit, re-run the installer with `--le-staging` to test against the staging environment (which has much higher limits) until your setup resolves validation correctly, then repeat without `--le-staging` for a trusted production certificate.

**Manual-cert validation.** The installer validates the cert/key pair before copying it into the Caddy cert directory:

- Key and cert public keys must match — mismatch is a hard error.
- Cert must not be expired — expired is a hard error; expiring within 30 days is a warning only.
- Cert SAN/CN must cover the configured domain — otherwise the installer asks for confirmation before proceeding.
- Optional chain file is parsed and its first cert's subject is compared to the leaf cert's issuer for basic sanity.

When a chain file is supplied, the installer concatenates `cert + chain` into the destination `caddy/<stack>/certs/cert.pem` (Caddy reads a single bundled PEM — no Caddyfile change needed).

**Common errors and fixes.**

- `tls: private key does not match certificate` at Caddy startup → cert/key pair mismatch. The installer now catches this before deploy and refuses to continue.
- Browser shows `NET::ERR_CERT_COMMON_NAME_INVALID` on an IP-based self-signed install → regenerate the cert with the updated installer; the SAN will now contain `IP:<addr>` instead of `DNS:<addr>`.
- Frontend API calls 404 or hit CORS after switching SSL mode → historically caused by the Next.js image caching `NEXT_PUBLIC_API_URL`. The installer now detects changes to this value and runs `docker compose build --no-cache frontend` before restarting.

#### New `.env` key

- `SSL_LE_STAGING` (blank or `true`) — when `true`, the generated Caddyfile injects `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` so Caddy issues certs from LE staging instead of production.

For a remote Ubuntu VM, use the normal user flow: clone the repo on the VM, install Docker plus Docker Compose v2, and run `python3 install.py` from the repository root on that VM. For remote HTTP installs, the installer's final success output uses the public host/IP you entered rather than `localhost`.

For the Parallels audit VM workflow (`parallels@10.211.55.5`), the repository now includes a helper sync script:

```bash
bash deploy-to-vm.sh
```

The script verifies SSH connectivity, checks remote Docker plus Compose, ensures `requests` and `cryptography` are available on the VM, and rsyncs the repository to `~/tsushin` with the usual large/local-only paths excluded (`.git/`, `.private/`, `backend/data/`, `frontend/.next/`, `node_modules/`, logs, backups, and `.env`). After the sync, SSH to the VM and run `sudo python3 install.py` from `~/tsushin`.

The installer automatically:

1. Installs `requests` and `cryptography` via pip.
2. Creates the `tsushin-network` Docker bridge if absent.
3. Generates `.env` with random `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `TSN_MASTER_KEY`.
4. Sets `HOST_BACKEND_DATA_PATH` to the absolute host path of `backend/data` (required for Docker-in-Docker volume mounts).
5. Builds backend + frontend images and starts the stack.
6. (If SSL) Generates `caddy/<stack-name>/Caddyfile` with stack-scoped upstreams plus matching self-signed cert or Let's Encrypt configuration.

Source: `install.py:49-53`, `docker-compose.yml:131-134` (HOST_BACKEND_DATA_PATH is required in `.env`).

### 3.3 Complete setup via browser

Open the URL printed at the end of install (e.g. `https://localhost`, `http://localhost:3030`, or `http://<public-host>:3030` for remote HTTP) and finish the `/setup` wizard:

1. Create admin account + organization.
2. Configure at least one AI provider API key (Gemini, Claude, OpenAI, Groq, Grok, DeepSeek, Ollama, OpenRouter).
3. The wizard automatically creates **ProviderInstance** records for each supported provider key entered during setup. The selected primary provider is also assigned as the **System AI** — no manual post-setup Hub provisioning is required for the providers entered in the wizard.
4. At completion, the wizard reveals an auto-generated **global admin** email/password pair. Record these credentials before leaving the completion screen; they are required for `/system/*` validation and system-level administration.
5. On first login an **onboarding tour** (16 steps) auto-opens. Steps 1 and 6–11 walk through platform areas (Welcome → Watcher → Studio → Hub → Channels → Flows → Playground). Steps 2–5 are a **"What's New in v0.6.0"** showcase covering (2) the expanded AI provider catalogue — Vertex AI, Grok, Groq, ElevenLabs — (3) Slack / Discord channels plus Webhook Triggers, (4) Custom Skills & MCP Servers, and (5) A2A agent-to-agent permissioning plus external vector stores for long-term memory. Steps 12–15 cover optional voice setup, Playground Mini, Sentinel block mode, and v0.7.0 Triggers & Continuous Agents. Step 16 is the "You're All Set" finale. Each showcase step includes a one-click deep-link to the relevant Hub tab or sub-page.
6. The tour highlights mandatory next steps: **connect a communication channel** (WhatsApp, Telegram, Slack, or Discord) via the Hub to enable agent messaging. Signed HTTP events use the separate Webhook Trigger path in Hub → Communication.
7. The **User Guide** is accessible anytime via the **?** button in the header.

**LLM provider keys are configured per-tenant through the Hub UI — not in environment variables.** This enables multi-tenant isolation. Source: `README.md:398`.

The fresh-install regression checklist used on the Ubuntu VM is maintained as an internal deployment playbook. The current checklist covers 13 first-run cases: infrastructure health, tenant/global-admin login, Watcher, Studio, Playground basic chat, Memory Inspector, Flows, Hub, all 15 Settings routes, the 4 System admin routes, conditional Browser Automation, and final log review.

For remote Ubuntu VM installs that use a host-level Ollama daemon, start with `http://host.docker.internal:11434` inside Tsushin. If the Docker engine on that host does not resolve `host.docker.internal`, use the container bridge gateway instead (for example `http://172.18.0.1:11434`) and re-test the provider instance from the Hub.

For repetitive QA runs, auth throttling can be raised or temporarily disabled without code changes by setting `TSN_AUTH_RATE_LIMIT` or `TSN_DISABLE_AUTH_RATE_LIMIT=true` in `.env` before recreating the backend container. This is intended for test automation and should not be left enabled on public production installs.

**Installer re-runs are idempotent (v0.6.1):** running `python3 install.py` a second time against an existing install preserves `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, and `ASANA_ENCRYPTION_KEY` from the current `.env`. Fresh values are only generated on true first installs (no existing `.env`) or when a specific key is missing. This prevents the pre-v0.6.1 failure mode where re-runs rotated the postgres password while the postgres data volume still carried the old one — producing `FATAL: password authentication failed for user "tsushin"` and a backend crash loop. Source: `install.py:1317-1339`.

### 3.4 Verify health

```bash
curl http://localhost:8081/api/health      # Liveness (lightweight)
curl http://localhost:8081/api/readiness   # Readiness (checks PostgreSQL)
docker compose ps                          # Container states
```

Source: `backend/api/routes.py:70` (health), `backend/api/routes.py:84` (readiness).

---

## 4. Deployment & Operations

### 4.1 Docker Compose (development / single-host)

Standard lifecycle (**always from the repository root**, never a worktree):

```bash
cd /path/to/tsushin

# Start
docker compose up -d

# Rebuild specific service after code changes
docker compose build --no-cache backend
docker compose up -d backend
docker compose build --no-cache frontend
docker compose up -d frontend

# Logs
docker compose logs -f backend
docker compose logs --tail=100 backend

# Stop without removing network (SAFE)
docker compose stop backend

# Local TTS (Kokoro): no compose profile. Configure a per-tenant instance at
#   Hub → Kokoro TTS → Setup with Wizard.
# The legacy `docker compose --profile tts up -d` path was removed in v0.7.0.

# Tester note
# The current repo does not define a `testing` compose profile.
# Hub tester controls resolve a legacy tester container when present,
# or the active runtime tester instance for the tenant.
```

Source: `docs/docker.md:114-169`. (The `tts` compose profile was removed in v0.7.0 — Kokoro runs as per-tenant auto-provisioned instances now.)

### 4.2 Container rebuild safety (SAFE vs UNSAFE)

**SAFE:** `docker compose build --no-cache <service>` followed by `docker compose up -d <service>` rebuilds individual services without touching the `tsushin-network` bridge. MCP WhatsApp bot containers keep their WebSocket sessions alive.

**UNSAFE:** `docker compose down` — the external network now survives it, but it still stops and removes the compose-managed services. You should avoid `down` for routine rebuilds; only use it when you genuinely need to reset Postgres or recreate containers from scratch.

**Session recovery if WhatsApp drops:**

```bash
docker logs mcp-agent-tenant_<id> --tail=10   # Look for QR-code re-auth loop
docker restart mcp-agent-tenant_<id>          # Restart, then re-scan QR from phone
```

### 4.3 Kubernetes / GKE (Helm chart)

Tsushin ships a Helm chart at `k8s/tsushin/`:

```
k8s/tsushin/
├── Chart.yaml              # name: tsushin, version: 0.1.0, appVersion: 0.6.0
├── values.yaml             # Default values
├── values-dev.yaml         # Dev overrides
├── values-prod.yaml        # Prod overrides (HPA, network policies, managed TLS)
└── templates/              # K8s manifest templates
```

Source: `k8s/tsushin/Chart.yaml:1-15`.

K8s mode is activated by setting `TSN_CONTAINER_RUNTIME=kubernetes`. The backend then uses the **K8sRuntime** backend (`backend/services/container_runtime.py:848-849, 1772`) which maps Docker operations (create, start, stop, exec) to K8s Deployments, Services, and `kubectl exec` API. Namespace and image-pull policy are controlled by `TSN_K8S_NAMESPACE` (default `tsushin`) and `TSN_K8S_IMAGE_PULL_POLICY` (default `IfNotPresent`). Source: `backend/settings.py:147-148`.

Features of the Helm chart (per `README.md:261-268`):

* Cloud SQL Proxy sidecar for managed PostgreSQL.
* Horizontal Pod Autoscaler (HPA).
* Network policies for east-west traffic control.
* Managed TLS via GCP-managed certificates.
* `/api/readiness` as the K8s readiness probe, `/api/health` as liveness.
* Prometheus metrics scraped from `/metrics`.
* Structured JSON logs via `TSN_LOG_FORMAT=json`.

### 4.4 GCP Secret Manager backend

Tsushin's secret retrieval is abstracted behind a `SecretProvider` interface. Activate the GCP provider with `TSN_SECRET_BACKEND=gcp` (default is `env`, which reads `os.environ`).

Source: `backend/services/secret_provider.py:286-304`, `backend/settings.py:19-24`.

GCP provider features (`services/secret_provider.py:148-267`):

* **Bootstrap env vars** (always read directly from `os.environ`, not from the provider): `TSN_GCP_PROJECT_ID` (**required**, hard-fails if unset), `TSN_GCP_SECRET_PREFIX` (default `tsushin`), `TSN_GCP_SECRET_VERSION` (default `latest`), `TSN_GCP_SECRET_CACHE_TTL` (seconds, default `300`).
* **Thread-safe TTL cache** — cached secrets are reused across workers within `TSN_GCP_SECRET_CACHE_TTL`.
* **Parallel warm-up** at startup.
* **Three-tier fallback:** GCP Secret Manager → `os.environ` → default value. Used when GCP is briefly unavailable (`services/secret_provider.py:203, 228, 267`).

**Secret naming:** A key `JWT_SECRET_KEY` with prefix `tsushin` becomes GCP secret `tsushin_JWT_SECRET_KEY` (or similar — confirm naming convention with `services/secret_provider.py`). Source: `backend/settings.py:142-144`.

### 4.5 Startup & Seeding Sequence

`db.init_database()` runs on every backend startup (called from `main.py`). It is fully idempotent — running it on an already-initialised DB is safe.

**PostgreSQL path:**
1. `alembic upgrade head` — applies any pending schema migrations.
2. Fall-through to shared seeding block below.

**SQLite path (dev / fallback):**
1. `Base.metadata.create_all()` — creates tables from ORM metadata.
2. Legacy inline migrations (FTS5, sentinel column, MCP auth, Discord/Slack, remote-access).
3. Fall-through to shared seeding block below.

**Shared seeding block (both backends):**

| Step | Function | File | Notes |
|---|---|---|---|
| Default config | inline | `db.py` | Creates `Config` row if none exists. |
| RBAC defaults | `seed_rbac_defaults()` | `db.py` | Roles + permissions; idempotent. |
| RBAC upgrade | `ensure_rbac_permissions()` | `db.py` | Adds any permissions missing from older installs. |
| Slash commands | `seed_slash_commands()` | `db.py` | 36 system-wide commands (en, pt, …). |
| Project command patterns | `seed_project_command_patterns()` | `db.py` | 10 patterns. |
| Personas | `seed_default_personas()` | `services/persona_seeding.py` | 4 system personas. |
| Tone presets | `seed_default_tone_presets()` | `services/tone_preset_seeding.py` | 4 presets. |
| Shell security patterns | `seed_default_security_patterns()` | `services/shell_pattern_seeding.py` | |
| Sentinel config | `seed_sentinel_config()` + migrations | `services/sentinel_seeding.py` | Detection types, security profiles. |
| **Subscription plans** | `seed_subscription_plans()` | `services/plan_seeding.py` | 4 plans: free / pro / team / enterprise. **Added v0.6.1** — fixes PostgreSQL fresh-install gap. |

**Per-startup jobs** (called from `app.py` lifespan, not `init_database`):
- `backfill_shell_skill_all_tenants()` — ensures every agent has a shell skill row.
- `SandboxedToolSeeder.seed_all_tenants()` — upserts tool manifests from `backend/tools/manifests/*.yaml`.

---

### 4.6 Emergency Stop (tenant + global kill switches)

Two independent kill switches sit in the header and gate every ingress point (WhatsApp, Telegram, Slack, Discord, webhooks, API triggers). Either switch being `true` halts processing for the messages it covers.

| Scope | Storage | Permission | Endpoint (stop / resume) | What it halts |
|---|---|---|---|---|
| **Tenant** | `tenant.emergency_stop` | `org.settings.write` (tenant owners) | `POST /api/system/emergency-stop` / `POST /api/system/resume` | All channels/triggers for the caller's tenant only. Other tenants keep running. |
| **Global** | `config.emergency_stop` | `is_global_admin = true` (enforced by `require_global_admin()`) | `POST /api/system/global-emergency-stop` / `POST /api/system/global-resume` | Every tenant on the instance. Reserved for platform-wide incidents. |

`GET /api/system/status` returns both flags so the frontend can render the correct UI state:

```json
{
  "emergency_stop": false,          // legacy: tenant OR global, kept for older clients
  "tenant_emergency_stop": false,
  "global_emergency_stop": false,
  "is_global_admin": false,
  "tenant_id": "tenant_...",
  "tenant_name": "Tsushin QA",
  "maintenance_mode": false
}
```

**Enforcement points** (both flags checked at each; either true → block):
- `backend/mcp_reader/filters.py` — MCP ingress filter; `MessageFilter` takes a `tenant_id` kwarg (passed from `services/watcher_manager.py` as `instance.tenant_id`).
- `backend/agent/router.py` — router-level block; uses `self.tenant_id` already tracked on the `AgentRouter`. Log lines tagged `[EMERGENCY STOP:global]` vs `[EMERGENCY STOP:tenant]`.
- `backend/api/routes_webhook_inbound.py` — webhook inbound ingress; reads `integration.tenant_id` and returns HTTP 503 when blocked.

All three fail-open on DB errors — a transient outage never silently halts a tenant.

**UI behaviour** (`frontend/components/LayoutContent.tsx`):
- Tenant toggle (always visible for anyone with `org.settings.write`): green "Online" / red "Tenant Stopped". Confirmation modal names the tenant explicitly.
- Global toggle (only rendered when `user.is_global_admin`): purple "Global" / amber "Global Stopped" with a shield icon. Confirmation modal titled "Halt ALL Tenants?".
- When the global flag is true, the tenant toggle is disabled with tooltip "Blocked by GLOBAL stop" — prevents a tenant owner from resuming into a no-op.

Both flags are polled from `/api/system/status` every 10 seconds.

---

---

## 5. System Configuration

All runtime configuration is driven by environment variables prefixed with `TSN_`. Most variables have backward-compatible legacy names without the prefix. Secret retrieval is routed through the `SecretProvider` abstraction so the same code path works with plain `.env` files or external vaults.

Switch between providers with `TSN_SECRET_BACKEND`:

| Value | Provider | Notes |
|-------|----------|-------|
| `env` (default) | `EnvSecretProvider` | Reads `.env` and `os.environ`. |
| `gcp` | `GcpSecretManagerProvider` | Fetches from Google Secret Manager with a 3-tier fallback and in-memory cache (TTL `TSN_GCP_SECRET_CACHE_TTL`, default 300s). |

Source: `backend/settings.py:19-24`, `backend/services/secret_provider.py:148-267`.

**The complete alphabetised env-var reference, with defaults, purposes, and source citations, is in [Appendix A](#29-appendix-a-complete-environment-variable-reference).** The most critical variables every operator needs to set are:

| Variable | Purpose |
|----------|---------|
| `JWT_SECRET_KEY` | JWT signing key (required). Generate with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `TSN_MASTER_KEY` | Fernet key that wraps all per-service encryption keys stored in the DB. Required for SaaS deployments. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. |
| `DATABASE_URL` | PostgreSQL connection string (production). Defaults to SQLite for development. |
| `POSTGRES_PASSWORD` | Set by `install.py`; consumed by `tsushin-postgres` container. |
| `HOST_BACKEND_DATA_PATH` | Absolute host path of `./backend/data` — required for Docker-in-Docker volume mounts in dynamically spawned MCP/toolbox containers. |
| `TSN_APP_HOST` / `TSN_APP_PORT` | Backend bind address and port (defaults: `127.0.0.1` / `8081`). |
| `TSN_BACKEND_URL` / `TSN_FRONTEND_URL` | Public URLs used for OAuth callbacks and CORS. |
| `TSN_STACK_NAME` | Stack prefix used for compose services plus runtime-created vector-store, MCP, toolbox, and volume names. |
| `TSN_CORS_ORIGINS` | Comma-separated allowed origins. Defaults to `*` — restrict in production. |
| `TSN_AUTH_RATE_LIMIT` / `TSN_DISABLE_AUTH_RATE_LIMIT` | Auth throttle controls for login/signup/setup/reset/SSO. Use the disable flag only for QA/dev bursts. |
| `TSN_LOG_LEVEL` / `TSN_LOG_FORMAT` | Logging (`INFO` / `text`). Set `TSN_LOG_FORMAT=json` for structured logs. |

Configuration is grouped by subsystem in Appendix A:

1. Application & URLs
2. Database & storage
3. Authentication & encryption keys
4. Logging & observability
5. Channel behaviour
6. Cleanup & maintenance workers
7. OAuth token refresh worker
8. Channel health & circuit breakers
9. Container runtime (Docker/Kubernetes)
10. External services (Kokoro TTS, Groq, ElevenLabs)
11. GCP & Kubernetes specifics

## 6. Authentication & Access

### 6.1 Login flows

All authentication endpoints live under `/api/auth/` (`backend/auth_routes.py:69`). Rate limiting is enforced by `slowapi` (MED-004, `auth_routes.py:22-24, 66-67`) and is configurable per install via `TSN_AUTH_RATE_LIMIT`. QA or local development can temporarily disable those auth throttles with `TSN_DISABLE_AUTH_RATE_LIMIT=true`; the installer defaults HTTP-only / self-signed installs to a higher `30/minute` login ceiling while leaving public HTTPS installs on the stricter default.

| Method | Path | Purpose | Source |
|---|---|---|---|
| POST | `/api/auth/login` | Email + password login. Returns JWT in response body and in `tsushin_session` httpOnly cookie. | `auth_routes.py:245` |
| POST | `/api/auth/signup` | New-tenant signup (creates Tenant + Owner user). | `auth_routes.py:299` |
| GET | `/api/auth/setup-status` | Returns whether the `/setup` wizard has been completed. | `auth_routes.py:342` |
| POST | `/api/auth/setup-wizard` | One-shot bootstrap endpoint — creates first tenant + global-admin account. | `auth_routes.py:349` |
| POST | `/api/auth/password-reset/request` | Send password-reset email with token. | `auth_routes.py:624` |
| POST | `/api/auth/password-reset/confirm` | Consume reset token + set new password. | `auth_routes.py:648` |
| GET | `/api/auth/me` | Current user profile. | `auth_routes.py:683` |
| PUT | `/api/auth/me` | Update current user profile. | `auth_routes.py:723` |
| POST | `/api/auth/change-password` | Self-service password change. | `auth_routes.py:741` |
| POST | `/api/auth/logout` | Clears session cookie. | `auth_routes.py:776` |
| GET | `/api/auth/invitation/{token}` | Fetch invitation metadata (tenant, role, inviter). | `auth_routes.py:809` |
| POST | `/api/auth/invitation/{token}/accept` | Accept invite, create user, return JWT. | `auth_routes.py:854` |
| GET | `/api/auth/google/status` | Per-tenant Google SSO config status. | `auth_routes.py:988` |
| GET | `/api/auth/google/authorize` | Return Google OAuth URL to begin SSO. | `auth_routes.py:1050` |
| GET | `/api/auth/google/callback` | Google OAuth callback. Redirects to frontend with a one-time exchange code (MED-009). | `auth_routes.py:1087` |
| POST | `/api/auth/sso-exchange` | Exchange one-time code for JWT. | `auth_routes.py:1151` |
| POST | `/api/auth/google/link` | Link Google account to existing user. | `auth_routes.py:1196` |
| DELETE | `/api/auth/google/unlink` | Unlink Google. | `auth_routes.py:1234` |

**Session cookie** (`auth_routes.py:43-61`):

* Name: `tsushin_session`
* `httpOnly=true`, `SameSite=Lax`, `max_age=86400` (24 h, matches JWT expiry)
* `secure` flag follows the effective request scheme when the backend can see it, so local HTTP and local HTTPS entrypoints can coexist.
* Google SSO callback URLs are resolved from the incoming request origin. When local self-signed HTTPS is enabled, loopback HTTP entrypoints such as `http://127.0.0.1:3030` hand off Google SSO to the configured HTTPS callback (`https://localhost/api/auth/google/callback`) so the same Google OAuth client works on both local origins.

**Local auth recovery / pool guardrails (2026-04-18):**

* Auth bootstrap now fails closed into `/auth/login?force=1&reason=session-recovery` instead of leaving protected routes stuck on `Loading Tsushin...` when `/api/auth/me` hangs or times out.
* Backend PostgreSQL connections set `idle_in_transaction_session_timeout` from `TSN_DB_IDLE_IN_TRANSACTION_TIMEOUT_MS` (default `15000`) to keep stale browser tabs or leaked request paths from saturating the pool long enough to break login or Google SSO.

### 6.2 Multi-tenancy model

Tenants are first-class entities defined by the `tenant` table (`backend/models_rbac.py:16-41`). Key columns:

| Column | Purpose |
|---|---|
| `id` (String(50)) | Tenant identifier (e.g. `tenant_20251202232822`). |
| `slug` (unique) | URL-safe identifier. |
| `plan` / `plan_id` | Legacy plan string (`'free'`) **and** FK to `subscription_plan` row. Both are populated on signup. Plans are seeded at startup by `backend/services/plan_seeding.py`. |
| `max_users`, `max_agents`, `max_monthly_requests` | Quota columns. Defaults: `max_users=5`, `max_agents=10`, `max_monthly_requests=10000`. |
| `status` | `active`, `suspended`, or `trial`. |
| `slash_commands_default_policy` | `enabled_for_known` (default) / `enabled_for_all` / `disabled`. |
| `audit_retention_days` | Default 90. |

Users map to tenants via `UserRole(user_id, role_id, tenant_id)` — one role per user per tenant (unique index `uq_user_tenant`, `models_rbac.py:140-142`). A **global admin** (`User.is_global_admin=True`) may have `tenant_id=NULL` and operates across all tenants.

### 6.3 RBAC roles & permissions matrix

Seeded roles (`backend/migrations/add_rbac_tables.py:405-410`):

| Role | Description |
|---|---|
| `owner` | Full control, including billing and team management. |
| `admin` | Everything except `billing.write`. |
| `member` | Standard user — create/manage own resources, no deletes of cross-tenant resources, no user-management. |
| `readonly` | View-only. |

Full role → permission mapping is defined in `backend/migrations/add_rbac_tables.py:422-495`. See Appendix B for the complete list of permission strings.

### 6.4 Global Admin vs Tenant Admin

| Concept | Tenant Admin | Global Admin |
|---|---|---|
| DB flag | `UserRole.role='admin'` for a given `tenant_id` | `User.is_global_admin=True` |
| Scope | One tenant | All tenants, plus `/api/tenants` CRUD, plans, SSO config, system integrations |
| Can create tenants? | No | Yes (`POST /api/tenants`, `routes_tenants.py:203`) |
| Can manage system integrations? | No | Yes (`system_integration` table, `models_rbac.py:183-199`) |
| Permission short-circuit | Must match specific permission strings | `ApiCaller.has_permission()` returns True for **any** permission when `is_global_admin` is set (`backend/api/api_auth.py:40-43`) |

Every global-admin action is recorded in the `global_admin_audit_log` table (`models_rbac.py:217-230`).

### 6.5 User Invitations (tenant + global scope)

Invitations are the primary way to onboard both tenant-scoped users and platform-wide global admins. Stored in `user_invitation` (`backend/models_rbac.py:153-176`).

| Field | Type | Notes |
|---|---|---|
| `tenant_id` | String(50), **nullable** | `NULL` for global-admin invites |
| `role_id` | Integer, **nullable** | `NULL` for global-admin invites |
| `is_global_admin` | Boolean NOT NULL default false | When true, acceptance creates `User.is_global_admin=true` with no `UserRole` row |
| `auth_provider` | VARCHAR(16) NOT NULL default `'local'` | `local` (invitee sets a password) or `google` (invitee must accept via Google SSO; email must match) |
| `invitation_token` | VARCHAR(255) unique | SHA-256 **hash** of the token; the raw token is sent by email and returned by the invite endpoint |
| `expires_at` | Timestamp | 7 days by default |
| `accepted_at` | Timestamp, nullable | Set on successful accept |

**Invariants** (enforced both in ORM and via PostgreSQL CHECK constraints):
- `ck_invitation_scope` — `(is_global_admin=TRUE AND tenant_id IS NULL AND role_id IS NULL)` XOR `(is_global_admin=FALSE AND tenant_id IS NOT NULL AND role_id IS NOT NULL)`.
- `ck_invitation_auth_provider` — `auth_provider IN ('local', 'google')`.
- Partial unique index `uq_invitation_tenant_email_pending ON (tenant_id, email) WHERE accepted_at IS NULL` — prevents duplicate pending invites while allowing re-invites after accept/cancel.

**Endpoints.**

| Caller | Method | Path | Notes |
|---|---|---|---|
| Tenant owner (users.invite) | POST | `/api/team/invite` | Tenant-scoped only; body accepts `auth_provider` |
| Tenant owner | GET/DELETE/POST | `/api/team/invitations[/{id}][/resend]` | List / cancel / resend |
| Global admin | POST | `/api/admin/invitations` | Body: `{email, tenant_id?, role?, is_global_admin, auth_provider, message?}`; returns the raw invitation link |
| Global admin | GET | `/api/admin/invitations` | Filters: `is_global_admin`, `tenant_id`, `email_contains`, `page`, `page_size` |
| Global admin | DELETE | `/api/admin/invitations/{id}` | Cancels a pending invite |
| Unauthenticated | GET | `/api/auth/invitation/{token}` | Returns invite info for the accept page — nullable `tenant_name`/`role_display_name` for global-admin invites, plus `auth_provider` and `is_global_admin` |
| Unauthenticated | POST | `/api/auth/invitation/{token}/accept` | Password-accept path. Rejects `auth_provider=google` invites with HTTP 400 |

**Accept flow branching** (`backend/auth_routes.py:accept_invitation`, `backend/auth_google.py:find_or_create_user`):

1. Token looked up by its SHA-256 hash; expired/accepted invites rejected.
2. If `auth_provider=google` and the caller is using the password form → HTTP 400 "Must accept via Google SSO".
3. If `is_global_admin=true` → create `User(tenant_id=NULL, is_global_admin=True, auth_provider='local'|'google')`; do **not** create a `UserRole` row.
4. Else (tenant-scoped) → create `User(tenant_id=invitation.tenant_id, is_global_admin=False)` + `UserRole(role_id=invitation.role_id, tenant_id=invitation.tenant_id)`.
5. For Google SSO accept: enforce `invitation.email == google.email` (case-insensitive); if an existing user with that email already exists and the invite is global-scope, reject — invitations cannot silently upgrade an existing account.

**UI entry points.**
- Tenant owner: `/settings/team/invite` — form with email / role / **Sign-in method** radio / message. The "Google SSO" radio is disabled (with a tooltip) when the tenant has no Google SSO configured.
- Global admin: `/system/users` → **Invite User** button. Modal leads with an explicit two-option **kind picker** — *Tenant User* (default) or *Global Admin* — to make the multi-tenant mental model unambiguous. Tenant-user path requires a non-empty Organization (dropdown labeled `{name} — {slug} ({user_count} members)`) and a role in `owner | admin | member | readonly`; Global-admin path hides tenant + role entirely. Submit button stays disabled until required fields for the active kind are filled. The same picker appears on the break-glass **+ Create User** modal. Backed by `POST /api/admin/invitations/` / `POST /api/admin/users/` (both accept `is_global_admin`).
- Invitee: `/auth/invite/[token]` — header/body adapt to global-admin invites and Google-only invites automatically.

### 6.6 Global vs tenant Google SSO independence

Platform-wide Google SSO is stored in the `global_sso_config` singleton (since 2026-04-18) and managed via `/api/admin/sso-config`. Per-tenant SSO remains in `TenantSSOConfig` + `GoogleOAuthCredentials`. See §22.3 for fields and the UI; see the credential-resolution order in that section. The two scopes are fully independent — changing one does not affect the other. Auto-provisioning of global admins is not enabled by default; global admins are created exclusively via invitation.

`GET /api/auth/google/authorize` requires explicit scope selection — either `tenant_slug=<slug>` for tenant-scoped SSO or `platform=true` for global-admin SSO. Requests without scope return `400` (previously they silently fell back to the first tenant with SSO enabled). Combining `tenant_slug` with `platform=true` also returns `400`.

### 6.7 WebSocket authentication guarantees

The `/ws/shell/status` and beacon-status handlers (`backend/api/shell_websocket.py`) perform the full auth chain on every JWT-authenticated connection:

1. JWT signature + expiry.
2. `User.is_active == True` AND `User.deleted_at IS NULL` (deactivated users are rejected even with a non-expired token).
3. `tenant_id` claim matches the User's current tenant.
4. At least one `shell.*` permission granted in the tenant scope.

Failures close the socket with code `4003` (forbidden). API-key-authenticated beacon connections additionally verify the tenant is not `deleted_at`-tombstoned and not emergency-stopped. This closes the vectors previously tracked under BUG-612 + BUG-613.

---


## 7. Agents

Agents are AI assistants scoped to a tenant, each linked to a `Contact` record (role="agent") and configurable for multi-channel operation. Stored in the `agent` table.

Source: `backend/models.py:300-392` (Agent model)

### 7.1 Creating Agents — Guided vs Advanced Mode

Studio → Agents ships **two creation surfaces**, toggled per-user via `localStorage['tsushin:agentWizardMode']` (default: `guided`).

**Guided Mode (default)** — multi-step wizard branching on agent type. Source: `frontend/components/agent-wizard/AgentWizard.tsx` and `steps/*`, provider at `frontend/contexts/AgentWizardContext.tsx`, pure reducer at `frontend/lib/agent-wizard/reducer.ts`.

Step graph (text agents skip step 4):

| # | Step | Purpose |
|---|---|---|
| 1 | Type | Text / Audio / Hybrid — branch selector |
| 2 | Basics | Name, optional phone, model provider + model |
| 3 | Personality | Persona + tone OR custom system prompt (with starter-role chips per type) |
| 4 | Voice *(audio/hybrid only)* | Capability (voice/transcript/hybrid), TTS provider (Kokoro/OpenAI/ElevenLabs), voice/language/speed/format, Kokoro container auto-provision |
| 5 | Skills | Built-in + custom skills; `audio_*` auto-selected and locked for audio/hybrid |
| 6 | Memory | Built-in ring buffer / built-in + semantic / external vector store; memory size slider |
| 7 | Channels | playground / whatsapp / telegram / slack / discord — catalog fetched from `GET /api/channels` (source: `backend/channels/catalog.py`), with a static fallback in `StepChannels.tsx` for offline mode. Channels needing per-tenant setup render a "Needs setup" badge when the tenant has no matching instance row. Webhook moved to the trigger catalog in the v0.7.0 Wave 1 checkpoint and is created from Hub → Communication → Webhook Triggers instead of the guided channel picker. |
| 8 | Review | Per-section summary with Edit buttons that jump back |
| 9 | Progress | Chained provisioning spinner; on success navigates to `/playground?agentId=<id>` |

**Chained API calls** (from `useCreateAgentChain`):
1. Contact resolve/create (case-insensitive by `friendly_name`).
2. `POST /api/agents` with minimal payload (contact_id, system_prompt, persona_id / tone_preset_id, model_provider, model_name).
3. `PUT /api/agents/{id}` with extended config (memory_size, memory_isolation_mode, enable_semantic_search, enabled_channels, vector_store_instance_id, vector_store_mode).
4. Per-skill fan-out: `PUT /api/agents/{id}/skills/{type}` sequentially.
5. Custom skills: `POST /api/agents/{id}/custom-skills` per selected id.
6. Audio (audio/hybrid only): Kokoro → `POST /api/tts-instances`, poll `GET /api/tts-instances/{id}/container-status`, then `POST /api/tts-instances/{id}/assign-to-agent`. OpenAI/ElevenLabs → `PUT /api/agents/{id}/skills/audio_tts` with provider config only.

**Partial-failure handling.** If any stage after step 2 fails, the agent row is preserved; the Progress step surfaces the failing stage and links to `/agents/{id}` in Studio rather than cascading a rollback delete.

**Advanced Mode** — the pre-existing single-form modal at `frontend/app/agents/page.tsx:~749-1069` with all fields on one page. Includes a "Switch to Guided" link in its header. When the user switches from Guided → Advanced mid-wizard, the current draft is read from `AgentWizardContext.persistedDraft` and pre-filled into the form (dismissible banner announces the pre-fill).

### 7.1a Create / Edit Agent Form (Advanced Mode)

The "Create New Agent" modal on Studio → Agents exposes the fields below.
Source: `frontend/app/agents/page.tsx:22-36` (form interface) and `:749-1069` (form JSX).

| Field | Type | Notes | Source |
|---|---|---|---|
| Agent Name (`agent_name`) | text, required | Stored on the linked Contact as `friendly_name`. | `frontend/app/agents/page.tsx:728-737` |
| Phone Number (`agent_phone`) | text, optional | Used to populate the agent Contact's WhatsApp phone identifier. | `:740-748` |
| System Prompt (`system_prompt`) | textarea, required | May include `{{PERSONA}}` or `{{TONE}}` placeholders. | `:751-759`, model at `backend/models.py:314` |
| Persona (`persona_id`) | select, optional | FK to Persona; displayed as "Name — Role". | `:762-775`, model at `models.py:316` |
| Tone Preset (`tone_preset_id`) vs. Custom Tone (`custom_tone`) | radio + select/textarea | Legacy — persona_id is preferred. | `:778-821`, model at `models.py:319-320` |
| Trigger Keywords (`keywords`) | tag list | Case-insensitive triggers for group chats. | `:823-850`, model at `models.py:323` |
| Model Provider (`model_provider`) | select | `anthropic`, `openai`, `gemini`, `ollama`, `openrouter` (UI list); DB also permits `groq`, `grok`. | `:40-75`, `:864-889`, model at `models.py:329` |
| Model Name (`model_name`) | select or free-text (OpenRouter supports custom `provider/model-name`) | Auto-populated from the provider's model list. | `:891-968`, model at `models.py:330` |
| Active (`is_active`) | checkbox, default true | `models.py:379` |
| Default (`is_default`) | checkbox | Marks the agent as default for new chats. | `:981-989`, `models.py:380` |

Edit-time fields beyond the modal (surfaced in `AgentConfigurationManager` / Agent detail page tabs):
- `description` — short human-readable description (`models.py:315`)
- `response_template` — default `"@{agent_name}: {response}"` (`models.py:333`)
- `avatar` slug — e.g. samurai, robot, ninja (`models.py:376`)
- `provider_instance_id` — binds to a configured `ProviderInstance` so API keys/base URLs come from the tenant's provider configuration. (`models.py:369`, `models.py:437-458`)
- `vector_store_instance_id` + `vector_store_mode` (`override|complement|shadow`) — Vector store binding. (`models.py:372-373`)
- `enabled_channels` JSON — conversational entry points such as `playground, whatsapp, telegram, slack, discord`. The guided wizard no longer offers webhook here because webhook is now modeled as a trigger; some legacy agent-management surfaces still carry the older webhook binding fields during the v0.7.0 transition. (`models.py:363`)
- `whatsapp_integration_id`, `telegram_integration_id`, `slack_integration_id`, `discord_integration_id`, `webhook_integration_id` — legacy per-instance bindings on `Agent`. v0.7.0 additionally introduces `*.default_agent_id` on instance rows plus `user_channel_default_agent`, with `default_agent_service.py` preferring the new resolution chain and falling back to these older FKs only when needed. (`models.py:364-368`, `backend/services/default_agent_service.py`)

The agent detail page (`frontend/app/agents/[id]/page.tsx:18-20`) provides six tabs: Configuration, Channels, Memory Management, Skills, Knowledge Base, Shared Knowledge.

### 7.2 Memory Modes & Memory Size

Fields on the Agent model (Source: `backend/models.py:337-359`):

| Field | Type | Default | Values |
|---|---|---|---|
| `memory_size` | Integer (nullable) | system default | Ring buffer length per sender. |
| `memory_isolation_mode` | String(20) | `"isolated"` | `isolated` \| `shared` \| `channel_isolated` |
| `enable_semantic_search` | Boolean | True | Toggle semantic memory per agent. |
| `semantic_search_results` | Integer | 10 | Max semantic results returned. |
| `semantic_similarity_threshold` | Float | 0.5 | Range 0.0–1.0. |
| `chroma_db_path` | String(500) | NULL | Per-agent ChromaDB directory override. |
| `memory_decay_enabled` | Boolean | False | Enable temporal decay. |
| `memory_decay_lambda` | Float | 0.01 | Exponential decay rate (~69-day half-life). |
| `memory_decay_archive_threshold` | Float | 0.05 | Auto-archive below this score. |
| `memory_decay_mmr_lambda` | Float | 0.5 | MMR diversity weight. |

Semantics:
- **isolated** — each sender key has its own ring buffer. For threaded Playground/API chats, Tsushin uses a canonical thread-scoped sender key, so one thread cannot recall another thread's isolated memory.
- **shared** — buffer is shared across senders for the agent.
- **channel_isolated** — buffer is partitioned per channel (whatsapp/telegram/playground…). Separate threads inside the same channel share the channel buffer, but the UI/API still filters message history per thread.
- Thread-aware Playground reads (`history`, `memory`, and clear-history operations) accept an optional `thread_id` and resolve the same canonical identity used on writes, so thread-scoped history does not drift from the underlying memory mode.

### 7.3 Per-Agent Trigger & Context Overrides

These fields on the Agent model allow per-agent overrides for messaging triggers and group context. When set to `NULL`, the system/tenant default from the `Config` table is used.

Source: `backend/models.py:342-354`.

| Field | Type | Default | Purpose |
|---|---|---|---|
| `trigger_dm_enabled` | Boolean (nullable) | NULL (system default) | Enable/disable DM auto-response for this agent. When `true`, the agent responds to direct messages from unknown senders. |
| `trigger_group_filters` | JSON (nullable) | NULL (system default) | List of WhatsApp group names this agent monitors, overriding `Config.group_filters`. Example: `["Support Group", "VIP Chat"]` |
| `trigger_number_filters` | JSON (nullable) | NULL (system default) | List of phone numbers this agent monitors, overriding `Config.number_filters`. Example: `["+5511999990001"]` |
| `context_message_count` | Integer (nullable) | NULL (system default) | Number of recent group messages fetched for context before responding. |
| `context_char_limit` | Integer (nullable) | NULL (system default) | Character limit for the context window sent to the LLM. |

**Configuration example** — Agent "SupportBot" with custom trigger settings:

```json
{
  "trigger_dm_enabled": true,
  "trigger_group_filters": ["Support Group", "VIP Chat"],
  "trigger_number_filters": ["+5511999990001", "+5511999990002"],
  "context_message_count": 15,
  "context_char_limit": 8000
}
```

These overrides are applied at the trigger/routing layer (`backend/mcp_reader/`) and `AgentRouter` (`backend/agent/agent_router.py`). The system default is inherited from the tenant `Config` row (`backend/models.py:19-20`). See also §15.1 for instance-level WhatsApp filters.

### 7.4 Cloning Agents

Cloning is performed via the agents API (`api.deleteAgent`, `api.updateAgent` exposed in `frontend/app/agents/page.tsx`). The Persona/Skills entities have dedicated Clone buttons (`frontend/app/agents/personas/page.tsx:185-203` — handleClonePersona); per-agent cloning follows the same duplicate-form pattern — not verified in source at the agent page level (confirm via `backend/api/routes_agents.py`).

### 7.5 Multi-Agent Orchestration

Two skills drive inter-agent behavior:

- **Agent Switcher Skill** — `skill_type="agent_switcher"`, `execution_mode="hybrid"` (default as of v0.6.0). "Allows users to switch their default agent for direct messages via natural language commands." Claims detection-type exemption for `agent_takeover`.
  Source: `backend/agent/skills/agent_switcher_skill.py:37-43`

- **Agent Communication Skill (A2A)** — `skill_type="agent_communication"`, `execution_mode="tool"`. "Ask other agents questions, discover available agents, or delegate tasks."
  Source: `backend/agent/skills/agent_communication_skill.py:28-31`

**Agent Switcher execution modes** (v0.6.0):

| Mode | Behavior |
|---|---|
| `tool` | LLM decides via MCP tool schema only. No keyword scanning. |
| `legacy` | Keyword-only path (e.g., "Switch me to Support"). |
| `hybrid` | **Default.** Both paths active — keyword triggers fire deterministically, and the LLM can also call the tool by name. Prevents keyword-only misses while keeping tool-calling precision. |

Set the mode per-agent in Studio → Skills → Agent Switcher → Config. The schema is defined at `backend/agent/skills/agent_switcher_skill.py:505-509`.

**A2A Communications live in Studio** (`/agents/communication`) — a first-class Studio tab sitting between Security and Builder in the Studio sub-nav. It mounts `A2APermissionsManager` (`frontend/components/studio/A2APermissionsManager.tsx`), which owns the full permission-rule CRUD: Source/Target/Max Depth/Rate Limit/Target Skills/Status/Delete table plus the Add-Permission modal. Observability (session log + statistics) lives separately in Watcher → A2A Comms (`frontend/components/watcher/CommunicationTab.tsx`), which is read-only since v0.7.2 and shows a banner pointing back to Studio for rule management.

**Per-permission `allow_target_skills` toggle (v0.7.2).** Each row in `agent_communication_permission` carries an opt-in boolean, exposed in Studio → A2A Communications as an amber inline toggle in the rules table and as a checkbox in the Add-Permission modal. When `false` (default), the target runs with `disable_skills=True` on its `AgentService` — pure LLM-knowledge reply, preserving the original A2A contract. When `true`, the target loads its own skills (gmail, sandboxed_tools, shell, …) during the A2A call, which is what lets "Tsushin, ask movl for the latest emails" actually reach movl's Gmail mailbox. Recursion stays bounded by the row's `max_depth` + `rate_limit_rpm`, and Sentinel analysis + permission checks still run. Implementation: `backend/services/agent_communication_service.py::send_message` reads the permission, `_invoke_target_agent` maps it to `disable_skills=not allow_target_skills`. API contract: `PermissionCreateRequest`, `PermissionUpdateRequest`, and `PermissionResponse` all carry the field (`backend/api/routes_agent_communication.py`).

---

## 8. Personas & Tone Presets

### 8.1 Persona Form

Persona form fields on the create/edit modal (Source: `frontend/app/agents/personas/page.tsx:15-28`, JSX `:419-564`, DB at `backend/models.py:242-297`).

| Field | Type | Notes |
|---|---|---|
| `name` | text, required (unique per tenant) | `models.py:253` |
| `description` | textarea, required | `models.py:254` |
| `role` | text | e.g., "Customer Support Specialist" — `models.py:257` |
| `role_description` | textarea | Detailed responsibilities — `models.py:258` |
| `personality_traits` | text | e.g., "Empathetic, patient, enthusiastic" — `models.py:265` |
| `tone_preset_id` / `custom_tone` | radio + select or textarea | Tone source (preset or free text) — `models.py:261-262` |
| `guardrails` | textarea | Safety rules/constraints — `models.py:283` |
| `is_active` | checkbox | `models.py:289` |

Additional fields stored (populated via Persona builder/APIs rather than this modal):
- `enabled_skills` (JSON list of Skill IDs) — `models.py:268`
- `enabled_sandboxed_tools` (JSON list of SandboxedTool IDs, alias `enabled_custom_tools`) — `models.py:270, 274-280`
- `enabled_knowledge_bases` (JSON list of KB IDs) — `models.py:271`
- `ai_summary` — auto-generated persona summary (custom personas only) — `models.py:286`
- `is_system` — True for built-in personas — `models.py:290`

System-persona names are read-only in the UI (`personas/page.tsx:431`).

### 8.2 Tone Preset Library

Source: `backend/models.py:222-239` (TonePreset model) and `backend/services/tone_preset_seeding.py`.

| Field | Type | Notes |
|---|---|---|
| `name` | String(50), unique per tenant | e.g., "Friendly", "Professional", "Humorous" |
| `description` | Text, required | The tone phrase injected into system prompts. |
| `is_system` | Boolean, default False | True for built-in presets. |
| `tenant_id` | String(50), nullable | NULL = shared/system preset. |

Seeded presets are created by `tone_preset_seeding.py` at install/bootstrap.

---

## 9. Skills

### 9.1 Built-in Skills Catalog

Each entry below is taken directly from the skill's class attributes. Config is inherited from `BaseSkill.get_config_schema()` (keywords, use_ai_fallback, ai_model) unless the subclass overrides.
Common base schema source: `backend/agent/skills/base.py:183-227`.

| skill_type | skill_name | execution_mode | Description | Source file |
|---|---|---|---|---|
| `audio_transcript` | Audio Communication | special | Process audio messages with conversational AI or transcription-only mode | `audio_transcript.py:46-49` |
| `audio_tts` | Audio TTS Response | passive | Convert text responses to audio using OpenAI, Kokoro, or ElevenLabs TTS | `audio_tts_skill.py:45-48` |
| `web_search` | Web Search | tool | Search the web using Brave Search (default provider) | `search_skill.py:50-53` |
| `image_analysis` | Image Analysis | special | Interpret screenshots/photos, answer questions about attached images, and extract visible text before the normal LLM reply path | `image_analysis_skill.py:25-33` |
| `image` | Image Generation & Editing | tool | Generate new images from text prompts or edit existing images using AI | `image_skill.py:47-50` |
| `gmail` | Gmail | tool | Read and search emails from connected Gmail accounts | `gmail_skill.py:47-50` |
| `automation` | Automation | tool | Multi-step workflow automation and process orchestration | `automation_skill.py:42-45` |
| `scheduler` | Scheduler | tool | Schedule reminders and AI-driven conversations via natural language | `scheduler_skill.py:40-43` |
| `scheduler_query` | Scheduler Query | legacy | Query and list scheduled events via natural language (merged into `scheduler` list action) | `scheduler_query_skill.py:24-27` |
| `flows` | Flows | tool | Schedule reminders, AI-driven conversations, and manage scheduled events | `flows_skill.py:62-65` |
| `flight_search` | Flight Search | tool | Search for flights using configured providers such as Amadeus or Google Flights | `flight_search_skill.py:42-45` |
| `shell` | Shell Commands | hybrid | Execute shell commands on registered remote hosts via secure beacon agents. Exempts `shell_malicious`. | `shell_skill.py:39-42` |
| `sandboxed_tools` | Sandboxed Tools | passive | Gate for running security tools (nmap, dig, nuclei, httpx) inside isolated Docker containers | `sandboxed_tools_skill.py:29-36` |
| `browser_automation` | Browser Automation | tool | Navigate, click, fill forms, extract content, capture screenshots | `browser_automation_skill.py:56-59` |
| `knowledge_sharing` | Knowledge Sharing | passive | Post-response hook for sharing facts into shared memory pool | `knowledge_sharing_skill.py:43-50` |
| `adaptive_personality` | Adaptive Personality | passive | Post-processing hook for fact extraction / persona learning | `adaptive_personality_skill.py:32-39` |
| `okg_term_memory` | OKG Term Memory | hybrid | Store/recall structured term memory with MemGuard validation | `okg_term_memory_skill.py:158-164` |
| `agent_switcher` | Agent Switcher | tool | Switch user's default DM agent via natural language | `agent_switcher_skill.py:39-42` |
| `agent_communication` | Agent Communication | tool | Ask other agents questions, delegate tasks, discover agents | `agent_communication_skill.py:28-31` |
| `custom` (base) | Custom Skill | tool | Adapter for tenant-authored custom skills. `skill_type` becomes `custom:{slug}` at runtime | `custom_skill_adapter.py:25-37` |

Execution modes (Source: `backend/agent/skills/base.py:71-78`):
- `legacy`/`programmatic` — keyword or slash command only (no LLM tool call).
- `tool`/`agentic` — exposed as an LLM function-call tool.
- `hybrid` — both tool and legacy modes.
- `passive` — post-processing hook (no direct trigger).
- `special` — media-triggered (e.g., audio).

All skills inherit the base config schema:

```json
{"type":"object","properties":{
  "keywords": {"type":"array","items":{"type":"string"},"default":[]},
  "use_ai_fallback": {"type":"boolean","default":true},
  "ai_model": {"type":"string","enum":["gemini-2.5-flash","gpt-3.5-turbo","claude-haiku"],"default":"gemini-2.5-flash"}
}}
```
Source: `backend/agent/skills/base.py:204-227`. Individual skills override to add their own fields (e.g., `scheduler_skill.py:1081`, `gmail_skill.py:1136-1138`, `browser_automation_skill.py:725`, `image_skill.py:659`).

### 9.2 Per-Agent Skill Binding & Config

Bindings are stored in the `agent_skill` table (Source: `backend/models.py:712` — class AgentSkill). Each row associates an `agent_id` + `skill_type` with an `is_enabled` flag, a per-agent `execution_mode` override, and a JSON `config` blob validated against the skill's `get_config_schema()`.

The Skills tab on the agent detail page (`frontend/app/agents/[id]/page.tsx:218-220`, component `AgentSkillsManager`) lists available skills from the `SkillManager` catalog (Source: `backend/agent/skills/skill_manager.py:146-184`) and renders a per-skill config modal using the returned `config_schema`.

`image_analysis` is media-triggered rather than tool-triggered. It activates on inbound image attachments, uses Gemini multimodal models to analyze the image, and returns a direct response with `skip_ai=true`. If the image caption looks like an edit request ("remove background", "change this", etc.), the skill intentionally defers so the existing `image` editing skill can handle the request instead.

### 9.3 Custom Skills (Instruction / Script / MCP Server)

Custom skills are tenant-authored skills registered under `backend/api/routes_custom_skills.py` and managed via Studio → Custom Skills (`frontend/app/agents/custom-skills/page.tsx`).

**Resource quotas** (Source: `routes_custom_skills.py:33-35`):
- Max instruction length: **8,000 characters**
- Max script size: **256 KB**
- Max skills per tenant: **50**

**Common schema fields** (Source: `routes_custom_skills.py:59-77`):

| Field | Type | Default | Description |
|---|---|---|---|
| `name` | string, required | — | Skill display name |
| `description` | string | null | Short description |
| `icon` | string | null | Icon identifier |
| `skill_type_variant` | string | `"instruction"` | `instruction` \| `script` \| `mcp_server` |
| `execution_mode` | string | `"tool"` | `tool` (LLM-facing) \| `passive` (post-processing) |
| `trigger_mode` | string | `"llm_decided"` | `llm_decided` (LLM decides when to call) \| `keyword` \| `always` |
| `trigger_keywords` | string[] | `[]` | Keywords that activate the skill (when `trigger_mode=keyword`) |
| `timeout_seconds` | integer | `30` | Execution timeout |
| `priority` | integer | `50` | Priority order (lower = higher priority) |
| `sentinel_profile_id` | integer | null | Security profile for Sentinel scan at save-time |
| `input_schema` | object | `{}` | JSON Schema for skill input parameters |

Lifecycle fields rendered in UI: `scan_status` (`pending`, `clean`, `rejected`, `unknown`), `last_scan_result`, `skill_type_variant` (Source: `:20-66`). Deployment handled by `backend/services/custom_skill_deploy_service.py`.

At runtime, custom skills are adapted by `CustomSkillAdapter` (Source: `backend/agent/skills/custom_skill_adapter.py:25-53`): its `skill_type` becomes `"custom:{slug}"`, `skill_name` and `execution_mode` are pulled from the database record; `passive` adapters have no `can_handle`.

#### 9.3.1 Instruction Skills

Natural-language instructions executed by the LLM as a tool. The simplest custom skill type — no code required.

**Runtime execution semantics (BUG-509, 2026-04-10):** Instruction skills behave differently depending on `execution_mode`:
- `execution_mode: tool` or `hybrid` (the default) — the skill is exposed to the agent as a callable tool. When the LLM invokes it, `CustomSkillAdapter.execute_tool` routes through `execute_instruction_with_llm`, which runs the `instructions_md` as a system prompt against the tenant's LLM and returns the LLM's processed output. This is the same code path that the `/api/custom-skills/{id}/test` endpoint uses, so the `/test` and runtime paths now always agree. Every runtime invocation writes a `CustomSkillExecution` history row just like `/test`.
- `execution_mode: passive` — the skill's `instructions_md` is concatenated into the agent's system prompt as always-on context and the skill is NOT exposed as a callable tool. Use this when you want the instructions to shape every response rather than be selectively invoked.

Before 2026-04-10, all instruction skills had their raw `instructions_md` dumped into the system prompt regardless of execution mode, which caused the LLM to parrot the template back verbatim when invoked. Passive mode is now the only path that injects raw instructions.

| Field | Type | Description |
|---|---|---|
| `instructions_md` | string (max 8,000 chars) | Markdown instructions executed by the LLM (tool/hybrid mode) or injected as always-on context (passive mode) |

**Example — Create a "Policy Lookup" instruction skill:**

```bash
curl -X POST http://localhost:8081/api/custom-skills \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Policy Lookup",
    "description": "Answers questions about company policies",
    "skill_type_variant": "instruction",
    "execution_mode": "tool",
    "trigger_mode": "llm_decided",
    "instructions_md": "When asked about company policies, search the knowledge base for relevant policy documents. Always cite the policy name and section number. If no policy is found, say so clearly.",
    "timeout_seconds": 30
  }'
```

#### 9.3.2 Script Skills

Executable scripts deployed to a sandboxed container. Supports Python, Bash, and Node.js. The runtime executes the script file and reads stdout (plain text or JSON with an `output` field). Returning a value from a function without printing it does not produce usable output, and `/api/custom-skills/{id}/test` now fails closed when stdout is blank.

| Field | Type | Description |
|---|---|---|
| `script_content` | string (max 256 KB) | The script source code |
| `script_language` | string | `python` \| `bash` \| `nodejs` |
| `script_entrypoint` | string | Entry file to execute (e.g., `run.py`). Bare names (e.g., `run`) are auto-extended based on `script_language`, but the file still needs to print its result to stdout. |

**Example — Create a Python data-processing skill:**

```bash
curl -X POST http://localhost:8081/api/custom-skills \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CSV Analyzer",
    "description": "Analyzes CSV data and returns statistics",
    "skill_type_variant": "script",
    "execution_mode": "tool",
    "script_language": "python",
    "script_entrypoint": "analyze",
    "script_content": "import json\nimport os\n\ninput_data = json.loads(os.environ.get(\"TSUSHIN_INPUT\", \"{}\"))\nrows = input_data.get(\"rows\", [])\nprint(json.dumps({\"output\": json.dumps({\"row_count\": len(rows)})}))",
    "timeout_seconds": 60
  }'
```

#### 9.3.3 MCP Server Skills

Connect to an external MCP-compliant tool server. The skill proxies requests to the MCP server and returns results.

| Field | Type | Description |
|---|---|---|
| `mcp_server_id` | integer | FK to a registered MCP server integration |
| `mcp_tool_name` | string | The specific tool name exposed by the MCP server |

**Example — Create an MCP Server skill:**

```bash
curl -X POST http://localhost:8081/api/custom-skills \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Database Query",
    "description": "Query the analytics database via MCP",
    "skill_type_variant": "mcp_server",
    "execution_mode": "tool",
    "mcp_server_id": 3,
    "mcp_tool_name": "query_analytics",
    "timeout_seconds": 45
  }'
```

### 9.4 Sandboxed Tools

Command syntax via chat / API: `/tool <tool_name> <command_name> param=value` (e.g. `/tool nmap quick_scan target=scanme.nmap.org`, `/tool dig lookup domain=google.com`). Flags like `--target` are NOT supported — only `param=value`.

Tools are defined via YAML manifests in `backend/tools/manifests/` (`sandboxed_tool_seeding.py:36`) and loaded into `SandboxedTool`/`SandboxedToolCommand`/`SandboxedToolParameter` tables (`models.py`). Container execution is the default (`execution_mode="container"`, Source: `models.py:1347`). The master toolbox image is built from `backend/containers/Dockerfile.toolbox`.

The `sandboxed_tools` skill acts as a passive gate — it grants the agent access to these tools without itself being an LLM-facing tool (`sandboxed_tools_skill.py:36`).

#### 9.4.1 nmap — Network Scanner

| Command | Template | Parameters |
|---|---|---|
| `quick_scan` | `nmap -T4 -F {target} -oN {output_file}` | `target` (string, **required**), `output_file` (string, default: `nmap_quick_scan.txt`) |
| `service_scan` | `nmap -sV --version-intensity {intensity} {target} -oN {output_file}` | `target` (**required**), `intensity` (integer 0-9, default: `5`), `output_file` |
| `ping_scan` | `nmap -sn {target} -oN {output_file}` | `target` (**required**), `output_file` |
| `aggressive_scan` | `nmap -A -p {ports} {target} -oN {output_file}` | `target` (**required**), `ports` (string, default: `1-1000`), `output_file` |

**Examples:**
```
/tool nmap quick_scan target=scanme.nmap.org
/tool nmap service_scan target=192.168.1.1 intensity=7
/tool nmap ping_scan target=192.168.1.0/24
/tool nmap aggressive_scan target=scanme.nmap.org ports=80,443
```

#### 9.4.2 nuclei — Vulnerability Scanner

| Command | Template | Parameters |
|---|---|---|
| `start_scan` | `nuclei -u {url} ... -t http/misconfiguration/ -t http/vulnerabilities/` | `url` (string, **required**) |
| `severity_scan` | `nuclei -u {url} -s {severity}` | `url` (**required**), `severity` (string: `info`/`low`/`medium`/`high`/`critical`, default: `critical`) |
| `full_scan` | `nuclei -u {url}` (all templates, long-running) | `url` (**required**) |

**Examples:**
```
/tool nuclei start_scan url=http://testphp.vulnweb.com
/tool nuclei severity_scan url=http://testphp.vulnweb.com severity=high
/tool nuclei full_scan url=http://testphp.vulnweb.com
```

#### 9.4.3 dig — DNS Lookup

| Command | Template | Parameters |
|---|---|---|
| `lookup` | `dig {domain} {record_type} +short` | `domain` (string, **required**), `record_type` (string: `A`/`AAAA`/`MX`/`NS`/`TXT`/`CNAME`/`SOA`/`ANY`, default: `A`) |
| `reverse` | `dig -x {ip_address} +short` | `ip_address` (string, **required**) |

**Examples:**
```
/tool dig lookup domain=google.com record_type=MX
/tool dig reverse ip_address=8.8.8.8
```

#### 9.4.4 httpx — HTTP Probing

| Command | Template | Parameters |
|---|---|---|
| `probe` | `httpx -u {target} -silent -o {output_file}` | `target` (string, **required**), `output_file` (default: `httpx_results.txt`) |
| `tech_detect` | `httpx -u {target} -tech-detect -o {output_file}` | `target` (**required**), `output_file` (default: `httpx_tech.txt`) |

**Examples:**
```
/tool httpx probe target=https://github.com
/tool httpx tech_detect target=https://shopify.com
```

#### 9.4.5 whois_lookup — Domain WHOIS Info

| Command | Template | Parameters |
|---|---|---|
| `lookup` | `whois {domain} \| head -30` | `domain` (string, **required**) |

**Example:**
```
/tool whois_lookup lookup domain=github.com
```

#### 9.4.6 katana — Web Crawler

| Command | Template | Parameters |
|---|---|---|
| `crawl` | `katana -u {target} -d {depth} -jc -silent ...` | `target` (string, **required**), `depth` (integer 1-3, default: `1`) |

**Examples:**
```
/tool katana crawl target=https://example.com
/tool katana crawl target=https://example.com depth=2
```

#### 9.4.7 subfinder — Subdomain Discovery

| Command | Template | Parameters |
|---|---|---|
| `scan` | `subfinder -d {domain} -silent` | `domain` (string, **required**) |

**Example:**
```
/tool subfinder scan domain=github.com
```

#### 9.4.8 webhook — HTTP Requests

| Command | Template | Parameters |
|---|---|---|
| `get` | `curl -sSLk -X GET "{url}" ...` | `url` (string, **required**) |
| `post` | `curl -sSLk -X POST "{url}" -d '{payload}' ...` | `url` (**required**), `payload` (JSON string, **required**), `output_file` |

**Examples:**
```
/tool webhook get url=https://api.github.com/users/octocat
/tool webhook post url=https://webhook.site/your-id payload={"message":"Hello from Tsushin"}
```

#### 9.4.9 sqlmap — SQL Injection Testing

| Command | Template | Parameters |
|---|---|---|
| `scan` | `sqlmap -u {target} --batch --level=1 --risk=1 --dbs` | `target` (string, **required** — URL with testable parameter) |

**Example:**
```
/tool sqlmap scan target=http://testphp.vulnweb.com/listproducts.php?cat=1
```

Source: YAML manifests in `backend/tools/manifests/` (9 files). Seeding: `backend/services/sandboxed_tool_seeding.py:38-49`.

---

## 10. Memory & Knowledge

### 10.1 Four-Layer Architecture

Source: `backend/agent/memory/agent_memory_system.py:1-32`.

- **Layer 1 — Working Memory**: ring buffer of last N messages per sender key, stored in the `memory` table (`messages_json` JSON field). Fast in-context recall. Source: `backend/models.py:130-144`. The `memory` table is keyed by `(tenant_id, agent_id, sender_key)` with a composite index `idx_memory_tenant_agent_sender`; every read and write path filters by `tenant_id` for DB-level cross-tenant isolation (see BUG-LOG-015).
- **Layer 2 — Long-Term Episodic Memory**: unlimited conversation history with semantic search via a vector store (ChromaDB default). Implemented in `SemanticMemoryService` (`backend/agent/memory/semantic_memory.py`).
- **Layer 3 — Semantic Knowledge Base**: learned facts about users, extracted by `FactExtractor` (`backend/agent/memory/fact_extractor.py`) and persisted via `KnowledgeService` (`backend/agent/memory/knowledge_service.py`).
- **Layer 4 — Shared Memory Pool**: cross-agent knowledge, managed by `SharedMemoryPool` (`backend/agent/memory/shared_memory_pool.py`).

Management / inspection services: `MemoryManagementService` (`memory_management_service.py`), `MultiAgentMemory` (`multi_agent_memory.py`), `VectorStoreManager` (`vector_store_manager.py`), `VectorStoreCached` (`vector_store_cached.py`), `ToolOutputBuffer` (`tool_output_buffer.py`).

### 10.2 Knowledge Bases (KB)

Uploads are handled by `POST /api/agents/{agent_id}/knowledge-base/upload` (Source: `backend/api/routes_knowledge_base.py:157-203`).

- Allowed extensions: `.txt`, `.csv`, `.json`, `.pdf`, `.docx` (`:186`).
- Max file size: 50 MB (`:170`).
- Processing is asynchronous (FastAPI BackgroundTasks).
- Required permission: `knowledge.write` (`:164`).

Chunking/embedding configuration is set on the Project (see 17.2) — per-agent uploads use system defaults from `backend/agent/knowledge/document_processor.py`.

Additional endpoints (`routes_knowledge_base.py`):
- `GET /agents/{id}/knowledge-base` — list documents
- `GET /agents/{id}/knowledge-base/stats` — stats
- `GET /agents/{id}/knowledge-base/{knowledge_id}` — detail
- `PATCH /agents/{id}/knowledge-base/{knowledge_id}` — rename document and update lightweight tags (stored without a DB migration)
- `GET /agents/{id}/knowledge-base/{knowledge_id}/chunks` — chunks
- `POST /agents/{id}/knowledge-base/search` — semantic search over KB
- `POST /agents/{id}/knowledge-base/{knowledge_id}/reprocess` — reprocess

Knowledge-document tags are normalized to lowercase, deduplicated, and stored as sidecar metadata beside the uploaded file so existing databases do not need a schema change just to support document organization.

### 10.3 OKG (Ontology Knowledge Graph)

Source: `backend/agent/memory/okg/okg_memory_service.py:1-38`.

Core operations: **store**, **recall**, **forget**, **merge**. Features:
- **MemGuard Layer A** pre-storage validation (security gate).
- Deterministic deduplication by `doc_id` (`sha256(agent_id:user_id:subject:relation:text[:100])[:32]`, `:31-37`).
- Temporal decay scoring.
- Audit logging to `okg_memory_audit_log` (Source: `models.py:3579-3609`).

**Merge modes** (Source: `okg_memory_service.py:28`):

| Mode | Behavior |
|---|---|
| `merge` (default) | Intelligent merge of new content into existing memory entry |
| `replace` | New value completely overwrites the existing entry |
| `prepend` | New value is prepended to the existing text |

Valid memory types (`okg_memory_service.py:26`): `fact`, `episodic`, `semantic`, `procedural`, `belief`.
Valid sources (`:27`): `tool_call`, `auto_capture`, `import`.

Context injection into LLM calls is done by `OKGContextInjector` (`backend/agent/memory/okg/okg_context_injector.py`). Skill surface: `okg_term_memory` (see 9.1).

### 10.4 Semantic Search Configuration

Per-agent config on the `agent` table (`backend/models.py:350-353`):

| Field | Type | Default |
|---|---|---|
| `enable_semantic_search` | Boolean | True |
| `semantic_search_results` | Integer | 10 |
| `semantic_similarity_threshold` | Float | 0.5 |
| `chroma_db_path` | String(500) | NULL |

### 10.5 Temporal Decay

Source: `backend/agent/memory/temporal_decay.py:14-60`.

| Parameter | Default | Meaning |
|---|---|---|
| `enabled` | False | Master switch (agent: `memory_decay_enabled`). |
| `decay_lambda` | 0.01 | Exponential decay rate; ~69-day half-life. |
| `archive_threshold` | 0.05 | Auto-archive memories below this effective score. |
| `mmr_lambda` | 0.5 | MMR diversity weight (0=max diversity, 1=pure relevance). |

Decay factor: `e^(-lambda * days_since_access)`. MMR (Maximum Marginal Relevance) reranking balances relevance against diversity so recall doesn't return near-duplicates. Config is loaded from the Agent row via `DecayConfig.from_agent()` (`temporal_decay.py:27-35`).

---

## 11. Vector Stores

Multi-vendor vector DB support. Each tenant can register one or more `VectorStoreInstance` rows and designate a default; agents can override per-agent via `agent.vector_store_instance_id`.

Model: `backend/models.py:3521-3576` (VectorStoreInstance).
Adapters: `backend/agent/memory/providers/` — `chroma_adapter.py`, `mongodb_adapter.py`, `pinecone_adapter.py`, `qdrant_adapter.py`. All implement `VectorStoreProvider` (`backend/agent/memory/providers/base.py:41-122`).

Common fields on `VectorStoreInstance`:
- `vendor`: `chromadb|mongodb|pinecone|qdrant`
- `instance_name` — unique per tenant
- `base_url`, `credentials_encrypted` (Fernet-encrypted JSON)
- `extra_config` (JSON): vendor-specific (`index_name`, `collection_name`, `namespace`, `embedding_dims`)
- `health_status` (`unknown|healthy|degraded|unavailable`)
- `is_auto_provisioned`, container fields (`container_name`, `container_port`, `container_status`, `container_image`, `volume_name`, `mem_limit`, `cpu_quota`)
- `security_config` (JSON): MemGuard thresholds, rate limits, batch limits

Namespace isolation per agent uses pattern `tsushin_{tenant_id}_{agent_id}` (`providers/base.py:49`).

### 11.1 Chroma (local, default)
Built-in. No external credentials required. Uses `chroma_db_path` per agent or a tenant default.
Adapter: `backend/agent/memory/providers/chroma_adapter.py`.

### 11.2 Pinecone
Cloud-hosted. `base_url` unused; API key stored in `credentials_encrypted`; `extra_config.index_name` + `extra_config.namespace` required.
Adapter: `backend/agent/memory/providers/pinecone_adapter.py`.

### 11.3 Qdrant
Self-hosted or cloud. `base_url` required; `extra_config.collection_name` required.
Adapter: `backend/agent/memory/providers/qdrant_adapter.py`.

### 11.4 MongoDB Atlas
`base_url` required (connection string in credentials); requires Atlas Vector Search.
Adapter: `backend/agent/memory/providers/mongodb_adapter.py`.

### UI

Settings → Vector Stores (`frontend/app/settings/vector-stores/page.tsx:21-125`) lets admins pick the default instance (`api.updateDefaultVectorStore`) and run connection tests (`api.testVectorStoreConnection`). The page renders vendor labels for `mongodb`, `pinecone`, `qdrant` (`:8-12`). Health dots reflect `health_status` (`:14-19`).

Per-agent override uses `agent.vector_store_mode`:
- `override` — agent uses its configured instance only.
- `complement` — agent reads from both its instance and the default.
- `shadow` — writes duplicated to secondary for migration/testing.
Source: `backend/models.py:372-373`.

### Per-Agent Vector Store UI

Studio > Agent > Configuration now includes a **Vector Store** section (`frontend/components/AgentConfigurationManager.tsx`) with:
- Status indicator showing current vector store (per-agent override, tenant default, or ChromaDB built-in)
- Dropdown to select from available vector store instances or "Use Tenant Default"
- Mode selector (Override/Complement/Shadow) shown when an override is selected
- Link to Hub > Vector Stores if no instances are configured

### Post-Creation Agent Attachment Wizard

When creating a new vector store in Hub > Vector Stores (`frontend/components/vector-stores/VectorStoreConfigModal.tsx`), after successful creation an optional "Attach to Agents" step appears:
- Lists all active agents with checkboxes
- Shows which agents already have a vector store override
- Assigns the new store with `override` mode to selected agents
- Skippable — users can attach later via Studio > Agent > Configuration

---

## 12. Security — Sentinel

Sentinel is an AI-powered detection/blocking layer. Registry source: `backend/services/sentinel_detections.py:17-141`. Profiles: `backend/services/sentinel_seeding.py:503-570`. UI: `frontend/app/settings/sentinel/page.tsx`, `frontend/app/agents/security/page.tsx`.

### 12.1 Detection Types (7)

| Key | Name | Severity | Applies to |
|---|---|---|---|
| `prompt_injection` | Prompt Injection | high | prompt |
| `agent_takeover` | Agent Takeover | high | prompt |
| `poisoning` | Poisoning Attack | medium | prompt |
| `shell_malicious` | Malicious Shell Intent | critical | shell |
| `memory_poisoning` | Memory Poisoning (MemGuard) | high | memory |
| `agent_escalation` | Agent Privilege Escalation | high | prompt |
| `browser_ssrf` | Browser SSRF | critical | browser |
| `vector_store_poisoning` | Vector Store Poisoning | high | vector_store |

(8 registry entries — the "7 detection types" referred to at the product level excludes `agent_escalation`, which shipped later.)
Source: `backend/services/sentinel_detections.py:17-141`.

### 12.2 Profiles

Source: `backend/services/sentinel_seeding.py:523-570`.

| Slug | Name | detection_mode | aggressiveness_level | Notes |
|---|---|---|---|---|
| `off` | Off | `off` | 0 | No analysis. |
| `permissive` | Permissive | `detect_only` | 1 | System-wide default. |
| `moderate` | Moderate | `block` | 1 | Recommended for production. |
| `aggressive` | Aggressive | `block` | 3 | Max sensitivity; more false positives. |
| `custom-skill-scan` | Custom Skill Scan | `block` | 1 | Tuned for custom-skill instruction scanning (disables `agent_takeover`, `poisoning`, `memory_poisoning`). |

Custom profiles per tenant are allowed via `SentinelProfile` records and cloning (`api.SentinelProfileCloneRequest` in `frontend/app/settings/sentinel/page.tsx:15`).

### 12.3 Modes & Aggressiveness

- **detection_mode**: `off` | `warn_only` | `detect_only` | `block`
- **aggressiveness_level**: 0 (off) | 1 (moderate) | 2 (aggressive) | 3 (extra aggressive). Controls which `DEFAULT_PROMPTS` template is used per detection (Source: `sentinel_detections.py:146-196`).
- **Strict-superset guarantee:** level-3 (`UNIFIED_CLASSIFICATION_PROMPT[3]`) is built to always catch every level-1 trigger plus additional aggressive phrasings. Promotions to level-3 never lose coverage versus level-1 (`sentinel_detections.py`).

### 12.3a Heuristic Floor (provider-independent)

A regex/keyword layer runs BEFORE any LLM call in `SentinelService._analyze_unified` and also in the LLM-error fallback path. Defined in `backend/agent/sentinel/heuristics.py` and invoked via `SentinelService._heuristic_floor_result`. Families covered:

- `prompt_injection` — "ignore previous instructions", "ignore prior rules", "disregard all above", "start fresh", "developer mode", DAN/jailbreak tokens.
- `agent_takeover` — "you are now X", "from now on you are", "act as the system", persona-override phrasings.
- `agent_escalation` — "delegate to another agent and bypass", "have another agent", escalation-to-privileged-agent phrasings.
- `memory_poisoning` (credential) — "remember forever the production api key", "embed this sentence as a high-priority fact", "store this as a system instruction".
- `memory_poisoning` (behavior prefix) — "always start every future reply with X", permanent-behavior-override phrasings.
- `vector_store_poisoning` — persistent-marker injections aimed at semantic/vector memory.
- `shell_malicious` — classic shell-injection phrasings.
- `browser_ssrf` — link-metadata / 169.254 / localhost-browsing phrasings.

The heuristic logs with `llm_provider="heuristic"`. It fires in `block`, `warn_only`, and `detect_only` modes and respects per-profile detection toggles. Result: Sentinel is no longer a no-op on installs without an LLM API key, and fail-closed timeouts in block mode are rarer because the heuristic short-circuits common attack phrasings before the LLM is called.

### 12.3b Fact-Extractor Untrusted-Content Guard

`backend/agent/memory/fact_extractor.py` now treats user-turn content as *quotation*, not instruction. Before the LLM fact-extraction call, `_sanitize_conversation_for_extraction` drops user turns that match prompt-injection markers. After extraction, `_filter_untrusted_facts`:

- Refuses any `instructions`-topic fact unless a trusted assistant/system turn is present.
- Drops facts whose `value` or `context` text itself matches injection markers.
- Caps any surviving `instructions`-topic fact at `confidence=0.9` (previously 0.95–0.98).

This is the primary defence against stored prompt-injection via memory poisoning, and runs regardless of which detection mode Sentinel is in.

### 12.4 Notifications & WhatsApp Alerts

Channel-based alert dispatching for Sentinel events is handled by `backend/services/channel_alert_dispatcher.py`. Alerts can be routed to specified Contacts (WhatsApp or other channels) when blocks/detections occur. Sentinel general-tab UI exposes notification toggles via `SentinelConfig` (`frontend/app/settings/sentinel/page.tsx:54`).

### 12.5 Exceptions & Allowlists

Exceptions are managed in `backend/services/sentinel_exceptions_service.py:32-186` via the `SentinelException` model. Scope hierarchy (order of checking): system (tenant_id NULL, agent_id NULL) → tenant (tenant_id set, agent_id NULL) → agent (agent_id set).

| Field | Values |
|---|---|
| `exception_type` | `pattern`, `domain`, … |
| `match_mode` | For `pattern`: controls literal/regex/glob matching. |
| `detection_types` | `*` (applies to all) or comma list. |
| `priority` | Higher wins. |
| `is_active` | Boolean. |

Source: `sentinel_exceptions_service.py:86-186`.

### 12.6 Per-Skill Security Overrides

Each skill class publishes `get_sentinel_context()` (expected_intents, expected_patterns, risk_notes) and `get_sentinel_exemptions()` (detection_type keys auto-exempted when the skill is enabled). Source: `backend/agent/skills/base.py:229-280`.

Effective per-skill profile resolution: `backend/services/sentinel_effective_config.py` (composes tenant → agent → skill-level profile assignments, returning `SentinelEffectiveConfig`; see usage in `sentinel_profiles_service.py:555-632`).

Per-agent security UI: `frontend/app/agents/security/page.tsx` mounts per-agent overrides.

---

## 13. Flows

Unified execution engine for reusable workflows. DB: `flow_definition`, `flow_node`, `flow_run`, `flow_node_run`.
Source: `backend/flows/flow_engine.py`, `backend/models.py:1528-1728`.

> **v0.6.0 — Integration resolution (BUG-559):** `flows_skill` now queries `AgentSkillIntegration` first when resolving provider accounts (e.g., Google Calendar, Gmail). This means flows respect the agent's per-skill integration binding set in Studio, and only fall back to system-wide config defaults if no binding exists. Previously the Google Calendar provider was ignored in favor of the config default, causing calendar steps to write to the wrong account.

### 13.1 Flow Types

`flow_definition.flow_type` values (Source: `backend/models.py:1563`): `conversation`, `notification`, `workflow`, `task`.

Initiator types (`models.py:1554`): `programmatic` (UI-created) | `agentic` (AI-created).

### 13.2 Execution Modes

`flow_definition.execution_method` (Source: `models.py:1546`):
- `immediate` — runs on creation/trigger.
- `scheduled` — runs at `scheduled_at` (DateTime).
- `recurring` — driven by `recurrence_rule` JSON: `{frequency, interval, days_of_week, timezone}` (Source: `models.py:1548`).

Scheduled execution is driven by `backend/flows/scheduled_flow_executor.py`. The engine tracks `last_executed_at`, `next_execution_at`, and `execution_count` on the definition (`models.py:1572-1574`).

### 13.3 Step Types

Step handlers registered in `FlowEngine.handlers` (Source: `backend/flows/flow_engine.py:2082-2102`):

| Type | Handler | Notes |
|---|---|---|
| `notification` | `NotificationStepHandler` | Sends a notification message to a recipient. Requires `recipient` or `recipients`, plus `message_template` or `content` in `config_json`. |
| `message` | `MessageStepHandler` | Sends a chat message (single-turn). |
| `tool` | `ToolStepHandler` | Invokes a tool/function. |
| `conversation` | `ConversationStepHandler` | Multi-turn AI conversation via `ConversationThread` (up to `max_turns`). |
| `slash_command` | `SlashCommandStepHandler` | Runs a platform slash command. |
| `skill` | `SkillStepHandler` | Agentic skill execution (Phase 16). |
| `custom_skill` | `SkillStepHandler` | Alias for tenant custom skills (Phase 22). |
| `summarization` | `SummarizationStepHandler` | AI summarization. Supports `thread_id`, `source_step`, or inline `text`/`content` in `config_json`. |
| `browser_automation` | `BrowserAutomationStepHandler` | Browser control (navigate/screenshot/click/fill/extract). |
| `Trigger`, `Subflow` + PascalCase aliases | Legacy handlers | Backward compat. |
| `AgentNode` | `ConversationStepHandler` alias | Alias accepted for compatibility (same config as `conversation`). |

Each `flow_node` row carries (Source: `models.py:1586-1639`):

| Field | Purpose |
|---|---|
| `name`, `step_description` | Human-readable identity. |
| `type` | One of the handler keys above. |
| `position` | 1-based execution order (unique per flow). |
| `config_json` | Step-type-specific config. |
| `timeout_seconds` | Default 300. |
| `retry_on_failure`, `max_retries`, `retry_delay_seconds` | Retry behavior (exponential backoff). |
| `condition` (JSON) | Conditional execution. |
| `on_success` / `on_failure` | `continue` \| `skip_to:{step}` \| `end` \| `retry` \| `skip` |
| `allow_multi_turn`, `max_turns` (default 20), `conversation_objective` | Conversation step config. |
| `agent_id` | Override flow-level default agent. |
| `persona_id` | Optional persona injection. |

### 13.4 Template Variables

Source: `backend/flows/template_parser.py:1-80`.

Variable references inside step configs/messages:

| Syntax | Meaning |
|---|---|
| `{{step_N.field}}` | Step by 1-based index, e.g. `{{step_1.status}}`. |
| `{{step_name.field}}` | Step by its `name`. |
| `{{previous_step.output}}` / `.summary` | Most recent completed step. |
| `{{flow.trigger_context.param}}` / `{{flow.id}}` | Flow-level context. |
| `{{step_1.raw_output.ports[0]}}` | JSON path with array access. |
| `{{truncate step_1.raw_output 100}}` | Helper function. |
| `{{#if step_1.success}}OK{{else}}FAIL{{/if}}` | Conditional block. |
| `{{default step_1.error "No error"}}` | Default fallback. |

Built-in helpers (Source: `template_parser.py:69-82`): `truncate`, `upper`, `lower`, `default`, `json`, `length`, `first`, `last`, `join`, `replace`, `trim`.

### 13.5 Flow Execution Status Lifecycle

**FlowRun statuses** (Source: `models.py:1663`):

| Status | Meaning |
|---|---|
| `pending` | Queued but not yet started |
| `running` | Currently executing steps |
| `completed` | All steps finished successfully |
| `failed` | One or more steps failed |
| `cancelled` | Manually cancelled by user or system |
| `paused` | Execution paused (e.g., conversation step awaiting response) |
| `timeout` | Exceeded time limit, auto-terminated |

**FlowNodeRun (step-level) statuses** (Source: `models.py:1708`):

| Status | Meaning |
|---|---|
| `pending` | Step queued, awaiting execution |
| `running` | Step currently executing |
| `completed` | Step finished successfully |
| `failed` | Step failed (may retry based on `retry_on_failure` config) |
| `skipped` | Step skipped due to condition or `on_failure=skip` |
| `cancelled` | Step cancelled (parent flow cancelled) |
| `timeout` | Step exceeded `timeout_seconds` |

### 13.6 Async Execution & Live Progress Modal

Flow execution via `POST /api/flows/{flow_id}/execute` is fully asynchronous. The endpoint creates a `FlowRun` record with status `pending`, returns it immediately (HTTP 202), and executes steps in a background task. The frontend's `ViewRunModal` opens instantly and polls `GET /api/flows/runs/{run_id}` + `GET /api/flows/runs/{run_id}/nodes` every 2 seconds while the run is active (`pending` or `running`). The modal shows a live progress bar (completed/total steps), per-step status badges with execution times, a pulsing "Live" indicator in the header, and a "remaining steps" counter. Polling stops automatically when the run reaches a terminal status (`completed`, `failed`, `cancelled`). The play button on the flows table shows a spinner during the brief API round-trip.

### 13.7 Stale Flow Cleanup

Source: `backend/flows/stale_flow_cleanup.py`. Periodically removes or marks stale flow runs (orphaned conversation threads, timed-out runs).

---

## 14. Scheduler & Triggers

### 14.1 Scheduled Events

Backed by the `ScheduledEvent` model and `ScheduledEventExecutor` (Source: `backend/scheduler/scheduler_service.py:1-30`). Supports:
- **Notifications** — smart reminders with contact resolution.
- **Conversations** — autonomous multi-turn AI-driven conversations, terminated by completion phrases (English + Portuguese list at `scheduler_service.py:32-41`).

Scheduled messages and tool-execution steps are handled by the Flows subsystem (see §13).

`backend/scheduler/worker.py` runs the periodic tick.

### 14.2 Scheduler Providers

Unified provider interface: `backend/agent/skills/scheduler/base.py`.

`SchedulerProviderType` enum (Source: `scheduler/base.py:19-23`): `flows`, `google_calendar`, `asana`.

Implementations:
- `backend/agent/skills/scheduler/flows_provider.py` — internal Flows/ScheduledEvent backend.
- `backend/agent/skills/scheduler/calendar_provider.py` — Google Calendar.
- `backend/agent/skills/scheduler/asana_provider.py` — Asana.

Event status values (`scheduler/base.py:27-32`): `scheduled`, `in_progress`, `completed`, `cancelled`, `failed`.

Provider selection is factory-driven: `backend/agent/skills/scheduler/factory.py` (reads `AgentSkillIntegration` rows, `factory.py:196`).

---

## 15. Channels

Tsushin's messaging transports are implemented as pluggable `ChannelAdapter` classes under `backend/channels/`. Each adapter implements a common contract: `start()`, `stop()`, `send_message()`, `health_check()`, and `validate_recipient()`. Adapters are registered in `backend/channels/registry.py` and used by `AgentRouter` for outbound delivery. Inbound handling is transport-specific (MCP bridges, bot watchers, webhook endpoints).

The base contract and shared types are defined at:
- `backend/channels/base.py` — abstract `ChannelAdapter`
- `backend/channels/types.py` — `SendResult`, `HealthResult` dataclasses

### 15.1 WhatsApp

**Source:** `backend/channels/whatsapp/adapter.py`

WhatsApp is delivered through a per-tenant containerized MCP bridge (Go-based WhatsApp bridge using whatsmeow). The backend never speaks the WhatsApp protocol directly — it proxies outbound messages to an MCP container that holds an authenticated WhatsApp session.

Adapter capability flags (`backend/channels/whatsapp/adapter.py:22-28`):

| Flag | Value |
|---|---|
| `channel_type` | `whatsapp` |
| `delivery_mode` | `pull` |
| `supports_threads` | false |
| `supports_reactions` | false |
| `supports_rich_formatting` | false |
| `supports_media` | true |
| `text_chunk_limit` | 4096 |

**MCP resolution flow** (`adapter.py:137-173`, `backend/services/whatsapp_binding_service.py`):
1. Resolve `Agent.whatsapp_integration_id` → `WhatsAppMCPInstance` row for the agent's dedicated bridge.
2. If no explicit binding exists, auto-resolve only when the tenant has exactly one unambiguous `instance_type == "agent"` WhatsApp instance.
3. If multiple candidate instances exist, the backend leaves the agent unbound and Graph/Studio surface that ambiguity instead of silently guessing.
4. Else fall back to the development default `http://127.0.0.1:8080/api`.

**Pre-send health gate** (`adapter.py:175-211`): Before each send the adapter hits `{mcp_api_url}/health` with a 5 s timeout. If the MCP reports `connected=false`, the send is refused to prevent queue buildup while the QR is not scanned.

**Recipient validation** (`adapter.py:123-135`): Accepts WhatsApp JIDs containing `@`, or phone numbers matching `^\+?\d{10,15}$`. Numeric IDs ≤10 digits without `+` (likely Telegram chat IDs) are explicitly blocked.

**Conversation delay** (humanization): `WHATSAPP_CONVERSATION_DELAY_SECONDS` env var (default `5.0` seconds). Source: `backend/settings.py:102-103`, env var `TSN_WHATSAPP_CONVERSATION_DELAY_SECONDS` (legacy `WHATSAPP_CONVERSATION_DELAY_SECONDS`). Stored per-instance in `whatsapp_conversation_delay_seconds` column (`backend/models.py:52`, Float default 5.0).

**Group and number filters** — stored on the MCP instance and on watcher records:
- System defaults: `Config.group_filters` / `Config.number_filters` (JSON lists) — `backend/models.py:19-20`.
- Per-trigger overrides: `trigger_group_filters`, `trigger_number_filters` (NULL = use system default) — `backend/models.py:342-343`.
- Per-instance filters: `group_filters`, `number_filters` on the MCP instance — `backend/models.py:2758-2759`.

**Health check** (`adapter.py:99-121`): Calls the MCP bridge's `/health` endpoint via `MCPSender.check_health()`, returning connected/disconnected with latency (ms).

**Runtime reconciliation** (`backend/services/mcp_container_manager.py`): before health-sensitive operations, the backend repairs stale MCP metadata from deterministic conventions and live container attrs. This includes recovering blank/stale `container_id` from `container_name`, normalizing `session_data_path` / `messages_db_path`, and restoring the canonical `mcp_api_url`. This is what prevents the legacy `Resource ID was not provided` failure when an old row has drifted from Docker state.

**WhatsApp MCP instance configuration reference** (Source: `models.py:2759-2773`):

| Field | Type | Default | Description |
|---|---|---|---|
| `is_group_handler` | Boolean | `false` | Only one instance per tenant should handle groups (prevents duplicate responses in multi-instance setups) |
| `group_filters` | JSON (nullable) | NULL | WhatsApp group names to monitor. Example: `["Support Group", "VIP Chat"]` |
| `number_filters` | JSON (nullable) | NULL | Phone number allowlist for DMs. Example: `["+5500000000001"]` |
| `group_keywords` | JSON (nullable) | NULL | Keywords that trigger bot responses in groups. Example: `["help", "bot", "support"]`. When set, the bot only responds to group messages containing these keywords. |
| `display_name` | String(100) (nullable) | NULL | Optional human-readable label for the instance (e.g., "Support Bot"). Shown in Hub UI; falls back to `phone_number` when NULL. |
| `dm_auto_mode` | Boolean | `true` | Auto-reply to direct messages from unknown senders. Disable to require contacts to be pre-registered. |
| `api_secret` | String(64) (nullable) | NULL | 32-byte hex-encoded token for cross-tenant MCP authentication (SSRF prevention) |
| `api_secret_created_at` | DateTime (nullable) | NULL | Timestamp for secret rotation tracking |

**E2E setup — WhatsApp channel (8-step guided wizard):**

The **WhatsApp Setup Wizard** (Hub → Communication → Setup Wizard) walks through the full configuration in 8 steps:

1. **Welcome** — overview of the setup process.
2. **Connect Phone** — enter an optional Instance Name (display label) and phone number, then scan the QR code. A bot contact is auto-created with the instance name.
3. **About You** — register yourself as a contact (name + phone + DM Trigger toggle). Pre-populates from your account name.
4. **DM Settings** — toggle Auto-Reply mode (Simple mode by default; Advanced reveals number allowlist).
5. **Group Settings** — toggle "Monitor all groups" or select specific groups (Advanced reveals keyword triggers).
6. **Contacts** — review auto-created contacts (bot + user) and add more manually.
7. **Bind Agent** — select which AI agent handles this WhatsApp number. Auto-creates ContactAgentMapping for user and bot contacts.
8. **All Done** — summary of all configured items with green/amber indicators.

The wizard can also be launched manually from the Hub Communication tab or from the onboarding tour's Communication Channels action. It no longer auto-launches after the main onboarding tour completes.

**Manual setup (alternative):**

1. Navigate to **Hub → Communication → WhatsApp** in the UI.
2. Click **Manual Setup** — provide a name and the WhatsApp phone number.
3. The system spawns a Docker container (`mcp-agent-tenant_{timestamp}_{id}`) on `tsushin-network`.
4. **Scan the QR code** — visible in the UI or via `docker logs <container_name> --tail=20`. The QR expires after ~60 seconds; refresh if needed.
5. Once authenticated, the instance status changes to `running` with `connected=true`.
6. **Configure filters** — set `group_filters`, `number_filters`, and `group_keywords` on the instance to control where the bot responds.
7. **Assign to an agent** — on the agent's Channels tab, set `whatsapp_integration_id` to point to this instance.
8. **Test** — send a message from the WhatsApp number; the bot should respond via the assigned agent.

**Hub QR recovery behavior:** the Hub QR modal now has three explicit states: `loading`, `ready`, and `degraded`. After repeated health failures or repeated empty QR polls, the UI stops the infinite spinner and offers recovery actions (`Restart`, `Reset Auth`, reopen QR). The same recovery flow exists for the compose-managed tester card.

**Graph + Studio consistency:** Graph View consumes `resolved_whatsapp_integration_id`, `whatsapp_binding_status`, and `whatsapp_binding_source` from `/api/v2/agents/graph-preview`. This allows Graph to show:
- solid edge for explicit binding
- dashed edge for resolved-default binding
- `WhatsApp Unassigned` warning node when the channel is enabled but ambiguous/unassigned — **suppressed on a truly fresh tenant** (zero WhatsApp instances *and* no agent carrying a stale `whatsapp_integration_id` pointing at a missing instance). The warning still surfaces when a real stale explicit binding exists so operators see the drift signal without first-run noise.

**Getting Started Checklist:** The Watcher dashboard displays a "Getting Started" widget tracking 5 setup milestones: Configure Agent, Connect Channel, Add Contacts, Test in Playground, Create Flow. It auto-hides when all items are complete and can be dismissed.

**Hub Integration Summary:** A compact status strip above the Hub tab bar shows connection counts for AI Providers, WhatsApp, Telegram, Slack, Discord, and Webhooks at a glance.

**Settings Progressive Disclosure:** The Settings page groups cards into "Essential" (Organization, Team Members, System AI, Integrations) always visible, and "Advanced" collapsed by default.

#### 15.1.1 Migration: LID support (v0.6.0)

WhatsApp is rolling out **Linked Device IDs (LIDs)** — a new identifier format that replaces the historical phone-number-based JID for many participants (especially in group chats, where privacy rules now obscure direct phone numbers). v0.6.0 ships three coordinated changes so existing Tsushin tenants upgrading from 0.5.x don't lose contact continuity:

1. **Contact auto-linking** — when an inbound message arrives with a new LID, the adapter looks up the existing `Contact` row by phone number (if the phone number is still exposed) and attaches the LID as an alternate identifier on the contact's `ContactChannelMapping`. No manual merge required.
   Source: `backend/channels/whatsapp/adapter.py` + `backend/services/contact_service.py`.

2. **UserAgentSession fallback via phone number** — `UserAgentSession` lookups (used for per-contact default agent resolution) now try LID-keyed rows first, then fall back to phone-number-keyed rows. Sessions created before the migration keep working until they're rewritten on next contact, at which point they get upgraded to LID keys.
   Source: `backend/services/user_agent_session_service.py`.

3. **ContactAgentMapping dual-key lookup** — `ContactAgentMapping` resolution accepts either a LID or a phone-number key and returns the first match. This keeps slash-command permissions, default-agent assignments, and DM trigger rules pointing at the right contact even as WhatsApp phases in LIDs for groups.
   Source: `backend/services/contact_agent_mapping_service.py`.

**Operational notes:**
- No migration script is required — the upgrade is transparent. Existing contacts continue to work; LIDs are attached on the fly as they arrive.
- If you see a group member that Tsushin treats as a new contact after the upgrade (because WhatsApp switched them to LID-only exposure), open the contact modal and add the previous phone number as an alternate identifier. The bot will then recognize both.
- Sentinel audit events for WhatsApp continue to log the original raw identifier (LID or phone), so the audit trail survives the transition.

### 15.2 Telegram

**Source:** `backend/channels/telegram/adapter.py`

Wraps a `TelegramSender` (bot token holder) using the official Telegram Bot HTTP API. Watchers/lifecycle are managed externally by `backend/services/telegram_watcher_manager.py` and `backend/services/telegram_bot_service.py`.

Capability flags (`adapter.py:19-25`):
- `delivery_mode=pull`, `text_chunk_limit=4096`, `supports_rich_formatting=true`, `supports_media=true`.

**Recipient validation** (`adapter.py:102-110`): Strictly numeric chat ID; any non-digit recipient is blocked.

**Send behavior** (`adapter.py:44-84`): If `media_path` is provided, uses `send_photo` with the text as caption; otherwise `send_message`.

**Health check** (`adapter.py:86-100`): Calls the Telegram bot API `getMe` and reports the bot's `@username`. `ChannelHealthService` directly hits `https://api.telegram.org/bot{token}/getMe` as well (`channel_health_service.py:268-269`).

**Token storage**: Encrypted with Fernet using the Telegram per-workspace encryption key (`services/encryption_key_service.get_telegram_encryption_key`, `services/channel_health_service.py:451-466`). Stored on `TelegramBotInstance.bot_token_encrypted`.

**E2E setup — Telegram channel:**

1. Create a bot via **@BotFather** on Telegram — use `/newbot`, choose a name and username.
2. Copy the bot token (format: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`).
3. Navigate to **Hub → Channels → Telegram** in the UI.
4. Click **Add Bot** — paste the bot token; the system validates by calling `getMe`.
5. Choose delivery mode: **Webhook** (recommended for production) or **Polling** (simpler, no public URL required).
6. If using webhook: provide the publicly accessible URL where Telegram will send updates.
7. **Assign to an agent** — on the agent's Channels tab, set `telegram_integration_id`.
8. **Test** — message the bot on Telegram; it should respond via the assigned agent.

### 15.2a Public Ingress Resolver

**Source:** `backend/services/public_ingress_resolver.py`, `backend/api/routes_tenant_settings.py`, `frontend/components/PublicBaseUrlCard.tsx`.

Slack HTTP Events, Discord Interactions, and Webhook-as-Channel all need a public HTTPS URL that reaches this backend. Three mechanisms could provide one, and before v0.6.1 they were inconsistent. The resolver unifies them.

**Endpoint (tenant-facing):**
```
GET /api/tenant/me/public-ingress
→ { "url": "https://...", "source": "override"|"tunnel"|"dev"|"none",
    "warning": null|string, "override_url": null|string }
```

**Precedence (first match wins):**

1. **`override`** — `tenant.public_base_url` (the Ingress Override card in Hub → Communication). Set and format-valid ⇒ this wins. Set but invalid ⇒ `source=override`, `url=null`, `warning` explains the problem (so the UI can surface the stored-but-broken state instead of silently falling through).
2. **`tunnel`** — the global Remote Access tunnel (`/system/remote-access`) is running and has a `public_url`. **Intentionally decoupled from the `remote_access_enabled` login gate**: a tenant can receive webhooks via the shared tunnel path even when tunnel-based login is disabled for their users.
3. **`dev`** — `TSN_DEV_PUBLIC_BASE_URL` environment variable on the backend. Dev escape hatch only; must not be set in production.
4. **`none`** — no ingress; the UI shows a call-to-action banner.

**Validation on `PATCH /api/tenant/me/settings`:**
- Requires `https://` in production (`http://` allowed only when `TSN_DEV_PUBLIC_BASE_URL` is set).
- Rejects credential-laced URLs (`user:pass@host`).
- Requires a public FQDN (`localhost` and single-label hostnames rejected).
- DNS pre-resolution (async, 2 s timeout) — typos are caught at save time.
- Every write logged via `log_tenant_event(..., TenantAuditActions.SETTINGS_UPDATE, ...)` with userinfo scrubbed from logged old/new values.

**Consumers.** `SlackSetupWizard`, `DiscordSetupWizard`, `WebhookSetupModal`, and the inline "Inbound:" copy button on the Webhook card in Hub all call `api.getMyPublicIngress()` and render a source badge ("via platform tunnel", "tenant override", "dev environment"). The **PublicBaseUrlCard** (renamed "Ingress Override (Advanced)") always displays the currently-resolved URL and its source, with a collapsible override input that auto-expands when `source === 'none'`.

**Operator guidance:**
- **SaaS deployments:** enable Remote Access globally and toggle `remote_access_enabled` per tenant for login; Slack/Discord webhooks work for every tenant without additional setup. Override is for exceptions (branded domains, corporate proxies).
- **Self-hosted without a tunnel:** set `TSN_DEV_PUBLIC_BASE_URL` or use the tenant override. Both work.
- **Local dev:** `TSN_DEV_PUBLIC_BASE_URL=https://<your-tunnel>.trycloudflare.com docker-compose up -d --build backend` — no tenant override needed, no global tunnel config needed.

**Invitation-link consumer (since 2026-04-19):** the resolver backs `resolve_invitation_base_url(request, tenant)`, a multi-tenant-aware helper used by the tenant (`POST /api/team/invite`) and global-admin (`POST /api/admin/invitations`) invite endpoints plus the email service. Precedence for building the absolute invite URL: invitation's **own** `tenant.public_base_url` (never the calling admin's tenant) → platform tunnel → request origin (honoring `X-Forwarded-Proto` / `X-Forwarded-Host` so Cloudflare named-tunnel hostnames survive the Caddy proxy) → `FRONTEND_URL` env. This ensures the same link is portable across `https://localhost` QA, `http://localhost:3030` dev, branded tenant domains, and Cloudflare Tunnel — and safe under concurrent multi-tenant invites. Unit-tested via `backend/tests/test_invitation_link_portability.py` (9 cases).

### 15.3 Slack

**Source:** `backend/channels/slack/adapter.py`

Uses `slack_sdk.WebClient` for REST calls and supports Socket Mode or HTTP Events API for inbound (lifecycle managed externally).

Capability flags (`adapter.py:20-26`):
- `delivery_mode=push`, `supports_threads=true`, `supports_reactions=true`, `supports_rich_formatting=true` (Block Kit), `supports_media=true`, `text_chunk_limit=4000`.

**Send behavior** (`adapter.py:54-113`):
- Text: `chat_postMessage` with optional `thread_ts`.
- File: `files_upload_v2` with `initial_comment` and `thread_ts`.
- All blocking calls dispatched via `loop.run_in_executor` (slack_sdk is synchronous).

**Recipient validation** (`adapter.py:130-134`): First character must be `C` (channel), `G` (group), `D` (DM channel), `U` or `W` (user ID).

**Health check** (`adapter.py:115-128`): Calls `auth.test` and returns bot user + team name on success.

**Model:** `SlackIntegration` (`backend/models.py:2835`). Bot token is Fernet-encrypted per tenant (`services/encryption_key_service.get_slack_encryption_key`).

**OAuth & scopes:** Credentials and scope configuration are not enumerated in the adapter; Slack app installation produces a `xoxb-` bot token that is stored encrypted on the integration row. Not verified in source — refer to SlackIntegration model and OAuth install route for exact scopes.

**Slack access control configuration** (Source: `models.py:2867-2868`):

| Field | Type | Default | Description |
|---|---|---|---|
| `dm_policy` | String(20) | `"allowlist"` | DM access policy: `open` (accept all DMs), `allowlist` (only respond in allowed channels), `disabled` (ignore all DMs) |
| `allowed_channels` | JSON | `[]` | List of Slack channel IDs the bot may respond in. Only used when `dm_policy=allowlist`. Example: `["C0123ABC", "C0456DEF"]` |

**E2E setup — Slack channel:**

1. **Create a Slack App** at [api.slack.com/apps](https://api.slack.com/apps) (the "From a manifest" option is the fastest way — Tsushin's recommended manifest enables Socket Mode and the bot scopes below in one shot):
   - Bot scopes: `app_mentions:read`, `channels:history`, `channels:read`, `chat:write`, `files:write`, `groups:history`, `im:history`, `im:read`, `im:write`, `mpim:history`, `users:read`.
   - Bot events: `app_mention`, `message.channels`, `message.groups`, `message.im`, `message.mpim`.
   - For **Socket Mode** (recommended): enable Socket Mode under Settings, then generate an **App-Level Token** with the `connections:write` scope (you'll get an `xapp-...` token).
   - For **HTTP Events API**: the Tsushin UI will show you the exact Request URL after you save the integration — paste that into Event Subscriptions → Request URL. Also copy the Signing Secret and App ID from Basic Information.
2. **Install the app** to your workspace — copy the `xoxb-` bot token from OAuth & Permissions.
3. (HTTP mode only) Ensure a **Public Ingress** is available for this tenant — either the global Remote Access tunnel (enabled via `/system/remote-access`) or an **Ingress Override** set in Hub → Communication. See §15.2a for how the resolver picks between them. Socket Mode does not need a public ingress.
4. Navigate to **Hub → Channels → Slack** in the UI.
5. Click **Connect Workspace** — paste the bot token plus the App-Level Token (Socket Mode) or the App ID + Signing Secret (HTTP mode). The modal will preview the exact webhook URL for HTTP mode.
6. Set `dm_policy` — `open` to accept all DMs, `allowlist` to restrict to specific channels, or `disabled`.
7. If using allowlist, add the Slack channel IDs where the bot should operate.
8. **Assign to an agent** — on the agent's Channels tab, enable the Slack channel and pick the workspace.
9. **Invite the bot** to your channel: `/invite @<bot name>` from inside Slack.
10. **Test** — message the bot in the allowed channel or DM; it should respond via the assigned agent. Replies in channel are auto-threaded under the original message (V060-CHN-031).

**How Socket Mode is wired (V060-CHN-002):** `SlackSocketModeManager` (in `backend/services/slack_socket_mode_manager.py`) is started by `app.py`'s lifespan and spins up one `slack_sdk.socket_mode.aiohttp.SocketModeClient` per active `mode='socket'` integration. The integration's create/update/delete endpoints in `routes_slack.py` call `restart_one()` / `stop_one()` so workers track integration state without a backend restart. The worker filters out non-message events and bot-authored messages, then enqueues the rest into `message_queue` (channel='slack'); the `QueueWorker._process_slack_message` dispatcher routes through `AgentRouter` and the bot replies via the existing `SlackChannelAdapter`.

### 15.4 Discord

**Source:** `backend/channels/discord/adapter.py`

Uses the Discord REST API v10 directly (`https://discord.com/api/v10`) via `aiohttp`. Gateway/intents are only needed for inbound events and are managed externally.

Capability flags (`adapter.py:27-33`):
- `delivery_mode=push`, `supports_threads=true`, `supports_reactions=true`, `supports_rich_formatting=true` (Markdown + Embeds), `supports_media=true`, `text_chunk_limit=2000`.

**Auth:** Bot token sent as `Authorization: Bot {token}` header (`adapter.py:50-55`).

**Send behavior** (`adapter.py:67-139`):
- Text: `POST /channels/{id}/messages` with `{"content": text}`. Supports `thread_id` via `message_reference`.
- Media: Multipart upload using `payload_json` + `files[0]`.

**Recipient validation** (`adapter.py:164-168`): Discord snowflake — 17-20 digit numeric string.

**Health check** (`adapter.py:141-162`): `GET /users/@me`.

**Model:** `DiscordIntegration` (`backend/models.py:2876`). Bot token Fernet-encrypted (`services/encryption_key_service.get_discord_encryption_key`).

**Discord access control configuration** (Source: `models.py:2904-2906`):

| Field | Type | Default | Description |
|---|---|---|---|
| `dm_policy` | String(20) | `"allowlist"` | DM access policy: `open` (accept all DMs), `allowlist` (only respond in allowed guilds/channels), `disabled` (ignore all DMs) |
| `allowed_guilds` | JSON | `[]` | List of Discord guild (server) IDs the bot may operate in. Example: `["123456789012345678"]` |
| `guild_channel_config` | JSON | `{}` | Per-guild channel configuration — controls which channels within each guild the bot listens to. Example: `{"123456789012345678": {"channels": ["987654321098765432"]}}` |

**E2E setup — Discord channel:**

1. Ensure this tenant has a **Public Ingress** — either the platform-managed Remote Access tunnel (global admin enables it in `/system/remote-access`) or an **Ingress Override** set in Hub → Communication. See §15.2a. Discord requires a publicly-reachable HTTPS URL for the Interactions endpoint — there is no Socket Mode equivalent. For local dev without a tunnel, set `TSN_DEV_PUBLIC_BASE_URL` in the backend environment and restart the container.
2. **Create a Discord Application** at [discord.com/developers](https://discord.com/developers/applications).
3. On **General Information**: copy the **Application ID** and the **Public Key** (64-character hex Ed25519). Both are required by Tsushin.
4. Under **Bot**: reset and copy the bot token; enable **Message Content Intent** under Privileged Gateway Intents.
5. Under **OAuth2 → URL Generator**: select scopes `bot` + `applications.commands` and permissions `Send Messages`, `Read Message History`, `Attach Files`, `Read Messages/View Channels`. Use the generated URL to invite the bot to your server.
6. Navigate to **Hub → Channels → Discord** in the UI.
7. Click **Connect Bot** — paste the **Application ID**, **Bot Token**, and **Public Key**. The modal will preview the exact Interactions Endpoint URL after save.
8. Copy that URL and paste it into Discord Dev Portal → General Information → **Interactions Endpoint URL**, then click Save Changes. Discord PINGs the URL for verification — Tsushin handles the PING automatically with the per-integration public key (BUG-311 fix).
9. Set `dm_policy` and `allowed_guilds` to control where the bot responds.
10. **Assign to an agent** — on the agent's Channels tab, enable the Discord channel and pick the bot.
11. **Test** — DM the bot in Discord or invoke it from a server channel; it should respond via the assigned agent.

**Why HTTP Interactions, not Gateway:** Tsushin uses Discord's HTTP Interactions endpoint (Ed25519-signed) rather than the Gateway WebSocket because it's stateless, scales horizontally, and doesn't require per-process bot session tracking. Inbound interactions arrive at `/api/channels/discord/{integration_id}/interactions`; the route ACKs Discord with a Type 5 (deferred response) within the 3-second window, then enqueues the interaction into `message_queue` (channel='discord'). `QueueWorker._process_discord_message` routes the message through `AgentRouter` and the agent's reply is sent via `DiscordChannelAdapter` (REST API).

### 15.5 Webhook Trigger

**Source:** `backend/channels/webhook/trigger.py`, `backend/api/routes_webhook_instances.py`, `backend/api/routes_webhook_inbound.py`

Webhook is now a first-class **Trigger**, not a conversational channel. Inbound external systems still POST HMAC-signed events to `/api/webhooks/{slug}/inbound` (handled by `routes_webhook_inbound.py`, enqueued into `MessageQueue`, routed through `AgentRouter` by `QueueWorker._handle_webhook`). Outbound responses use `WebhookTrigger.notify_external_system(...)` to POST back to the configured `callback_url`.

**URI slug modes (v0.7.1):** each integration has a human-readable `slug` used in the inbound path.
- **Auto** (default on create) — server generates `wh-{6-hex}`.
- **Custom** — user-supplied. Validated against `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (3–64 chars, lowercase, must start with a letter, no leading/trailing/consecutive hyphens), checked against the reserved set (`inbound, rotate-secret, health, status, test, callback, docs, openapi, api, webhooks, admin, v1`), and required to be globally unique.
- Global uniqueness is enforced because the inbound route is authenticated by HMAC *after* the row lookup — the slug is the only identifier used to resolve the tenant.
- **Backward compatibility:** the inbound route still accepts a numeric integration id via a `slug.isdigit()` fallback, so any legacy `/api/webhooks/{id}/inbound` URL keeps working.
- **Live availability check:** `GET /api/triggers/webhook/slug-available?slug=…[&exclude_id=…]` → `{ available, reason }` backs the UI's green-check / red-X indicator. `exclude_id` lets the edit flow check "is this slug free for me to keep or rename to?" without colliding with itself.

**Lifecycle: edit / pause / delete.** Each card exposes three actions in addition to Rotate Secret:
- **Edit** — opens `WebhookEditModal` to change the name, slug, callback URL, rate limit, and IP allowlist. Secret rotation is intentionally separate (Rotate button) to avoid mixing destructive secret operations with non-destructive config edits.
- **Pause / Enable toggle** — flips `is_active` via `PATCH /api/triggers/webhook/{id}`. When paused, inbound `POST /api/webhooks/{slug}/inbound` returns `403` and the slug is still reserved globally; nothing else will be able to create a new integration with the same slug. **Only `DELETE` frees the slug for reuse.**
- **Delete** — removes the integration row; agent bindings are nulled via `ON DELETE SET NULL`.

Capability flags (`trigger.py:19-27`):
- `delivery_mode=push`, text-only in v1 (`supports_media=false`), `text_chunk_limit=16000`.

**Outbound callback POST** (`trigger.py:74-171`):
- Optional — governed by `integration.callback_enabled` + `integration.callback_url`. If disabled, the trigger reports success with `message_id="webhook_inbound_only"` (result pollable via `/api/v1/queue/{id}`).
- SSRF-validated via `utils/ssrf_validator.validate_url()` before the POST.
- Timeout: `10.0` seconds (`_CALLBACK_TIMEOUT_SECONDS`, `trigger.py:17`).
- Response body capped at `65536` bytes (`_MAX_RESPONSE_BYTES`, `trigger.py:16`).
- `follow_redirects=False`.

**HMAC signing** (`trigger.py:108-121`):
- Canonical payload JSON (sorted keys, compact separators) includes: `event`, `webhook_id`, `timestamp`, `text`, `agent_id`, `sender_key`, `source_id`.
- Signature: `HMAC-SHA256(secret, f"{timestamp}.".bytes + body_bytes)` — replay-protected.
- Headers emitted: `X-Tsushin-Signature: sha256={hex}`, `X-Tsushin-Timestamp`, `X-Tsushin-Event`, `X-Tsushin-Webhook-Id`, `User-Agent: Tsushin-Webhook/1.0`.

**Secret encryption:** `api_secret_encrypted` is decrypted via `TokenEncryption` keyed by the webhook encryption master key + per-tenant derivation (`trigger.py:52-68`, `services/encryption_key_service.get_webhook_encryption_key`).

**Health:** Uses stored snapshot from the `WebhookIntegration` row (`is_active`, `status`, `circuit_breaker_state`, `health_status`, `circuit_breaker_failure_count`) — no live probe to avoid amplification (`trigger.py:173-190`).

**Model:** `WebhookIntegration` (`backend/models.py:2918`).

**Criteria filtering:** `WebhookIntegration.trigger_criteria` stores the shared trigger-criteria envelope. Supported payload matchers live in `filters.jsonpath_matchers` with `path`, `operator`, and optional `value`. Supported operators are `exists`, `not_exists`, `equals`, `not_equals`, `contains`, `in`, and `regex`. Criteria are evaluated before wake dispatch; a mismatch returns `204 No Content` from inbound processing and records `filtered_out` in `channel_event_dedupe`.

**Canonical management surface:** `GET /api/triggers` lists trigger catalog entries, and `/api/triggers/webhook/*` is the canonical CRUD namespace. Legacy `Agent.webhook_integration_id` bindings still exist during the migration window, but the long-term routing model is instance-level `default_agent_id` plus trigger-aware default resolution.

**E2E setup — Webhook trigger:**

1. Navigate to **Hub → Communication → Webhook Triggers** in the UI.
2. Click **+ New Webhook Trigger** — provide a name, choose **Auto** or **Custom** URI mode (Custom gets a live-validated slug input), and optionally a callback URL for outbound responses.
3. The system generates an HMAC signing secret. A reveal modal shows the full plaintext once with a copy button (auto-copied to clipboard) **plus a ready-to-paste `openssl`+`curl` snippet pre-filled with your secret and inbound URL** — copy the block, paste it into any shell with `openssl` + `curl`, and a successful reply (`{"status":"queued",…}`) confirms the integration end-to-end without leaving the browser. **Save the secret now** — the same modal will appear again only if you rotate the secret.
4. Configure optional defenses: IP allowlist (CIDR ranges), rate limit (RPM), max payload size.
5. **Choose the receiving agent** — during the Wave 1 checkpoint, routing can still fall back to the legacy `Agent.webhook_integration_id` binding where present; the v0.7.0 target model is the trigger's own `default_agent_id` plus `/settings/default-agents`.
6. **Test inbound** — send a signed event to your webhook (the absolute URL appears in the card, e.g. `https://localhost/api/webhooks/my-crm/inbound`):

```bash
# Generate HMAC signature
TIMESTAMP=$(date +%s)
BODY='{"text":"Hello from webhook","sender_key":"external-user-1"}'
SIGNATURE=$(printf '%s.%s' "${TIMESTAMP}" "${BODY}" | openssl dgst -sha256 -hmac "<your_api_secret>" -hex | awk '{print $2}')

# Send inbound event (use the slug shown on the card, or the numeric id for legacy URLs)
curl -X POST https://localhost/api/webhooks/<slug>/inbound \
  -H "Content-Type: application/json" \
  -H "X-Tsushin-Signature: sha256=${SIGNATURE}" \
  -H "X-Tsushin-Timestamp: ${TIMESTAMP}" \
  -d "${BODY}"
```

7. If `callback_url` is configured, the agent's response will be POSTed there with HMAC-signed headers.
8. **Rotate Secret** — the button on each card invalidates the previous secret and opens the same reveal modal showing the fresh plaintext. Update your external system before the next request, or it will start failing with `403`.

#### Email triggers (Gmail-backed control plane)

**Source:** `backend/api/routes_email_triggers.py`, `backend/models.py`, `frontend/components/triggers/EmailTriggerWizard.tsx`

Email triggers are modeled as trigger rows, not communication channels. The Gmail account remains a reusable integration resource, and the trigger stores the control-plane configuration that will later drive inbox polling and wake-event emission.

**Model:** `EmailChannelInstance` stores:
- trigger display name (`integration_name`)
- `gmail_integration_id`
- `default_agent_id`
- optional Gmail search query (`search_query`)
- optional shared trigger criteria envelope (`trigger_criteria`) with Gmail query helpers and JSONPath matchers for payload fields such as `$.message.body_text`
- poll interval (`30-3600` seconds)
- `is_active`, `status`, and health snapshot fields

**API surface:**
- `GET /api/triggers/email` — list the tenant's persisted email trigger rows
- `POST /api/triggers/email` — create a trigger row bound to an existing Gmail integration
- `POST /api/triggers/email/test-query` — test a Gmail integration and query before saving
- `GET /api/triggers/email/{id}` — fetch one trigger
- `PATCH /api/triggers/email/{id}` — rename, rebind the Gmail integration, change the default agent, search query, poll interval, or active state
- `POST /api/triggers/email/{id}/test-query` — test the saved trigger query and return sample message previews
- `POST /api/triggers/email/{id}/notification-subscription` — enable/reuse the managed WhatsApp notification action for matching Email wakes
- `POST /api/triggers/email/{id}/poll-now` — force one immediate Gmail poll for validation or operator checks
- `POST /api/triggers/email/{id}/triage-subscription` — enable/reuse managed Gmail draft triage
- `DELETE /api/triggers/email/{id}` — delete one trigger row

**Hub flow:** Hub → Communication → **Triggers** → **+ New Trigger** → **Email**
- Confirms Google OAuth app credentials
- Reuses or creates a Gmail account through the existing OAuth popup contract
- Captures the trigger name, Gmail search query, poll interval, default agent, and active/paused state
- Saves a persisted trigger row without treating Gmail as a conversational channel

**Runtime notes:**
- Gmail-backed Email triggers are polled by the scheduler worker through `EmailTrigger.poll_active()`. The poller supports Gmail search queries, persisted criteria evaluation through `TriggerDispatchService`, cursor/dedupe advancement, wake-event dispatch, and system-owned managed triage or WhatsApp notification subscriptions.
- A keyword flow such as Gmail search query `XYZ` can be saved in `search_query` and mirrored into `trigger_criteria.filters.email.search_query`; optional JSONPath matchers can further require body text such as `$.message.body_text contains "XYZ"` before a wake/run is emitted.
- Email dedupe remains once per Gmail message id (`gmail:{message_id}`) plus cursor advancement, so polling the same matching message again does not send a second WhatsApp notification or create a second run.
- Managed triage creates Gmail drafts only when the linked Gmail integration has a draft-compatible scope. Without `gmail.compose`, `gmail.modify`, or `mail.google.com/`, triage runs fail closed with a missing-scope result rather than sending mail.
- Managed WhatsApp notification requires an active tenant-owned WhatsApp agent instance. Notification messages include subject, sender, Gmail account, optional date, Gmail message id, and a short plain-text preview; email body text is treated as untrusted context.
- Trigger routing uses the trigger-aware default-agent chain in `default_agent_service.py`: explicit agent -> trigger instance default -> legacy bound agent -> tenant default.
- If no active agent resolves for a trigger, the runtime is expected to fail closed rather than silently enqueue work.

#### Jira triggers

**Source:** `backend/api/routes_jira_triggers.py`, `backend/channels/jira/trigger.py`, `frontend/components/triggers/TriggerSetupModal.tsx`

Jira triggers watch Jira Cloud REST JQL queries and normalize matching issue payloads into `TriggerDispatchInput`. Track B introduced the persisted trigger row, JQL test-query, credential encryption, detail UI, and issue-normalization contract; v0.7.0 finalization adds the live poll loop and managed WhatsApp notifier proof.

**API surface:**
- `GET/POST /api/triggers/jira`
- `GET/PATCH/DELETE /api/triggers/jira/{id}`
- `POST /api/triggers/jira/test-query`
- `POST /api/triggers/jira/{id}/test-query`
- `POST /api/triggers/jira/{id}/notification-subscription`
- `POST /api/triggers/jira/{id}/poll-now`

**Stored config:** site URL, project key, JQL, optional auth email + encrypted API token preview, poll interval, trigger criteria, default agent, active/status/health fields, and cursor/activity timestamps.

**Runtime and notifier contract:**
- Active Jira triggers poll on their configured interval using Jira Cloud's enhanced JQL search endpoint (`/rest/api/3/search/jql`), dispatch matching issues through the shared trigger dispatch path, and persist dedupe evidence so the same issue is processed once.
- Jira credentials are UI-managed and encrypted at rest; API responses expose only `api_token_preview`.
- The managed WhatsApp notifier is an outbound action for Jira trigger results, not a Jira channel. It requires an operator-provided recipient, must use a tenant-owned WhatsApp instance, and should produce one notification per deduped Jira issue.
- Jira base URLs are normalized by stripping a trailing `/jira`; issue links and REST calls use the canonical site root.
- Browser QA covers setup/edit/test-query, detail state, wake-event evidence, and the poll-now manual proof action. Backend QA covers successful polling, duplicate suppression, missing/paused channel failures, and cross-tenant ownership rejection.

#### Schedule triggers

**Source:** `backend/api/routes_schedule_triggers.py`, `backend/channels/schedule/trigger.py`, `backend/scheduler/worker.py`

Schedule triggers use `ScheduleChannelInstance` as their source of truth. The scheduler worker remains the poll-loop driver, but trigger-backed schedules dispatch wake events through `ScheduleTrigger.poll_due()` instead of creating or executing legacy `ScheduledEvent` rows.

**API surface:**
- `GET/POST /api/triggers/schedule`
- `GET/PATCH/DELETE /api/triggers/schedule/{id}`
- `POST /api/triggers/schedule/preview`

**Stored config:** cron expression, IANA timezone, optional payload template, trigger criteria, next/last fire timestamps, default agent, and health/activity fields.

#### GitHub triggers

**Source:** `backend/api/routes_github_triggers.py`, `backend/api/routes_github_inbound.py`, `backend/channels/github/trigger.py`

GitHub triggers receive signed repository webhook deliveries and dispatch matching events to continuous-agent wakeups.

**API surface:**
- `GET/POST /api/triggers/github`
- `GET/PATCH/DELETE /api/triggers/github/{id}`
- `POST /api/triggers/github/test-connection`
- `POST /api/triggers/github/{id}/check-connection`
- `POST /api/triggers/github/{id}/inbound`

**Stored config:** auth method (`pat` or `app`), repository owner/name, optional installation id, encrypted PAT preview, encrypted webhook-secret preview, event filters, branch/path/author filters, trigger criteria, default agent, and delivery/activity cursors.

**Inbound contract:** GitHub sends `X-Hub-Signature-256`, `X-GitHub-Event`, and `X-GitHub-Delivery`. The route validates HMAC using the stored webhook secret, applies repo/event/branch/path/author filters, dedupes on delivery id, and dispatches via `TriggerDispatchService`.

### 15.6 Playground

**Source:** `backend/channels/playground/adapter.py`

The web Playground is request/response (API + WebSocket streaming) — responses are delivered synchronously via `PlaygroundService` and the adapter's `send_message` is a no-op success (`adapter.py:39-50`).

Capability flags (`adapter.py:20-26`):
- `delivery_mode=push`, `supports_threads=true`, `supports_rich_formatting=true`, `supports_media=true`, `text_chunk_limit=65536`.

**Health:** Always healthy — no external connection (`adapter.py:52-54`).

Underlying services:
- `backend/services/playground_service.py`
- `backend/services/playground_websocket_service.py`
- `backend/services/playground_thread_service.py`
- `backend/services/playground_message_service.py`
- `backend/services/playground_document_service.py`

### 15.7 Channel Health Monitoring & Circuit Breakers

**Source:** `backend/services/channel_health_service.py`, `backend/services/circuit_breaker.py`

`ChannelHealthService` is a background asyncio task that periodically probes every active WhatsApp/Telegram/Slack/Discord instance and transitions a per-instance circuit breaker across `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`.

**Configuration (env vars)** — `backend/settings.py:204-207`:

| Env var | Default | Purpose |
|---|---|---|
| `TSN_CHANNEL_HEALTH_ENABLED` | `true` | Enable the background monitor |
| `TSN_CHANNEL_HEALTH_CHECK_INTERVAL` | `30` (seconds) | Probe interval |
| `TSN_CHANNEL_CB_FAILURE_THRESHOLD` | `3` | Consecutive failures to trip CB to OPEN |
| `TSN_CHANNEL_CB_RECOVERY_TIMEOUT` | `60` (seconds) | OPEN → HALF_OPEN cooldown |

**Per-channel probe logic** (`channel_health_service.py:187-445`):
- WhatsApp: delegates to `MCPContainerManager.health_check(instance)`; healthy if `status` ∈ {healthy, degraded} AND `connected=True`.
- Telegram: calls `api.telegram.org/bot{token}/getMe` with 10 s timeout.
- Slack: constructs `SlackChannelAdapter` and calls its `health_check` (`auth.test`).
- Discord: constructs `DiscordChannelAdapter` and calls `/users/@me`.

**State-transition side effects** (`_handle_transition`, `channel_health_service.py:519-611`):
1. Emit Prometheus counters (`TSN_CIRCUIT_BREAKER_TRANSITIONS_TOTAL`) and gauge (`TSN_CIRCUIT_BREAKER_STATE`, CLOSED=0, OPEN=1, HALF_OPEN=2).
2. Persist a `ChannelHealthEvent` row (isolated DB session).
3. Emit WebSocket event via `WatcherActivityService.emit_channel_health`.
4. If transition is to OPEN, dispatch an alert via `ChannelAlertDispatcher`.

**Admin overrides** (`channel_health_service.py:775-799`): `reset_circuit_breaker()` forces CLOSED, `on_external_recovery()` jumps to HALF_OPEN, `manual_probe()` triggers an immediate probe.

Dispatcher for channel alerts: `backend/services/channel_alert_dispatcher.py`.

---

## 16. Contacts & Channel Mapping

### 16.1 Contact Form Fields

Source: `frontend/app/agents/contacts/page.tsx:17-52` (form interface), `:97-194` (handlers). DB: `backend/models.py:144-181`.

| Field | Type | DB column |
|---|---|---|
| `friendly_name` | text, required | `friendly_name` (`:155`) |
| `phone_number` | text | `phone_number` (deprecated — prefer channel_mappings) (`:157`) |
| `telegram_id` | text | `telegram_id` (deprecated) (`:160`) |
| `telegram_username` | text | `telegram_username` (deprecated) (`:161`) |
| `role` | `user` \| `agent` \| `external` | `role` (default `user`) (`:163`) |
| `is_dm_trigger` | Boolean, default true | `is_dm_trigger` (`:165`) |
| `slash_commands_enabled` | tri-state (null\|true\|false) | `slash_commands_enabled` (NULL=use tenant default) (`:166`) |
| `notes` | textarea | `notes` (`:167`) |
| `linked_user_id` | select | FK to User (linking contact to a tenant user account). |
| `default_agent_id` | select | Persisted as `ContactAgentMapping` row (see `:167-182`). |

Unique constraint: `(friendly_name, tenant_id)` (`models.py:180`).

### 16.2 ContactChannelMapping

Universal mapping table for multi-channel identifiers (Source: `models.py:184-219`).

| Field | Purpose |
|---|---|
| `contact_id` | FK Contact. |
| `channel_type` | `whatsapp`, `telegram`, `phone`, `discord`, `email`, … |
| `channel_identifier` | The primary channel ID (phone, user_id, email…). |
| `channel_metadata` (JSON) | e.g. `{username: "@johndoe", display_name: "John Doe"}`. |
| `tenant_id` | Tenant isolation. |

Uniqueness: `(channel_type, channel_identifier, tenant_id)` (`:213-214`). One contact can hold multiple mappings across channels.

Service: `backend/services/contact_channel_mapping_service.py`. Auto-population (e.g., WhatsApp ID discovery): `backend/services/contact_auto_populate_service.py`, `backend/services/whatsapp_id_discovery.py`. Contact resolution for group senders: `backend/services/group_sender_resolver.py`.

### 16.3 Slash Command Access Control

Two-level policy (tenant default + per-contact override):
- **Tenant default** — set in `Config` table (tenant-level); used when contact override is NULL.
- **Per-contact override** — `Contact.slash_commands_enabled` (NULL/True/False) (Source: `models.py:166`).

Enforcement logic: `backend/services/slash_command_permission_service.py` (referenced under `backend/services/`). Available slash commands are defined in `backend/services/slash_command_service.py` and related `*_command_service.py` modules.

### 16.4 Usage Examples

**Create a contact with multi-channel mapping:**

```bash
# Create the contact
curl -X POST http://localhost:8081/api/contacts \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{
    "friendly_name": "John Doe",
    "role": "user",
    "is_dm_trigger": true,
    "slash_commands_enabled": true,
    "notes": "VIP customer, priority support"
  }'

# Add WhatsApp channel mapping
curl -X POST http://localhost:8081/api/contacts/<contact_id>/channel-mappings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"channel_type": "whatsapp", "channel_identifier": "+5511999990001"}'

# Add Telegram channel mapping
curl -X POST http://localhost:8081/api/contacts/<contact_id>/channel-mappings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"channel_type": "telegram", "channel_identifier": "123456789"}'
```

**Link a contact to a system user account:**

```bash
curl -X PATCH http://localhost:8081/api/contacts/<contact_id> \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"linked_user_id": 5}'
```

When a contact is linked to a system user, messages from that contact inherit the user's RBAC permissions and audit trail.

**Assign a default agent per contact:**

```bash
curl -X POST http://localhost:8081/api/contacts/<contact_id>/agent-mapping \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"agent_id": 3}'
```

This ensures messages from this contact are always routed to the specified agent, overriding the tenant's default agent.

---

## 17. Projects (Studio)

Projects are tenant-wide isolated workspaces with dedicated KBs, memory, and tool configurations. Since Phase 15 they are no longer user-scoped.

DB: `backend/models.py:1024-1082`. UI: `frontend/app/agents/projects/page.tsx`, detail at `frontend/app/agents/projects/[id]/page.tsx`. API: `backend/api/routes_projects.py`.

### 17.1 Project Form

Source: `frontend/app/agents/projects/page.tsx:92-108`.

| Field | Type | Default | Source |
|---|---|---|---|
| `name` | text, required | — | `models.py:1042` |
| `description` | text | — | `models.py:1043` |
| `icon` | select | `"folder"` | 12 icon options at `:44-57` |
| `color` | select | `"blue"` | 7 color options at `:33-41` |
| `agent_id` | select | NULL | Default agent for project — `models.py:1046` |
| `system_prompt_override` | text | NULL | Custom instructions — `models.py:1049` |

### 17.2 Knowledge Base Config (per project)

Source: `backend/models.py:1062-1065`, UI at `page.tsx:99-101, 65-77`.

| Field | Default | Options |
|---|---|---|
| `kb_chunk_size` | 500 (chars) | integer |
| `kb_chunk_overlap` | 50 (chars) | integer |
| `kb_embedding_model` | `"all-MiniLM-L6-v2"` | `all-MiniLM-L6-v2`, `all-mpnet-base-v2`, `paraphrase-multilingual-MiniLM-L12-v2`, `text-embedding-3-small`, `text-embedding-3-large`, `text-embedding-ada-002`, `text-embedding-004`, `embedding-001` |

Embedding model list: `frontend/app/agents/projects/page.tsx:65-77`.

### 17.3 Memory Config (per project)

Source: `backend/models.py:1067-1072`.

| Field | Default |
|---|---|
| `enable_semantic_memory` | True |
| `semantic_memory_results` | 10 |
| `semantic_similarity_threshold` | 0.5 |
| `enable_factual_memory` | True |
| `factual_extraction_threshold` | 5 (messages before fact extraction) |

### 17.4 Enabled Tools

- `enabled_tools` (JSON) — built-in tool IDs (`models.py:1050`).
- `enabled_sandboxed_tools` (JSON, alias `enabled_custom_tools`) — sandboxed tool IDs (`models.py:1051-1060`).
- `is_archived` — archive flag (`models.py:1075`).

Project command patterns are exposed via `backend/services/project_command_service.py`.

Per-project documents live in `project_knowledge` (`models.py:1085-1103`) with fields: `document_name`, `document_type`, `file_path`, `file_size_bytes`, `num_chunks`, `status` (`pending|processing|completed|failed`), `error_message`, `upload_date`, `processed_date`. Memory: `backend/services/project_memory_service.py`.

---

## 18. Playground

Web-based chat UI for testing/interacting with agents. UI: `frontend/app/playground/page.tsx`. Backend: `backend/api/routes_playground.py`, services under `backend/services/playground_*.py`.

### 18.1 Thread Management

Threads managed by `backend/services/playground_thread_service.py`. Each thread holds a message history and belongs to a tenant/user. Auto-rename is supported and emitted over WebSocket (`frontend/app/playground/page.tsx:142, :178`).

The Playground history and memory endpoints accept an optional `thread_id` so reads use the same identity contract as writes:
- `isolated` → per-thread memory
- `channel_isolated` → shared memory across Playground threads in the same channel, but thread-scoped history display
- `shared` → per-agent global memory across Playground threads

### 18.2 Audio Recording & Whisper Transcription

The page uses `MediaRecorder` to capture voice directly in the browser (`page.tsx:498-518`):
- Preferred MIME types (in order): `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, `audio/mp4` (`:502-510`).
- Audio capabilities are loaded per selected agent (`:484-490`) — determined by the agent's configured `audio_transcript` skill.

Transcription is performed by the `audio_transcript` skill (Source: `backend/agent/skills/audio_transcript.py`) using one of three routes: explicit OpenAI Whisper, the tenant default ASR instance, or a specific pinned local Speaches/Whisper instance. When the selected local path is unavailable, the skill falls back to OpenAI Whisper. Skill is `execution_mode="special"` (media-triggered).

### 18.3 Document Uploads

Supported extensions (Source: `backend/services/playground_document_service.py:32-38`):
- `.pdf` → pdf
- `.txt` → txt
- `.csv` → csv
- `.json` → json
- `.xlsx` / `.xls` → xlsx
- `.docx` / `.doc` → docx
- `.md` / `.markdown` → md
- `.rtf` → rtf

The Playground "Attach documents" flow is document-only. Images and other unsupported file types are rejected by both the frontend chooser and the backend validation layer with an explicit supported-types error message. Maximum file size is 10 MB per document.

Handling lives in `playground_document_service.py` and `playground_message_service.py`.

### 18.4 UI Features

- **Expert mode** — advanced controls visible on the page.
- **Command palette** — quick slash-command entry.
- **Knowledge panel** — surfaces relevant KB chunks used to answer.
- **Memory inspector** — inspect which memory layer entries were pulled (backed by `MemoryManagementService`).

(These UI panels are toggled within `frontend/app/playground/page.tsx`; exact field names not enumerated here — recommend confirmation by opening the file in UI if precise toggle names are needed.)

### 18.5 Token Streaming (WebSocket)

Source: `frontend/app/playground/page.tsx:98-232`, `backend/services/playground_websocket_service.py`.

- Client hook: `usePlaygroundWebSocket` (`:21`, `:131-232`).
- Cookie-based auth (no localStorage token) — "SEC-005" note.
- Events: `onQueueProcessingStarted`, `onQueueMessageCompleted`, thread-auto-rename, token streaming.
- Feature-flagged via `useWebSocket` state (default true, `:99`).

Backend WebSocket handler: `backend/services/playground_websocket_service.py`. Fallback to HTTP polling when WS disabled.

### 18.6 Playground Mini (floating quick-test bubble)

A compact companion to the full Playground, mounted globally in `frontend/app/layout.tsx` so it appears on **every authenticated page** (Watcher, Studio, Hub, Flows, Core, Settings, System). Intended for the "I just want to fire one prompt to check this agent without leaving this page" case that comes up constantly while exploring the Watcher Graph view, editing a Flow, or comparing dashboards.

**Surface and placement.** Implemented under `frontend/components/playground/mini/`: `PlaygroundMini.tsx` (top-level FAB + panel wrapper), `PlaygroundMiniPanel.tsx` (the visible card), `MiniHeader.tsx`, `MiniMessageList.tsx`, `MiniStreamingMessage.tsx`, `MiniComposer.tsx`, and the `usePlaygroundMini.ts` data hook. The FAB is a 56×56 circle pinned to `bottom-6 right-6 z-[70]` with `data-testid="playground-mini"`. The panel opens to 380×560 on desktop (mobile: `inset-x-4 bottom-4 top-16`) with the `animate-scale-in` keyframe. `role="dialog"` `aria-modal="false"` — the page stays interactive behind it. Route-gated: hidden on `/playground`, `/auth/*`, `/setup`.

**Controls.**
- Agent dropdown — populated from `GET /api/playground/agents`. Switching clears the active thread and re-scopes the thread list.
- Project dropdown — `(No project)` plus all non-archived projects from `GET /api/projects`. Selecting a project uses its name as the `folder` filter on `GET /api/playground/threads` and as the `folder` value when creating a new thread, matching the full Playground's `/enter <project>` convention.
- Thread selector — lists threads for the current agent+project. Switching fetches messages via `GET /api/playground/threads/:id`.
- "+" new-thread button — calls `POST /api/playground/threads` synchronously so the new thread has an id before the first send; focus moves to the composer.
- Expand — builds `/playground?agent=<id>&thread=<id>&project=<id>`, navigates via `router.push`, and closes the panel. See handover below.
- Close — closes the panel; focus returns to the FAB.

**Composer.** Auto-grow textarea capped at 4 visible rows. `Enter = send`, `Shift+Enter = newline`, `Ctrl/Cmd+Enter = send`, `Alt+Enter` ignored. Disabled while a send is in flight.

**Markdown.** Assistant messages are rendered through `react-markdown` + `remark-gfm` with a `.mini-markdown` stylesheet in `frontend/app/globals.css` (compact p / h1–h4 / strong / em / a / ul / ol / blockquote / code / pre / table / hr styles tuned for the tight bubble). Links open in a new tab with `rel="noopener noreferrer"`. User messages render as plain text to preserve user-typed formatting. Empty assistant content shows `…`.

**Send path.** `POST /api/playground/chat?sync=true` — the Mini intentionally does **not** open a second WebSocket connection (the full Playground already manages the `/ws/playground` stream; running two WS consumers from the same tab would race `thread_created` / `done` events). A pending indicator (three pulsing dots in `MiniStreamingMessage`) shows while the HTTP call is in flight. On success, the assistant reply is appended. On failure, the optimistic user bubble is rolled back and an error surfaces inside the bubble.

**Expand handover.** The critical promise of the Mini is that the conversation carries over to the full Playground intact. The handover is consumed inside `frontend/app/playground/page.tsx`:
- `selectedAgentId` is seeded from `window.location.search` via a **lazy `useState` initializer** — this runs at mount, before `loadAgents()` can default-pick an agent, so `?agent=<id>` wins the race.
- `initializeThreads` (the effect that fires when `selectedAgentId` changes) reads `window.location.search` directly (not via `useSearchParams`) and looks up `?thread=<id>` in the freshly fetched agent's thread list. On hit, it selects the thread, triggers `handleThreadSelect` to pull the messages, and strips the URL with `window.history.replaceState(null, '', '/playground')` (not `router.replace`, which would remount the page and wipe the consumption state).
- A module-local `lastConsumedHandoverThreadRef` de-dupes repeat consumption within one session so `initializeThreads` firing twice for the same agent doesn't re-select. Expanding again with a different thread still works.
- If the URL's `?agent=<id>` is not in the tenant's agent list (stale copy-paste, deleted agent, cross-tenant URL leak), `loadAgents` falls back to the tenant's default agent to prevent foreign-agent writes.

**Persistence.** Selection state (`isOpen`, `selectedAgentId`, `selectedProjectId`, `activeThreadId`) is persisted to `sessionStorage` keyed by `tsushin:playground-mini:v1:<userId>` (`frontend/lib/playgroundMiniSessionStore.ts`). Messages are **not** persisted — they re-fetch from `api.getThread(activeThreadId)` on panel open, which re-validates tenant ownership on every call. `AuthContext.logout()` clears the per-user key (and `clearAll()` on missing userId) so a second user on the same tab starts fresh. `hasLoadedOnceRef` inside the hook is also reset when the active user changes.

**Multi-tenant safety.** No new backend endpoints, no new auth paths. All data operations go through the same tenant-scoped `/api/playground/*` and `/api/projects` routes the full Playground uses. `X-Tenant-Id` enforcement on the backend and the httpOnly session cookie are the authoritative guards; the Mini is a pure UI wrapper on top of them.

**Keyboard shortcuts.**
- `Ctrl/Cmd + Shift + L` — toggle panel. Ignored when any `[role="dialog"][aria-modal="true"]` is visible so Modal/Setup/WhatsApp-wizard dialogs don't compete for the keybind.
- `Escape` — close the panel when focus is inside it; restores focus to the FAB.

**Onboarding tour integration.** `frontend/contexts/OnboardingContext.tsx` bumped `TOTAL_STEPS` from 12 to 13. `frontend/components/OnboardingWizard.tsx` added a new step ("New: Playground Mini") targeting `[data-testid="playground-mini"]`. When the step becomes active, the wizard applies both the generic `.tour-highlight` outline and the new `.playground-mini-tour-glow` keyframe — a 1.4s × 3-iterations box-shadow pulse using `tsushin-accent` + `tsushin-indigo` designed to be strong enough to grab attention without being jarring. The step's "Open Playground Mini" action button dispatches `tsushin:playground-mini:open`, which the FAB listens for, opens the panel, and re-triggers the glow. A MutationObserver on the FAB watches for `.tour-highlight` so the glow also fires if the user relaunches the tour from the header `?` button. If the user is on an excluded route (`/playground`, `/auth/*`, `/setup`) when they click the step's action, the wizard first navigates home via `router.push('/')` before dispatching the event.

**Files of record:**
- `frontend/components/playground/mini/` (all 7 files under this folder)
- `frontend/lib/playgroundMiniSessionStore.ts`
- `frontend/app/layout.tsx` (mount)
- `frontend/app/playground/page.tsx` (handover)
- `frontend/components/OnboardingWizard.tsx` (tour step)
- `frontend/contexts/OnboardingContext.tsx` (`TOTAL_STEPS = 13`)
- `frontend/app/globals.css` (`.playground-mini-tour-glow`, `.mini-markdown`)
- `frontend/contexts/AuthContext.tsx` (`logout()` clears sessionStorage)

### 18.6.1 Live Regression Harness

For live-stack regression and diagnosis, use `backend/dev_tests/run_playground_regression_live.py`.

**Purpose.** This runner validates the existing Playground / Playground Mini / Watcher Graph contracts on the currently running local HTTPS stack without introducing any new test-only product endpoints. It is intended for "the stack is already up, tell me whether full Playground, Mini, watcher activity, KB glow, provider glow, and A2A still work right now" passes.

**Entry assumptions.**
- Run from the repo root: `/Users/vinicios/code/tsushin`.
- Target base URL: `https://localhost`.
- Owner fixture: `test@example.com / test1234`.
- Fixture KB document: `sample_data/acme_sales.csv`.

**Covered interfaces.**
- Auth/session: `/api/auth/login`, `/api/auth/me`
- Playground: `/api/playground/agents`, `/api/playground/threads`, `/api/playground/threads/{id}`, `/api/playground/chat?sync=true`
- Projects: `/api/projects`
- Graph/Watcher discovery: `/api/v2/agents/graph-preview`, `/api/v2/agents/{id}/expand-data`, `/api/v2/agents/comm-enabled`
- Knowledge base: `/api/agents/{id}/knowledge-base/*`
- Watcher activity socket: `/ws/watcher/activity`

**Behavior.**
- Uses cookie auth for HTTPS requests and first-message token auth for `wss://localhost/ws/watcher/activity`.
- Discovers the live primary/provider/A2A-capable agents from current API state instead of assuming hard-coded ids, while still preferring the common `Tsushin (1) -> Gemini1 (17)` mapping when present.
- Uploads `sample_data/acme_sales.csv` to the chosen provider-backed agent KB, polls until `status=completed` and `num_chunks > 0`, then runs:
  - baseline thread create -> read -> sync chat -> post-read -> explicit rename -> filtered thread list
  - provider-backed `web_search`
  - KB-backed answer using the uploaded CSV
  - `agent_communication` from the primary agent to the provider-backed target
- Captures watcher event families around each chat so the report can tie browser graph glow, watcher activity, and backend logs together with explicit correlation tokens.

**Artifacts.**
- API JSON report: `output/playwright/playground-regression-api-<timestamp>.json`
- Intended paired browser artifact folder: `output/playwright/playground-regression-<timestamp>/`

**Useful flags.**
- Default mode cleans up the runner-created KB document and threads.
- `--skip-cleanup` leaves the artifacts in place so a browser/Graph pass can verify the same KB node and recent regression threads before teardown.

### 18.7 Async Queuing & Dead-Letter Retry

Service layer: `backend/services/message_queue_service.py`, `backend/services/queue_worker.py`.

- Messages submitted via the async path receive a `queue_id`.
- Placeholder messages render in UI with `message_id = "queue_{id}"` (`page.tsx:193, 205, 232`).
- On completion, `onQueueMessageCompleted` replaces the placeholder with the real response and triggers a thread refresh.
- Dead-letter retry is handled server-side by the queue worker on failed jobs.

## 19. LLM Providers

**Sources:**
- `backend/services/provider_instance_service.py` — CRUD/encryption/SSRF
- `backend/api/routes_provider_instances.py` — REST endpoints
- `backend/services/model_discovery_service.py` — model auto-fetch
- `backend/api/routes_model_pricing.py` — pricing endpoints
- `frontend/app/settings/model-pricing/page.tsx` — pricing UI

### 19.1 Provider Instance Model

Each tenant may configure **multiple provider instances** (e.g., two OpenAI accounts, a self-hosted Ollama + a hosted Groq). Each instance holds:

| Field | Purpose | Source |
|---|---|---|
| `vendor` | Provider key (see matrix below) | `provider_instance_service.py:20-32` |
| `instance_name` | Display name (unique per tenant+vendor) | `create_instance` args |
| `base_url` | Override vendor default; SSRF-validated before save | `provider_instance_service.py:110-118` |
| `api_key` | Fernet-encrypted via `TokenEncryption` + per-tenant derivation | `create_instance` (encrypt path) |
| `available_models` | JSON list of model IDs exposed for use | `create_instance` args |
| `is_default` | Only one default per (tenant, vendor) enforced | `create_instance` |
| `is_active` | Soft disable | list filters |

Encryption uses the same pattern as `api_key_service.py` — `TokenEncryption` keyed by the master encryption key from `services/encryption_key_service.py`.

During first-run setup, the `/setup` wizard can create multiple provider instances in one pass. Every supported provider key entered in the wizard is provisioned as its own tenant-scoped instance, and the selected primary provider is also written to the system-AI configuration.

Hub provider setup uses a guided multi-step **Add Provider** wizard (see §19.8). The wizard branches on modality (LLM / TTS / Image) and hosting (Cloud / Self-hosted) to show only the relevant vendors, collects credentials or container settings, runs a live connection test, and creates the instance via the same backend endpoints the legacy form used. The previous provider-instance form remains available as a one-click fallback via the wizard footer's **Switch to Advanced** button (`ProviderInstanceModal`).

### 19.2 Provider Matrix

From `backend/services/provider_instance_service.py:20-32`:

| Vendor key | Default `base_url` | Notes |
|---|---|---|
| `openai` | None (SDK default) | Standard OpenAI API |
| `anthropic` | None (SDK default) | Anthropic Claude API |
| `gemini` | None (SDK default) | Google Generative AI |
| `groq` | `https://api.groq.com/openai/v1` | OpenAI-compatible |
| `grok` | `https://api.x.ai/v1` | xAI, OpenAI-compatible |
| `deepseek` | `https://api.deepseek.com/v1` | OpenAI-compatible |
| `openrouter` | `https://openrouter.ai/api/v1` | Router / multi-vendor |
| `ollama` | `http://host.docker.internal:11434` | Local LLM server; `validate_ollama_url` SSRF guard |
| `vertex_ai` | None | Region-resolved from credentials |
| `custom` | Free-form (SSRF-validated) | Any OpenAI-compatible endpoint |

An Ollama default is auto-provisioned per tenant on demand via `ensure_ollama_instance()` (`provider_instance_service.py:37-65`), seeded from `Config.ollama_base_url` or the default. In Docker-on-Linux VM setups, `host.docker.internal` is the preferred endpoint; if that hostname is unavailable on the target host, point the provider instance at the Docker bridge gateway IP instead and retest from the Hub UI.

### 19.3 Dynamic Provider & Model Dropdowns

All agent creation and configuration UIs — the `/agents` Create Agent modal, the Studio `+` button (`StudioAgentSelector`), `AgentConfigurationManager`, and the Playground config panel — fetch the provider list **at runtime** from `GET /api/provider-instances`. The dropdown shows only vendors that have at least one active instance configured in Hub > AI Providers. Models shown for each vendor come from that instance's `available_models` list (set during hub configuration or model discovery).

This means: adding a new provider in Hub automatically makes it available everywhere without any code change. The shared `VENDOR_LABELS` map (`frontend/lib/client.ts`) provides human-readable vendor names.

The Hub AI Providers tab follows the same runtime shape: vendor sections render only when at least one active instance exists. Empty static provider panels, unused local-service panels, and unconfigured fallback-key cards are hidden until the user adds the corresponding provider through the guided setup flow.

**Vendor catalog endpoint (`GET /api/providers/vendors`)** — returns every vendor from backend `VALID_VENDORS` + `VENDOR_DISPLAY_NAMES` with `{id, display_name, default_base_url, supports_discovery, tenant_has_configured}`. The **Add Provider Instance** modal (`ProviderInstanceModal.tsx`) fetches this list on open and falls back to a reduced static array only when the call fails, so a vendor added to `VALID_VENDORS` backend-side surfaces in the dropdown without any frontend edit. `tenant_has_configured` is resolved in one DB round-trip (distinct `ProviderInstance.vendor` rows for the tenant). `backend/tests/test_wizard_drift.py` Guard 6 keeps the fallback consistent with the backend set.

### 19.4 Model Discovery

`backend/services/model_discovery_service.py` auto-fetches the vendor's `/models` endpoint (for OpenAI-compatible providers) and populates `available_models`. Used by the frontend Provider form to let the user pick which models to expose.

**Auto health-test on save (2026-04-19).** `POST /api/provider-instances` and `PUT /api/provider-instances/{id}` schedule a connection test in a FastAPI `BackgroundTasks` after the response returns, so the Hub UI dot reflects real connectivity instead of staying gray (`unknown`) until the user clicks **Test Connection**. Same code path as the manual test (model picked from `available_models[0]` → `PROVIDER_TEST_MODELS` fallback; `AIClient.generate` with `max_tokens=20` and SDK retries disabled). Result is written to `health_status` (`healthy` / `unavailable`), `health_status_reason`, `last_health_check`, plus a `ProviderConnectionAudit` row with `action="auto_test_on_save"`. Triggers only when (a) credentials are present (or vendor is `ollama`) **and** `available_models` is non-empty; updates require a connectivity-relevant change (`api_key`, `base_url`, `extra_config`, `available_models`) — pure renames or default-toggles do not re-test. Clearing the API key (`api_key=""`) resets `health_status` back to `unknown` so the dot doesn't keep showing a stale green from the previous valid key. (`backend/api/routes_provider_instances.py` — `_background_test_instance`).

### 19.5 Model Pricing

**Source:** `frontend/app/settings/model-pricing/page.tsx`, `backend/api/routes_model_pricing.py`

Pricing rates per 1M tokens used for cost estimation in the Playground debug panel. Defaults are based on official provider pricing; tenant-set custom rates override defaults.

UI table columns (`model-pricing/page.tsx:326-347`):
- Model (with provider badge, display name, raw model name)
- Input cost per 1M tokens (numeric input, step=0.001)
- Output cost per 1M tokens (numeric input, step=0.001)
- Status
- Actions (Edit / Save)

Filters: "All" or a provider badge filter (`page.tsx:292-323`). Tenants without `org.settings.write` see read-only mode (gate at top of file).

### 19.6 Anthropic Prompt Caching — v0.6.0

v0.6.0 enables Anthropic's **prompt caching** across all Claude requests. Caching reuses Anthropic-side computation of stable prompt prefixes (system prompt, persona, skill instructions, knowledge snippets) across subsequent requests, so the LLM only re-processes the dynamic tail of the conversation. Tenants with chat-heavy workloads see a **40–65% reduction in input token cost** with no behavioral change.

**How it works (3 breakpoints + relocation trick):**

Anthropic supports up to four `cache_control` breakpoints per request. Tsushin uses three, strategically placed to maximize hit rate:

| # | Position | Cached content | Rationale |
|---|---|---|---|
| 1 | End of system prompt | Persona, tone preset, agent rules, skill catalog | Stable across every turn of the same agent |
| 2 | End of tool definitions block | MCP schemas, sandboxed tool defs, custom skill descriptors | Changes only when skills are added/removed |
| 3 | Just before the current user turn | Conversation history + any retrieved-knowledge context | The "relocation trick" — cache point moves forward as the conversation grows, so each prior turn gets cached on its way past breakpoint 3 |

**Default Anthropic model:** `claude-haiku-4-5` (v0.6.0 bump). The default is set in `backend/services/provider_instance_service.py` and surfaces in the agent Create modal under Hub → AI Providers → Anthropic → Default Model. Override per-agent in the agent config UI.

**Sources:**
- `backend/providers/anthropic_provider.py` — breakpoint placement and `cache_control` injection
- `backend/services/token_tracker.py` — cache-hit accounting in the Watcher billing dashboard

**Requirements & caveats:**
- Requires Anthropic API access with prompt caching enabled (on by default for all Anthropic accounts in 2025+).
- Cache hits appear in the Playground debug panel and in `/api/usage` token summaries under `cache_read_input_tokens` / `cache_creation_input_tokens`.
- Cache TTL is Anthropic-managed (5 minutes idle, or evicted under load). Tsushin does not persist anything client-side.
- No configuration is required — it's always on for Anthropic requests. To disable for a specific agent (rare — e.g., if you want to rehearse a cold token count), set `provider_config.cache_enabled = false` in the agent config JSON.

### 19.7 Gemini 3.x preview models — v0.6.0 (added 2026-04-20)

Google's Gemini 3.x preview line is first-class across every picker and pricing surface. Added late into v0.6.0 before the public announcement.

| Model ID | Tier | Input / Output context | Notable capabilities |
|---|---|---|---|
| `gemini-3-flash-preview` | Flash (flagship agentic) | 1,048,576 / 65,536 | **First Flash-tier with native `computer_use` tool support.** Thinking/reasoning, code execution, Search + Maps grounding. No Live API. |
| `gemini-3.1-flash-lite-preview` | Flash-Lite (cheapest 3.x) | 1,048,576 / 65,536 | Thinking/reasoning, Search + Maps grounding. No `computer_use`, no Live API. |
| `gemini-3.1-flash-tts-preview` | TTS (preview, default) | 8,192 / 16,384 | Default Gemini TTS — Balanced tier. See §20.6. |
| `gemini-2.5-flash-tts-preview` | TTS (preview) | 8,192 / 16,384 | Fast tier. See §20.6. |
| `gemini-2.5-pro-tts-preview` | TTS (preview) | 8,192 / 16,384 | Quality tier. See §20.6. |
| `gemini-2.5-flash-image` | Image generation (default) | — | "Nano Banana (Fast)". Default in `ImageSkill.SUPPORTED_MODELS`. |
| `gemini-3.1-flash-image-preview` | Image generation | — | Available in `ImageSkill.SUPPORTED_MODELS` (`backend/agent/skills/image_skill.py`). |
| `gemini-3-pro-image-preview` | Image generation (premium) | — | "Nano Banana Pro" — quality tier. |

**Backend auto-lift of output tokens.** `backend/agent/ai_client.py` `_call_gemini` raises the default `generation_config.max_output_tokens` to **65,536** when the model name starts with `gemini-3-` or `gemini-3.1-` (the 2.x default of 8,192 truncates long 3.x outputs). The lift applies only when the caller hasn't explicitly set a lower value.

**Pricing placeholders.** Google has not yet published official pricing for the 3.x preview line. `backend/analytics/token_tracker.py` seeds rows based on the 2.5 Flash / 2.5 Flash-Lite analogues (`0.30/2.50` and `0.10/0.40` per 1M tokens respectively) and marks each with a `TODO confirm` comment. TTS pricing is stubbed `$0.00` until Google publishes.

**Wizards covered.** Setup Wizard, Playground ConfigPanel, Agent Wizard → Step Audio, and Audio Agents Wizard all include the 3.x models. The Agent Wizard → Step Basics picker is API-fed from `ProviderInstance.available_models`, so 3.x preview models appear there automatically once model discovery hits Google's `/models` endpoint.

### 19.8 ProviderWizard — guided multi-step setup (v0.7.x)

**Sources:**
- `frontend/components/provider-wizard/ProviderWizard.tsx` — Modal shell, step pills, Back/Next/Advanced/Cancel footer.
- `frontend/components/provider-wizard/steps/*` — one component per step.
- `frontend/contexts/ProviderWizardContext.tsx` — global provider mounted in `app/layout.tsx`. Exposes `openWizard(preset?)`, `closeWizard`, `patchDraft`, `registerOnComplete`.
- `frontend/lib/provider-wizard/reducer.ts` — pure reducer + step-order branching.

The guided wizard replaces the flat `ProviderSetupWizard` category picker (deleted) with a step-based flow that mirrors the Agent, WhatsApp, Gmail, and Audio wizards. Entry points in `app/hub/page.tsx`:

- **`+ New Instance`** (tab header) → opens wizard at Step 1 (modality).
- **Per-vendor `+ Add Instance`** (inside each vendor group) → opens wizard prefilled with that vendor so the user lands on the credentials/container step directly. Modality and hosting are inferred from the vendor.
- **Empty-state `Add Provider`** → Step 1.

**Step order (branching).** Computed in `reducer.getStepOrder(draft)`:

| Step | When rendered | Component |
|---|---|---|
| Modality | Always | `StepModality` — LLM / TTS / Image |
| Hosting | Skipped when `modality='image'` (auto-cloud today) | `StepHosting` — Cloud / Self-hosted |
| Vendor | Always | `StepVendorSelect` — filtered by `(modality, hosting)` |
| Credentials | `hosting='cloud'` | `StepCredentials` — api_key, base_url, Vertex AI fields |
| Container | `hosting='local'` | `StepContainerProvision` — instance_name, mem_limit, GPU |
| Pull models | `vendor='ollama' && hosting='local'` | `StepOllamaPullModels` — curated starter models, skippable |
| Test & models | Always | `StepTestAndModels` — Test Connection, Auto-detect models, default toggle |
| Review | Always | `StepReview` — summary with jump-to-edit rows |
| Progress | Always (terminal) | `StepProgress` — fires the actual create call |

**Vendor catalog per branch:**

| Modality | Hosting | Vendors |
|---|---|---|
| LLM | Cloud | openai, anthropic, gemini, vertex_ai, groq, grok, deepseek, openrouter, custom |
| LLM | Local | ollama |
| TTS | Cloud | elevenlabs |
| TTS | Local | kokoro |
| Image | Cloud | gemini (pre-tagged "Uses Nano Banana / Nano Banana Pro") |

**Backend endpoints used (no new endpoints introduced):**

- `POST /api/provider-instances` — LLM cloud, LLM local (Ollama), Image (Gemini).
- `POST /api/tts-instances` — TTS Kokoro (auto-provisions its own container).
- `POST /api/api-keys` — TTS ElevenLabs (legacy api_keys surface).
- `POST /api/settings/ollama/provision` — Ollama container lifecycle after `ProviderInstance` create.
- `api.pullOllamaModel(id, model)` — each selected starter model.
- `api.testProviderConnectionRaw({...})` — unsaved connection test on Step 5.
- `api.discoverModelsRaw(vendor, apiKey, baseUrl)` — live model discovery on Step 5.

**Advanced mode.** The wizard footer's **Switch to Advanced** button:

1. Persists the current non-secret draft to `localStorage['tsushin:providerWizardDraft']`.
2. Closes the wizard.
3. Dispatches a `tsushin:open-provider-advanced-modal` `CustomEvent` with `detail.vendor`.
4. `hub/page.tsx` listens for that event and opens the existing `ProviderInstanceModal` with the current vendor pre-selected.

Mode preference persists to `localStorage['tsushin:providerWizardMode']` (`'guided' | 'advanced'`).

**Security invariants.** Secrets (`api_key`, Vertex AI `private_key`) are stripped from the persisted draft before writing to localStorage — only non-sensitive fields survive a page refresh or a mode switch. The wizard never echoes a saved key back into the DOM.

### 19.9 ManagedContainerPanel — unified local-service controls (v0.7.x)

**Source:** `frontend/components/hub/ManagedContainerPanel.tsx`.

All three auto-provisioned services (Ollama, Kokoro, SearXNG) render through the same `<ManagedContainerPanel />` component, giving tenants one consistent control strip instead of per-service variations.

| Control | Behavior |
|---|---|
| **Enable/Disable toggle** | Single source of truth for start/stop. Hooked to the service-specific lifecycle endpoint (`/container/start\|stop`). |
| **Restart** | Visible when container is `running` or `stopped` and an `onRestart` handler is passed. |
| **Logs** | Visible when `running`. Toggles between "Logs" and "Hide Logs" based on `logsOpen` prop. |
| **Test** | Optional — only rendered when `onTest` is passed. |
| **Delete** | Optional — destructive; confirms in the host before calling the handler. |

Props are documented in the component itself. Call sites in `hub/page.tsx`:

- Ollama (auto-provisioned, per-instance) — start↔stop / restart / logs / test / delete.
- Ollama (host mode, per-instance) — inline `Test` / `Refresh Models` / `Delete` strip (no container lifecycle — the URL points at an external daemon).
- Kokoro instance row — start↔stop / restart / logs / delete.
- SearXNG instance row — start↔stop / restart / logs / delete.

The legacy Ollama panel-level **Enable Ollama** `ToggleSwitch` at the card header was removed in favor of the per-instance panel; this eliminates the drift where Ollama had two lifecycle toggles (panel + instance) while Kokoro and SearXNG only had one.

**v0.7.x follow-up — full Ollama/Kokoro parity.** The Ollama panel also no longer renders when the tenant has no `ollama` provider instance, matching Kokoro (`kokoroInstances.length > 0`) and SearXNG (`searxngInstances.length > 0`). Mode (host vs. auto-provision) is derived from `instance.is_auto_provisioned` rather than a live radio on the card — it's a creation-time choice made in the wizard. The separate **Deprovision** / **Test Connection** / **Refresh Models** / **Manage Instance** buttons that used to live at the bottom of the Ollama card were removed; `ManagedContainerPanel.onTest` + `onDelete` + the inline host-mode action strip cover those affordances. A new `ollamaConfirmDelete` modal (mirroring the Kokoro modal) handles the Delete action, including the optional "remove container volume" checkbox for pulled-model cleanup.

### 19.10 Service API Keys disclosure (v0.7.x)

The **Hub → AI Providers** tab no longer renders the legacy Service API Keys block as an always-visible grid. Instead it's a collapsed `<details>` disclosure that:

- Only renders when `visibleAiFallbackProviders.length > 0` (i.e., at least one vendor has a fallback api_key configured).
- Filters out any vendor that already has a `ProviderInstance` row (`vendorsWithInstances` set at `hub/page.tsx`). This removes the duplicate-Gemini display by construction: a vendor with an instance is configured via the instance grid; a vendor with only a legacy `api_keys` row falls into this disclosure.
- Stays collapsed by default so the Hub is clean for tenants who only use instances.

The inline "Fallback — instance key takes priority" amber label has been removed — with the new filtering, the fallback card and the instance card can never appear on the same page simultaneously.

---

## 20. Hub Integrations

**Sources:** `backend/hub/`, `backend/hub/providers/`, `backend/hub/oauth_token_refresh_worker.py`, `frontend/app/hub/page.tsx`.

### 20.1 Google (Calendar, Gmail)

**Sources:** `backend/hub/google/oauth_handler.py`, `backend/hub/google/calendar_service.py`, `backend/hub/google/gmail_service.py`

- OAuth2 installed-app flow (redirect URI pattern documented in `oauth_handler.py`).
- Models: `GmailIntegration` (`models.py:3021`), `CalendarIntegration` (`models.py:3061`) — both subclass `HubIntegration`.
- Tokens encrypted with the Google encryption key (`encryption_key_service.get_google_encryption_key`).
- Google SSO credentials (`client_id`, `client_secret`) are stored under `Settings → Security & SSO` (see §21.5) and reused for both Gmail/Calendar integrations and user sign-in.

### 20.2 Asana (OAuth + MCP)

**Sources:** `backend/hub/asana/asana_service.py`, `backend/hub/asana/asana_mcp_client.py`, `backend/hub/asana/oauth_handler.py`

- OAuth2 code flow → `AsanaIntegration` (`models.py:1851`).
- MCP client (`asana_mcp_client.py`) speaks MCP protocol to Asana's hosted MCP server to list projects, tasks, and members.
- Tokens encrypted with the Hub encryption key.

### 20.3 Amadeus (flight search)

**Source:** `backend/hub/amadeus/amadeus_service.py`, `backend/hub/providers/amadeus_provider.py`
Model: `AmadeusIntegration` (`models.py:1881`). Holds Amadeus API key+secret (encrypted) and talks to the Amadeus test/production API for flight offers.

### 20.4 Brave Search / SerpAPI / SearXNG / Tavily / Google Flights

**Sources:** `backend/hub/providers/brave_search_provider.py`, `backend/hub/providers/serpapi_search_provider.py`, `backend/hub/providers/searxng_search_provider.py`, `backend/hub/providers/tavily_search_provider.py`, `backend/hub/providers/google_flights_provider.py`, `backend/hub/providers/search_registry.py`, `backend/hub/providers/flight_search_provider.py`

- **Brave Search**: API key based web search provider (primary supported search provider in v0.6.0).
- **SerpAPI**: used for both generic web search and Google Flights (Google Flights falls back to env var `SERPAPI_KEY` or `GOOGLE_FLIGHTS_API_KEY` — `google_flights_provider.py:71-74`).
- **SearXNG (self-hosted, auto-provisioned)** — since v0.6.0-patch.6. Per-tenant
  `SearxngInstance` rows spawn a dedicated container in port range **6500–6599**
  via `services/searxng_container_manager.py`, mirroring the Kokoro TTS /
  Ollama auto-provisioning pattern. A fresh `secret_key` is generated at
  provision time (`secrets.token_urlsafe(48)`) and injected into
  `/etc/searxng/settings.yml` inside the container via Docker `put_archive` —
  no host-file mount, no shipped compose service, no repo-committed secrets.
  CRUD + lifecycle endpoints at `/api/hub/searxng/instances`. Setup flow:
  **Hub > Tool APIs > Add Integration > Web Search > SearXNG**. External-URL
  installs are also supported (toggle off auto-provision in the wizard).
  Instance names are tenant-scoped and must be unique; the wizard fetches the
  tenant's existing instances, auto-suggests a fresh name (`SearXNG`,
  `SearXNG (2)`, …), and offers inline delete for any listed row. The Hub
  **Tool APIs** tab only renders SearXNG cards/panels after the tenant has at
  least one SearXNG instance. Configured rows use the shared managed-container
  control pattern: an enable/disable toggle maps to container start/stop, while
  Restart, Logs, and Delete stay separate actions. Stale failed provisions
  (`container_status ∈ {error, failed, none, null}` with no `container_name`)
  are auto-purged on the next create so tenants don't get stuck; genuinely-
  healthy conflicts still 409 but with a structured detail payload
  (`code: 'searxng_instance_exists'`) the wizard surfaces as a recovery hint
  (BUG-669, 2026-04-20). The same soft-delete-purge pattern is also applied in
  `provider_instance_service.create_instance()` so the Ollama `ensure-ollama`
  flow doesn't 500 on re-create after a previous instance was soft-deleted
  (BUG-670).
- **Tavily** — since v0.6.0-patch.6. AI-optimized web search wrapping
  `https://api.tavily.com/search`. Request posts JSON `{api_key, query,
  search_depth: 'basic', max_results, include_answer: true}`; response carries
  both a ranked result list and a pre-synthesized `answer` string surfaced via
  `SearchResponse.metadata['answer']`. API key is stored encrypted per-tenant
  (`service='tavily'`) and loaded through `get_api_key('tavily', ...)` like
  every other API-key provider.
- All search providers register with `SearchRegistry` and are configured
  through the Hub page via the generic **Add Integration** wizard
  (`frontend/components/integrations/AddIntegrationWizard.tsx`). Since v0.7.x
  the wizard fetches its catalog from the live backend registries rather
  than shipping a hardcoded list — endpoints:
  - `GET /api/hub/search-providers` — every registered search provider
    (`SearchProviderRegistry`) with `{id, name, description, status,
    requires_api_key, is_free, tenant_has_configured}`.
  - `GET /api/hub/travel-providers` — same shape for flight/travel providers
    (`FlightProviderRegistry`).

  Both require the `hub.read` permission, both are tenant-scoped, and both
  are backed by `backend/api/routes_hub_providers.py`. The wizard keeps a
  static `FALLBACK_PROVIDERS` array (in `AddIntegrationWizard.tsx`) as an
  offline fallback; `backend/tests/test_wizard_drift.py` asserts both
  registries remain in lockstep with that fallback so a new provider can
  never ship backend-only.

**Port-range allocation summary** (auto-provisioned tenant containers):

| Service | Port range | Manager |
|---------|------------|---------|
| Kokoro TTS | 6600–6699 | `services/kokoro_container_manager.py` |
| Ollama | 6700–6799 | `services/ollama_container_manager.py` |
| SearXNG | 6500–6599 | `services/searxng_container_manager.py` |

### 20.5 Browser Automation (Playwright, CDP)

**Sources:** `backend/hub/providers/browser_automation_provider.py`, `backend/hub/providers/playwright_provider.py`, `backend/hub/providers/cdp_provider.py`, `backend/hub/providers/browser_session_manager.py`, `backend/hub/providers/browser_automation_registry.py`
Model: `BrowserAutomationIntegration` (`models.py:3136`).

Two provider types (`browser_automation_provider.py:196-252`):

| Provider | `provider_type` | Config |
|---|---|---|
| Playwright (in-container) | `playwright` | Launches Chromium inside the backend container |
| CDP (host browser) | `cdp` | Connects over CDP to a running Chrome on the host; default `cdp_url=http://host.docker.internal:9222` |

The CDP provider validates the CDP URL through `utils/cdp_url_validator.validate_cdp_url` before connecting (`cdp_provider.py:66-72`) and persists browser state (cookies, localStorage, active logins) via the live CDP connection.

### 20.6 TTS (Kokoro, OpenAI, ElevenLabs, Gemini)

**Sources:** `backend/hub/providers/tts_provider.py` (abstract + `TTSRequest`/`TTSResponse`/`VoiceInfo`), `backend/hub/providers/kokoro_tts_provider.py`, `backend/hub/providers/openai_tts_provider.py`, `backend/hub/providers/elevenlabs_tts_provider.py`, `backend/hub/providers/gemini_tts_provider.py`, `backend/hub/providers/tts_registry.py`, `backend/api/routes_tts_providers.py`

- Providers expose `get_available_voices()` → `List[VoiceInfo]` and a default voice.
- OpenAI TTS default voice: `"nova"` (`tts_provider.py:43`).
- Kokoro is a local/self-hosted TTS option. **v0.7.0 removed the stack-level `kokoro-tts` compose service and the `KOKORO_SERVICE_URL` env fallback** — Kokoro now runs as per-tenant auto-provisioned containers managed by `KokoroContainerManager` and addressed via `TTSInstance.base_url`. The provider's `synthesize()` raises `RuntimeError` if called without a `base_url`; `AudioTTSSkill` resolves one from `AgentSkill.config.tts_instance_id` → `Config.default_tts_instance_id`, and surfaces a clear skill-result error if neither is set.

#### 20.6.0 Gemini TTS (v0.6.0 addendum, preview — multi-model)

**Source:** `backend/hub/providers/gemini_tts_provider.py`. Registered in `TTSProviderRegistry` as `"gemini"` with `requires_api_key=True`, `status="preview"`.

- **Models** (`GeminiTTSProvider.SUPPORTED_MODELS`, all preview):

  | Model id | Tier | Notes |
  |---|---|---|
  | `gemini-3.1-flash-tts-preview` | Balanced (default — `DEFAULT_MODEL`) | The original 3.1 Flash TTS. Good cost / latency / quality balance. |
  | `gemini-2.5-flash-tts-preview` | Fast | Shorter latency; identical SDK shape; same WAV output. |
  | `gemini-2.5-pro-tts-preview` | Quality | Highest quality tier; pricing typically 5–10× Flash (currently `$0.00` until Google publishes pricing — see TODO in `get_pricing_info()`). |

  Tenants pick the model per agent via the Audio Agents Wizard or the regular Agent Wizard's audio step. The selection is persisted into `AgentSkill.config.model` (no migration — JSON field) and is delivered into the SDK via `client.models.generate_content(model=…)`. Unknown model ids fall back to `DEFAULT_MODEL` with a `warning` log line (rather than silently routing to a wrong model). Discover the catalog programmatically via `GET /api/tts-providers/gemini/models` (returns `[{model_id, label, is_default}]`).

- **Endpoint shape:** standard `generateContent` with `response_modalities=["AUDIO"]` and a `SpeechConfig(voice_config=VoiceConfig(prebuilt_voice_config=PrebuiltVoiceConfig(voice_name=…)))` block.
- **30 prebuilt voices:** Zephyr, Puck, Charon, Kore, Fenrir, Leda, Orus, Aoede, Callirrhoe, Autonoe, Enceladus, Iapetus, Umbriel, Algieba, Despina, Erinome, Algenib, Rasalgethi, Laomedeia, Achernar, Alnilam, Schedar, Gacrux, Pulcherrima, Achird, Zubenelgenubi, Vindemiatrix, Sadachbia, Sadaltager, Sulafat. Case-sensitive proper nouns. (Documented for the 3.1 model; the 2.5 Flash/Pro models are assumed to share the same catalog — verify per Google docs before announcing.)
- **Output:** Google returns raw 24 kHz / 16-bit / mono PCM. The provider wraps it in a WAV container using stdlib `wave` before persisting — the skill layer always receives a playable `.wav` file path under `<tempdir>/tsushin_audio/gemini_<message_id>.wav`.
- **Input quirks:** plain text + inline audio tags (`[whispers]`, `[laughs]`, `[excited]`). No SSML. No speed control across any of the 3 models. Default voice: **Zephyr**.
- **Preview retry:** Google documents that the model occasionally returns text tokens instead of audio. The provider retries up to **2 times** before surfacing a failure.
- **API key:** reuses the existing tenant Gemini key (`ApiKey.service="gemini"`). No new credential flow — the same key services LLM, TTS, and image-generation calls.
- **No per-tenant container** — Gemini TTS is a pure API call, unlike Kokoro.
- **Generic model endpoint contract:** `GET /api/tts-providers/{provider}/models` is provider-agnostic. Providers without a `SUPPORTED_MODELS` attribute (Kokoro / OpenAI / ElevenLabs today) return `[]` (200), so the frontend uniformly hides the model picker. When OpenAI's `tts-1` / `tts-1-hd` are exposed in a future release, the picker will surface automatically without a UI change.
- Surfaced in all TTS-facing wizards: `AudioAgentsWizard` (`frontend/components/audio-wizard/AudioAgentsWizard.tsx`), `AgentWizard → StepAudio` (`frontend/components/agent-wizard/steps/StepAudio.tsx`), and the shared `AudioProviderPicker` / `AudioProviderFields` components. Drift between the backend `SUPPORTED_MODELS` dict and the frontend `GEMINI_TTS_MODELS` fallback array is enforced by `backend/tests/test_wizard_drift.py` Guard 10.

#### 20.6.1 Kokoro TTS Setup Wizard

**Component:** `frontend/components/tts/KokoroSetupWizard.tsx`
**Entry point:** `/hub` page → AI Providers tab → `+ New Instance` → Add Provider → Audio/TTS → Kokoro. Per-tenant Kokoro instance management is consolidated inside the Hub Kokoro card after an instance exists. The card renders the full instance list with a per-instance enable/disable container toggle, Restart / Logs / Delete controls, and a default-selector radio. (The legacy `/settings/tts` page and the compose `tts` profile toggle were removed in v0.7.0.)

Four-step guided flow for creating a per-tenant Kokoro TTS container and (optionally) wiring it to agents:

1. **What is Kokoro TTS?** — marketing/explanation card (languages, voice count, cost, image size, CPU-friendliness).
2. **Configure** — instance name, auto-provision toggle, memory limit (1g/1.5g/2g), default voice (from a curated list of 14 Kokoro voices with language/gender auto-hints), default speed (0.5–2.0× slider), default language (pt/en), audio format (opus/mp3/wav), set-as-tenant-default checkbox.
3. **Link to Agent(s)** — multi-select checkbox list of tenant agents with "Select all" / "Skip this step". Enables the `audio_response` skill on each selected agent.
4. **Review & Create** — summary + "Create & Provision" CTA. Progress step then polls `GET /api/tts-instances/{id}/container/status` every 3 s until `running`, auto-calls `assign-to-agent` per selected agent, and closes with a success toast. Error states surface a Retry button.

**Backend support:**
- `POST /api/tts-instances/{id}/assign-to-agent` — body `{agent_id, voice?, speed?, language?, response_format?}`. Upserts the `audio_response` AgentSkill row for the target agent. Tenant isolation double-guarded on both the TTS instance and the agent (404 on mismatch). Permission: `org.settings.write`.

#### 20.6.1a Audio Agents Onboarding Wizard (v0.7.0)

**Component:** `frontend/components/audio-wizard/AudioAgentsWizard.tsx`
**Context provider:** `frontend/contexts/AudioWizardContext.tsx` (mounted globally in `app/layout.tsx` alongside `GoogleWizardProvider` and `WhatsAppWizardProvider`)
**Entry points:**
- **Onboarding tour step 12** — a "Voice Capabilities (optional)" step calls `useAudioWizard().openWizard()`; skippable in one click.
- **Studio → New Agent modal** (`frontend/components/watcher/studio/StudioAgentSelector.tsx`) — a Text / Voice / Hybrid radio; picking Voice or Hybrid closes the inline create modal and calls `openWizard({ presetMode: 'new', presetAgentType, presetNewAgentName })`.
- Any consumer can also call `useAudioWizard().openWizard({ presetProvider?, presetAgentId?, presetMode? })` directly.

This wizard replaced the built-in Kokoro / Kira / Transcript seed agents (removed from `backend/services/agent_seeding.py` in v0.7.0). Existing tenants keep any already-seeded audio agents untouched; new tenants start with only the text-only defaults and create audio agents opt-in through this wizard.

Five configuration steps + one progress step:

1. **Intent** — three cards: *Voice responses (TTS)*, *Audio transcription only*, *Hybrid — both*.
2. **Provider** — four cards: Kokoro (free/local), OpenAI TTS (paid), ElevenLabs (premium), Google Gemini TTS (preview, reuses tenant Gemini key). Each card shows a **Detected** badge when the tenant already has that provider configured (`api.getTTSInstances()` for Kokoro, `api.getProviderInstances()` for OpenAI / ElevenLabs / Gemini keys), or a **Needs API key** badge linking back to Hub → AI Providers otherwise.
3. **Voice & transcription settings** — language first (shared between TTS + STT), then:
   for TTS, the existing provider-specific voice / speed / format controls (plus Kokoro memory-limit + "Set as tenant-default TTS");
   for transcription, an **ASR backend** selector with *OpenAI Whisper*, *Use tenant default*, and *Pin a specific local instance*. The local-instance options are sourced from `GET /api/asr-instances`, while the tenant-default card reflects `GET /api/settings/asr/default`.
4. **Agent target** — radio: *Create a new Voice Assistant* (system prompt defaults mirror the old Kira/Kokoro prompts, preserved as client-side templates in `defaults.ts`) or *Attach audio to an existing agent* (preserves other skills on the target). Existing-agent radio is disabled if the tenant has no agents yet.
5. **Review & Create** — summary cards + skill diff (`audio_tts`, `audio_transcript`, or both) + "Create & Provision" CTA.

On submit: the Kokoro path creates a `TTSInstance`, polls `GET /api/tts-instances/{id}/container/status` every 3 s until `running` (~30–90 s) and then calls `POST /api/tts-instances/{id}/assign-to-agent`; the OpenAI/ElevenLabs/Gemini path skips the TTSInstance and directly calls `PUT /api/agents/{id}/skills/audio_tts` with `{provider, voice, language, speed, response_format, model?}`. If intent is hybrid or transcript, `PUT /api/agents/{id}/skills/audio_transcript` is also called with `{response_mode, language, model, asr_mode, asr_instance_id?}`. New-agent mode creates a Contact (`POST /api/contacts`), an Agent (`POST /api/agents`), then an update call (`PUT /api/agents/{id}`) to apply `memory_size` / `response_template` / `enabled_channels` defaults. All orchestration is client-side — no new backend endpoint was introduced.

**Events.** The provider emits `window.dispatchEvent(new CustomEvent('tsushin:audio-wizard-closed'))` on close so the onboarding tour's step 12 callback can auto-advance to step 13 (mirrors the WhatsApp wizard pattern).

**Completion callbacks.** `useAudioWizardComplete(cb)` subscribes to wizard completion for the lifetime of a component — Hub / Studio pages can use this to reload their agent and TTS-instance lists.

### 25.8 `/settings/asr`

`frontend/app/settings/asr/page.tsx` is the tenant-facing ASR control plane for Track D:

1. **Default transcription path** — `GET/PUT /api/settings/asr/default`. `null` means OpenAI Whisper; a concrete `default_asr_instance_id` means "use this tenant's local Speaches/Whisper instance by default".
2. **Local instance provisioning** — `POST /api/asr-instances` creates a managed or external ASR instance. The page exposes instance name, default model, memory limit, and auto-provision toggle.
3. **Container lifecycle** — per-instance `start` / `stop` / `restart` / `delete` actions call `/api/asr-instances/{id}/container/*` and `/api/asr-instances/{id}`. Managed Speaches containers mount their Hugging Face cache at `/root/.cache/huggingface`; deactivating, deleting, or discovering a stale inactive default clears `Tenant.default_asr_instance_id` back to OpenAI fallback.

Agent-level audio surfaces (Audio Agents Wizard, Agent Wizard, Agent Skills Manager) can then choose `openai`, `tenant_default`, or `instance` for `audio_transcript.config.asr_mode`.

#### 20.6.2 Ollama Setup Wizard

**Component:** `frontend/components/ollama/OllamaSetupWizard.tsx`
**Entry point:** `/hub` page → AI Providers tab → `+ New Instance` → Add Provider → Local LLM → Ollama. Once an Ollama instance exists, the Hub Local Services card appears; auto-provisioned containers use the same enable/disable toggle pattern as Kokoro and SearXNG, with Restart / Logs / deprovision kept as explicit secondary actions. Host-mode Ollama keeps host URL management semantics.

Five-step guided flow for provisioning an Ollama container, pulling a model, and wiring agents:

1. **What is Ollama?** — explanation (cost, GPU optional, image/model sizes, best-for scenarios).
2. **Configure container** — instance name, GPU checkbox (with NVIDIA Container Toolkit note), memory limit (2/4/8/16 GB).
3. **Choose a model** — radio list of 7 curated models (llama3.2:1b, llama3.2:3b, qwen2.5:3b, qwen2.5:7b, deepseek-r1:7b, phi3.5:3.8b, mistral:7b) with params/disk/summary columns, plus a Custom option for any `namespace/model:tag`. The curated list lives in `frontend/lib/ollama-curated-models.ts` (`OLLAMA_CURATED_MODELS` / `OLLAMA_CURATED_MODEL_IDS`) and is imported by both this wizard and the Hub Ollama panel — edits to the module propagate to both surfaces.
4. **Link to Agent(s)** — multi-select agents; their LLM backend will switch to Ollama on the chosen model.
5. **Review & Provision** — summary + "Provision & Pull" CTA. Progress step runs `ensureOllamaInstance` → `provisionOllamaContainer` → poll status → `pullOllamaModel` → poll pull job (2 s tick, live progress bar) → `assignOllamaInstanceToAgent` per selected agent. Three-stage indicator (Provision / Pull / Assign) with per-stage active/done states and a Retry button on error.

**Backend support:**
- `POST /api/provider-instances/{id}/assign-to-agent` — body `{agent_id, model_name}`. Sets `Agent.provider_instance_id`, `Agent.model_name`, and `Agent.model_provider` (to the instance vendor — typically `"ollama"`) in one call. Same double-guarded tenant isolation. Empty `model_name` returns 400. Permission: `org.settings.write`.

### 20.7 MCP Server Registration

**Sources:** `backend/hub/mcp/connection_manager.py`, `backend/hub/mcp/sse_transport.py`, `backend/hub/mcp/stdio_transport.py`, `backend/hub/mcp/transport_base.py`, `backend/hub/mcp/utils.py`
Custom third-party MCP servers can be registered via stdio or SSE transports. The `connection_manager` maintains the active MCP client sessions and exposes them to agent skills.

**Stdio transport toolbox bootstrap (BUG-512, 2026-04-10):** stdio MCP servers run their binary inside the tenant's toolbox container. `MCPConnectionManager.get_or_connect` now calls `ToolboxContainerService.ensure_container_running(tenant_id, db)` before constructing a stdio transport, so first-time `POST /api/mcp-servers/{id}/test` calls and first-time runtime invocations create or start the toolbox container on demand. Prior to this, fresh installs would error with `Container not found for tenant ... Please start it first` because there was no first-class UI action to bootstrap the toolbox. SSE and streamable_http transports are unaffected.

### 20.7.1 MCP Server Creation Wizard

After creating a new MCP server in Hub > MCP Servers, a 3-step wizard (`frontend/components/mcp/MCPServerWizard.tsx`) guides users through:

1. **Success + Tool Discovery** — shows server name, connection status, and discovered tools list
2. **Create Custom Skill** — pre-populates a custom skill form with the MCP server and selected tool; user can customize name and description
3. **Assign to Agents** — lists active agents with checkboxes to assign the new custom skill

Each step is skippable. The wizard eliminates the need to navigate between Hub > MCP Servers, Studio > Custom Skills, and Studio > Agent > Custom Skills tabs.

### 20.8 OAuth Token Refresh Worker

**Source:** `backend/hub/oauth_token_refresh_worker.py`

A background worker that polls all OAuth-backed integrations (Google, Asana, etc.) and refreshes access tokens before expiry.

**Env var configuration** — `backend/settings.py:111-120`:

| Env var | Default | Purpose |
|---|---|---|
| `TSN_OAUTH_REFRESH_POLL_MINUTES` | `30` | Poll interval in minutes |
| `TSN_OAUTH_REFRESH_THRESHOLD_HOURS` | `24` | Refresh tokens expiring within this window |
| `TSN_OAUTH_REFRESH_MAX_RETRIES` | `3` | Per-token refresh retry count |
| `TSN_OAUTH_REFRESH_RETRY_DELAY` | `5` (seconds) | Base exponential backoff |

---

## 21. Settings — UI Taxonomy

All subpages live at `frontend/app/settings/<subpage>/page.tsx`. Directory confirmed by listing `frontend/app/settings/`. The index page is `frontend/app/settings/page.tsx`.

### 21.1 Organization (`frontend/app/settings/organization/page.tsx`)

**Purpose:** View and edit tenant-level identity and plan information.

| Field | Type | Source line |
|---|---|---|
| Organization Name | Input (editable by org.settings.write) | `organization/page.tsx:196` |
| Organization Slug | Input | `organization/page.tsx:204` |
| Organization ID | Input (read-only display) | `organization/page.tsx:212` |
| Status | Label (e.g., active/suspended) | `organization/page.tsx:219` |

Sections:
- "Basic Information" (`:192`)
- "Plan & Limits" (`:234`) — shows current plan
- "Usage This Month" (`:256`)
- "Save Changes" button (`:282`)

### 21.2 Team Members (`frontend/app/settings/team/`)

Subroutes:
- `team/page.tsx` — member list with search (`placeholder="Search by name or email..."`, `:250`)
- `team/invite/page.tsx` — invite form:
  - **Email Address** input — `team/invite/page.tsx:171` (`placeholder="colleague@example.com"`, `:176`)
  - **Personal message** textarea (`placeholder="Add a personal message to the invitation email..."`, `:226`)
- `team/[id]/` — per-member detail view

### 21.3 Roles & Permissions (`frontend/app/settings/roles/page.tsx`)

Lists system and tenant-defined roles with display names and permission badges. Read-heavy page — permissions are rendered per-role with description blocks.

### 21.4 Integrations (`frontend/app/settings/integrations/page.tsx`)

**Purpose:** Tenant-level OAuth credentials (Client ID / Client Secret) for third-party providers. Currently houses the Google OAuth credentials panel.

| Field | Type | Source |
|---|---|---|
| Google — Client ID | Input (`placeholder="xxxxx.apps.googleusercontent.com"`) | `integrations/page.tsx:315` |
| Google — Client Secret | Password input (`placeholder="GOCSPX-xxxxx"` or "(leave blank to keep current)") | `integrations/page.tsx:323` |
| Client ID (display) | Read-only display of saved value | `integrations/page.tsx:200` |
| Client Secret (display) | Masked | `integrations/page.tsx:206` |

"Coming Soon" section (`:277`) lists planned integrations. Removing Google credentials warns that it will disconnect all Google integrations (Gmail, Calendar) and disable Google SSO (`:79`).

**Guided wizards — shared with Hub.** The "Set up Gmail →" and "Set up Google Calendar →" buttons on this page open the same 6-step wizards (`GmailSetupWizard`, `GoogleCalendarSetupWizard`) that the Hub **"+ Add Productivity Integration"** launcher dispatches to. Gmail is no longer offered from the channel picker; inbound email automation now starts from Hub → Communication → Triggers → Email Trigger. The Hub wizards (`frontend/components/integrations/ProductivityWizard.tsx`, `frontend/components/triggers/TriggerWizard.tsx`) run a picker step and then hand off to the per-service sub-wizard — this is the same pattern the AI-Provider `ProviderWizard` uses. Both Google sub-wizards live under a global `GoogleWizardProvider` (`frontend/contexts/GoogleWizardContext.tsx`) mounted in `app/layout.tsx`. The wizard:
1. Confirms Google OAuth app credentials are configured.
2. Opens a popup to `/api/hub/google/{gmail|calendar}/oauth/authorize` and polls `/api/hub/google/{gmail|calendar}/integrations` for the new row.
3. Lets the user pick one or more agents and, on completion, calls `PUT /api/agents/{id}/skills/{gmail|scheduler}` + `PUT /api/agents/{id}/skill-integrations/{gmail|scheduler}` to enable the skill and bind the new `integration_id`.

Either caller page can subscribe to completion via `useGoogleWizardComplete(kind, cb)` — Settings re-fetches Google credentials, Hub re-fetches `/api/hub/integrations` so the card list refreshes without a page reload.

**Disconnected accounts are excluded from the wizard's Step 3 picker.** `GET /api/hub/google/{gmail|calendar}/integrations` filters out rows with `health_status='disconnected'`, matching the filter used by the Hub card list. This prevents a user from binding an agent skill to a dead integration, which would hide the resulting card in Hub and make the flow feel silently broken. To reuse a previously-disconnected email, click "Connect new account" — the OAuth callback flips the existing row back to `is_active=True` and clears the `disconnected` status, so it reappears in the picker.

**OAuth popup handoff.** "Connect new account" opens the Google consent screen in a popup. After approval, Google redirects the popup to the backend OAuth callback, which in turn redirects to `/hub?integration=<kind>&status=success&id=<n>`. The Hub page detects it's loaded inside a popup (via `window.opener`) and, instead of rendering, posts a `{ source: 'tsushin-google-oauth', integration, integration_id, status }` message to the opener (same-origin) and calls `window.close()`. The wizard listens for that message in a `useEffect` gated on `isOpen`, stops its 3-second poll, re-fetches the integration list, and selects the new row. Popup-blocked fallback still works: a direct visit to `/hub?…` has no `window.opener`, so the page renders normally.

**Integration type is carried through the callback.** `backend/hub/google/oauth_handler.py::handle_callback` receives `integration_type` as an explicit argument; the outer `backend/api/routes_google.py::oauth_callback` reads it from the `OAuthState.integration_type` prefix (`google_gmail` → `gmail`, `google_calendar` → `calendar`) and passes it in. The legacy fallback that parsed the type from the `redirect_url` query string is still there for the direct-redirect flow, but if neither source yields a valid type the handler raises `ValueError` rather than defaulting to calendar — the popup-driven wizard flow never sets a `redirect_url`, and silently defaulting used to cause gmail OAuth to upsert into the calendar integration tables.

### 21.4.1 Default Agents (`frontend/app/settings/default-agents/page.tsx`)

**Purpose:** central routing control for tenant-wide fallback agent resolution. This page replaces the old inline "set default" affordance in Agent Studio.

**Sections:**
- **Tenant Default** — last-resort fallback when no more specific match exists
- **Channel Defaults** — per-instance defaults for conversational channels such as WhatsApp, Telegram, Slack, and Discord
- **Trigger Defaults** — per-instance defaults for trigger rows such as webhook and email
- **User Defaults** — per-channel sender identifier overrides for known raw channel IDs before a contact-level mapping exists

**Runtime resolution order** (`backend/services/default_agent_service.py`):
- Channels: explicit agent -> `ContactAgentMapping` -> `UserChannelDefaultAgent` -> instance `default_agent_id` -> legacy bound agent FK -> tenant default
- Triggers: explicit agent -> trigger instance `default_agent_id` -> legacy bound agent FK -> tenant default

**Fail-closed trigger behavior:** if no active agent resolves for a trigger, runtime execution is expected to stop with an explicit error/health signal instead of silently queueing work.

**Related UI changes:** `frontend/app/agents/page.tsx` still shows the current tenant default as a read-only stat card, but all edits now route to `/settings/default-agents`.

### 21.5 Security & SSO (`frontend/app/settings/security/page.tsx`)

Three sections:

**Google Sign-In Policy:**

| Field | Type | Source |
|---|---|---|
| Enable Google Sign-In | Toggle | `security/page.tsx:326-339` |
| Allowed Email Domains | Comma-separated input (`placeholder="example.com, company.org"`) | `security/page.tsx:356-366` |
| Auto-provision new users | Toggle | `security/page.tsx:382-395` |
| Default Role for New Users | Select (only visible when auto-provision ON) | `security/page.tsx:417-433` |

**Encryption Keys** (`security/page.tsx:459-`):

| Field | Purpose | Source |
|---|---|---|
| Google Encryption Key | Fernet key for Google OAuth tokens (Gmail, Calendar) | `security/page.tsx:491-522` |
| Hub Encryption Key | Fernet key for Asana, Amadeus, Telegram tokens | `security/page.tsx:527-559` |

Each key field has a show/hide eye toggle and placeholder `"Enter Fernet encryption key"`. Helper text includes the generation command: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` (`:471`).

### 21.6 Billing & Plans (`frontend/app/settings/billing/page.tsx`)

360-line page displaying the current plan, usage breakdown, and upgrade/downgrade options. No form inputs inventoried in the grep pass — the page is primarily read-only with plan-tier cards and action buttons.

### 21.7 Audit Logs (`frontend/app/settings/audit-logs/page.tsx`)

**Filters** (select dropdowns, `audit-logs/page.tsx:39-66`):

| Filter | Options |
|---|---|
| Action | All Actions, Authentication, Agents, Flows, Contacts, Settings, Security, Shell, API Clients, Custom Skills, MCP Servers, Team |
| Severity | All Severities, Info, Warning, Critical |
| Channel | All Channels, Web, API, WhatsApp, Telegram, System |
| From / To | Date range |

Date-only filters now expand to full-day bounds on the backend, so selecting `To = 2026-04-23` includes events through `2026-04-23 23:59:59.999999` instead of stopping at midnight.

**Syslog Forwarding Panel** (`audit-logs/page.tsx:416-521`):

| Field | Type | Source |
|---|---|---|
| Host | Input (`placeholder="logs.example.com"`) | `:416-424` |
| Port | Numeric input | `:426-437` |
| Protocol | Select: UDP / TCP / TLS | `:439-449` |
| Facility | Select: User-level (1), Auth (4), Auth-priv (10), Audit (13), Local0–7 (16-23) | `:451-460` |
| App Name | Input (`placeholder="tsushin"`) | `:463-470` |
| TLS CA Certificate | Textarea (PEM) | `:487-495` |
| Event Categories | Checkbox list (per-category filter) | `:513-521` |

CSV export, retention config, and searchable event log are rendered in the main body.

### 21.8 Model Pricing (`frontend/app/settings/model-pricing/page.tsx`)

See §19.4.

### 21.9 System AI (`frontend/app/settings/ai-configuration/page.tsx`)

**Note:** `frontend/app/settings/system-ai/page.tsx` is a 5-line stub; the actual system AI configuration lives at `frontend/app/settings/ai-configuration/page.tsx`.

**Purpose:** Select the AI provider instance and model used by system-level features (Sentinel, memory extraction, skill classification, etc.).

The System AI config now points to an existing **Provider Instance** (managed in the Hub) instead of maintaining its own duplicated provider/model lists. The `Config` table stores `system_ai_provider_instance_id` (FK to `provider_instance`) alongside the model name.

UI flow:
- "Select Provider Instance" — card grid of active Provider Instances showing vendor icon, instance name, health dot, model count, and default badge. Managed via the Hub link.
- "Select Model" — list of models from the selected instance's `available_models`. If the instance has no discovered models, a manual text input is shown.
- "Test Connection" — sends a test message via the selected instance + model.
- Saves `{provider_instance_id, model_name}` to system config.

Backend resolution (`services/system_ai_config.py`): When `system_ai_provider_instance_id` is set, the vendor is resolved from the ProviderInstance and the AIClient receives the `provider_instance_id` for proper API key/base URL resolution. Falls back to legacy `system_ai_provider`/`system_ai_model` columns when no instance is linked.

### 21.10 Vector Stores (`frontend/app/settings/vector-stores/page.tsx`)

**Purpose:** Select the tenant's default vector store instance for agent long-term memory.

| Field | Type | Source |
|---|---|---|
| Default Vector Store | Select (options: `ChromaDB (built-in)` default, then per-instance `name (vendor)` entries with `- Provisioned` suffix for auto-provisioned) | `vector-stores/page.tsx:123-140` |

Supported vendors (label map, `:8-12`): `mongodb → MongoDB`, `pinecone → Pinecone`, `qdrant → Qdrant`.

Actions: **Save**, **Test** (connection probe returns `{success, message}` via `api.testVectorStoreConnection`).

Fresh setup now attempts to create `Qdrant (Default)` through the shared vector-store provisioning helper. If provisioning fails (for example image pull or runtime startup issues), setup completes with a warning and the operator can repair or recreate the instance later from **Settings → Vector Stores**.

Agents can override the default in the Agent Builder.

### 21.11 Prompts & Patterns (`frontend/app/settings/prompts/page.tsx`)

Four tabs (`prompts/page.tsx:70-88`):

| Tab | Label | Purpose |
|---|---|---|
| 1 | Global Config | Tenant-wide prompt configuration |
| 2 | Tone Presets | Manage tone presets (seeded via `backend/services/tone_preset_seeding.py`) |
| 3 | Slash Commands | Tenant custom slash commands (see §26) |
| 4 | Project Patterns | Project-matching patterns |

### 21.12 Sentinel Security (`frontend/app/settings/sentinel/page.tsx`)

Large 2877-line page with 8 tabs (`sentinel/page.tsx:541-548`):

| Tab | Label |
|---|---|
| general | General |
| profiles | Profiles |
| memguard | MemGuard |
| prompts | Analysis Prompts |
| llm | LLM Configuration |
| stats | Statistics |
| exceptions | Exceptions |
| hierarchy | Hierarchy |

**Enforcement Modes** (`sentinel/page.tsx:787-790`):

| Mode | Description |
|---|---|
| `block` | Analyze and block detected threats (recommended) |
| `warn_only` | Analyze and flag threats without blocking |
| `detect_only` | Analyze and log threats silently (audit mode) |
| `off` | Disable Sentinel analysis entirely |

**Analysis Toggles** (`sentinel/page.tsx:696-699`):

| Key | Label |
|---|---|
| `enable_prompt_analysis` | Prompt Analysis — analyze user messages for injection attempts |
| `enable_tool_analysis` | Tool Analysis — analyze tool arguments |
| `enable_shell_analysis` | Shell Analysis — analyze shell commands |
| `enable_slash_command_analysis` | Slash Command Analysis — analyze `/invoke`, `/shell` (disable to bypass) |

**Detection Toggles** (`sentinel/page.tsx:841-846`):

| Key | Label | Severity |
|---|---|---|
| `detect_prompt_injection` | Prompt Injection | high |
| `detect_agent_takeover` | Agent Takeover | high |
| `detect_poisoning` | Poisoning Attacks | medium |
| `detect_shell_malicious_intent` | Shell Malicious Intent | critical |
| `detect_browser_ssrf` | Browser SSRF | critical |
| `detect_vector_store_poisoning` | Vector Store Poisoning | high |

Aggressiveness slider: multi-level labels (`:885-894`) — specific labels not enumerated here.

### 21.13 API Clients (`frontend/app/settings/api-clients/page.tsx`)

Create / list / rotate / revoke API clients for the Public API v1.

**Create form** (`api-clients/page.tsx:365-405`):

| Field | Type | Source |
|---|---|---|
| Name * | Input (`placeholder="e.g., CRM Integration"`) | `:365-371` |
| Description | Textarea (`placeholder="What will this client be used for?"`) | `:376-382` |
| Role | Select (5 role options, below) | `:387-395` |
| Rate Limit (requests/minute) | Numeric input | `:400` |

**API Roles** (`api-clients/page.tsx:14-19`):

| Value | Label | Description |
|---|---|---|
| `api_agent_only` | Agent Only | Can list agents and chat (read + execute) |
| `api_readonly` | Read Only | Can view agents, contacts, memory, analytics |
| `api_member` | Member | Can create/update agents, contacts, flows, knowledge |
| `api_admin` | Admin | Full API access except billing and team |
| `api_owner` | Owner | Full API access including org settings and audit |

On creation the UI reveals **Client ID** (`:450`) and **Client Secret** (`:469`) once — the secret must be copied before navigating away.

### 21.14 Message Filtering (`frontend/app/settings/filtering/page.tsx`)

**Purpose:** Global filters for WhatsApp/Telegram message intake (mirrors per-instance filters described in §15.1).

| Field | Type | Source |
|---|---|---|
| Group name (allowlist) | Input (`placeholder="Enter group name (exact match)"`) | `filtering/page.tsx:220` |
| Phone number (DM allowlist) | Input (`placeholder="Enter phone number (e.g., +5500000000001)"`) | `filtering/page.tsx:275` |
| Keyword filter | Input (`placeholder="Enter keyword"`) | `filtering/page.tsx:330` |
| DM Auto Mode | Labelled toggle (`dmAutoMode`) | `filtering/page.tsx:387` |

These values persist into `Config.group_filters` / `Config.number_filters` (JSON arrays) on the tenant config row.

---

## 22. System Admin (Global Admin Only)

All global admin pages are under `frontend/app/system/` and are only accessible to users with the `is_global_admin` flag set on the `User` model.

### 22.1 Tenant Management (`frontend/app/system/tenants/`)

- `tenants/page.tsx` — list all tenants (create, activate, suspend).
- `tenants/[id]/` — per-tenant detail subroute (not enumerated in this pass).

Backing service: `backend/services/audit_service.py` (global admin actions logged as `tenant.create`, `tenant.suspend`, etc. — see §23).

### 22.2 User Management (`frontend/app/system/users/page.tsx`)

Global user directory — list all users across tenants, toggle `is_global_admin`, reset credentials, suspend accounts.

**Invite User + Create User — explicit kind picker (since 2026-04-19).** Both modals lead with a two-option segmented control:

| Kind | Semantics | Required fields |
|---|---|---|
| **Tenant User** (default) | Belongs to exactly one organization; cannot cross tenant boundaries | email, **Organization** (required — labeled `{name} — {slug} ({user_count} members)`), **Role** (`owner | admin | member | readonly`) |
| **Global Admin** | Platform-wide administrator, `User.is_global_admin=True`, `User.tenant_id=NULL`, no `UserRole` row | email only (tenant + role hidden) |

The Organization dropdown is only shown for the Tenant-User path; when empty it surfaces a red inline helper (*"Invitees are not global admins and must belong to one tenant"*). The submit button stays disabled until required fields for the active kind are filled — the form cannot submit in an ambiguous state. Backing endpoints: `POST /api/admin/invitations/` (invite) and `POST /api/admin/users/` (direct create). Both accept the same shape: `is_global_admin=true` ⇒ no tenant_id/role; `is_global_admin=false` ⇒ both required. See §6.5.

**Pending Invitations.** A second section on the same page lists outstanding invites across all tenants with scope (Global vs tenant name), role, auth provider, invited-by, expiry, and a Cancel button. Powered by `GET /api/admin/invitations` + `DELETE /api/admin/invitations/{id}`.

### 22.3 Global SSO (`frontend/app/system/sso/page.tsx`)

Dedicated page for platform-wide Google OAuth configuration (moved out of the retired `/system/integrations` hub in 2026-04-19). Backed by the `global_sso_config` singleton table and the `/api/admin/sso-config` endpoints. Fields:

| Field | Purpose |
|---|---|
| `google_sso_enabled` | Master toggle for platform-scope SSO |
| `google_client_id` | Platform OAuth 2.0 Client ID (visible) |
| `google_client_secret` | Platform OAuth 2.0 Client Secret (Fernet-encrypted at rest, `sso_client_secret_global` identifier; never returned by default — pass `?include_secret=true`) |
| `allowed_domains` | JSON array of domains the platform will accept Google sign-ins from |
| `auto_provision_users` | **Disabled by default.** Creating global admins on first sign-in is an unsafe default — global admins must always be explicitly invited. This toggle is reserved for future use with a strict domain whitelist. |
| `default_role_id` | Only consulted if `auto_provision_users=true`; shown conditionally in the UI |

**Credential resolution order** (`backend/auth_google.py::get_oauth_credentials`): per-tenant `GoogleOAuthCredentials` (when a tenant context is present) → `GlobalSSOConfig` (when `google_sso_enabled=true` and credentials are complete) → env-var fallback (`GOOGLE_SSO_CLIENT_ID` / `GOOGLE_SSO_CLIENT_SECRET` in `backend/settings.py`). Global and tenant scopes are fully independent — updates at one scope do not affect the other.

**`/system/integrations` is deprecated.** The old hub page (navigation cards + embedded SSO config) was split in 2026-04-19: the admin cards now live as a *System* card group inside Core (`/settings`); the SSO config moved here. The `/system/integrations` route is a redirect stub that `router.replace('/settings')` on mount so old bookmarks and email links do not 404.

### 22.3.1 System group inside Core (global admin only)

Starting 2026-04-19, the global-admin view no longer has a separate top-level **System** nav item. Instead, `/settings` (the **Core** hub) gains a *System* card group (role-gated on `is_global_admin`) with five cards: **Tenant Management**, **User Management**, **Plans & Limits**, **Remote Access**, **Global SSO**. This matches the tenant-view pattern where operational areas are discovered as cards under Core. Global-admin login now redirects to `/settings` (was `/system/integrations`). Top nav is identical for all roles.

### 22.4 Plans / Subscription Tiers (`frontend/app/system/plans/page.tsx`)

Define plan tiers (Free, Pro, Enterprise, etc.) with quotas and feature toggles. Each tenant's current plan is visible on the Organization page (§21.1).

### 22.5 Remote Access (Cloudflare Tunnel) — v0.6.0

**Primary sources:**
- `backend/services/cloudflare_tunnel_service.py` — subprocess lifecycle, supervisor, metrics probe
- `backend/services/remote_access_config_service.py` — DB CRUD + optimistic concurrency + audit
- `backend/api/routes_remote_access.py` — REST surface under `/api/admin/remote-access/*`
- `backend/auth_routes.py::_enforce_remote_access_gate` — per-tenant login gate
- `frontend/app/system/remote-access/page.tsx` — Global Admin UI

Remote Access exposes the whole Tsushin instance through a single Cloudflare Tunnel so users can log in from outside the internal network. The feature is **off by default** at both the system level (`RemoteAccessConfig.enabled=false`) and the per-tenant level (`Tenant.remote_access_enabled=false`). There are two layers of control:

1. **System tunnel** (managed by the Global Admin in `/system/remote-access`): configures and runs the `cloudflared` subprocess inside the backend container.
2. **Per-tenant entitlement** (managed by the Global Admin per tenant): gates which tenants' users can actually log in via the public URL. Users from tenants without the entitlement get an HTTP 403 with the error code `REMOTE_ACCESS_TENANT_DISABLED` and the message "Remote access is not enabled for this tenant. Contact your administrator." The attempt is written to the tenant audit log as `auth.remote_access.denied` (severity=warning).

#### 22.5.1 Architecture

```
┌──────────────────────┐         ┌────────────────────────────┐
│ Cloudflare Edge      │◀──QUIC──│ cloudflared subprocess     │
│ tsushin.example.com  │         │ (inside tsushin-backend,   │
└──────────────────────┘         │  metrics @127.0.0.1:20241) │
                                 └────────────┬───────────────┘
                                              │ http://tsushin-proxy:80
                                              ▼
                                 ┌────────────────────────────┐
                                 │ Caddy (tsushin-proxy)      │
                                 │ /api/*  → backend:8081     │
                                 │ /ws/*   → backend:8081     │
                                 │ else    → frontend:3030    │
                                 └────────────────────────────┘
```

Key properties:
- `cloudflared` runs as a supervised Python subprocess inside `tsushin-backend` (not a separate compose sidecar). A supervisor task restarts it up to 3 times with 5s/15s/30s backoff before giving up and marking `status=error`.
- Readiness for **named** mode is a two-stage check (BUG-589): (1) poll `cloudflared`'s Prometheus metrics endpoint for `cloudflared_tunnel_ha_connections > 0` — proves the local subprocess has an edge connection — then (2) run a retrying `HEAD https://<tunnel_hostname>/api/health` probe (up to ~30 s, 2 s between attempts) to prove the **public hostname actually serves the app end-to-end**. Only after both pass does the snapshot transition to `state="running"`. Between stages the state is `state="verifying"` with a `"Verifying public hostname <host> is serving the app"` message. If the public probe never succeeds, the tunnel is stopped and the admin sees the real error (e.g. last HTTP status `502`) instead of a false green "running" badge. Quick-mode readiness continues to rely on `public_url` appearing on stdout.
- Cloudflare terminates TLS at the edge. The tunnel forwards plain HTTP to the local Caddy proxy on port 80, which then routes `/api/*` and `/ws/*` to the backend and everything else to the frontend. This is why `install.py` generates a `:80` site block in every SSL mode; without it, tunnel requests would bypass Caddy's `/api` routing and the frontend's API calls would 502.
- The tunnel token is encrypted at rest with a dedicated Fernet key (`config.remote_access_encryption_key`), which itself is wrapped with `TSN_MASTER_KEY` (SEC-006 envelope pattern). The plaintext token is never logged, never returned in any API response, and only surfaced as the boolean `tunnel_token_configured` in the GET config endpoint.
- Optimistic concurrency on config writes: the PUT endpoint takes an `expected_updated_at` and returns HTTP 409 if the stored `updated_at` has moved since the admin last read it.

#### 22.5.2 Tunnel modes

| Mode | When to use | URL | Persistence | Auth |
|---|---|---|---|---|
| **Quick** | Dev, demos, smoke tests | Random `https://<words>.trycloudflare.com` | Ephemeral (new URL per start) | None — any visitor can reach it |
| **Named** | Production / enterprise | Custom FQDN (e.g. `https://tsushin.acme.com`) | Stable; bound to a Cloudflare Tunnel in your Zero Trust account | Tunnel token pinned to your Cloudflare account; add Zero Trust Access policies if you want additional auth on top of Tsushin's own login |

In both modes, Tsushin's own RBAC + per-tenant entitlement still apply.

#### 22.5.3 Setting up a Named Tunnel (production)

One-time Cloudflare setup (only needed for Named mode):

1. Log in to the Cloudflare dashboard → **Zero Trust** → **Networks** → **Connectors** (previously "Tunnels").
2. **Create a tunnel** → choose **Cloudflared** → name it (e.g. `tsushin`). Cloudflare generates a connector token — copy it; you'll need it in a moment.
3. Go to **Published application routes** → **Add a published application route**:
   - **Subdomain + Domain**: pick the hostname you want (e.g. `tsushin` + `acme.com` → `tsushin.acme.com`). Cloudflare will auto-create the DNS record for you.
   - **Path**: leave empty.
   - **Service type**: HTTP.
   - **Service URL**: `tsushin-proxy:80` (the Caddy reverse proxy inside your Docker network). **Do not** use `frontend:3030` — that would bypass Caddy and break `/api` routing.
   - Tsushin now defaults saved tunnel targets to the stack proxy service and rejects starts when that proxy/Caddy layer is unreachable, rather than booting a broken public route.

Tsushin setup:

1. Log in as a Global Admin and navigate to **System Administration** → **Remote Access** (`/system/remote-access`).
2. In the **Tunnel Configuration** card:
   - Check **Feature enabled globally**.
   - Select **Named** mode.
   - Paste the **Tunnel hostname** (e.g. `tsushin.acme.com`).
   - Paste the **Tunnel token** from Cloudflare (write-only — placeholder turns to `●●●●●● (configured)` after save).
   - Optionally toggle **Auto-start on boot (with supervisor)** so the tunnel survives backend restarts.
   - Click **Save configuration**.
3. Scroll to the **Google OAuth callback URIs** card. **Before** starting the tunnel, copy both URIs and add them to your Google Cloud Console OAuth 2.0 client (**APIs & Services → Credentials → your OAuth client → Authorized redirect URIs**):
   - `https://<hostname>/api/auth/google/callback` (SSO login)
   - `https://<hostname>/api/hub/google/oauth/callback` (Hub Gmail/Calendar integrations)
   - Skipping this step will break Google SSO for users arriving via the public URL.
4. In the **Tunnel Status** card, select **Named** in the mode dropdown and click **Start**. Within 10–15 seconds the badge will turn green (`Running`) and the public URL field will show your hostname.
5. Open `https://<hostname>` in a browser — you should see the Tsushin login page.

#### 22.5.4 Enabling remote access for a specific tenant

Even after the tunnel is running, no tenant can actually log in through the public URL until the Global Admin enables their `remote_access_enabled` flag. Two ways to do it:

**Option A — from `/system/remote-access` (fastest for bulk toggles):**
1. Scroll to the **Per-tenant entitlement** card at the bottom.
2. Find the tenant in the table and click the toggle in the **Remote Access** column. The toggle is optimistic (instant visual feedback with rollback on error).
3. The "Last changed" column updates with the admin's email. Both the global audit log and the tenant-scoped audit log record the change (`remote_access.tenant.enabled` or `remote_access.tenant.disabled`).

**Option B — from the tenant detail page:**
1. Navigate to **System Administration** → **Tenant Management** → click into the specific tenant.
2. Scroll to the **Remote Access** card and flip the toggle.
3. Same audit trail as Option A.

**What happens behind the scenes:**
- A user from an enabled tenant logs in at `https://<hostname>/auth/login` → normal login flow, normal JWT, normal dashboard.
- A user from a disabled tenant sees a banner on the login page: "Remote access is not enabled for this tenant. Contact your administrator." → 403 response, no JWT issued, `auth.remote_access.denied` written to their tenant audit log.
- Global admins (`user.tenant_id IS NULL`) always pass the gate — they can always reach the system via the public URL.
- **Internal network access is unaffected.** The gate only fires when the request's `Host` / `X-Forwarded-Host` header matches the configured `tunnel_hostname`. Requests coming in via `https://localhost` or direct to `tsushin-backend:8081` skip the gate entirely.

#### 22.5.5 Quick Tunnel (dev / demo)

For quick spot-checks you can skip the named-tunnel setup entirely:

1. `/system/remote-access` → **Tunnel Status** → mode dropdown = **Quick** → **Start**.
2. Within 30 seconds the public URL field shows a random `https://<words>.trycloudflare.com` URL.
3. Share that URL with the demo audience; it stays alive until you click **Stop** or restart the backend.
4. Per-tenant entitlement still applies.

Quick tunnels are intentionally unauthenticated at the Cloudflare layer — anyone with the URL can reach Tsushin's login page. The per-tenant gate + Tsushin login + (optionally) Google SSO are the only things protecting it. **Never use quick mode for production traffic.**

#### 22.5.6 Status, lifecycle, and troubleshooting

The Status card polls `GET /api/admin/remote-access/status` every 5 seconds while the tab is visible (it pauses when you switch away, per the `document.visibilityState` API). State values:

| State | Meaning |
|---|---|
| `stopped` | Subprocess is not running. Default state after boot if autostart is off. |
| `starting` | Subprocess is launching; readiness probe hasn't confirmed yet. |
| `verifying` | (Named mode, BUG-589) Local cloudflared has ≥1 HA connection, now probing `HEAD https://<tunnel_hostname>/api/health` to confirm the public hostname actually serves the app. |
| `running` | Subprocess is up, Cloudflare edge has ≥1 HA connection, AND the public hostname probe returned a non-5xx response. |
| `stopping` | Graceful stop in progress (SIGTERM → 10s → SIGKILL → 5s ladder). |
| `crashed` | Subprocess exited unexpectedly; supervisor may be about to restart. |
| `error` | Supervisor gave up after 3 restart attempts — manual intervention required. |
| `unavailable` | `cloudflared` binary not found in the backend container (should never happen with the shipped Dockerfile). |

Common errors surfaced in `last_error`:
- **"Named tunnel failed readiness probe (no HA connections in 15s)"** — the tunnel token is wrong, the hostname isn't bound to any route, or outbound QUIC/HTTPS is blocked by your firewall. Double-check the token and the Cloudflare Dashboard route.
- **"Named tunnel started but public hostname `<host>` is not serving the app (last HTTP status: 502)"** — BUG-589. Cloudflared is connected to the edge but the ingress rule points at the wrong target or the target container is down. Check the route's Service URL in the Cloudflare Dashboard (it should be `http://tsushin-proxy:80`, not `frontend:3030`), and confirm `tsushin-proxy` is healthy (`docker ps --filter name=tsushin-proxy`).
- **"Quick tunnel timed out waiting for URL"** — cloudflared couldn't reach the `trycloudflare.com` edge. Network / egress issue.
- **"Supervisor gave up after 3 restart attempts"** — cloudflared keeps crashing. Check `docker logs tsushin-backend | grep cloudflared` for the underlying error; typical causes: invalid token, revoked route, stale DNS record.

#### 22.5.7 Public vs gated endpoint policy

Remote Access exposes the same Tsushin app over a public hostname, so the safe posture is "public only when the route is intentionally bootstrap-, docs-, or webhook-related; everything else is gated." After the v0.6.0 hardening follow-up, the expected anonymous/public surface is:

- `GET /api/health` and `GET /api/readiness`
- Auth/bootstrap flows such as `GET /api/auth/setup-status`, `POST /api/auth/setup-wizard`, login, Google callback exchange, and explicit password-reset flows
- `GET /api/plans/` (public plan catalog)
- Inbound webhook receivers that do not use session auth and instead enforce their own signature/secret validation, such as `POST /api/webhooks/{id}/inbound`
- Static metadata/docs endpoints such as `/api/v1/openapi.json` and `/api/v1/docs`
- `GET /api/provider-instances/predefined-models`
- `POST /api/provider-instances/discover-models-raw` only before first-run provisioning (`needs_setup=true`)

The routes specifically tightened for public Remote Access are now gated as follows:

- `POST /api/provider-instances/discover-models-raw`: requires `org.settings.write` after the first user exists
- `GET /api/skills/available`: requires `agents.read`
- `GET /api/shell/beacon/version`: requires a valid active `ShellIntegration` API key in `X-API-Key`
- `GET /api/shell/beacon/download`: requires either `X-API-Key` for an active `ShellIntegration` or a valid signed-in session with `shell.read`
- `GET /api/ollama/health`: requires an authenticated session

One accepted exception remains: Playground audio/image asset URLs (`/api/playground/audio/{uuid}` and `/api/playground/images/{uuid}`) are capability URLs. They intentionally stay unauthenticated because browsers cannot attach bearer/session headers to `<audio>` and `<img>` fetches in the same way, and the UUID itself is treated as the unguessable bearer capability. The hardening pass did not change that behavior.

#### 22.5.8 Security considerations

- **Token at rest:** Fernet (AES-128-CBC + HMAC-SHA256) with a per-feature key that's envelope-wrapped by `TSN_MASTER_KEY`. Rotating `TSN_MASTER_KEY` without re-encrypting the token will cause `_load_config` to throw and the tunnel will refuse to start — document the rotation procedure in your runbook.
- **Token in transit:** never logged, never returned in any API response, never surfaced to the frontend beyond a boolean `tunnel_token_configured` flag.
- **Login gate:** enforced on both the password login path and the Google SSO exchange path. Host header spoofing from inside your LAN is possible but accepted — the gate is permissive (allows local access) by design, and your internal network is assumed to be trusted. External attackers can only reach the backend via the tunnel, which enforces the hostname upstream.
- **Global admin bypass:** intentional — the platform operator always needs a way in, even if every tenant is disabled.
- **Audit:** every config change fires `remote_access.config.updated` on `GlobalAdminAuditLog`. Tenant entitlement changes fire on BOTH the global stream and the tenant-scoped stream. Denied logins fire `auth.remote_access.denied` on the tenant-scoped stream with `severity=warning`.
- **Rotating the tunnel token:** paste a new token in the Config card and click Save. If the tunnel is currently running, the backend performs a stop→start cycle automatically (`reload_config()`).

#### 22.5.9 Disabling the feature

To fully disable remote access for every tenant without tearing the config down:

1. `/system/remote-access` → **Tunnel Status** → **Stop**.
2. (Optional) In **Tunnel Configuration**, uncheck **Feature enabled globally** → Save.

To restore it later, just click Start — the encrypted token and hostname are preserved.

---

## 23. Audit Logging & Compliance

**Primary sources:**
- `backend/services/audit_service.py` (563 lines) — `AuditService` class
- `backend/services/audit_retention_worker.py` — retention enforcement
- `backend/services/syslog_service.py` (335 lines) — RFC 5424 formatter + sender
- `backend/services/syslog_forwarder.py` (297 lines) — async queue + worker
- `models_rbac.py` — `GlobalAdminAuditLog`, `AuditEvent`

### 23.1 Event Types & Severity

`AuditService` exposes two logging entry points:

- **`log_action()`** (`audit_service.py:28-79`) — for global admin actions. Writes `GlobalAdminAuditLog` rows with fields: `global_admin_id`, `action` (e.g., `tenant.create`, `user.suspend`), `target_tenant_id`, `resource_type`, `resource_id`, `details_json`, `ip_address`, `user_agent`.
- **`log_event()` / `log_tenant_event()`** (`audit_service.py:302-326`, `:497-554`) — for tenant-scoped audit events written to `AuditEvent`. Default severity is `"info"`.

**Severity levels** (used in queries and filters, `audit_service.py:354-407`):

| Severity |
|---|
| `info` |
| `warning` |
| `critical` |

The audit-logs UI exposes the same three (plus "All Severities") — see §21.7.

**Action categories** (from the UI filter catalog, `audit-logs/page.tsx:40-66`): auth, agent, flow, contact, settings, security, shell, api_client, skill, mcp, team.

**Channels**: web, api, whatsapp, telegram, system.

### 23.2 Filtering, CSV Export, Retention

- Query API supports filtering by severity, action, channel, date range (`audit_service.py:338-407`).
- CSV export is implemented via Python `csv` + `io` (`audit_service.py:12-13`, `:476`) streaming rows to the client.
- Retention is enforced by `backend/services/audit_retention_worker.py` — a background worker that purges events older than the configured retention window.

### 23.3 Syslog Forwarding

Source files: `backend/services/syslog_service.py`, `backend/services/syslog_forwarder.py`.

- **Format:** RFC 5424 via `RFC5424Formatter` (`syslog_service.py:25`).
- **Transports:** UDP, TCP, TLS (Protocol selector in the UI — §21.7).
- **Facility:** Configurable per-tenant. Supported values exposed in UI: `1` User-level, `4` Auth, `10` Auth-priv, `13` Audit, `16-23` Local0–Local7 (`audit-logs/page.tsx:264-275`). Default facility when unset is `1` (`syslog_forwarder.py:75`).
- **TLS:** Encrypted CA cert, client cert, and client key stored on the tenant config, decrypted at forward time with namespaces `syslog_ca_cert_{tenant_id}`, `syslog_client_cert_{tenant_id}`, `syslog_client_key_{tenant_id}` (`syslog_forwarder.py:117-134`).
- **Delivery:** Non-blocking queue enqueue (`syslog_forwarder.py:31`) consumed by a background worker — `start_syslog_forwarder(engine, queue_size=10000, batch_size=50, poll_interval_ms=200)` (`syslog_forwarder.py:268-285`). Stopped via `stop_syslog_forwarder()` (`:291`).

---

## 24. Observability

### 24.1 Watcher dashboard tabs

Watcher is the frontend observability surface. Tabs per `README.md:178-188`:

| Tab | Purpose |
|---|---|
| **Dashboard** | KPIs, activity timeline, system performance, distribution charts. System Performance includes a **Semantic Search** badge driven by `GET /api/stats/memory`'s `agents_with_semantic_search / total_agents` aggregation (Active when all agents enabled, Partial when some, Disabled when none). |
| **Conversations** | Live conversation feed with filtering. |
| **Flows** | Flow execution tracking & status. |
| **Billing** | Token usage and cost analytics per agent/model. |
| **Security** | Sentinel threat events with severity filtering. |
| **Graph View** | Interactive system topology (agents, users, projects) with Dagre auto-layout, node expand/collapse, fullscreen mode. |

Access requires the `watcher.read` permission (`backend/migrations/add_rbac_tables.py:387-388`).

### 24.2 Prometheus metrics (`/metrics`)

The `/metrics` endpoint is registered in `backend/app.py:1314`:

```python
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
```

* Enabled by default; disable with `TSN_METRICS_ENABLED=false` (`backend/settings.py:139`).
* Optional bearer token for scraping: `TSN_METRICS_SCRAPE_TOKEN` (`backend/services/metrics_service.py:109`). When set, scrapers must present `Authorization: Bearer <token>`.
* Implemented by `backend/services/metrics_service.py`.

### 24.3 Health & readiness probes

| Endpoint | Purpose | Source |
|---|---|---|
| `GET /api/health` | Lightweight liveness probe — returns `{"status":"healthy"}` without external dependency checks. | `backend/api/routes.py:70` |
| `GET /api/readiness` | Readiness probe — checks PostgreSQL engine + connectivity. Returns **200** when all components healthy, **503** when any is degraded. Response body: `{"status":"ready"/"degraded", "postgresql":{...}}`. | `backend/api/routes.py:84-138` |

In Kubernetes, wire these to `livenessProbe` and `readinessProbe` respectively.

### 24.4 Token usage & cost tracking

* Watcher's **Billing** tab surfaces token usage and estimated cost per agent + per model.
* Cost estimation is driven by the **Model Pricing** settings (`backend/api/routes_model_pricing.py`, paths `/api/settings/model-pricing`, `/api/settings/model-pricing/{model_provider}/{model_name}`).
* Token counts are recorded as `AuditEvent` rows (`models_rbac.py:233-253`) and aggregated in the Analytics service (`backend/api/routes_analytics.py`).

---

## 25. Public API v1

All Public API v1 endpoints are mounted under `/api/v1/` via the aggregator router at `backend/api/v1/router.py`. OpenAPI/Swagger UI is available at `/docs`. Source: `backend/api/v1/router.py:1-23`, `README.md:228-236`.

If you generate an external client/SDK, fetch `http://<host>:8081/openapi.json` to a local file first and generate from that file. During the 2026-04-07 Ubuntu VM audit, file-based generation was more reliable than pointing code generators directly at the live URL.

### 25.1 Authentication

Two equivalent modes — choose whichever fits your client:

**Mode 1 — OAuth2 Client Credentials** (`backend/api/v1/routes_oauth.py:23`):

```bash
curl -X POST http://localhost:8081/api/v1/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET"
# → { "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600 }
# NOTE (BUG-535): The Content-Type header is required. Omitting it causes FastAPI to return
# 422 "Field required: grant_type" even though the field is present in the body.

curl -H "Authorization: Bearer <jwt>" http://localhost:8081/api/v1/agents
```

**Mode 2 — Direct API Key** (use the secret from `/api/clients` directly):

```bash
curl -H "X-API-Key: $TSN_API_CLIENT_SECRET" http://localhost:8081/api/v1/agents
```

The unified auth dependency (`backend/api/api_auth.py:46-80`) resolves both modes into an `ApiCaller` with `tenant_id`, `permissions`, and `rate_limit_rpm`.

### 25.2 Rate limiting

Every API-v1 response carries standard rate-limit headers (`backend/middleware/rate_limiter.py:192-215`):

| Header | Meaning |
|---|---|
| `X-RateLimit-Limit` | Maximum requests per minute for this caller. |
| `X-RateLimit-Remaining` | Remaining quota in the current window. |
| `X-RateLimit-Reset` | UNIX timestamp (seconds) when the window resets. |

On **429 Too Many Requests** (`backend/api/v1/schemas.py:174`) the same three headers are set; clients should back off until `X-RateLimit-Reset`.

Per-client `rate_limit_rpm` is stored on the `ApiClient` record (default 60 RPM; seeded regression clients may be provisioned at a higher limit, e.g. 120 RPM).

### 25.3 `/api/v1/*` endpoint reference

**OAuth** (`backend/api/v1/routes_oauth.py`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/oauth/token` | Client-credentials → bearer JWT. |

**Agents** (`backend/api/v1/routes_agents.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/agents` | List agents (paginated). |
| GET | `/api/v1/agents/{agent_id}` | Agent detail. |
| POST | `/api/v1/agents` | Create agent. |
| PUT | `/api/v1/agents/{agent_id}` | Update agent. |
| DELETE | `/api/v1/agents/{agent_id}` | Delete agent (refuses if it's the only one). |
| POST | `/api/v1/agents/{agent_id}/skills` | Attach a skill to an agent. |
| DELETE | `/api/v1/agents/{agent_id}/skills/{skill_type}` | Detach a skill. |
| PUT | `/api/v1/agents/{agent_id}/persona` | Assign / update persona. |

**Chat & Threads** (`backend/api/v1/routes_chat.py`)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/agents/{agent_id}/chat` | Send a message. Sync by default; append `?async=true` for queued delivery. SSE streaming supported. |
| GET | `/api/v1/queue/{queue_id}` | Poll status of an async chat request. Append `?include_scratchpad=true` to include the top-level agentic scratchpad for authorized clients; nested result scratchpads are always redacted. |
| GET | `/api/v1/agents/{agent_id}/threads` | List threads for an agent. |
| GET | `/api/v1/agents/{agent_id}/threads/{thread_id}/messages` | Fetch messages in a thread. |
| DELETE | `/api/v1/agents/{agent_id}/threads/{thread_id}` | Delete a thread. |

**Resources (read-only)** (`backend/api/v1/routes_resources.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/skills` | List built-in skills. |
| GET | `/api/v1/tools` | List sandboxed tools. |
| GET | `/api/v1/personas` | List personas. |
| GET | `/api/v1/security-profiles` | List Sentinel security profiles. |
| GET | `/api/v1/tone-presets` | List tone presets. |

**Flows** (`backend/api/v1/routes_flows.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/flows` | List flows. |
| POST | `/api/v1/flows` | Create flow. |
| GET | `/api/v1/flows/runs` | List all flow runs. |
| GET | `/api/v1/flows/runs/{run_id}` | Run detail. |
| POST | `/api/v1/flows/runs/{run_id}/cancel` | Cancel running flow. |
| GET | `/api/v1/flows/{flow_id}` | Flow detail. |
| PUT | `/api/v1/flows/{flow_id}` | Update flow. |
| DELETE | `/api/v1/flows/{flow_id}` | Delete flow. |
| GET | `/api/v1/flows/{flow_id}/steps` | List steps. |
| POST | `/api/v1/flows/{flow_id}/steps` | Add step. |
| PUT | `/api/v1/flows/{flow_id}/steps/{step_id}` | Update step. |
| DELETE | `/api/v1/flows/{flow_id}/steps/{step_id}` | Delete step. |
| POST | `/api/v1/flows/{flow_id}/execute` | Execute (202 Accepted, returns run_id). |

Notification-step note: API v1 validates notification configs on create and update. They must include a non-empty `recipient` or `recipients` field and a non-empty `message_template` or `content` field. Legacy `message` input is normalized to `message_template` before persistence.

**Hub** (`backend/api/v1/routes_hub.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/hub/integrations` | List integrations attached to tenant. |
| GET | `/api/v1/hub/integrations/{integration_id}` | Integration detail. |
| GET | `/api/v1/hub/integrations/...` (2 more) | Category / provider-filtered views. |
| POST | `/api/v1/hub/...` | Create/attach integration. |
| GET | `/api/v1/hub/providers` | List available provider types. |

**Studio (visual agent builder)** (`backend/api/v1/routes_studio.py`)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/v1/studio/agents/{agent_id}` | Load full builder graph (skills, tools, personas, channels, security). |
| PUT | `/api/v1/studio/agents/{agent_id}` | Atomic batch save. |
| POST | `/api/v1/studio/agents/{agent_id}/clone` | Clone agent. |

### 25.4 Tenant API reference (UI-facing, `/api/*`)

Tenant-scoped routes backing the frontend (require UI JWT). All routers are included in `backend/app.py:1239-1310`. One-liner summary of namespaces:

| Prefix | Route file | Purpose |
|---|---|---|
| `/api/agents*` | `routes_agents.py` | Tenant-scoped agent CRUD, memory, knowledge, skills |
| `/api/api-keys*` | `routes_api_keys.py` | AI-provider API-key management |
| `/api/audit-logs*` | `routes_audit.py` | Audit event browse + export |
| `/api/cache*` | `routes_cache.py` | Contact/memory cache admin |
| `/api/channel-health*` | `routes_channel_health.py` | Channel up/down monitoring |
| `/api/clients*` | `routes_api_clients.py` | Public-API client CRUD (UI) |
| `/api/commands*` | `routes_commands.py` | Slash-command registry |
| `/api/custom-skills*` | `routes_custom_skills.py` | Instruction + script + MCP-server custom skills |
| `/api/custom-tools*` | `routes_sandboxed_tools.py` | Sandboxed tool CRUD + execute |
| `/api/flows*` | `routes_flows.py` | Flow CRUD + runs |
| `/api/hub*` | `routes_hub.py` | Hub integrations (providers, channels, TTS) |
| `/api/integrations*` | `routes_integrations.py` | Test-connection endpoints |
| `/api/knowledge*` / `/api/agents/{id}/knowledge-base*` | `routes_knowledge*.py` | Semantic knowledge bases |
| `/api/mcp/*` | `routes_mcp_instances.py` | WhatsApp MCP instance lifecycle |
| `/api/playground/*` | `routes_playground.py` | Playground UI (threads, messages, documents, search, TTS) |
| `/api/projects*` | `routes_projects.py` | Studio Projects |
| `/api/scheduler*` | `routes_scheduler.py` | Scheduled flows |
| `/api/sentinel*` / `/api/sentinel-profiles*` / `/api/sentinel-exceptions*` | `routes_sentinel*.py` | Sentinel security |
| `/api/shell*` / `/api/beacon/*` | `routes_shell.py`, `shell_approval_routes.py`, `shell_websocket.py` | Shell skill + Beacon C2 |
| `/api/telegram/*` | `routes_telegram_instances.py` | Telegram bot instances |
| `/api/webhooks/{id}/inbound` | `routes_webhook_inbound.py` | Public HMAC-signed inbound webhook |
| `/api/webhooks*` | `routes_webhook_instances.py` | Tenant-scoped webhook instance CRUD |
| `/api/team*` | `routes_team.py` | Team member management |
| `/api/vector-stores*` | `routes_vector_stores.py` | External vector DB registration |

> **BUG-533 — Path correction notice:** Several paths that appear in older docs or conventions return 404. Use the actual paths listed below:
>
> | Old / expected path (404) | Actual working path |
> |---|---|
> | `GET /api/tone-presets` | `GET /api/tones` (UI-facing) or `GET /api/v1/tone-presets` (public API v1) |
> | `GET /api/security-profiles` | `GET /api/sentinel/profiles` |
> | `GET /api/skills` | `GET /api/custom-skills` (custom) or `GET /api/v1/skills` (system, public) |
> | `GET /api/knowledge-base` | `GET /api/agents/{id}/knowledge-base` (per-agent, not global) |
> | `GET /api/hub/providers` | `GET /api/provider-instances` |
> | `GET /api/slash-commands` | `GET /api/commands` |
>
> The `/api/*` namespace (UI-facing) is not versioned and is subject to change. For stable integrations, prefer the public `/api/v1/*` equivalents documented in §25.3.

A few illustrative endpoints (grepped verbatim from `backend/api/routes_*.py`):

| Method | Path | Source |
|---|---|---|
| GET | `/api/playground/agents` | `routes_playground.py` |
| POST | `/api/playground/chat` | `routes_playground.py` |
| GET | `/api/playground/memory/{agent_id}` | `routes_playground.py` |
| POST | `/api/playground/stream` | `routes_playground.py` |
| GET | `/api/audit-logs` | `routes_audit.py` |
| GET | `/api/audit-logs/export` | `routes_audit.py` |
| POST | `/api/clients` | `routes_api_clients.py` |
| POST | `/api/clients/{client_id}/rotate-secret` | `routes_api_clients.py` |
| GET | `/api/commands/autocomplete` | `routes_commands.py` |
| POST | `/api/commands/execute` | `routes_commands.py` |
| POST | `/api/webhooks/{webhook_id}/inbound` | `routes_webhook_inbound.py` |
| GET | `/api/settings/model-pricing` | `routes_model_pricing.py` |

### 25.5 Admin API reference

**Tenants** (`backend/api/routes_tenants.py`, prefix `/api/tenants`, global-admin only):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tenants` | List tenants (paginated). |
| POST | `/api/tenants` | Create tenant. |
| GET | `/api/tenants/current` | Current caller's tenant. |
| GET | `/api/tenants/{tenant_id}` | Tenant detail. |
| PUT | `/api/tenants/{tenant_id}` | Update tenant. |
| DELETE | `/api/tenants/{tenant_id}` | Soft-delete tenant. |
| GET | `/api/tenants/{tenant_id}/stats` | Tenant usage statistics. |

**System configuration** (routers mounted in `backend/app.py`):

* `plans_router` → `/api/plans*` — Subscription plan management.
* `sso_config_router` → `/api/sso-config*` — Per-tenant Google SSO config (`tenant_sso_config` table).
* `global_users_router` → `/api/global/users*` — Cross-tenant user administration.
* `system_ai_router` → `/api/system/ai*` — System-wide AI provider config.
* `syslog_config_router` → `/api/tenants/*/syslog*` — Per-tenant syslog forwarding (`tenant_syslog_config` table, `models_rbac.py:309-344`).

Source: `backend/app.py:1270-1309`.

### 25.6 Webhooks (trigger-based, HMAC-signed)

The webhook integration is now modeled as a trigger (`backend/channels/webhook/trigger.py`) even though the public inbound endpoint remains `POST /api/webhooks/{slug}/inbound` (numeric ids still work as a legacy fallback).

**Inbound** — external systems POST signed events to `POST /api/webhooks/{slug}/inbound` (`backend/api/routes_webhook_inbound.py`). Events are enqueued into `MessageQueue`; `QueueWorker._handle_webhook` routes them to the target agent.

**Outbound** — agent responses are HMAC-signed and POSTed to the webhook's `callback_url` via `Trigger.notify_external_system(...)`. Signing uses `hmac.new(secret, signed_input, sha256)` (`channels/webhook/trigger.py`). Outbound requests carry custom headers:

* `X-Tsushin-Webhook-Id: <int>`
* `X-Tsushin-Signature: <hex sha256 HMAC>`
* (plus timestamp fields — see `channels/webhook/trigger.py:114-121`)

Callback URLs are subject to SSRF policy enforcement (`channels/webhook/trigger.py`). The `api_secret_encrypted` column on `WebhookIntegration` is Fernet-encrypted using a per-tenant-derived webhook key (`get_webhook_encryption_key`, `channels/webhook/trigger.py`). Webhooks can be configured as inbound-only (outbound disabled) by leaving `callback_url` empty, and their canonical management surface is `/api/triggers/webhook/*` plus `GET /api/triggers`.

---

## 26. Slash Commands (System-Wide Catalog)

**Registry source:** `backend/models.py:1197` (`SlashCommand` model) + seeded rows in `backend/db.py` (the `_system` tenant holds all built-in commands).
**Handler source:** `backend/services/slash_command_service.py`.

Seed entries (`backend/db.py:830-1259`, all `tenant_id="_system"`, `handler_type="built-in"`):

| Category | Command | Pattern | Description |
|---|---|---|---|
| agent | `invoke` | `^/invoke\s+(.+)$` | Invoke another agent (EN) |
| agent | `invocar` | (PT alias) | Same, Portuguese |
| project | `project enter` | `^/project enter …$` | Enter project context |
| project | `project exit` | … | Exit project context |
| project | `project list` | … | List projects |
| project | `project info` | … | Current project info |
| project | `projeto entrar` / `projeto sair` / `projeto listar` | PT aliases | |
| agent | `agent info` | | Show active agent |
| agent | `agent skills` | | List agent skills |
| agent | `agent list` | | List tenant agents |
| memory | `memory clear` | `^/memory\s+clear$` | Clear conversation memory |
| memory | `memoria limpar` | PT alias | |
| memory | `memory status` | `^/memory\s+status$` | Show memory statistics |
| memory | `facts list` | `^/facts\s+list$` | List learned facts |
| system | `commands` | `^/commands$` | List all commands (aliases: `help`, `?`) |
| system | `help` | `^/help\s*(.*)$` | Get help on a command |
| system | `status` | `^/status$` | Show agent/channel/project context |
| system | `shortcuts` | `^/shortcuts$` | Keyboard shortcuts (alias: `keys`) |
| system | `tools` | `^/tools$` | List available tools (alias: `t`) |
| system | `ferramentas` | PT alias | |
| tool | `tool` | `^/tool\s+(\w+)\s*(.*)$` | Execute a tool |
| tool | `ferramenta` | PT alias | |
| tool | `inject` | `^/inject\s*(.*)$` | Inject tool output into conversation (alias: `recall`) |
| tool | `inject list` | `^/inject\s+list$` | List buffered executions |
| tool | `inject clear` | `^/inject\s+clear$` | Clear inject buffer |
| tool | `injetar` | PT alias | |
| flows | `flows run` | `^/flows\s+run\s+(.+)$` | Execute a workflow by name or ID |
| flows | `flows list` | `^/flows\s+list$` | List workflows |
| scheduler | `scheduler info` | `^/scheduler\s+info$` | Provider/account info (alias: `sched info`) |
| scheduler | `scheduler list` | `^/scheduler\s+list …` | List events (today, tomorrow, week, month, date) |
| scheduler | `scheduler create` | `^/scheduler\s+create\s+(.+)$` | NL event creation with recurrence/duration |
| scheduler | `scheduler update` | see regex | Update event name/description |
| scheduler | `scheduler delete` | | Delete an event |
| email | `email inbox` | `^/email\s+inbox(?:\s+(\d+))?$` | List recent emails from inbox (zero AI tokens). Optional count param. |
| email | `email search` | `^/email\s+search\s+"?(.+?)"?$` | Search emails with Gmail query syntax (zero AI tokens) |
| email | `email unread` | `^/email\s+unread$` | Show unread email count and list |
| email | `email info` | `^/email\s+info$` | Show Gmail configuration and connection status |
| email | `email list` | `^/email\s+list(?:\s+(\w+))?$` | List emails with optional filter: `unread`, `today`, or a count |
| email | `email read` | `^/email\s+read\s+(.+)$` | Read full email by ID or list index |
| search | `search` | `^/search\s+"?(.+?)"?$` | Web search (zero AI tokens, uses Brave Search) |
| shell | `shell` | `^/shell\s+(?:([\w\-@]+):)?(.+)$` | Execute shell command on a registered beacon host |
| thread | `thread end` | `^/thread\s+end$` | End the active conversation thread |
| thread | `thread list` | `^/thread\s+list$` | List active conversation threads for this sender |
| thread | `thread status` | `^/thread\s+status$` | Show current thread details (objective, progress, time) |

**Total: 37 built-in commands** (26 seeded in `db.py` + 11 added via migrations).

**Tenant customization:** `SlashCommand.tenant_id` supports per-tenant overrides; the service query unions the tenant and `_system` rows (`slash_command_service.py:58-73`). Tenant custom commands are managed under **Settings → Prompts & Patterns → Slash Commands** (§21.11).

**Handler dispatch:** `SlashCommandService` (`slash_command_service.py:20`) matches the incoming text against each command's regex `pattern`, filters by `language_code`, and routes to the matching built-in handler. If a command resolves to a sandboxed tool name, execution is delegated through `_parse_tool_arguments` → `ToolDiscoveryService`. Flag-style args (`--target`) are rejected for sandboxed tools (`:1668`) — use `param=value` syntax instead.

**`/help` behavior** (`slash_command_service.py:1017-1086`): `/help` lists all commands grouped by category; `/help <command>` shows syntax + examples for one command; `/help all` renders every command's first-line usage.

### 26.1 Usage Examples by Category

#### Agent commands
```
/invoke SecurityBot              — Switch to SecurityBot agent
/agent info                      — Show current active agent details
/agent skills                    — List skills enabled for the active agent
/agent list                      — List all agents in the tenant
```

#### Project commands
```
/project enter MyProject         — Enter project context
/project exit                    — Exit current project context
/project list                    — List all projects
/project info                    — Show current project details
```

#### Memory commands
```
/memory clear                    — Clear conversation memory for current sender
/memory status                   — Show memory statistics (ring buffer, semantic, facts)
/facts list                      — List all learned facts about the current user
```

#### Email commands (requires Gmail skill enabled)
```
/email inbox                     — Show last 10 emails
/email inbox 20                  — Show last 20 emails
/email unread                    — Show unread emails
/email search "from:boss subject:urgent"  — Search with Gmail query syntax
/email read 3                    — Read email #3 from the last list
/email info                      — Show Gmail connection status
/email list unread               — List filtered by unread
/email list today                — List today's emails
```

#### Search commands (requires web_search skill)
```
/search "kubernetes best practices 2026"  — Web search via Brave Search
```

#### Shell commands (requires shell skill + registered beacon)
```
/shell ls -la                    — Execute on default target beacon
/shell myserver:df -h            — Execute on specific host "myserver"
/shell @all:uptime               — Execute on all registered beacons
```

Shell command requests are rate-limited per beacon/integration (60 commands/minute by default in the shared shell security service), and the HTTP beacon endpoints apply additional throttles. Registration and version checks are capped at 12 requests/minute per beacon, beacon-package downloads are capped at 6 requests/minute per beacon or signed-in user, check-ins get 3x burst headroom over the configured poll cadence (clamped to 30-360 RPM), and command-result posts get 8x headroom (clamped to 60-480 RPM).

#### Thread commands
```
/thread status                   — Show current thread objective, progress, time
/thread list                     — Show all active threads for this sender
/thread end                      — End the current active thread
```

#### Tool commands (sandboxed — see §9.4 for full parameter reference)
```
/tool nmap quick_scan target=scanme.nmap.org
/tool dig lookup domain=google.com record_type=MX
/tool nuclei start_scan url=http://testphp.vulnweb.com
/tool httpx probe target=https://github.com
/tool subfinder scan domain=github.com
/tool katana crawl target=https://example.com depth=2
/tool whois_lookup lookup domain=github.com
/tool webhook get url=https://api.github.com/users/octocat
/tool sqlmap scan target=http://testphp.vulnweb.com/listproducts.php?cat=1
```

#### Inject commands (buffer tool output for conversation context)
```
/inject                          — Inject last tool output into conversation
/inject list                     — List buffered tool executions
/inject clear                    — Clear inject buffer
```

**Shell → `/inject` integration (BUG-510, 2026-04-10):** `/shell` executions are now visible to `/inject`. Fire-and-forget `/shell` writes a **pending stub** tagged `source='shell_command'` with the beacon command id stored in metadata; `wait_for_result=True` calls buffer the final stdout/stderr immediately. On every `/inject list` or `/inject <id>` call, `SlashCommandService._resolve_pending_shell_executions` pulls updated results via `ShellCommandService.get_command_result` for any pending shell entries (capped at 10 per call) and rewrites their buffered output once the beacon marks the command `completed`/`failed`/`timeout`. Pending entries render with a `[pending]` suffix in `to_reference_string()`.

#### Flow commands
```
/flows list                      — List all workflows
/flows run "Daily Report"        — Execute a workflow by name
/flows run 42                    — Execute a workflow by ID
```

#### Scheduler commands
```
/scheduler info                  — Show calendar provider and account info
/scheduler list today            — List today's events
/scheduler list week             — List this week's events
/scheduler list 2026-04-15       — List events for a specific date
/scheduler create "Team standup tomorrow at 9am, recurring weekdays"
/scheduler update 42 name="Updated Standup"
/scheduler delete 42             — Delete event by ID
```

#### System commands
```
/commands                        — List all available commands (aliases: /help, /?)
/help                            — General help
/help email                      — Help for email commands
/status                          — Show agent/channel/project context
/tools                           — List available sandboxed tools
/shortcuts                       — Show keyboard shortcuts
```

---

## 27. CLI & Tester MCP

**Source:** `backend/tester-mcp/README.md`, `backend/tester-mcp/main.go`

The Tester MCP is a containerized Go WhatsApp bridge dedicated to QA. It is configured with its own phone number and runs alongside production MCP containers on `tsushin-network`.

> **Fresh-install note (BUG-537):** The tester MCP container is **not bundled** in the default compose stack (`docker-compose.yml`). On a fresh install, `GET /api/mcp/instances/tester/status` returns `container_state: "not_found"` and Hub → Communication → WhatsApp is empty. To provision a tester instance manually:
> 1. Navigate to **Hub → Communication → WhatsApp**.
> 2. Click **+ New Instance** and create a new runtime WhatsApp instance.
> 3. Assign it a dedicated QA phone number (must differ from all tenant agent numbers).
> 4. Scan the QR code to authenticate.
> 5. The backend will automatically recognise the active tester instance for `/api/mcp/instances/tester/*` controls.
> 6. Use `POST http://localhost:8088/api/send` (if the legacy compose tester is present) or call the runtime instance API for round-trip test sends.

**Default port:** `8088` (host) → `8080` (container).

**Env vars:**

| Variable | Purpose | Default |
|---|---|---|
| `PHONE_NUMBER` | Tester's WhatsApp phone number | — |
| `PORT` | Container-internal port | 8080 |

**HTTP endpoints** (`tester-mcp/README.md:48-53`):

| Method + Path | Purpose |
|---|---|
| `GET /api/health` | Health check |
| `POST /api/send` | Send a WhatsApp message |
| `POST /api/download` | Download media |
| `GET /api/qr-code` | Get QR code for initial auth |

**Authentication:** Bearer token on `Authorization: Bearer <api_secret>` (per project conventions; exact secret provisioning is container-specific — see the tester container's env).

**Hub visibility:** Hub now shows runtime tester instances in the main WhatsApp list, while the dedicated **QA Tester** controls backed by `/api/mcp/instances/tester/*` resolve the current tester target for QR/auth/restart actions. Those controls prefer a legacy/compose tester container when present and otherwise target the tenant's active runtime tester instance.

**Stdio launcher baseline:** The tenant toolbox base image ships `uvx`, and the Hub stdio/MCP launcher guidance is aligned to that shipped runtime. Use approved launchers such as `uvx` rather than assuming host-local package managers inside the backend container.

**Tester vs. tenant agent separation:** the tester is a dedicated QA bridge, not a tenant-managed production instance. For meaningful end-to-end validation, the tester and the tenant agent must authenticate with different WhatsApp accounts/phone numbers. If the same phone number is reused, `/api/mcp/instances/tester/status` and `/api/mcp/instances/{id}/health` now surface warning strings, and tenant-agent creation is rejected when the requested number is already in use by an authenticated tester or another WhatsApp MCP instance.

**Send-message example:**

```bash
curl -X POST http://localhost:8088/api/send \
  -H "Authorization: Bearer <api_secret>" \
  -H "Content-Type: application/json" \
  -d '{"recipient": "<msisdn_without_plus>", "message": "<test_command>"}'
```

**Sandboxed tool command format** (supported over this channel — see §26):
- Format: `/tool <tool_name> <command_name> param=value`
- Example: `/tool nmap quick_scan target=scanme.nmap.org`
- Example: `/tool dig lookup domain=google.com`
- Note: command-line flags like `--target` are **not** supported by the sandboxed-tool parser; use `param=value`.

**Round-trip verification pattern** (used by regression tests):
1. Tester sends via `POST /api/send` → verify tester logs show `Message sent true`.
2. Agent MCP container logs show `STORAGE SUCCESS`.
3. Wait ~30-60 s for LLM processing + conversation delay.
4. Tester logs show an inbound arrow from the bot's LID number.
5. If silent, inspect backend logs for `generate|gemini|send` lines.

**Validation prerequisite:** do not scan the tester QR and the tenant agent QR with the same WhatsApp account. That topology can look healthy in status checks while making tester-to-agent round-trip validation impossible.

## 28. Troubleshooting

### 28.1 Container won't start

```bash
docker compose logs backend                 # Read the stack trace
docker inspect tsushin-backend --format='{{.State.Health.Status}}'
lsof -i :8081                               # Port collision?
curl http://localhost:8081/api/health       # Liveness
curl http://localhost:8081/api/readiness    # DB connectivity
```

Source: `docs/docker.md:260-272`.

### 28.2 WhatsApp session dropped / QR re-auth loop

Symptoms: the MCP container for a WhatsApp number keeps regenerating QR codes in `docker logs mcp-agent-tenant_<id>`.

Cause: The `tsushin-network` bridge was torn down (historically via `docker compose down`), severing the WebSocket to `whatsmeow`.

Fix:

```bash
docker restart mcp-agent-tenant_<id>    # Restart container
# Then re-scan QR on the linked phone.
```

Prevention: never `docker compose down` for routine rebuilds — use `docker compose build --no-cache <service>` followed by `docker compose up -d <service>` instead. The compose file declares `tsushin-network` as `external: true`, so the network survives, but the compose services still restart if you tear them down.

### 28.3 Database issues

```bash
docker exec -it tsushin-postgres psql -U tsushin -d tsushin -c "\dt"     # List tables
docker exec -it tsushin-postgres psql -U tsushin -d tsushin              # Interactive shell
```

Source: `docs/docker.md:275-282`.

**Playground search note:** Postgres deployments do not use SQLite FTS5. Tsushin now falls back cleanly to LIKE-based conversation search on Postgres and rolls back failed search probes before continuing, so a failed search should not poison the rest of the request transaction.

### 28.4 Memory / slow model loading

The backend lazy-loads `sentence-transformers` models; first boot can be slow. Pre-warm:

```bash
docker exec tsushin-backend python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

Or raise Docker Desktop memory limit to ≥ 6 GB. Source: `docs/docker.md:286-294`.

### 28.5 Permission issues on bind mounts (Linux)

```bash
sudo chown -R 1000:1000 backend/data/
sudo chown -R 1000:1000 logs/
```

Source: `docs/docker.md:298-301`.

### 28.6 Disk space

Builds accumulate layers and BuildKit cache. Prune periodically:

```bash
docker system df                        # Report
docker system prune -af --volumes=false # KEEPS named volumes (Postgres)
docker builder prune -af                # Clear BuildKit cache
```

Never use `--volumes` in prune — that destroys `tsushin-postgres-data`.

### 28.7 Worktree Docker data mismatch

If you start Docker from a git worktree (e.g. `~/.claude-worktrees/...`), the empty `backend/data/` inside the worktree will be bind-mounted, making all tenant data appear missing. The fix: **always** run `docker compose` from the main repository clone. If you did start from a worktree, `docker stop tsushin-backend tsushin-frontend && docker rm tsushin-backend tsushin-frontend` and restart from the canonical path.

Note: Postgres data lives in the `tsushin-postgres-data` named volume and is NOT affected by working directory. Only ChromaDB vectors and per-MCP-instance data in `backend/data/` are at risk.

---

## 29. Appendix A: Complete Environment Variable Reference

All variables accept legacy (non-prefixed) aliases where noted. Resolution order (per `backend/settings.py:27-57`): new (`TSN_*`) name → legacy name → default.

### A.1 Application

| Variable | Default | Purpose | Legacy alias | Source |
|---|---|---|---|---|
| `TSN_APP_HOST` | `127.0.0.1` (Docker sets `0.0.0.0`) | Bind address for FastAPI. | `APP_HOST` | `settings.py:61` |
| `TSN_APP_PORT` | `8081` | Backend HTTP port. | `APP_PORT` | `settings.py:62` |
| `TSN_BACKEND_URL` | `http://{APP_HOST}:{APP_PORT}` | Absolute backend URL (for OAuth callbacks). | `BACKEND_URL` | `settings.py:66` |
| `TSN_FRONTEND_URL` | `http://localhost:3030` | Absolute frontend URL. | `FRONTEND_URL` | `settings.py:67` |
| `TSN_STACK_NAME` | `tsushin` | Naming prefix for compose services, volumes, and runtime-created MCP/toolbox/vector-store containers. | — | `install.py:204-205`, `docker-compose.yml:24,49,92,197,269-283`, `services/mcp_container_manager.py:979-980`, `services/toolbox_container_service.py:59-61`, `services/vector_store_container_manager.py:47-49` |
| `FRONTEND_PORT` | `3030` | Host port mapped to frontend. | — | `docker-compose.yml:181` |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8081` | Frontend build-time API URL. | — | `docker-compose.yml:178` |

### A.2 Database & storage paths

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `DATABASE_URL` | `sqlite:///{INTERNAL_DB_PATH}` | SQLAlchemy URL. Compose sets PostgreSQL URL. | `settings.py:87` |
| `POSTGRES_PASSWORD` | (required in compose) | PG password for compose; also used inside `DATABASE_URL`. | `docker-compose.yml:28,123` |
| `TSN_INTERNAL_DB_PATH` | `./data/agent.db` | Legacy SQLite path (rollback + MCP reader). | `settings.py:86` |
| `TSN_MCP_MESSAGES_DB_PATH` | *(empty, optional since Phase 9)* | Legacy single-watcher DB; multi-watcher is now default. | `settings.py:88` |
| `TSN_WORKSPACE_DIR` | `./data/workspace` | Per-tenant skill workspaces. | `settings.py:91` |
| `TSN_CHROMA_DIR` | `./data/chroma` | ChromaDB persistence. | `settings.py:92` |
| `TSN_BACKUPS_DIR` | `./data/backups` | Backup output. | `settings.py:93` |
| `HOST_BACKEND_DATA_PATH` | (required in compose) | **Absolute host path to `backend/data`**, used by MCP containers for Docker-in-Docker bind mounts. | `docker-compose.yml:134`, `services/toolbox_container_service.py:114`, `services/mcp_container_manager.py:234` |

### A.3 Logging

| Variable | Default | Purpose | Legacy | Source |
|---|---|---|---|---|
| `TSN_LOG_FILE` | `logs/tsushin.log` | Log file path. | `LOG_FILE` | `settings.py:96` |
| `TSN_LOG_LEVEL` | `INFO` | Root log level. | `LOG_LEVEL` | `settings.py:97` |
| `TSN_LOG_FORMAT` | `text` | `text` or `json` (structured logs for K8s). | — | `settings.py:98` |

**Notable emitted log lines** (useful grep patterns for operators):

| Pattern | Purpose | Source |
|---|---|---|
| `🤖 AIClient.generate(): provider=…` | Every LLM call records provider + model + operation type. | `backend/agent/ai_client.py:377` |
| `🔍 Web search: provider=…, query=…` | Every web search records which provider (Brave / SerpAPI / Tavily / etc.) handled the query. Query is truncated to 120 chars. Emitted from all three search code paths (slash command, skill, legacy tool). v0.6.1 BUG-9. | `backend/services/search_command_service.py:146`, `backend/agent/skills/search_skill.py:210`, `backend/agent/tools/search_tool.py:62` |
| `⚡ Emitted agent_processing: agent=…, status=start/end, listeners=…` | Watcher activity WebSocket emits. `listeners=0` means no Graph View is subscribed for that tenant; `listeners≥1` means the Graph View glow will fire on the node. | `backend/services/watcher_activity_service.py` |
| `⚡ Graph View WS registered: tenant=…, total=…` | A new browser subscribed to `/ws/watcher/activity`. | `backend/api/watcher_activity_websocket.py` |

### A.4 Security / Auth

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `JWT_SECRET_KEY` | (required) | HMAC key for JWTs. Generate with `secrets.token_urlsafe(32)`. | `auth_utils.py:26`, `docker-compose.yml:137` |
| `TSN_MASTER_KEY` | (required for SEC-006) | Fernet master key for envelope-encrypting per-tenant encryption keys stored in DB. Generate with `Fernet.generate_key()`. | `services/encryption_key_service.py:42`, `migrations/wrap_encryption_keys.py:66` |
| `TSN_CORS_ORIGINS` | `*` | Comma-separated allowed origins. | `app.py:1108` |
| `TSN_AUTH_RATE_LIMIT` | `30/minute` on local `disabled`/`selfsigned` installs unless overridden | Login throttle policy. Installer writes this explicitly for local workflows; production can override it. | `install.py:267-269`, `install.py:918`, `docker-compose.yml:123` |
| `TSN_TRUSTED_PROXY_HOSTS` | `127.0.0.1,::1` | X-Forwarded-For proxy allowlist. | `app.py:1138` |
| `TSN_ENABLE_HSTS` | *(unset)* | Set `1`/`true` to emit HSTS header. | `app.py:1172` |
| `TSN_AUTH_RATE_LIMIT` | `5/minute` on public HTTPS installs, `30/minute` on `disabled` / `selfsigned` installs | Default auth throttle applied to login and related auth endpoints unless a more specific override is present. | `install.py:217-223`, `auth_routes.py:95-100` |
| `TSN_DISABLE_AUTH_RATE_LIMIT` | `false` | QA/dev escape hatch that effectively disables auth throttling by swapping in a very high limit. Do not enable on public production installs. | `install.py:226-228`, `auth_routes.py:81-94` |
| `TSN_SSL_MODE` | *(unset)* | When unset/`off`/`none`/`disabled`, session cookie `secure` flag is OFF. | `auth_routes.py:51` |
| `GOOGLE_SSO_CLIENT_ID` / `TSN_GOOGLE_SSO_CLIENT_ID` | `""` | Google SSO OAuth client ID (platform-wide). | `settings.py:77` |
| `GOOGLE_SSO_CLIENT_SECRET` / `TSN_GOOGLE_SSO_CLIENT_SECRET` | `""` | Platform-wide SSO secret. | `settings.py:78` |
| `TSN_GOOGLE_SSO_REDIRECT_URI` | `{BACKEND_URL}/api/auth/google/callback` | SSO callback URL. | `settings.py:79-83` |
| `TSN_GOOGLE_OAUTH_REDIRECT_URI` | `{BACKEND_URL}/api/hub/google/oauth/callback` | Gmail/Calendar integration OAuth callback. | `settings.py:70-74` |

### A.5 Secret backend (GCP Secret Manager)

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_SECRET_BACKEND` | `env` | `env` or `gcp`. | `services/secret_provider.py:304` |
| `TSN_GCP_PROJECT_ID` | *(required when `=gcp`)* | GCP project for Secret Manager. | `settings.py:142`, `services/secret_provider.py:169` |
| `TSN_GCP_SECRET_PREFIX` | `tsushin` | Prefix applied to secret names. | `settings.py:143` |
| `TSN_GCP_SECRET_VERSION` | `latest` | Secret version to read. | `services/secret_provider.py:171` |
| `TSN_GCP_SECRET_CACHE_TTL` | `300` | Cache TTL (seconds). | `settings.py:144` |

### A.6 Container runtime (Docker / Kubernetes)

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_CONTAINER_RUNTIME` | `docker` | `docker` or `kubernetes`. | `services/container_runtime.py:1772` |
| `TSN_K8S_NAMESPACE` | `tsushin` | K8s namespace for spawned workloads. | `settings.py:147` |
| `TSN_K8S_IMAGE_PULL_POLICY` | `IfNotPresent` | `Always`, `IfNotPresent`, `Never`. | `settings.py:148` |
| `DOCKER_HOST` | `tcp://docker-socket-proxy:2375` (in compose) | Docker API endpoint (proxied). | `docker-compose.yml:115` |

### A.7 Observability

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_METRICS_ENABLED` | `true` | Enable `/metrics` Prometheus endpoint. | `settings.py:139` |
| `TSN_METRICS_SCRAPE_TOKEN` | *(unset)* | Bearer token required to scrape `/metrics` if set. | `services/metrics_service.py:109` |

### A.8 Watcher / MCP workers

| Variable | Default | Purpose | Legacy | Source |
|---|---|---|---|---|
| `TSN_POLL_INTERVAL_MS` | `3000` | MCP watcher poll interval (ms). | `POLL_INTERVAL_MS` | `settings.py:101` |
| `TSN_WHATSAPP_CONVERSATION_DELAY_SECONDS` | `5` | Delay before responding on WhatsApp (debounce). | `WHATSAPP_CONVERSATION_DELAY_SECONDS` | `settings.py:102-104` |
| `TSN_WATCHER_MAX_CATCHUP_SECONDS` | `300` | Max look-back window after rebuild. | `WATCHER_MAX_CATCHUP_SECONDS` | `settings.py:105-107` |

### A.9 OAuth token-refresh worker

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_OAUTH_REFRESH_POLL_MINUTES` | `30` | Worker poll cadence. | `settings.py:110-112` |
| `TSN_OAUTH_REFRESH_THRESHOLD_HOURS` | `24` | Refresh tokens within this window. | `settings.py:113-115` |
| `TSN_OAUTH_REFRESH_MAX_RETRIES` | `3` | Max refresh attempts. | `settings.py:116-118` |
| `TSN_OAUTH_REFRESH_RETRY_DELAY` | `5` | Base seconds for exponential backoff. | `settings.py:119-121` |

### A.10 Stale flow / conversation cleanup

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_STALE_FLOW_THRESHOLD_SECONDS` | `7200` (2 h) | Mark flow stale after this age. | `settings.py:124-126` |
| `TSN_STALE_FLOW_CHECK_INTERVAL_SECONDS` | `300` (5 min) | Cleanup check cadence. | `settings.py:127-129` |
| `TSN_STALE_CONVERSATION_THRESHOLD_SECONDS` | `3600` (1 h) | Mark conversation stale. | `settings.py:130-132` |

### A.11 Channel health & circuit breaker

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_CHANNEL_HEALTH_CHECK_INTERVAL` | `30` | Health-check cadence (seconds). | `settings.py:204` |
| `TSN_CHANNEL_HEALTH_ENABLED` | `true` | Enable channel-health worker. | `settings.py:207` |
| `TSN_CHANNEL_CB_FAILURE_THRESHOLD` | `3` | CB trips after N consecutive failures. | `settings.py:205` |
| `TSN_CHANNEL_CB_RECOVERY_TIMEOUT` | `60` | CB half-open after N seconds. | `settings.py:206` |

### A.12 Misc / integrations (grepped from codebase)

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `TSN_CB_QUEUE_ENABLED` | `true` | Enable circuit-breaker queue on router. | `agent/router.py:1297` |
| `THREAD_ABSOLUTE_MAX_TURNS` | `25` | Hard cap on turns per thread. | `agent/router.py:2748` |
| `THREAD_MAX_MESSAGES_PER_MINUTE` | `15` | Per-thread throttle. | `agent/router.py:2767` |
| `THREAD_MAX_DURATION_MINUTES` | `30` | Thread auto-close. | `agent/router.py:2794` |
| `TTS_CLEANUP_DELAY_SECONDS` | `5` | Delay before deleting TTS audio. | `agent/router.py:2415` |
| `CONTAMINATION_PATTERNS_EXTRA` | `""` | Extra regex patterns for Sentinel contamination detector. | `agent/contamination_detector.py:54` |
| `QA_PHONE_NUMBER` | `""` | Allowlist phone for QA tester. | `app.py:430` |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Ollama endpoint from inside container. | `agent/ai_client.py:205`, `db.py:1339` |
| `GROQ_API_KEY` / `GROK_API_KEY` / `ELEVENLABS_API_KEY` | `""` | Pass-through env for providers not configured via Hub. | `docker-compose.yml:149-151` |
| `ASANA_ENCRYPTION_KEY` | `""` | Fernet key for Asana integration. | `docker-compose.yml:144`, `migrations/add_service_encryption_keys.py:164` |
| `ASANA_REDIRECT_URI` | `http://localhost:3030/hub/asana/callback` | Asana OAuth callback. | `api/routes_hub.py:153` |
| `TELEGRAM_ENCRYPTION_KEY` | *(unset)* | Fernet key for Telegram bot token encryption. | `services/telegram_bot_service.py:40` |
| `SERPAPI_KEY` / `GOOGLE_FLIGHTS_API_KEY` | *(unset)* | Google Flights via SerpAPI. | `hub/providers/google_flights_provider.py:74` |
| `DISCORD_PUBLIC_KEY` / `DISCORD_PUBLIC_KEY_{id}` | *(unset)* | Discord interaction-verification pubkey(s). | `api/routes_channel_webhooks.py:244` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM_EMAIL` / `SMTP_USE_TLS` | *(unset / 587 / "" / "" / noreply@tsushin.io / true)* | Outbound email. | `services/email_service.py:119-127` |
| `APP_NAME` | `Tsushin` | Branding in transactional emails. | `services/email_service.py:135` |

Shell-Beacon agent (separate binary installed on endpoints, not the server):

| Variable | Purpose | Source |
|---|---|---|
| `TSUSHIN_SERVER_URL` | Beacon → server URL. | `shell_beacon/config.py:173` |
| `TSUSHIN_API_KEY` | Beacon auth key. | `shell_beacon/config.py:175` |
| `TSUSHIN_POLL_INTERVAL` / `TSUSHIN_SHELL` / `TSUSHIN_TIMEOUT` / `TSUSHIN_WORKING_DIR` / `TSUSHIN_LOG_LEVEL` / `TSUSHIN_LOG_FILE` / `TSUSHIN_AUTO_UPDATE` | Beacon config. | `shell_beacon/config.py:179-197` |

**Fresh-install note — self-signed HTTPS and Shell Beacons.** The beacon uses normal TLS verification through Python `requests`; it does not automatically bypass trust failures the way a browser automation session can. If `TSUSHIN_SERVER_URL` points at an installer-generated self-signed HTTPS endpoint, the beacon host must trust that certificate (or trust the issuing CA) before registration/check-in will work. For same-host QA smoke tests only, point the beacon at local HTTP such as `http://127.0.0.1:8081/api/shell` instead of the public self-signed URL.

---

## 30. Appendix B: Permission Scopes

All 47 permission strings seeded by `backend/migrations/add_rbac_tables.py:326-393`:

| Resource | Permissions |
|---|---|
| `agents` | `agents.read`, `agents.write`, `agents.delete`, `agents.execute` |
| `contacts` | `contacts.read`, `contacts.write`, `contacts.delete` |
| `memory` | `memory.read`, `memory.write`, `memory.delete` |
| `flows` | `flows.read`, `flows.write`, `flows.delete`, `flows.execute` |
| `knowledge` | `knowledge.read`, `knowledge.write`, `knowledge.delete` |
| `mcp_instances` | `mcp.instances.read`, `mcp.instances.create`, `mcp.instances.manage`, `mcp.instances.delete` |
| `telegram_instances` | `telegram.instances.create`, `telegram.instances.read`, `telegram.instances.manage`, `telegram.instances.delete` |
| `hub` | `hub.read`, `hub.write`, `hub.delete` |
| `users` | `users.read`, `users.invite`, `users.manage`, `users.remove` |
| `org_settings` | `org.settings.read`, `org.settings.write` |
| `billing` | `billing.read`, `billing.write` |
| `analytics` | `analytics.read` |
| `audit` | `audit.read` |
| `tools` | `tools.read`, `tools.manage`, `tools.execute` |
| `shell` | `shell.read`, `shell.write`, `shell.execute`, `shell.approve` |
| `watcher` | `watcher.read` |
| `api_clients` | `api_clients.read`, `api_clients.write`, `api_clients.delete` |

Role mapping summary (`add_rbac_tables.py:422-495`):

| Permission | owner | admin | member | readonly |
|---|:-:|:-:|:-:|:-:|
| `*.read` (across all resources above) | ✓ | ✓ | ✓ | ✓ |
| `*.write` (own resources) | ✓ | ✓ | ✓ | — |
| `*.delete` | ✓ | ✓ | — | — |
| `*.execute` | ✓ | ✓ | ✓ | — |
| `users.invite` / `.manage` / `.remove` | ✓ | ✓ | — | — |
| `billing.write` | ✓ | — | — | — |
| `shell.*` | ✓ | ✓ | — | — |
| `tools.manage` | ✓ | ✓ | — | — |
| `api_clients.*` | ✓ | ✓ | — | — |
| `audit.read` | ✓ | ✓ | — | — |

**Global Admin** (`User.is_global_admin=True`) bypasses all permission checks via `ApiCaller.has_permission()` (`backend/api/api_auth.py:40-43`).

---

## 31. Appendix C: Glossary

| Term | Definition |
|---|---|
| **Tenant** | An isolated organization — owns users, agents, flows, memory, knowledge, integrations. Represented by `tenant` table; id is a string like `tenant_20251202232822`. |
| **Agent** | A configurable AI persona (provider + model + persona + skills + tools + security profile + channels + knowledge). Scoped to one tenant. |
| **Flow** | A multi-step automated workflow. Types: Conversation, Notification, Workflow, Task. 7 step types (Conversation, Message, Notification, Tool, Skill, Summarization, Slash Command). |
| **Skill** | A built-in agent capability (19 shipped: TTS, Transcription, Web Search, Scraping, Browser, Image Gen, Shell, Flows, Gmail, Calendar, Flight Search, etc.). |
| **Custom Skill** | Tenant-authored skill — Instruction (prompt injection), Script (Python/Bash/Node in sandbox), or MCP-Server (external MCP connection). |
| **Tool (Sandboxed)** | A security/utility binary (nmap, dig, nuclei, httpx, subfinder, katana, sqlmap, webhook, whois) executed in a per-tenant Docker container. |
| **Persona** | A reusable personality template — role, tone preset, personality traits, per-persona skills/tools/knowledge, guardrails. |
| **Tone Preset** | Reusable communication style (formal, casual, technical, etc.). |
| **Sentinel** | LLM-based threat-detection agent. Detects prompt injection, agent takeover, poisoning, shell malicious intent. |
| **Security Profile** | Sentinel configuration (Off, Permissive, Moderate, Aggressive) attachable at tenant / agent / skill scope with inheritance. |
| **MemGuard** | Memory-poisoning protection — regex + fact-validation gate before long-term storage. |
| **MCP** | Model Context Protocol. In Tsushin, also refers to the WhatsApp bridge containers (`mcp-agent-tenant_*`). |
| **MCP Server Skill** | External MCP-protocol server (SSE / HTTP / Stdio) consumed as a tool provider. |
| **WAHA / whatsmeow** | Underlying WhatsApp Web automation libraries used by the WhatsApp MCP containers (see `tester-mcp` running Go 1.24 + whatsmeow). |
| **OKG** | Organisational Knowledge Graph — v0.6.1 memory architecture extension (see private roadmap). |
| **Vector Store** | External vector DB integrations (e.g., Pinecone, Qdrant, MongoDB, local Chroma) registered under `/api/vector-stores`. |
| **Hub** | Tenant-facing integration marketplace — AI providers, channels, tool APIs, TTS providers, MCP servers. |
| **Studio** | The visual agent-builder surface — Agents + Personas + Contacts + Projects + Tone Presets + Knowledge Bases. |
| **Watcher** | Observability dashboard — dashboard, conversations, flows, billing, security, graph view. |
| **Playground** | Interactive in-browser chat for development and testing — threads, documents, slash commands, streaming. |
| **Beacon** | Installable endpoint agent for Shell skill (WebSocket C2). Separate from Beacon here meaning the GKE/K8s concept. |
| **Toolbox** | Per-tenant Docker container hosting sandboxed tools. Managed by `ToolboxContainerService`. |
| **Global Admin** | Platform-level administrator (`User.is_global_admin=True`), crosses tenant boundaries. |
| **HMAC webhook** | Inbound/outbound HTTP channel with SHA-256 HMAC signing via per-webhook secrets (Fernet-encrypted at rest). |

---

*Source citations reference repository-relative files.*
