<p align="center">
  <img src="images/tsushin-banner.png" alt="Tsushin Banner" width="100%">
</p>

<p align="center">
  <a href=""><img src="https://img.shields.io/badge/status-beta-orange" alt="Status"></a>
  <a href=""><img src="https://img.shields.io/badge/version-v0.6.0-blue" alt="Version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

**Tsushin** (通信 — "Communication" in Japanese) is a multi-tenant agentic messaging platform that unifies AI agent orchestration, conversational channels, semantic memory, workflow automation, AI-powered security, and observability — self-hostable, with RBAC and full multi-tenancy.

> 📖 **Full reference:** see **[documentation.md](documentation.md)** for the exhaustive guide covering every configuration item, feature, form field, channel, integration, API endpoint, and appendix.

---

## Feature Highlights

- **Multi-agent orchestration** — per-agent personas, tone presets, memory modes (isolated / channel / shared), keyword triggers, and dynamic agent switching.
- **6 channels** — WhatsApp (WAHA), Telegram, Slack, Discord, HTTP Webhook (HMAC-signed), and a built-in Playground web chat.
- **10+ LLM providers** — OpenAI, Anthropic, Gemini, Groq, Grok, DeepSeek, Ollama, OpenRouter, Vertex AI, and any OpenAI-compatible endpoint. Provider instances are configured per-tenant via the Hub.
- **4-layer memory** — working, episodic, semantic (with temporal decay), and shared memory pool; optional OKG (Ontology Knowledge Graph).
- **Vector stores** — Chroma (default), Pinecone, Qdrant, or MongoDB Atlas.
- **19 built-in skills** — audio TTS/transcription, web search, scraping, browser automation, Gmail, flight search, scheduler, knowledge sharing, OKG terms, sandboxed shell/network tools, and more.
- **Custom skills** — Instruction, Script (Python/Bash/Node), and MCP-server skills, gated by a Sentinel scan at save-time.
- **37 slash commands** — agent management, email (Gmail), web search, shell, thread control, sandboxed tools, flows, scheduler, memory, project context, and system commands — all with per-contact access control.
- **Sandboxed tools** — per-tenant Docker containers with `nmap`, `nuclei`, `dig`, `httpx`, `whois`, `katana`, `subfinder`, `sqlmap`, and a generic webhook tool. Invoked via `/tool <name> <cmd> param=value`.
- **Flows** — 4 flow types (conversation, notification, workflow, task) with immediate, scheduled, or recurring (cron) execution; 7 step types with template-variable interpolation.
- **Sentinel security** — AI-powered detection of prompt injection, agent takeover, poisoning, shell malicious intent, memory poisoning (MemGuard), browser SSRF, and vector-store poisoning. Profiles with block / warn-only / detect-only / off modes.
- **Studio** — visual agent builder, personas, contacts, projects (knowledge isolation), custom skills, and agent-to-agent communication.
- **Playground** — real-time streaming chat, audio recording + Whisper transcription, document uploads, command palette, memory inspector, expert mode.
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

> The Docker network `tsushin-network` must exist before `docker-compose up`. The installer creates it automatically. Manual: `docker network create tsushin-network`.

### Installation

