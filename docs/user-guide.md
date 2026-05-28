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

### For Administrators: Installer Options (v0.7.0)

If you're the administrator installing Tsushin for your organization, run `python3 install.py` from the repository root. The installer hardens introduced in v0.6.x and carried forward in v0.7.x:

- **`--le-staging`** -- when combined with `--domain` and `--email`, uses the Let's Encrypt **staging** directory instead of production. Use this to rehearse the full ACME flow without burning your production rate-limit budget (LE limits you to ~5 failed challenges per domain per hour on production). Example: `python3 install.py --defaults --domain app.example.com --email you@example.com --le-staging`.
- **IP-address installs work correctly.** The self-signed SAN emits `IP:<addr>,DNS:localhost,IP:127.0.0.1,IP:::1` (the old format `DNS:<IP>` was rejected by browsers and curl). If you're accessing Tsushin by IP (e.g., `https://10.0.0.5`), the installer detects a stale SAN from a prior run and regenerates automatically.
- **Frontend rebuild on API URL change.** If you rerun the installer and change `NEXT_PUBLIC_API_URL`, the installer diffs the previous `.env` and rebuilds the frontend image with `--no-cache`. Previously it would silently ship a stale cached bundle and leave the UI pointing at the old URL.
- **Stack-scoped frontend proxy builds (v0.6.1).** The Caddy config and frontend proxy build target stack-scoped upstreams such as `${TSN_STACK_NAME}-frontend` and `${TSN_STACK_NAME}-backend`. That keeps both HTTP and HTTPS browser traffic pinned to the intended stack even when multiple Tsushin instances share `tsushin-network`.
- **Idempotent re-runs.** Re-running `python3 install.py` against an existing install preserves `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, and `ASANA_ENCRYPTION_KEY`. Fresh values are only generated on first installs or when a specific key is missing — fixes the pre-v0.6.1 failure mode where re-runs rotated the postgres password while the data volume still carried the old one.
- **Manual-cert pre-flight validation.** Key↔cert match, expiry window, SAN coverage, optional intermediate chain bundle support (resolves Sectigo/GoDaddy chain mismatches).

Full installer reference, GKE/Helm, GCP Secret Manager, and `.env` details live in [documentation.md §3 Quick Start](documentation.md#3-quick-start) and [§4 Deployment & Operations](documentation.md#4-deployment--operations).

### First Login and Setup Wizard

When you open Tsushin for the first time, you will be greeted by the **Setup Wizard**. This one-time process creates your organization and your administrator account.

1. Open your Tsushin URL in a browser (for example, `https://localhost` or the URL provided by your administrator).
2. You will be redirected to the `/setup` page automatically.
3. Fill in your **name**, **email address**, and **password** to create your admin account.
4. Enter your **organization name** -- this becomes your tenant in the system.
5. Click **Complete Setup**. You are now logged in as the organization owner.

During setup, Tsushin automatically creates provider instances for any supported API keys you enter and assigns the selected primary provider as the initial **System AI** and Sentinel LLM provider. If you skip provider keys during setup and later create the tenant's first LLM Provider Instance in Hub, Tsushin auto-attaches still-unbound System AI and Sentinel settings to that instance. The completion screen also reveals an auto-generated **global admin** email/password pair for system-level administration, so make sure to capture it before you leave the page.

After first login, a getting-started onboarding tour auto-opens. It now walks through the v0.7.0 operating path: AI providers, channels vs triggers, GitHub/GitLab repository connections, skills, memory and knowledge, Watcher, Studio, Hub, flows, Playground, optional voice setup, Sentinel, trigger readiness, and the final next step. Each setup-oriented step includes a direct action to open the relevant Hub, Studio, Flows, Playground, or wizard surface. You can minimize the tour at any time with the chevron icon — a "Continue tour" pill survives a full page reload — or dismiss it permanently with ×. The tour pauses while another blocking editor modal is open, then resumes when that modal closes.

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

If you're mid-flow on another page — inspecting the Watcher Graph, editing a Flow, reading a dashboard — you don't have to leave to try an agent. **Playground Mini** is a floating chat bubble available on every page and hides while blocking edit modals are open so it does not cover form actions:

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

#### TTS Providers (Text-to-Speech)

Three options: **Kokoro** (local, self-hosted), **OpenAI TTS**, or **ElevenLabs**. Configure under **Hub > TTS Providers**, then enable the TTS skill on your agents.

#### ASR Providers (Speech-to-Text) — v0.7.0

Tsushin supports four ASR engines for transcribing inbound audio (WhatsApp voice notes, Playground audio, Telegram voice messages):

| Engine | Where it runs | When to use |
|---|---|---|
| **OpenAI Whisper API** | Cloud (OpenAI). Reuses your tenant's saved OpenAI key. | Default if you already have OpenAI configured and don't mind cloud transcription. |
| **Whisper (local)** | Auto-provisioned container under Hub > Local Services. | Privacy-sensitive deployments — voice data never leaves your infrastructure. CPU-friendly. |
| **Speaches** | Auto-provisioned container under Hub > Local Services. | Local Whisper alternative with different performance profile. The guided wizard recommends and defaults to **4 GB** memory to avoid startup/transcription OOM churn. |
| **Google Gemini (multimodal)** | Cloud (Google). Reuses your tenant's Gemini Provider Instance — same credential as the Gemini LLM. | Multilingual voice notes where a multimodal model gives stronger context understanding than pure Whisper, or when you already pay for Gemini and want to consolidate billing. Inline upload up to 20 MB; larger files automatically use the Gemini Files API. |

