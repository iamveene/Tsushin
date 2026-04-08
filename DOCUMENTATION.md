# Tsushin — Comprehensive Documentation

**Tsushin** (通信 — Japanese for "Communication") is a multi-tenant, self-hostable agentic messaging platform that unifies AI agent orchestration, conversational channels (WhatsApp, Telegram, Slack, Discord, Webhook, Playground), multi-layer semantic memory, workflow automation (Flows), AI-powered security (Sentinel), and observability.

This document is the exhaustive reference for configuring, deploying, operating, and using every feature of the platform. For a condensed overview, see [README.md](README.md).

> **Version:** v0.6.0 (README) / `SERVICE_VERSION = "0.5.0"` (`backend/settings.py:136`).
> **License:** MIT. **Author:** Vinicios Soares ([@iamveene](https://github.com/iamveene)).

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

# Tsushin Platform Documentation — Writer-A Draft

## 1. Introduction & Audience

**Tsushin** (通信 — Japanese for "Communication") is a multi-tenant, agentic messaging framework that unifies AI agent orchestration, conversational channels (WhatsApp, Telegram, Slack, Discord, HTTP Webhook, Playground), a multi-layer semantic memory system, workflow automation ("Flows"), AI-powered security (Sentinel), and observability under a single self-hostable platform.

Source: `/Users/vinicios/code/tsushin/README.md:11`, `/Users/vinicios/code/tsushin/backend/settings.py:136` (`SERVICE_VERSION = "0.5.0"`), README badge `version-v0.6.0`.

**Audience for this document:**

| Role | What this doc gives you |
|------|-------------------------|
| **Platform operators / SREs** | Container topology, env-var reference, deployment modes (Docker Compose, GKE Helm), health probes, Prometheus metrics, troubleshooting. |
| **Tenant admins** | RBAC roles and permissions, SSO configuration, audit/syslog streaming, API-client management. |
| **Application developers** | Public API v1 reference, OAuth2 client-credentials + direct API-key auth, rate limiting, webhook integration. |
| **Security engineers** | Sentinel profiles, permission scopes, HMAC-signed webhooks, envelope-encrypted secrets, docker-socket-proxy isolation. |

Version under documentation: **v0.6.0** (README.md), with backend `SERVICE_VERSION = "0.5.0"` constant still in `settings.py:136`. Operators should treat `v0.6.0` as the marketing/release version.

---

## 2. Architecture Overview

### 2.1 Container topology (Docker Compose)

Tsushin ships as a Docker Compose stack defined in `/Users/vinicios/code/tsushin/docker-compose.yml`. The core services:

| Service | Image / Build | Port | Purpose | Source |
|---------|---------------|------|---------|--------|
| `tsushin-postgres` | `postgres:16-alpine` | 5432 (internal) | Relational database — tenants, users, agents, flows, events, audit logs. | `docker-compose.yml:22-38` |
| `tsushin-docker-proxy` | `tecnativa/docker-socket-proxy:latest` | 2375 (internal) | Restricts the Docker API surface to reduce container-escape risk. Backend talks to `tcp://docker-socket-proxy:2375` rather than mounting the raw socket. | `docker-compose.yml:43-75` |
| `tsushin-backend` | Built from `./backend/Dockerfile` | `${TSN_APP_PORT:-8081}` | FastAPI app. Agents, flows, memory, skills, channels, API v1, WebSockets. | `docker-compose.yml:80-168` |
| `tsushin-frontend` | Built from `./frontend/Dockerfile` | `${FRONTEND_PORT:-3030}` | Next.js 16 UI (Watcher, Hub, Studio, Playground, Settings). | `docker-compose.yml:173-195` |
| `kokoro-tts` (profile `tts`) | `ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4` | 8880 | Optional local text-to-speech. | `docker-compose.yml:200-224` |

**Network:** All services attach to the **external** bridge network `tsushin-network`. The network is declared `external: true` in compose so that `docker-compose down` *cannot* tear it down — this is critical because MCP WhatsApp bot containers (spawned dynamically by `ToolboxContainerService` / `MCPContainerManager`) also join this network and would lose their WhatsApp sessions if the bridge were removed. Create the network once with `docker network create tsushin-network`; `install.py` handles this automatically. Source: `docker-compose.yml:229-237`.

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

Source: `/Users/vinicios/code/tsushin/README.md:289-328`.

### 2.3 Dynamically-managed MCP containers

Tsushin spawns per-tenant containers outside the compose stack, all joining `tsushin-network`:

* **WhatsApp MCP bots** — one container per connected WhatsApp number, built from the `mcp-agent-tenant` image, managed by `services/mcp_container_manager.py`.
* **Tester MCP** — optional QA bridge (port 8088) run with `--profile testing`.
* **Toolbox containers** — per-tenant sandboxes for "Sandboxed Tools" (nmap, dig, nuclei, etc.), managed by `services/toolbox_container_service.py` with base image built from `backend/containers/Dockerfile.toolbox`.

Source: `docker-compose.yml:12-14`, `backend/services/toolbox_container_service.py:114`, `backend/services/mcp_container_manager.py:234`.

---

## 3. Quick Start

### 3.1 Prerequisites

* Docker Engine 20.10+ and Docker Compose V2
* Python 3.8+ with pip (installer only)
* Git
* At least 4 GB RAM available
* A domain name (only if deploying with Let's Encrypt SSL)

Sources: `README.md:17-22`, `DOCKER.md:33-36`.

### 3.2 Clone and install

```bash
git clone https://github.com/iamveene/tsushin.git
cd tsushin

# Interactive install (prompts for ports, access type, SSL)
python3 install.py

# Unattended with self-signed HTTPS, auto-detected IP
python3 install.py --defaults

# Unattended with Let's Encrypt (public domain required)
python3 install.py --defaults --domain app.example.com --email you@example.com

# Unattended HTTP-only (dev/test only — insecure)
python3 install.py --defaults --http

# Custom ports
python3 install.py --port 9090 --frontend-port 3031
```

Source: `README.md:29-48`, `install.py:38-96`. `--http` and `--domain` are mutually exclusive and both require `--defaults` (`install.py:102-109`).

For a remote Ubuntu VM, use the normal user flow: clone the repo on the VM, install Docker plus Docker Compose v2, and run `python3 install.py` from the repository root on that VM. For remote HTTP installs, the installer's final success output uses the public host/IP you entered rather than `localhost`.

The installer automatically:

1. Installs `requests` and `cryptography` via pip.
2. Creates the `tsushin-network` Docker bridge if absent.
3. Generates `.env` with random `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, `TSN_MASTER_KEY`.
4. Sets `HOST_BACKEND_DATA_PATH` to the absolute host path of `backend/data` (required for Docker-in-Docker volume mounts).
5. Builds backend + frontend images and starts the stack.
6. (If SSL) Generates Caddy config and self-signed cert or configures Let's Encrypt.

Source: `install.py:49-53`, `docker-compose.yml:131-134` (HOST_BACKEND_DATA_PATH is required in `.env`).

### 3.3 Complete setup via browser

Open the URL printed at the end of install (e.g. `https://localhost`, `http://localhost:3030`, or `http://<public-host>:3030` for remote HTTP) and finish the `/setup` wizard:

1. Create admin account + organization.
2. Configure at least one AI provider API key (Gemini, Claude, OpenAI, Groq, Grok, DeepSeek, Ollama, OpenRouter).
3. The wizard automatically creates **ProviderInstance** records for each supported provider key entered during setup. The selected primary provider is also assigned as the **System AI** — no manual post-setup Hub provisioning is required for the providers entered in the wizard.
4. At completion, the wizard reveals an auto-generated **global admin** email/password pair. Record these credentials before leaving the completion screen; they are required for `/system/*` validation and system-level administration.
5. On first login an **onboarding tour** (9 steps) walks through all platform areas: Watcher, Studio, Hub, Channels, Flows, Playground, Security, and a final setup checklist.
6. The tour highlights mandatory next steps: **connect a communication channel** (WhatsApp/Telegram) via the Hub to enable agent messaging.
7. The **User Guide** is accessible anytime via the **?** button in the header.

**LLM provider keys are configured per-tenant through the Hub UI — not in environment variables.** This enables multi-tenant isolation. Source: `README.md:398`.

For remote Ubuntu VM installs that use a host-level Ollama daemon, start with `http://host.docker.internal:11434` inside Tsushin. If the Docker engine on that host does not resolve `host.docker.internal`, use the container bridge gateway instead (for example `http://172.18.0.1:11434`) and re-test the provider instance from the Hub.

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
docker compose up -d --build --no-cache backend
docker compose up -d --build --no-cache frontend

# Logs
docker compose logs -f backend
docker compose logs --tail=100 backend

# Stop without removing network (SAFE)
docker compose stop backend

# Optional profiles
docker compose --profile tts up -d        # Add Kokoro TTS
docker compose --profile testing up -d    # Add tester-mcp (port 8088)
```

Source: `DOCKER.md:114-169`, `docker-compose.yml:203-204` (tts profile).

### 4.2 Container rebuild safety (SAFE vs UNSAFE)

**SAFE:** `docker compose up -d --build --no-cache <service>` rebuilds individual services without touching the `tsushin-network` bridge. MCP WhatsApp bot containers keep their WebSocket sessions alive.

**UNSAFE:** `docker compose down` — this used to tear down the network, killing every WhatsApp session and forcing a QR re-scan. To prevent this the compose file declares `tsushin-network` as `external: true` (`docker-compose.yml:229-237`), so `docker compose down` now leaves the network in place. You should still avoid `down` for routine rebuilds; only use it when you genuinely need to reset Postgres or recreate containers from scratch.

**Session recovery if WhatsApp drops:**

```bash
docker logs mcp-agent-tenant_<id> --tail=10   # Look for QR-code re-auth loop
docker restart mcp-agent-tenant_<id>          # Restart, then re-scan QR from phone
```

### 4.3 Kubernetes / GKE (Helm chart)

Tsushin ships a Helm chart at `/Users/vinicios/code/tsushin/k8s/tsushin/`:

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
| `TSN_CORS_ORIGINS` | Comma-separated allowed origins. Defaults to `*` — restrict in production. |
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

All authentication endpoints live under `/api/auth/` (`backend/auth_routes.py:69`). Rate limiting is enforced by `slowapi` (MED-004, `auth_routes.py:22-24, 66-67`).

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
* `secure` flag is set when `TSN_SSL_MODE` is anything other than `""`, `off`, `none`, `disabled`.

### 6.2 Multi-tenancy model

Tenants are first-class entities defined by the `tenant` table (`backend/models_rbac.py:16-41`). Key columns:

| Column | Purpose |
|---|---|
| `id` (String(50)) | Tenant identifier (e.g. `tenant_20251202232822`). |
| `slug` (unique) | URL-safe identifier. |
| `plan` / `plan_id` | Legacy plan name or FK to `subscription_plan` row. |
| `max_users`, `max_agents`, `max_monthly_requests` | Quota columns. |
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

---


## 7. Agents

Agents are AI assistants scoped to a tenant, each linked to a `Contact` record (role="agent") and configurable for multi-channel operation. Stored in the `agent` table.

Source: `backend/models.py:300-392` (Agent model)

### 7.1 Create / Edit Agent Form

The "Create New Agent" modal on Studio → Agents exposes the fields below.
Source: `frontend/app/agents/page.tsx:22-36` (form interface) and `:726-990` (form JSX).

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
- `enabled_channels` JSON — any of `playground, whatsapp, telegram, slack, discord, webhook`. (`models.py:363`)
- `whatsapp_integration_id`, `telegram_integration_id`, `slack_integration_id`, `discord_integration_id`, `webhook_integration_id` — per-channel FKs. (`models.py:364-368`)

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

- **Agent Switcher Skill** — `skill_type="agent_switcher"`, `execution_mode="tool"`. "Allows users to switch their default agent for direct messages via natural language commands." Claims detection-type exemption for `agent_takeover`.
  Source: `backend/agent/skills/agent_switcher_skill.py:39-42`

- **Agent Communication Skill (A2A)** — `skill_type="agent_communication"`, `execution_mode="tool"`. "Ask other agents questions, discover available agents, or delegate tasks."
  Source: `backend/agent/skills/agent_communication_skill.py:28-31`

The Studio → Agent Communication page (`frontend/app/agents/communication/page.tsx`) mounts `AgentCommunicationManager` to manage inter-agent messaging permissions and monitor communication sessions.

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
| `flight_search` | Flight Search | tool | Search for flights using configured provider (Amadeus, Skyscanner, etc.) | `flight_search_skill.py:42-45` |
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

| Field | Type | Description |
|---|---|---|
| `instructions_md` | string (max 8,000 chars) | Markdown instructions injected into the LLM tool definition |

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

Executable scripts deployed to a sandboxed container. Supports Python, Bash, and Node.js.

| Field | Type | Description |
|---|---|---|
| `script_content` | string (max 256 KB) | The script source code |
| `script_language` | string | `python` \| `bash` \| `nodejs` |
| `script_entrypoint` | string | Entry function or file to execute |

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
    "script_content": "import json\nimport statistics\n\ndef analyze(data: str) -> str:\n    rows = data.strip().split(\"\\n\")\n    return json.dumps({\"row_count\": len(rows)})",
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

- **Layer 1 — Working Memory**: ring buffer of last N messages per sender key, stored in the `memory` table (`messages_json` JSON field). Fast in-context recall. Source: `backend/models.py:112-119`.
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
- `GET /agents/{id}/knowledge-base/{knowledge_id}/chunks` — chunks
- `POST /agents/{id}/knowledge-base/search` — semantic search over KB
- `POST /agents/{id}/knowledge-base/{knowledge_id}/reprocess` — reprocess

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
| `summarization` | `SummarizationStepHandler` | AI summarization of prior step outputs. |
| `browser_automation` | `BrowserAutomationStepHandler` | Browser control (navigate/screenshot/click/fill/extract). |
| `Trigger`, `Subflow` + PascalCase aliases | Legacy handlers | Backward compat. |

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

The wizard can also be launched manually from the Hub Communication tab or auto-launches after the onboarding tour if no WhatsApp instances exist.

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
- `WhatsApp Unassigned` warning node when the channel is enabled but ambiguous/unassigned

**Getting Started Checklist:** The Watcher dashboard displays a "Getting Started" widget tracking 5 setup milestones: Configure Agent, Connect Channel, Add Contacts, Test in Playground, Create Flow. It auto-hides when all items are complete and can be dismissed.

**Hub Integration Summary:** A compact status strip above the Hub tab bar shows connection counts for AI Providers, WhatsApp, Telegram, Slack, Discord, and Webhooks at a glance.

**Settings Progressive Disclosure:** The Settings page groups cards into "Essential" (Organization, Team Members, System AI, Integrations) always visible, and "Advanced" collapsed by default.

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

1. **Create a Slack App** at [api.slack.com/apps](https://api.slack.com/apps):
   - Add bot token scopes: `chat:write`, `channels:read`, `users:read`, `files:write` (minimum).
   - For Socket Mode: enable Socket Mode and generate an app-level token (`xapp-...`).
   - For HTTP Events API: set the Request URL and copy the Signing Secret.
2. **Install the app** to your workspace — copy the `xoxb-` bot token.
3. Navigate to **Hub → Channels → Slack** in the UI.
4. Click **Add Integration** — paste the bot token and app token (or signing secret for HTTP mode).
5. Choose mode: **Socket Mode** (recommended — no public URL needed) or **HTTP Events API**.
6. Set `dm_policy` — `open` to accept all DMs, `allowlist` to restrict to specific channels, or `disabled`.
7. If using allowlist, add the Slack channel IDs where the bot should operate.
8. **Assign to an agent** — on the agent's Channels tab, set `slack_integration_id`.
9. **Test** — message the bot in an allowed channel or DM; it should respond via the assigned agent.

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

1. **Create a Discord Application** at [discord.com/developers](https://discord.com/developers/applications).
2. Under **Bot** settings: reset/copy the bot token, enable **Message Content Intent** and other required Gateway Intents.
3. Under **OAuth2 → URL Generator**: select `bot` scope and required permissions (`Send Messages`, `Read Message History`, `Attach Files`). Use the generated URL to invite the bot to your server.
4. Navigate to **Hub → Channels → Discord** in the UI.
5. Click **Add Integration** — paste the bot token and the Application ID.
6. Set `dm_policy` and `allowed_guilds` to control where the bot responds.
7. Optionally configure `guild_channel_config` for per-guild channel restrictions.
8. **Assign to an agent** — on the agent's Channels tab, set `discord_integration_id`.
9. **Test** — message the bot in a Discord channel or DM; it should respond via the assigned agent.

### 15.5 Webhook

**Source:** `backend/channels/webhook/adapter.py`

Bidirectional HTTP channel. Inbound: external systems POST HMAC-signed events to `/api/webhooks/{id}/inbound` (handled by `routes_webhook_inbound.py`, enqueued into `MessageQueue`, routed through `AgentRouter` by `QueueWorker._handle_webhook`). Outbound: the adapter POSTs agent responses back to the customer's `callback_url`.

Capability flags (`adapter.py:39-46`):
- `delivery_mode=push`, text-only in v1 (`supports_media=false`), `text_chunk_limit=16000`.

**Outbound callback POST** (`adapter.py:88-202`):
- Optional — governed by `integration.callback_enabled` + `integration.callback_url`. If disabled, the adapter reports success with `message_id="webhook_inbound_only"` (result pollable via `/api/v1/queue/{id}`).
- SSRF-validated via `utils/ssrf_validator.validate_url()` before the POST.
- Timeout: `10.0` seconds (`_CALLBACK_TIMEOUT_SECONDS`, `adapter.py:33`).
- Response body capped at `65536` bytes (`_MAX_RESPONSE_BYTES`, `adapter.py:32`).
- `follow_redirects=False`.

**HMAC signing** (`adapter.py:134-157`):
- Canonical payload JSON (sorted keys, compact separators) includes: `event`, `webhook_id`, `timestamp`, `text`, `agent_id`, `sender_key`, `source_id`.
- Signature: `HMAC-SHA256(secret, f"{timestamp}.".bytes + body_bytes)` — replay-protected.
- Headers emitted: `X-Tsushin-Signature: sha256={hex}`, `X-Tsushin-Timestamp`, `X-Tsushin-Event`, `X-Tsushin-Webhook-Id`, `User-Agent: Tsushin-Webhook/1.0`.

**Secret encryption:** `api_secret_encrypted` decrypted via `TokenEncryption` keyed by the webhook encryption master key + per-tenant derivation (`adapter.py:71-86`, `services/encryption_key_service.get_webhook_encryption_key`).

**Health:** Uses stored snapshot from the `WebhookIntegration` row (`is_active`, `status`, `circuit_breaker_state`, `health_status`, `circuit_breaker_failure_count`) — no live probe to avoid amplification (`adapter.py:204-222`).

**Model:** `WebhookIntegration` (`backend/models.py:2918`).

**E2E setup — Webhook channel:**

1. Navigate to **Hub → Channels → Webhooks** in the UI.
2. Click **Add Integration** — provide a name and optionally a callback URL for outbound responses.
3. The system generates an HMAC signing secret (visible once, stored encrypted). **Copy and save it.**
4. Configure optional defenses: IP allowlist (CIDR ranges), rate limit (RPM), max payload size.
5. **Assign to an agent** — on the agent's Channels tab, set `webhook_integration_id`.
6. **Test inbound** — send a signed event to your webhook:

```bash
# Generate HMAC signature
TIMESTAMP=$(date +%s)
BODY='{"text":"Hello from webhook","sender_key":"external-user-1"}'
SIGNATURE=$(echo -n "${TIMESTAMP}.${BODY}" | openssl dgst -sha256 -hmac "<your_api_secret>" | awk '{print $2}')

# Send inbound event
curl -X POST http://localhost:8081/api/webhooks/<webhook_id>/inbound \
  -H "Content-Type: application/json" \
  -H "X-Tsushin-Signature: sha256=${SIGNATURE}" \
  -H "X-Tsushin-Timestamp: ${TIMESTAMP}" \
  -d "${BODY}"
```

7. If `callback_url` is configured, the agent's response will be POSTed there with HMAC-signed headers.

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

### 18.2 Audio Recording & Whisper Transcription

The page uses `MediaRecorder` to capture voice directly in the browser (`page.tsx:498-518`):
- Preferred MIME types (in order): `audio/webm;codecs=opus`, `audio/webm`, `audio/ogg;codecs=opus`, `audio/mp4` (`:502-510`).
- Audio capabilities are loaded per selected agent (`:484-490`) — determined by the agent's configured `audio_transcript` skill.

Transcription is performed by the `audio_transcript` skill (Source: `backend/agent/skills/audio_transcript.py`) using OpenAI Whisper or configured provider. Skill is `execution_mode="special"` (media-triggered).

### 18.3 Document Uploads

Supported extensions (Source: `backend/services/playground_document_service.py:32-38`):
- `.pdf` → pdf
- `.txt` → txt
- `.csv` → csv
- `.json` → json
- `.docx` → docx

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

### 18.6 Async Queuing & Dead-Letter Retry

Service layer: `backend/services/message_queue_service.py`, `backend/services/queue_worker.py`.

- Messages submitted via the async path receive a `queue_id`.
- Placeholder messages render in UI with `message_id = "queue_{id}"` (`page.tsx:193, 205, 232`).
- On completion, `onQueueMessageCompleted` replaces the placeholder with the real response and triggers a thread refresh.
- Dead-letter retry is handled server-side by the queue worker on failed jobs.

---

*End of Writer-B draft.*
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

### 19.3 Model Discovery

`backend/services/model_discovery_service.py` auto-fetches the vendor's `/models` endpoint (for OpenAI-compatible providers) and populates `available_models`. Used by the frontend Provider form to let the user pick which models to expose.

### 19.4 Model Pricing

**Source:** `frontend/app/settings/model-pricing/page.tsx`, `backend/api/routes_model_pricing.py`

Pricing rates per 1M tokens used for cost estimation in the Playground debug panel. Defaults are based on official provider pricing; tenant-set custom rates override defaults.

UI table columns (`model-pricing/page.tsx:326-347`):
- Model (with provider badge, display name, raw model name)
- Input cost per 1M tokens (numeric input, step=0.001)
- Output cost per 1M tokens (numeric input, step=0.001)
- Status
- Actions (Edit / Save)

Filters: "All" or a provider badge filter (`page.tsx:292-323`). Tenants without `org.settings.write` see read-only mode (gate at top of file).

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

### 20.4 Brave Search / SerpAPI / Google Flights

**Sources:** `backend/hub/providers/brave_search_provider.py`, `backend/hub/providers/serpapi_search_provider.py`, `backend/hub/providers/google_flights_provider.py`, `backend/hub/providers/search_registry.py`, `backend/hub/providers/flight_search_provider.py`

- Brave Search: API key based web search provider (primary supported search provider in v0.6.0).
- SerpAPI: used for both generic web search and Google Flights (Google Flights falls back to env var `SERPAPI_KEY` or `GOOGLE_FLIGHTS_API_KEY` — `google_flights_provider.py:71-74`).
- All search providers register with `SearchRegistry` and are configured through the Hub page (`GoogleFlightsIntegration` — `models.py:3108`).
- **Tavily:** Not supported in v0.6.0. Planned for a future release. If you need a search provider, use Brave Search.

### 20.5 Browser Automation (Playwright, CDP)

**Sources:** `backend/hub/providers/browser_automation_provider.py`, `backend/hub/providers/playwright_provider.py`, `backend/hub/providers/cdp_provider.py`, `backend/hub/providers/browser_session_manager.py`, `backend/hub/providers/browser_automation_registry.py`
Model: `BrowserAutomationIntegration` (`models.py:3136`).

Two provider types (`browser_automation_provider.py:196-252`):

| Provider | `provider_type` | Config |
|---|---|---|
| Playwright (in-container) | `playwright` | Launches Chromium inside the backend container |
| CDP (host browser) | `cdp` | Connects over CDP to a running Chrome on the host; default `cdp_url=http://host.docker.internal:9222` |

The CDP provider validates the CDP URL through `utils/cdp_url_validator.validate_cdp_url` before connecting (`cdp_provider.py:66-72`) and persists browser state (cookies, localStorage, active logins) via the live CDP connection.

### 20.6 TTS (Kokoro, OpenAI, ElevenLabs)

**Sources:** `backend/hub/providers/tts_provider.py` (abstract + `TTSRequest`/`TTSResponse`/`VoiceInfo`), `backend/hub/providers/kokoro_tts_provider.py`, `backend/hub/providers/openai_tts_provider.py`, `backend/hub/providers/elevenlabs_tts_provider.py`, `backend/hub/providers/tts_registry.py`, `backend/api/routes_tts_providers.py`

- Providers expose `get_available_voices()` → `List[VoiceInfo]` and a default voice.
- OpenAI TTS default voice: `"nova"` (`tts_provider.py:43`).
- Kokoro is a local/self-hosted TTS option (see `KOKORO_TTS_FIX.md`).

### 20.7 MCP Server Registration

**Sources:** `backend/hub/mcp/connection_manager.py`, `backend/hub/mcp/sse_transport.py`, `backend/hub/mcp/stdio_transport.py`, `backend/hub/mcp/transport_base.py`, `backend/hub/mcp/utils.py`
Custom third-party MCP servers can be registered via stdio or SSE transports. The `connection_manager` maintains the active MCP client sessions and exposes them to agent skills.

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
| Action | All Actions, Authentication, Agents, Flows, Contacts, Settings, Security, API Clients, Custom Skills, MCP Servers, Team |
| Severity | All Severities, Info, Warning, Critical |
| Channel | All Channels, Web, API, WhatsApp, Telegram, System |
| From / To | Date range |

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

### 22.3 Platform Integrations (`frontend/app/system/integrations/page.tsx`)

Platform-level third-party credentials (keys that apply globally, not per-tenant). This is the global counterpart to §21.4.

### 22.4 Plans / Subscription Tiers (`frontend/app/system/plans/page.tsx`)

Define plan tiers (Free, Pro, Enterprise, etc.) with quotas and feature toggles. Each tenant's current plan is visible on the Organization page (§21.1).

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

**Action categories** (from the UI filter catalog, `audit-logs/page.tsx:40-66`): auth, agent, flow, contact, settings, security, api_client, skill, mcp, team.

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
| **Dashboard** | KPIs, activity timeline, system performance, distribution charts. |
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
  -d "grant_type=client_credentials&client_id=$CLIENT_ID&client_secret=$CLIENT_SECRET"
# → { "access_token": "<jwt>", "token_type": "bearer", "expires_in": 3600 }

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
| GET | `/api/v1/queue/{queue_id}` | Poll status of an async chat request. |
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

### 25.6 Webhooks (bidirectional, HMAC-signed)

The webhook channel (`backend/channels/webhook/adapter.py`) is bidirectional:

**Inbound** — external systems POST signed events to `POST /api/webhooks/{webhook_id}/inbound` (`backend/api/routes_webhook_inbound.py`). Events are enqueued into `MessageQueue`; `QueueWorker._handle_webhook` routes them to the target agent.

**Outbound** — agent responses are HMAC-signed and POSTed to the webhook's `callback_url`. Signing uses `hmac.new(secret, signed_input, sha256)` (`channels/webhook/adapter.py:148`). Outbound requests carry custom headers:

* `X-Tsushin-Webhook-Id: <int>`
* `X-Tsushin-Signature: <hex sha256 HMAC>`
* (plus timestamp fields — see `channels/webhook/adapter.py:131-155`)

Callback URLs are subject to SSRF policy enforcement (`channels/webhook/adapter.py:125`). The `api_secret_encrypted` column on `WebhookIntegration` is Fernet-encrypted using a per-tenant-derived webhook key (`get_webhook_encryption_key`, `channels/webhook/adapter.py:72-85`). Webhooks can be configured as inbound-only (outbound disabled) by leaving `callback_url` empty.

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

**Hub visibility:** the tester is intentionally not listed as a tenant-managed `WhatsAppMCPInstance`. Instead, Hub exposes it as a dedicated **QA Tester** card backed by `/api/mcp/instances/tester/*` endpoints so operators can monitor auth state, fetch QR, restart the tester, and reset auth without confusing it with production tenant instances.

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

---

*End of Writer-C draft.*
## 28. Troubleshooting

### 28.1 Container won't start

```bash
docker compose logs backend                 # Read the stack trace
docker inspect tsushin-backend --format='{{.State.Health.Status}}'
lsof -i :8081                               # Port collision?
curl http://localhost:8081/api/health       # Liveness
curl http://localhost:8081/api/readiness    # DB connectivity
```

Source: `DOCKER.md:260-272`.

### 28.2 WhatsApp session dropped / QR re-auth loop

Symptoms: the MCP container for a WhatsApp number keeps regenerating QR codes in `docker logs mcp-agent-tenant_<id>`.

Cause: The `tsushin-network` bridge was torn down (historically via `docker compose down`), severing the WebSocket to `whatsmeow`.

Fix:

```bash
docker restart mcp-agent-tenant_<id>    # Restart container
# Then re-scan QR on the linked phone.
```

Prevention: never `docker compose down` for routine rebuilds — use `docker compose up -d --build --no-cache <service>` instead. The compose file now declares `tsushin-network` as `external: true` so even `down` cannot remove it.

### 28.3 Database issues

```bash
docker exec -it tsushin-postgres psql -U tsushin -d tsushin -c "\dt"     # List tables
docker exec -it tsushin-postgres psql -U tsushin -d tsushin              # Interactive shell
```

Source: `DOCKER.md:275-282`.

**Playground search note:** Postgres deployments do not use SQLite FTS5. Tsushin now falls back cleanly to LIKE-based conversation search on Postgres and rolls back failed search probes before continuing, so a failed search should not poison the rest of the request transaction.

### 28.4 Memory / slow model loading

The backend lazy-loads `sentence-transformers` models; first boot can be slow. Pre-warm:

```bash
docker exec tsushin-backend python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
```

Or raise Docker Desktop memory limit to ≥ 6 GB. Source: `DOCKER.md:286-294`.

### 28.5 Permission issues on bind mounts (Linux)

```bash
sudo chown -R 1000:1000 backend/data/
sudo chown -R 1000:1000 logs/
```

Source: `DOCKER.md:298-301`.

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

### A.4 Security / Auth

| Variable | Default | Purpose | Source |
|---|---|---|---|
| `JWT_SECRET_KEY` | (required) | HMAC key for JWTs. Generate with `secrets.token_urlsafe(32)`. | `auth_utils.py:26`, `docker-compose.yml:137` |
| `TSN_MASTER_KEY` | (required for SEC-006) | Fernet master key for envelope-encrypting per-tenant encryption keys stored in DB. Generate with `Fernet.generate_key()`. | `services/encryption_key_service.py:42`, `migrations/wrap_encryption_keys.py:66` |
| `TSN_CORS_ORIGINS` | `*` | Comma-separated allowed origins. | `app.py:1108` |
| `TSN_TRUSTED_PROXY_HOSTS` | `127.0.0.1,::1` | X-Forwarded-For proxy allowlist. | `app.py:1138` |
| `TSN_ENABLE_HSTS` | *(unset)* | Set `1`/`true` to emit HSTS header. | `app.py:1172` |
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
| `KOKORO_SERVICE_URL` | `http://kokoro-tts:8880` | Kokoro TTS service URL. | `hub/providers/kokoro_tts_provider.py:176` |
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
| **Skill** | A built-in agent capability (20 shipped: TTS, Transcription, Web Search, Scraping, Browser, Image Gen, Shell, Flows, Gmail, Calendar, Flight Search, etc.). |
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

*End of Writer-A draft. Source citations reference files under `/Users/vinicios/code/tsushin/`.*
