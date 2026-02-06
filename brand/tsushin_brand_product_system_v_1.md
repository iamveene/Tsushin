# Tsushin — Brand & Product System v1.0

> **Purpose**: A single, export‑ready reference to rebrand repos, docs, and assets for your agentic messaging framework.

---

## 1) Name & Concept
**Brand name:** **Tsushin**
**Kanji/Logomark:** **通信** (primary glyph **通**)
**Meaning:** “Communication / transmission.” Aligns with a multi‑channel, agentic messaging OS.

**Pronunciation:** _TSOO‑sheen_ (IPA: /tsuːʃiːn/). In Japanese romanization often written **tsūshin** (with a macron). We use "Tsushin" for global legibility.

**Positioning (one-liner):** _“The agentic messaging OS: orchestrate conversations, automate outcomes.”_

**Core idea:** Tsushin unifies channels (WhatsApp, Gmail, Telegram, etc.) behind persona‑driven agents that can converse, plan, schedule, and execute workflows.

---

## 2) Visual Identity

### 2.1 Logomark & Glyphs
- **Primary icon:** the **通** glyph (from 通信). Represents passage, flow, connection.
- **Secondary motif:** full **通信** block for headers/hero art. Use sparingly for emphasis.
- **Construction:** Set the logomark in a solid geometric form (square or rounded‑square container). Keep strokes readable at 16px.

**Clear‑space rule:** Maintain a minimum clear space equal to the cap height of the "T" in the wordmark around the icon on all sides.

** Image Logo Full ** Available here brand\logo\tsushin_fulllogo.png and should be used as the main logo.
** Image Glyph Logo ** Available here brand\logo\tsushin_smalllogo.png and should be used for small places like buttoms top-left menu badget, and so on.

**Do not:**
- Distort, add gradients, or outline strokes of 通.
- Place over busy imagery without a solid background.
- Use “Yubikami” or any previous experimental names in production marks.

### 2.2 Wordmark
Set **TSUSHIN** in a geometric sans (e.g., **Inter**, **Söhne**, **Nunito Sans**, **Geist**). Weight: Medium/Semibold. Tight tracking (‑1% to ‑2%). Case style options:
- **Uppercase**: TSUSHIN (official)
- **Title**: Tsushin (body text)

### 2.3 Color System (Please adjust for Dark MOde which is the default mode for the UI)
- **Ink** (Primary): #0B0F14
- **Indigo** (Action): #3C5AFE
- **Vermilion** (Signal): #EE3E2D
- **Fog** (UI bg): #F6F7F9
- **Slate** (Text‑secondary): #5B6674

Rules: Use Ink for wordmark; Indigo for CTAs/links; Vermilion for warnings/alerts; generous white/Fog space.

### 2.4 Iconography & Emojis
- Prefer sharp, simple system icons.
- Optional accent emoji in docs: 📨 (inbound), 🧠 (agents), 🕸️ (integrations), ⚙️ (automation).

---

## 3) Voice & Messaging
- **Tone:** confident, precise, quietly opinionated; avoid hype.
- **Style:** short sentences, verb‑led headings, concrete examples.
- **Lexicon:** “agent,” “flow,” “orchestrate,” “connector,” “skill,” “memory,” “policy.”

**Brand taglines (approved):**
1. The agentic messaging OS.
2. Orchestrate conversations. Automate outcomes.
3. One mind across every channel.
4. From message to mission—automated.

**Boilerplate (65 words):**
**Tsushin** is an agentic messaging OS that unifies WhatsApp, Gmail, Telegram, and more under persona‑driven agents. Tsushin agents converse, plan, and execute—triggering tasks, schedules, and workflows across your stack. With a modular runtime, visual flows, and a knowledge graph, Tsushin turns conversations into outcomes while preserving enterprise‑grade observability and control.

---

## 4) Product Lines & Modules

### 4.1 Suite
- **Core** — agent runtime & policy engine (execution, tools, guardrails, audit).
- **Integratation Hub** — channel connectors (WhatsApp, Gmail, Telegram, Slack, etc.), third-party services to be used as tools (brave search, weather).
- **Studio** — agent persona/skills designer, testing workbench.
- **Flows** — schedules and workflows (multistep, conditional, retries, SLAs).
- **Graph** — knowledge, memory, embeddings, and data governance.
- **Watcher** — monitoring, alerts, analytics, and run‑history.

### 4.2 SDKs & Interfaces
- **API:** REST + webhooks;
- **CLI:** `tsushin` (alias `tsu`), with subcommands: `init`, `agent`, `flow`, `channel`, `deploy`, `logs`, `secr``ets`.

### 4.3 Naming Rules
- Products: **Tsushin <Noun>** (Core, Integration Hub, Studio, Flows, Graph, Watcher).
- Internal packages: `@tsushin/<module>` or `github.com/tsushin/<module>`.
- Agent templates: **Tsushin Persona: <Name>** (e.g., Tsushin Persona: Operator).
- Connectors: **Tsushin Hub: <Channel>** (e.g., Tsushin Hub: WhatsApp).