**Setup (Hub > Add Provider > Speech-to-Text):**

1. Go to **Hub > AI Providers > + New Instance**, pick **Speech-to-Text** as the modality.
2. Choose **Cloud** (OpenAI Whisper API — no extra credentials needed) or **Local** (Whisper or Speaches).
3. For Local: name the instance, optionally pick a GPU profile, and click **Provision**. The container is created with `auto_provision=true`; the wizard polls until it's healthy. Speaches defaults to **4 GB** memory; keep that recommendation unless you have host-level evidence that a smaller limit is safe.
4. Once running, the instance shows up under **Hub > Local Services > Speech-to-Text** with start/stop/restart/logs/status controls.

**Per-agent assignment.** The `audio_transcript` skill on each agent has three modes:

- **`openai`** — call the OpenAI Whisper API directly (requires the OpenAI key in the tenant Hub).
- **`instance`** — pin a specific tenant-owned local ASR instance (requires `asr_instance_id`).
- **`gemini`** — send the audio inline to Google Gemini multimodal (default `gemini-3.5-flash`). Requires a Gemini Provider Instance configured under **Hub > AI Providers > Gemini** (the same credential is reused for Gemini LLM calls).

Both Audio Agents Wizard and the agent's Skills tab show a list of every active tenant ASR instance so you can pick which one this agent uses. There is **no global Settings → ASR page** and **no tenant-default ASR** in v0.7.0 — assignment is always explicit at the agent level.

**Local ASR guidance (2026-05-18).** When a skill is pinned to a local ASR instance, Audio Agents Wizard and the Skills tab expose optional **Prompt/context** and **Hotwords / terms** fields. Use them for names, product terms, acronyms, PT-BR vocabulary, and words that Speaches tends to miss. The runtime forwards the guidance to Speaches as `prompt` and `hotwords` multipart fields while preserving the configured `language` and `vad_filter` values. OpenAI cloud transcription remains an explicit cloud mode or benchmark reference; pinned-local agents still fail closed and do not silently fall back to OpenAI.

**Mode-aware model field (2026-05-16).** The Audio Transcript config panel renders the model field differently per mode so the picker matches what actually drives transcription:

- In **cloud mode**, the panel shows an editable "OpenAI model" dropdown (e.g. `whisper-1`).
- In **local instance mode**, the panel shows a read-only "Local model" label of the form `vendor · default_model` (e.g. `speaches · whisper-large-v3`). The local container dictates which model it serves, so the skill config has no per-agent override.

The instance list also auto-refreshes when you switch to instance mode or create a new ASR instance in another tab — you no longer need to close and reopen the modal to pick up a freshly-provisioned instance.

**Speaches CPU tuning and model promotion.** Auto-provisioned Speaches containers default to CPU-friendly `WHISPER__COMPUTE_TYPE=int8` and a keep-warm TTL (`WHISPER__TTL=-1`, with `STT_MODEL_TTL=-1` retained as a compatibility alias) so the promoted model is not repeatedly unloaded between voice notes. Larger models should be trialed through a benchmark instance first, using real user-sent audio and watching latency plus Docker memory. Updating `default_model` on an active auto-provisioned ASR instance reprovisions the same container target and keeps the model-cache volume, so promote only after the benchmark shows acceptable PT-BR accuracy, memory, and roughly realtime-to-2x latency.

**Cascade-aware delete.** Deleting an ASR instance shows a banner enumerating every agent currently pinned to it. The delete reconciles those agents in the same transaction: pinned skills are repointed to another active ASR instance if one exists; otherwise they are disabled (so the agent stops trying to transcribe via a now-deleted endpoint). The cascade summary appears in the response so the UI surfaces "3 agents reassigned to OpenAI Whisper QA" instead of failing silently.

**Failure-mode honesty (2026-05-06).** If you pin an agent to a local instance, the runtime does **not** silently fall back to the OpenAI cloud Whisper API on failure. The local provider's error surfaces directly so you find out about a stalled or unhealthy local container instead of leaking voice data to a third-party cloud. To use the cloud path explicitly, set `asr_mode='openai'` on the agent. Transient local ASR errors are retried through the provider path, and OOM-style failures are reported with diagnostic detail so operators can raise the container memory limit (Speaches recommendation/default: **4 GB**) rather than misreading the incident as a cloud-key problem.

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
| **Trigger subscriptions** | At least one | Bind the agent to one or more Email/Webhook/Jira/GitHub/GitLab triggers (or wake events). Scheduled and recurring work belongs in Flows. |
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

- **Agent Switcher** -- lets users switch their default agent through `/invoke` or an LLM tool call (e.g., "Switch me to the Support agent"). Raw text keyword matching is no longer used for skill dispatch.
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
5. **Triggers** — bind active Webhook, GitHub, GitLab, Jira, or Gmail trigger instances. (The Phase 6 restriction that excluded Gmail was lifted on 2026-05-07.)
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

Tsushin ships with 22 built-in skills. Enable or disable them per agent from the **Skills** tab.

