<p align="center">
  <img src="images/tsushin-banner.png" alt="Tsushin Banner" width="100%">
</p>

<p align="center">
  <a href=""><img src="https://img.shields.io/badge/status-beta-orange" alt="Status"></a>
  <a href=""><img src="https://img.shields.io/badge/version-v0.6.0-blue" alt="Version"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

**Tsushin** (通信 - "Communication" in Japanese) is a multi-tenant agentic messaging framework with RBAC, multi-agent orchestration, semantic memory, autonomous workflows, AI-powered security, and full observability — designed to be an enterprise-grade SaaS in the future.

---

## Quick Start

### Prerequisites
- **Docker & Docker Compose** (Docker Desktop on macOS/Windows)
- **Python 3.8+** with **pip** (for installer)
- **Git**
- **Supported platforms:** Linux, macOS, Windows 10+

> **Note:** The Docker network `tsushin-network` must exist before running `docker-compose up`. The installer creates it automatically. For manual setup: `docker network create tsushin-network`.

> The installer automatically installs required Python packages (`requests`, `cryptography`) via pip.

### Installation

```bash
# 1. Clone Repository
git clone https://github.com/iamveene/tsushin.git
cd tsushin

# 2. Run Installer
python3 install.py          # macOS
python3 install.py          # Linux (ensure user is in the docker group)
python install.py           # Windows (PowerShell or CMD)

# 3. Access
# Frontend: http://localhost:3030
# Playground: http://localhost:3030/playground
```

The installer will guide you through configuration, deploy Docker containers, and set up your initial tenant and agents.

---

## Key Features

### Multi-Agent Orchestration
- Multiple agents with distinct personalities
- Per-agent memory isolation (isolated, channel, shared)
- Custom keyword triggers and contact mappings
- Persona templates with role, tone, skills, tools, and knowledge configuration
- Reusable tone presets for communication styles
- Contact management with WhatsApp/Telegram ID mapping and agent routing

### 4-Layer Memory Architecture
1. **Working Memory** - Ring buffer (last N messages)
2. **Episodic Memory** - Vector search over conversation history
3. **Semantic Knowledge** - Learned facts with confidence scoring
4. **Shared Memory Pool** - Cross-agent knowledge sharing

### Multi-Provider AI
| Provider | Local | API Key | Notes |
|----------|:-----:|:-------:|-------|
| Google Gemini | No | Required | Default provider |
| Anthropic Claude | No | Required | Claude 3.5+ |
| OpenAI | No | Required | GPT-4o, GPT-4 Turbo |
| Groq | No | Required | Ultra-fast inference (Llama, Mixtral) |
| Grok (xAI) | No | Required | Grok 3, Grok 3 Mini |
| DeepSeek | No | Required | DeepSeek-V3, DeepSeek-R1 |
| Ollama | Yes | Not needed | 100% local, free |
| OpenRouter | No | Required | 100+ models via single API |

- **Multi-instance support**: Multiple named instances per provider with independent API keys and base URLs
- **Custom URL rebase**: Connect to LiteLLM, vLLM, LocalAI, or any OpenAI-compatible proxy

**TTS Providers:**

| Provider | Type | Notes |
|----------|------|-------|
| Kokoro | Local/self-hosted | Free, PTBR support |
| OpenAI | Cloud | Premium voices |
| ElevenLabs | Cloud | Neural TTS, voice cloning, 25+ languages |

### Skills (20 Built-in)
| Skill | Description |
|-------|-------------|
| Audio Transcription | Whisper API voice-to-text |
| Audio TTS | Multi-provider text-to-speech (Kokoro, OpenAI) |
| Web Search | Multi-provider search (Brave Search, SerpAPI) |
| Web Scraping | Content extraction from web pages |
| Browser Automation | AI-powered web browser control |
| Image Generation | AI-powered image generation and editing |
| Shell | Remote command execution with approval workflow |
| Flows | Automated multi-step workflows |
| Automation | Multi-step workflow orchestration |
| Gmail | Email integration with filters |
| Adaptive Personality | Mirror user communication style |
| Knowledge Sharing | Cross-agent fact extraction |
| Agent Switcher | Switch agents via conversation |
| Flight Search | Amadeus and Google Flights search |
| Sandboxed Tools | Master toggle for Docker-isolated tool access |