---

## 5) Logo Usage Library (ASCII for quick reference)
```
[ Primary Icon ]               [ Wordmark ]
┌───────────┐                  TSUSHIN
│    通     │                  (Geometric sans, Medium/Semibold)
└───────────┘
```

Use provided SVGs in the /brand folder (see checklist below). Keep monochrome for most product UIs; reserve color for marketing.

---

## 6) Domains & URLs
- **Primary:** **tsushin.io**
- **Secondary:** **tsushin.ai** → 301 redirect to .io

**DNS/Infra quick spec:**
- `www.tsushin.io` → main site (A/AAAA or CNAME to CDN).
- `api.tsushin.io` → public API (JWT + mTLS optional).
- `console.tsushin.io` → Flows/Studio.
- `docs.tsushin.dev` → developer docs (Docusaurus/Next).
- `cdn.tsushin.io` → assets.
- `status.tsushin.io` → status page.

**Email:** hello@tsushin.io, support@, security@, press@.

---

## 7) Codebase Rebrand Checklist
**Repos & Packages**
- Rename org to **tsushin‑org** (or **tsushin‑labs**).
- Migrate packages to `@iamveene/tsushin/*` / `github.com/iamveene/tsushin/*`.

**Namespaces & Identifiers**
- Prefix env vars with `TSN_` (e.g., `TSN_ENV`, `TSN_HUB_WHATSAPP_TOKEN`).
- Service names: `tsn-core`, `tsn-hub`, `tsn-studio`, `tsn-flows`, `tsn-graph`, `tsn-watch`.

**Binaries & CLI**
- Binary names: `tsushin-core`, `tsushin-hub`, etc.
- CLI: `tsushin` (alias `tsu`).

**Config & Files**
- Global config: `tsushin.yaml`.
- Default data dir: `~/.tsushin/`.
- Log format: JSON w/ fields `tsn.run_id`, `agent.id`, `flow.id`, `channel`, `latency_ms`.

**Telemetry**
- User agent: `Tsushin/<version> (<lang>)`.
- Metrics prefix: `tsn.*`.

**Docs**
- Update README, CONTRIBUTING, CODE_OF_CONDUCT.
- Replace all legacy names (search for Yubi*, Message*, etc.).

---

## 8) UX Writing & API Style
- **Endpoints:** `/v1/agents`, `/v1/flows`, `/v1/hub/channels`, `/v1/runs`, `/v1/webhooks`.
- **Resource nouns:** agent, persona, skill, tool, connector, message, run, schedule, task.
- **Verbs:** send, plan, execute, escalate, retry, cancel.
- **Errors:** machine‑readable codes like `TSN_AGENT_NOT_FOUND`.

**CLI patterns:**
```
# create an agent
$ tsushin agent create --name "Operator" --persona operator.yaml

# connect WhatsApp
$ tsushin channel add whatsapp --token $TSN_HUB_WHATSAPP_TOKEN

# deploy a flow
$ tsushin flow deploy flows/support-intake.yaml
```

---

## 9) Design System Snippets
- **Buttons:** Solid Indigo for primary actions; Ghost Ink for secondary.
- **Cards:** rounded‑xl, soft shadows, lots of Fog.
- **Tables:** monospace for IDs; wrap long hashes.
- **Dark mode:** invert background to #0B0F14; maintain Indigo links.

---

## 10) Legal & Trademark Notes
- "Tsushin" is a common Japanese noun; assess trademark registrability in target jurisdictions.
- Prefer distinct logomark (custom **通**) + suite naming for distinctiveness.
- Maintain an IP log of first public use (site launch, repo timestamps).

---

## 11) Launch Copy Blocks
**Hero**
Tsushin (通信) is the agentic messaging OS. Orchestrate conversations, automate outcomes, and connect WhatsApp, Gmail, Telegram, and more—through persona‑driven agents that think, plan, and execute.

**Why Tsushin**
- One runtime for agents, flows, and tools
- First‑class connectors for every channel
- Visual orchestration with enterprise guardrails
- Knowledge & memory that respects governance

---

## 13) Roadmap Names (Optional)
- **Tsushin Atlas** — multi‑tenant workspace & org graph.
- **Tsushin Relay** — high‑throughput message bus.
- **Tsushin Forge** — template marketplace for agents/flows.

---

## 15) Appendix — Quick References
- **Primary name:** Tsushin
- **Glyph:** 通 (full: 通信)
- **Tagline:** The agentic messaging OS
- **Suite:** Core, Hub, Studio, Flows, Graph, Watch
- **CLI:** `tsushin` (alias `tsu`)
- **Env prefix:** TSN_
- **Primary domain:** tsushin.io
- **Accent color:** Indigo #3C5AFE