| Skill | Mode | What It Does |
|---|---|---|
| **Audio Communication** | Special | Processes audio messages with AI or transcription-only mode. |
| **Audio TTS Response** | Passive | Converts text responses to audio (OpenAI, Kokoro, or ElevenLabs). |
| **Web Search** | Tool | Searches the web using Brave Search (default), Google/SerpAPI, SearXNG, or Tavily. |
| **Image Analysis** | Special | Interprets inbound images, answers questions about attached photos, and extracts visible text. |
| **Image Generation & Editing** | Tool | Generates or edits images from text prompts (Gemini-backed across WhatsApp, Telegram, Playground). |
| **Gmail** | Tool | Reads, searches, and (with capability gates) sends/replies/drafts on connected Gmail accounts. |
| **Code Repository** *(v0.7.x)* | Tool | Search/read repository data from GitHub or GitLab. Read on by default; write actions (create_issue, merge_pull_request, etc.) are off by default and filtered out of the LLM tool spec. GitLab writes currently fail closed until explicitly enabled in a future release. |
| **Ticket Management** *(v0.7.0)* | Tool | Search/read/act on Jira tickets. Read on by default; write actions (update, add_comment, transition) off by default. |
| **Automation** | Tool | Multi-step workflow automation. |
| **Scheduler** | Tool | Schedules reminders and conversations via natural language. |
| **Scheduler Query** | Tool | Lists scheduled events (merged into Scheduler). |
| **Flows** | Tool | Runs and manages workflows and scheduled events. |
| **Flight Search** | Tool | Searches for flights via configured providers (Amadeus, Google Flights via SerpAPI). |
| **Shell Commands** | Tool | Executes shell commands on registered remote hosts via secure beacon agents and `/shell`. |
| **Sandboxed Tools** | Passive | Gates access to isolated security tools (nmap, dig, nuclei, httpx, whois, katana, subfinder, sqlmap, webhook). |
| **Browser Automation** | Tool | Navigates websites, fills forms, extracts content, captures screenshots. |
| **Password Vault** *(v0.7.x)* | Tool | Resolves approved vault references through 1Password-backed Hub Tool APIs with redacted outputs and short-lived handles. |
| **Knowledge Sharing** | Passive | Shares learned facts into a cross-agent memory pool. |
| **Adaptive Personality** | Passive | Extracts user facts and adapts the persona over time. |
| **OKG Term Memory** | Tool | Stores/recalls structured term memory (own knowledge graph) with MemGuard validation. |
| **Agent Switcher** | Tool | Lets users switch their default agent through `/invoke` or the LLM tool. |
| **Agent Communication (A2A)** | Tool | Enables inter-agent questions and task delegation, gated by `agent_communication_permission` rules. |
| **Custom Skill (Adapter)** | Tool | Runtime adapter for tenant-authored custom skills (Instruction / Script / MCP Server). |

Provider names in skills and Flow steps are normalized to typed Hub integrations. Brave/Tavily/Google web search credentials are configured through **Hub > Tool APIs > Add Integration > Web Search**. Google Flights is configured separately through **Hub > Tool APIs > Add Integration > Travel > Google Flights**, and agents that use the **Flight Search** skill can then select Google Flights as their provider.

**Active skill modes:** `Tool` (LLM tool call or explicit slash command), `Passive` (runs automatically after every response), and `Special` (media-triggered).

### Custom Skills

Create your own skills under **Studio > Custom Skills**. Three types:

#### Instruction Skills

No code required. Provide natural-language instructions the LLM follows.

1. Click **Create Skill** > select **Instruction**.
2. Write your instructions (up to 8,000 characters, Markdown supported).
3. Choose whether the skill is a callable tool or passive instructions. Custom skills no longer support keyword trigger mode.

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

### Code Repository skill (GitHub/GitLab) — v0.7.x

The `code_repository` skill lets agents read from GitHub or GitLab and, for providers that support it, optionally act on repository objects. It's backed by a tenant-scoped repository connection in **Hub > Developer Tools**.

**Setup:**

1. Go to **Hub > Developer Tools**, click **Add Repository Connection**, choose GitHub or GitLab, and enter the connection details. GitLab asks for a GitLab.com personal/project access token and optional default project path; GitHub asks for the GitHub token/default owner/repo fields.
2. Open an agent's **Skills** tab, click **Add Skill**, pick **Code Repository**, choose GitHub or GitLab, and select the connection you just created.
3. The capability matrix is split into **read** (default ON) and **write** (default OFF) groups:
   - **Read:** `search_repos`, `list_pull_requests`, `read_pull_request`, `list_issues`, `read_issue`.
   - **Write:** `create_issue`, `add_pr_comment`, `approve_pull_request`, `request_changes`, `merge_pull_request`, `close_pull_request`, `close_issue`.
4. Toggle write capabilities on only when you intend to grant them. The agent UI shows red **WRITE** badges next to active write capabilities; the `code_repository` tool spec the LLM sees never includes disabled actions, so the model cannot accidentally call something you've forbidden.

**GitLab mapping.** GitLab read actions map pull-request language to merge requests: `pull_request` means merge request, and `pr_number` means MR IID. Missing provider config defaults to GitHub for existing agents.

**GitLab token scopes.** Use a token that can read the target project through GitLab's API. Read flows need project API read access; project creation or provider-side webhook provisioning outside Tsushin requires broader GitLab `api` scope. In this release, Tsushin keeps GitLab repository write actions hidden and fail-closed.

**Trigger pairing.** GitHub and GitLab repository triggers can pre-filter on push, PR/MR, issue, comment/note, release/tag, and workflow/pipeline events. The matched payload is delivered to the bound agent, team, or flow with normalized repository metadata and provider-specific object details.

### Repository Automation Wizard (GitHub/GitLab) — v0.7.x

Use the **Repository Automation Wizard** as the recommended setup path for GitHub and GitLab repository automation. It keeps the primitives separate while wiring them together in one guided flow:

