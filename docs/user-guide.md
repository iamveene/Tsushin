# Tsushin User Guide

This guide walks you through using the Tsushin platform from a user's perspective -- setting up channels, creating agents, building workflows, and everything in between. For the exhaustive technical reference (internal architecture, model schemas, environment variables, appendices), see [documentation.md](documentation.md).

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [LLM Providers and Hub](#2-llm-providers-and-hub)
3. [Creating and Configuring Agents](#3-creating-and-configuring-agents)
3a. [Agent Teams](#3a-agent-teams)
4. [Personas and Tone Presets](#4-personas-and-tone-presets)
5. [Skills](#5-skills)
6. [Setting Up Communication Channels](#6-setting-up-communication-channels)
6a. [Setting Up Event Triggers (v0.7.0)](#6a-setting-up-event-triggers-v070)
7. [Managing Contacts](#7-managing-contacts)
8. [Using the Playground](#8-using-the-playground)
9. [Flows (Workflow Automation)](#9-flows-workflow-automation)
10. [Scheduler](#10-scheduler)
11. [Projects (Knowledge Isolation)](#11-projects-knowledge-isolation)
12. [Memory and Knowledge](#12-memory-and-knowledge)
13. [Security -- Sentinel](#13-security----sentinel)
13a. [Watcher Reference](#13a-watcher-reference)
14. [Settings Reference](#14-settings-reference)
15. [Slash Commands Reference](#15-slash-commands-reference)
16. [Using the Public API](#16-using-the-public-api)
17. [Audit and Compliance](#17-audit-and-compliance)
18. [Remote Access (System Administrators)](#18-remote-access-system-administrators)

---

## 1. Getting Started

Welcome to Tsushin -- your multi-tenant AI agent platform. This section walks you through going from zero to your first AI conversation.

### For Administrators: Installer Options (v0.6.0)

If you're the administrator installing Tsushin for your organization, run `python3 install.py` from the repository root. v0.6.0 adds three installer behaviors worth knowing about:

- **`--le-staging`** -- when combined with `--domain` and `--email`, uses the Let's Encrypt **staging** directory instead of production. Use this to rehearse the full ACME flow without burning your production rate-limit budget (LE limits you to ~5 failed challenges per domain per hour on production). Example: `python3 install.py --defaults --domain app.example.com --email you@example.com --le-staging`.
- **IP-address installs now work correctly.** The self-signed SAN now emits `IP:<addr>,DNS:localhost,IP:127.0.0.1,IP:::1` (the old format `DNS:<IP>` was rejected by browsers and curl). If you're accessing Tsushin by IP (e.g., `https://10.0.0.5`), the installer detects a stale SAN from a prior run and regenerates automatically.
- **Frontend rebuild on API URL change.** If you rerun the installer and change `NEXT_PUBLIC_API_URL`, the installer diffs the previous `.env` and rebuilds the frontend image with `--no-cache`. Previously it would silently ship a stale cached bundle and leave the UI pointing at the old URL.

Full installer reference, GKE/Helm, GCP Secret Manager, and `.env` details live in [documentation.md §3 Quick Start](documentation.md#3-quick-start) and [§4 Deployment & Operations](documentation.md#4-deployment--operations).

### First Login and Setup Wizard

When you open Tsushin for the first time, you will be greeted by the **Setup Wizard**. This one-time process creates your organization and your administrator account.

1. Open your Tsushin URL in a browser (for example, `https://localhost` or the URL provided by your administrator).
2. You will be redirected to the `/setup` page automatically.
3. Fill in your **name**, **email address**, and **password** to create your admin account.
4. Enter your **organization name** -- this becomes your tenant in the system.
5. Click **Complete Setup**. You are now logged in as the organization owner.

During setup, Tsushin automatically creates provider instances for any supported API keys you enter and assigns the selected primary provider as the initial **System AI**. The completion screen also reveals an auto-generated **global admin** email/password pair for system-level administration, so make sure to capture it before you leave the page.

After first login, an 8-step onboarding tour highlights Watcher, Studio, Hub, Channels, Flows, Playground, Security, and the final setup checklist.

### Creating Your Organization

Your organization (also called a "tenant") is your isolated workspace. Everything you create -- agents, flows, knowledge bases, integrations -- lives inside it. The setup wizard creates it for you, but you can customize it later:

1. Go to **Settings** (gear icon in the sidebar).
2. Click **Organization**.
3. Here you can update your organization name, view your plan and usage limits, and see current-month usage statistics.
4. Click **Save Changes** when done.

### Setting Up Your First AI Provider

Before your agents can think and respond, you need to connect at least one AI provider (such as OpenAI, Google Gemini, or Anthropic Claude).

1. Navigate to **Hub** in the sidebar.
2. Click on the **Providers** section.
3. Click **Add Provider** and choose your provider type. Supported providers include:
   - **OpenAI** (GPT-4o, GPT-4, GPT-3.5, etc.)
   - **Anthropic** (Claude 4 Opus, Claude 4 Sonnet, etc.)
   - **Google Gemini**
   - **Groq** (fast inference)
   - **Grok** (xAI)
   - **DeepSeek**
   - **Ollama** (local/self-hosted models)
   - **OpenRouter** (multi-provider router)
   - **Vertex AI** (Google Cloud)
   - **Custom** (any OpenAI-compatible endpoint)
4. Give the provider instance a **name** (e.g., "My OpenAI Account").
5. Paste your **API key**.
6. Optionally set a **base URL** if you are using a custom endpoint.
7. Select a **default model** from the list (models are auto-discovered from the provider).
8. Click **Save**.

### Creating Your First Agent

1. Go to **Studio > Agents** in the sidebar.
2. Click **Create New Agent**.
3. Fill in the form:
   - **Agent Name** -- give it a friendly name (e.g., "Customer Support Bot").
   - **System Prompt** -- write instructions that define how the agent should behave.
   - **Model Provider** -- select the provider you just configured.
   - **Model Name** -- pick the specific model.
   - Optionally assign a **Persona** for a pre-built personality and tone.
4. Click **Create**.

### Testing in the Playground

1. Go to **Playground** in the sidebar.
2. Select your newly created agent from the agent dropdown at the top.
3. Type a message and press Enter.
4. The agent will respond using the provider and model you configured.

### Quick-testing with Playground Mini (without leaving the page you're on)

If you're mid-flow on another page — inspecting the Watcher Graph, editing a Flow, reading a dashboard — you don't have to leave to try an agent. **Playground Mini** is a floating chat bubble available on every page:

1. Click the circular chat icon in the **bottom-right** corner (it appears on Watcher, Studio, Hub, Flows, Core, Settings, and System pages). You can also open it anywhere with **Ctrl/Cmd + Shift + L**.
2. Pick an **agent**, optionally a **project**, and either continue an existing **thread** or click **+** for a new one.
3. Type a message and press **Enter** (`Shift+Enter` for a newline). Responses render with full markdown — headings, bullet lists, code blocks, tables, everything.
4. If the conversation gets interesting and you want the full Playground's tools (memory inspector, document attachments, expert mode, streaming, etc.), click the **expand icon** (external-link arrow). You'll land in `/playground` with the same agent and thread already selected and every message preserved — no lost context.
5. Close the bubble with **Esc** or the close button.

Selection (agent, project, thread) persists across page navigation via session storage and resets cleanly on logout.

---

## 2. LLM Providers and Hub

### Configuring AI Providers

Tsushin supports a wide range of AI providers. You can connect as many as you need, and each agent can use a different one.

| Provider | Description |
|---|---|
| OpenAI | GPT-4o, GPT-4, GPT-3.5, and other OpenAI models |
| Anthropic | Claude 4 Opus, Claude 4 Sonnet, Claude Haiku |
| Gemini | Google's Generative AI models |
| Groq | Ultra-fast inference for open models |
| Grok | xAI's models |
| DeepSeek | DeepSeek's reasoning and coding models |
| Ollama | Run open-source models locally on your own hardware |
| OpenRouter | A multi-provider router -- access many models through one API |
| Vertex AI | Google Cloud's enterprise AI platform |
| Custom (OpenAI-compatible) | Any service that speaks the OpenAI API format |

**Adding a Provider Instance:**

1. Go to **Hub > Providers**.
2. Click **Add Provider**.
3. Fill in: **Name**, **Type**, **API Key**, optionally **Base URL**, and **Default Model**.
4. Click **Save**.

You can have multiple instances of the same provider type (e.g., two different OpenAI accounts for different teams).

**Model Discovery and Pricing:**

When you add a provider, Tsushin automatically queries its API to discover available models. To configure cost tracking, go to **Settings > Model Pricing** to set per-model input and output costs (per 1M tokens). These costs appear in the Watcher billing dashboard.

**Anthropic prompt caching (v0.6.0):**

Anthropic requests are automatically **prompt-cached** — Claude caches the stable prefix of each conversation (system prompt, persona, skill catalog, knowledge snippets) and reuses it on subsequent turns. For chat-heavy workloads this typically cuts input token cost by **40–65%** with no configuration required on your end. Cache hits show up in the Playground debug panel as `cache_read_input_tokens`. The default Anthropic model in v0.6.0 is `claude-haiku-4-5` — you can override per-agent in the agent config. Technical details: [documentation.md §19.6](documentation.md#196-anthropic-prompt-caching--v060).

### Hub Integrations

The Hub is your integration marketplace. Beyond AI providers, you can connect external services.

#### Google (Calendar and Gmail)

1. Go to **Settings > Integrations** and enter your Google OAuth Client ID and Client Secret.
2. Go to **Hub > Integrations**, find Google Calendar or Gmail, and click **Connect**.
3. Sign in with your Google account and grant permissions.
4. Enable the **Calendar** or **Gmail** skill on your agents.

#### Asana

1. Go to **Hub > Integrations**, find Asana, and click **Connect**.
2. Authorize via OAuth. Agents with the appropriate skills can list projects, create tasks, and query your workspace.

#### Browser Automation

Two modes: **Playwright** (in-container, no setup needed) or **CDP** (connects to your host Chrome). Configure under **Hub > Integrations**.

#### Password Vault and 1Password

1. Go to **Hub > Tool APIs > Password Vault**.
2. Add a **1Password** service-account connection, set the default vault and optional item/field allowlists, then use **Test**.
3. Open an agent's **Skills** tab or the guided Agent Wizard, add **Password Vault**, choose the 1Password connection, and keep only the required capabilities enabled.
4. In Flows, add a **Password Vault** step or a `password_vault` tool/skill step and select the vault/item/field through the picker. Flow runs persist redacted output, not plaintext secrets.

If **Password Vault** is already attached to an agent, it appears as an active skill card rather than as another option inside **Add Skill**. Use **Configure** on that card to change the provider or capability toggles.

For migrated financial automations, use **Flows > From Template** when a supported provider is available. Templates expand into ordinary editable steps rather than a hidden runner: Password Vault, Browser Automation or HTTP Request, Data Transform, Store/Dedupe, Gate, and Notification. The wizard keeps technical overrides in **Advanced options** by default, so most users only choose the vault reference, agent, channel, and recipient before previewing the visible step graph.

#### TTS Providers (Text-to-Speech)

Three options: **Kokoro** (local, self-hosted), **OpenAI TTS**, or **ElevenLabs**. Configure under **Hub > TTS Providers**, then enable the TTS skill on your agents.

#### ASR Providers (Speech-to-Text) — v0.7.0

Tsushin supports three ASR engines for transcribing inbound audio (WhatsApp voice notes, Playground audio, Telegram voice messages):

| Engine | Where it runs | When to use |
|---|---|---|
| **OpenAI Whisper API** | Cloud (OpenAI). Reuses your tenant's saved OpenAI key. | Default if you already have OpenAI configured and don't mind cloud transcription. |
| **Whisper (local)** | Auto-provisioned container under Hub > Local Services. | Privacy-sensitive deployments — voice data never leaves your infrastructure. CPU-friendly. |
| **Speaches** | Auto-provisioned container under Hub > Local Services. | Local Whisper alternative with different performance profile. |

**Setup (Hub > Add Provider > Speech-to-Text):**

1. Go to **Hub > AI Providers > + New Instance**, pick **Speech-to-Text** as the modality.
2. Choose **Cloud** (OpenAI Whisper API — no extra credentials needed) or **Local** (Whisper or Speaches).
3. For Local: name the instance, optionally pick a GPU profile, and click **Provision**. The container is created with `auto_provision=true`; the wizard polls until it's healthy.
4. Once running, the instance shows up under **Hub > Local Services > Speech-to-Text** with start/stop/restart/logs/status controls.

**Per-agent assignment.** The `audio_transcript` skill on each agent has two modes:

- **`openai`** — call the OpenAI Whisper API directly (requires the OpenAI key in the tenant Hub).
- **`instance`** — pin a specific tenant-owned local ASR instance (requires `asr_instance_id`).

Both Audio Agents Wizard and the agent's Skills tab show a list of every active tenant ASR instance so you can pick which one this agent uses. There is **no global Settings → ASR page** and **no tenant-default ASR** in v0.7.0 — assignment is always explicit at the agent level.

**Cascade-aware delete.** Deleting an ASR instance shows a banner enumerating every agent currently pinned to it. The delete reconciles those agents in the same transaction: pinned skills are repointed to another active ASR instance if one exists; otherwise they are disabled (so the agent stops trying to transcribe via a now-deleted endpoint). The cascade summary appears in the response so the UI surfaces "3 agents reassigned to OpenAI Whisper QA" instead of failing silently.

**Failure-mode honesty (2026-05-06).** If you pin an agent to a local instance, the runtime does **not** silently fall back to the OpenAI cloud Whisper API on failure. The local provider's error surfaces directly so you find out about a stalled or unhealthy local container instead of leaking voice data to a third-party cloud. To use the cloud path explicitly, set `asr_mode='openai'` on the agent.

#### MCP Server Registration

Connect external MCP (Model Context Protocol) tool servers under **Hub > MCP Servers**. Choose SSE (HTTP) or Stdio (local command-line) transport.

---

## 3. Creating and Configuring Agents

Agents are the AI assistants that power your conversations across every channel.

### Agent Form Fields

| Field | Required? | What It Does |
|---|---|---|
| **Agent Name** | Yes | The display name your users will see. |
| **System Prompt** | Yes | Core instructions. Use `{{PERSONA}}` and `{{TONE}}` placeholders for dynamic injection. |
| **Description** | No | A short summary of what this agent does. |
| **Persona** | No | Select a pre-built or custom persona (see Section 4). |
| **Tone Preset / Custom Tone** | No | Choose a tone preset or write custom tone instructions. |
| **Model Provider** | Yes | The AI provider to use. |
| **Model Name** | Yes | The specific model from that provider. |
| **Trigger Keywords** | No | Words that activate this agent in group chats (e.g., "help", "support"). |
| **Avatar** | No | Choose an avatar style (samurai, robot, ninja, etc.). |
| **Active** | -- | Enabled by default. Uncheck to deactivate without deleting. |
| **Default** | -- | Mark as the default agent for new conversations. |

After creating the agent, open it to access six tabs: **Configuration**, **Channels**, **Memory Management**, **Skills**, **Knowledge Base**, and **Shared Knowledge**.

### Channel Configuration

On the **Channels** tab:
1. **Enable channels** -- toggle which conversational channels the agent is available on: Playground, WhatsApp, Telegram, Slack, and Discord. Webhooks are configured separately as event triggers.
2. **Assign integrations** -- for each enabled channel, select the specific integration instance.

### Conversational vs Continuous Agents

Create agents from **Studio**. The Studio Agents page exposes a unified create surface with three options:

- **Agent** (on-demand) — configurable persona + skills + model that replies when you message it. The foundation for the other two.
- **Continuous Agent** (always-on) — wraps an existing Agent so it wakes on a trigger event with daily budget caps. Reactive single-agent execution.
- **Team** (multi-agent) — coordinate multiple agents on one task, sequential (LINE) or collaborative (MESH).

Click **"Compare options"** next to the Create button (or pick directly from the SplitButton dropdown) to open the **kind chooser** modal — a side-by-side card view that explains each surface's bullets, an example use case, and routes you to the correct creation flow. Studio also has a dedicated **Continuous Agents** tab between Personas and Teams for direct creation/management.

The legacy "wake mode" picker in the Agent Wizard still works: choosing **Continuous** during agent creation hands off to the **Continuous Agent setup** screen with the agent pre-selected. There you must provide:

| Field | Required? | What It Does |
|---|---|---|
| **Purpose** | Yes | A 1-2 sentence statement of what the agent is supposed to accomplish per run. Surfaces in Watcher and in the trigger detail. |
| **Action kind** | Yes | What the agent is allowed to do at the end of its run — `notify_only`, `reply`, `tool_use`, `flow_dispatch`. The runtime enforces this; an action_kind=`notify_only` agent cannot accidentally fire arbitrary tools. |
| **Trigger subscriptions** | At least one | Bind the agent to one or more Email/Webhook/Jira/GitHub/Schedule triggers (or wake events) — the agent only runs when one of these fires. |
| **Delivery + budget policy** | Optional | Per-run token / wall-clock / cost ceilings; aggregation rules if multiple wake events arrive close together. |

**Watching Continuous Agent runs.** Open **Watcher → Agents → Continuous Agents** for the tenant-wide run history. Each row shows the wake event that triggered the run, the run status (`pending`, `running`, `completed`, `failed`, `sentinel_blocked`, `cancelled`), input summary, output, token + cost, and links to the originating trigger and dispatched flow (if any). The Watcher Agents tab nests five related run-time surfaces — Continuous Agents, Wake Events, Conversations, Team Runs, and A2A Comms — so you can move between agent inventory and recent activity without leaving the page.

**Deleting a Continuous Agent.** If subscriptions or active runs still reference the agent, the delete attempt returns a structured `409 Conflict` with a JSON body that names the blockers and surfaces an actionable cleanup prompt in the UI ("Detach 2 trigger subscriptions and cancel 1 active run, then retry"). The wizard offers to do the cleanup for you instead of failing silently.

### Memory Configuration

On the **Memory Management** tab:

| Setting | What It Does |
|---|---|
| **Memory Isolation Mode** | `Isolated` (per-user, default), `Shared` (all users share), or `Channel Isolated` (per-channel). |
| **Memory Size** | Recent messages kept in working memory. Leave blank for system default. |
| **Semantic Search** | Enable meaning-based recall of older conversations (default: on). |
| **Semantic Search Results** | Max past memories retrieved per query (default: 10). |
| **Similarity Threshold** | Minimum match score for retrieval (0.0-1.0; default: 0.5). |
| **Temporal Decay** | Older memories gradually lose importance (default: off). |
| **Decay Rate** | Speed of memory fading (default: 0.01 = ~69-day half-life). |
| **MMR Diversity Weight** | Balances relevance vs. diversity (0-1; default: 0.5). |

### Trigger Overrides

Per-agent settings that override your tenant's global defaults. Leave blank to inherit the default.

| Setting | What It Does |
|---|---|
| **DM Auto-Response** | Enable/disable auto-response to direct messages from unknown senders. |
| **Group Filters** | Restrict which groups this agent monitors (e.g., `["Support Group", "VIP Chat"]`). |
| **Number Filters** | Restrict which phone numbers this agent responds to. |
| **Context Message Count** | How many recent group messages the agent reads for context. |
| **Context Character Limit** | Maximum character length of the context window. |

### Cloning Agents

Use the **Clone** action on the Agents list to duplicate an agent with all configuration -- system prompt, persona, skills, memory settings, and channel bindings.

### Multi-Agent Orchestration

Two built-in skills for agents to work together:

- **Agent Switcher** -- lets users switch their default agent via natural language (e.g., "Switch me to the Support agent"). **Default execution mode in v0.6.0 is `hybrid`** — both the keyword trigger ("Switch me to ...") and the LLM tool call work, so deterministic phrasings never miss and the LLM can also route on intent.
- **Agent Communication (A2A)** -- allows agents to ask other agents questions, discover agents, or delegate tasks.

Manage inter-agent messaging from **Studio > Agent Communication**.

---

## 3a. Agent Teams

An **Agent Team** is a group of agents that work together on a single goal under one of two topologies. Agent Teams ship in v0.7.0 (Phases 1-10) and are reachable from **Studio > Teams**.

### Why Teams (vs. a single agent)?

- A single agent does one thing well; a team can split work across specialists (e.g., a researcher, an analyst, a writer).
- The team has its own Sentinel profile override so you can dial security up for sensitive multi-step workflows without touching the underlying agents.
- Watcher shows the **Team Run** as a single audited unit with member-run breakdown, so you can answer "what did the team do for that ticket" with one click instead of cross-referencing per-agent logs.

### Topologies

- **Line** — members run in a fixed order. Each member sees the prior summary; the final member produces the team output. Predictable, deterministic, easy to debug. Use this when the workflow is "research → analyze → write" or any sequential pipeline.
- **Mesh** — a hidden internal **coordinator** agent decides which member to dispatch next from a JSON command (`dispatch`, `finish`, or `escalate`). The coordinator is `is_internal=true` and never shows up in agent lists, agent palettes, or A2A surfaces. Use mesh when the workflow is dynamic ("triage this ticket and pick the right specialist") or when you need branching.

### Creating a Team

From **Studio > Teams** click **+ New Team** to open the Team Wizard:

1. **Custom or Template** — start from scratch or pick a preset (e.g., "Triage + Reply", "Research → Write").
2. **Basics** — name, description, topology (line vs mesh), `max_concurrent_runs`, `max_steps`, `max_total_tokens`, wall-clock timeout.
3. **Topology** — confirm the topology; mesh teams render the hidden coordinator on the canvas with a lock icon.
4. **Members** — drag agents from the global agent palette (internal coordinators are filtered out). For line teams set `execution_order`; for mesh set `is_required` per member.
5. **Triggers** — bind active Webhook, GitHub, Jira, or Gmail trigger instances. (The Phase 6 restriction that excluded Gmail was lifted on 2026-05-07.)
6. **Review** — summary cards for every prior step.
7. **Create** — persists the team, its members, and trigger bindings in one transaction. You land on the new Team Builder.

### Editing in the Team Builder

`/studio/teams/{id}` is a five-tab Team Builder shell:

- **Topology** — React Flow canvas with line and mesh layouts, coordinator/member nodes with expandable details, drag-to-add agent membership, line reordering, node position persistence, remove/toggle-required actions. Read-only while a run is active.
- **Triggers** — add, edit, or remove trigger bindings after creation. Useful when a team was created without triggers in the wizard or when you need to swap the bound instance.
- **Sentinel** — choose a team-level Sentinel profile that overrides the per-member or tenant default during team-run start and handoff checks. Clearing the field falls back to the existing inherited profile chain.
- **Runs** — manual run start (with goal text), run history, run drilldown with member-run timeline, output summaries, token/cost metadata, Sentinel decision JSON, mesh coordinator command log, and cancel actions.
- **Settings** — name/description editing, topology guardrails, archive (soft-delete; preserves run history) and **Delete permanently** (only available on archived teams; requires retyping the team name).

### Watching Team Runs

Open **Watcher → Agents → Team Runs** for the tenant-wide run history across every team you can see. The page filters by team, status (`pending`, `running`, `completed`, `failed`, `sentinel_blocked`, `cancelled`), and date range. Each row updates live via WebSocket — start a manual run from Team Builder and watch the row tick from `pending` to `running` to a final status without a refresh.

Click a row for the detail panel:
- Ordered run timeline + member-run cards (each with input, output, token usage, Sentinel decision).
- Mesh coordinator command log when applicable.
- Trigger or wake-event origin (so you can jump to the bound trigger).
- Final output, errors, token + cost summary.

### Trigger payload context (2026-05-07)

The orchestrator now loads the originating wake event's payload doc plus a short summary string at the start of every team run and threads them into member-step inputs. Member agents reason about the event that woke them up, not just the team's `goal_text`.

### Reference

For the implementation contract, schema migrations, and the per-phase surface contract, see [documentation.md §§ 2.4.1 - 2.4.10](documentation.md#241-v070-agent-teams-phase-1-db-foundation).

---

## 4. Personas and Tone Presets

Personas and tone presets define reusable personality templates shared across multiple agents.

### Creating a Persona

Navigate to **Studio > Personas** and click **Create Persona**:

| Field | What It Does |
|---|---|
| **Name** | Unique name within your tenant. |
| **Description** | Summary of what this persona represents. |
| **Role** | Job title or function (e.g., "Customer Support Specialist"). |
| **Role Description** | Detailed responsibilities and context. |
| **Personality Traits** | Comma-separated traits (e.g., "Empathetic, patient, enthusiastic"). |
| **Tone Preset / Custom Tone** | Assign a preset or write custom tone description. |
| **Guardrails** | Safety rules and constraints (e.g., "Never provide medical advice"). |

### Tone Presets

- **Tone Preset** -- select from the built-in library (Friendly, Professional, Humorous, etc.).
- **Custom Tone** -- write your own free-text tone description.

### System vs. Custom Personas

**System personas** are built-in templates (read-only names, but clonable). **Custom personas** are yours to create and fully edit.

---

## 5. Skills

Skills extend what your agents can do.

### Built-in Skills

Tsushin ships with 20 built-in skills. Enable or disable them per agent from the **Skills** tab.

| Skill | Mode | What It Does |
|---|---|---|
| **Audio Communication** | Special | Processes audio messages with AI or transcription-only mode. |
| **Audio TTS Response** | Passive | Converts text responses to audio (OpenAI, Kokoro, or ElevenLabs). |
| **Web Search** | Tool | Searches the web using Brave Search. |
| **Image Generation & Editing** | Tool | Generates or edits images from text prompts. |
| **Gmail** | Tool | Reads and searches emails from connected Gmail accounts. |
| **Automation** | Tool | Multi-step workflow automation. |
| **Scheduler** | Tool | Schedules reminders and conversations via natural language. |
| **Scheduler Query** | Legacy | Lists scheduled events (merged into Scheduler). |
| **Flows** | Tool | Manages workflows and scheduled events. |
| **Flight Search** | Tool | Searches for flights via configured providers. |
| **Shell Commands** | Hybrid | Executes shell commands on registered remote hosts. |
| **Sandboxed Tools** | Passive | Grants access to isolated security tools (nmap, dig, etc.). |
| **Browser Automation** | Tool | Navigates websites, fills forms, captures screenshots. |
| **Password Vault** | Tool | Resolves approved vault references through 1Password-backed Hub Tool APIs with redacted outputs and short-lived handles. |
| **Knowledge Sharing** | Passive | Shares learned facts into a cross-agent memory pool. |
| **Adaptive Personality** | Passive | Extracts user facts and adapts the persona over time. |
| **OKG Term Memory** | Hybrid | Stores/recalls structured term memory with MemGuard. |
| **Agent Switcher** | Tool | Lets users switch their default agent via natural language. |
| **Agent Communication** | Tool | Enables inter-agent questions and task delegation. |
| **Custom Skill (Adapter)** | Tool | Runtime adapter for tenant-authored custom skills. |

**Execution modes:** `Tool` (LLM decides when to invoke), `Passive` (runs automatically after every response), `Hybrid` (both), `Special` (media-triggered), `Legacy` (keywords/commands only).

### Custom Skills

Create your own skills under **Studio > Custom Skills**. Three types:

#### Instruction Skills

No code required. Provide natural-language instructions the LLM follows.

1. Click **Create Skill** > select **Instruction**.
2. Write your instructions (up to 8,000 characters, Markdown supported).
3. Choose a trigger mode: **LLM Decided**, **Keyword**, or **Always**.

#### Script Skills

Write executable code in Python, Bash, or Node.js that runs in a sandboxed container.

1. Click **Create Skill** > select **Script**.
2. Choose language, write code (up to 256 KB), set entrypoint.

#### MCP Server Skills

Connect to an external MCP-compliant tool server.

1. Click **Create Skill** > select **MCP Server**.
2. Select the registered MCP server and tool name.

**Resource quotas:** 8,000 char instructions, 256 KB scripts, 50 skills per tenant. All custom skills are scanned by Sentinel at save time.

### Sandboxed Tools

Security and utility tools running in isolated Docker containers. Invoke with:

```
/tool <tool_name> <command_name> param=value
```

**Important:** Use `param=value` syntax only. Flag-style arguments like `--target` are not supported.

#### Quick Reference

| Tool | Commands | Example |
|---|---|---|
| **nmap** | `quick_scan`, `service_scan`, `ping_scan`, `aggressive_scan` | `/tool nmap quick_scan target=scanme.nmap.org` |
| **nuclei** | `start_scan`, `severity_scan`, `full_scan` | `/tool nuclei start_scan url=http://example.com` |
| **dig** | `lookup`, `reverse` | `/tool dig lookup domain=google.com record_type=MX` |
| **httpx** | `probe`, `tech_detect` | `/tool httpx probe target=https://github.com` |
| **whois_lookup** | `lookup` | `/tool whois_lookup lookup domain=github.com` |
| **katana** | `crawl` | `/tool katana crawl target=https://example.com depth=2` |
| **subfinder** | `scan` | `/tool subfinder scan domain=github.com` |
| **webhook** | `get`, `post` | `/tool webhook get url=https://api.github.com/users/octocat` |
| **sqlmap** | `scan` | `/tool sqlmap scan target=http://example.com/page?id=1` |

For full parameter details, see [documentation.md §9.4](documentation.md#94-sandboxed-tools).

### Code Repository skill (GitHub) — v0.7.0

The `code_repository` skill lets agents read from and (optionally) act on GitHub. It's backed by a tenant-scoped **GitHubIntegration** in **Hub > Tool APIs**.

**Setup:**

1. Go to **Hub > Tool APIs > GitHub** and add an integration: paste the GitHub App / fine-grained PAT credentials, select the repositories the integration can see, and click **Test**.
2. Open an agent's **Skills** tab, click **Add Skill**, pick **Code Repository**, and select the GitHub integration you just created.
3. The capability matrix has 12 actions split into **read** (default ON) and **write** (default OFF) groups:
   - **Read:** `list_repos`, `get_repo`, `list_pull_requests`, `get_pull_request`, `list_issues`, `get_issue`, `list_commits`, `read_file`.
   - **Write:** `create_issue`, `comment_pull_request`, `create_pull_request`, `merge_pull_request`.
4. Toggle write capabilities on only when you intend to grant them. The agent UI shows red **WRITE** badges next to active write capabilities; the `code_repository` tool spec the LLM sees never includes disabled actions, so the model cannot accidentally call something you've forbidden.

**Trigger pairing.** A `pull_request` GitHub trigger can pre-filter on event types (`opened`, `reopened`, `closed`, `synchronize`), draft state, branch patterns, label patterns, and author patterns. The matched payload is delivered to the bound agent or flow with the full PR envelope so the `code_repository` skill can act on it.

### Ticket Management skill (Jira) — v0.7.0

The `ticket_management` skill exposes Jira through the `ticket_operation` tool with the same capability-gating contract as `code_repository`.

**Setup:**

1. Go to **Hub > Tool APIs > Jira** and add an integration with your Atlassian site URL, email, and API token. Click **Test**.
2. On an agent's Skills tab, **Add Skill > Ticket Management**, pick the Jira integration.
3. Capability matrix:
   - **Read (default ON):** `search`, `get_issue`, `list_projects`.
   - **Write (default OFF):** `update`, `add_comment`, `transition`.
4. Disabled actions are filtered out of the LLM's tool spec; the WRITE badges in the UI mirror the active capabilities.

**Trigger pairing.** The Jira trigger runs live JQL polling on Jira Cloud's enhanced JQL search endpoint, dedupes once-per-issue per matched event, and routes the matched payload through the auto-generated FlowDefinition's Source step.

### Granular Gmail send capability — v0.7.0

The Gmail skill is no longer all-or-nothing. The capability set is split into:

| Capability | Default |
|---|---|
| `search` | ON |
| `read_message` | ON |
| `send` | OFF |
| `reply` | OFF |
| `draft` | OFF |

Toggle send/reply/draft on per agent in the Skills tab when you trust that agent to send mail on the connected Gmail account. The capability config is enforced end-to-end — `SkillManager` honors it, the tool spec only includes enabled actions, and the live gate ("outbound upgrade incomplete") surfaces a warning if you connected a Gmail account but have not yet enabled any outbound capability.

---

## 6. Setting Up Communication Channels

Tsushin supports six communication channels. Each connects your AI agents to the messaging platforms your users already use.

### WhatsApp

1. Go to **Hub > Channels > WhatsApp** and click **Add Instance**.
2. Enter a name and the WhatsApp phone number.
3. **Scan the QR code** -- open WhatsApp on your phone, go to **Settings > Linked Devices > Link a Device**, and scan the QR displayed in Tsushin. It expires after ~60 seconds; refresh if needed.
4. Once scanned, the instance status changes to **Running** with a green "Connected" indicator.

**Configure filters:**
- **Group Filters** -- which WhatsApp groups the bot monitors (e.g., "Support Group", "VIP Chat").
- **Number Filters** -- restrict the bot to specific phone numbers.
- **Group Keywords** -- the bot only responds to group messages containing these keywords (e.g., "help", "bot").
- **DM Auto-Mode** (enabled by default) -- auto-reply to DMs from unknown senders. Disable to only respond to pre-registered contacts.
- **Conversation Delay** -- adds a pause before replying (default: 5 seconds) for a more human feel.

**Assign to an agent:** On the agent's **Channels** tab, set **WhatsApp Integration** to this instance.

**Upgrading from 0.5.x — WhatsApp LID migration (v0.6.0):**

WhatsApp is rolling out **Linked Device IDs (LIDs)** — a new privacy-aware identifier that replaces the phone-number JID for many participants (especially in groups). v0.6.0 handles this transparently:

- Existing contacts keep working -- the adapter auto-links new LIDs to existing contacts by phone number on first message.
- Per-contact default agents (`UserAgentSession`) and slash-command permissions (`ContactAgentMapping`) accept either LID or phone-number keys.
- If a group member appears as a new contact after the upgrade (because WhatsApp now exposes only their LID), open the contact's edit modal and add the previous phone number as an alternate identifier to re-link them.

No migration script is needed. Full details: [documentation.md §15.1.1](documentation.md#1511-migration-lid-support-v060).

### Telegram

1. Create a bot via **@BotFather** on Telegram (`/newbot`), copy the bot token.
2. Go to **Hub > Channels > Telegram**, click **Add Bot**, paste the token.
3. Choose **Polling** (simpler, no public URL needed) or **Webhook** (recommended for production, requires HTTPS URL).
4. Assign to an agent on the **Channels** tab.

### Slack

1. **Create a Slack App** at [api.slack.com/apps](https://api.slack.com/apps):
   - Bot token scopes: `chat:write`, `channels:read`, `users:read`, `files:write`.
   - For Socket Mode: enable it and generate an app-level token (`xapp-...`).
   - For HTTP Events API: set the Request URL and copy the Signing Secret.
2. Install the app to your workspace, copy the `xoxb-` bot token.
3. Go to **Hub > Channels > Slack**, click **Add Integration**, paste tokens.
4. Choose mode: **Socket Mode** (recommended) or **HTTP Events API**.
5. Set **DM Policy**: `Open` (accept all DMs), `Allowlist` (only allowed channels), or `Disabled`.
6. If using Allowlist, add Slack channel IDs to **Allowed Channels**.
7. Assign to an agent on the **Channels** tab.

### Discord

1. **Create a Discord Application** at [discord.com/developers](https://discord.com/developers/applications).
2. Under **Bot**: copy the bot token, enable **Message Content Intent**.
3. Under **OAuth2 > URL Generator**: select `bot` scope + permissions (`Send Messages`, `Read Message History`, `Attach Files`). Use the URL to invite the bot to your server.
4. Go to **Hub > Channels > Discord**, click **Add Integration**, paste token and Application ID.
5. Set **DM Policy**: `Open`, `Allowlist`, or `Disabled`.
6. Add **Allowed Guilds** (server IDs) and optionally configure **Guild Channel Config** for per-guild channel restrictions.
7. Assign to an agent on the **Channels** tab.

### Webhook

1. Go to **Hub > Channels > Webhooks**, click **Add Integration**.
2. Enter a name and optionally a **Callback URL** for outbound responses.
3. Copy the generated **HMAC signing secret** (shown only once).
4. Optionally configure: **IP Allowlist** (CIDR ranges), **Rate Limit** (RPM), **Max Payload Size**.
5. Assign to an agent on the **Channels** tab.

**Testing with curl:**

```bash
TIMESTAMP=$(date +%s)
BODY='{"text":"Hello from webhook","sender_key":"external-user-1"}'
SECRET="your_api_secret_here"
SIGNATURE=$(echo -n "${TIMESTAMP}.${BODY}" | openssl dgst -sha256 -hmac "${SECRET}" | awk '{print $2}')

curl -X POST http://your-tsushin-server/api/webhooks/<webhook_id>/inbound \
  -H "Content-Type: application/json" \
  -H "X-Tsushin-Signature: sha256=${SIGNATURE}" \
  -H "X-Tsushin-Timestamp: ${TIMESTAMP}" \
  -d "${BODY}"
```

### Playground

The built-in web chat interface. No setup required -- always available in the sidebar. See [Section 8](#8-using-the-playground) for details.

---

## 6a. Setting Up Event Triggers (v0.7.0)

Triggers are the event-side counterpart to channels. They wake an agent on external events (a Jira issue is created, a webhook is called, an email matching a saved query arrives, or a GitHub PR is opened) instead of on a human DM. Scheduled and recurring work is created in Flows, not as a trigger.

All trigger kinds share the same **Trigger Creation Wizard** (Hub > Triggers > "+ Add Trigger"). The wizard selects the source, criteria, and linked Hub integration where needed, then creates or wires a Flow so outputs are edited in the Flow editor.

### The 4 trigger kinds

- **Email** -- a Gmail saved-query polled every minute. Filter by subject, sender, label, body. Operators paste a saved Gmail search query (e.g., `is:unread label:support has:attachment`); the trigger fires once per matching message and dedupes on the message id.
- **Webhook** -- inbound HMAC-signed POST from any external system. The wizard generates a slug (auto or custom), an HMAC signing secret, and an inbound URL like `https://<your-host>/api/webhooks/<slug>/inbound` that you paste into the external system.
- **Jira** -- live JQL polling against a Jira Cloud project. Connect your Jira account once via Hub > Tool APIs > Jira (with an API token); the wizard then asks for a JQL query and a poll interval. One notification per deduped issue.
- **GitHub** -- pull-request events on a connected repo. Connect your GitHub account once via Hub > Tool APIs > GitHub; the wizard then asks for the events to listen to (`opened`, `reopened`, `closed`, etc.) and per-PR filters (branch, paths changed, author, draft state, title/body matchers).

### What happens after you click "Create Trigger"

1. The trigger row is persisted (e.g., trigger #9).
2. An **auto-generated flow** is minted (e.g., flow #99) with four steps: **Source -> Gate -> Conversation -> Notification**. The flow is system-managed: you can edit its content but you can't delete it directly -- delete the trigger to remove the flow.
3. The wizard's Confirmation step shows a "Wired Flow" card with the auto-flow ID and an **Open Flow Editor** button.
4. Clicking the button takes you to `/flows?edit=<auto_flow_id>` where you can edit the Notification step's message template -- this is where you reference data from the inbound event using template variables like `{{source.payload.issue.key}}`, `{{source.payload.issue.fields.summary}}`, or `{{source.payload.pull_request.title}}`.

### Per-kind trigger-generated flow badges

Auto-generated flows are visually distinct in the flows list and the Edit Flow modal header: each trigger kind has its own coloured "Trigger" pill (Jira blue, Email emerald, GitHub violet, Webhook cyan). The Delete button on auto-generated flows is disabled with a tooltip "Auto-generated from <kind> trigger -- delete the trigger to remove this flow."

### Editing template variables in the auto-flow

Open the auto-flow's Notification step. The **Variable Reference panel** on the right shows previous-step outputs as draggable chips. The Source step's chips are per-kind: for a Jira auto-flow you'll see `payload.issue.key`, `payload.issue.fields.summary`, `payload.issue.fields.status.name`, `payload.issue.fields.priority.name`, `payload.issue.fields.assignee.displayName`, and ~10 more. Click a chip to insert it at the cursor, or drag it into the textarea -- the editor accepts `{{source.payload.X}}` and `{{step_1.payload.X}}` interchangeably.

Example notification template for a Jira trigger:

```
Jira issue {{source.payload.issue.key}}: {{source.payload.issue.fields.summary}} (status: {{source.payload.issue.fields.status.name}})
```

When the trigger fires on issue `JSM-12345` with summary `Customer can't log in` and status `In Progress`, the rendered WhatsApp message is:

```
Jira issue JSM-12345: Customer can't log in (status: In Progress)
```

### Where each part of the trigger lives in the Hub

v0.7.0 split the Hub into four roles so the right surface owns each concern:

| Hub area | What lives there |
|---|---|
| **Hub > Channels** | WhatsApp / Telegram / Slack / Discord / Playground — bidirectional conversational transports. |
| **Hub > Triggers** | Email / Webhook / Jira / GitHub trigger instances. |
| **Hub > Tool APIs** | Programmatic credentials reused by triggers and skills: Jira API token, GitHub integration, Password Vault (1Password), Asana OAuth, etc. The Email trigger reuses the Hub > Google connection for Gmail. |
| **Hub > Local Services** | Auto-provisioned containers — Whisper / Speaches (ASR), Kokoro (TTS), Ollama (LLM), Qdrant (vector store). Lifecycle controls (start/stop/restart/logs/status) live here. |

**Wake Events** moved under **Watcher**. The standalone Schedule Trigger was retired; cron-based execution now lives only on the FlowDefinition (Flows > Create > Scheduled or Recurring).

### Aggregating outputs on the trigger detail page

The trigger detail page lists every binding kind that can fan out from a single trigger event:

- **Wired Flows** — every `flow_trigger_binding` for this trigger.
- **Wired Teams** — every `agent_team_trigger` (Webhook/GitHub/Jira; Gmail since 2026-05-07).
- **Wired Continuous Agents** — every `continuous_subscription`.

Each card supports pause/resume and unbind, gated on `agents.write`. System-owned subscriptions render disabled controls with an explanatory tooltip. Use this page when you need to understand "what will fire when this trigger runs?" without reverse-engineering it from per-team or per-flow surfaces.

### Trigger Case Memory v2 (default-off, experimental)

When **Case Memory** is enabled for your tenant (Core > Organization > Case Memory), each trigger can carry a per-trigger **Memory Recap** config. The recap pulls similar past cases (by query template, scope, k, similarity floor, vector kind) and injects a short summary into the dispatched flow or continuous agent at the position you choose.

To enable for a trigger:

1. Confirm Case Memory is on for the tenant: Core > Organization > Case Memory > **Indexing enabled**. Trigger Recap can be enabled independently.
2. In the trigger creation wizard or detail page, open **Memory Recap**.
3. Configure the query template (e.g., `{{source.payload.issue.fields.summary}}`), scope (`tenant` / `agent` / `team`), k (default 3), similarity floor (default 0.5), vector kind (Tsushin default vs Gemini external), failed-case inclusion, injection position (system prompt vs user message), and max recap length.
4. Save. Live preview is available from the same panel via `/api/triggers/{kind}/{id}/test-recap`.

Recap output appears in the run timeline as `trigger_context.source.memory_recap` and surfaces in the Watcher trigger detail.

> Trigger Case Memory v2 is experimental and gated behind tenant-scoped feature flags (`Tenant.case_memory_enabled` and `Tenant.case_memory_recap_enabled`). Reach out before turning it on for production triggers.

---

## 7. Managing Contacts

Contacts represent the people who interact with your agents across any channel.

### Creating a Contact

1. Go to **Agents > Contacts** and click **Add Contact**.
2. Fill in:
   - **Friendly Name** (required) -- must be unique within your tenant.
   - **Role** -- `User` (default), `Agent`, or `External`.
   - **Notes** -- optional free-text.
3. Click **Save**.

### Adding Channel Mappings

A single contact can be reachable on multiple channels:

1. Open the contact's detail page.
2. Under **Channel Mappings**, click **Add Mapping**.
3. Select the channel type and enter the identifier:
   - **WhatsApp** -- phone number (e.g., `+5511999990001`)
   - **Telegram** -- user ID (numeric)
   - **Discord** -- user ID (numeric snowflake)
   - **Email** -- email address

When that person messages from any mapped platform, Tsushin recognizes them as the same contact.

### DM Trigger Control

The **DM Trigger** toggle (enabled by default) controls whether incoming DMs from this contact trigger agent processing. Disable to receive and store messages without automated replies.

### Slash Command Access Control

Two levels:
- **Tenant Default** -- set in tenant settings, applies to all contacts.
- **Per-Contact Override** -- `Use tenant default` (null), `Enabled`, or `Disabled`.

### Linking Contacts to System User Accounts

Link a contact to a Tsushin user account under **Linked User**. Messages from that contact then inherit the user's RBAC permissions and appear in the audit trail under that user's identity.

### Assigning a Default Agent

Override the tenant's default routing: set a specific **Default Agent** for a contact so all their messages go to that agent regardless of channel.

---

## 8. Using the Playground

The Playground is Tsushin's built-in web chat interface for testing and interacting with your agents.

### Starting a Conversation

1. Click **Playground** in the sidebar.
2. Select an agent from the dropdown.
3. Type your message and press **Enter**.
4. The agent's response streams in real time.

### Thread Management

- **New Thread** -- click "+" to start a fresh conversation.
- **Switch Threads** -- click any thread in the sidebar.
- **Auto-Rename** -- threads are automatically named based on conversation content.

### Audio Recording and Transcription

If the **Audio Transcript** skill is enabled:
1. Click the **microphone** icon.
2. Speak your message.
3. Click again to stop -- the audio is transcribed and processed automatically.

### Document Uploads

Click the **upload** icon to attach files. Supported: `.pdf`, `.txt`, `.csv`, `.json`, `.docx`.

### Command Palette

Type `/` in the message input to open the command palette -- browse and execute slash commands.

### Memory Inspector

Toggle from the toolbar to see what the agent "remembers" about the conversation and which memory entries influenced the response.

### Expert Mode

Toggle from the toolbar for advanced controls and diagnostics.

### WebSocket Streaming

Responses stream token-by-token via WebSocket by default. Falls back to HTTP polling if WebSocket is unavailable. No configuration needed.

---

## 9. Flows (Workflow Automation)

Flows let you build multi-step automated workflows.

### Flow Types

| Type | Best For | Example |
|---|---|---|
| **Conversation** | Multi-turn AI dialogues | Onboarding flow asking a series of questions |
| **Notification** | Alerts, reminders, status updates | Daily summary notification to Slack |
| **Workflow** | Multi-step processes | Security audit: scan, analyze, post report |
| **Task** | Structured task execution | Process CSV files and generate reports |

### Creating a Flow

1. Navigate to **Studio > Flows** and click **Create Flow**.
2. Name your flow and select the type.
3. Choose an **execution mode**: Immediate, Scheduled (one-time), Recurring (cron-based), Keyword, or Triggered.
4. For **Triggered**, select an existing Hub trigger (Email/Gmail, Jira, GitHub, or Webhook). Tsushin creates a locked Source step and the `flow_trigger_binding` automatically.
5. For **Scheduled**, **Recurring**, or **Keyword**, fill the required schedule, recurrence, or keyword fields before saving.
6. **Add steps** in sequence.

### Step Types

| Step Type | What It Does |
|---|---|
| **Notification** | Sends a notification to a recipient. |
| **Message** | Sends a single chat message. |
| **Tool** | Invokes a tool or function. |
| **Conversation** | Multi-turn AI conversation with an objective (configurable max turns, default: 20). |
| **Slash Command** | Executes a platform slash command. |
| **Skill** | Runs an agent skill (built-in or custom). |
| **Summarization** | AI summarization of previous step outputs. |
| **Password Vault** | Resolves an approved vault reference without placing secrets in prompts. |
| **Browser Automation** | Navigate, click, fill forms, extract content, screenshot. |
| **HTTP Request** | Calls an API with editable method, URL, headers, body, and secret references. |
| **Data Transform** | Extracts and normalizes fields from previous step outputs. |
| **Financial Record Store** | Persists and dedupes financial records. |
| **Utility Bill Store** | Utility-bill-specific storage and dedupe alias. |

The **Source** step appears only on triggered flows and is generated from the selected Hub trigger. It is locked at the top of the flow and cannot be added manually.

Financial templates should remain editable like any other Flow. Open a browser step to adjust URL/action/selectors, add a **Skill** or **Summarization** step for agentic reasoning, and end with a conditional **Notification** fed by a previous storage/gate output.

**Step configuration:** timeout (default: 300s), retry on failure, conditions, on_success/on_failure actions (continue, skip_to, end, retry, skip), agent/persona overrides.

### System-managed (auto-generated) trigger flows

When you create a Hub trigger, Tsushin auto-generates a four-step **system-managed flow** wired to that trigger via a `flow_trigger_binding`. The flow editor is intentionally tailored when you open a system-managed flow:

- **Banner at the top of the Edit modal** reorients you: *edit the trigger to change what fires, edit the steps to change what happens after*. Includes a deep link back to the Hub trigger detail page.
- **Source step** shows a read-only **Trigger configuration** card with kind-specific inputs — JQL + project key for Jira, inbox + search query for Email, repo + events + path/branch filters for GitHub — plus a `trigger_criteria.filters` JSON preview and an **Edit in Hub** deep link. Filters are managed on the trigger, not on the flow.
- **Criteria gate** prepends an **upstream-filter callout** explaining the trigger's criteria already gated the event, so anything you add on the gate is a *secondary* filter. Empty gate is the canonical default.
- **Default agent** step (a `conversation` step) hides the outbound-message fields (channel, recipient, initial prompt) and shows an **Inbound step** note instead — the conversation receives the trigger payload and the agent processes it according to the objective.
- **Sample data preview** — every non-source step has a "Sample data this step receives" expander that fetches the most-recent wake event for the bound trigger and shows the JSON payload + a count badge of `{{source.payload.X}}` references in your step's config. Use this to author template references with confidence.

### Trigger fan-out: parallel-fire vs flow-only

A single trigger event can fan out to three independent runtimes in parallel: bound flows (`FlowRun`), continuous-agent subscriptions (`ContinuousRun`), and agent-team triggers (`AgentTeamRun`). On the Hub trigger detail page the **Wired Flows** card shows a pill toggle per binding:

- **● Parallel fire** (amber, default) — both this flow AND any wired continuous agent fire on each event. Safe migration mode.
- **● Flow-only** (emerald) — this flow takes over and the legacy continuous-agent path is suppressed for this trigger.

Click the pill to flip between the two states. Toast confirms the change. Wired Agent Teams fire independently of this toggle.

### Template Variables

Reference previous step outputs:

| Syntax | What It Does |
|---|---|
| `{{step_1.output}}` | Output of step 1 (by position) |
| `{{step_name.output}}` | Output of a step by name |
| `{{previous_step.output}}` | Most recently completed step |
| `{{flow.trigger_context.param}}` | Data passed when flow was triggered |

**Helpers:** `truncate`, `upper`, `lower`, `default`, `json`, `length`, `first`, `last`, `join`, `replace`, `trim`.

**Conditionals:**
```
{{#if step_1.success}}OK{{else}}FAIL{{/if}}
```

### Flow Status Lifecycle

| Status | Meaning |
|---|---|
| Pending | Queued, waiting to start |
| Running | Executing steps |
| Completed | All steps finished successfully |
| Failed | One or more steps failed |
| Cancelled | Stopped manually |
| Paused | Waiting for response (e.g., conversation step) |
| Timeout | Exceeded time limit |

**Slash commands:** `/flows list`, `/flows run "Daily Report"`, `/flows run 42`.

---

## 10. Scheduler

Create events, reminders, and recurring AI-driven conversations using natural language.

### Scheduler Providers

| Provider | Description |
|---|---|
| **Flows** (Internal) | Built-in, no external account needed. |
| **Google Calendar** | Events appear on your Google Calendar. |
| **Asana** | Tasks created in your Asana workspace. |

Check the active provider with `/scheduler info`.

### Creating Events

```
/scheduler create "Team standup tomorrow at 9am"
/scheduler create "Weekly report every Friday at 5pm"
/scheduler create "Daily security scan at 6am recurring weekdays"
```

### Listing, Updating, and Deleting

```
/scheduler list today
/scheduler list week
/scheduler list 2026-04-15
/scheduler update 42 name="Updated Standup"
/scheduler delete 42
```

### Event Types

- **Notification** -- sends a reminder message at the scheduled time.
- **Conversation** -- initiates an autonomous multi-turn AI conversation at the scheduled time.

---

## 11. Projects (Knowledge Isolation)

Projects are tenant-wide workspaces with dedicated knowledge bases, memory settings, and tool configurations.

### Creating a Project

1. Navigate to **Studio > Projects** and click **Create Project**.
2. Fill in: **Name**, **Description**, **Icon**, **Color**, **Default Agent**, and optionally a **System Prompt Override**.

### Knowledge Base Configuration

Each project has its own settings: **Chunk Size** (default: 500), **Chunk Overlap** (default: 50), and **Embedding Model** (default: all-MiniLM-L6-v2).

### Memory Configuration

Per-project: **Semantic Memory** (on/off), **Results** (default: 10), **Similarity Threshold** (default: 0.5), **Factual Memory** (on/off), **Extraction Threshold** (default: 5 messages).

### Project Context via Slash Commands

```
/project enter MyProject     -- Enter project context
/project exit                -- Leave current project
/project list                -- List all projects
/project info                -- Show current project details
```

---

## 12. Memory and Knowledge

### Four Memory Layers

1. **Working Memory** -- the last N messages from each conversation (short-term context).
2. **Episodic Memory** -- all conversations indexed for semantic search (long-term recall).
3. **Semantic Knowledge** -- automatically extracted facts about users (preferences, roles, history).
4. **Shared Memory** -- cross-agent knowledge pool. If Agent A learns something, Agent B can access it.

### Uploading Knowledge Base Documents

Supported formats: `.txt`, `.csv`, `.json`, `.pdf`, `.docx`. Max: 50 MB per file.

1. Open the agent's **Knowledge Base** tab.
2. Click **Upload Document** and select your file.
3. The document is processed in the background (chunked and indexed).

### OKG (Ontology Knowledge Graph)

Structured memory that stores facts with relationships. Memory types: `fact`, `episodic`, `semantic`, `procedural`, `belief`.

Includes **MemGuard** security validation to protect against memory poisoning.

### Trigger Case Memory v2 (experimental, default-off) — v0.7.0

Trigger Case Memory is an opt-in long-term store that captures the recap of every trigger run (Email/Webhook/Jira/GitHub) so future runs can pull a short summary of similar past cases into the dispatched flow or continuous agent. See [§ 6a](#6a-setting-up-event-triggers-v070) for trigger-side configuration. Tenant-level toggles live in **Core > Organization > Case Memory**:

- **Indexing enabled** — populates the case memory store. Requires the optional Gemini external embedder if you don't want to spend tokens on the default embedder.
- **Recap injection enabled** — independently controls whether saved configs actually inject recap output into runs. Useful when you want to start indexing but defer recap injection until you've validated the recap quality.

### Configuring Vector Stores

Go to **Settings > Vector Stores**. Tsushin supports four vector store backends:

- **Chroma** (default) -- built-in, no external setup.
- **Pinecone** -- cloud-hosted. Requires API key and index name.
- **Qdrant** -- self-hosted (auto-provisioned during setup when available) or cloud. Requires URL and collection name.
- **MongoDB Atlas** -- requires connection string and Atlas Vector Search.

**Multi-index per surface (v0.7.0).** Tsushin distinguishes three vector-store *surfaces*:

| Surface | What it stores | Where to attach |
|---|---|---|
| **Long-term memory** | Tenant-level memory (semantic search across conversations) | Settings > Vector Stores > **Default for memory** |
| **Agent KB** | Per-agent knowledge base documents | Agent > Knowledge Base tab > **Vector store** |
| **Project KB** | Per-project (Studio Projects) knowledge base | Project > Knowledge Base tab > **Vector store** |

Each surface can pick a different index (and even a different backend), and each surface can pick its own **embedding provider** (default vs Gemini external). This lets you, for example, keep long-term memory on built-in Chroma + default embeddings while putting Project KB on a tenant-owned Qdrant collection with Gemini embeddings.

**Per-agent vector store override.** Individual agents can still override the default with three modes:
- **Override** — the agent ignores the default and uses only its own store.
- **Complement** — the agent reads from both its store and the default, merging results.
- **Shadow** — the agent reads from the default but writes to both, allowing offline migration.

---

## 13. Security -- Sentinel

Sentinel is Tsushin's AI-powered security system that monitors all agent interactions in real time.

### 8 Detection Types

1. **Prompt Injection** -- hidden commands trying to override agent instructions.
2. **Agent Takeover** -- attempts to hijack the agent's behavior entirely.
3. **Poisoning Attack** -- feeding false information to corrupt responses.
4. **Malicious Shell Intent** -- dangerous commands when agents have shell access.
5. **Memory Poisoning** -- injecting false facts into long-term memory. MemGuard validates every fact before storage.
6. **Agent Privilege Escalation** -- making an agent exceed its authorized permissions.
7. **Browser SSRF** -- forcing browser automation to access internal/restricted resources.
8. **Vector Store Poisoning** -- corrupting the vector database powering agent memory.

### Security Profiles

| Profile | Behavior |
|---|---|
| **Off** | No security analysis (development only) |
| **Permissive** | Detect and log silently (no blocking) |
| **Moderate** | Block confirmed threats (recommended) |
| **Aggressive** | Maximum sensitivity, blocks borderline cases |

Assign profiles to agents on the agent's security settings. Create custom profiles by cloning an existing one.

### Viewing Security Events

Go to **Watcher > Security** tab to see blocked threats, warnings, and detections. Filter by severity, type, or date range.

### Exceptions and Allowlists

Go to **Settings > Sentinel Security > Exceptions** to add pattern-based, domain-based, or other exceptions to prevent false positives.

---

## 13a. Watcher Reference

Watcher is the **observability** surface — read-only insight into what's running and what's recently happened. Configuration belongs in **Studio** and **Hub**; Watcher only watches.

| Top-level tab | What It Shows |
|---|---|
| **Dashboard** | KPIs (messages, agent runs, success rate, avg response) and the live Activity Timeline. |
| **Graph View** *(admin)* | Network visualization of agents, contacts, and channels. |
| **Agents** | Run-time view of agents — see sub-tabs below. |
| **Flows** | Flow execution history, status pills, per-step timing, last-run links. |
| **Security** | Sentinel detections — blocked threats, warnings, severity, type. |
| **Channel Health** | Per-instance circuit-breaker state and inbound channel readiness. |
| **Billing** | AI cost and token consumption breakdown per provider/model. |

The **Agents** tab nests five related run-time surfaces under one menu so you can pivot between agent inventory and recent activity without leaving the page:

| Sub-tab | What It Shows |
|---|---|
| **Continuous Agents** *(default landing)* | Always-on inventory: each Continuous Agent, its monitored triggers, mode (`autonomous`/`hybrid`/`notify_only`), latest run status, daily-budget consumption. |
| **Wake Events** | Trigger-event browser — every event that fired (status, kind, instance, occurred-at) with click-through to the raw payload. |
| **Conversations** | Message and agent-run threads across channels (Playground, WhatsApp, Telegram, Slack, Discord). |
| **Team Runs** | Agent Team executions with progress (`N/M steps`), status, and per-team filtering. |
| **A2A Comms** | Inter-agent messaging sessions, depth, message count. |

Continuous Agent **creation** lives in Studio (**Studio → Continuous Agents**), not Watcher — Watcher only displays inventory + history.

---

## 14. Settings Reference

| Page | What It Does |
|---|---|
| **Organization** | Name, slug, plan, usage limits, statistics. |
| **Team Members** | Invite, manage, search team members. |
| **Roles & Permissions** | 4 built-in roles (Owner, Admin, Member, Read-only), 47 permission scopes. |
| **Integrations** | Google OAuth credentials for Gmail, Calendar, SSO. |
| **Security & SSO** | Google Sign-In, allowed email domains, auto-provisioning, encryption keys. |
| **Billing & Plans** | Subscription management, usage breakdown. |
| **Audit Logs** | Browse, filter, export events. Configure retention and syslog forwarding. |
| **Model Pricing** | Per-model input/output cost configuration (per 1M tokens). |
| **System AI** | Provider/model for internal features (Sentinel, fact extraction). |
| **Vector Stores** | Default vector DB selection, external provider connections. |
| **Prompts & Patterns** | Global config, tone presets, custom slash commands, project patterns. |
| **Sentinel Security** | Profiles, MemGuard, analysis prompts, statistics, exceptions, hierarchy. |
| **API Clients** | Create/manage OAuth2 API clients (name, role, rate limit, credentials). |
| **Message Filtering** | Global WhatsApp/Telegram filters: group allowlist, number allowlist, keyword filters, DM auto-mode. |

---

## 15. Slash Commands Reference

Type `/` in any chat (Playground, WhatsApp, Telegram, etc.) to access slash commands.

### Agent Commands

| Command | Usage | Description |
|---|---|---|
| `/invoke <name>` | `/invoke SecurityBot` | Switch to a different agent |
| `/agent info` | `/agent info` | Show current agent details |
| `/agent skills` | `/agent skills` | List enabled skills |
| `/agent list` | `/agent list` | List all agents |

### Project Commands

| Command | Usage | Description |
|---|---|---|
| `/project enter <name>` | `/project enter MyProject` | Enter project context |
| `/project exit` | `/project exit` | Leave current project |
| `/project list` | `/project list` | List all projects |
| `/project info` | `/project info` | Current project details |

### Memory Commands

| Command | Usage | Description |
|---|---|---|
| `/memory clear` | `/memory clear` | Clear conversation memory |
| `/memory status` | `/memory status` | Show memory statistics |
| `/facts list` | `/facts list` | List learned facts |

### Email Commands (requires Gmail skill)

| Command | Usage | Description |
|---|---|---|
| `/email inbox [count]` | `/email inbox 20` | Show recent emails |
| `/email search <query>` | `/email search "from:boss subject:urgent"` | Search with Gmail syntax |
| `/email unread` | `/email unread` | Show unread emails |
| `/email info` | `/email info` | Gmail connection status |
| `/email list <filter>` | `/email list today` | List with filter (unread, today, count) |
| `/email read <id>` | `/email read 3` | Read full email |

### Search Commands (requires web_search skill)

| Command | Usage |
|---|---|
| `/search <query>` | `/search "kubernetes best practices 2026"` |

### Shell Commands (requires shell skill + beacon)

| Command | Usage |
|---|---|
| `/shell <command>` | `/shell ls -la` |
| `/shell <host>:<command>` | `/shell myserver:df -h` |

### Thread Commands

| Command | Usage | Description |
|---|---|---|
| `/thread end` | `/thread end` | End active thread |
| `/thread list` | `/thread list` | List active threads |
| `/thread status` | `/thread status` | Show thread details |

### Tool Commands (sandboxed)

```
/tool nmap quick_scan target=scanme.nmap.org
/tool dig lookup domain=google.com record_type=MX
/tool nuclei start_scan url=http://example.com
/tool httpx probe target=https://github.com
/tool subfinder scan domain=github.com
/tool katana crawl target=https://example.com depth=2
/tool whois_lookup lookup domain=github.com
/tool webhook get url=https://api.github.com/users/octocat
/tool sqlmap scan target=http://example.com/page?id=1
```

### Inject Commands

| Command | Description |
|---|---|
| `/inject` | Inject last tool output into conversation |
| `/inject list` | List buffered executions |
| `/inject clear` | Clear buffer |

### Flow Commands

| Command | Usage |
|---|---|
| `/flows list` | List all workflows |
| `/flows run <name or ID>` | `/flows run "Daily Report"` |

### Scheduler Commands

| Command | Usage |
|---|---|
| `/scheduler info` | Show provider info |
| `/scheduler list <range>` | `/scheduler list today` or `/scheduler list week` |
| `/scheduler create <desc>` | `/scheduler create "Standup tomorrow 9am recurring weekdays"` |
| `/scheduler update <id> <fields>` | `/scheduler update 42 name="New Name"` |
| `/scheduler delete <id>` | `/scheduler delete 42` |

### System Commands

| Command | Description |
|---|---|
| `/commands` | List all commands (aliases: `/help`, `/?`) |
| `/help [command]` | General help or help for a specific command |
| `/status` | Show agent/channel/project context |
| `/tools` | List available sandboxed tools |
| `/shortcuts` | Show keyboard shortcuts |

---

## 16. Using the Public API

Tsushin provides a REST API for programmatic access.

### Authentication

**Option 1: API Key** -- include as a header:
```
X-API-Key: your_client_secret_here
```

**Option 2: OAuth2 Client Credentials** -- exchange credentials for a bearer token:
```bash
curl -X POST https://your-tsushin-url/api/v1/oauth/token \
  -d "grant_type=client_credentials&client_id=<your-client-id>&client_secret=<your-client-secret>"
```

Create API clients under **Settings > API Clients**.

### Quick Start

```bash
# List agents
curl -H "X-API-Key: <your-api-key>" https://your-tsushin-url/api/v1/agents

# Chat with an agent
curl -X POST -H "X-API-Key: <your-api-key>" \
  -H "Content-Type: application/json" \
  https://your-tsushin-url/api/v1/agents/1/chat \
  -d '{"message": "Hello! What can you help me with?"}'
```

### Key Endpoints

| Area | Endpoints | What You Can Do |
|---|---|---|
| **Agents** | `GET/POST/PUT/DELETE /api/v1/agents` | Manage agents, skills, personas |
| **Chat** | `POST /api/v1/agents/{id}/chat` | Send messages (sync or async) |
| **Threads** | `GET /api/v1/agents/{id}/threads` | Manage conversation threads |
| **Flows** | `GET/POST/PUT/DELETE /api/v1/flows` | Manage and execute workflows |
| **Skills** | `GET /api/v1/skills` | List available skills |
| **Tools** | `GET /api/v1/tools` | List sandboxed tools |
| **Personas** | `GET /api/v1/personas` | List personas |
| **Tone Presets** | `GET /api/v1/tone-presets` | List tone presets |
| **Security Profiles** | `GET /api/v1/security-profiles` | List Sentinel profiles |
| **Hub** | `GET /api/v1/hub/integrations` | List integrations |
| **Studio** | `GET/PUT /api/v1/studio/agents/{id}` | Agent builder config |

### Rate Limiting

Default: 60 requests/minute (customizable per API client). Check `X-RateLimit-Remaining` headers. `429` response means you've exceeded your limit.

### Async Chat Mode

For long-running responses, add `?async=true` to get a `queue_id`, then poll with `GET /api/v1/queue/{queue_id}`.

---

## 17. Audit and Compliance

### Viewing Audit Logs

Go to **Settings > Audit Logs** to browse events chronologically. Each shows timestamp, action type, user, severity, channel, and description. Click for full details.

### Filtering

Filter by **Action** (Authentication, Agents, Flows, etc.), **Severity** (Info, Warning, Critical), **Channel** (Web, API, WhatsApp, Telegram, System), and **Date Range**.

### CSV Export

Click **Export CSV** to download filtered events for external analysis or compliance reporting.

### Retention

Default: 90 days. Configure in the Audit Logs page. Events older than the retention window are automatically purged.

### Syslog Forwarding

Stream events to an external syslog collector:

1. On the Audit Logs page, scroll to **Syslog Forwarding**.
2. Configure: **Host**, **Port**, **Protocol** (UDP/TCP/TLS), **Facility**, **App Name** (default: "tsushin").
3. For TLS: paste your CA Certificate (PEM format).
4. Select which event categories to forward.
5. Save.

Events are formatted using the RFC 5424 syslog standard and delivered asynchronously.

---

## 18. Remote Access (System Administrators)

> **Audience:** Global Admins only. Regular tenant owners and members do not see this feature.

v0.6.0 introduces **Remote Access via Cloudflare Tunnel** — a one-click way to expose your Tsushin instance on a public HTTPS URL without opening firewall ports or managing a reverse proxy. It is **off by default** at both the system level and the per-tenant level, so nothing becomes internet-reachable until you explicitly enable it.

**Why you might use this:**
- Collaborate with external teams, testers, or auditors without VPN provisioning.
- Give Slack, Discord, or Webhook channels a stable HTTPS callback URL when running Tsushin on a laptop or a private network.
- Expose a short-lived demo environment.

**Two modes:**

| Mode | URL style | Lifetime | Use case |
|---|---|---|---|
| **Quick** | `https://<random>.trycloudflare.com` | Lives only while cloudflared is running; new URL each start | Dev, demos, short tests |
| **Named** | Custom FQDN you own (e.g., `https://tsushin.acme.com`) | Stable across restarts, bound to your Cloudflare Zero Trust account | Production, enterprise |

**Setting it up:**

1. Log in as a **Global Admin** and navigate to **System Administration > Remote Access** (`/system/remote-access`).
2. For **Quick Mode**: just click **Start**. Cloudflare hands you a throwaway HTTPS URL within a few seconds.
3. For **Named Mode**: create a tunnel in your Cloudflare Zero Trust dashboard, copy the connector token, paste it into the Remote Access config, then **Start**.
4. **Enable per-tenant entitlement:** toggle Remote Access for each tenant you want to let in. Users from tenants that are not entitled see a login banner (*"Remote access is not enabled for this tenant"*) and a 403 is written to their tenant audit log as `auth.remote_access.denied`.

**Security posture:**

Cloudflare Tunnel makes the entire Tsushin app reachable on one public URL, so authentication and tenant entitlement become the sole gate. v0.6.0 has tightened which routes are anonymous (health, webhook receive, login) versus authenticated (everything else). Under Named Mode you can stack additional Zero Trust Access policies on top if you need them.

**Disabling remote access instantly:** `/system/remote-access` > **Tunnel Status** > **Stop**. The tunnel subprocess exits and no new requests can reach the instance from the public URL until you start it again.

Full technical reference (architecture diagram, supervisor behavior, troubleshooting, route hardening list): [documentation.md §22.5](documentation.md#225-remote-access-cloudflare-tunnel--v060).
