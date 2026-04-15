<p align="center">
  <img src="images/tsushin-banner.png" alt="Tsushin Banner" width="100%">
</p>

<p align="center">
  <a href=""><img src="https://img.shields.io/badge/status-beta-orange" alt="Status"></a>
  <a href=""><img src="https://img.shields.io/badge/version-v0.6.0-blue" alt="Version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

**Tsushin** (通信 — "Communication" in Japanese) is a multi-tenant agentic messaging platform that unifies AI agent orchestration, conversational channels, semantic memory, workflow automation, AI-powered security, and observability — self-hostable, with RBAC and full multi-tenancy.

> 📖 **Full reference:** see **[docs/DOCUMENTATION.md](docs/DOCUMENTATION.md)** for the exhaustive technical guide covering every configuration item, feature, form field, channel, integration, API endpoint, and appendix.
>
> 📘 **User guide:** see **[docs/USER_GUIDE.md](docs/USER_GUIDE.md)** for a practical walkthrough of setting up channels, creating agents, configuring skills, building flows, using slash commands, and more.

---

## Feature Highlights

- **Multi-agent orchestration** — per-agent personas, tone presets, memory modes (isolated / channel / shared), keyword triggers, and dynamic agent switching.
- **6 channels** — WhatsApp (WAHA), Telegram, Slack, Discord, HTTP Webhook (HMAC-signed), and a built-in Playground web chat.
- **10+ LLM providers** — OpenAI, Anthropic, Gemini, Groq, Grok, DeepSeek, Ollama, OpenRouter, Vertex AI, and any OpenAI-compatible endpoint. Provider instances are configured per-tenant via the Hub.
- **4-layer memory** — working, episodic, semantic (with temporal decay), and shared memory pool; optional OKG (Ontology Knowledge Graph).
- **Vector stores** — Chroma (built-in), Qdrant (auto-provisioned during setup when available), Pinecone, or MongoDB Atlas.
- **19 built-in skills** — audio TTS/transcription, web search, scraping, browser automation, Gmail, flight search, scheduler, knowledge sharing, OKG terms, sandboxed shell/network tools, and more.
- **Custom skills** — Instruction, Script (Python/Bash/Node), and MCP-server skills, gated by a Sentinel scan at save-time.
- **37 slash commands** — agent management, email (Gmail), web search, shell, thread control, sandboxed tools, flows, scheduler, memory, project context, and system commands — all with per-contact access control.
- **Sandboxed tools** — per-tenant Docker containers with `nmap`, `nuclei`, `dig`, `httpx`, `whois`, `katana`, `subfinder`, `sqlmap`, and a generic webhook tool. Invoked via `/tool <name> <cmd> param=value`.
- **Flows** — 4 flow types (conversation, notification, workflow, task) with immediate, scheduled, or recurring (cron) execution; 8 step types with template-variable interpolation.
- **Sentinel security** — AI-powered detection of prompt injection, agent takeover, poisoning, shell malicious intent, memory poisoning (MemGuard), browser SSRF, and vector-store poisoning. Profiles with block / warn-only / detect-only / off modes.
- **Studio** — visual agent builder, personas, contacts, projects (knowledge isolation), custom skills, and agent-to-agent communication.
- **Playground** — real-time streaming chat, audio recording + Whisper transcription, document-only uploads, command palette, memory inspector, expert mode.
- **Watcher** — observability dashboard with conversations, flows, security events, channel health, billing, and a graph view.
- **Public API v1** — OAuth2 client credentials + direct API key, rate-limited, 40+ endpoints (agents, chat, flows, hub, studio, resources).
- **Multi-tenancy & RBAC** — 4 built-in roles (owner / admin / member / readonly), 47 permission scopes, per-tenant isolation, envelope-encrypted per-service keys.
- **Audit & compliance** — tenant-scoped audit events, CSV export, per-tenant retention, RFC 5424 syslog streaming (TCP / UDP / TLS).
- **Cloud-native** — Docker Compose (dev), Helm chart at `k8s/tsushin/` (GKE), GCP Secret Manager backend, Prometheus metrics at `/metrics`.

---

## Quick Start

### Prerequisites
- **Docker & Docker Compose V2**
- **Python 3.8+** with **pip** (installer only)
- **Git**

> The Docker network `tsushin-network` must exist before `docker compose up`. The installer creates it automatically. Manual: `docker network create tsushin-network`.

### Installation

```bash
# 1. Clone
git clone https://github.com/iamveene/Tsushin.git
cd Tsushin

# 2. Run installer (interactive — prompts for ports, access type, SSL)
python3 install.py

# Unattended, self-signed HTTPS, auto-detected IP
python3 install.py --defaults

# Unattended with Let's Encrypt SSL
python3 install.py --defaults --domain app.example.com --email you@example.com

# See all options
python3 install.py --help

# 3. Open the URL printed at the end and finish the /setup wizard:
#    create admin account + configure at least one AI provider API key.
```