| Primitive | Role |
|---|---|
| **Repository Integration** | Stores GitHub or GitLab credentials once for the tenant. |
| **Trigger** | Listens for repository events, currently centered on PR/MR review criteria in the UI. |
| **Flow** | Runs deterministic Source -> Gate -> Conversation/Skill -> Notification steps after a trigger fires. |
| **Agent** | Acts with configured tools, including Code Repository and A2A when enabled. |
| **Team** | Coordinates multiple actors through line or mesh topology. |

The wizard offers two repository-review templates:

- **Review team** — creates a coordinated team with **Coordinator**, **Reviewer**, and **Merge Readiness** roles. The team trigger binding is the active route; the generated Flow is linked for deterministic review/output edits but kept inactive to avoid duplicate review runs. The **Team completion notification** selector chooses the WhatsApp contact that receives the final team summary; if your user account is mapped to an active reachable contact, the wizard preselects that contact.
- **Standalone PR/MR reviewer agent** — creates or wires one reviewer agent with Code Repository access and **A2A enabled**, then leaves the generated Flow route active so the trigger runs through that agent.

After creation, the success screen shows what Tsushin created and what still needs to be configured at the provider. Copy the inbound URL, enable the listed GitHub/GitLab events, and paste the one-time webhook secret when the trigger was newly created. Existing trigger secrets are never revealed again; use the trigger detail page's rotate-secret action if you need a replacement secret and then update the provider-side webhook.

When you open the generated Flow for a review-team automation, remember that the Flow Notification node is not the active team-summary route while the generated Flow binding is inactive. The edit modal surfaces the wired Agent Team completion target, such as `@Vini`, so you can tell who receives the final summary even though the Flow notification recipient may be blank unless you intentionally enable the Flow route.

Repository criteria should be read as PR/MR-first where the current UI is PR/MR-centered. GitHub uses pull request language; GitLab maps the same review workflow to merge requests and MR IIDs.

GitLab review output is advisory/read-only in this release. Generated reviewers can inspect merge requests and recommend approve/hold outcomes, but Tsushin does not perform GitLab MR approval or request-changes write actions unless those capabilities are explicitly enabled in a future release.

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

Triggers are the event-side counterpart to channels. They wake an agent on external events (a Jira issue is created, a webhook is called, an email matching a saved query arrives, a GitHub PR is opened, or a GitLab MR is updated) instead of on a human DM. Scheduled and recurring work is created in Flows, not as a trigger.

All trigger kinds share the same **Trigger Creation Wizard** (Hub > Triggers > "+ Add Trigger"). The wizard selects the source, criteria, and linked Hub integration where needed, then creates or wires a Flow so outputs are edited in the Flow editor. Repository triggers reuse **Hub > Developer Tools** repository connections, so a single GitHub or GitLab connection can power both repository triggers and the Code Repository skill without storing PATs on individual trigger rows. For repository-review automation, prefer the Repository Automation Wizard; it wraps this trigger setup together with the review Flow and Agent/Team template choices.

### The trigger kinds

- **Email** -- a Gmail saved-query polled every minute. Filter by subject, sender, label, body. Operators paste a saved Gmail search query (e.g., `is:unread label:support has:attachment`); the trigger fires once per matching message and dedupes on the message id.
- **Webhook** -- inbound HMAC-signed POST from any external system. The wizard generates a slug (auto or custom), an HMAC signing secret, and an inbound URL like `https://<your-host>/api/webhooks/<slug>/inbound` that you paste into the external system.
- **Jira** -- live JQL polling against a Jira Cloud project. Connect your Jira account once via Hub > Tool APIs > Jira (with an API token); the wizard then asks for a JQL query and a poll interval. One notification per deduped issue.
- **GitHub** -- repository events on a connected repo. Connect your GitHub account once via Hub > Developer Tools; the wizard then asks for the events to listen to and repository filters (branch, paths changed, author, draft state, title/body matchers for PRs).
- **GitLab** -- GitLab.com project webhook events on a connected project. Connect GitLab once via Hub > Developer Tools; the wizard asks for the full project path, events such as push or merge request, and the same shared repository criteria model.

GitHub/GitLab trigger detail pages include a provider setup card with the inbound URL, enabled events, masked secret preview, last delivery timestamp, and a rotate-secret action for users with write access. Rotation returns the replacement secret once; after that, Tsushin only shows the masked preview.

### What happens after you click "Create Trigger"