### Sentinel Security System
AI-powered threat detection using LLM-based semantic analysis.

| Detection Type | Description |
|---|---|
| Prompt Injection | Detects instruction override attempts |
| Agent Takeover | Detects identity hijacking and impersonation |
| Poisoning | Detects gradual manipulation attacks |
| Shell Malicious | Detects malicious intent in shell commands |
| Memory Poisoning (MemGuard) | Pre-storage regex + fact validation gate |

- **Security Profiles**: Granular per-tenant/agent/skill profiles (Off, Permissive, Moderate, Aggressive)
- Hierarchical inheritance with per-scope overrides
- Configurable modes: **block**, **warn**, **detect_only**
- Aggressiveness levels (0-3: Off, Moderate, Aggressive, Extra Aggressive)
- Exception and allowlist management (network targets, patterns, tools)
- Per-agent security overrides with tenant-level defaults
- Real-time security event feed in Watcher
- WhatsApp notifications for security events

### Sandboxed Tools
Per-tenant isolated Docker containers for running security and utility tools.

| Tool | Description |
|------|-------------|
| nmap | Network exploration and security auditing |
| nuclei | Vulnerability scanning with templates |
| katana | Web crawling for endpoint discovery |
| httpx | HTTP probing and analysis |
| subfinder | Subdomain discovery |
| dig | DNS lookup |
| whois_lookup | Domain information |
| sqlmap | SQL injection testing |
| webhook | HTTP requests via curl |

- Custom tool creation via YAML manifests
- Per-tenant container isolation
- Package management (pip, apt)
- Workspace directory support
- Execution history with logs
- Container commit for persistence

### Shell Access
- Remote command execution with approval workflow
- Security pattern detection with risk levels (low/medium/high/critical)
- YOLO mode for trusted environments (auto-approve)
- Allowed commands and paths whitelisting
- Execution history with stdout/stderr capture

### Flows
Automated multi-step workflow engine.

| | |
|---|---|
| **Flow Types** | Conversation, Notification, Workflow, Task |
| **Execution** | Immediate, Scheduled, Recurring |
| **Step Types** | Conversation, Message, Notification, Tool, Skill, Summarization, Slash Command |

- Template-based flow creation
- Variable interpolation
- Multi-turn conversation support within flows
- Skill integration (flights, web search, and more)
- Flow execution history and status tracking

### Watcher (Observability)
Real-time monitoring and analytics platform.

| Tab | Purpose |
|-----|---------|
| Dashboard | KPIs, activity timeline, system performance, distribution charts |
| Conversations | Live conversation feed with filtering |
| Flows | Flow execution tracking and status |
| Billing | Token usage and cost analytics per agent/model |
| Security | Sentinel threat events with severity filtering |
| Graph View | Network visualization (agents, users, projects) |

**Graph View** provides interactive system topology visualization with Dagre auto-layout, node expansion/collapse, multiple view types (agents, users, projects), and fullscreen mode.

### Studio
- **Projects** - Isolated knowledge workspaces with per-project knowledge bases, semantic memory, factual learning, conversation isolation, and multi-agent access control. Supports configurable embedding models (local MiniLM/MPNet, OpenAI, Gemini).
- **Personas** - Reusable personality templates with role description, tone presets, personality traits, per-persona skills/tools/knowledge, and guardrails
- **Contacts** - Contact management with WhatsApp/Telegram ID mapping, agent routing, and DM trigger configuration

### Hub Integrations
| Category | Integrations |
|----------|-------------|
| AI Providers | Gemini, Claude, OpenAI, Groq, Grok, DeepSeek, Ollama, OpenRouter |
| Communication | WhatsApp, Telegram, Slack, Discord |
| Productivity | Asana, Google Calendar |
| Developer Tools | Shell, Browser Automation |
| Tool APIs | Brave Search, SerpAPI, Amadeus |
| TTS Providers | Kokoro, OpenAI, ElevenLabs |
| MCP Servers | SSE, HTTP Streamable, Stdio transports |

