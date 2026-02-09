# Tsushin — Think, Secure, Build

> **Multi-Tenant Agentic Framework**

[![Status](https://img.shields.io/badge/status-beta-orange)]()
[![Version](https://img.shields.io/badge/version-v0.5.0--beta-blue)]()
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Tsushin** (通信 - "Communication" in Japanese) is a multi-tenant agentic messaging framework with RBAC, multi-agent orchestration, semantic memory, autonomous workflows, AI-powered security, and full observability — designed to be an enterprise-grade SaaS in the future.

---

## Quick Start

### Prerequisites
- **Docker & Docker Compose** (Docker Desktop on macOS/Windows)
- **Python 3.8+** with **pip** (for installer)
- **Git**
- **Supported platforms:** Linux, macOS, Windows 10+

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
| Provider | Local | API Key |
|----------|:-----:|:-------:|
| Google Gemini | No | Required |
| Anthropic Claude | No | Required |
| OpenAI | No | Required |
| Ollama | Yes | Not needed |
| OpenRouter | No | Required |

OpenRouter provides access to 100+ models through a unified API.

**TTS Providers:**

| Provider | Type |
|----------|------|
| Kokoro | Local/self-hosted |
| OpenAI | Cloud |

### Skills (16 Built-in)
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
| Weather | Multi-provider weather information |
| Sandboxed Tools | Master toggle for Docker-isolated tool access |

### Sentinel Security System
AI-powered threat detection using LLM-based semantic analysis.

| Detection Type | Description |
|---|---|
| Prompt Injection | Detects instruction override attempts |
| Agent Takeover | Detects identity hijacking and impersonation |
| Poisoning | Detects gradual manipulation attacks |
| Shell Malicious | Detects malicious intent in shell commands |

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
- Skill integration (weather, flights, and more)
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
| AI Providers | Gemini, Claude, OpenAI, Ollama, OpenRouter |
| Communication | WhatsApp, Telegram |
| Productivity | Asana, Google Calendar |
| Developer Tools | Shell, Browser Automation |
| Tool APIs | Brave Search, SerpAPI, Amadeus, OpenWeather |
| TTS Providers | Kokoro, OpenAI |

### Playground
Interactive agent chat interface for development and testing.
- Thread management with conversation history
- Audio recording and transcription
- Document attachments (PDF, DOCX, TXT, CSV, JSON)
- Expert mode for advanced users
- Command palette with slash commands
- Knowledge panel and memory inspector
- Tool sandbox for testing tool invocations
- Streaming messages via WebSocket
- Project session support

### Knowledge Management
- Document upload (PDF, TXT, DOCX, CSV, JSON)
- Semantic search with configurable embedding models (local, OpenAI, Gemini)
- Per-agent and per-project knowledge bases
- Knowledge sharing across agents
- Automatic chunking and embedding

### Multi-Tenancy & RBAC
- Organization isolation with complete data separation
- Role-based access control (Owner, Admin, Member, Read-only)
- 50+ granular permissions with visual permission matrix
- Team management

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                           TSUSHIN PLATFORM                                   │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────────┐     ┌──────────────────────────┐  │
│  │ Frontend UI  │     │   Backend API    │     │      RBAC Layer          │  │
│  │  Next.js 14  │◄───►│    FastAPI       │◄───►│  Auth / Tenants / Roles  │  │
│  └──────────────┘     └────────┬─────────┘     └──────────────────────────┘  │
│                                │                                             │
│         ┌──────────────────────┼──────────────────────────┐                  │
│         │                      │                          │                  │
│         ▼                      ▼                          ▼                  │
│  ┌──────────────┐     ┌───────────────┐     ┌─────────────────────┐         │
│  │     CORE     │     │      HUB      │     │       STUDIO        │         │
│  │              │     │               │     │                     │         │
│  │ Agent Engine │     │ AI Providers  │     │ Agents   Personas   │         │
│  │ 16 Skills    │     │ Comm Channels │     │ Contacts Projects   │         │
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
│  │  Per-tenant Docker isolation  │     │  WhatsApp (MCP)  │  Telegram    │   │
│  │  9 pre-installed tools        │     │  Playground      │              │   │
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

**Version 0.5.0-beta** | **Last Updated:** February 2026