1. The trigger row is persisted (e.g., trigger #9).
2. An **auto-generated flow** is minted (e.g., flow #99) with four steps: **Source -> Gate -> Conversation -> Notification**. The flow is system-managed: you can edit its content but you can't delete it directly -- delete the trigger to remove the flow.
3. The wizard's Confirmation step shows a "Wired Flow" card with the auto-flow ID and an **Open Flow Editor** button.
4. Clicking the button takes you to `/flows?edit=<auto_flow_id>` where you can edit the Notification step's message template -- this is where you reference data from the inbound event using template variables like `{{source.payload.issue.key}}`, `{{source.payload.issue.fields.summary}}`, or `{{source.payload.pull_request.title}}`.

### Per-kind trigger-generated flow badges

Auto-generated flows are visually distinct in the flows list and the Edit Flow modal header: each trigger kind has its own coloured "Trigger" pill (Jira blue, Email emerald, GitHub violet, GitLab orange, Webhook cyan). The Delete button on auto-generated flows is disabled with a tooltip "Auto-generated from <kind> trigger -- delete the trigger to remove this flow."

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
| **Hub > Triggers** | Email / Webhook / Jira / GitHub / GitLab trigger instances. |
| **Hub > Developer Tools** | Shell Command Center, Sandboxed Tools, and GitHub/GitLab repository connections reused by repository triggers and the Code Repository skill. |
| **Hub > Tool APIs** | Programmatic credentials reused by triggers and skills: Jira API token, Password Vault (1Password), Asana OAuth, search/flight providers, etc. The Email trigger reuses the Hub > Google connection for Gmail. |
| **Hub > Local Services** | Auto-provisioned containers — Whisper / Speaches (ASR), Kokoro (TTS), Ollama (LLM), Qdrant (vector store). Lifecycle controls (start/stop/restart/logs/status) live here. |

**Wake Events** moved under **Watcher**. The standalone Schedule Trigger was retired; cron-based execution now lives only on the FlowDefinition (Flows > Create > Scheduled or Recurring).

### Aggregating outputs on the trigger detail page

The trigger detail page lists every binding kind that can fan out from a single trigger event:

- **Wired Flows** — every `flow_trigger_binding` for this trigger.
- **Wired Teams** — every `agent_team_trigger` (Webhook/GitHub/GitLab/Jira; Gmail since 2026-05-07).
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
3. Choose an **execution mode**: Immediate, Scheduled (one-time), Recurring, Keyword, or Triggered.
4. For **Triggered**, select an existing Hub trigger (Email/Gmail, Jira, GitHub, GitLab, or Webhook). Tsushin creates a locked Source step and the `flow_trigger_binding` automatically.
5. For **Scheduled**, **Recurring**, or **Keyword**, fill the required schedule, recurrence, or keyword fields before saving. Recurring flows can run hourly, daily, weekly, or monthly; use the cron override when the schedule needs a raw cron expression.
6. **Add steps** in sequence.

Browser automation CAPTCHA steps stay configurable per site: choose the image, input, submit, and success selectors in the step settings, set exact or min/max code length when needed, then select an available multimodal solver provider such as Ollama or Gemini. Selector and argument rows are edited as repeatable cards, and long node names or gate badges wrap in the Flow editor so portal profiles remain readable on desktop and mobile.

Generic tracking, scraping, and portal-monitoring flows should be reconstructable from the UI. Keep site profiles in visible step fields: browser selectors, CAPTCHA selectors, wait/result selectors, extraction scripts or rules, dedupe keys, Gate conditions, and Notification recipients/templates. If you clone a profile to a similar site, update those fields in the step editors rather than relying on a hidden site-specific runner.

### Step Types

| Step Type | What It Does |
|---|---|
| **Notification** | Sends a notification to a recipient. Supports `message_templates_by_state` (per-state templates keyed off an upstream `notification_state` such as `new_boleto`, `barcode_changed`, `paid`). |
| **Message** | Sends a single chat message. |
| **Tool** | Invokes a tool or function (built-in tool, sandboxed tool, or skill in tool mode). |
| **Conversation** | Multi-turn AI conversation with an objective (configurable max turns, default: 20). |
| **Slash Command** | Executes a platform slash command. |
| **Skill** | Runs an agent skill (built-in or custom). |
| **Summarization** | AI summarization of previous step outputs. |
| **Gate** | Conditional branch — evaluates `gate_conditions` against `gate_logic` (`all`, `any`, programmatic). v0.7.x adds `in` / `not_in` operators on list values, useful for routing on an upstream `notification_state`. |
| **Password Vault** | Resolves an approved vault reference without placing secrets in prompts. |
| **Browser Automation** | Navigate, click, fill forms, extract content, screenshot — configured through a guided wizard that picks between **🎬 Record a flow** (drive Chromium once, Tsushin compiles the selectors) and **⚙️ Configure manually** (action picker → URL → selector rows). Advanced settings (timeout overrides, session profile, integration ID, tool arguments) live behind a single collapsible toggle on the Review step. |
| **HTTP Request** | Calls an API with editable method, URL, headers, body, and secret references. |
| **Data Transform** | Extracts and normalizes fields from previous step outputs. |

The **Source** step appears only on triggered flows and is generated from the selected Hub trigger. It is locked at the top of the flow and cannot be added manually. The legacy `Trigger`, `Subflow`, and `AgentNode` step types are kept as backward-compatible aliases for older flows.

Financial templates should remain editable like any other Flow. Open a browser step to adjust URL/action/selectors, add a **Skill** or **Summarization** step for agentic reasoning, and end with a conditional **Notification** fed by a previous storage/gate output.

#### Authoring browser steps with the wizard (2026-05-26)

The **Browser Automation** step opens a guided wizard instead of the old flat panel. Every field that was previously exposed at once (Mode, Provider, Timeout, Session TTL, Profile, Integration ID, Tool Arguments, Selectors) is now staged behind the right question at the right moment.

The wizard starts with a **trail picker**:

1. **🎬 Record a flow (recommended)** — type a starting URL, the recorder modal opens with the URL already filled in, and Chromium streams into the Flows page. Every click, fill, and navigation is captured into a step ledger and compiled into the same `selectors[]` rows you'd otherwise type by hand.
2. **⚙️ Configure manually** — pick a friendly action (Open a page, Click something, Fill a form, Extract text, Wait for element, Run JS, or "More actions…"), type the URL, and the wizard shows ONLY the selector fields that action needs. No more rummaging through 6 unrelated columns to fill in one form field.

Editing an existing step opens the wizard directly on the **Review** stage with everything pre-loaded and **Advanced** collapsed, so simple tweaks stay fast. Click "← Start over" to drop selectors and pick a new trail; click "Change action" inside the Manual trail to swap actions without losing the URL.

The **Browser session profile** field is now a dropdown sourced from **Hub > Tool APIs**. Picking a profile auto-populates its integration ID; choose "— No profile —" for a fresh isolated context, or "Type a profile name instead…" to drop down to a manual text input when the API is unreachable.

The recorder can still be driven by an LLM in **▾ Agentic mode** from the recorder modal itself (requires `browser-use` from `requirements-optional.txt` and an Anthropic Provider Instance under Hub > Providers).

Whichever trail you pick, the output writes into the same `FlowStepConfig` shape — no schema change, existing flows round-trip cleanly.

##### ToolPalette tiles

- **▣ Mark captcha** drags a box over a captcha image and emits a `solve_captcha` row pointing at the next captured fill — exactly the shape the official Correios postal-tracking flow needs.
- **👁 Capture output** drags over a text region and emits an `extract` row with a named output variable for downstream steps.
- **📋 Capture timeline** drags over a tracking/event timeline (e.g. the Correios SEDEX history) and compiles a structured `execute_script` parser instead of a plain text extract. It returns an `events[]` list plus `latest_status`/`latest_at`/`latest_location`, an `event_count`, and a deterministic dedupe key (`latest_event_key`). The recorder auto-appends a `normalize_tracking` Data Transform that **exposes the parsed object as the reusable flow variable `{{normalize_tracking.data_preview.*}}`** (`latest_status`, `latest_at`, `latest_location`, `event_count`, `latest_event_key`, `tracking_code`). The recorder does **not** send anything — to deliver the update, add a **Notification** step after the recording (next section, step 10) and reference those fields. (Decoupling rationale: sending is the first-class Notification step's job; the recorder just produces the data, so the same variable can feed any channel.)
- **🔑 Vault?** chip appears on any captured fill whose field name or `type=password` suggests a credential. Click it to open the existing Password Vault picker; the plaintext value gets swapped for the picker's `op://` reference and a row is added to `browser_secret_references`. The Save button refuses to compile if any plaintext password remains.
- **▾ Agentic mode** (opt-in; requires `browser-use` from `requirements-optional.txt`) lets a Browser-Use agent drive the same recording session from a free-form prompt. Pause/resume hands control back to you mid-run. The compiled output is bit-for-bit shaped like a human recording. Requires an Anthropic Provider Instance configured under Hub > Providers for the tenant; the recorder surfaces a 503 with a setup hint when missing.

##### Worked example — replicate "Postal Track | Correios | AD468811215BR" via UI in ~2 minutes

This is the canonical browser-automation flow shipped with Tsushin. It pulls package status from the official Correios tracker (https://rastreamento.correios.com.br/app/index.php), which gates results behind a Securimage CAPTCHA. The recorder produces all five selector rows from one human pass:

1. **Flows → "+ New flow"** → name it `Postal Track | Correios | AD468811215BR` → add a **Browser Automation** step.
2. In the step's "Selectors and actions" header, click **🎬 Record**.
3. URL: `https://rastreamento.correios.com.br/app/index.php`. Click **Start recording**. Wait ~1s for the canvas to show the live page.
4. **Click the tracking input** (`Informe o código de rastreamento`) on the canvas, then type `AD468811215BR`. A `Fill` row appears in the right panel.
5. Click the **▣ Mark captcha** tile. Drag a box over the Securimage CAPTCHA image. A `Captcha` row appears with the image's selector. The recorder will automatically wire its `value_target` to the next field you fill.
6. **Click the CAPTCHA text input** (right of the image) → type any placeholder (e.g. `XXXXXX`). This becomes the `value_target` for the `solve_captcha` row. At flow execution time the `solve_captcha` skill OCRs the live image and overwrites this placeholder.
7. **Click the "Consultar" button**. A `Click` row appears.
8. After Correios responds (a few seconds), click **👁 Capture output**, drag a box over the tracking-result panel, and name the variable `delivery_status` when prompted.
9. Click **Save as flow step**. The dialog closes; the BrowserAutomationConfigPanel below is now pre-filled with five rows that look like:
   - `fill input[name="objeto"]` value=`AD468811215BR`
   - `solve_captcha img#captcha_image` value_target=`input[name="captcha"]`
   - `fill input[name="captcha"]` value=`XXXXXX` (runtime overwrites with OCR result)
   - `click button[name="b-pesquisar"]`
   - `extract <result panel selector>` as=`delivery_status`
10. **Add a Notification step at the bottom** so you actually find out the flow ran. Click *+ Add step* → choose **Notification** → set channel `whatsapp`, recipient `@Vini` (or whichever contact handle). For a **📋 Capture timeline** recording, reference the `normalize_tracking` variable the recorder exposed — the canonical message (no footer):

    ```
    Correios {{normalize_tracking.data_preview.tracking_code}} update
    Status: {{normalize_tracking.data_preview.latest_status}}
    When: {{normalize_tracking.data_preview.latest_at}}
    Location: {{normalize_tracking.data_preview.latest_location}}
    Events: {{normalize_tracking.data_preview.event_count}}
    Dedupe: {{normalize_tracking.data_preview.latest_event_key}}
    ```

    (For a plain **👁 Capture output** extract, reference its named variable instead, e.g. `{{step_1.delivery_status}}`.) The Notification step's **Variable Reference {x}** panel lists the available previous-step fields. This is a project-wide convention: every browser-automation flow should end with a notification so the success/failure is observable. A silent flow is indistinguishable from a flow that didn't run.
11. Click **Update Flow** at the top of the editor. Done — when this flow executes, the recorder replays the recorded actions, the runtime solves the live captcha, and the notification step pings you with the extracted `delivery_status`.

Alternative: under **▾ Agentic mode**, paste the prompt *"Track Brazilian postal package AD468811215BR. Fill the tracking code in the search field, mark the CAPTCHA image, and click Consultar."* and click Start. The agent drives steps 4–8 for you while you watch. Take over at any point with the Pause button. Don't forget to still append the Notification step manually before saving — the recorder doesn't add it for you.

##### Multi-FlowNode compile output (the production-ready shape, 2026-05-23)

The recorder backend's `/compile` endpoint emits *two* shapes for every recording:

- **`config_json`** — legacy single-FlowNode shape that drops into the existing `BrowserAutomationConfigPanel` editor when you click *Save as flow step*. Good for adding a single browser action to an existing flow you're editing manually.
- **`flow_nodes[]`** — production-ready multi-FlowNode shape, one FlowNode per browser action. This is what programmatic consumers (smoke-test script, future "Save as new flow" button) should use. Captcha chains automatically collapse into one canonical `solve_captcha` step with `solver_provider: "gemini"` and `solver_timeout_seconds: 120` for fast vision OCR.

Today the manual *Save as flow step* button in the recorder dialog uses the legacy shape (one step at a time). Use the smoke-test script (below) or the API directly to insert multi-FlowNode recordings into a new flow.

##### BrowserGroupStep — one card per recording (2026-05-24)

A recording-as-a-multi-FlowNode flow used to render as N flat steps interleaved with the surrounding notification / gate steps. The flow editor and the run-detail watcher now fold those consecutive browser_automation steps into a single **collapsible BrowserGroup card** with:

- **Header**: target host (e.g. *Browser session · rastreamento.correios.com.br*), a **Human / Agent / Mixed** badge that reflects the `RecordingDriver` per step (mixed when a single recording toggled modes mid-session), a child-count chip, and a "Recorded N ago" relative timestamp.
- **Expanded body**: one row per child action with a colored action chip (cyan navigate, emerald fill, sky click, amber solve_captcha, fuchsia extract), the step name, and a thumbnail captured at the moment the action was recorded.
- **Ungroup button** (real groups only): deletes the `browser_group` parent step. The children remain and resynthesize as a synthetic group on the next render — full unflatten requires deleting a child or inserting a non-browser step between them.

The same renderer powers the **Watcher → Flows → View Details** modal in **run mode**: the expanded body adds a runtime thumbnail next to each recorded one (sourced from `FlowNodeRun.output_json.screenshot_paths`) plus a status chip (completed / failed / running) so auditors can compare *what was recorded* against *what actually happened* without opening multiple tabs.

The recorder /compile endpoint now emits a *third* shape — `flow_group = { group_node, child_nodes }` — alongside `config_json` and `flow_nodes[]`. The `group_node` is a new `browser_group` step type whose runtime handler is a pure no-op (returns `completed` in 0 ms); the children execute exactly as ordinary `browser_automation` steps. All grouping data (`group_recording_id`, `group_index`, `recorded_driver`, `recorded_at`, `screenshot_b64`) lives in each child's `config_json` so the card needs no extra fetch.

**Backwards compat**: any existing flow with ≥2 consecutive `browser_automation` steps auto-renders as a *synthetic* group, marked with an amber **Auto-grouped — save to persist** badge. No migration is needed — the original flat steps are untouched in storage; only the rendering changed.

##### Smoke-test script

`backend/scripts/recorder_e2e_correios_to_vini.py` runs the whole loop end-to-end against a healthy backend: records the Correios flow via the recorder WebSocket, compiles it, creates a real FlowDefinition (browser_automation → notification @Vini), executes it, and reports structured proof of the notification leg (resolved recipient, rendered message body, MCP URL it POSTed to). Use this to validate new tenants or after stack changes:

```
docker exec tsushin-backend python /app/scripts/recorder_e2e_correios_to_vini.py
```

A healthy run ends with `OVERALL: PASS` and a WhatsApp ping to Vini. If the WhatsApp MCP isn't QR-authenticated, the script reports `STRUCTURAL PASS` and shows what message *would* have been sent so you can re-auth and re-run.

##### Constraints to know

- The recorder uses **stock Playwright** — sites that ban automated browsers may reject the inner session. For those targets, the existing manual editor still works.
- Each tenant can have **2 concurrent recordings** open at once; trying to start a third returns HTTP 409 with a "discard an existing recording first" hint.
- Recordings auto-tear down **30 minutes** after the last interaction, hard cap **2 hours**. A forgotten dialog won't leak a Chromium instance.
- **Recorder behaviour after the 2026-05-27 bug-fix wave** (PRs #214/#216/#218/#220):
  - The streamed canvas auto-focuses on first click — typing the very next character reaches the inner page (no devtools focus trick needed).
  - FILL events in the step ledger collapse one row per typed string (was one row per keystroke).
  - The captcha "Mark captcha" toolbar resolves the image selector correctly; the compiler scrubs document-root selectors (`body`/`html`/`*`) and refuses to ship them.
  - The captcha submit button is chosen from the recorded sequence by name — `button[name="b-pesquisar"]` / submit-button-like CSS — instead of the focus-click into the captcha input.
  - When the recorder didn't capture an explicit wait between submit and extract, the compiler auto-inserts `wait_tracking_result` targeting the extract's selector (only when the selector matches a content-region pattern like `.ship-steps` / `.result` / `.tracking`).
  - The captcha skill's `success_selector` is only populated when the recorded extract matches a content-region pattern — noise selectors (carousel, ads) are scrubbed so the skill doesn't exit before the page settles.
  - Newly recorded browser_automation children + new Notification steps default `on_failure='continue'` — so a single bad step never silently swallows the trailing alert.
  - The "Capture as output" naming dialog is now an in-modal form (was `window.prompt`); Cancel really cancels.
  - The notification step's MCP resolver falls back to a `tester` instance for the same tenant when no `agent` instance is registered — the default local-dev shape (e.g. a tenant whose only WhatsApp MCP is the Vini local tester on port 8082) now delivers correctly instead of silently routing to the hardcoded `127.0.0.1:8080` default.
- **Known limitation when driving the recorder from test tooling** (Playwright `computer.type`, Claude-in-Chrome, similar): OS-level keyboard simulation often delivers each character as 2-3 keydown events within microseconds, and the inter-character gap can be just as small — so a frontend time-based dedupe either keeps the noise (window too tight) or eats legitimate consecutive same-char typing such as `"88"`/`"11"` in tracking codes. Real users typing in a browser don't trigger this. **Workarounds for automation:** (a) paste the text via the canvas's clipboard-paste handler (one envelope per paste, no per-keystroke noise), or (b) record the rest of the flow normally and fix the fill value post-record in the wizard step editor.

**Step configuration:** timeout (default: 300s), retry on failure, conditions, on_success/on_failure actions (continue, skip_to, end, retry, skip), agent/persona overrides.

### System-managed (auto-generated) trigger flows

When you create a Hub trigger, Tsushin auto-generates a four-step **system-managed flow** wired to that trigger via a `flow_trigger_binding`. The flow editor is intentionally tailored when you open a system-managed flow:

- **Banner at the top of the Edit modal** reorients you: *edit the trigger to change what fires, edit the steps to change what happens after*. Includes a deep link back to the Hub trigger detail page.
- **Source step** shows a read-only **Trigger configuration** card with kind-specific inputs — JQL + project key for Jira, inbox + search query for Email, repo + events + path/branch filters for GitHub, project path + events + path/branch filters for GitLab — plus a `trigger_criteria.filters` JSON preview and an **Edit in Hub** deep link. Filters are managed on the trigger, not on the flow.
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

Trigger Case Memory is an opt-in long-term store that captures the recap of every trigger run (Email/Webhook/Jira/GitHub/GitLab) so future runs can pull a short summary of similar past cases into the dispatched flow or continuous agent. See [§ 6a](#6a-setting-up-event-triggers-v070) for trigger-side configuration. Tenant-level toggles live in **Core > Organization > Case Memory**:

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

### 9 Detection Types

1. **Prompt Injection** -- hidden commands trying to override agent instructions.
2. **Agent Takeover** -- attempts to hijack the agent's behavior entirely.
3. **Poisoning Attack** -- feeding false information to corrupt responses.
4. **Malicious Shell Intent** -- dangerous commands when agents have shell access.
5. **Memory Poisoning** -- injecting false facts into long-term memory. MemGuard validates every fact before storage.
6. **Agent Privilege Escalation** -- making an agent exceed its authorized permissions.
7. **Browser SSRF** -- forcing browser automation to access internal/restricted resources.
8. **Vector Store Poisoning** -- corrupting the vector database powering agent memory.
9. **Continuous-Agent Action Approval** *(v0.7.0)* -- gates the action plan a Continuous Agent proposes before it runs (relevant when `action_kind` is `tool_use` or `flow_dispatch`).

### Security Profiles

| Profile | Behavior |
|---|---|
| **Off** | No security analysis (development only) |
| **Permissive** | Detect and log silently (no blocking) |
| **Moderate** | Block confirmed threats (recommended) |
| **Aggressive** | Maximum sensitivity, blocks borderline cases |

Assign profiles to agents on the agent's security settings. Create custom profiles by cloning an existing one.

### Sentinel LLM Provider

Go to **Settings > Sentinel Security > LLM Configuration** to choose the Provider Instance and model Sentinel uses for analysis. Fresh setup and the first Hub-created LLM Provider Instance auto-fill this binding only while Sentinel is still unbound; after you choose a specific instance, Tsushin preserves that explicit choice. The selector uses the same compact provider/instance/model picker as **Settings > System AI**: pick an existing instance from Hub, select a discovered model, or type a manual model ID. Custom Sentinel profiles can also bind their own Provider Instance in the profile editor.

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

**Remote Access via Cloudflare Tunnel** (introduced v0.6.0; sidecar opt-out added v0.7.0) — a one-click way to expose your Tsushin instance on a public HTTPS URL without opening firewall ports or managing a reverse proxy. It is **off by default** at both the system level and the per-tenant level, so nothing becomes internet-reachable until you explicitly enable it. v0.7.0 adds an opt-out (`TSN_CLOUDFLARED_DISABLE_INPROCESS=true`) so deployments can run `cloudflared` as an external sidecar instead of as an in-process subprocess; the backend continues to own config, audit, entitlement, and status responsibilities.

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

Cloudflare Tunnel makes the entire Tsushin app reachable on one public URL, so authentication and tenant entitlement become the sole gate. The platform tightens which routes are anonymous (health, webhook receive, login) versus authenticated (everything else); v0.7.0 adds `cf-visitor` scheme honoring so the backend issues `Secure` cookies and emits HTTPS redirects when the visitor reaches the origin via Tunnel. Under Named Mode you can stack additional Zero Trust Access policies on top if you need them.

**Disabling remote access instantly:** `/system/remote-access` > **Tunnel Status** > **Stop**. The tunnel subprocess exits and no new requests can reach the instance from the public URL until you start it again.

Full technical reference (architecture diagram, supervisor behavior, troubleshooting, route hardening list): [documentation.md §22.5](documentation.md#225-remote-access-cloudflare-tunnel--v060).