### Playground
Interactive agent chat interface for development and testing.
- Thread management with conversation history
- Audio recording and transcription
- Document attachments (PDF, DOCX, TXT, CSV, JSON)
- Expert mode for advanced users
- Command palette with slash commands
- Knowledge panel and memory inspector
- Tool sandbox for testing tool invocations
- Token-by-token streaming via WebSocket with auto-reconnect
- Async message queuing with dead-letter retry
- Auto-save drafts per thread (restored on switch)
- Smart paste: auto-detects JSON/code and wraps in markdown fences
- Project session support

### Knowledge Management
- Document upload (PDF, TXT, DOCX, CSV, JSON)
- Semantic search with configurable embedding models (local, OpenAI, Gemini)
- Per-agent and per-project knowledge bases
- Knowledge sharing across agents
- Automatic chunking and embedding

### Public API v1
Programmatic REST API for external applications.
- OAuth2 Client Credentials + Direct API Key authentication
- 32 endpoints: Agents CRUD, Chat (sync/async/SSE streaming), Threads, Flows, Hub, Studio
- Rate limiting with `X-RateLimit-*` headers
- 5 API roles with granular permission scopes
- OpenAPI documentation at `/docs` (Swagger UI)
- Per-client request audit logging

### Agent Studio (Visual Builder)
- React Flow canvas with drag-and-drop agent configuration
- Attach/detach: Personas, Channels, Skills, Tools, Security Profiles, Knowledge
- Atomic batch save with inline config editing
- Agent cloning for quick duplication

### Slash Command Access Control
- Per-contact slash command permissions (enabled/disabled/tenant default)
- Tenant-level default policy: `enabled_for_known`, `enabled_for_all`, `disabled`
- `@agent /command` support in WhatsApp/Telegram groups

### Custom Skills
- **Instruction skills**: Inject domain knowledge and behavioral rules into agent prompts
- **Script skills**: Python/Bash/Node.js scripts executed in per-tenant sandboxed containers
- **MCP Server skills**: Connect external MCP servers as tool providers (SSE, HTTP, Stdio transports)
- Sentinel scanning at save time with dedicated "Custom Skill Scan" profile
- Agent assignment with per-skill config, flow builder integration
- Binary allowlist for Stdio transport (uvx, npx, node)

### SSL/HTTPS
- Caddy reverse proxy with 3 modes: Let's Encrypt, manual certs, self-signed
- Automatic HTTP→HTTPS redirect and WSS auto-detection
- Built into installer with domain validation

### Cloud-Native / GKE Deployment
- Helm chart for Google Kubernetes Engine deployment (`k8s/tsushin/`)
- Observability endpoints: `/api/readiness` (K8s readiness probe), `/metrics` (Prometheus)
- Structured JSON logging via `TSN_LOG_FORMAT=json`
- **K8sRuntime** — fully implemented Kubernetes container backend, mapping Docker operations to K8s Deployments, Services, and exec API. Activated via `TSN_CONTAINER_RUNTIME=kubernetes`
- **GCPSecretProvider** — fully implemented Google Secret Manager backend with thread-safe TTL cache, parallel warm-up, and three-tier fallback (GCP, env, default). Activated via `TSN_SECRET_BACKEND=gcp`
- Local Docker Compose development is completely unaffected — both providers default to Docker/env
- CI/CD pipeline for GKE with Cloud SQL Proxy, HPA, network policies, and managed TLS

### Multi-Tenancy & RBAC
- Organization isolation with complete data separation
- Role-based access control (Owner, Admin, Member, Read-only)
- 64+ granular permissions with visual permission matrix
- Team management