```bash
# 1. Clone
git clone https://github.com/iamveene/tsushin.git
cd tsushin

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

→ Full deployment options, GKE/Helm, GCP Secret Manager, and rebuild-safety rules: see [documentation.md §4 Deployment & Operations](documentation.md#4-deployment--operations).

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
│  │  Next.js 14  │◄───►│ FastAPI + PG 16  │◄───►│  Auth / Tenants / Roles  │  │
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

→ Full container topology, data flow, and dynamically-managed MCP containers: see [documentation.md §2 Architecture Overview](documentation.md#2-architecture-overview).

---

## Documentation Map

| Topic | Section |
|-------|---------|
| Deployment (Compose / GKE / GCP SM) | [§4](documentation.md#4-deployment--operations) |
| Environment variable reference | [§5](documentation.md#5-system-configuration) + [Appendix A](documentation.md#29-appendix-a-complete-environment-variable-reference) |
| Authentication, SSO, RBAC | [§6](documentation.md#6-authentication--access) + [Appendix B](documentation.md#30-appendix-b-permission-scopes) |
| Agents, personas, tone presets | [§7](documentation.md#7-agents), [§8](documentation.md#8-personas--tone-presets) |
| Skills (built-in + custom) & sandboxed tools | [§9](documentation.md#9-skills) |
| Memory, knowledge, vector stores | [§10](documentation.md#10-memory--knowledge), [§11](documentation.md#11-vector-stores) |
| Sentinel security | [§12](documentation.md#12-security--sentinel) |
| Flows & scheduler | [§13](documentation.md#13-flows), [§14](documentation.md#14-scheduler--triggers) |
| Channels (WhatsApp / Telegram / Slack / Discord / Webhook / Playground) | [§15](documentation.md#15-channels) |
| Contacts, projects, playground | [§16](documentation.md#16-contacts--channel-mapping), [§17](documentation.md#17-projects-studio), [§18](documentation.md#18-playground) |
| LLM providers & hub integrations | [§19](documentation.md#19-llm-providers), [§20](documentation.md#20-hub-integrations) |
| Settings UI (every subpage) & system admin | [§21](documentation.md#21-settings--ui-taxonomy), [§22](documentation.md#22-system-admin-global-admin-only) |
| Audit & syslog | [§23](documentation.md#23-audit-logging--compliance) |
| Observability & metrics | [§24](documentation.md#24-observability) |
| Public API v1 reference | [§25](documentation.md#25-public-api-v1) |
| Slash commands (37 commands + usage examples) | [§26](documentation.md#26-slash-commands-system-wide-catalog) |
| Troubleshooting | [§28](documentation.md#28-troubleshooting) |

---

## Essential Configuration

Minimal `.env` for a fresh deployment (the installer generates these automatically):

```env
# Security — required
JWT_SECRET_KEY=<generated>        # python3 -c "import secrets; print(secrets.token_urlsafe(32))"
TSN_MASTER_KEY=<generated>        # Fernet key wrapping per-service encryption keys

# PostgreSQL — required
DATABASE_URL=postgresql+asyncpg://tsushin:<password>@tsushin-postgres:5432/tsushin
POSTGRES_PASSWORD=<generated>

# Docker-in-Docker — required for MCP/toolbox container mounts
HOST_BACKEND_DATA_PATH=/absolute/host/path/to/backend/data

# URLs
TSN_BACKEND_URL=http://localhost:8081
TSN_FRONTEND_URL=http://localhost:3030
TSN_CORS_ORIGINS=*                # restrict in production

# Logging & metrics
TSN_LOG_LEVEL=INFO                # DEBUG | INFO | WARNING | ERROR
TSN_LOG_FORMAT=text               # text | json (structured)
TSN_METRICS_ENABLED=true
```

**LLM provider API keys are configured per-tenant through the Hub UI**, not in environment variables — this enables true multi-tenant isolation. See [documentation.md §19 LLM Providers](documentation.md#19-llm-providers).

→ Complete env-var reference (80+ variables, all defaults, all subsystems): [Appendix A](documentation.md#29-appendix-a-complete-environment-variable-reference).

---

## Contributing

Contributions are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md) for branching strategy, code style, and PR guidelines. Pre-commit hooks protect against accidental secret commits:

```bash
./scripts/setup-hooks.sh
```

---

## License

Tsushin is open-source software licensed under the [MIT License](LICENSE).

## Author

**Marcos Vinicios Penha** — [@iamveene](https://github.com/iamveene) 🇧🇷

---

**Version 0.6.0** · [Changelog](CHANGELOG.md) · [Roadmap](ROADMAP.md) · [Documentation](documentation.md)