The installer handles infrastructure only (containers, networking, SSL, `.env` secrets). Organization setup and LLM provider keys are configured per-tenant through the `/setup` wizard and Hub UI — not via environment variables — enabling multi-tenant isolation.

For SSL installs, the generated Caddy config now targets stack-scoped upstreams such as `${TSN_STACK_NAME}-frontend` and `${TSN_STACK_NAME}-backend`. That keeps `https://localhost` pinned to the intended stack even when multiple Tsushin instances share `tsushin-network`.

→ Full deployment options, GKE/Helm, GCP Secret Manager, and rebuild-safety rules: see [docs/DOCUMENTATION.md §4 Deployment & Operations](docs/DOCUMENTATION.md#4-deployment--operations).

### Verify

```bash
curl http://localhost:8081/api/health      # Liveness
curl http://localhost:8081/api/readiness   # Readiness (checks PostgreSQL)
docker compose ps                          # Container states
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           TSUSHIN PLATFORM                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐  │
│  │ Frontend UI  │     │   Backend API    │     │      RBAC Layer          │  │
│  │  Next.js 16  │◄───►│ FastAPI + PG 16  │◄───►│  Auth / Tenants / Roles  │  │
│  └──────────────┘     └────────┬─────────┘     └──────────────────────────┘  │
│                                │                                             │
│         ┌──────────────────────┼──────────────────────────┐                  │
│         │                      │                          │                  │
│         ▼                      ▼                          ▼                  │
│  ┌──────────────┐     ┌───────────────┐     ┌─────────────────────┐         │
│  │     CORE     │     │      HUB      │     │       STUDIO        │         │
│  │ Agent Engine │     │ AI Providers  │     │ Agents   Personas   │         │
│  │ 19 Skills    │     │ Comm Channels │     │ Contacts Projects   │         │
│  │ Sentinel     │     │ Tool APIs     │     │ Tone Presets        │         │
│  └──────┬───────┘     └───────┬───────┘     └─────────────────────┘         │
│         │                     │                                              │
│         ▼                     ▼                                              │
│  ┌──────────────┐     ┌───────────────┐     ┌─────────────────────┐         │
│  │    FLOWS     │     │    MEMORY     │     │      WATCHER        │         │
│  │ 4 types      │     │ Working       │     │ Dashboard  Billing  │         │
│  │ 7 step types │     │ Episodic      │     │ Convos     Security │         │
│  │ Scheduler    │     │ Semantic      │     │ Flows   Graph View  │         │
│  │ Templates    │     │ Shared        │     │                     │         │
│  └──────────────┘     └───────────────┘     └─────────────────────┘         │
│                                                                              │
│  ┌──────────────────────────────┐     ┌──────────────────────────────────┐   │
│  │      SANDBOXED TOOLS         │     │          CHANNELS                │   │
│  │ Per-tenant Docker isolation  │     │ WhatsApp │ Telegram │ Slack      │   │
│  │ 9 pre-installed tools        │     │ Discord  │ Webhook  │ Playground │   │
│  └──────────────────────────────┘     └──────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

→ Full container topology, data flow, and dynamically-managed MCP containers: see [docs/DOCUMENTATION.md §2 Architecture Overview](docs/DOCUMENTATION.md#2-architecture-overview).

---

## Documentation Map

| Topic | Section |
|-------|---------|
| Deployment (Compose / GKE / GCP SM) | [§4](docs/DOCUMENTATION.md#4-deployment--operations) |
| Environment variable reference | [§5](docs/DOCUMENTATION.md#5-system-configuration) + [Appendix A](docs/DOCUMENTATION.md#29-appendix-a-complete-environment-variable-reference) |
| Authentication, SSO, RBAC | [§6](docs/DOCUMENTATION.md#6-authentication--access) + [Appendix B](docs/DOCUMENTATION.md#30-appendix-b-permission-scopes) |
| Agents, personas, tone presets | [§7](docs/DOCUMENTATION.md#7-agents), [§8](docs/DOCUMENTATION.md#8-personas--tone-presets) |
| Skills (built-in + custom) & sandboxed tools | [§9](docs/DOCUMENTATION.md#9-skills) |
| Memory, knowledge, vector stores | [§10](docs/DOCUMENTATION.md#10-memory--knowledge), [§11](docs/DOCUMENTATION.md#11-vector-stores) |
| Sentinel security | [§12](docs/DOCUMENTATION.md#12-security--sentinel) |
| Flows & scheduler | [§13](docs/DOCUMENTATION.md#13-flows), [§14](docs/DOCUMENTATION.md#14-scheduler--triggers) |
| Channels (WhatsApp / Telegram / Slack / Discord / Webhook / Playground) | [§15](docs/DOCUMENTATION.md#15-channels) |
| Contacts, projects, playground | [§16](docs/DOCUMENTATION.md#16-contacts--channel-mapping), [§17](docs/DOCUMENTATION.md#17-projects-studio), [§18](docs/DOCUMENTATION.md#18-playground) |
| LLM providers & hub integrations | [§19](docs/DOCUMENTATION.md#19-llm-providers), [§20](docs/DOCUMENTATION.md#20-hub-integrations) |
| Settings UI (every subpage) & system admin | [§21](docs/DOCUMENTATION.md#21-settings--ui-taxonomy), [§22](docs/DOCUMENTATION.md#22-system-admin-global-admin-only) |
| Audit & syslog | [§23](docs/DOCUMENTATION.md#23-audit-logging--compliance) |
| Observability & metrics | [§24](docs/DOCUMENTATION.md#24-observability) |
| Public API v1 reference | [§25](docs/DOCUMENTATION.md#25-public-api-v1) |
| Slash commands (37 commands + usage examples) | [§26](docs/DOCUMENTATION.md#26-slash-commands-system-wide-catalog) |
| Troubleshooting | [§28](docs/DOCUMENTATION.md#28-troubleshooting) |

---

## Essential Configuration

Representative minimal `.env` for a manual deployment. The installer writes a fuller file and derives stack-aware values such as `TSN_STACK_NAME`, `TSN_CORS_ORIGINS`, and local `TSN_AUTH_RATE_LIMIT` automatically:

```env
# Security — required
JWT_SECRET_KEY=<generated>        # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
TSN_MASTER_KEY=<generated>        # Fernet key wrapping per-service encryption keys

# Stack identity
TSN_STACK_NAME=tsushin

# PostgreSQL — required
# Compose derives DATABASE_URL from TSN_STACK_NAME/POSTGRES_PASSWORD; set explicitly for manual deployments
DATABASE_URL=postgresql+asyncpg://tsushin:<password>@tsushin-postgres:5432/tsushin
POSTGRES_PASSWORD=<generated>

# Docker-in-Docker — required for MCP/toolbox container mounts
HOST_BACKEND_DATA_PATH=/absolute/host/path/to/backend/data

# URLs
TSN_BACKEND_URL=http://localhost:8081
TSN_FRONTEND_URL=http://localhost:3030
TSN_CORS_ORIGINS=http://localhost:3030,http://127.0.0.1:3030
TSN_AUTH_RATE_LIMIT=30/minute     # recommended local/self-signed default

# Logging & metrics
TSN_LOG_LEVEL=INFO                # DEBUG | INFO | WARNING | ERROR
TSN_LOG_FORMAT=text               # text | json (structured)
TSN_METRICS_ENABLED=true
```

**LLM provider API keys are configured per-tenant through the Hub UI**, not in environment variables — this enables true multi-tenant isolation. See [docs/DOCUMENTATION.md §19 LLM Providers](docs/DOCUMENTATION.md#19-llm-providers).

**Operational notes for WhatsApp:**
- Prefer `docker compose build --no-cache backend` followed by `docker compose up -d backend` (and the equivalent frontend commands) instead of `docker compose down`. The external `tsushin-network` now survives `down`, but routine rebuilds should still avoid tearing down the compose services.
- Hub → Communication now exposes dedicated **QA Tester** controls for the current tester target and also lists runtime tester rows in the main WhatsApp table, so QA sessions stay visible without mixing them into normal agent operations.
- Graph View now distinguishes explicit WhatsApp bindings, resolved-default bindings, and ambiguous/unassigned states; if an agent has WhatsApp enabled but no wire, check for the `WhatsApp Unassigned` warning node instead of assuming the graph failed to load.

→ Complete env-var reference (80+ variables, all defaults, all subsystems): [Appendix A](docs/DOCUMENTATION.md#29-appendix-a-complete-environment-variable-reference).

---

## Contributing

Contributions are welcome. See [docs/CONTRIBUTING.md](docs/CONTRIBUTING.md) for branching strategy, code style, and PR guidelines. Pre-commit hooks protect against accidental secret commits:

```bash
./scripts/setup-hooks.sh
```

---

## License

Tsushin is open-source software licensed under the [MIT License](LICENSE).

## Author

**Marcos Vinicios Penha** — [@iamveene](https://github.com/iamveene) 🇧🇷

---

**Version 0.6.0** · [Docs Index](docs/README.md) · [Changelog](docs/CHANGELOG.md) · [Documentation](docs/DOCUMENTATION.md) · [User Guide](docs/USER_GUIDE.md)