### Audit Logging & Compliance
- Tenant-scoped audit events with 30+ event types (auth, CRUD, security, team)
- JSONB structured details, severity levels, channel tracking
- Advanced filtering (action, severity, channel, date range) with CSV export
- Per-tenant retention policies (configurable days)
- **Syslog streaming**: RFC 5424 forwarding via TCP, UDP, or TLS to external syslog servers
- Per-tenant syslog configuration with event category filtering and circuit breaker
- Background forwarder worker with connection pooling and batch processing

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
│  │              │     │               │     │                     │         │
│  │ Agent Engine │     │ AI Providers  │     │ Agents   Personas   │         │
│  │ 20 Skills    │     │ Comm Channels │     │ Contacts Projects   │         │
│  │ AI Classifier│     │ Tool APIs     │     │ Tone Presets        │         │
│  │ Sentinel     │     │ TTS Providers │     │ Knowledge Bases     │         │
│  └──────┬───────┘     └───────┬───────┘     └─────────────────────┘         │
│         │                     │                                              │
│         ▼                     ▼                                              │
│  ┌──────────────┐     ┌───────────────┐     ┌─────────────────────┐         │
│  │    FLOWS     │     │    MEMORY     │     │      WATCHER        │         │
│  │              │     │               │     │                     │         │
│  │ 4 Flow Types │     │ Working       │     │ Dashboard  Billing  │         │
│  │ 7 Step Types │     │ Episodic      │     │ Convos     Security │         │
│  │ Scheduler    │     │ Semantic      │     │ Flows    Graph View │         │
│  │ Templates    │     │ Shared        │     │                     │         │
│  └──────────────┘     └───────────────┘     └─────────────────────┘         │
│                                                                              │
│  ┌──────────────────────────────┐     ┌──────────────────────────────────┐   │
│  │       SANDBOXED TOOLS        │     │           CHANNELS               │   │
│  │  Per-tenant Docker isolation  │     │  WhatsApp │ Telegram │ Slack    │   │
│  │  9 pre-installed tools        │     │  Discord  │ Playground          │   │
│  └──────────────────────────────┘     └──────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Development Setup

### Pre-commit Hooks (Recommended)

We use pre-commit hooks to prevent secrets from being committed to the repository.

```bash
# One-time setup
./scripts/setup-hooks.sh

# Or manually:
pip install pre-commit
brew install gitleaks  # macOS
pre-commit install
```

The hooks will automatically scan for:
- API keys (Anthropic, OpenAI, Google, Brave, etc.)
- Private keys (SSH, PGP, RSA)
- JWT secrets and encryption keys
- High-entropy strings that look like credentials

**Handling False Positives:**
1. Verify it's not an actual secret
2. Add the pattern to `.gitleaks.toml` allowlist
3. For test files, use obvious fake values like `test-key-12345`

**Emergency Bypass** (use sparingly):
```bash
git commit --no-verify -m "docs: update example"
```

---

## Configuration

Essential environment variables (`.env`):

```env
# Security (Required)
JWT_SECRET_KEY=your-secret-key

# PostgreSQL Database (Required)
DATABASE_URL=postgresql+asyncpg://tsushin:<password>@tsushin-postgres:5432/tsushin
POSTGRES_PASSWORD=your_secure_password_here

# Cloud-Native (Optional — for GKE/K8s deployments)
TSN_LOG_FORMAT=text            # text (default) or json (structured logging)
TSN_METRICS_ENABLED=false      # Enable Prometheus /metrics endpoint
TSN_CONTAINER_RUNTIME=docker   # docker (default) or kubernetes
TSN_SECRET_BACKEND=env         # env (default) or gcp (Google Secret Manager)

# Kubernetes Runtime (only when TSN_CONTAINER_RUNTIME=kubernetes)
TSN_K8S_NAMESPACE=tsushin              # K8s namespace for workloads
TSN_K8S_IMAGE_PULL_POLICY=IfNotPresent # Image pull policy (Always, IfNotPresent, Never)

# GCP Secret Manager (only when TSN_SECRET_BACKEND=gcp)
TSN_GCP_PROJECT_ID=my-project          # GCP project ID
TSN_GCP_SECRET_PREFIX=tsushin_         # Prefix for secret names in Secret Manager
TSN_GCP_SECRET_CACHE_TTL=300           # Cache TTL in seconds (default: 300)
TSN_GCP_SECRET_VERSION=latest          # Secret version (default: latest)

# Watcher
TSN_WATCHER_MAX_CATCHUP_SECONDS=60    # Max catchup window after container rebuild
```

LLM provider API keys are configured per-tenant through the Hub interface, not in environment variables. This allows multi-tenant isolation where each organization manages their own AI provider credentials.

See `env.docker.example` for all available options.

---

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details on how to get started.

---

## License

Tsushin is open source software licensed under the [MIT License](LICENSE).

---

## Author

**Marcos Vinicios Penha** 🇧🇷

---

**Version 0.6.0** | **Last Updated:** March 2026
