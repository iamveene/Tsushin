# Changelog

All notable changes to the Tsushin project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Track B — Trigger Breadth (2026-04-24)

**Added:**
- Jira, Schedule, and GitHub trigger instance models, migrations, CRUD APIs, default-agent bindings, trigger catalog entries, and shared dispatch registration. Track B adapter migrations now chain `0058 -> 0052 -> 0053 -> 0054`.
- Webhook trigger criteria on `WebhookIntegration`, with JSONPath-style payload matchers evaluated before dispatch. Non-matching signed webhook payloads can return `204 No Content` and write a `filtered_out` dedupe outcome without creating wake/run rows.
- Jira JQL test-query support, Schedule cron preview and due-trigger polling, and GitHub signed inbound webhook support using `X-Hub-Signature-256` plus delivery-id dedupe.
- Hub Communication UI for Jira/Schedule/GitHub trigger cards, setup modal flows, trigger detail pages, Webhook criteria editing/testing, and wake-event filters.
- Shared trigger criteria builder for setup/detail pages, including inline JSONPath payload testing for Webhook criteria.
- Focused backend regression coverage for Track B dispatch registration, route CRUD, tenant isolation, criteria filtering, schedule poll/no double-fire behavior, Jira normalization, and GitHub signature/filter handling.

**Changed:**
- SchedulerWorker now polls trigger-backed schedules through `ScheduleTrigger` after legacy scheduled-event polling, keeping `ScheduleChannelInstance` as the trigger source of truth and avoiding duplicate `ScheduledEvent` execution.
- Default-agent settings now include Jira, Schedule, and GitHub trigger instances alongside Email/Webhook trigger defaults.
- Webhook trigger CRUD now exposes `default_agent_id` and `trigger_criteria`, while preserving the existing signed inbound queue contract.

**Validated:**
- `python -m py_compile` passed for all touched backend app/model/route/channel/migration modules.
- Targeted backend bundle passed: `32 passed` for dispatch, Jira, Schedule, GitHub, and trigger-wizard drift tests.
- Static Alembic graph check reports single head `0054` over the reserved `0058 -> 0052 -> 0053 -> 0054` chain.
- Targeted frontend ESLint passed for the new trigger components, Webhook setup/edit/detail surfaces, and Jira/Schedule/GitHub detail pages.
- `git diff --check` passed.

### Track B — Trigger Dispatch Foundation (2026-04-24)

**Added:**
- Shared trigger dispatch foundation for future Jira, Schedule, GitHub, Webhook, and Email trigger adapters. The foundation normalizes trigger events, resolves tenant-owned trigger instances from persisted rows, deduplicates events, stores redacted payload references, and creates wake/run evidence for active continuous subscriptions.
- Focused backend regression coverage for trigger dedupe, tenant ownership, payload-ref creation, subscription matching, and webhook dual-write behavior.
- Public QA summary for the foundation-only Track B slice at `docs/qa/v0.7.0/track-b-dispatch-foundation-summary.md`.

**Changed:**
- Webhook inbound handling preserves the existing signed `202 {status, queue_id, poll_url}` direct queue contract while also writing continuous-agent wake evidence when matching subscriptions exist.
- `TriggerEvent` now carries an explicit `event_type` while keeping `trigger_type` for backward compatibility with the existing trigger base contract.
- `docs/internal/v0.7.0-migration-slots.md` now records the actual `0059` ASR default migration and states that later Track B adapter migrations chain from current head as `0052 -> 0053 -> 0054`.

**Contract notes:**
- This slice intentionally creates no Track B adapter migrations. Jira, Schedule, and GitHub instance tables remain deferred.
- `ChannelEventRule` remains conversational-channel-only; trigger criteria storage and UI builders remain deferred.
- `continuous_task` queue dispatch remains reserved and is not enqueued by this foundation.

**Validated:**
- Local and integrated root backend regression bundles both passed the Track B/provider/control-plane slice (`43 passed` after integration).
- Root backend no-cache rebuild succeeded via `docker-compose build --no-cache backend && docker-compose up -d backend`; backend/frontend/postgres/proxy were healthy.
- Direct backend and HTTPS proxy `/api/health` returned healthy, and Alembic `current`/`heads` both reported `0058 (head)`.
- Live signed webhook smoke returned the existing `202 {status, queue_id, poll_url}` contract, duplicate delivery returned the same queue id, matching continuous subscriptions produced one wake event plus one queued continuous run, payload redaction stored secrets out-of-row, and cross-tenant wake detail access returned `403`.
- Browser smoke covered Hub Communication, `/hub/wake-events`, `/continuous-agents`, webhook trigger detail, email trigger detail, and Watcher Dashboard with no console errors, page errors, failed requests, or HTTP 4xx/5xx responses.

### Wave 3A — Track C UI readiness + Track F agentic-loop core (2026-04-23)

**Added:**
- Alembic `0049_add_agent_skill_tool_result_columns.py`, `0057_add_platform_agentic_bounds.py`, and `0058_add_agent_max_agentic_rounds.py` for the Track F schema slice. `0049` adds `conversation_thread.agentic_scratchpad` plus `agent_skill.auto_inject_results`, `skip_ai_on_data_fetch`, `max_result_bytes`, `max_results_retained`, and `max_turns_lookback`; `0057` adds platform min/max agentic bounds on `Config`; `0058` adds per-agent `max_agentic_rounds` and `max_agentic_loop_bytes`. The chain now lands on single Alembic head `0058`.
- `backend/agent/followup_detector.py` and focused Track F tests covering English/Portuguese follow-up references, fresh-fetch override phrases, agentic loop caps, bounded DATA injection, queue scratchpad redaction, tenant/API-client queue ownership, and Option X single-shot preservation.
- Read-only Track C UI surfaces for `/continuous-agents`, `/continuous-agents/{id}`, `/hub/wake-events`, `/hub/triggers/email/{id}`, and `/hub/triggers/webhook/{id}` against the existing A2 read contracts.
- Frontend client methods/types for continuous agents, continuous runs, wake events, email-trigger delete, trigger detail reads, and conversational channel routing rules.
- Channel routing-rule UI in Hub Communication for WhatsApp, Telegram, Slack, and Discord only, plus Watcher handling for `type=continuous_run`.
- Onboarding step 16, "Triggers & Continuous Agents", pointing users toward the Hub Communication trigger and continuous-agent surfaces.

**Changed:**
- API v1 agent creation now defaults omitted `max_agentic_rounds` to `1`, preserving prior single-shot behavior unless a caller opts into more rounds.
- API v1 async queue polling exposes a top-level `agentic_scratchpad` only when `include_scratchpad=true`; nested `result.agentic_scratchpad` remains redacted.
- Playground/API-v1 Gmail follow-ups can now reuse structured tool DATA from `conversation_thread.agentic_scratchpad` without re-calling the Gmail tool when the follow-up detector identifies a same-skill reference.
- Agentic DATA reuse now preserves the prior scratchpad when the follow-up answer produces no new tool result.

**Validated:**
- `docker-compose build --no-cache backend` and `docker-compose up -d backend` from the root stack succeeded; backend/frontend/postgres/proxy were healthy.
- Direct backend and HTTPS proxy `/api/health` returned healthy; Alembic `current` and `heads` both reported `0058 (head)`.
- M-3 audit query found `0` legacy `agent_skill.config` rows using the new Track F toggle keys.
- Container tests: `20 passed, 4 deselected, 17 warnings` for Track F/provider parser coverage; `15 passed, 2 warnings` for A2 continuous control plane, email triggers, and default agents.
- Live API smoke returned `200` for `/api/continuous-agents`, `/api/continuous-runs`, and `/api/wake-events`.
- Live `movl` API-v1 two-turn scenario: turn 1 used `skill:gmail_operation`; turn 2 returned with `tool_used=null`; `conversation_thread.agentic_scratchpad` remained length `1`; the recent `agent_run` rows showed the second run without a tool.
- Browser smoke covered Hub Communication, `/continuous-agents`, `/hub/wake-events`, webhook trigger detail, `/settings/default-agents`, `/settings/asr`, and Watcher with 0 console errors.
- Targeted ESLint passed for the Track C/Watcher/onboarding files. Full `npm --prefix frontend run typecheck` is still blocked by existing repo-wide TypeScript debt outside this slice.

### Track A2 — Continuous-Agent Control Plane backend contracts (2026-04-23)

**Added:**
- Alembic `0047_add_continuous_agent_models.py` for `delivery_policy`, `budget_policy`, `continuous_agent`, `continuous_subscription`, `wake_event`, `continuous_run`, plus managed `is_system_owned` flags on `custom_skill` and `flow_definition`.
- Alembic `0050_add_channel_event_rule.py` for channel routing rules. `0047` revises current release head `0059`, and `0050` revises `0047` to avoid multi-heads while preserving Track A2's allocated IDs.
- Read-only continuous-agent APIs: `GET /api/continuous-agents`, `/api/continuous-runs`, and `/api/wake-events` plus `{id}` detail endpoints. Pagination returns `items`, `total`, `limit`, `offset`.
- Generic routing-rule API at `/api/channels/{channel_type}/{instance_id}/routing-rules` for conversational channels; `POST /api/channels/slack/{id}/routing-rules` is the Slack contract Track C can target.
- `ContinuousBudgetLimiter` with `budget_kind` keying and exhaustion decisions (`pause`, `degrade_to_hybrid`, `notify_only`), plus `WatcherActivityService` events for `type=continuous_run`.

**Changed:**
- Gmail send/reply/draft now invokes Sentinel's `continuous_agent_action_approval` detection when the skill config carries explicit continuous-agent context.
- `docs/internal/v0.7.0-fk-cascades.md` now records Phase 2 FK behavior, including `wake_event.tenant_id` and `continuous_run.tenant_id` as `RESTRICT`.

**Contract notes:**
- Continuous-agent write endpoints are intentionally deferred in this checkpoint.
- `wake_event` stores only `payload_ref`; inline payload and payload-fetch APIs are not part of A2.
- Trigger details remain per-type APIs (`/api/triggers/email`, `/api/triggers/webhook`) for now.
- `continuous_run.wake_event_ids` is JSONB to match the ORM JSON list contract used by the control-plane APIs.
- API-client `api_readonly`, `api_member`, `api_admin`, and `api_owner` scopes include `watcher.read` so `/api/continuous-runs*` and `/api/wake-events*` work through the same public API auth path as `/api/continuous-agents*`.

### Track A Phase 1 control plane — Default Agents + Email Triggers (2026-04-23)

Phase 1's routing control plane is now implemented in the Track A worktree and ready for integrated validation/merge sequencing.

**Added:**
- Alembic `0051_add_email_trigger_instance.py` and `EmailChannelInstance` so Gmail-backed trigger rows are first-class tenant resources rather than ad hoc wizard state.
- `backend/api/routes_default_agents.py` with `GET /api/settings/default-agents`, `PUT /tenant`, `PUT /instances/{channel_type}/{instance_id}`, `POST /users`, and `DELETE /users/{id}`.
- `backend/api/routes_email_triggers.py` with `GET/POST /api/triggers/email` and `GET/PATCH /api/triggers/email/{id}` for persisted email-trigger CRUD.
- `frontend/app/settings/default-agents/page.tsx` plus a new Settings card linking to it.
- Shared modal-based `frontend/components/ui/Wizard.tsx`, `frontend/components/triggers/TriggerWizard.tsx`, and `frontend/components/triggers/EmailTriggerWizard.tsx`.

**Changed:**
- `backend/channels/catalog.py` now exposes `email` in `TRIGGER_CATALOG`, and the default-agent service resolves `email` trigger rows through the trigger precedence chain.
- Hub Communication now has a dedicated **Triggers** launcher and an **Email Triggers** section. Gmail remains managed as a reusable account resource under Productivity; it is no longer offered by the channel wizard.
- Agent Studio (`frontend/app/agents/page.tsx`) removed the inline "set default" editing path and now points users to `/settings/default-agents` for routing changes.
- `backend/tests/test_wizard_drift.py` now guards the Trigger wizard fallback array in addition to the existing channel/productivity/provider drift checks.

**Validated:**
- `python3 -m pytest -q -o addopts='' tests/test_default_agent_service.py tests/test_channel_trigger_split.py tests/test_routes_default_agents.py tests/test_routes_email_triggers.py` -> `16 passed, 123 warnings`
- `./node_modules/.bin/eslint app/settings/default-agents/page.tsx components/triggers/TriggerWizard.tsx components/triggers/EmailTriggerWizard.tsx components/integrations/ChannelsWizard.tsx --max-warnings 0` -> clean
- `git diff --check` -> clean

### Track E — audit-log hardening + shell/beacon throttles (2026-04-23)

- Tightened tenant audit filtering in `backend/api/routes_audit.py` so date-only `from_date` / `to_date` inputs expand to whole-day bounds and inverted ranges fail fast with `400` instead of silently dropping same-day events after midnight.
- Added shell audit action constants and fixed `backend/services/shell_approval_service.py` to write real tenant-scoped `AuditEvent` rows for approval requested / approved / rejected / expired transitions; the old path imported a non-existent helper and only fell back to logger output.
- Closed the Shell Command Center REST bypass in `backend/api/routes_shell.py`: direct `POST /api/shell/commands/{shell_id}` now enforces the shared per-command rate limiter before security-pattern checks, persists blocked attempts for auditability, emits tenant audit events for queued / blocked / pending-approval commands, and returns `429` with `Retry-After: 60` on command bursts.
- Added per-beacon throttles on the Shell Beacon HTTP endpoints in `backend/api/routes_shell.py`: `/register`, `/checkin`, `/result`, `/beacon/version`, and `/beacon/download` now use bounded in-memory rate limits keyed by beacon + action, with check-in / result caps derived from `poll_interval` so noisy or looping beacons cannot spam the backend indefinitely. Session-authenticated beacon downloads are also capped per user.
- Fixed `POST /api/shell/approvals/expire-old` to expire only the current tenant's stale approvals instead of sweeping pending approvals across tenants.
- Hardened the audit UI in `frontend/app/settings/audit-logs/page.tsx` and `frontend/components/rbac/AuditLogEntry.tsx`: Shell is now a first-class audit/syslog category with dedicated iconography, CSV export is only shown to `audit.export`, and export failures surface to the user instead of failing silently.
- Added focused regression coverage in `backend/tests/test_track_e_shell_audit_hardening.py` for audit date bounds, beacon-rate math/enforcement, the REST shell 429 audit path, tenant-scoped approval expiry, and shell-approval actor resolution.

### Fix — Gmail draft capability now tracks `gmail.compose`, and the live gate exposes incomplete outbound upgrades (2026-04-23)

Track G's Phase 3.1 exit proof against the dedicated Gmail fixture account surfaced a real scope mismatch: `users.messages.send` and `reply_to_message()` succeeded with the current `gmail.send`-scoped integration, but `users.drafts.create` returned `403 Forbidden` because Gmail draft creation requires `gmail.compose`, `gmail.modify`, or `mail.google.com/` ([users.drafts.create](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.drafts/create), [users.messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send), [Choose Gmail API scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)).

**Changed:**
- `backend/hub/google/gmail_service.py` now distinguishes send-compatible scopes from draft-compatible scopes. `send_message()` / `reply_to_message()` accept any Gmail scope that Google documents for `users.messages.send`, while `create_draft()` now fails fast with an explicit `gmail.compose` reauthorization error instead of surfacing Gmail's raw 403 after the request has already gone out.
- `backend/api/routes_google.py` now requests both `gmail.send` and `gmail.compose` when `include_send_scope=true` is used, and Gmail integration list responses expose `can_send` and `can_draft` separately so UI flows can distinguish "send/reply only" from "full send + draft".
- `frontend/components/integrations/GmailSetupWizard.tsx` now advertises the full outbound scope set (`gmail.readonly + gmail.send + gmail.compose`) and labels legacy integrations accurately: send/reply can be enabled before drafts are.
- `backend/services/email_command_service.py` now reports outbound send/reply vs. draft readiness separately in `/email info`.
- Added regression coverage in `backend/tests/test_gmail_send_phase3_checkpoint.py` for compose-compatible send and draft-scope enforcement, plus an opt-in root-only live gate in `backend/tests/test_gmail_send_phase3_live_gate.py` that is skipped by default and fails if root runs it before the fixture has a draft-compatible scope.

**Validated:**
- Direct live `GmailService.send_message()` against integration `1` succeeded and was discoverable via `in:sent`.
- Direct live `GmailService.reply_to_message()` succeeded and the live Gmail thread reached 2 messages.
- Live `GmailSkill.execute_tool({"action":"send", ...})` succeeded and the sent mail was discoverable via `in:sent`.
- Direct live `GmailService.create_draft()` is still blocked on the current fixture account because that integration has `gmail.send` but not `gmail.compose`; the new behavior now surfaces that as an explicit permission error instead of a downstream 403.
- Full Phase 3.1 completion is not claimed here: root must re-authorize the fixture with `gmail.compose` or a broader Gmail write scope, then run the opt-in live gate and optional full API/agent-chat scaffold.

### Wave 1 checkpoints — Track A/F foundation + Track G Gmail send (2026-04-23)

Wave 1 has started landing on `release/0.7.0` in safe checkpoints rather than waiting for every downstream phase to finish.

**Track A backend checkpoint merged:**
- Introduced the `EntryPoint` split in `backend/channels/`: `Channel` now covers conversational transports, `Trigger` covers event-driven wake sources, and outbound dispatch is centralized in `backend/channels/dispatch.py` so conversational replies still call `Channel.send_message(...)` while webhook callbacks now flow through `Trigger.notify_external_system(...)`.
- Moved webhook to the trigger catalog as `WebhookTrigger` (`backend/channels/webhook/trigger.py`), added `GET /api/triggers`, and made `/api/triggers/webhook/*` the canonical CRUD surface. The Hub Communication view now renders separate **Communication Channels** and **Webhook Triggers** sections, and the guided `+ Add Channel` flow no longer offers webhook as a selectable channel.
- Added Alembic `0046_add_default_agent_fks.py`, which backfills `default_agent_id` onto WhatsApp / Telegram / Slack / Discord / Webhook instance rows and creates `user_channel_default_agent` with `tenant_id` stored as `String(50)` plus SQL backfills from the legacy reverse FKs on `agent`.
- Added `backend/services/default_agent_service.py` to centralize v2 default-agent resolution. Channels now resolve explicit agent -> contact mapping -> user/channel override -> instance default -> legacy bound agent -> tenant default, while triggers use the shorter explicit -> instance default -> legacy bound agent -> tenant default chain.
- Added targeted regression coverage in `backend/tests/test_channel_trigger_split.py` and `backend/tests/test_default_agent_service.py` for registry separation, outbound channel-vs-trigger dispatch, and trigger/channel default-agent resolution behavior.

**Track F0 prep merged:**
- Extracted `_parse_tool_call_block()` and `_parse_tool_call_response()` in `backend/agent/agent_service.py` so the upcoming multi-round loop work can extend one parser boundary instead of re-editing the live tool-call path inline.
- Added reserved top-level config-key auditing to `backend/agent/skills/skill_manager.py` to protect future scratchpad / queue metadata from colliding with existing `agent_skill.config` payloads before the Phase 6 schema lands.
- Added prep-only regression coverage in `backend/tests/test_provider_instance_hardening.py` for the new parser boundary and reserved-key audit helpers. No schema/API behavior changed in this Track F slice yet.

**Track G Gmail-send checkpoint merged:**
- Extended `backend/hub/google/gmail_service.py` with `send_message(...)`, `reply_to_message(...)`, and `create_draft(...)`, and threaded those capabilities through `backend/services/email_command_service.py` plus `backend/agent/skills/gmail_skill.py` so outbound Gmail actions are first-class tool calls instead of read-only placeholders.
- Tightened the Gmail OAuth contract so outbound send/reply actions fail closed unless the integration has a Gmail send-compatible scope, draft creation requires `gmail.compose` (or a broader Gmail write scope), and the Hub/API reauthorization surfaces request `include_send_scope=true` to add both `gmail.send` and `gmail.compose` when a tenant upgrades an older read-only Gmail integration.
- Updated Gmail capability copy across the Hub setup wizard, agent skill descriptions, and privacy docs so the product now explicitly advertises read + send behavior rather than stale read-only messaging.
- Added targeted regression coverage in `backend/tests/test_gmail_send_phase3_checkpoint.py` for send, draft, reply, and scope-gating behavior.

**Verified:**
- `docker-compose build --no-cache backend frontend`
- `docker-compose up -d backend frontend`
- `curl -fsS http://localhost:8081/api/health` -> healthy
- `curl -fsS http://localhost:8081/api/readiness` -> ready
- `docker exec tsushin-backend python -m pytest -q -o addopts='' tests/test_channel_trigger_split.py tests/test_default_agent_service.py` -> `6 passed, 2 warnings`
- `docker exec tsushin-backend python -m pytest -q -o addopts='' tests/test_gmail_send_phase3_checkpoint.py` -> `6 passed, 2 warnings`
- `python3 -m pytest -q -o addopts='' backend/tests/test_wizard_drift.py -k 'channel_catalog or channels_wizard'` -> `2 passed, 12 deselected`
- `python3 -m pytest -q -o addopts='' backend/tests/test_provider_instance_hardening.py` -> `6 passed, 20 warnings`
- Playwright headed validation on `https://localhost/hub` confirmed a separate **Webhook Triggers** card group, `+ New Webhook Trigger`, and an `+ Add Channel` modal that offers WhatsApp / Telegram / Slack / Discord / Gmail (inbound) but no webhook. Console showed 0 errors; the only warnings were repeated CSS preload notices captured in private QA evidence.
- Playwright headed validation on the Hub Gmail wizard confirmed the setup copy now advertises `Read + outbound (gmail.readonly + gmail.send)`, explains that existing read-only integrations need reauthorization, and logs 0 browser console errors beyond the same CSS preload warnings.

**Still open after that checkpoint:** Track A Phase 2 continuous-agent models, the live Gmail outbound integration gate (real send + Sent visibility), and the actual Phase 6 schema/API/UI work (`0049`, `0057`, `0058`, scratchpad exposure, multi-round loop).

### Feat — Agent knowledge documents can be renamed and tagged without a schema migration (2026-04-23)

Track E's first reviewable checkpoint adds lightweight metadata editing for per-agent knowledge documents without consuming migration slot `0055`.

**Changed:**
- `backend/api/routes_knowledge_base.py` now returns `tags` on knowledge-document reads and exposes `PATCH /api/agents/{id}/knowledge-base/{knowledge_id}` for renaming a document and updating its tags.
- `backend/agent/knowledge/knowledge_service.py` persists document tags in an atomic sidecar metadata file next to the uploaded knowledge document, validates tag count/length instead of silently truncating user input, surfaces corrupt metadata as an error, and keeps rename operations limited to the stored `document_name` without moving the underlying file path.
- `frontend/components/AgentKnowledgeManager.tsx` adds an Edit flow so tenant users can rename a document and manage comma/newline-separated tags directly from the agent knowledge screen, with client-side guidance for the 12-tag / 48-character limits.
- `frontend/lib/client.ts` now models `tags` on `AgentKnowledge` and provides an `updateKnowledgeDocument()` helper for the new PATCH route.

**Validated:**
- Added focused backend coverage in `backend/tests/test_agent_knowledge_metadata.py` for name sanitization, explicit tag validation, atomic sidecar persistence/rollback behavior, and corrupt-metadata surfacing.

### Track D — backend-only Whisper/Speaches ASR checkpoint (2026-04-23)

**Added:**
- Alembic `0048` and `ASRInstance` for tenant-scoped Whisper/Speaches rows, including encrypted per-instance auth tokens, default model selection, runtime URL, and managed-container metadata.
- Alembic `0059` and `Tenant.default_asr_instance_id` so each tenant can choose a default local ASR instance while preserving OpenAI Whisper as the null/default fallback. Track D intentionally targets `down_revision='0051'` because Track F owns `0049`; root integration should merge this after Track A `0051`.
- `backend/services/whisper_instance_service.py`, `backend/services/whisper_container_manager.py`, and `backend/api/routes_asr_instances.py` to create/list/update/delete ASR instances and manage their container lifecycle on the reserved `6400-6499` port range.
- `backend/hub/providers/asr_provider.py`, `backend/hub/providers/asr_registry.py`, `backend/hub/providers/openai_asr_provider.py`, and `backend/hub/providers/whisper_asr_provider.py` for a dedicated speech-to-text provider abstraction.
- `/api/settings/asr/default`, frontend client methods for ASR instances/defaults, `/settings/asr`, and a shared transcript/ASR selector now used by the Audio Agents Wizard, the regular Agent Wizard audio step, and Agent Skills Manager.

**Changed:**
- `backend/agent/skills/audio_transcript.py` now resolves `audio_transcript.config.asr_mode` (`openai`, `tenant_default`, `instance`), preserving the legacy `asr_instance_id` path for pinned local instances and falling back to OpenAI Whisper when the selected local route is unavailable.
- Authenticated container warm-up now uses `POST /v1/audio/transcriptions` with the per-instance credentials instead of trusting the public `/health` endpoint alone, so ASR containers are only marked healthy after auth + model load succeed.
- Speaches managed containers now mount the model cache at `/root/.cache/huggingface`, matching the root user used by the image rather than the previous `/home/ubuntu` path.
- Tenant default ASR is cleared when the selected instance is deactivated, deleted, or detected stale/inactive during default lookup.
- `backend/api/routes_skills.py` validates tenant-scoped `audio_transcript.asr_instance_id` values before persisting them, so agents cannot save cross-tenant ASR references.

**Validated:**
- `python -m pytest -q -p no:cacheprovider -o addopts='' backend/tests/test_audio_transcript_skill_asr.py backend/tests/test_whisper_container_manager.py` -> `15 passed` (explicit local instance, tenant default instance, forced OpenAI resolution, stale/deactivated tenant-default clearing, and existing ASR container-manager coverage).
- `npx eslint --no-warn-ignored components/AgentSkillsManager.tsx components/agent-wizard/hooks/useCreateAgentChain.ts` -> passed.

### Build Prep — v0.7.0 Phase 0 foundation (2026-04-23)

Phase 0 of v0.7.0 now has the serial foundation needed before release-track worktrees fan out.

**Added:**
- Alembic `0045` for `message_queue.message_type`, the `channel_event_dedupe` audit ledger, and Sentinel continuous-agent approval toggles.
- Central inclusive `PORT_RANGES` in `backend/services/container_runtime.py`, shared by vector-store, SearXNG, Kokoro, Ollama, MCP, and future Whisper/Speaches provisioning.
- `backend/services/queue_router.py`, preserving the existing `playground`, `whatsapp`, `telegram`, `webhook`, `api`, `slack`, and `discord` inbound branches while reserving `trigger_event` and `continuous_task` discriminators.
- Sentinel `continuous_agent_action_approval` detection registration, heuristics, idempotent seed defaults, and effective-config plumbing surfaced through `/api/sentinel/detection-types`.
- Frontend Playwright visual baseline scaffolding under `frontend/tests/visual/` with deterministic committed baselines and private runtime output under `.private/qa/v0.7.0/`.
- Internal Phase 0 docs for migration slots, FK cascade decisions, Speaches auth, and background-job durability.
- Phase 0.5 fixture gate hardening: committed ASR speech clips under `backend/tests/fixtures/`, validation coverage in `backend/tests/test_phase0_5_fixtures.py`, a canonical Gmail fixture path shared by exporter/loader, a fail-closed Gmail OAuth release gate, Gmail re-authorization paths (API + Hub UI) that request `gmail.send` for the dedicated Phase 0.5 fixture account, and exporter support for resolving the Google token-encryption key from the live config store when env-only lookup is unavailable.

### Fix — ProviderWizard Review step showed misleading "Models — Missing" deadlock for TTS (2026-04-22)

After the previous fix made OpenAI/Gemini TTS visible in the Add Provider wizard, the user reported the Review step (Step 6) still showed "**Models — Missing — go back and add at least one.**" in red for cloud TTS providers. Even though the Create button was technically enabled (no `disabled` attribute), the strong visual signal made the UX appear deadlocked — the user couldn't tell whether finalizing would work. Same pattern as the StepTestAndModels gate fix: a row that's load-bearing for LLM providers (`available_models`) was rendered uncritically for TTS, where the concept doesn't apply.

**Fix:**
- `frontend/components/provider-wizard/steps/StepReview.tsx`: when `modality === 'tts'`, the row now renders as **"Voices & models — Picked per-agent in the Audio Agents Wizard"** (gray, informational) instead of the LLM-shaped "Models — Missing" red error. Discovery URL is `/api/tts-providers/{provider}/voices` and `/models`, both surfaced in the Audio Agents Wizard.
- `frontend/components/provider-wizard/steps/StepReview.tsx`: hides the **"Default instance"** row entirely for cloud-TTS-via-api_keys (ElevenLabs/OpenAI/Gemini). Those vendors save through `POST /api/api-keys` which is keyed `(service, tenant_id)` — there's at most one row per service per tenant, so "default" doesn't apply. Kokoro (TTS local) and LLM/Image still show the row because they create real `TTSInstance` / `ProviderInstance` rows that support multi-instance default routing.
- `frontend/components/provider-wizard/steps/StepTestAndModels.tsx`: same logic — hides the **"Set as default for {vendor}"** checkbox at the bottom of Step 5 for the same cloud-TTS-via-api_keys cases, so the toggle never shows up only to be ignored at save time.

**Verified end-to-end (Playwright):** Walked the wizard Modality=TTS → Cloud → Gemini → Step 4 (throwaway `AIza`-prefixed key) → Step 5 (no Set-as-default checkbox, info card visible) → Step 6 (Voices & models row in gray, no Models/Missing row, no Default instance row, Create button enabled). Discarded without clicking Create — verified the production Gemini key (`AIza...Dlug`, id 1) was not overwritten. 0 console errors.

### Fix — ProviderWizard (Hub → Add Provider) was missing OpenAI TTS and Gemini TTS vendor cards (2026-04-22)

User-visible symptom: opening Hub → AI Providers → "+ New Instance" → Modality=TTS → Hosting=Cloud showed only **ElevenLabs** with the message "Only one provider fits your choices — click to continue". Tenants couldn't use this wizard to register Google Gemini TTS or OpenAI TTS as a provider, despite the backend `TTSProviderRegistry` already supporting them and the Audio Agents Wizard surfacing them correctly.

**Root cause — drift between three frontend surfaces vs. one backend registry.** `frontend/components/provider-wizard/steps/StepVendorSelect.tsx:44` had a hardcoded `TTS_CLOUD: VendorOption[]` array containing only ElevenLabs, while `frontend/components/audio-wizard/AudioProviderFields.tsx:44-49` (FALLBACK_PROVIDER_CARDS), `frontend/components/audio-wizard/defaults.ts:9` (AudioProvider type union), and `backend/hub/providers/tts_registry.py` all listed 4 providers. The existing wizard-drift guard (Guard 2 in `backend/tests/test_wizard_drift.py`) only checked the `AudioProvider` type union — it never noticed the ProviderWizard's parallel hardcoded list.

**Fix:**
- `frontend/components/provider-wizard/steps/StepVendorSelect.tsx`: added OpenAI TTS and Gemini TTS to `TTS_CLOUD` with copy that explicitly notes the API key is reused from the LLM/Image cards (no need to re-enter). Now tenants see all 3 cloud TTS vendors in step 3 of the wizard.
- `frontend/components/provider-wizard/steps/StepProgress.tsx`: extended the cloud-TTS save branch (previously only matched `vendor === 'elevenlabs'`) to also handle `openai` and `gemini` via the same `POST /api/api-keys` upsert path. The endpoint is idempotent (`create_or_update_api_key`) so re-saving an existing key from the LLM flow is non-destructive — refreshes the encrypted blob and bumps `updated_at`.
- `frontend/components/provider-wizard/steps/StepTestAndModels.tsx`: previously gated Next on `draft.available_models.length > 0`, which broke the TTS path entirely (TTS providers don't expose `available_models` the same way LLMs do). Now bypasses the gate when `modality === 'tts'` and renders a per-vendor info card explaining that voices and TTS models are picked per-agent in the Audio Agents Wizard (`/api/tts-providers/{provider}/models` and `/voices` are the runtime source of truth, not this credential step).

**Drift prevention — Guard 2 expanded to cover ALL TTS-provider surfaces.** The wizard-drift test in `backend/tests/test_wizard_drift.py` now asserts that every backend-registered TTS provider appears in **5 frontend surfaces**, not just 1:
1. `AudioProvider` type union in `defaults.ts` (existing)
2. `FALLBACK_PROVIDER_CARDS` in `AudioProviderFields.tsx` (new)
3. `PROVIDER_COPY` marketing dict in `AudioProviderFields.tsx` (new)
4. `VOICE_AGENT_DEFAULTS` per-provider templates in `defaults.ts` (new)
5. `TTS_CLOUD` + `TTS_LOCAL` in `provider-wizard/StepVendorSelect.tsx` (new — the surface that drifted in this bug)
6. The cloud-TTS save branch condition in `StepProgress.tsx` (new — registered providers minus Kokoro must all appear in the OR-chain, otherwise save silently falls through to the LLM path and 400s)

If any of these 6 surfaces miss a backend-registered provider in the future, the test fails with a precise pointer to which surface and which provider id is missing.

**Studio audit — no additional drift found.** The Studio's quick-create modal (`frontend/components/watcher/studio/StudioAgentSelector.tsx`) for Voice/Hybrid agents already delegates to `openAudioWizard()` (the AudioAgentsWizard with the new model picker), and its LLM picker is fully API-driven via `api.getProviderInstances()`. The "Open full create flow" link routes to the regular Agent Wizard's `StepAudio` (also fixed). No hardcoded TTS provider lists in the Studio surfaces.

**Verified end-to-end (Playwright, 9/9 checks):** Hub → Add Provider → TTS + Cloud now shows all 3 vendors with correct copy; selecting Gemini → Step 4 credentials renders normally; Step 5 unblocks for TTS modality and shows a "Voices & TTS models" info card pointing to the Audio Agents Wizard; Self-hosted shows only Kokoro (TTS_LOCAL unchanged). 0 console errors.

### Feat — Gemini TTS multi-model support + image-generation catalog consolidation (2026-04-22)

**TTS:** Tsushin's Gemini TTS provider previously hardcoded a single model id (`gemini-3.1-flash-tts-preview`). Tenants can now pick between three Gemini TTS preview models per agent — Fast (`gemini-2.5-flash-tts-preview`), Balanced (`gemini-3.1-flash-tts-preview`, default — preserves prior behavior), and Quality (`gemini-2.5-pro-tts-preview`). The selection is exposed in both the Audio Agents Wizard and the regular Agent Wizard's audio step, persists into `AgentSkill.config.model`, and is delivered into the SDK call without changing the existing voice / language / format surface.

**Image generation:** the existing `ImageSkill` already supports `gemini-2.5-flash-image`, `gemini-3.1-flash-image-preview`, and `gemini-3-pro-image-preview` (from earlier in v0.6.0). No code change — this changelog entry consolidates the catalog in docs so tenants can see the full set explicitly.

**Backend:**
- `backend/hub/providers/gemini_tts_provider.py`: replaced module-level `_GEMINI_TTS_MODEL` constant with class-level `SUPPORTED_MODELS = {…}` dict + `DEFAULT_MODEL`. New `_resolve_model()` falls back to default with a warning on unknown ids (rather than silently using a wrong model). `_invoke_gemini()` accepts `model` and threads it into `client.models.generate_content(model=…)`. `synthesize()` reads `request.model`, propagates into the SDK call, `_track_usage(model_name=…)`, and the response `metadata["model"]`. `get_pricing_info()` and `health_check().details` now return the full model list.
- `backend/hub/providers/tts_provider.py`: `TTSRequest` gained `model: Optional[str] = None`. Backward-compatible — Kokoro/OpenAI/ElevenLabs ignore it; only Gemini honors it today.
- `backend/agent/skills/audio_tts_skill.py`: forwards `config.get("model")` into `TTSRequest`. New `"model"` property in `get_config_schema()`. No DB migration — `AgentSkill.config` is JSON.
- `backend/api/routes_tts_providers.py`: new generic endpoint `GET /api/tts-providers/{provider}/models` — returns `[]` for providers without `SUPPORTED_MODELS` (frontend hides the picker uniformly), populated from the provider's `SUPPORTED_MODELS` dict for Gemini. `AgentTTSProviderResponse` and `AgentTTSProviderUpdate` Pydantic models gained `model: Optional[str]`; persisted into `tts_config["model"]` when set.

**Frontend:**
- `frontend/lib/client.ts`: new `TTSModelInfo` type, `AgentTTSConfig.model?` field, `getTTSProviderModels(provider)` API method.
- `frontend/components/audio-wizard/defaults.ts`: new `GEMINI_TTS_MODELS` array and `GEMINI_TTS_DEFAULT_MODEL` constant — used as offline fallback when the live `/models` endpoint is unreachable. Drift-checked by `backend/tests/test_wizard_drift.py` (Guard 10).
- `frontend/components/audio-wizard/AudioProviderFields.tsx`: `AudioVoiceFieldsValue.model?` field. Fetches `getTTSProviderModels(provider)` and reconciles state on provider change. Renders the Model dropdown only when the provider exposes a non-empty model list (uniformly hides for Kokoro / OpenAI / ElevenLabs today; will surface automatically when those providers expose `SUPPORTED_MODELS` in the future).
- `frontend/components/audio-wizard/AudioAgentsWizard.tsx`: `WizardState.model`, defaults to `GEMINI_TTS_DEFAULT_MODEL` when provider preset is Gemini, included in the `audio_tts` skill config payload, displayed in Step 5 review.
- `frontend/lib/agent-wizard/reducer.ts`: `AudioConfig.model?` field.
- `frontend/components/agent-wizard/steps/StepAudio.tsx`: passes `audio.model` to `AudioVoiceFields`.
- `frontend/components/agent-wizard/hooks/useCreateAgentChain.ts`: includes `model` in the `audio_tts` skill config when set.
- `frontend/components/agent-wizard/steps/StepReview.tsx`: shows model id when present.

**Wizards intentionally NOT touched:** the Provider Wizard (`frontend/components/provider-wizard/`) is the credential-and-LLM-discovery surface — TTS model selection happens at the per-agent level, not at the credential level. The single Gemini API key (`ApiKey.service="gemini"`) is shared across LLM + TTS + Image, so adding TTS models doesn't require a new credential surface.

**Tests:**
- `backend/tests/test_gemini_tts_provider.py` (new): unit tests for `_resolve_model` (default fallback, valid passthrough, invalid + warning), `_invoke_gemini` SDK plumb-through (parametrized over all 3 models), `synthesize()` end-to-end (model in metadata + tracker `model_name`), and unknown-model fallback path.
- `backend/tests/test_wizard_drift.py` (Guard 10): asserts `GeminiTTSProvider.SUPPORTED_MODELS` matches frontend `GEMINI_TTS_MODELS` and that `DEFAULT_MODEL` matches `GEMINI_TTS_DEFAULT_MODEL`.

**Known follow-ups (NOT in this commit):**
- Pricing for the 3 Gemini TTS preview models is `$0.00` until Google publishes it. Pro tier is typically 5–10× Flash, so analytics will under-report Pro spend in the meantime — there's a TODO in `get_pricing_info()`.
- The 30 voice presets are documented for the 3.1 model only. Smoke-testing the 2.5 Flash/Pro models against Google's docs may reveal a per-model voice catalog; if so, `SUPPORTED_MODELS` should be extended to carry per-model voice lists and the frontend voice dropdown should refilter on model change.

### Fix — DELETE /api/agents/{id} returned 500 on any agent with linked integrations (BUG-701 — 2026-04-22)

Reported on the `wizard-test-gmail-20260422` agent (id 217) created during the BUG-700 investigation — clicking Delete in the UI returned `Internal Server Error`. Reproducing via API confirmed `HTTP 500 {"detail":"Internal server error"}`. Root cause in [routes_agents.py:1021](backend/api/routes_agents.py:1021): `db.delete(agent); db.commit()` runs without cleaning up child rows. Eight tables have `FK(agent.id)` with `delete_rule = NO ACTION` (the default — `agent_skill_integration`, `agent_project_access`, `message_queue`, `sentinel_agent_config`, `sentinel_exception`, `shell_command`, `user_agent_session`, `user_project_session`) — any row in any of them raises `ForeignKeyViolation` → FastAPI converts to 500. In agent 217's case, the blocker was the single `agent_skill_integration` row the Gmail wizard inserted after assigning the Gmail integration to the test agent. Additionally, **seventeen more tables** reference `agent_id` without any FK constraint at all (`agent_skill`, `agent_knowledge`, `agent_run`, `memory`, `conversation_thread`, `conversation_logs`, `semantic_knowledge`, `token_usage`, `playground_document`, etc.), so those rows would become silent orphans if we only deleted the agent.

**Fix:** `delete_agent` now cascade-cleans all child rows inside the same transaction before deleting the agent. Owned-by-agent tables (operational state, sessions, queues, per-agent config — 19 tables) are `DELETE`d; audit/historical tables with nullable `agent_id` (`sentinel_exception`, `sentinel_analysis_log`, `shell_command.executed_by_agent_id`, `token_usage`) are `UPDATE ... SET agent_id = NULL` to preserve past activity records; `project.agent_id` and `flow_node.agent_id` are set to NULL so projects/flows aren't destroyed when the agent is unbound. Five tables with `CASCADE` FKs (`agent_communication_message`, `agent_communication_permission`, `agent_communication_session`, `agent_custom_skill`, `sentinel_profile_assignment`) continue to be handled by Postgres automatically. If anything still raises `IntegrityError` (meaning a future schema change added a new referencing table), the transaction rolls back and the user gets `HTTP 409` with a specific error message pointing to the agent ID instead of a generic 500.

Verified E2E: `DELETE /api/agents/217` now returns `HTTP 204`. Pre-fix, agent 217 had 3 `agent_skill` rows + 1 `agent_skill_integration` row; post-fix, both counts are zero and the agent is gone. Sanity check across the instance: `agent` count moved 10 → 9; `agent_skill` count moved exactly 173 → 170 (matching the 3 skills that belonged to 217); `agent_skill_integration` moved 11 → 10 (matching the 1 Gmail row). No collateral damage.

**Related follow-up (NOT in this commit):** the FK constraints themselves should be migrated to `CASCADE` (owned-by-agent) or `SET NULL` (audit) as a schema-level fix so application-layer cleanup becomes belt-and-suspenders instead of the sole defense. Also, the 17 `agent_id` columns that have no FK at all are a silent data-integrity gap — they should gain proper FK constraints. Both items are tracked as v0.7.0 architectural hygiene in `.private/ROADMAP.md`.

### Feat — Option X: second LLM reasoning call for skill-tool results (2026-04-22)

**User symptom resolved:** on agent `movl` after listing emails, follow-up questions like "qual desses é o mais importante?" now return a reasoned analysis (e.g., "The most important is Maria Júlia's request from the accounting team — formal PDF statement request; Marcos's reply (item 1) is related as it forwards those statements; items 4 and 5 are automated delivery notifications") instead of re-dumping the same raw email list. Before this change, the LLM would correctly decide to call the Gmail tool (tool-mode was active after the earlier BUG-699 cleanup), but the tool's rendered output would **replace** the LLM's response via a single-shot text substitution at `backend/agent/agent_service.py:1071`, so the LLM never got a chance to compose a reasoned answer over the tool result. The raw `📧 N emails: ...` listing became the final reply, regardless of what the user actually asked.

**Root cause:** Tsushin's tool-calling pipeline was never a true Anthropic-style `tool_use → tool_result → final_response` loop. It was a one-shot: (1) LLM emits a tool_call text block; (2) `agent_service` parses and executes the tool; (3) the tool's rendered `output` string replaces the entire `ai_response`. There was no second LLM call to let the model reason over the tool result. `SkillResult.metadata.skip_ai` (which already encoded the right intent: `skip_ai=False` means "LLM should reason", `skip_ai=True` means "raw output is the final answer") was read only in the router's legacy keyword-dispatch path, not in the agent_service tool-mode path.

**Fix (Option X):** add a second LLM call in `backend/agent/agent_service.py` after text-returning skill tools execute, passing the original user message + the raw tool output + the agent's existing system prompt, so the model composes a natural-language final reply. The second call is gated on `SkillResult.metadata.skip_ai == False`, which encodes the correct intent per skill:

- **Bucket A (reasoning fires):** `gmail` list/search, `flows` list, `flight_search`, `web_search`, `agent_communication.ask`, `agent_communication.list_agents`, `okg_term_memory.recall`, `browser_automation` when `skip_ai=False` per action. Data-fetch operations where the LLM should synthesize an answer.
- **Bucket B/C-special (reasoning bypassed):** `generate_image` (media artifact is the reply), `agent_communication.delegate` (`skip_ai=True` — target's answer passes through verbatim by design), shell commands (`is_shell_tool` branch, structurally separate), sandboxed tools (`run_shell_command`, `/tool nmap`, `/tool dig`, etc. — raw technical output is expected).
- **Bucket C (write confirmations):** `flows.create/update/delete`, `agent_switcher.set`, `automation.run/status` — all keep `skip_ai=True`, raw confirmation string is fine.

**Changes:**

- `backend/agent/agent_service.py`:
  - Range 1013-1074 (the skill-tool execution block) now always passes `return_full_result=True` so we have access to `SkillResult.metadata` for every skill (previously only `generate_image` did this). Media paths handling is unchanged.
  - New `_should_reason` local bool, set True only when `skill_result.success and not needs_media_output and not metadata.get('skip_ai', False)`. Defaults False (shell branch + legacy string-return fallbacks never reason).
  - Range 1161-1186: after `ai_response = tool_execution_result`, invoke the new `_reason_over_tool_result` helper when `_should_reason` is True. Its return replaces `ai_response`; on any failure (exception, empty answer, AI error flag) the raw tool output is retained so the reply pipeline is never blocked.
  - New private method `_reason_over_tool_result` (between `_prefer_tool_result_when_response_empty` and `process_message`). Truncates tool output to 4000 chars, builds a reasoning user-message with explicit "do not output tool call blocks" guard, calls `self.ai_client.generate()` with `operation_type="tool_reasoning"` (tracked separately in token analytics), strips reasoning tags / internal context / sensitive content from the returned answer (same sanitizers applied to the first-call output), returns `None` on any failure.
  - Added `Any` to `typing` imports.

- `backend/agent/skills/gmail_skill.py` (lines 428, 511): flipped `skip_ai: True` → `skip_ai: False` on the success paths of `_handle_list_emails` and `_handle_search_emails`. Empty-result and error paths keep `skip_ai: True` (those strings are self-explanatory). This aligns skills-as-tools semantics: list/search is "data for the LLM to reason over", not "final answer dump".

- `backend/agent/skills/flows_skill.py` (line 1990): flipped `skip_ai: True` → `skip_ai: False` on the `_execute_tool_list` non-empty success path. Create/update/delete confirmations keep `skip_ai: True`.

- `backend/agent/skills/flight_search_skill.py`: no change required — success path already had no `skip_ai` key, so `metadata.get('skip_ai', False)` defaults correctly to `False`.

**Token/latency cost:** +1 LLM call per tool-invoking turn for bucket-A skills. Typical Gmail list (5 emails, ~1.5 KB tool output) adds ~1500 input + ~200 output tokens at ~$0.0001 per turn on Gemini Flash. Latency +1-3s per turn. No per-agent feature flag — the per-skill `skip_ai` flag already provides the right granularity; agents that want raw dumps can flip `skip_ai` on specific handlers.

**Verified E2E:**
- API v1 `POST /api/v1/agents/41/chat` (agent `movl`): Turn 1 `{"message": "quais meus ultimos emails?"}` → reasoned summary naming each sender + content hint, not raw markdown list. Turn 2 `{"message": "qual desses emails eh o mais importante?", "thread_id": 282}` → LLM identifies "Maria Júlia (item 3) – EXTRATOS BANCARIOS" as most important, explains the accounting context, groups the related emails (items 1, 2), dismisses the automated delivery updates (items 4, 5). `operation=tool_reasoning` visible in `AIClient.generate()` logs.
- WhatsApp channel via tester MCP (+5527999616279 → +5527988290533, `/invoke movl`): same two-turn flow produced the same reasoned behavior end-to-end on the user's actual channel. Turn 2 response: "Vini, o e-mail mais importante parece ser o da **Maria Júlia**, do setor contábil. Ela está solicitando os extratos bancários em PDF, o que geralmente é uma tarefa prioritária..."
- A2A regression: `ask movl qual eh seu ultimo email recebido` to agent `Tsushin` → Tsushin delegates via `agent_communication.ask`, movl replies, Tsushin composes a reasoned final answer for the user. Deep reasoning chain works.
- Bucket-E regression: `/tool dig lookup domain=example.com` on agent `Tsushin` → raw dig output with execution time box preserved, `tool_used: custom:dig`, no `tool_reasoning` call (sandboxed branch structurally separate).
- Bucket-A skills with legitimate `skip_ai=True` (e.g. write confirmations) still bypass reasoning.

**Out of scope — reserved for v0.7.0:**

Even with Option X, a follow-up question that still triggers a new tool call (e.g., the LLM re-calling `gmail_operation` in turn 2 because `conversation_history` only persists the rendered text, not the structured `emails[]` metadata) incurs the fetch again. The full fix — per-skill `auto_inject_results` toggle on `AgentSkillConfig` that persists `tool_result` structured data in `conversation_history` and re-injects it into the LLM prompt on subsequent turns, plus a referential-pronoun guard to suppress redundant tool dispatches — is scheduled for v0.7.0 under "Skill Tool-Result Reasoning & Cross-Turn Context Injection" in `.private/ROADMAP.md`. Option X closes the single-turn UX gap; v0.7.0 closes the cross-turn one.

### Fix — Gmail/Flight/Image/Web-Search skills silently ran in legacy keyword mode despite being declared tool-only (2026-04-22)

Commit `b1b1bb9` (2026-03-29) deprecated legacy keyword triggering by flipping the class-level `execution_mode` attribute from `"hybrid"` to `"tool"` on 10 skills. The intent was that the LLM would be the only one deciding when to call these skills, via the MCP tool schema. However, for four of those skills (`gmail`, `flight_search`, `image`, `web_search`) the commit left the stale value `"hybrid"` inside `get_default_config()` (and inside the UI schema default in `get_config_schema()`). At runtime, `config.get('execution_mode', self.execution_mode)` returns the persisted value first — so every new agent whose skill row was seeded from that default ended up with `config.execution_mode == "hybrid"` stored in the DB, silently re-activating the keyword-routing path the commit was supposed to delete.

**User-visible symptom (reproduced on agent `movl`):** mentioning "email" to the Gmail-enabled agent caused the skill to fire in legacy mode, which short-circuits the LLM via `skip_ai=True` and dumps a hardcoded 10-email list. Follow-up reasoning ("qual desses é mais importante?") never reached the LLM because the keyword "email" re-triggered the skill. The volume-10 looked hardcoded because `_handle_list_emails` reads `config.default_max_results` (hardcoded default: 10) and `_build_email_query` extracts no count from the message — every legacy-mode invocation ends up returning the same 10.

**Fix:**
- `backend/agent/skills/gmail_skill.py`, `backend/agent/skills/flight_search_skill.py`, `backend/agent/skills/image_skill.py`, `backend/agent/skills/search_skill.py` — flipped `execution_mode` from `"hybrid"` to `"tool"` in both `get_default_config()` and the UI schema `default`. Class-level `execution_mode = "tool"` was already correct from `b1b1bb9`; these changes make the default config and the UI form default consistent with it.
- `frontend/components/integrations/GmailSetupWizard.tsx` (line 200) — the "Link Gmail to agents" wizard now sends `{ is_enabled: true, config: {} }` explicitly instead of relying on backend Pydantic to populate `config`. Cosmetic / defense-in-depth — Pydantic `default_factory=dict` already compensates, but now the frontend→backend contract is explicit and won't regress silently if the default is ever tightened.
- `backend/alembic/versions/0044_fix_skill_execution_mode_hybrid_leftover.py` — new migration flips `config.execution_mode` from `"hybrid"` to `"tool"` on existing rows for the four affected skill types (`gmail`, `flight_search`, `image`, `web_search`). Rows where `config` is `NULL` or `{}` self-heal via the runtime fallback once the code fix is deployed; this migration handles the rows that already have `"hybrid"` explicitly persisted. Idempotent (filtered on current value), Postgres+SQLite safe.

**Verified end-to-end:** after the rebuild+migration, agent `movl` (id 41) responded to `POST /api/v1/agents/41/chat` with `{"message": "quais meus ultimos emails?"}` using `tool_used: "skill:gmail_operation"` (tool mode, previously `skip_ai` bypass) and returned 5 emails (LLM chose via max_results, previously hardcoded 10). DB verification: all four skill types now have `execution_mode="tool"` (or NULL/empty which resolve to `"tool"` via the class-attr fallback) across all 13 affected rows in the test tenant.

**Out of scope — tracked for v0.7.0:** even with tool mode active, asking a follow-up question ("qual desses é mais importante?") still causes the LLM to re-invoke the Gmail tool instead of reasoning over the emails from the prior turn. Root cause: Tsushin's tool path is single-shot text substitution (`agent_service.py:1071` swaps the tool result into the response string) — there is no native `tool_use → tool_result → final_response` agentic loop, and `conversation_history` only persists the rendered string, not the structured `emails[]` metadata. The fix is the proposed framework-level `auto_inject_results` toggle on `AgentSkillConfig` planned for v0.7.0 (see plan `pq-isso-acontece-ele-zesty-puffin.md`). This changelog entry covers only the leftover-architecture cleanup.

### Fix — Watcher "Semantic Search Disabled" badge was reading a vestigial global flag (2026-04-22)

Watcher dashboard's System Performance card always showed "Semantic Search Disabled" even when every agent had per-agent semantic search turned on. The `/api/stats/memory` endpoint was reading `Config.enable_semantic_search`, a legacy global singleton that defaults to `False` and is not referenced anywhere else in the backend (no runtime path actually gates on it). Meanwhile, the real behavior is driven per-agent by `Agent.enable_semantic_search`, which defaults to `True`.

**Fix:**
- `backend/api/routes.py` (`get_memory_stats`) — `semantic_search_enabled` is now derived by aggregating the per-agent flag over the in-scope agents (all agents for global admins, tenant-scoped otherwise). The response also now includes `agents_with_semantic_search` and `total_agents`. The vector-store embedding aggregation loop now skips agents that have semantic search disabled rather than indiscriminately counting every agent's ChromaDB collection.
- `frontend/lib/client.ts`, `frontend/components/watcher/DashboardTab.tsx`, `frontend/components/watcher/dashboard/SystemPerformanceSection.tsx` — `MemoryStats` extended with the new fields. The badge now has four states with correct styling: "Semantic Search Active (M/M agents)" (green) when all in-scope agents have it on, "Semantic Search Partial (N/M agents)" (warning) when only some do, "Semantic Search Disabled (0/M agents)" (muted) when none do, and "Semantic Search — no agents" (muted) when the tenant has no agents yet.

**Verified end-to-end:** backend `/api/stats/memory` now returns `semantic_search_enabled: true, agents_with_semantic_search: 10, total_agents: 10` for the test tenant (previously `false`). Frontend UI renders the green "Semantic Search Active (10/10 agents)" badge with `bg-tsushin-success/10 border border-tsushin-success/30` styling. The legacy `Config.enable_semantic_search` column remains in the schema but is now orphaned — a later commit can drop it.

### QA - VM fresh-install UI-first regression campaign (2026-04-22)

Completed fresh-install regression run `20260422-081634` against a disposable Ubuntu 24.04 aarch64 Parallels VM from a clean `origin/develop` clone. The stock `python3 install.py --defaults` pass completed but revalidated the already-open IP-literal self-signed TLS failure (`BUG-688`). The interactive installer pass using `10.211.55.5.sslip.io` completed with self-signed HTTPS, `/setup` was completed in Playwright, and final `/api/health` plus `/api/readiness` remained 200 before cleanup.

Coverage included hosted providers (OpenAI, Anthropic, Gemini, Vertex AI), tool APIs (Brave, Tavily, SerpAPI/Google Flights), auto-provisioned Qdrant vector store, Ollama provisioning path, memory/facts/KB, Sentinel/MemGuard detect and block probes, Playground UI/API chat, slash commands, A2A permission/session APIs, custom instruction/script skills, MCP server linkage, sandboxed tools, Shell Command Center, webhook channel delivery, graph activity/glow instrumentation, programmatic/agentic flows, API client OAuth token exchange, live OpenAPI download, generated Python client smoke, and a 21-page Playwright UI sweep across Watcher, Hub, Studio, Playground, Flows, Agent Studio, and settings.

Pass/fail summary: sslip self-signed install path PASS; setup/browser login PASS; API health/readiness PASS; provider matrix PASS after replacing the stale Anthropic model with a current Claude 4.x model; API follow-ups PASS; generated client smoke PASS; graph showed Playground/Webhook/KB activity and no WhatsApp graph node when WhatsApp was unconfigured; Playground UI sent a real browser message and received `UI_OK`. New bugs opened: 5 total — High 2 (`BUG-694`, `BUG-695`), Medium 1 (`BUG-697`), Low 2 (`BUG-696`, `BUG-698`). Duplicates/revalidations not counted as new: `BUG-688`, the `BUG-308` stale-model family, and the `BUG-542` Gemini multi-part extraction log symptom.

### Fix — A2A `context` leak between agents (BUG-693, partial — 2026-04-22)

User investigating Google Calendar isolation found that when Tsushin asks movl for events via `agent_communication.ask`, then asks archsec the same question in the same thread, archsec "answered" with movl's events — even though archsec is bound to a different Calendar integration. Root cause is NOT a calendar/tenant leak (DB bindings and `SchedulerProviderFactory` are correctly scoped — verified by direct `GoogleCalendarProvider.list_events` calls). The leak lives in the A2A request path: the calling LLM populates a free-form `context` string that the target agent is shown as `"Additional Context: {context}"` with no untrust marker. Tsushin's LLM hoisted movl's tool output into that field; archsec's LLM paraphrased it verbatim, especially because the default `allow_target_skills=False` disables the target's own tools.

**Defense-in-depth shipped in this commit:**
- `backend/agent/skills/agent_communication_skill.py` — the MCP schema for `context` now explicitly tells the calling LLM not to paste tool output, emails, calendar events, or account-scoped data into the field.
- `backend/services/agent_communication_service.py` (`_invoke_target_agent` prompt assembly) — source-supplied `context` is now framed as an UNTRUSTED hint with explicit instructions to the target agent: prefer own memory/tools, do not repeat specifics (names, dates, numbers, quoted content) unless independently verified, and when skills are disabled, say so instead of paraphrasing the hint as if verified.

**Verified end-to-end — two rounds:**
1. **Adversarial injection:** re-ran the same scenario with a deliberately hand-crafted tainted context. Tsushin's request to archsec carried `"Known events include Apr 22 Dr Eliud at 09:30; Apr 23 Dr Grossi at 09:40; Apr 24 LATAM LA 3243; Apr 27 LATAM LA 3644"` in `context_transferred`. Archsec ignored the untrusted hint, called its own `manage_reminders` tool, and returned only the two real `mv@archsec.io` events (`xASM`, `Sync Kees Mv`) — none of the tainted context appeared in the response.
2. **Natural round-trip (both calendars in one Tsushin thread):** user asked Tsushin for events from movl then from archsec back-to-back. Movl returned its 7 real `movl2007@gmail.com` events; archsec returned only its 2 real `mv@archsec.io` events. Tsushin's LLM this time followed the new schema description and sent only a benign `"User wants a summary of their weekly events."` as archsec's `context` — no event specifics hoisted from movl's prior turn. Both defenses (caller-side schema nudge and callee-side untrust marker) worked. Evidence in `agent_communication_message.id IN (85,86,87,88)`.

**Structural follow-up (not in this commit):** ideally drop the free-form `context` parameter entirely and let target agents fetch their own data via their own tools; or restrict `context` to a typed schema that cannot be misread as authoritative data. A regression test (two calendar-bound agents + verify no cross-event leak) should be added to `backend/tests/`. Tracked in BUG-693.

### Fix — `scheduler` skill registry miss broke Google Calendar + flow-template execution (2026-04-21)

User-reported toast after connecting Google Calendar: `Skill type 'scheduler' is not registered. Available: ['…', 'flows', '…']`. Root cause: v0.6.0 replaced `SchedulerSkill` with `FlowsSkill` and registered it under `skill_type='flows'`, but `'scheduler'` remained the canonical abstraction name used everywhere else — integration wizards (`GoogleCalendarSetupWizard`, `GmailSetupWizard`), seeded flow templates (Weekly Calendar Summary), the Flows page dropdown, and any DB rows created via those paths. At flow-execution time, `flow_engine.py` looked up `'scheduler'` in the skill registry, missed, and raised.

Scheduler is the skill abstraction; Flows, Google Calendar, and Asana are all providers of it — Google Calendar has nothing to do with "flows" beyond sharing the same provider-aware skill class. The registry should expose the abstraction name, not one of its provider names.

**Fix:**
- `backend/agent/skills/skill_manager.py` — `FlowsSkill` is now registered under both `"flows"` (legacy alias, preserved for DB rows that already use it) and `"scheduler"` (canonical abstraction, used by the wizards and templates). Both keys resolve to the same provider-aware implementation.
- `backend/api/routes_skill_integrations.py` — updated the "unknown skill type" error message to advertise the full set (`scheduler, flows, email, gmail, flight_search, web_search`).
- `backend/dev_tests/test_week5_skills.py` — fixed stale assertions that expected the removed `scheduler_query` key.

Not changed (intentional): `flow_template_seeding.py:260` still uses `skill_type="scheduler"` — that value is semantically correct (the Weekly Calendar Summary template targets the Scheduler abstraction, not the Flows provider). The registry alias is what makes it executable again.

**Verified:** registry now exposes both keys resolving to `FlowsSkill`; movl agent received a calendar query in the Playground without the registry error (the subsequent `manage_reminders` tool-enablement issue is an unrelated MCP tool gate, not a scheduler registry problem); backend logs show zero `Skill type 'scheduler' is not registered` entries after the fix.

**Wizard fix + DB migration (follow-up commit):** `GoogleCalendarSetupWizard` was writing `skill_type='scheduler'` while `AgentSkillsManager` writes `'flows'`. The registry alias made execution tolerate either, but downstream lookups (`skill_manager._get_skill_record`, `SchedulerProviderFactory.get_provider_for_agent`, ~40 other sites) query by the canonical value `'flows'` and missed the wizard-created rows, so tool calls to `manage_reminders` returned "Tool is not enabled for this agent" even though the skill was technically registered and enabled. Fix: wizard now writes `'flows'`, and existing `AgentSkill` / `AgentSkillIntegration` rows with `skill_type='scheduler'` were migrated to `'flows'`. Verified end-to-end on agent "movl": `List my calendar events for the next 7 days` returned 7 real Google Calendar events via the `google_calendar` provider.

### Fix — OAuth/email/frontend HTTP/HTTPS landmines + SSL-overlay auto-load (2026-04-21)

A user-reported Google Calendar OAuth regression (`redirect_uri=https://localhost/api/hub/google/oauth/callback` rejected) surfaced a broader set of HTTP/HTTPS inconsistencies. Root cause had two layers:

1. Several code paths hard-coded `http://localhost:…` defaults and ignored `TSN_FRONTEND_URL` / `TSN_BACKEND_URL`. Any integration whose dedicated env var wasn't explicitly set (Asana is the obvious one — `ASANA_REDIRECT_URI` is not in `.env`) silently fell back to HTTP even when the operator had set the public URLs to HTTPS.
2. `docker-compose` commands that omitted `docker-compose.ssl.yml` recreated the Caddy `proxy` against the base (HTTP-only) Caddyfile, so `https://localhost` and port 443 publishing silently disappeared after any rebuild. This was the "UI got downgraded from HTTPS to HTTP during a test" regression the user has hit repeatedly.

**Code fixes (derive from `settings.FRONTEND_URL` / `settings.BACKEND_URL`):**
- `backend/api/routes_hub.py`, `backend/api/v1/routes_hub.py` — Asana OAuth redirect URI now derives from `settings.FRONTEND_URL` when `ASANA_REDIRECT_URI` is unset.
- `backend/agent/skills/scheduler/asana_provider.py` — Asana scheduler provider token-refresh redirect_uri now matches the OAuth auth flow (`{FRONTEND_URL}/hub/asana/callback`); previously it used a completely different backend path (`/api/hub/asana/oauth/callback`), which Asana rejects with `invalid_grant` on refresh.
- `backend/services/email_service.py` — `base_url` now reads `settings.FRONTEND_URL` (handles both `TSN_FRONTEND_URL` and the legacy `FRONTEND_URL` names) instead of `os.getenv("FRONTEND_URL")`, which only saw the legacy name and fell back to HTTP. Fixes invitation and password-reset email links on HTTPS deployments.
- `backend/services/public_ingress_resolver.py` — last-resort invitation base-URL fallback now uses `settings.FRONTEND_URL` instead of a bare `os.getenv("FRONTEND_URL")`.
- `backend/agent/skills/scheduler_skill.py` — bot reply text linking to `/flows` now uses `settings.FRONTEND_URL` instead of a hard-coded `http://localhost:3030/flows`.

**Compose + env:**
- `docker-compose.yml` — `TSN_GOOGLE_OAUTH_REDIRECT_URI` and `ASANA_REDIRECT_URI` defaults now inherit from `${TSN_BACKEND_URL}` / `${TSN_FRONTEND_URL}` via nested `${VAR:-${VAR:-…}}` substitution. Setting the two public URLs in `.env` is now sufficient to flip the whole stack to HTTPS.
- `.env` — pinned `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml` so every `docker-compose` call automatically applies the SSL overlay. Without this, any recreate of the `proxy` service drops the TLS mount + port publishing and silently takes `https://localhost` offline.

**Doc + playbook guardrails:**
- `CLAUDE.md` — added an "SSL Overlay (CRITICAL — do NOT downgrade the proxy)" section under the Safe Container Rebuild rules, and replaced the old `docker-compose up -d --build --no-cache` incantation (which isn't a valid flag combination on current compose) with `docker-compose build --no-cache` + `docker-compose up -d`.
- `.claude/agents/qa-tester.md`, `methodology/commands/fire_full_regression.md`, `methodology/commands/fire_regression.md`, `methodology/commands/fire_remediation.md` — prepended a "Do NOT flip the instance's HTTP/HTTPS mode" block that tells the runner to source `.env`, export `UI_URL` / `API_URL`, and substitute those everywhere the doc says `http://localhost:3030` / `http://localhost:8081`. The goal is to stop agents from "fixing" hard-coded URLs in the test scripts by editing the operator's `.env`.

Verified post-fix on the live instance: `https://localhost/api/health`, login, `/api/v1/oauth/token`, `/api/v1/agents/1/chat` (agent returned `REGRESSION_OK`), and the frontend root redirect to `/auth/login` all return 200 over HTTPS; `ASANA_REDIRECT_URI` inside the container resolves to `https://localhost/hub/asana/callback`; `email_service.base_url` resolves to `https://localhost`; WhatsApp agent container reconnected cleanly; no new backend errors beyond the pre-existing Qdrant fallback warning.

### QA - UI-first partial regression campaign (2026-04-22)

Partial run of `.private/TEST_PLAYBOOK_UI_FIRST_REGRESSION.md` (run ID `20260421b`) against the existing local Mac stack (E2 path). Campaign was interrupted by a user-reported login issue (root cause: Chrome HSTS redirect for `localhost` → `https://localhost` which is not published — de-duped against BUG-685). Login confirmed working at `http://127.0.0.1:3030`. Completed phases: Preflight (all healthy), Playground API/WS (PASS), Playground + Mini browser (PASS with 2 bugs), Flows API/schema (PASS), Sentinel programmatic tests (62/62 PASS, LLM gate PASS), Audit 5 local instance (PASS). Phases C2, B2, D1–D4 not reached. All QA fixtures (2 agents, 2 contacts, 1 vector store, 2 sentinel profiles, 2 threads) were deleted and the stack was fully reverted to pre-run state.

Bug count from this campaign: 3 new open bugs — Medium 3 (BUG-690: onboarding modal buttons unresponsive, BUG-691: Playground wrong thread after refresh, BUG-692: Mini expand wrong thread handoff).

### QA - UI-first regression rerun aborted on backend health timeout (2026-04-21)

Started an autonomous subagent-first rerun of `.private/TEST_PLAYBOOK_UI_FIRST_REGRESSION.md` with run id `20260421-204933`. The run selected the existing-local-instance Audit 5 track and initially passed direct backend HTTP health/readiness, compose health, disk, setup-status, and MCP log checks. E2 local-instance non-browser validation passed and de-duped the local HTTPS refusal to existing `BUG-685`.

The campaign was then aborted per the playbook hard-stop rule after parallel A1/B1/C1 activity caused or exposed backend unresponsiveness: direct `/api/health` and `/api/readiness` timed out with HTTP `000`, and `docker compose ps` showed backend and proxy unhealthy. C1's preserved Sentinel benchmark log shows repeated Gemini/Sentinel unified-analysis timeouts before the abort. New tracker entry: `BUG-689` (Critical), covering backend health/readiness timeout during the Sentinel benchmark run. No product code was changed and no restart/rebuild was used to mask the failure.

### QA - UI-first full regression campaign completed (2026-04-21)

Ran the full UI-first regression campaign from `.private/TEST_PLAYBOOK_UI_FIRST_REGRESSION.md` after the required health recovery gate, including local A/B/C/D audit tracks, isolated VM fresh-install validation, cleanup, and final health checks.

- Playground API/WebSocket, Playground UI, Mini, and Graph tracks passed.
- Flows API/schema checks passed; Flows UI builder coverage opened one Medium bug because browser create attempts reached configuration screens but did not complete flow creation.
- Sentinel preflight, fixture setup, Gemini Flash LLM gate, and API matrix passed; Sentinel UI opened one Medium bug for the Test Analysis result being hidden until the User Guide state was dismissed.
- Tenant admin, global admin, and SSO UI surfaces loaded cleanly; destructive multi-tenant stress/provisioning writes were skipped where the playbook required safety.
- VM fresh-install HTTP pass succeeded; self-signed IP HTTPS pass opened one High installer/TLS bug.
- Local HTTPS proxy coverage opened one Medium bug because `https://localhost` was unavailable while the proxy container was healthy.
- Final cleanup verification found no leftover run-owned containers, VM workdirs, or active local QA resources; final local health and readiness were green.

Bug count from this campaign: 4 new open bugs - High 1, Medium 3.

### Hub Productivity + Communication rework — guided wizards replace fixed cards (2026-04-21)

User follow-up to the v0.7 Hub rework: apply the same judgement used for AI Providers and Tool APIs (single guided "+ Add …" launcher, no placeholder cards for unused services) to the Productivity and Communication tabs. Both tabs previously leaned on fixed/placeholder cards that took screen space for services the tenant had not chosen to use; they now collapse to configured-instance cards only, with a single wizard launcher per tab.

**Productivity tab (`frontend/app/hub/page.tsx`)**

- Removed the fixed **Google Integration** status card, the **Asana — Not Connected** placeholder card, and the **Google Calendar — Not Connected** placeholder card.
- Added a single top-right **"+ Add Productivity Integration"** launcher that opens the new `ProductivityWizard`. The wizard runs Category (calendar / email / tasks / knowledge base) → Service (Google Calendar / Gmail / Asana / …), then hands off to the existing per-service setup flow (`GmailSetupWizard`, `GoogleCalendarSetupWizard`, Asana OAuth redirect) — dispatcher pattern, no rewrite of deep OAuth flows.
- Google OAuth configuration state is now a compact inline badge instead of a full card. Empty tab state shows one centred "No productivity integrations yet" CTA; with at least one configured service, only the matching instance cards render.
- Gmail cards are intentionally surfaced only under **Communication** (email-as-channel) to avoid the duplicate placement the v0.6 layout had.

**Communication tab (`frontend/app/hub/page.tsx`)**

- Consolidated six scattered CTAs (top-level `+ Create WhatsApp Instance`; per-section `+ Create Bot` / `+ Connect Workspace` / `+ Connect Bot` / `+ New Webhook` / `+ Add Gmail Account`; plus duplicate empty-state body buttons) into one top-level **"+ Add Channel"** launcher that opens the new `ChannelsWizard`.
- Per-channel sections (WhatsApp, Telegram, Slack, Discord, Webhooks, Gmail Email Integration) are hidden when the tenant has zero instances of that channel — so an unused Telegram / Slack / Discord section no longer occupies a full empty-state card. Section-level `+ Create …` buttons are retained when at least one instance exists, so a second instance can be added without round-tripping through the wizard.
- The dashed **"Add Another Gmail"** placeholder is gone — adding a Gmail account now flows through `+ Add Channel` → Gmail, or `+ Add Productivity Integration` → Email → Gmail.
- The Public-Base-URL advanced card renders only when a Slack / Discord / Webhook integration actually exists (the setting is irrelevant otherwise).
- Unified empty-state card shown only when zero channels are configured anywhere on the tab.

**New wizards**

- `frontend/components/integrations/ProductivityWizard.tsx` — two-step picker (Category → Service), fetches `/api/hub/productivity-services`, falls back to a static array on offline/degraded boot. Dispatches to existing sub-wizards via a caller-provided `onServiceSelected` callback so modals don't stack.
- `frontend/components/integrations/ChannelsWizard.tsx` — one-step picker (Channel), fetches `/api/channels`, merges per-tenant `tenant_has_configured` badges into the fallback. Dispatches to `WhatsAppSetupWizard` / `TelegramBotModal` / `SlackSetupWizard` / `DiscordSetupWizard` / `WebhookSetupModal` / `GmailSetupWizard`. Includes an inbound-email `gmail` entry the backend catalog doesn't currently expose; Guard 9 (below) allowlists that extra.

**Backend catalog**

- New `backend/hub/productivity_catalog.py` — `ProductivityServiceInfo` dataclass + `PRODUCTIVITY_CATALOG` array (google_calendar, gmail, asana). Pattern mirrors `backend/channels/catalog.py`.
- New `GET /api/hub/productivity-services` endpoint in `backend/api/routes_hub_providers.py` — returns the catalog annotated with `tenant_has_configured` (per integration type) and `tenant_has_oauth_credentials` (per OAuth provider; surfaced to the wizard so successive Google-backed picks don't re-ask for the same secret).
- `frontend/lib/client.ts` — `ProductivityServiceInfo` interface + `api.getProductivityServices()` method.

**Drift prevention (item 5)**

- `backend/tests/test_wizard_drift.py` extended with **Guard 8** (backend `PRODUCTIVITY_CATALOG` ⇄ `ProductivityWizard` `FALLBACK_SERVICES`) and **Guard 9** (backend `CHANNEL_CATALOG` actionable entries ⇄ `ChannelsWizard` `FALLBACK_CHANNELS`, with a narrow `{gmail}` allowlist for wizard-only extras). Adding a new productivity service or channel to the backend without updating the wizard fallback now fails CI.
- New `frontend/lib/wizard-registry.ts` — a pure-metadata registry that enumerates every wizard + the backend catalog each one depends on. Not imported by the wizards themselves (keeps offline mode robust), but documents the coupling in one place so future wizard additions pick up the drift guard.

**Before/after cosmetic baseline (captured 2026-04-21 via Playwright)**

- Productivity before: 0 configured cards, 3 fixed/placeholder cards (Google Integration, Asana, Google Calendar).
- Productivity after: 0 configured cards → single centred empty-state CTA; ≥1 configured → only configured cards + inline OAuth badge.
- Communication before: 5 configured cards, 1 dashed "Add Another Gmail" placeholder, 3 empty-state shells (Telegram/Slack/Discord), 6 scattered CTAs.
- Communication after: configured-only sections, zero placeholders, 1 top-level "+ Add Channel" (plus per-section "+" only when ≥1 instance exists).

Evidence under `output/playwright/hub-wizard-v0.7/pre-impl/` (pre-impl screenshots).

### Fourth Sweep — Zero open bugs (2026-04-21)

User wanted no open bugs. Closed the final 2 architectural items with fixes + live verification.

- **BUG-682 (High) — Docker-aware port allocation (`backend/services/vector_store_container_manager.py`).** `_allocate_port` now enumerates every host port published by any running container via `client.containers.list()` + `NetworkSettings.Ports`, in addition to the in-app DB check and the socket-bind probe. Side-by-side Tsushin stacks on the same host no longer each allocate the same port from their isolated DBs and collide on `docker run`. Live: on this stack, enumerator returns 16 published ports including 6300; `_allocate_port()` correctly returns 6302.
- **BUG-684 (Critical) — Per-integration health-check timeout on Hub list route (`backend/api/routes_hub.py`).** Every inline `check_health` call in `GET /api/hub/integrations?refresh_health=true` (Asana, Calendar, Gmail) is now wrapped in `asyncio.wait_for(..., timeout=8.0)`. Failing external APIs can no longer hold the FastAPI `get_db` session for 30s+ per integration. Combined with the earlier 10s httpx timeout in Gmail/Calendar services, the effective QueuePool saturation window is 2-3x larger than before. Live: refresh_health completes in 0.76s vs the original 30s-per-failing-integration pattern that triggered the original deadlock.

**Validation:** `output/playwright/full-regression-20260421/preflight/final-regression-sweep4.txt` — **PASS 34 / FAIL 0**. Zero open bugs. Zero open PRs.

### Third Sweep — UI-first validation of remaining bugs (2026-04-21)

User asked to validate each remaining open bug against the live stack, fix real ones, and run UI-first browser regression.

- **BUG-540 (Medium) — OKG Qdrant auto-connect (`backend/agent/skills/okg_term_memory_skill.py`).** `_get_service` now falls back to the tenant's default (or any healthy active) `VectorStoreInstance` when the agent has no explicit `vector_store_instance_id`. On fresh installs, OKG Term Memory recall now returns results instead of "no vector store provider available". Verified: `OKG service initialized, provider=True` on an agent with no explicit VS assignment.
- **BUG-681 (High) — Readonly UI mutation controls (`frontend/app/hub/page.tsx`, `frontend/app/flows/page.tsx`, `frontend/components/playground/ExpertMode.tsx`).** Hub `+ New Instance` and per-vendor `Add Instance` buttons now render only when `canWriteHub`. Flows `Enabled`/`Disabled` status toggles (list + detail) now `disabled={!canWriteFlows}` with `cursor: not-allowed` and an explanatory tooltip. Playground composer + Send button gated on `agents.execute`; placeholder changes to "Read-only — requires agents.execute permission" for read-only users. Verified end-to-end via Playwright against a seeded readonly user — all three surfaces went from clickable to non-interactive, owner experience unchanged.
- **BUG-684 (Critical) — Gmail/Calendar httpx timeout tightened (`backend/hub/google/gmail_service.py`, `backend/hub/google/calendar_service.py`).** `_make_request` timeout cut from 30s → 10s on both services. Each failing external-API call now holds a DB session for ≤10s instead of 30s, tripling the effective `QueuePool` saturation threshold under Google-API outages. The deeper architectural fix (releasing the DB session before awaiting the external httpx call across `routes_hub.py`'s health-refresh path) is deferred to a dedicated refactor.
- **BUG-539 (High) — Sentinel `DetachedInstanceError` — closed as FP.** `POST /api/sentinel/test detection_type=shell_malicious` returns 200 with correct threat detection on the current stack; no detach error reproduces.
- **BUG-682 (High) — Qdrant host-port collision on side-by-side installs — deferred.** Requires disposable installer + multi-stack environment to reproduce. Tracked for the next installer-hardening pass.

**Validation:** `output/playwright/full-regression-20260421/preflight/final-regression-sweep3.txt` → **PASS 32 / FAIL 0**. Plus live browser validation against readonly + owner sessions — see BUGS.md "Third Sweep" for per-surface before/after evidence.

Open bugs remaining: 2 (BUG-684 deeper architectural refactor, BUG-682 installer multi-stack port allocation). Down from 5.

### Second Sweep — 8 more bugs fixed on develop (2026-04-21)

User asked to "fix all remaining bugs with comprehensive validation for perfection." This pass landed:

- **BUG-592 — `/api/v2/agents` 500 (`backend/api/routes_agents_protected.py`).** `Agent` has no `.contact` relationship attribute; handler was calling `agent.contact.friendly_name` and raising `AttributeError`. Replaced with explicit `Contact.id.in_(contact_ids)` prefetch. Now returns 200.
- **BUG-593 — Webhook inbound status code (`backend/api/routes_webhook_inbound.py`).** `POST /api/webhooks/{slug}/inbound` now returns **202 Accepted** (was 200), matching documented queued semantics.
- **BUG-590 — `new_contact_welcome` flow template (`backend/flows/flow_engine.py`).** `SummarizationStepHandler` now handles `source_step="trigger"`: serializes `flow.trigger_context` as JSON and feeds it as the source text for the LLM to follow `summary_prompt`. The template runs end-to-end instead of failing with "No thread_id or source text found."
- **BUG-666 — Tool API key validation (`backend/api/routes_api_keys.py`).** Added `_validate_api_key_shape()` with per-service minimum-length + optional prefix rules (OpenAI `sk-*`, Anthropic `sk-ant-*`, Tavily `tvly-*`, Grok `xai-*`, Groq `gsk_*`, etc.). POST and PUT `/api/api-keys` reject structurally invalid keys with 400 before encryption. Cards can no longer be "activated" with placeholder strings like `"test"`.
- **BUG-675 — Hub Slack/Discord Test Connection (`backend/api/routes_slack.py`, `backend/api/routes_discord.py`).** Added 4 missing endpoints: `POST /api/slack/integrations/{id}/test` (Slack `auth.test`), `GET /api/slack/integrations/{id}/channels` (`conversations.list`), `POST /api/discord/integrations/{id}/test` (Discord `/users/@me` + guild count), `GET /api/discord/integrations/{id}/guilds` (`/users/@me/guilds`). Hub UI buttons now hit real endpoints instead of 404-ing.
- **BUG-683 — Public setup calls authenticated `/api/tts-providers` (`frontend/components/OnboardingWizard.tsx`).** `useEffect` that fires `api.getTTSProviders()` now short-circuits on `/auth/*` and `/setup/*` — matches the existing render-guard so no 401 fires before login.
- **BUG-589 (FP) — Tavily registered but reportedly rejected.** Verified in `SearchProviderRegistry.initialize_providers()`; Tavily IS registered and `get_provider("tavily")` returns an instance. Not reproducible on current `develop`. Closing as FP / already fixed.
- **BUG-591 (FP) — `proactive_watcher` flow `tool_name` mismatch.** `_execute_sandboxed_tool` already accepts both tool-slug strings and numeric ids (lines 740-757 look up the id internally). Template works as-is. Closing as FP / already fixed.

Still open (deferred, non-trivial): BUG-684 (architectural session-leak refactor — mitigated, deeper fix deferred), BUG-539 (Sentinel DetachedInstanceError — can't reproduce, pending concrete repro), BUG-540 (OKG Qdrant auto-connect — fresh-install specific), BUG-681 (cross-cutting frontend RBAC gating — backend already 403s), BUG-682 (Qdrant port collision on side-by-side installs).

**Validation:** `output/playwright/full-regression-20260421/preflight/final-regression.txt` = PASS 32 / FAIL 0.

### Post-Abort Bug Sweep — 9 bugs fixed on develop (2026-04-21)

After the 4-audit regression aborted on the `BUG-684` backend deadlock, I fixed the remaining backend-side open bugs and validated them against a rebuilt stack. 19/20 smoke checks pass (the 20th is a `/api/hub/integrations/` 307 trailing-slash redirect — not a regression).

- **BUG-671 (High) — WebSocket auth rejects disabled users (`backend/app.py`).** `/ws` and `/ws/playground` now look up `User` by `id`, reject inactive/deleted accounts with close code 4003 "Account disabled" — mirrors `/ws/shell/status`.
- **BUG-672 (High) — Playground / commands gated on `agents.execute` (`backend/api/routes_playground.py`, `backend/api/routes_commands.py`).** `POST /api/playground/chat`, `POST /api/playground/threads`, and `POST /api/commands/execute` all now require `agents.execute`; read-only role (which lacks it) will be denied by the permission middleware. Also added `except HTTPException: raise` to `send_chat_message` so raised 404s propagate instead of being swallowed into a 200 with `status=error`.
- **BUG-673 (Medium) — System persona/tone detail access (`backend/api/routes_personas.py`, `backend/api/routes_agents.py`).** Detail endpoints now pass `allow_shared=True` to `ctx.can_access_resource(...)`, matching the list endpoints which already return `tenant_id=NULL` system rows.
- **BUG-674 (Low) — Agent detail 403/404 oracle (`backend/api/routes_agents.py`).** Internal `GET /api/agents/{id}` now returns 404 on cross-tenant access, matching API v1 — no more existence enumeration via 403/404 delta.
- **BUG-676 (Medium) — Slack update mode validation (`backend/api/routes_slack.py`).** `PUT /api/slack/integrations/{id}` now rejects `mode="socket"` when no `app_level_token` is stored or supplied, instead of silently saving a config that cannot start the Socket Mode worker.
- **BUG-677 dupe (Low) — `skills.custom.read` granted to readonly role (`backend/db.py`).** `ensure_rbac_permissions` now grants the permission to read-only on boot. Fresh installs seed it; existing deployments pick it up on next restart.
- **BUG-678 (Low) — Slack create fails closed on missing tenant (`backend/api/routes_slack.py`).** `POST /api/slack/integrations/` returns 400 "Slack integrations are tenant-scoped..." when `current_user.tenant_id` is None (global admin without tenant), instead of bubbling a lower-level 500.
- **BUG-679 (High) — Cross-tenant agent ID in thread create (`backend/services/playground_thread_service.py`).** `PlaygroundThreadService.create_thread` now filters the `Agent` lookup by BOTH `id` AND `tenant_id`, so a foreign-tenant `agent_id` is rejected before the `ConversationThread` row is persisted.
- **BUG-680 (Medium) — Inactive agents executable via direct ID (`backend/api/routes_playground.py`).** `send_chat_message` now returns 404 when `agent.is_active` is false. Verified: HTTP 404 with `"detail":"Agent {id} not found"`.
- **BUG-684 (Critical) — Backend deadlock from Gmail `ConnectTimeout` + `QueuePool` exhaustion (mitigation).** The immediate wedge was cleared by restart + rebuild. Pool status post-fix: 0 checked-out, no waiters. Longer-term remediation (moving async external-API calls outside held DB sessions) tracked as follow-up; no session-leak remediation code landed in this sweep.

**Deferred (not in this sweep):** BUG-675, BUG-681, BUG-683 (frontend-heavy), BUG-682 (installer port allocation). Tracker header count updated to reflect resolution of 9 + the pool-deadlock clear (10 total), leaving 4 recent bugs open (plus older ones).

### QA — UI-First 4-Audit Regression Campaign, ABORTED at preflight (2026-04-21)

Autonomous run of `.private/TEST_PLAYBOOK_UI_FIRST_REGRESSION.md` on the `develop` stack was **aborted at Phase A** per the playbook's §14 hard rule ("Backend returns 502 after burst of `/api/readiness` → Abort the audit. Do not mask by restart."). The backend container had accumulated 137 consecutive unhealthy health-check failures when the campaign started; every `/api/health` request returned `502` from Caddy because the FastAPI worker was deadlocked on `QueuePool` acquisition.

Root cause (documented as `BUG-677`, Critical): the Gmail poll loop in `backend/hub/google/gmail_service.py` leaks a DB session on every `httpx.ConnectTimeout` against `*.googleapis.com`. The `channel_health_service` async loop re-runs each cycle, leaking one session per failure. After ~50 cycles the pool exhausts (`QueuePool limit of size 20 overflow 30 reached, connection timed out, timeout 30.00`) and every downstream request — including `/api/health` — deadlocks.

Phases B (Playground), C (Sentinel), D (Flows), E (Full-Stack Multi-Tenant), F (VM fresh install) were **not executed** — any evidence collected against a wedged backend would have been meaningless. Cleanup (Phase H) is a no-op because no fixtures were created.

- **Severity counts:** Critical × 1 (`BUG-677`). Opened 1 new bug, closed 0.
- **Evidence:** `output/playwright/full-regression-20260421/preflight/{preflight-summary.md,backend-logs.txt,backend-health.json,docker-ps.txt}` and draft at `tmp/regression-20260421/bugs-drafts/audit-0-preflight.md`.
- **Follow-up:** rerun the 4-audit matrix after `BUG-677` is resolved. Until then, merging `develop` → `main` (PR #32) is flagged as risky — the deadlock reproduces on the current `develop` tip.

### ProviderWizard — Link-to-agents post-create step + delete-volume default on (2026-04-21)

Two follow-ups after the Ollama parity pass.

- **Default `Also remove container volume` → checked (`frontend/app/hub/page.tsx`)** — when a tenant clicks Delete on a managed container row, the volume checkbox opens checked. Leaving volumes behind after a delete was almost never what users wanted (stale cached models + reprovision-blocked name collisions per BUG-670). They can still uncheck to preserve the volume.
- **New `assignAgents` wizard step (`frontend/lib/provider-wizard/reducer.ts`, `frontend/components/provider-wizard/ProviderWizard.tsx`, new `frontend/components/provider-wizard/steps/StepAssignAgents.tsx`)** — after creating an LLM provider instance the Progress "Ready" screen now surfaces a `Link to agents →` button that takes the user to an optional post-create step. That step lists the tenant's agents with their current LLM (`vendor/model_name`), lets the user pick a model from the newly-created instance's `available_models`, and hits `POST /api/provider-instances/{id}/assign-to-agent` per selected agent — the same endpoint the Ollama setup wizard already uses. Each row shows an inline per-agent result (Linked / Linking… / Failed). Skip is first-class: a `Done` footer button closes without applying. TTS and Image modalities skip the step entirely because they have their own assign flows. This closes the gap identified during BUG-582 triage where creating a provider via the wizard meant a second trip to Agent Studio just to point an agent at it.

### ProviderWizard — consolidate Ollama model selection (2026-04-21)

The guided ProviderWizard was asking for Ollama models twice: Step 5 "Pull starter models?" (to feed the provisioner) then Step 6 "Test & choose models" (to expose to agents). The second step was redundant for the Ollama local path — users had to pick the same models again, and typing a model in Step 6 that wasn't pulled in Step 5 produced a broken instance.

- **`frontend/lib/provider-wizard/reducer.ts`** — `getStepOrder` no longer emits `testAndModels` for `vendor='ollama' && hosting='local'`. Ollama local flow goes `modality → hosting → vendor → container → pullModels → review → progress`.
- **`frontend/components/provider-wizard/steps/StepOllamaPullModels.tsx`** — Rewritten as the single "Pick models" step. Curated suggestions still rendered as toggle cards; a new custom-tag input lets users add any Ollama tag (`llama3.2:8b-instruct-q4_K_M`, etc.), with chips to remove them. Whatever the user picks is mirrored into BOTH `pull_models` (so the provisioner downloads it) AND `available_models` (so agents can select it). At least one model is required — Next is gated on selection since `ProviderInstanceCreate` requires `available_models.length >= 1`.

No backend change. Cloud/Image paths still use the standard `testAndModels` step.

### Hub provider setup UX — Ollama parity, wizard drift fixes, card cleanup (2026-04-21)

Follow-up pass on the Hub provider setup work. Ollama's panel was still a tangle of radio buttons, inline Test/Refresh/Manage buttons, and a separate Deprovision button, while Kokoro and SearXNG had already moved to a single `ManagedContainerPanel`. That drift was user-visible — cards felt different depending on the service. At the same time, a dedicated wizard-drift audit surfaced three BUG-582-class silent field losses.

- **Ollama card refactored to match Kokoro / SearXNG (`frontend/app/hub/page.tsx`):**
  - Panel now renders only when an active `ollama` provider instance exists (mirrors `kokoroInstances.length > 0` and `searxngInstances.length > 0`). The old `ollamaEnabled` gate kept the panel visible even with no instance and was the source of the "fixed card" complaint.
  - Mode radio (host vs. auto-provision) removed. Mode is derived from `instance.is_auto_provisioned` — it's a creation-time choice made in the wizard, not a live toggle. Auto-provisioned → ManagedContainerPanel with enable/disable/restart/logs/test/delete; host-mode → URL inline editor, Docker networking note, and a compact Test/Refresh-Models/Delete action strip (container lifecycle affordances are meaningless against an external host).
  - Separate Deprovision button dropped; `ManagedContainerPanel`'s Delete opens the new `ollamaConfirmDelete` modal (mirrors the Kokoro modal, including the "remove container volume" escape hatch).
  - Bottom Test Connection / Refresh Models / Manage Instance action row dropped; those affordances are folded into the per-instance row.
- **Notion + GitHub "coming soon" cards removed (`frontend/app/hub/page.tsx`):** deleted from `PRODUCTIVITY_APPS` / `DEVELOPER_TOOLS`, dropped the dead `.filter(...).map(...)` render blocks, pruned the unused `DocumentIcon` / `GitHubIcon` imports, and updated the Productivity and Developer Tools info-box copy so it no longer references them.
- **ProviderWizard — Step 5 gates Next on having ≥ 1 model (`frontend/components/provider-wizard/steps/StepTestAndModels.tsx`, `StepReview.tsx`):** `ProviderInstanceCreate` requires `available_models.length >= 1`; Step 5 previously always marked itself complete and the empty state read "Auto-detect after saving", which is false — POST returns 400. Step 5 now fails to complete until a model is added (via Auto-detect, suggestion, or typed ID), the empty state shows a red "At least one model is required…" message, and the Review step calls out a missing-models row explicitly rather than implying auto-save.
- **BUG-582-class: Slack `dm_policy` silently dropped (`backend/api/routes_slack.py`):** `SlackSetupWizard` sent `dm_policy: 'open' | 'allowlist' | 'disabled'`, but `SlackIntegrationCreate` / `SlackIntegrationUpdate` did not list the field, so Pydantic discarded it and the row fell back to the column default. Added `dm_policy` to both schemas (with validator), wired it through the create handler, the update handler, and `SlackIntegrationResponse`. Roundtrip verified end-to-end against a live tenant: POST with `dm_policy: 'disabled'` → 200 → GET returns `"dm_policy": "disabled"`.
- **BUG-582-class: ProviderWizard Kokoro branch dropped voice defaults (`frontend/components/provider-wizard/steps/StepProgress.tsx`):** `TTSInstanceCreate` accepts `default_voice / default_language / default_speed / default_format`, but the guided wizard's Kokoro branch omitted them, producing instances with null voice configuration that fell back to whatever the service layer hardcoded. The guided path now forwards the same defaults `KokoroSetupWizard` uses (`pf_dora / pt / 1.0 / opus`) so a Kokoro instance is usable out of the box; the advanced `KokoroSetupWizard` remains the place to pick custom voices.
- **OllamaSetupWizard — instance_name now applied (`frontend/components/ollama/OllamaSetupWizard.tsx`):** `POST /api/provider-instances/ensure-ollama` ignores the request body and always names the row "Ollama (Local)", so the wizard's step-2 name field had no effect. The wizard now follows the ensure-instance call with a rename via `updateProviderInstance` when the user-chosen name differs from the default; rename failures are non-blocking so provisioning still proceeds.
- **Validation:** `docker compose build --no-cache backend frontend` passed cleanly; guided Cloud LLM (Anthropic) wizard walked end-to-end (create with fake key + model → "Ready", cleaned up via DELETE); guided Web-Search wizard walked end-to-end (SearXNG container auto-provisioned, health "healthy", panel rendered with `ManagedContainerPanel`, cleaned up with `?remove_volume=true`); Slack `dm_policy` roundtripped through POST+GET+DELETE; Kokoro voice fields roundtripped through POST+GET (all four fields persisted).

### BUG-582: Agent wizard dropped provider_instance_id (2026-04-21)

Root-cause fix for a silent-data-loss bug in the Agent Creation Wizard where the user-selected provider binding was never persisted — fatal for Vertex AI (and any vendor whose credentials live on the instance, not on a flat `api_key` row).

- **Backend schema.** `AgentCreate` in `backend/api/routes_agents.py` was missing `provider_instance_id` entirely, so Pydantic silently dropped the field on `POST /api/agents`. Added the field plus a tenant-scoped validator that verifies the instance belongs to the caller, is active, and matches the requested vendor. The same validator was added to the update path. `memory_isolation_mode` was also missing from both schemas and the update allowlist — added.
- **Frontend wizard.** `StepBasics` now renders a real **Provider instance** selector filtered to `(vendor, is_active, api_key_configured)`. Previously the step deduplicated instances down to one per vendor and only captured the vendor name, so a tenant with three Vertex instances had no way to pick one. The wizard draft (`BasicsConfig`) now carries `provider_instance_id`, the validator requires it for every non-Ollama vendor, and `useCreateAgentChain` sends it in the create payload. The "Built-in + semantic" / "External vector store" memory modes now also toggle the `semantic_search` skill — previously the setting was recorded on the draft but never wired through to an `AgentSkill` row.
- **Runtime safety net.** `AIClient.__init__` now resolves the tenant's default `ProviderInstance` for the requested vendor when no `provider_instance_id` is passed. This recovers pre-fix orphan agents (NULL FK) and prevents the Vertex flat-field path (which can never succeed) from being hit when a working default instance exists.
- **Files modified.** `backend/api/routes_agents.py`, `backend/agent/ai_client.py`, `frontend/components/agent-wizard/steps/StepBasics.tsx`, `frontend/components/agent-wizard/hooks/useCreateAgentChain.ts`, `frontend/lib/agent-wizard/reducer.ts`.
- **Validation.** (1) Orphan agent 211 (`provider_instance_id = NULL`, vendor `vertex_ai`) — chat via `POST /api/v1/agents/211/chat` returned `"pong"` in 19s, confirming the safety net auto-bound to the tenant default Vertex instance. (2) Wizard-created agent 212 (`WizardFixTest`) — DB row shows `provider_instance_id = 2`, `memory_isolation_mode = 'isolated'`; chat returned `"wizard-fix-confirmed"` in 7s. (3) Backend rebuilt with `docker-compose build --no-cache backend && docker-compose up -d backend` and frontend with `--force-recreate`, both healthy post-restart, zero backend errors.

### Hub: guided ProviderWizard + unified ManagedContainerPanel (2026-04-21)

Second-pass refactor on top of the earlier Hub cleanup. The flat `ProviderSetupWizard` picker was replaced with a guided multi-step wizard that mirrors the Agent/WhatsApp/Audio/Gmail wizard pattern, and the three auto-provisioned local services (Ollama, Kokoro, SearXNG) now share a single `<ManagedContainerPanel />` for lifecycle controls.

- **New guided Provider wizard.** `frontend/components/provider-wizard/ProviderWizard.tsx` with 7 step modules (`StepModality`, `StepHosting`, `StepVendorSelect`, `StepCredentials`, `StepContainerProvision`, `StepOllamaPullModels`, `StepTestAndModels`, `StepReview`, `StepProgress`). Step pills, Back/Next/Advanced/Cancel footer, jump-to-edit on the review step. Mounted globally via `ProviderWizardProvider` in `app/layout.tsx`.
- **Modality-first branching.** Step 1 asks LLM vs TTS vs Image generation. Step 2 asks Cloud vs Self-hosted (auto-skipped for Image → Cloud only today). Step 3 filters the vendor list to the matching combination. The removed "Web Search / Tool API" category stays in the Tool APIs tab's own flow — no cross-contamination.
- **Image generation is a first-class modality.** Selecting Image → Cloud lands on Gemini pre-tagged "Uses Nano Banana / Nano Banana Pro". No new backend vendor; it's still a `ProviderInstance` with `vendor='gemini'`.
- **Advanced fallback.** The wizard footer's "Switch to Advanced" button dispatches `tsushin:open-provider-advanced-modal`; `hub/page.tsx` listens and opens the existing `ProviderInstanceModal` with the current vendor prefilled. Mode preference persists to `localStorage` (`tsushin:providerWizardMode`), non-secret draft persists to `tsushin:providerWizardDraft`.
- **ManagedContainerPanel extracted.** `frontend/components/hub/ManagedContainerPanel.tsx` replaces the inline `renderManagedContainerControls` helper at all three call sites (Ollama running, Ollama stopped, Kokoro instance row, SearXNG instance row). Every managed container now renders the exact same control strip: status pill + enable/disable toggle + restart + logs + optional test + delete.
- **Ollama panel-level toggle removed.** The divergent `ToggleSwitch` at the Ollama card header is gone — the per-instance `ManagedContainerPanel` is now the single source of truth for start/stop, matching Kokoro and SearXNG.
- **Service API Keys collapsed.** The always-visible fallback block in AI Providers is now a `<details>` disclosure collapsed by default. Only vendors with a fallback api_key AND zero `ProviderInstance` rows appear — this kills the duplicate-Gemini display by construction. The inline "Fallback — instance key takes priority" amber label is removed.
- **Files created.** `frontend/contexts/ProviderWizardContext.tsx`, `frontend/lib/provider-wizard/reducer.ts`, `frontend/components/provider-wizard/ProviderWizard.tsx`, `frontend/components/provider-wizard/steps/*`, `frontend/components/hub/ManagedContainerPanel.tsx`.
- **Files deleted.** `frontend/components/providers/ProviderSetupWizard.tsx` (the flat picker).
- **Files modified.** `frontend/app/hub/page.tsx` (bridge `openProviderSetupWizard` → new wizard, remove state, collapse Service API Keys, swap in `ManagedContainerPanel`), `frontend/app/layout.tsx` (mount `ProviderWizardProvider`).
- **No backend changes.** Reuses existing endpoints: `POST /api/provider-instances`, `POST /api/tts-instances`, `POST /api/api-keys`, `POST /api/settings/ollama/provision`, `POST /api/provider-instances/{id}/test-connection`, `GET /api/providers/vendors`, `GET /api/providers/predefined-models`.
- **Validation.** `docker-compose build --no-cache frontend` compiled with zero errors in 18.4s. `docker logs tsushin-frontend` shows zero errors post-rebuild; `curl -sk https://localhost/auth/login` returns 200.
- **Post-QA fixes.** Normalized Docker's `'exited'` container state to `'stopped'` inside `ManagedContainerPanel` and the Ollama/Kokoro/SearXNG container-state branches so the lifecycle control strip (toggle / restart / logs / delete) renders for stopped-but-still-existing containers — previously all render branches fell through when the container was `exited`. Defined `isStopped` locally in the Kokoro and SearXNG `.map()` closures; they were silently leaking to the outer Ollama IIFE scope. Restyled Ollama "Manage Instance" as a pill button for visual parity with `Test Connection` / `Refresh Models`. Full QA re-run: Defect #2 PASS (container `exited → panel visible → toggle → running` end-to-end); Service API Keys disclosure verified working-as-designed (hidden when empty, renders correctly when an ElevenLabs fallback key exists without a matching instance).

### Hub provider setup UX cleanup (2026-04-21)

Tenant-facing cleanup for Hub > AI Providers and Hub > Tool APIs so unused provider configuration no longer appears as fixed empty cards.

- **Hub AI Providers**: empty static vendor panels are gone. The tab now renders only configured provider-instance vendor groups, hides unused Local Services cards until Ollama/Kokoro exists, and only shows Service API Key fallback cards when an actual fallback key is configured.
- **Guided setup default**: `+ New Instance` now opens a guided Add Provider wizard with Cloud/API LLM, Local LLM, Audio/TTS, and Web Search/Tool API routes. The existing provider instance form remains available through Advanced Form, while Ollama/Kokoro/SearXNG continue through their existing guided flows.
- **Tool APIs / SearXNG**: the SearXNG top card and self-hosted management panel no longer render before an instance exists. SearXNG remains available from `+ Add Integration` and the guided provider wizard.
- **Container controls**: Ollama, Kokoro, and SearXNG managed rows now use a consistent enable/disable toggle for container start/stop. Restart, Logs, Delete, and deprovision remain explicit secondary/destructive actions.
- **Mobile polish**: Hub section headers stack their primary setup actions on small screens, provider-level add actions render as compact pills, and the shell header no longer creates horizontal overflow on Hub mobile views.
- **Backend hardening**: provider-instance responses include Ollama container metadata for reliable UI state, auto-provisioned Ollama deletes deprovision before soft-delete, and SearXNG delete cleanup is scoped through tenant-owned agents only.
- **Validation**: `npm run build` passed for the frontend; focused backend regression `pytest -o addopts='' tests/test_provider_instance_hardening.py -q` passed with 3 tests; `docker-compose build --no-cache frontend && docker-compose up -d frontend` refreshed the Hub bundle after polish. Baseline browser artifacts were captured under `output/playwright/hub-provider-setup-baseline-20260421/`; final desktop/mobile screenshots and overflow checks are under `output/playwright/hub-provider-setup-final-20260421/`.

### Fresh-install VM regression audit — current `develop` (2026-04-20)

Audit-only pass from a brand-new Ubuntu VM clone at `~/tsushin-v060-audit-20260420`, with evidence under `.private/qa/vm-fresh-install-20260420/run-20260420-230152/` and browser artifacts under `output/playwright/vm-fresh-install-20260420/run-20260420-230152/`. The clone captured `2317397e0d97222981a5b9a69c8a6f6b43ca8c62`; `origin/develop` advanced after the install evidence was captured. The requested `sudo python3 install.py` path was attempted and logged, but the disposable VM user could not provide a sudo password, so the installer was run non-sudo from the same fresh clone without `.env`, Caddy, Docker, certificate-store, or generated-file edits.

- Fresh remote self-signed install on `https://10-211-55-5.sslip.io` completed with backend `8081`, frontend `3030`, Caddy, Postgres, Docker proxy, WhatsApp MCP image, and toolbox image healthy on stock Docker 28.2.2 without buildx. Final backend, readiness, and `curl -k` edge checks stayed healthy after the breadth pass.
- `/setup` completed in headed Playwright with a disposable tenant admin, default agents enabled, Gemini bootstrap provider, and captured global-admin credentials stored only in private evidence. Tenant and global browser sweeps covered Watcher dashboard/graph/security/A2A, Hub, Agent Studio/custom skills, Playground, Flows, vector stores, API clients, Sentinel settings, integrations, tenants, users, plans, remote access, and SSO. Watcher graph showed seeded agent, Playground, and Webhook nodes with no phantom WhatsApp node.
- Provider matrix revalidated Gemini, OpenAI, Anthropic, Vertex AI, Brave Search, and Tavily through product/API-supported setup and connection tests. SerpAPI was skipped because no private SerpAPI secret was available. Ollama auto-provision completed through product APIs, pulled `llama3.2:1b`, discovered the model, and passed the saved provider-instance connection test after the cold image pull settled.
- TC-1 through TC-23 API coverage passed for setup/auth, provider setup, memory/facts/vector-store/KB paths, Sentinel/MemGuard preflight, custom instruction/script/MCP skills, slash commands, flows/templates, webhook signing/queue completion, API v1 OAuth/direct-key/sync/async/OpenAPI/generated-client paths, `/api/v2/agents/graph-preview`, and the post-breadth stability checkpoint. The old QueuePool/idle-in-transaction outage family did not reappear; post-breadth health/readiness stayed green.
- Existing findings revalidated: BUG-592 still reproduces (`GET /api/v2/agents/` returns 500), BUG-593 still reproduces as a contract mismatch (`POST /api/webhooks/{id}/inbound` returns 200 with queued payload instead of documented 202), and BUG-595 still reproduces because strict Shell Beacon registration against the installer-generated self-signed public URL fails certificate verification. BUG-594 and BUG-663 were revalidated as fixed in this pass: provider-instance-backed webhook work completed successfully and cold Ollama auto-provision reached a healthy local model.

### UI-first exact-tag v0.6.0 fresh-install audit (2026-04-20)

Audit-only pass from a disposable clone at `.private/installations/fresh-install-v060-20260420-232626/tsushin`, with evidence under `.private/qa/fresh-install-v060-20260420-232626/`. The original local runtime was backed up, stopped without deleting persistent state, and restored after the disposable runtime was removed. Local restore verification passed for the original backend, readiness endpoint, Caddy proxy, and captured dynamic containers; the public `tsushin.archsec.io` hostname remained Cloudflare 1033 before and after the audit.

- Tested exact tag `v0.6.0` (`ec6f3f9`) with unattended self-signed install and stack identity `freshinstall-v060-tsushin`.
- Revalidated BUG-575 as a release-tag blocker: the backend fails Alembic startup because baseline migration `0001` creates `tenant.public_base_url` from ORM metadata and migration `0034_add_tenant_public_base_url.py` then unconditionally tries to add the same column. The backend enters a restart loop, so `/api/health`, `/api/readiness`, frontend `/setup`, provider setup, Remote Access, API v1, memory/vector-store, Sentinel/MemGuard, A2A, flows, MCP/custom skill/toolbox/shell, sandbox/slash-command, and WhatsApp sweep items were blocked on the unmodified tag.
- No product code, schema, API, or runbook changes were made in this audit; `BUGS.md` was updated locally with the revalidation and evidence paths.

### Hub panel cosmetic consistency — Ollama / Kokoro / SearXNG (2026-04-20)

Tenant-reported cosmetic drift between the three auto-provisionable service panels (Ollama in AI Providers → Local Services, Kokoro in the same block, SearXNG in Tool APIs). Flagged issues: Kokoro empty-state duplicated the "Setup with Wizard" CTA (header + body), Ollama showed the `ToggleSwitch` even before activation so users had two setup entry points competing, SearXNG auto-hid its management panel when empty and had no header "Setup with Wizard" shortcut (tenants had to go to Tool APIs → Add Integration → Web Search → SearXNG). Delete/Logs action divergence across panels.

- **Kokoro** (`frontend/app/hub/page.tsx`): removed the body `Setup with Wizard` in the empty state; the panel header already has `+ Setup with Wizard` and that's now the single entry point. Empty-state message points at it.
- **Ollama** (`frontend/app/hub/page.tsx`): `ToggleSwitch` is hidden until the tenant has opted in. When disabled, the big `+ Setup with Wizard` CTA is the only action. When enabled, the toggle + Mode selector + advanced controls are shown and the wizard CTA is hidden — one primary action per state. Status copy changed from `Healthy/Offline` to `1 instance / pending / disabled` to align with Kokoro/SearXNG.
- **SearXNG** (`frontend/app/hub/page.tsx`): panel always renders (auto-hide dropped), with an empty-state message mirroring Kokoro's. Added `+ Setup with Wizard` header button that opens `AddIntegrationWizard` pre-selected on SearXNG. Added `Logs` action on the instance card (new `getSearxngContainerLogs` client helper). Replaced the native `confirm()` delete with a proper modal matching the Kokoro pattern. Header gained a globe icon + "Per-tenant metasearch containers" subtitle so the panel structure matches the Kokoro card.
- **Tool APIs grid card for SearXNG**: was hard-coded to `Not configured` because the badge only checked `api_keys` rows. Now also counts `SearxngInstance` rows via a new `hasSearxngInstance` closure in `renderIntegrationCard`. Card shows `Active` + `Configured via instance:` helper when instances exist, `Not configured` otherwise.
- **Client** (`frontend/lib/client.ts`): new `getSearxngContainerLogs(id, tail)` helper backing the SearXNG Logs drawer.

No backend changes. UI verified end-to-end for both populated and empty states; auto-provision E2E regression re-run afterwards (SearXNG port 6500, Kokoro port 6600, Ollama port 6700 — all healthy).

### BUG-670 — Ollama re-provision after delete fails with UniqueViolation (2026-04-20)

Surfaced by the `delete all → auto-provision all` regression run after BUG-669 landed: `POST /api/provider-instances/ensure-ollama` returned 500 when the tenant previously had a soft-deleted `Ollama (Local)` row. The unique constraint `uq_provider_instance_tenant_name` covers both active and soft-deleted rows, so `create_instance()` hit `psycopg2.errors.UniqueViolation` on re-create. Same bug class as BUG-669 but for the provider-instance create path.

- `backend/services/provider_instance_service.py create_instance()` now purges any soft-deleted rows matching `(tenant_id, instance_name)` before insert. Matches the SearXNG pattern in `routes_searxng_instances.py` and preserves the soft-delete audit trail for deleted rows with different names.

### BUG-669 — SearXNG wizard `default already exists` unblock + Hub management panel (2026-04-20)

Tenants who hit a partial/failed SearXNG auto-provision (or simply re-opened the wizard) were stuck: the Add-Integration wizard hardcoded `instance_name='default'` and the backend rejected the duplicate with a bare 409 `"SearXNG instance 'default' already exists"` — no recovery UI, no way to rename, no way to delete from the frontend. Mirrors the same pattern Ollama and Kokoro avoided by (a) letting users name instances and (b) exposing a Hub management panel.

- **Backend auto-recovery.** `backend/api/routes_searxng_instances.py create_searxng_instance()` now inspects the conflicting active row and auto-purges it if it's a stale failed provision (`container_status ∈ {error, failed, none, null}` and `container_name` is null). Only genuinely-healthy conflicts keep the 409 — and the response body is now a structured `{code: 'searxng_instance_exists', existing_instance_id, existing_instance_name, existing_container_status, message}` so the UI can link to recovery actions.
- **Frontend wizard.** `frontend/components/integrations/AddIntegrationWizard.tsx` no longer hardcodes the name. Step 3 fetches `GET /api/hub/searxng/instances`, lists any existing rows with an inline delete action, and auto-suggests a unique name (`SearXNG`, `SearXNG (2)`, …). The 409 structured-detail is parsed and surfaces a recovery hint rather than a raw error.
- **Frontend Hub management panel.** `frontend/app/hub/page.tsx` Tool APIs tab now renders a SearXNG instances card (auto-hidden when empty) with list, start/stop/restart, delete, and provisioning-status polling — same pattern as the Kokoro/Ollama panels that already exist.
- **Client helpers.** `frontend/lib/client.ts` gains `SearxngInstance` + `SearxngInstanceCreate` types and `listSearxngInstances`, `createSearxngInstance`, `deleteSearxngInstance`, `searxngContainerAction`, `getSearxngContainerStatus`.

Container-manager failure path already marks `container_status='error'` and clears `container_name` (`backend/services/searxng_container_manager.py`), so the auto-purge guard catches the common stuck-state without further service-layer changes.

### AddIntegrationWizard fetches providers from live registry (2026-04-20)

Continuation of the wizard-drift-prevention work. `AddIntegrationWizard` (Hub > Tool APIs > Add Integration) no longer treats its hardcoded `PROVIDERS` array as canonical — the wizard now fetches the live catalog at mount and falls back to a renamed static `FALLBACK_PROVIDERS` array only when the API is unreachable.

- New endpoints: `GET /api/hub/search-providers` and `GET /api/hub/travel-providers` (`backend/api/routes_hub_providers.py`) return every registered provider with `{id, name, description, status, requires_api_key, is_free, tenant_has_configured}`. Both require `hub.read`, both tenant-scope the `tenant_has_configured` check (API keys, SearXNG instances, Amadeus / Google Flights integrations are all tenant-owned).
- Frontend typed clients `api.getSearchProviders()` / `api.getTravelProviders()` (`frontend/lib/client.ts`) return `SearchProviderInfo` / `TravelProviderInfo`. The wizard merges the live catalog with `FALLBACK_PROVIDERS` (matched by `id`) — credential-workflow fields (`credentialMode`, `skillProvider`, `apiKeyService`, `keyUrl`) stay in the fallback because they're UI-only metadata not tracked in backend registries.
- Renamed the frontend fallback id `serpapi` → `google` to match the backend `SearchProviderRegistry` key. Label and downstream behaviour unchanged (`skillProvider: 'google'`, `apiKeyService: 'serpapi'`).
- Drift guards: `backend/tests/test_wizard_drift.py` gains `test_search_providers_registered_match_wizard_fallback` + `test_flight_providers_registered_match_wizard_fallback`. Adding a backend provider without updating the fallback array now fails CI.

No user-facing UX change — the wizard renders identically, just sourced from the API when available.

### Wizard drift prevention — ProviderInstanceModal vendors + Ollama curated models (2026-04-20)

Third pass of the wizard-drift consolidation started in commits `a9bfdc9` / `28f54bb` / `d8805f0`. Two more hardcoded lists folded into single-source modules.

- **Vendor catalog.** `ProviderInstanceModal.tsx` used to keep a parallel 10-entry `VENDORS` array shadowing backend `VALID_VENDORS` (`routes_provider_instances.py`) and `SUPPORTED_VENDORS` (`provider_instance_service.py`). New endpoint `GET /api/providers/vendors` returns `[{id, display_name, default_base_url, supports_discovery, tenant_has_configured}, …]` for all 10 vendors (openai, anthropic, gemini, groq, grok, openrouter, deepseek, vertex_ai, ollama, custom). `tenant_has_configured` resolves in one DB round-trip per request. The modal now fetches on open and falls back to a reduced static array only on failure. `VENDOR_DISPLAY_NAMES` + `VENDORS_WITH_LIVE_DISCOVERY` added alongside `VALID_VENDORS` as the single source of truth.
- **Ollama curated models.** Extracted the 7 editorial curated models (llama3.2:1b, llama3.2:3b, qwen2.5:3b, qwen2.5:7b, deepseek-r1:7b, phi3.5:3.8b, mistral:7b) to `frontend/lib/ollama-curated-models.ts` as `OLLAMA_CURATED_MODELS` (typed objects) + `OLLAMA_CURATED_MODEL_IDS` (tags). Both the Hub Ollama panel (`frontend/app/hub/page.tsx`) and the setup wizard (`frontend/components/ollama/OllamaSetupWizard.tsx`) now import from the shared module instead of redeclaring the list. No backend endpoint — the curation is editorial, not derived from a registry.
- **Client types.** `frontend/lib/client.ts` gained `VendorInfo` interface + `api.getProviderVendors()` method (returns `[]` on failure, preserves offline fallback).
- **Drift guards.** `backend/tests/test_wizard_drift.py` gets Guard 6 (vendor catalog: backend `VALID_VENDORS` ⇄ `SUPPORTED_VENDORS` ⇄ modal fallback `VENDORS: VendorInfo[]`) and Guard 7 (shared Ollama module exports + both call-sites import from it, never redeclare).

Verified end-to-end on the local stack: `GET /api/providers/vendors` returns 10 rows with correct `tenant_has_configured` for the test tenant. New wizard-drift tests pass.

### Wizard drift prevention — StepChannels fetches backend catalog (2026-04-20)

Mirrors the StepSkills pattern landed in commit `a9bfdc9`: the agent wizard's channel picker no longer hardcodes its 6-channel list.

- Added `backend/channels/catalog.py` with `CHANNEL_CATALOG` (frozen `ChannelInfo` dataclass per channel: id, display_name, description, requires_setup, setup_hint, icon_hint). Seeded with playground, whatsapp, telegram, slack, discord, webhook.
- Added `GET /api/channels` (`backend/api/routes_channels.py`) returning each catalog entry annotated with `tenant_has_configured` — checks `WhatsAppMCPInstance`, `TelegramBotInstance`, `SlackIntegration`, `DiscordIntegration`, `WebhookIntegration` rows for the caller's tenant. Playground is always considered configured; DB lookup failures degrade conservatively to `false`.
- Registered the router in `backend/app.py`.
- `frontend/lib/client.ts` gained `ChannelCatalogEntry` + `api.getChannelCatalog()`.
- `frontend/components/agent-wizard/steps/StepChannels.tsx` now fetches the catalog at mount and falls back to a commented fallback-only array when the API is unreachable. Channels with `requires_setup && !tenant_has_configured` render a "Needs setup" amber badge.
- `backend/tests/test_wizard_drift.py` extended with a Guard 5 that asserts every backend catalog id is present in the frontend fallback array and every entry has a non-empty `display_name`.

### BUG-668 — Kokoro auto-provision disconnect fix (2026-04-20, post-PR-#26 regression)

Surfaced by the post-merge comprehensive regression when a QA agent actually exercised the Kokoro wizard end-to-end (earlier regression passes only clicked through the wizard UI without committing a provision). Kokoro hit the same `psycopg2.OperationalError: server closed the connection unexpectedly` + `docker-socket-proxy Read timed out` disconnect pattern BUG-663 fixed for Ollama, because the BUG-663 fix only covered `ollama_container_manager.py` and didn't include the parallel `kokoro_container_manager.py` path.

Applied the same fix pattern to `kokoro_container_manager.py provision()`:
- Capture `instance_id`, `tenant_id`, `internal_port`, `volume_bind`, and a reference to the engine BEFORE the blocking `create_container()` call.
- Close the original DB session BEFORE `create_container()` so the idle pooled connection cannot time out during the long docker pull.
- Open three short-lived fresh sessions after `create_container()`: one to persist `container_id` + `base_url`, one for the final running/health status, and (on exception) one to write the error state.
- Mirrors the sessionmaker+filter-by-instance-id+tenant_id pattern in the Ollama fix.

Verified: cold Kokoro provision via the Hub wizard on a freshly-rebuilt local backend completes without the prior psycopg/docker-socket-proxy timeout; `tts-kokoro-*` container transitions to `running`; `/api/tts-providers/kokoro/status` returns healthy.

### Fresh-install regression sweep — BUG-662/663/664/665 closed + BUG-666 surfaced (2026-04-20)

Four open bugs from the 2026-04-20 Ubuntu VM fresh-install audit closed in one pass, plus one new bug surfaced by a newly-added Hub API-key validation regression test.

**BUG-662 (High) — Fresh install on stock Docker 28.2.2 + missing buildx.**
- `install.py` probes `docker buildx version` in `check_prerequisites()` and stores a `self.buildx_available` flag. When False, both `run_docker_compose()` and `build_additional_images()` strip `DOCKER_BUILDKIT=1` / `COMPOSE_DOCKER_CLI_BUILD=1` from the child env so Docker Compose falls back to the legacy inline builder and `docker build` for the WhatsApp MCP + toolbox images succeeds.
- `backend/containers/Dockerfile.toolbox` drops the `# syntax=docker/dockerfile:1.4` parser directive and converts all five `RUN --mount=type=cache,target=...` blocks to plain `RUN` with `mkdir -p /tmp/pd-cache` prepended, so the ProjectDiscovery download paths exist under the legacy builder.

**BUG-663 (High) — Cold Ollama auto-provision failed on first wizard run.**
- `backend/services/ollama_container_manager.py` `provision()` closes the DB session BEFORE the blocking `create_container()` (which can run `docker pull` for up to 20 min) and reopens a fresh short-lived session afterwards to write `container_id` + `base_url`. Eliminates the `psycopg2.OperationalError: server closed the connection unexpectedly` mid-pull failure family.
- `backend/api/routes_provider_instances.py` gates `_background_test_instance` to skip when `is_auto_provisioned and not base_url`, so the auto-test no longer fires during provisioning with a null base URL and falls through to `host.docker.internal:11434` connection-refused on Linux.
- `backend/services/provider_instance_service.py` adds a thread-safe cached `_resolve_ollama_host()` helper (tries `host.docker.internal`, falls back to `172.17.0.1` — Docker default-bridge gateway — on Linux hosts without `host-gateway`) and a lazy `get_vendor_default_base_url(vendor)` accessor. `VENDOR_DEFAULT_BASE_URLS["ollama"]` is now `None` at module-import time so no DNS call can block backend startup. `backend/agent/ai_client.py` and `backend/services/model_discovery_service.py` switched to the lazy accessor.

**BUG-664 (Medium) — Hub still called the removed `/api/services/kokoro/status` (HTTP 410 noise).**
- `frontend/lib/client.ts` removed `getKokoroStatus()` and `startKokoro()`.
- `frontend/app/hub/page.tsx` removed `fetchKokoroContainerStatus`, `handleStartKokoro`, `handleStopKokoro`, the `kokoroActionLoading` / `kokoroContainerStatus` state + setters, and the legacy-panel Start/Stop toggle. The legacy panel now shows a binary "Online" / "Offline" status sourced exclusively from `/api/tts-providers/kokoro/status`. Per-tenant Kokoro lifecycle lives in the main per-tenant card (v0.7.0).
- `backend/api/routes_services.py:71-80` (HTTP 410 Gone for `/api/services/kokoro/status`) intentionally retained as a regression canary for any external caller still pointing at the removed path.

**BUG-665 (Critical) — BUG-588 regression: QueuePool exhaustion + idle-in-transaction partial outage.**
- `backend/services/channel_health_service.py` `_handle_transition` now uses `with self._db_session_scope()` for both the audit and persist sessions, with all `await` calls and `asyncio.create_task(...)` moved AFTER both `with` blocks exit so the pool slots are released before async suspension.
- `backend/services/mcp_server_health_service.py` `_reconnect_server` splits into three short-lived scoped sessions (pre-validate → network call → record result). Timeout reduced from 30s to 10s on the health-loop speculative reconnect to bound worst-case pool hold. Added an end-of-`_monitor_loop` `pg_stat_activity` idle-in-transaction probe that updates a Prometheus gauge.
- `backend/db.py` `pool_recycle` dropped from 1800s → 300s. Registered SQLAlchemy pool `checkout`/`checkin` event hooks feeding a new `tsn_db_pool_checked_out` gauge.
- `backend/services/metrics_service.py` registers `tsn_db_pool_checked_out` + `tsn_db_idle_in_transaction` gauges under `METRICS_ENABLED`.
- Verified via breadth-smoke (75 concurrent API calls): `idle_in_transaction` stayed at 1, `tsn_db_pool_checked_out` stayed at 1.0, zero QueuePool timeouts in backend logs over 5 min.

**BUG-666 (Medium) — OPENED by the regression's new Hub API-key validation test.** The Hub Tool-API Edit/Save path writes the submitted key to the backend and immediately marks the card "Active" without validating against the provider. A bogus key like `bogus-key-for-regression-test-12345` round-trips silently; the user discovers it only on first live call. Scope-separated from this PR — tracked for the next sprint.

**Regression evidence:** Phase-5 in-place full regression green on the local stack: 28/29 tests passing in `backend/tests/test_api_v1_e2e.py` (1 pre-existing flaky test unrelated to this work — `test_list_agents_shows_description` 409 name collision from second-level `int(time.time())` uniqueness), 75-call concurrent breadth smoke clean, Playwright browser sweep green for Dashboard / Hub / Add Integration wizard (all 6 provider paths: Brave / Tavily / SerpAPI / SearXNG auto-provision / Google Flights / Amadeus) / legacy Kokoro panel binary state. Evidence under `output/playwright/bugfix-phase5-regression/`. Ubuntu VM fresh install + local fresh install + restore regressions pending as separate validation workstreams.

### Gemini 3.x preview models + Gemini TTS provider (2026-04-20, v0.6.0 addendum)

Adds first-class support for Google's Gemini 3.x preview line across every wizard,
picker, pricing table, and skill config surface. Folded into v0.6.0 since the
release has not been publicly announced yet.

**New LLMs** (already listed in `PREDEFINED_MODELS`, now wired into pricing + UI):

- `gemini-3-flash-preview` — flagship Flash for agents; first Flash-tier with
  native `computer_use` tool support. 1M input / 65K output context.
- `gemini-3.1-flash-lite-preview` — cheapest 3.x multimodal tier. Same 1M/65K
  context; drops Live API, adds Maps grounding.

**New TTS provider** — `gemini-3.1-flash-tts-preview` as the 4th TTS backend
alongside OpenAI, Kokoro, and ElevenLabs:

- Registered as `"gemini"` in `TTSProviderRegistry` with status `preview`.
- Uses standard `generateContent` with `response_modalities=["AUDIO"]` + a
  `SpeechConfig` block. 30 prebuilt voices (Zephyr, Puck, Charon, Kore, …).
- Reuses the tenant's existing Gemini API key (no new credential flow).
- Wraps Google's raw 24 kHz / 16-bit / mono PCM response in a WAV container
  using stdlib `wave` before persisting — the skill layer always gets a
  playable `.wav` file path.
- Implements the documented retry for the preview-quirk where the model
  occasionally returns text tokens instead of audio (up to 2 retries).
- No per-tenant container needed — pure API call.

**Image skill** — adds `gemini-3.1-flash-image-preview` as a new option on
`ImageSkill.SUPPORTED_MODELS` (alongside the existing `gemini-2.5-flash-image`
and `gemini-3-pro-image-preview`). Pricing seeded in `MODEL_PRICING`.

**Wizards updated** (per directive — "all affected wizards must be updated"):

- **Setup Wizard** (`frontend/app/setup/page.tsx`) — 3.x previews prepended to
  Gemini fallback model list.
- **Playground ConfigPanel** (`frontend/components/playground/ConfigPanel.tsx`) —
  new 3.x entries in `MODEL_OPTIONS` + pricing table.
- **Audio Agents Wizard** (`frontend/components/audio-wizard/`) — Gemini provider
  card with "Preview" badge; new `GEMINI_VOICES` dropdown (30 voices); speed
  slider hidden for Gemini; format locked to WAV.
- **Agent Wizard → Step Audio** (`frontend/components/agent-wizard/steps/StepAudio.tsx`) —
  Gemini wired through the shared `AudioProviderPicker` + `AudioVoiceFields`.

**Backend**:

- `backend/analytics/token_tracker.py` — pricing rows for
  `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`,
  `gemini-3.1-flash-tts-preview`, `gemini-3.1-flash-image-preview` + matching
  OpenRouter aliases. All marked with `TODO confirm` pending Google's pricing
  announcement.
- `backend/agent/ai_client.py` (`_call_gemini`) — default
  `generation_config.max_output_tokens` now lifts to **65,536** when the model
  name starts with `gemini-3-` or `gemini-3.1-` (vs. 8,192 on 2.x), matching
  the 3.x Flash context window.
- `backend/hub/providers/gemini_tts_provider.py` — new provider class.
- `backend/hub/providers/tts_registry.py` — registers the new provider.
- `backend/agent/skills/image_skill.py` — `SUPPORTED_MODELS` extended.

**Playground ConfigPanel polish** (post-QA, 2026-04-20):

- Chat-model dropdown now filters out TTS-only models (anything ending in
  `-tts-preview` or `-tts`), so `gemini-3.1-flash-tts-preview` no longer
  appears as a selectable chat model — it would fail at call time since the
  model only emits audio.
- Instance-sourced model IDs are now enriched with friendly labels from
  `MODEL_OPTIONS` when a match exists (e.g. `gemini-3-flash-preview` renders
  as "Gemini 3 Flash (Preview)" instead of the raw ID). Unknown model IDs
  still fall back to the raw ID so new models surface without code changes.

**Regression evidence** (2026-04-20):

- `gemini-3-flash-preview` text chat via `/api/v1/agents/{id}/chat` → 200,
  response `"PONG-3-FLASH"`, 6.9s.
- `gemini-3.1-flash-lite-preview` text chat → 200, response `"PONG-31-LITE"`,
  2.1s.
- Direct Gemini TTS synthesize with `voice=Zephyr` → success, 213 KB output,
  valid RIFF/WAVE header (`b'RIFF\\xa4@\\x03\\x00WAVE'`).
- `ImageSkill.SUPPORTED_MODELS` introspection confirms all three image
  models (including the new `gemini-3.1-flash-image-preview`) appear in both
  the MCP tool definition enum and the skill config schema.
- Browser QA (Playwright): Audio Agents Wizard Step 2 renders all four
  provider cards; Step 3 for Gemini renders 30 voices, speed slider hidden
  with explanatory note, format locked to WAV.

### Tavily search provider (2026-04-20)

- New `TavilySearchProvider` wrapping `https://api.tavily.com/search`.
  Registered in `SearchProviderRegistry` as `tavily` (`requires_api_key=True`).
- Wizard: removed the "Coming soon" placeholder on Tavily — the provider step
  now saves the key and the runtime adapter actually uses it.
- Motivation: Hub card previously showed "Active" for any saved API key row
  even when no backend adapter existed, which was misleading. With the adapter
  shipped, "Active" is now truthful for Tavily.

### Add Integration wizard + SearXNG auto-provisioning (2026-04-20)

Addresses a post-PR-#24 regression where the Hub > Tool APIs "Setup Web Search" button
only covered three search providers (Brave/Tavily/SerpAPI) even though the same tab
exposed Amadeus and Google Flights cards. Also removes a hardcoded-secret/default-
container security issue shipped in PR #24.

**What changed:**

- **Hub > Tool APIs — generic "Add Integration" wizard.** Renamed `SearchIntegrationWizard`
  → `AddIntegrationWizard`. The wizard is now category-aware (Web Search / Travel) and
  walks users through the right flow per provider — API key for Brave/Tavily/SerpAPI/
  Google Flights, auto-provisioning toggle for SearXNG, or API key + secret + env for
  Amadeus. The "Configure" button on SearXNG / Amadeus / Google Flights cards now routes
  through the wizard with the provider pre-selected. Other Tool APIs still open the
  legacy API-key modal.
- **SearXNG now auto-provisioned per-tenant** (mirrors Kokoro/Ollama).
  New `SearxngInstance` DB table + `SearxngContainerManager` allocate a port in
  6500–6599, pull `ghcr.io/searxng/searxng:latest`, generate a fresh `secret_key`
  via `secrets.token_urlsafe(48)`, and inject a tenant-specific `settings.yml`
  into `/etc/searxng/` via Docker `put_archive` (no host-file mount). Full CRUD
  endpoints under `/api/hub/searxng/instances`. Startup reconcile hooked up
  alongside Kokoro/Ollama.
- **Shipped compose service removed.** `searxng` service block and `searxng-cache`
  volume removed from `docker-compose.yml`. The repo-root `searxng/settings.yml`
  (which shipped with a hardcoded `secret_key: "tsushin-searxng-local-secret-change-me"`)
  is deleted. Migration `0043` best-effort removes any lingering compose-managed
  `<stack>-searxng` container (matched by label `tsushin.lifecycle=compose`).
- **Existing external-SearXNG users preserved.** Migration `0043` backfills a
  `SearxngInstance(is_auto_provisioned=False)` row for every tenant that had an
  `ApiKey('searxng')` configured, then soft-deactivates the ApiKey. The provider
  resolver also keeps a legacy ApiKey fallback so the user can reconfigure
  through the wizard at their leisure.
- **Frontend color maps updated** — `SkillProviderNode.tsx` and
  `BuilderSkillProviderNode.tsx` gained `searxng` (teal) and `tavily` (purple)
  entries so Agent Studio/Watcher shows the right colors instead of the default
  slate.
- **Auto-link** — the wizard's agent-linking step (step 4) now category-aware:
  web_search providers upsert `AgentSkill.web_search.config.provider`; travel
  providers use `PUT /api/flight-providers/agents/{id}/provider`.
- **Tests + docs** — backend unit tests for the search registry and the SearXNG
  container manager settings rendering/port allocation. Documentation section
  updated.

**Port range allocation summary:**

| Service | Port range |
|---------|------------|
| Kokoro TTS | 6600–6699 |
| Ollama | 6700–6799 |
| SearXNG (new) | 6500–6599 |

## v0.6.0-patch.5 (2026-04-20)

Multi-day stabilization release rolling up the v0.7.0-preview guided-wizard work, a massive bug-remediation campaign, independent-review follow-ups, and a VM fresh-install regression fix. Scope is stabilization + feature-completion on the v0.6.0 line, not a new minor release — headline features (agents, memory, flows, Sentinel) are unchanged; this patch ships the full setup-wizard track, a 51-bug remediation sweep, and six follow-up regression fixes caught by independent reviewers.

**Highlights**
- Full guided-wizard suite across Gmail, Google Calendar, Shell Beacon, Sandboxed Tools, Search (Brave/Tavily/SerpAPI), and Audio Agents (Kokoro TTS + Whisper transcript). Reusable primitives (`CopyableBlock`, `GoogleAppCredentialsStep`, `BeaconInstallInstructions`) extracted for future wizards.
- Tenant-isolation hardening of `/api/skill-integrations` and `/api/skill-providers/{skill_type}` (BUG-608/609).
- 51 bugs closed in a single parallel-group campaign (Groups F test-infra, A Sentinel, B Flows, C Playground, D Install/Infra, E Security/RBAC/SSO/UX).
- 6 concrete follow-up regressions caught and closed by post-sprint independent review (gate-binding spread overwrite, SSO login 400, WS default-tenant bypass, beacon auth exception swallow, stale ORM ref, localStorage cross-tenant leak).
- VM fresh-install fix (BUG-653b) — IP-only HTTPS now works via port-only `:443` site matcher so curl and mainstream browsers (which don't send SNI for IP-literal hosts per RFC 3546) complete the handshake.

**Regression** — 319+ assertions, 13/13 phases green, 0 ship-blockers. See the detailed per-group entries below.

### Ubuntu VM fresh-install re-audit (2026-04-20)

Completed a second UI-first/API regression audit against a disposable Ubuntu 24.04 VM clone (`~/tsushin-v060-audit-20260420`) using the interactive installer, self-signed HTTPS on `https://10-211-55-5.sslip.io`, headed Playwright, direct backend truth checks, and an exported/generated API v1 client. The install path and `/setup` both succeeded. Hosted-provider setup passed for Gemini, OpenAI, Anthropic, and Vertex AI plus Brave Search, Tavily, and SerpAPI. The pass also revalidated working baseline behavior for Watcher graph glow, knowledge-base grounding, fact CRUD, isolated/shared memory, Sentinel/MemGuard detections, API v1 OAuth + direct-key auth, sync/async chat, `/api/v1/openapi.json`, generated-client auth, and `/api/v2/agents/graph-preview`.

This session was audit-only: no product code changed. It revalidated two pre-existing open findings — BUG-538 (`tsushin-toolbox:base` still absent at runtime on the fresh VM) and BUG-592 (`GET /api/v2/agents/` still returns 500) — and logged four new internal findings: BUG-662 (stock Docker 28.2.2 missing/broken buildx leaves WhatsApp MCP and toolbox images unavailable during install), BUG-663 (cold Ollama auto-provision still fails on the first wizard run), BUG-664 (Hub still calls the removed `/api/services/kokoro/status` endpoint and emits 410 noise), and BUG-665 (BUG-588 regression: late-session QueuePool / `idle in transaction` partial outage during moderate audit breadth). Because BUG-665 wedged backend truth endpoints mid-run, the remaining custom-skill, MCP, webhook, shell-registration, and template-flow creation checks were blocked without manual intervention. The deployment playbook now includes a new post-breadth stability checkpoint so future audits fail explicitly when this class of regression reappears.

### BUG-653b — IP-only HTTPS handshake fix (2026-04-20)

After the 2026-04-19 VM regression pass, curl / browser HTTPS against IP-only self-signed installs still failed with `TLSv1 alert internal error` even though `openssl s_client -servername <IP>` correctly served the Caddy-internal cert with an IP SAN. Root cause: curl (and mainstream browsers) do NOT send SNI for IP-literal hosts per RFC 3546 §3.1, so with a domain-matching site block `{IP} { tls internal ... }` Caddy had no way to pick a site on SNI-less connections and aborted the handshake.

`install.py` now emits a port-only `:443 { tls internal ... }` site block for IP-literal bindings. Port-only matching serves the internal cert on any TLS connection regardless of SNI, and Caddy's internal CA automatically issues the cert with an IP SAN for the bound IP. Hostname installs are unchanged — they keep the existing `default_sni {domain}` + domain-matching block. `caddy/Caddyfile.template` docstring updated with both patterns side-by-side.

### Bug-remediation follow-up regression patch (2026-04-20)

An independent post-sprint review surfaced **six concrete regressions** introduced by the 2026-04-19 remediation campaign. All six were fixed in commit `ba751a2`.

- **Flow gate-binding silent neutralization** (`backend/flows/flow_engine.py _build_step_context`): the dict literal `{"output": output, **output}` let the `**output` spread overwrite the canonical dict alias with whatever the handler emitted — a string for Slash, Skill, BrowserAutomation, and Message handlers. The BUG-632 fix was silently undone for those four handler types. Reordered to `{**output, ..., "output": output}` so the dict alias wins, and re-asserted the top-level bookkeeping fields (`position`, `name`, `type`, `status`, `error`, `execution_time_ms`, `retry_count`) after the spread so a misbehaving handler can't clobber them either.
- **Primary tenant SSO login broken** (`frontend/app/auth/login/LoginClient.tsx`): `handleGoogleSignIn()` called `loginWithGoogle()` with no arguments. After the BUG-647 guard enforced explicit scope, every unauthenticated user hitting the public login page got `400` on click. Now passes `{platform: true}` — the correct scope per the backend docstring ("Required for global-admin flows and any login page not bound to a tenant"). `AuthContext.loginWithGoogle` type signature + `api.getGoogleAuthURL()` client method extended to accept the `platform` flag.
- **Stale tenant-less JWTs bypassed the tenant-hopping guard** (`backend/api/shell_websocket.py`): pre-multi-tenant tokens without a `tenant_id` claim were falling back to `tenant_id = "default"` and then carved out of the guard (`tenant_id not in ("default",)`). Any stale JWT could subscribe to any tenant's shell/beacon feed until it expired naturally. Now rejects such tokens outright with `4003 "Missing tenant claim — please re-login"` and the `"default"` carve-out is removed.
- **Beacon auth tenant-check silently fell through on exception** (`backend/api/shell_websocket.py authenticate_beacon`): the deleted_at / emergency_stop check was wrapped in a bare `except Exception` that logged and continued to the happy path. Security-critical checks must never default-allow on error. Now fails CLOSED with an explicit `auth_failed` response and `return None` on any tenant-state-check exception.
- **Ollama error-path used stale ORM reference** (`backend/services/ollama_container_manager.py provision`): the except branch referenced `instance.id` after `db.close()` — technically `DetachedInstanceError` territory even though loaded PKs usually survive in `__dict__`. Now captures `err_instance_id` + `err_tenant_id_capture` before the close (mirroring the happy-path pattern at line 260) and filters by both columns on the fresh session for tenant safety.
- **Cross-tenant `lastThreadId` leak** (`frontend/app/playground/page.tsx`): when `initializeThreads` detected a stale `?thread=` param that didn't belong to the current agent's thread list, it stripped the URL param but left `localStorage['tsushin.playground.lastThreadId']` pointing at the stale id. On a shared browser that id bled across agent switches and (in the worst case) across tenants. Now clears the localStorage key alongside the URL param.
- **Fact-extractor parameter rename for security clarity** (`backend/agent/memory/fact_extractor.py`): the parameter named `had_trusted_user_turn` actually carries "had trusted non-user turn" (assistant/system role present). Renamed to `had_trusted_non_user_turn` throughout — no behavior change, pure readability / correctness-of-reasoning fix so the security invariant matches the variable name.

Post-follow-up regression: 319+ assertions across 7 suites still green (sentinel_fast_benchmark 248/248 with zero false positives; group-level pytest suites 37+ pass standalone; UI-first API + source regression audit GREEN across all 10 checkpoints).

### Massive Bug Remediation Campaign — summary (52 open → 2 deferred) (2026-04-19)

A full triage + debate + group-fix sweep of every open entry in `BUGS.md`
at the start of the sprint (52 bugs). Triage closed 5 as false-positives
after code audit (BUG-598/622/623/659/660), rescoped 4 where the
description didn't match the real root cause (BUG-642/643/647/661), and
shipped 51 fixes across six parallel groups (F, A, B, C, D, E).

Two bugs remain deferred (BUG-616 — test-harness, not backend seed;
BUG-657 — referenced route file does not exist; wizard status lives in
`auth_routes.py` which is already hardened). All other open bugs closed
or fixed.

Post-sprint regression (319+ assertions across 7 suites):
- `sentinel_fast_benchmark.py` — 248/248, 0 false positives across all
  4 aggressiveness levels.
- `backend/tests/test_api_v1_e2e.py` — 28/29 (1 test-isolation case
  pre-dates this sprint, tracked under BUG-638 fixture cleanup helper).
- `backend/tests/test_playground_memory_regressions.py` — 6/6.
- `backend/dev_tests/test_sentinel_rescoped_bugs.py` — 13/13.
- `backend/dev_tests/test_flows_group_b.py` — 9/9.
- `backend/dev_tests/test_group_e_security.py` — 9/9.
- `backend/dev_tests/test_group_d_infra.py` — 6/6 (+2 host-only skipped).
- WhatsApp round-trip: tester → bot → tester verified end-to-end on the
  live stack (02:36:48 ping → 02:36:52 reply).
- Sandboxed-tool API: 200 OK for `/api/v1/agents/17/chat` with a tool
  command.
- Post-regression container logs: no new backend/frontend ERROR lines
  (only pre-existing env noise: Qdrant DNS when Qdrant isn't configured,
  Vertex AI credential gaps for unconfigured providers).

### Sentinel / Memory hardening — Group A (BUG-642/643/644/646/656/661) (2026-04-19)

Critical prompt-injection hardening: the fact extractor was promoting
adversarial "remember this" user turns (including credential-poisoning
and behavior-prefix payloads) into persistent, high-confidence long-term
facts whenever Sentinel was in `detect_only` mode or missed the attack.
Sentinel itself was empirically under-blocking at level-1 and was
a complete no-op without an LLM provider key (fail-open for `detect_only`,
fail-closed for `block`). Three-layer fix:

- **BUG-642 + BUG-661** — `backend/agent/memory/fact_extractor.py` gains
  `_sanitize_conversation_for_extraction` (drops user turns matching
  injection markers before the LLM extractor sees them) and
  `_filter_untrusted_facts` (refuses any `instructions`-topic fact
  unless a trusted assistant/system turn exists, drops facts whose
  value or context looks injection-like, caps any surviving
  `instructions` fact at confidence 0.9). User content is treated as
  quotation, not instruction.
- **BUG-643 + BUG-656** — new `backend/agent/sentinel/heuristics.py` +
  `SentinelService._heuristic_floor_result`, wired into `_analyze_unified`
  BEFORE the LLM call AND in the LLM-error fallback. Provider-independent
  regex floor covering `prompt_injection`, `agent_takeover`,
  `memory_poisoning` (credential + behavior-prefix), `agent_escalation`,
  `vector_store_poisoning`, `shell_malicious`, `browser_ssrf`. Fires
  in block / warn_only / detect_only modes, respects per-profile
  detection toggles, logs with `llm_provider="heuristic"`. Zero LLM
  key required — Sentinel is no longer a no-op on LLM-less installs.
- **BUG-644** — `UNIFIED_CLASSIFICATION_PROMPT[1]` and `[3]` in
  `backend/services/sentinel_detections.py` rewritten. Level-1 tightened
  with explicit MUST-block phrasings per family; level-3 rebuilt as a
  strict superset of level-1, always catching every level-1 trigger
  plus the three aggressiveness regressions (`attack-ssrf`,
  `attack-memory-cred-a`, `attack-vs-poisoning`). Benign carve-outs
  (preferences, roleplay games, educational questions) preserved.
- **BUG-646** — `frontend/app/playground/page.tsx` +
  `frontend/components/playground/ExpertMode.tsx` now render a
  distinctive red-bordered inline card with the threat family pill
  and full `threat_reason` when Sentinel blocks a turn, instead of
  showing only a generic error state. Also handles the legacy
  "🛡️ Your message was blocked…" prefix in persisted history.

Regression guard: `backend/dev_tests/test_sentinel_rescoped_bugs.py`
(13/13 passing).

### Test infrastructure — Group F (BUG-638/639/640/641) (2026-04-19)

- **BUG-641** — `backend/Dockerfile` now installs
  `backend/requirements-dev.txt` (pytest, pytest-asyncio, pytest-cov)
  into `/opt/venv` in the builder stage so the runtime image has the
  full test harness. `docker exec tsushin-backend python -m pytest
  --collect-only tests/` now collects 270 tests without module-not-found.
- **BUG-640** — `backend/tests/test_sentinel_detection_mode_fix.py`
  imports `models_rbac` so `User` is registered on `Base.metadata`
  before `ApiClient.created_by` FK resolution, and narrows
  `db_engine` to the Sentinel-only tables so SQLite doesn't compile
  Postgres-only JSONB columns. 10 tests collect; 10 tests pass.
- **BUG-639** — `test_scheduler_message_with_no_threat_llm` now sets
  `timeout_seconds=5.0` and `max_input_chars=5000` on the MagicMock
  so `asyncio.wait_for`/prompt slicing no longer crash on
  TypeError.
- **BUG-638** — new `backend/dev_tests/cleanup_reg_fixtures.py` helper
  + `test_fixture_cleanup.py` — resolves the tenant by
  email/id/slug, finds agents whose linked `Contact.friendly_name`
  starts with `reg-`, respects an `--older-than-hours` guard, and
  cascades agent + contact deletion. Dry-run by default, `--apply`
  to commit.

### Playground & Studio state/threading — Group C (BUG-597/600/617/618/619/620/621/625/645) (2026-04-19)

Playground UX hardening sprint focused on state persistence, race
conditions, and misleading graph affordances.

- **BUG-597** — Agent Builder cold-load blank-canvas fixed via a React
  Flow overlay spinner in `AgentStudioTab.tsx` that holds until
  `builder.nodes.length > 0` for the selected agent.
- **BUG-600** — A2A Network ghost peer nodes no longer dropped. Instead
  of `commEnabledAgents.filter`, `useAgentBuilder.ts` iterates
  `peerIds` directly and synthesizes `"Agent #N"` placeholders when
  the comm-enabled payload omits a peer.
- **BUG-617** — Rapid double-click on "+ New Thread" now produces exactly
  one thread. `handleNewThread` gains a `creatingThreadRef` in-flight
  guard; second click is dropped until the first `createThread`
  request settles.
- **BUG-618** — Hard refresh no longer loses the active Playground
  thread. `activeThreadId` hydrates from `?thread=<id>` then
  `localStorage['tsushin.playground.lastThreadId']`; a dedicated
  effect mirrors state back via `window.history.replaceState`
  without triggering a client remount.
- **BUG-619** — Project-scope thread filter now applied. `ExpertMode.tsx`
  computes `scopedThreads` client-side when `projectSession?.is_in_project`
  and the Threads badge reflects the scope.
- **BUG-620** — `[WebSocket] Connection error: Event` log noise quieted.
  `websocket.ts` onerror now logs structured diagnostics
  (`readyState`, `readyStateLabel`, `url`, `type`) once per
  close-cycle as `warn`; clean closes (code 1000) are `debug`.
- **BUG-621** — Watcher Graph-Glow no longer lights every skill-category
  edge. `GraphCanvas.tsx` builds `categorySkillTypesByNodeId` and only
  glows Agent→Category edges when the invoked skill's type matches one
  of that category's skill types.
- **BUG-625** — Thread context menu no longer opens on whole-row click.
  Row `onClick` ignores events originating inside `[data-no-row-click]`;
  kebab is `opacity-0 group-hover:opacity-100`; right-click adds
  explicit `onContextMenu` for the menu.
- **BUG-645** — "Thread N not found" crash replaced with self-healing
  WS `onError` handler: detects the specific pattern, drops the stale
  id, clears URL/localStorage, reloads the thread list, suppresses the
  error banner. User can retry immediately.

### Security / RBAC / SSO / UX — Group E bug sprint (BUG-599/601/602/610/611/612+613/614/615/624/626/636/647/648) (2026-04-19)

Remediation sprint for the Group E audit findings (WS auth bypass, RBAC UI
gates, SSO scoping, hub 500, schema gap, onboarding/guide UX). Regression
guard at `backend/dev_tests/test_group_e_security.py` (9 live tests).

- **BUG-612 + BUG-613** (HIGH) `/ws/shell/status` decoded the JWT but never
  verified the User row. A deactivated or tombstoned user still held a valid
  token and could keep receiving live beacon/status events. `shell_websocket.py`
  now looks up the `User`, asserts `is_active=True` + `deleted_at IS NULL`,
  rejects tenant-mismatched JWTs, and requires at least one `shell.*`
  permission before sending `auth_success` (otherwise WebSocket close 4003).
  The sister `/ws/beacon/{integration_id}` handler also now rejects beacons
  whose tenant is deleted or in emergency stop.
- **BUG-615** (HIGH) `GET /api/hub/integrations?refresh_health=true` was 500ing
  across all roles when a polymorphic `HubIntegration` row pointed at a
  deleted child (ObjectDeletedError on `hub.type` attribute access). Every
  per-integration iteration is now wrapped in try/except; guarded `getattr`
  calls harvest what can be surfaced and a degraded `{status:"error"}` row is
  emitted instead of 500ing the whole list.
- **BUG-614** (MEDIUM) Playground debug endpoint joined
  `sandboxed_tool_executions` on a `tenant_id` column that did not exist in
  the DB schema. Added Alembic migration `0042_add_sandboxed_tool_exec_tenant_id`
  (nullable `VARCHAR(50)` + index, backfilled from
  `agent_run.agent_id → agent.tenant_id`), added the column to the
  `SandboxedToolExecution` ORM model, and threaded `self.tenant_id` into
  `SandboxedToolService.execute_command` insertion.
- **BUG-647** (HIGH) SSO `/api/auth/google/authorize` silently fell back to
  "first tenant with SSO enabled" — a cross-tenant leak. New explicit
  `platform=true` query param routes to `GlobalSSOConfig`; callers must now
  pass either `tenant_slug=<slug>` OR `platform=true` (never both, never
  neither) or receive a 400.
- **BUG-648** (MEDIUM) Tenant invitation list view never returned
  `invitation_link` (raw tokens are not stored). New admin-only
  `POST /api/team/invitations/{id}/resend-link` endpoint rotates the
  invitation token, extends the expiry by 7 days, and returns the
  fresh link WITHOUT triggering a duplicate email (the existing
  `/resend` endpoint continues to email).
- **BUG-610** (HIGH) Read-only users saw mutation UI on Hub / Agents / Flows.
  Added `hasPermission('agents.write' | 'flows.write' | 'hub.write')` gates
  around every create / edit / delete / toggle / bulk-action control, plus
  a top-of-page read-only banner on Hub.
- **BUG-611** (MEDIUM) Settings overview hid Billing from owners — the
  overview card gated on `billing.manage` but the billing subpage itself
  gated on `billing.write`. Aligned both to `billing.write`.
- **BUG-636** (MEDIUM) Flow editor edit-then-execute path produced no run.
  `handleRunFlow` now re-fetches the latest saved flow before execute so a
  just-edited flow is executed against its fresh definition, and the edit
  modal's `onSuccess` awaits `loadData()` before closing the modal.
- **BUG-624** (LOW) `UserGuidePanel` persisted in the DOM after dismissal
  with only `translate-x-full`; assistive tech still saw a dialog role. Added
  `aria-hidden` + `visibility: hidden` to both the backdrop and panel when
  `isOpen` is false.
- **BUG-626** (LOW) Onboarding tour re-appeared after Skip Tour if the
  provider remounted. `handleGuideClose` now treats `localStorage` as the
  source of truth — any persisted completion marker blocks restart
  unconditionally and re-syncs `tourDismissedRef`.
- **BUG-599** (MEDIUM) User Guide Escape key conflicted with Studio's
  fullscreen Esc handler. UserGuide's handler now calls
  `stopImmediatePropagation` in addition to `stopPropagation` so a single
  Esc press cleanly closes the guide without also collapsing Studio.
- **BUG-601** (MEDIUM) Palette items were draggable even when attached, but
  there was no drop-to-detach handler — the tooltip promised behavior that
  didn't exist. Attached items are now `draggable={false}` and the tooltip
  truthfully says "Double-click to detach".
- **BUG-602** (MEDIUM) Studio's "Create new agent" was a parallel
  implementation that produced persona-less / tone-less agents vs. the main
  `/agents` modal. Quick-create now emits the same explicit-null payload
  shape as the main modal, and a new footer link routes users who need
  persona / tone / keywords to `/agents?create=1` (AgentsPage auto-opens the
  create flow from that query param).

Touched files: `backend/api/shell_websocket.py`, `backend/api/routes_hub.py`,
`backend/api/routes_team.py`,
`backend/alembic/versions/0042_add_sandboxed_tool_exec_tenant_id.py` (new),
`backend/models.py`, `backend/agent/tools/sandboxed_tool_service.py`,
`backend/auth_routes.py`, `backend/auth_google.py`,
`frontend/app/hub/page.tsx`, `frontend/app/agents/page.tsx`,
`frontend/app/flows/page.tsx`, `frontend/app/settings/page.tsx`,
`frontend/components/UserGuidePanel.tsx`,
`frontend/contexts/OnboardingContext.tsx`,
`frontend/components/watcher/studio/StudioAgentSelector.tsx`,
`frontend/components/watcher/studio/palette/PaletteItem.tsx`.

### Agent Creation Wizard — guided multi-step flow (2026-04-19)

Creating an agent was a single modal with ~12 fields — powerful for experts, intimidating for newcomers. New **Agent Creation Wizard** branches upfront on **Text / Audio / Hybrid** and progressively discloses only the steps that matter for the chosen type. Guided is the default; Advanced (existing single-form modal) remains available for power users via a per-user toggle.

**What's new**

- **Guided mode.** 7–9 steps (varies by type): Type → Basics → Personality → [Voice for audio/hybrid] → Skills → Memory → Channels → Review → Progress. Circular-checkmark step indicator, per-step validation, Back-nav preserves draft.
- **Type branching.** Text agents skip the Voice step and hide audio-only skills. Audio & Hybrid reuse the extracted `AudioProviderPicker` / `AudioVoiceFields` from the Audio Agents Wizard — single source of truth for voice UX.
- **Advanced mode preserved.** Existing `frontend/app/agents/page.tsx` modal is unchanged in behavior; it now shows a "Switch to Guided" link and reads a pre-filled draft from `AgentWizardContext` when the user switched mid-flow.
- **Mode preference.** Per-user `localStorage['tsushin:agentWizardMode']` — defaults to `guided`. Both directions persist the user's choice on switch.
- **Chained provisioning.** `useCreateAgentChain` orchestrates: contact resolve → `createAgent` → `updateAgent` (memory/channels/vector store) → per-skill fan-out → custom skills → Kokoro TTS provisioning + voice binding (for audio/hybrid). On partial failure after the agent row is created, the wizard keeps the agent and surfaces the failing stage rather than rolling back.
- **Deep-link on success.** Progress step's primary CTA navigates to `/playground?agentId=<id>` so the new agent is chattable immediately.

**Extracted shared modules**

- `frontend/components/audio-wizard/AudioProviderFields.tsx` — `AudioProviderPicker` + `AudioVoiceFields` (lifted from `AudioAgentsWizard` steps 2 & 3).
- `frontend/components/agent-wizard/hooks/useKokoroPolling.ts` — Kokoro container status polling (lifted from `AudioAgentsWizard`).
- `AudioAgentsWizard.tsx` refactored to consume both; behavior unchanged.

**Touched files.** `frontend/contexts/AgentWizardContext.tsx` (new), `frontend/lib/agent-wizard/reducer.ts` (new, pure), `frontend/components/agent-wizard/*` (new — AgentWizard shell + 9 step components + 2 hooks + defaults), `frontend/components/audio-wizard/AudioProviderFields.tsx` (new extraction), `frontend/components/audio-wizard/AudioAgentsWizard.tsx` (refactor — consumes extracted modules), `frontend/app/layout.tsx` (mount `AgentWizardProvider`), `frontend/app/agents/page.tsx` (Create button dispatches by mode; "Switch to Guided" link; pre-fill banner).

### Infra / install / observability — Group D bug sprint (BUG-649/650/651/652/653/654/655/658) (2026-04-19)

Remediation sprint for the Group D audit findings. Regression guard at
`backend/dev_tests/test_group_d_infra.py` (6 live tests + 2 host-only checks).

- **BUG-649** (HIGH) Ollama auto-provisioning failed on chat/provision due to a
  pooled DB connection held idle across a 60-120s health wait and silently
  dropped by Postgres. `OllamaContainerManager.provision` now explicitly
  `db.close()` before the health loop, runs a new `_wait_for_health_detached`
  against the captured `base_url`, and opens a fresh session to write back
  `container_status` / `health_status`.
- **BUG-650** (LOW) Provisioning errors wrote raw SQL snippets + 64-char
  container IDs into `health_status_reason`. New `_sanitize_health_reason`
  helper strips `[SQL: ...]`, SQLAlchemy background URLs, `psycopg2.*`
  wrappers, and long hex IDs before the text is persisted.
- **BUG-651** (LOW) `POST /api/tts-instances` with `auto_provision=true`
  briefly reported `is_auto_provisioned: false` in its 202 response. The route
  now calls `TTSInstanceService.mark_pending_auto_provision` to flip
  `is_auto_provisioned=True` + `container_status=provisioning` synchronously
  before kicking off the background worker.
- **BUG-652** (LOW) `POST /api/vector-stores {"vendor":"chroma", ...}`
  returned `400 Unsupported vendor: chroma`. Added `chroma` to
  `VectorStoreInstanceService.SUPPORTED_VENDORS` (remains absent from
  `AUTO_PROVISIONABLE_VENDORS` — chroma is the in-process default with no container).
- **BUG-653** (HIGH) Self-signed Caddy installs bound to bare IP literals
  broke external TLS handshakes because the generator emitted
  `default_sni localhost` (Caddy rejects IP literals in `default_sni`). For
  IP-literal binds the `install.py` generator now omits the `default_sni`
  directive entirely and lets Caddy auto-select; hostname binds keep
  `default_sni {domain}`.
- **BUG-654** (MEDIUM) `docker-compose.yml` declared `TSN_AUTH_RATE_LIMIT`
  twice, shadowing the `5/minute` default with an empty string. Removed the
  earlier duplicate.
- **BUG-655** (MEDIUM) Toolbox image build failed on aarch64 hosts because
  classic `docker build` never populates `TARGETARCH` in the Dockerfile, so
  the arch-aware lines silently pulled amd64 binaries on arm64. `install.py`
  now detects the host arch and passes `--build-arg TARGETARCH=arm64|amd64`,
  and emits a clearer warning + a ready-to-copy rebuild command when a build
  does fail.
- **BUG-658** (LOW) Installer SSL-proxy health check now fails fast after
  three consecutive TLS handshake errors (rather than burning all 20 attempts)
  and points the operator at BUG-653 as the likely root cause.

### Flows engine — Group B bug sprint (BUG-627..637) (2026-04-19)

Remediation sprint for the flows audit findings. Nine Group B bugs resolved in one commit; see `backend/dev_tests/test_flows_group_b.py` for the regression guard (9/9 passing).

- **BUG-627** (template credential pre-flight). `POST /api/flows/templates/{id}/instantiate` now runs `_check_required_credentials` against the tenant's `ApiKey` rows before building the flow. Missing credentials return `400 {error: "missing_credentials", missing_credentials: [...]}`. Pass `skip_credential_check: true` in params to bypass (integration tests).
- **BUG-628** (template detail endpoint). New `GET /api/flows/templates/{id}` returns the template summary plus best-effort `preview_steps` for UI previews.
- **BUG-629** (`StepType` vocabulary). `schemas.StepType` now exposes `custom_skill` and `browser_automation` so typed `POST /api/flows/create` accepts the full runtime vocabulary. Enum change is additive — `FlowNode.type` is stored as a string, no DB migration required. A runtime test asserts every `StepType` value has a handler registered.
- **BUG-630** (step_count / node_count alias). `FlowResponse` (v2), `FlowDefinitionResponse` (legacy), and the v1 summary dict now populate **both** `step_count` and `node_count`, mirrored via validators. Clients can migrate between legacy and v2 endpoints without field-name handling.
- **BUG-631** (empty-flow guard). Template instantiation refuses to persist a flow with zero steps (returns 500 with `error: template_produced_empty_flow`). Runtime also marks empty FlowRuns as `noop` (see BUG-637) as defence in depth.
- **BUG-632 / BUG-633** (Gate binding). `_build_step_context` now exposes the previous step's whole output dict under the literal key `output`, so Gate conditions bound with `field: "step_1.output"` resolve to actual data instead of literal `"null"`. Both programmatic and agentic gate modes benefit — the fix is at the context layer.
- **BUG-634** (Summarization auto-bind). `SummarizationStepHandler` now walks three layers to find a conversation `thread_id` when neither `thread_id` nor `source_step` is set: immediate previous step → earlier steps in the context dict → `ConversationThread.flow_step_run_id` DB lookup within the same FlowRun. Raw-text fallback only triggers when all three layers return nothing. The `output` dict (new in BUG-632) is NOT treated as source text, so summarization doesn't garbage-summarize step JSON.
- **BUG-635** (skill error surfacing). `SkillStepHandler` now includes a top-level `error` field on failure; the executor's `step_run.error_text` fallback reads `output.error → metadata.error → metadata.message → output.message → output.output (if str)` before landing on the generic message. Skill failures now carry actionable detail to the run UI.
- **BUG-637** (zero-step status). `run_flow` marks a FlowRun as `status=noop` (not `completed`) when `total_steps == 0 and completed_steps == 0 and failed_steps == 0`. Includes an `error_text` explaining the no-op.

**Touched files.** `backend/flows/flow_engine.py` (context builder, gate binding, skill/summarization handlers, run-completion status), `backend/api/routes_flows.py` (credential pre-flight, template detail endpoint, empty-step guard, FlowDefinitionResponse alias), `backend/api/v1/routes_flows.py` (FlowSummary / FlowDetailResponse alias), `backend/schemas.py` (`StepType` additions, `FlowResponse.node_count` mirror), `backend/dev_tests/test_flows_group_b.py` (new test suite, gitignored).

**Deferred.** BUG-636 (edit-then-execute from the flow editor) is a frontend concern in `frontend/app/flows/page.tsx` — deferred to Group E.

### Emergency Stop split into tenant + global scopes (2026-04-19)

The header emergency-stop toggle was a single control writing a **singleton** flag on `config.emergency_stop`. That made it a GLOBAL kill switch in practice — any tenant owner with `org.settings.write` could halt every tenant on the instance. Functional for defence, wrong for multi-tenant separation of concerns.

**What changed.** The control is now **two independent toggles**, one per scope:

- **Tenant stop** (`tenant.emergency_stop`, new column) — toggled by the logged-in tenant owner via `POST /api/system/emergency-stop` and `/api/system/resume`. Halts all channels/triggers for that tenant only (WhatsApp, Telegram, Slack, Discord, webhooks, API). Other tenants keep running. Permission: unchanged — still `org.settings.write`.
- **Global stop** (`config.emergency_stop`, existing column, now admin-only) — toggled by global admins via the new `POST /api/system/global-emergency-stop` and `/api/system/global-resume` endpoints guarded by `require_global_admin()`. Halts every tenant on the instance — reserved for platform-wide incidents.

**Enforcement.** All three existing ingress points now evaluate `Config.emergency_stop (global) OR Tenant.emergency_stop (this tenant)`:
- `backend/mcp_reader/filters.py` — `MessageFilter` gained a `tenant_id` kwarg; `watcher_manager.py` passes `instance.tenant_id` when constructing the filter. MCP-sourced WhatsApp/Telegram messages are dropped before routing.
- `backend/agent/router.py` — the existing router-level block now also reads `Tenant.emergency_stop` via `self.tenant_id`. Log lines are tagged `[EMERGENCY STOP:global]` vs `[EMERGENCY STOP:tenant]` so ops can attribute the halt.
- `backend/api/routes_webhook_inbound.py` — webhook inbound path reads `integration.tenant_id` and rejects with 503 when either flag is true.

All three fail-open on DB errors (unchanged behavior — a DB blip should not silently halt a tenant).

**Header UI** (`frontend/components/LayoutContent.tsx`). Two toggles in the top-right:
- Tenant toggle: green "Online" / red "Tenant Stopped". Tooltip names the tenant explicitly. Confirmation modal is red, titled "Tenant Emergency Stop", button "Stop This Tenant".
- Global toggle (visible only when `user.is_global_admin`): purple "Global" / amber "Global Stopped" + shield icon to telegraph system-wide scope. Confirmation modal is amber, titled "Halt ALL Tenants?", button "Halt Every Tenant".
- When a global stop is active, the tenant toggle is disabled with tooltip "Blocked by GLOBAL stop" — prevents a confused tenant owner from resuming into a no-op.
- Both toggles share the same `/api/system/status` poll (10s) which now returns `{ tenant_emergency_stop, global_emergency_stop, is_global_admin, tenant_id, tenant_name, maintenance_mode }`. Legacy `emergency_stop` field remains (= tenant OR global) for older clients.

**Migration.** `backend/alembic/versions/0041_add_tenant_emergency_stop.py` — `ALTER TABLE tenant ADD COLUMN emergency_stop BOOLEAN NOT NULL DEFAULT FALSE` with `server_default=false`, so every existing tenant row is backfilled automatically on deploy.

**Touched files.**
- Backend: `backend/models_rbac.py` (+`Tenant.emergency_stop`), `backend/alembic/versions/0041_add_tenant_emergency_stop.py` (new), `backend/api/routes.py` (two endpoints re-scoped to tenant + two new global endpoints + extended status payload + audit log calls), `backend/mcp_reader/filters.py` (`tenant_id` kwarg, dual-flag check), `backend/services/watcher_manager.py` (pass `instance.tenant_id` to `MessageFilter`), `backend/agent/router.py` (dual-flag check at router), `backend/api/routes_webhook_inbound.py` (dual-flag check at webhook ingress).
- Frontend: `frontend/components/LayoutContent.tsx` (two independent toggles, scope-aware confirmation modal, blocked-state styling when global is on).

**Verified via API + browser automation (https://localhost):**
- `GET /api/system/status` as tenant owner returns `{tenant_emergency_stop:false, global_emergency_stop:false, is_global_admin:false}`.
- Tenant owner `POST /api/system/emergency-stop` flips only the tenant flag; `/api/system/global-emergency-stop` returns 403.
- Global admin `POST /api/system/global-emergency-stop` flips the global flag; the tenant owner's subsequent `/api/system/status` correctly reports `global_emergency_stop:true`, greying out the tenant toggle.
- Resumes work for both scopes; clearing the global flag restores the tenant toggle's interactive state.

### Audio Agents Onboarding Wizard — Kokoro / Kira / Transcript removed from seed (2026-04-19)

Every fresh tenant used to get three audio agents seeded automatically: **Kokoro** (free/local TTS), **Kira** (OpenAI TTS), and **Transcript** (Whisper-only). Most tenants never configured audio at all, so those agents sat idle at the top of every agent list — and Kokoro in particular silently disabled itself because it required a Kokoro Docker container that was never provisioned.

The audio agents are now **opt-in** via a new **Audio Agents wizard** that covers all three intents (TTS responses, transcription-only, hybrid) across all three providers (Kokoro / OpenAI / ElevenLabs) in a single guided flow.

**What the wizard does.** 5 steps, all client-side orchestration over existing endpoints:
1. *Intent* — voice (TTS out), transcript (voice in), or hybrid (both).
2. *Provider* — Kokoro / OpenAI / ElevenLabs. "Detected" badge renders when the provider is already configured for this tenant (`api.getProviderInstances()` for OpenAI/ElevenLabs keys, `api.getTTSInstances()` for Kokoro); "Needs API key" badge links to Hub → AI Providers otherwise.
3. *Voice & credentials* — language → voice list (Kokoro voices filter by language), speed, format; Kokoro step also asks for mem_limit and "set as tenant-default TTS".
4. *Agent target* — create a new Voice Assistant (default system prompt carries over from the old Kira/Kokoro prompts as client-side templates) OR attach `audio_tts` + `audio_transcript` skills to an existing agent.
5. *Review* + *Provision & wire* — creates the TTSInstance (Kokoro only), polls `/api/tts-instances/{id}/container/status` until `running` (~30–90s), creates the Contact + Agent if new-mode, wires skills via `assignTTSInstanceToAgent` (Kokoro) or `updateAgentSkill('audio_tts'/'audio_transcript')` (OpenAI/ElevenLabs).

**Two entry points** (both optional):
- **Onboarding tour step 12** — new "Voice Capabilities (optional)" page with a "Set up voice agent" CTA and a skip button. Tour total raised 14 → 15.
- **Studio → New Agent** — the inline "Create New Agent" modal now has a **Text / Voice / Hybrid** radio. Picking Voice or Hybrid hands off to the wizard preset with the agent name pre-filled and `presetMode='new'`.

**Backward compatibility.** Existing tenants keep their already-seeded Kokoro / Kira / Transcript agents untouched — the change is remove-only in `agent_seeding.py`. The previous Kokoro-TTSInstance resolution block that seeded the `audio_tts` skill disabled-with-a-hint is also gone (no longer needed since the agent isn't seeded). `KokoroSetupWizard` is still mounted in Hub → Voice as a direct deep-link for power users.

**Touched files.**
- Backend: `backend/services/agent_seeding.py` (removed Kokoro/Kira/Transcript dicts from `agents_config`; removed Kokoro TTSInstance lookup block and the `audio_tts skill_type=='kokoro'` enablement branch; updated `default_agent_names` list used by `check_existing_agents` and the module docstring), `backend/auth_routes.py` (updated the `agents_created` example in the `/api/auth/setup` docstring).
- Frontend: `frontend/contexts/AudioWizardContext.tsx` (new global provider modeled on `GoogleWizardContext` — `openWizard({ presetProvider, presetAgentId, presetMode, presetAgentType, presetNewAgentName })`, `closeWizard`, `registerOnComplete`, `useAudioWizardComplete`; emits `tsushin:audio-wizard-closed` so the tour can auto-resume), `frontend/components/audio-wizard/AudioAgentsWizard.tsx` (new 6-step wizard — 5 config steps + 1 progress step, container polling, skill wiring), `frontend/components/audio-wizard/defaults.ts` (new — voice/agent templates carrying over the Kira/Kokoro/Transcript prompts as client-side constants), `frontend/app/layout.tsx` (mount `AudioWizardProvider` alongside the existing wizard providers), `frontend/contexts/OnboardingContext.tsx` (`TOTAL_STEPS` 14 → 15), `frontend/components/OnboardingWizard.tsx` (new `openVoiceWizard` callback; new "Voice Capabilities (optional)" tour step between Playground and Playground Mini; shifted step-numbering comments on Sentinel/finale), `frontend/components/watcher/studio/StudioAgentSelector.tsx` (new `newAgentKind` state — text / voice / hybrid — with Audio Wizard hand-off; provider/instance/model fields now render only for Text; button label flips to "Continue in Audio Wizard →" for Voice/Hybrid).
- Docs: this changelog entry; documentation.md updated under "Voice & Audio" and "Default Agents".

### Hub: auto health-test provider instances on save (2026-04-19)

Cloud LLM provider instances (OpenAI, Gemini, Anthropic, Groq, Grok, DeepSeek, OpenRouter, Vertex AI, custom) used to sit at `health_status="unknown"` — gray dot in **Hub → AI Providers** — until the user opened the row's three-dot menu and clicked **Test Connection**. Even with valid credentials configured, nothing else flipped the status; only Ollama (which has its own container-manager probe) went green on its own.

The `POST /api/provider-instances` and `PUT /api/provider-instances/{id}` endpoints now schedule a connection test in a FastAPI `BackgroundTasks` after the response is returned. The test mirrors the manual button: it picks the first model (or vendor fallback), calls `AIClient.generate` with `max_tokens=20` and SDK retries disabled, then writes `health_status` (`healthy`/`unavailable`), `health_status_reason`, `last_health_check`, and a `ProviderConnectionAudit` row with `action="auto_test_on_save"`.

**Trigger rules.**
- *Create:* fire iff the instance was saved with credentials (or vendor is `ollama`) **and** `available_models` is non-empty.
- *Update:* fire iff a connectivity-relevant field changed (`api_key`, `base_url`, `extra_config`, `available_models`) and the instance still has credentials and is active. Pure renames or default-toggles do not re-test.
- *Clear key:* setting `api_key=""` resets `health_status` back to `"unknown"` (gray) so the dot doesn't keep showing a stale green from the previous valid key.

**Touched files.**
- Backend: `backend/api/routes_provider_instances.py` (new `_background_test_instance` helper; `BackgroundTasks` parameter on create + update; clear-key resets health).

### A2A Communications moved to Studio (2026-04-19)

A2A permission-rule CRUD was previously hosted under **Watcher → A2A Comms → Permissions**, which was a layering mistake — Watcher is the observability surface ("what's happening"), not configuration ("what's allowed"). Since A2A wiring describes the whole multi-agent graph (many-to-many, group-level), it belongs in Studio, where tenant-admins already configure agents, personas, projects, and security profiles.

**New location.** `/agents/communication` — a first-class Studio tab sitting between **Security** and **Builder** in the Studio sub-nav, with a two-way-arrow icon. The full CRUD lives here: Permission Rules table (Source, Target, Max Depth, Rate Limit, Target Skills toggle, Status toggle, Delete) + Add-Permission modal.

**Watcher → A2A Comms** is now purely read-only observability: sub-nav is just **Communication Log** + **Statistics**, with an info banner at the top of the page pointing users to Studio → A2A Communications for rule management.

**Touched files.**
- Frontend: `frontend/app/agents/communication/page.tsx` (new Studio route; mounts StudioTabs + the manager), `frontend/components/studio/A2APermissionsManager.tsx` (new — full permission CRUD, extracted from CommunicationTab), `frontend/components/studio/StudioTabs.tsx` (+`A2A Communications` entry with a cyan two-way-arrow icon), `frontend/components/watcher/CommunicationTab.tsx` (removed Permissions view, Add modal, and all CRUD handlers/state; added pointer banner).

**Verified via browser automation (https://localhost):**
- Studio nav shows A2A Communications between Security and Builder; clicking it loads the Permission Rules table with the two existing pairs (Tsushin→movl, Tsushin→archsec), TARGET SKILLS amber toggle ON, STATUS teal toggle ON.
- Add-Permission modal renders all fields including the "Allow target to use its own skills" checkbox + help text.
- Watcher → A2A Comms sub-nav is now **Communication Log | Statistics** only; banner "Permission rules moved — configure which agents can communicate in Studio → A2A Communications" links to `/agents/communication`.
- 0 console errors.

### A2A: opt-in "allow_target_skills" per permission row (2026-04-19)

The `agent_communication_service._invoke_target_agent` call had historically hard-coded `disable_skills=True`, so when Agent A asked Agent B anything via A2A, B answered with LLM knowledge only — every tool (gmail, sandboxed_tools, shell, …) was silenced. A user asking "Tsushin, ask movl for the latest emails" got "I have no email access" back from movl, even though movl had its Gmail integration correctly bound to `movl2007@gmail.com`.

`AgentCommunicationPermission` now has an `allow_target_skills` Boolean column (default `false`, preserves old behavior for every existing row). When `true` on a source→target pair, the target's own skills load during A2A invocation; depth limit, rate limiting, permission check, and Sentinel analysis continue to bound the call.

**Touched files.**
- Backend: `backend/alembic/versions/0040_add_allow_target_skills_to_agent_comm_permission.py` (new migration, idempotent, `server_default=false`), `backend/models.py` (+`allow_target_skills` column), `backend/services/agent_communication_service.py` (`create_permission`/`update_permission` accept the flag; `send_message` reads it from the permission row and passes through; `_invoke_target_agent` translates it into `disable_skills=not allow_target_skills`), `backend/api/routes_agent_communication.py` (`PermissionResponse`/`PermissionCreateRequest`/`PermissionUpdateRequest` updated, route plumbing passes the flag on).
- Frontend: `frontend/lib/client.ts` (`AgentCommPermission.allow_target_skills`, extended create/update signatures), `frontend/components/watcher/CommunicationTab.tsx` (new "Target Skills" column with inline amber toggle + `handleToggleTargetSkills`; checkbox in Add-Permission modal with help text).
- Tests: `backend/tests/test_agent_communication_service.py` (+6 cases covering default-false, opt-in true, toggle-update, `_invoke_target_agent` disable_skills mapping in both directions, and end-to-end propagation from permission row → invoke call).

**Verified:**
- Migration applied cleanly: `0039 -> 0040` in backend logs, column present on `agent_communication_permission`.
- Unit tests: 15/15 pass (`pytest tests/test_agent_communication_service.py -o addopts=`); API v1 E2E 28/29 pass (the one failure is a pre-existing agent-quota 409, unrelated).
- Live E2E via `/api/v1/agents/1/chat`: Tsushin asked movl → movl fetched and returned real subjects from `movl2007@gmail.com`; asked archsec → archsec returned real subjects from `mv@archsec.io`. Three completed sessions recorded in `agent_communication_session` (status=completed, depth=1).
- UI: Permissions table shows the new column + amber toggle; Add-Permission modal shows the new checkbox and help text; Graph View renders the A2A edges (`a2a-4` Tsushin→movl, `a2a-5` Tsushin→archsec) with dashed styling and glows during active calls.

### Webhook: ready-to-paste test snippet in the reveal modal (2026-04-19)

The Webhook reveal modal (shown once on create and after Rotate Secret) now includes a pre-filled `openssl`+`curl` snippet with the actual secret and inbound URL baked in. The user copies the block, pastes it into any shell, and a successful reply (`{"status":"queued",…}`) confirms the integration end-to-end — no signing library or manual HMAC computation required. The `-k` flag is included automatically when the URL is `https://localhost` so the self-signed cert on the dev stack doesn't break the test; production URLs render without it.

Touched files: `frontend/components/WebhookSecretRevealModal.tsx` (new test block + Copy command button).

### Webhook: edit modal + enable/pause toggle (2026-04-19)

Each webhook card now has an **Edit** button (opens `WebhookEditModal` — name, slug, callback, rate limit, IP allowlist) and a **Pause / Enable** toggle that flips `is_active` via `PATCH /api/webhook-integrations/{id}`. The slug-available endpoint gained an optional `exclude_id` query param so the edit flow doesn't collide with the integration's own current slug.

**Slug collision while paused.** Uniqueness is independent of `is_active`. A paused webhook's slug stays reserved — only `DELETE` frees it for reuse. Verified: `PATCH {is_active:false}` on `qa-crm-test` + `POST /api/webhook-integrations` with the same slug returns `409 {"detail":"Slug already in use"}`.

**Touched files.**
- Backend: `backend/api/routes_webhook_instances.py` (exclude_id on slug-available).
- Frontend: `frontend/components/WebhookEditModal.tsx` (new), `frontend/app/hub/page.tsx` (toggle + Edit button + modal mount), `frontend/lib/client.ts` (`checkWebhookSlugAvailable(slug, excludeId?)`).

### Webhook: reveal rotated secret + custom URI slug (2026-04-19)

Two UX defects addressed in the v0.6.0 Webhook-as-a-Channel feature.

**Bug fix — Rotate Secret now reveals the new plaintext.** Previously, `Rotate Secret` copied the new HMAC secret to the clipboard and flashed a masked-preview toast; if the clipboard write failed or the user dismissed the toast, the secret was gone forever (only the encrypted blob + 10-char preview are persisted by design). A new `WebhookSecretRevealModal` now opens with the full plaintext secret in a read-only input, a copy button, the inbound URL, signing instructions, and an amber "never shown again" warning. The same component is reused by the create flow.

**Feature — custom inbound URI slug.** Webhook integrations now have a human-readable `slug` used in the inbound path: `/api/webhooks/<slug>/inbound`. The create modal exposes two modes:

- **Auto** (default) — server generates `wh-{6-hex}` on create.
- **Custom** — user types a slug. Live-validated against `^[a-z][a-z0-9]*(-[a-z0-9]+)*$` (3–64 chars, must start with a letter, lowercase, no consecutive/leading/trailing hyphens), checked against a reserved list (`inbound, rotate-secret, health, status, test, callback, docs, openapi, api, webhooks, admin, v1`), and checked for global uniqueness via a new `GET /api/webhook-integrations/slug-available?slug=…` endpoint. Red X + reason when invalid/taken, green check + "Available" when OK. The full inbound URL is previewed live.

Slug is globally unique (not per-tenant) because the inbound route has no auth before the DB lookup — the slug is the identifier used to resolve the tenant.

**Backward compatibility.** Existing integrations were backfilled to `slug = wh-{id}`. The inbound route still accepts numeric IDs via a `slug.isdigit()` fallback so every legacy URL (`/api/webhooks/123/inbound`) keeps working.

**Touched files.**
- Backend: `backend/models.py` (+slug column on `WebhookIntegration`), `backend/alembic/versions/0039_add_webhook_integration_slug.py` (new — nullable add + backfill + NOT NULL + unique index), `backend/api/routes_webhook_instances.py` (slug validation, auto-gen, `/slug-available` endpoint, CRUD updates, `inbound_url` now derives from slug), `backend/api/routes_webhook_inbound.py` (path param `int → str`, slug-first lookup with numeric fallback).
- Frontend: `frontend/components/WebhookSecretRevealModal.tsx` (new), `frontend/components/WebhookSetupModal.tsx` (URI mode radio + debounced slug availability check + URL preview), `frontend/app/hub/page.tsx` (rotate handler now opens reveal modal instead of toast-copy), `frontend/lib/client.ts` (types + `checkWebhookSlugAvailable`).

**Verified via UI regression (https://localhost):**
- Rotate Secret on existing webhook → reveal modal shows full plaintext, inbound URL, copy buttons, auto-copy notice.
- Create with Custom mode, slug `qa-ui-test` → green "Available", full URL preview, modal shows secret + URL ending `/qa-ui-test/inbound`.
- Slug `inbound` → "Slug is reserved"; slug `qa-crm-test` (existing) → "Slug already in use" — both block Create.
- Graph View renders webhook channel nodes per integration with their readable name (e.g., "Webhook QA UI Custom").

**Verified via API:**
- Signed inbound POST to `/api/webhooks/qa-ui-test/inbound` → 200 `{queue_id, poll_url}`; agent binding resolved; queue worker picked up the item.
- Signed inbound POST to legacy numeric path `/api/webhooks/<id>/inbound` → HMAC accepted, agent lookup path identical (backward-compat confirmed).

### Google OAuth handle_callback honors the real integration_type (2026-04-19)

**Root-cause fix for a years-old latent bug surfaced by the wizard QA pass today.**

`backend/hub/google/oauth_handler.py::handle_callback` was inferring `integration_type` by parsing the `redirect_url` query string and **defaulting to `"calendar"`** when it couldn't find one. The popup-driven wizard flow never sets a `redirect_url` (it uses the same tab via `window.open` and relies on a postMessage handoff), so **every wizard-initiated Gmail OAuth actually upserted the user's email into the Calendar integration table.** The frontend's success URL correctly said `type=gmail` because the outer `routes_google.py::oauth_callback` read the state prefix, but that value was never passed into the handler — two independent copies of "what type is this", and only one of them was right.

Example: running the Gmail wizard for `mv@archsec.io` on the test tenant updated Calendar row `id=3` (it already existed, disconnected) and wrote a Gmail-scope OAuth token against it. The Gmail row `id=4` stayed `is_active=false, health_status=disconnected`, so the wizard's Step-3 list (which correctly filters disconnected rows) stayed empty — "wizard is stuck".

**Fix.** `handle_callback` now accepts `integration_type: Optional[str]` and the outer `oauth_callback` at `backend/api/routes_google.py::527` passes it in explicitly (already parsed from the `OAuthState` prefix). The handler still falls back to parsing `redirect_url` for the legacy direct-redirect path, but if it still can't determine the type, it now raises `ValueError` instead of silently defaulting to calendar. Defense-in-depth: the caller knows, the handler verifies, no silent miscategorization.

**Data cleanup.** Restored test-tenant Calendar row `id=3` to `is_active=false, health_status='disconnected'` and deleted the misrouted Gmail-scope `oauth_token` row (`id=1561, integration_id=3`) so it can't be used.

**Verified.** `GET /api/hub/google/gmail/integrations` and `.../calendar/integrations` both return only their correctly-typed, non-disconnected rows. After the fix, re-running the Gmail wizard for `mv@archsec.io` should upsert Gmail row `id=4` (not Calendar).

### Gmail/Calendar OAuth popup auto-closes and hands off to the wizard (2026-04-19)

Fixes a stuck-wizard UX in the Gmail / Calendar setup flow.

**Symptom.** In Step 3 ("Connect a Gmail account" / "Connect a Calendar account"), clicking "Connect new account" opened the Google consent screen in a popup window. After the user approved, Google redirected the popup to the backend callback, which in turn redirected to `/hub?integration=<kind>&status=success&type=<kind>&id=<n>`. The popup then loaded the entire Hub page inside itself and stayed open. The wizard's parent window had no way to know OAuth had finished — it waited for its 3-second poll tick, which could be missed entirely if the user closed the popup manually before it fired.

**Fix — two-sided.**

1. **Popup side** (`frontend/app/hub/page.tsx`): At the very top of `HubPage`, before any hooks, we check `window.opener && window.opener !== window` plus the `status=success` + `integration=gmail|calendar` query params. When that's true, we post a `{ source: 'tsushin-google-oauth', integration, integration_id, status }` message back to `window.opener` (same-origin), call `window.close()`, and `return null`. This runs only in the popup render — a direct browser visit to `/hub?integration=gmail&status=success&…` (the popup-blocked fallback path) still renders Hub normally because `window.opener` is null.
2. **Wizard side** (`frontend/components/integrations/GmailSetupWizard.tsx`, `GoogleCalendarSetupWizard.tsx`): Added a `message` event listener inside a `useEffect` gated on `isOpen`. On receipt of a same-origin message with the expected shape, it stops the 3-second poll, refreshes the integrations list, and selects the integration ID the popup reported (falling back to "first id not in the initial snapshot" if the payload is missing).

**Verified end-to-end (Playwright):**
- Direct visit to `/hub?integration=gmail&status=success&type=gmail&id=3` (no `window.opener`) renders Hub normally — the popup-blocked fallback still works.
- `window.open('/hub?integration=gmail&status=success&type=gmail&id=3', …)` from the parent tab → parent received exactly one `{source:'tsushin-google-oauth', integration:'gmail', integration_id:3, status:'success'}` message; `popup.closed === true` within ~3 s. Calendar path behaves identically with `integration:'calendar', integration_id:4`.

**Not touched:** the backend OAuth callback continues to redirect to `/hub?…` so the legacy popup-blocked fallback (which the wizard code still supports) stays unchanged.

### Wizard Step 3 no longer lists disconnected Gmail/Calendar accounts (2026-04-19)

Follow-up to the wizard-unification work below. `GET /api/hub/google/gmail/integrations` and `GET /api/hub/google/calendar/integrations` now exclude rows with `health_status='disconnected'`, matching the filter already applied by the main Hub list endpoint.

**Why.** The wizard's Step 3 "Existing accounts" picker was backed by an unfiltered query, so a previously-disconnected row still appeared there. A user could select it, walk through the agent-linking step, and `PUT /api/agents/{id}/skill-integrations/gmail` would happily bind the agent's Gmail skill to the dead `integration_id`. The Hub card list correctly hid the integration (because it's disconnected), which made the wizard feel silently broken — "I finished the flow, where's my card?".

**Fix.** Added `HubIntegration.health_status != 'disconnected'` to both list endpoints in `backend/api/routes_google.py`. Reconnecting a disconnected account goes through the OAuth flow, which already flips `is_active=True` and clears the `disconnected` status, so the row becomes eligible for the wizard list again naturally.

**Data cleanup.** Unbound a stale `agent_skill_integration` row on a test-tenant agent that was pointing at a disconnected Gmail integration, and disabled the orphan Gmail skill row so the agent wouldn't sit in an "enabled but unbound" state.

### Unify Gmail / Google Calendar wizards across Settings and Hub (2026-04-19)

Hub → Communication "Add Gmail Account" and Hub → Productivity "Add Calendar Account" now open the same multi-step `GmailSetupWizard` / `GoogleCalendarSetupWizard` already used on `/settings/integrations`, instead of doing a bare `window.location.href` OAuth redirect.

**Problem.** The Hub buttons called `/api/hub/google/{gmail|calendar}/oauth/authorize` directly and full-page-redirected. The user came back to Hub with an `HubIntegration` row but with **no agent bound** — they had to re-do the flow from Settings to enable the Gmail / Scheduler skill on the agent and link the integration. Two entry points, two different experiences, silently diverging outcomes.

**Fix.** Lifted the wizards into a shared `GoogleWizardProvider` mounted globally in `app/layout.tsx` (same pattern already in use for WhatsApp via `WhatsAppWizardProvider`). A new `useGoogleWizard()` hook exposes `openWizard('gmail' | 'calendar')`; a `useGoogleWizardComplete(kind, cb)` companion hook lets consumer pages refresh their local integration lists when the wizard finishes.

**Touched files.**
- `frontend/contexts/GoogleWizardContext.tsx` (new) — provider, hook, `GoogleWizardHost` that mounts both dynamic-imported wizards.
- `frontend/app/layout.tsx` — wraps tree with `GoogleWizardProvider`.
- `frontend/app/settings/integrations/page.tsx` — removed local wizard state and inline mounts; buttons call `openWizard()`; `useGoogleWizardComplete` re-fetches Google credentials after completion.
- `frontend/app/hub/page.tsx` — rewrote `handleGmailConnect` and `handleGoogleCalendarConnect` to call `openWizard()`; registered `loadHubIntegrations` as the completion callback via a ref (the function is declared below the hook call in the same component).

**No backend changes.** Wizards already call `/api/hub/google/{gmail|calendar}/oauth/authorize` in popup mode and then `PUT /api/agents/{id}/skills/{type}` + `PUT /api/agents/{id}/skill-integrations/{type}` — the existing endpoints and schema are unchanged.

**Verified end-to-end (Playwright, https://localhost):**
- Hub → Communication → "+ Add Gmail Account" opens the 6-step Gmail wizard (not a redirect).
- Hub → Productivity → "+ Add Calendar Account" opens the 6-step Calendar wizard.
- `/settings/integrations` → "Set up Gmail →" / "Set up Google Calendar →" still open the same wizards (regression clean).
- No `ReferenceError`, `TypeError`, or React invariant violations in the browser console.

### QA — UI-First 4-Audit Regression Campaign (2026-04-19)

- Coverage: Playground + Mini + Graph-Glow (A1 API harness + A2 browser), Flows (B1 API + B2 UI 20-shape matrix + 2 edit scenarios), Sentinel + MemGuard (C1 preflight + C2 browser matrix across Chroma × block/aggressive), Full-Stack multi-tenant UI + Ollama/Kokoro autoprov (D12 + D34-api), Ubuntu VM fresh install (HTTP + self-signed TLS, E1).
- Outcome: 43 bugs filed (BUG-616..BUG-658). 1 Critical, 12 High, 12 Medium, 18 Low. Top findings: memory-poisoning persistence writing adversarial "IGNORE PREVIOUS INSTRUCTIONS" content as high-confidence long-term facts (BUG-642); Sentinel aggressive-level-3 regressing below block-level-1 on 3 attack families (BUG-644); Gate step data-binding returning literal `"null"` for `step_N.output` across 5 flow shapes (BUG-632); Ollama idle-DB-connection failures during long image pulls and CPU inference (BUG-649); platform Google SSO authorize URL leaking tenant client_id (BUG-647); self-signed Caddy TLS aborting SNI-less handshakes on IP-only hosts (BUG-653).
- Evidence root: `output/playwright/full-regression-20260419/` (gitignored).
- Playbook (reusable): `.private/TEST_PLAYBOOK_UI_FIRST_REGRESSION.md`.

### Agent Studio empty-canvas + stale-switch fix, fullscreen exit button, integration-disconnect leak fix (2026-04-19)

Three fixes in the Studio/Hub areas surfaced by a UI regression pass.

**Agent Studio — canvas empty on first load (`frontend/components/watcher/studio/hooks/useAgentBuilder.ts`).**
- Symptom: on fresh page load the default agent auto-selected in the dropdown, but the React Flow canvas rendered 0 nodes. The `/api/v2/agents/{id}/builder-data` call fired and returned 200, yet the layout never committed.
- Root cause: the node-generation effect used a `let cancelled = false` local with a cleanup `() => { cancelled = true }`. Because the effect depends on `detachProfile` (and other callbacks whose refs change on every parent render — `onWarning` in `AgentStudioTab` was an unmemoized lambda), the effect re-ran frequently. Each re-run cancelled the prior in-flight dagre layout, and if the re-run early-returned (because the structural fingerprint hadn't changed) no new layout was kicked off — so the first layout's nodes never landed.
- Fix: replaced the cleanup-based cancellation with a `layoutRequestVersion` ref. A pending layout only gets discarded when a newer layout is actually started, so benign re-renders no longer wipe the canvas.

**Agent Studio — first agent switch rendered the previous agent's data (`useAgentBuilder.ts` + `useStudioData.ts`).**
- Symptom: after the empty-canvas state above, clicking a different agent showed the dropdown updated to the new agent but the canvas rendered the previously-selected agent's name, channels, skill count, etc. Only the first switch was affected.
- Root cause: `useStudioData` did not clear `agent`/`skills`/etc. when `agentId` changed — it waited for the new fetch to resolve, during which consumers saw the old payload combined with the new id.
- Fix: `useStudioData` now tracks the last synced agentId via a ref and clears the per-agent state slice the moment `agentId` actually changes (before kicking off the new fetch). `useAgentBuilder`'s load-state effect also gained a defensive `if (studioData.agent.id !== agentId) return` guard so it never processes a mismatched payload even for a single render.

**Agent Studio — exit-fullscreen button hidden behind backdrop (`frontend/components/watcher/studio/AgentStudioTab.tsx`).**
- When the board was maximized, the existing minimize button in the header row ended up under the `z-40` backdrop (header wasn't elevated), so users had to hit `Esc` or click the dark overlay — both non-obvious.
- Added a visible close button (top-right, `z-[60]`) inside the maximized container. `Esc` and click-outside still work.

**Hub — Gmail / Google Calendar / Asana disconnect left the card visible.**
- Symptom: clicking "Disconnect" on a Gmail/Calendar/Asana card would sometimes succeed on the backend but the card remained in the list after reload.
- Root cause split across layers:
  1. Backend `disconnect_integration` (`backend/hub/google/oauth_handler.py`, `backend/hub/asana/oauth_handler.py`) set `integration.is_active = False` but did not reset `health_status`. The listing filter in `backend/api/routes_hub.py` returned integrations where `is_active=True` **or** `health_status='unavailable'` (the "needs re-auth" branch), so a just-disconnected integration that was previously unavailable still matched.
  2. Frontend handlers (`frontend/app/hub/page.tsx`) for Gmail/Calendar/Asana did not check `response.ok`, silently showing the "Disconnected" toast even on backend failure; they also didn't await the re-fetch.
- Fix: backend now sets `health_status = 'disconnected'` alongside `is_active = False`. Listing filter now requires `health_status != 'disconnected'` in addition to the existing active/unavailable predicate. Frontend handlers throw on non-2xx responses, optimistically drop the card from local state, await the re-fetch, and surface errors via the existing error toast path instead of a silent success.
- Reconnect path is unaffected — the existing authorize flow resets `is_active=True` and `health_status='unknown'`, which clears the `disconnected` marker.

### Live Playground regression harness (2026-04-19)

Added a reusable live-stack regression runner for Playground / Playground Mini / Watcher Graph verification.

- **New test-only runner** — `backend/dev_tests/run_playground_regression_live.py`
  - Authenticates against `https://localhost` with the current owner fixture (`test@example.com / test1234`).
  - Validates the existing live interfaces only: `/api/auth/login`, `/api/auth/me`, `/api/playground/agents`, `/api/projects`, `/api/playground/threads`, `/api/playground/chat?sync=true`, `/api/v2/agents/graph-preview`, `/api/v2/agents/{id}/expand-data`, `/api/v2/agents/comm-enabled`, `/api/agents/{id}/knowledge-base/*`, and `/ws/watcher/activity`.
  - Discovers the live default/default-capable agent mapping, uploads `sample_data/acme_sales.csv` to the provider-backed graph agent knowledge base, waits for chunking completion, and then exercises baseline thread flow, provider-backed `web_search`, KB-backed answers, and `agent_communication` A2A.
  - Writes a structured JSON report into `output/playwright/playground-regression-api-<timestamp>.json` with correlation tokens, watcher event capture, cleanup targets, and per-scenario assertions.
  - Supports `--skip-cleanup` so the browser Graph run can inspect the same KB / thread artifacts before cleanup.

- **Regression artifact convention** — browser evidence for the paired Playwright CLI run is now expected under `output/playwright/playground-regression-<timestamp>/` so screenshots, summaries, and API JSON stay grouped per live pass.

- **No product contract changes.** This is regression-only scaffolding; all coverage uses the existing tenant-scoped Playground, project, watcher, graph, KB, and auth routes.

### Global admin invite UX + System-under-Core nav consolidation (2026-04-19)

Hardens the multi-tenant mental model in the global-admin UI. Previously, inviting a user from `/system/users` let the admin drift into an ambiguous state where a tenant-scoped invite could be submitted with no tenant selected, relying solely on a backend 400 to catch it — and the Create User modal had the same shape. The System area also lived as a standalone top-level nav item in the global-admin view, inconsistent with the tenant view where System is a card under Core.

**Frontend — explicit `Tenant User` vs `Global Admin` branching** (`frontend/app/system/users/page.tsx`).
- Both Invite User and Create User modals now lead with a two-option segmented picker: **Tenant User** (belongs to a specific organization — the common case, default) and **Global Admin** (platform-wide administrator, no tenant).
- Tenant-user path: required Organization dropdown labeled with `{name} — {slug} ({user_count} members)` so the admin can disambiguate; inline red helper when empty (*"Invitees are not global admins and must belong to one tenant"*); role dropdown constrained to `owner | admin | member | readonly` (no `global_admin` row here — global admin is chosen via the kind picker).
- Global-admin path: tenant + role dropdowns hidden; small purple info banner explains platform-wide scope.
- Submit button disabled until all required fields for the active kind are filled — the old form could submit without a tenant and fail server-side.
- When no tenants exist yet, both modals surface an amber hint to create one via System → Tenant Management first.

**Frontend — System becomes a Core section, not a standalone nav link.**
- Removed the separate `System` top-level nav item for global admins in `components/LayoutContent.tsx`. Top nav is now identical for all roles: `Watcher, Studio, Hub, Flows, Playground, Core`.
- `app/settings/page.tsx` — expanded the global-admin section from one card (Tenant Management) to five: **Tenant Management, User Management, Plans & Limits, Remote Access, Global SSO**. Section header renamed from `Platform Administration` to `System` to match the concept (and the old nav label).
- Global admin login now redirects to `/settings` (Core) instead of `/system/integrations`.
- `app/system/integrations/page.tsx` replaced with a redirect stub that `router.replace('/settings')` — preserves old bookmarks and email links.
- New `app/system/sso/page.tsx` — dedicated Global SSO page; extracts the Google SSO config block (credentials form, domain whitelist, auto-provision + default-role dropdown, setup instructions) from the old `/system/integrations` hub. Behavior preserved verbatim (`api.getGlobalSSOConfig` / `api.updateGlobalSSOConfig`).

**Backend — clearer validation + `is_global_admin` on create (non-breaking).**
- `backend/api/routes_admin_invitations.py`: replaced the two generic 400s with field-specific messages that name the missing or forbidden field (`"tenant_id is required for tenant-scoped invitations. Pick the organization this user should belong to."`, `"Global admin invitations must not include tenant_id. Global admins are platform-wide and not scoped to a tenant."`, etc.), so the UI can surface actionable feedback.
- `backend/api/routes_global_users.py`: `POST /api/admin/users/` now accepts `is_global_admin: bool = False` and branches shape validation the same way as the invite endpoint. When `True`, `tenant_id`/`role_name` must be absent, the user is created with `tenant_id=NULL` and `is_global_admin=True`, no `UserRole` row is inserted, and the tenant user-limit check is skipped. When `False` (default), both `tenant_id` and `role_name` are required and the existing tenant-scoped path runs unchanged. Existing callers are 100% unaffected. Audit log includes `is_global_admin` in details.

**Frontend type change** — `lib/client.ts` `UserCreateRequest` now has `tenant_id?: string | null`, `role_name?: string | null`, and `is_global_admin?: boolean` to match the widened backend contract.

**Database — no migration.** The existing `UserInvitation` CHECK constraint `(is_global_admin=TRUE ↔ tenant_id IS NULL AND role_id IS NULL)` and the `User.tenant_id` nullable column already support both shapes.

**Verified.** `docker-compose build --no-cache backend frontend` + `up -d`. Browser sweep: global-admin login lands on `/settings`; top nav no longer shows `System`; Core shows System group with 5 cards; invite with kind=`Tenant User` + no tenant keeps submit disabled and shows the red helper; invite with kind=`Global Admin` hides tenant/role and submits against the admin-invitations endpoint with `is_global_admin=true`; `/system/integrations` redirects to `/settings`. Tenant-owner invite flow at `/settings/team/invite` unchanged.

### Calendar + Shell Beacon + Sandboxed Tools + Search wizards + Sentinel tour step (2026-04-19)

Completes the guided-setup wizard track. Five new end-to-end flows + one onboarding tour step, all following the Kokoro shape (numbered pill indicator, 4-card info grid on step 1, Back / Cancel / primary-action footer). Cosmetically verified in-browser — consistent accent color per wizard (red Gmail, blue Calendar, teal Shell / Tools / Search).

- **Google Calendar Setup Wizard** (`frontend/components/integrations/GoogleCalendarSetupWizard.tsx`, 6 steps) — reuses `GoogleAppCredentialsStep`; step 3 lists existing `CalendarIntegration` rows + popup-and-poll new-account flow + optional `default_calendar_id` / timezone fields that PUT through `/api/hub/google/calendar/{id}`. Step 6 per-agent: `PUT /skills/scheduler {is_enabled:true}` then `PUT /skill-integrations/scheduler {integration_id, scheduler_provider:"google_calendar", config:{permissions:{read,write}}}`.
- **Shell Beacon Setup Wizard** (`frontend/components/shell/ShellBeaconSetupWizard.tsx`, 6 steps) + shared `BeaconInstallInstructions` (`frontend/components/shell/BeaconInstallInstructions.tsx`, ~150 LOC extracted from `hub/shell/page.tsx:1450-1617`). Configure step covers name, display name, mode, poll interval, retention, allowlist chips (commands + paths, Enter to add), YOLO toggle with red warning. Create step POSTs `/api/shell/integrations`, renders the one-time API key, loops `PUT /skills/shell` with `execution_mode=hybrid` per agent, and surfaces the install snippet via the shared component — same source of truth as the existing "Advanced: bare form" modal. Final step lists testable `/shell uptime | ls /tmp | df -h | whoami && hostname` commands and a link to the approval queue.
- **Sandboxed Tools Setup Wizard** (`frontend/components/tools/SandboxedToolsSetupWizard.tsx`, 5 steps) — two-column tool checkbox grid with Select-all / Clear / defaults-only helpers. Apply step ensures `AgentSkill(sandboxed_tools, is_enabled=true)` per agent then `POST /api/agents/{id}/custom-tools` per selected tool (swallows 400 "already assigned" as idempotent). Success screen surfaces "Try one of these" example commands keyed to the 9 pre-seeded tools with Copy buttons.
- **Search Integrations Wizard** (`frontend/components/integrations/SearchIntegrationWizard.tsx`, 5 steps) — 3 provider cards: Brave (recommended), Tavily (gated "Coming soon" badge with disabled radio until the adapter ships), SerpAPI. Masked API-key input with Show/Hide toggle. POSTs `/api/api-keys`; on `400 already configured` retries as `PUT /api/api-keys/{service}`. Per-agent `PUT /skills/web_search {is_enabled:true, config:{provider, max_results:5, language:"en", country:"US", safe_search:true}}`. No skill-integrations row needed (`routes_skill_integrations.py:640-648` reports `requires_integration:false` for `web_search`).
- **Sentinel step in onboarding tour** — `TOTAL_STEPS` bumped from 13 to 14 in `frontend/contexts/OnboardingContext.tsx`. New `customBody?: React.ReactNode` field on the `TourStep` interface + inline `SentinelTourPanel` (~80 LOC) inside `frontend/components/OnboardingWizard.tsx`. Panel reads `api.getSentinelConfig()` on mount and renders a Block-vs-Detect-only toggle that writes `{is_enabled:true, detection_mode:"block", block_on_detection:true, enable_prompt_analysis:true, enable_tool_analysis:true, enable_shell_analysis:true}` on ON or `{detection_mode:"detect_only", block_on_detection:false}` on OFF. Deep-links to `/settings/sentinel` for per-agent overrides. Spliced between the Playground Mini step and the All-Set finale.

**Entry points wired.** `settings/integrations` — "Set up Gmail" + "Set up Google Calendar" buttons; the previously-disabled `(soon)` placeholder is now live. `hub/shell` — "+ Register Beacon" opens the wizard, the old inline modal survives as "Advanced: bare form". `hub/sandboxed-tools` — "🪄 Guided Setup" primary CTA next to the old "+ Create Tool". `hub?tab=tool-apis` — "🔎 Setup Web Search" header CTA.

**Safety.** Every endpoint these wizards touch was tenant-isolation audited in the preceding commit (BUG-608 + BUG-609). Browser walkthrough confirmed Phase 0 fix live: Gmail step 3's existing-accounts list shows only the current tenant's emails.

**Verified.** `docker-compose build --no-cache frontend` (clean TS compile, no new lints) + `up -d frontend` (healthy < 10 s). Step 1 of every wizard + the Sentinel tour step screenshotted and visually reviewed for consistency. Skip + Back + Cancel paths exercised. No console errors on wizard open / close.

### Gmail setup wizard + shared wizard primitives (2026-04-19)

Added the first of a planned series of friction-reduction wizards that bundle resource creation, OAuth authorization, and agent-skill wiring into a single modal flow. The Gmail wizard replaces a four-UI-hop sequence (configure Google OAuth credentials → start the OAuth flow → enable the Gmail skill on each agent → link the integration per-agent from Agent Studio) with a 6-step guided path.

**New — `frontend/components/integrations/GmailSetupWizard.tsx` (~670 LOC).** Steps:
1. Welcome (explains read-only scope `gmail.readonly` and multi-account support).
2. Google OAuth app credentials (delegates to the shared `GoogleAppCredentialsStep`; auto-skips when the tenant already has credentials).
3. Connect Gmail account — radio picker of existing `GmailIntegration` rows plus "Connect new Gmail account" that opens the authorization URL in a popup and polls `/api/hub/google/gmail/integrations` every 3 s (6-minute ceiling) for the new row. Popup-blocked fallback redirects to the auth URL in the current tab.
4. Link to agents — multi-select, cloned from the Kokoro pattern; uses `api.getAgents(true)`.
5. Review — account + scope + selected agents summary.
6. Progress — for each selected agent, `api.updateAgentSkill(id, 'gmail', {is_enabled: true})` then `api.updateSkillIntegration(id, 'gmail', {integration_id, config: {}})`. Per-agent live log, "Retry failed" button, green success banner.

**New — `frontend/components/ui/CopyableBlock.tsx` (~40 LOC).** Extracted the copy-to-clipboard code block that lived inline in `SlackSetupWizard.tsx:87-107`. Accepts a `tone` prop (teal / purple / blue / amber / slate) so each wizard can match its accent. `SlackSetupWizard` updated to import the shared component and pass `tone="purple"` at its two call sites.

**New — `frontend/components/integrations/GoogleAppCredentialsStep.tsx` (~200 LOC).** Reusable wizard step that ensures the tenant has Google OAuth app credentials before any downstream Gmail / Calendar OAuth flow can start. Fetches `GET /api/hub/google/credentials`; if configured, shows a "Use these credentials" confirmation panel; if missing, renders the client_id / client_secret form and POSTs. Mirrors the copy + amber help box from the Integrations settings page.

**Entry points** (in `frontend/app/settings/integrations/page.tsx`): when Google credentials are configured, a red "Set up Gmail →" button lives next to the existing Update / Remove actions. When no credentials yet, a secondary "Or jump into a guided setup: Gmail · Google Calendar (soon)" link appears below the primary "Configure Google Integration" CTA. The wizard is lazy-loaded via `next/dynamic` with `ssr:false`. The Google Calendar entry point is present but disabled with a "(soon)" tooltip — the Calendar wizard lands in a follow-up commit in the same release.

**Safety.** Every backend endpoint the wizard calls was tenant-isolation-audited in the preceding commit (BUG-608 / BUG-609). Integration ids passed to `PUT /api/agents/{id}/skill-integrations/gmail` are verified against `HubIntegration.tenant_id == ctx.tenant_id`, and `GET /api/skill-providers/gmail` is scoped to the caller's tenant, so the wizard cannot leak or link cross-tenant resources even if the payload is tampered with.

**Verified.** `docker-compose build --no-cache frontend` + `docker-compose up -d frontend` clean compile and healthy boot.

### Legacy Kokoro compose service removed (2026-04-19)

The stack-level `kokoro-tts` compose service and the `KOKORO_SERVICE_URL` env fallback have been deleted. Per-tenant auto-provisioned Kokoro containers (introduced in v0.7.0 via the TTSInstance model and the Hub "Kokoro TTS → Setup with Wizard" flow) are now the only supported way to run Kokoro.

- **BREAKING**: Removed `kokoro-tts` service from `docker-compose.yml` and the `tts` profile. Users running `docker compose --profile tts up -d` must migrate to per-tenant auto-provisioned instances via Hub → Kokoro TTS → Setup with Wizard. The `kokoro-models` and `kokoro-audio` top-level volumes were also removed (the old compose service owned them; per-tenant instances manage their own volumes via `KokoroContainerManager`).
- `KOKORO_SERVICE_URL` env fallback removed from `KokoroTTSProvider`. `synthesize(request, *, base_url)` now raises `RuntimeError` immediately if `base_url` is not supplied, and `health_check(base_url=None)` returns `status="unknown"` when called without one. `AudioTTSSkill` no longer silently falls back to an env URL: agents without a `tts_instance_id` or `Config.default_tts_instance_id` now return a clear `SkillResult` error pointing at Hub → Kokoro TTS → Setup with Wizard.
- `POST /api/services/kokoro/{start,stop}` and `GET /api/services/kokoro/status` now return HTTP 410 Gone with a JSON body `{error, message, replacement: "/api/tts-instances"}` and a `Link: </api/tts-instances>; rel="successor-version"` header so old clients get a helpful migration message instead of a 404.
- `install.py` no longer writes `KOKORO_SERVICE_URL` to `.env` during install and no longer backfills it into existing `.env` files. The `_get_default_kokoro_service_url()` helper has been deleted.
- `backend/services/agent_seeding.py` is now Kokoro-instance-aware. When seeding the default "Kokoro" demo agent, it checks for an existing per-tenant `TTSInstance(vendor="kokoro", is_active=True)`. If one exists, the seeded `audio_tts` skill is wired to it via `tts_instance_id`. If none exists, the skill is seeded with `is_enabled=False` and a `_note` pointing the user to Hub → Kokoro TTS → Setup with Wizard — no more zombie agents referencing a dead compose URL.
- Docs: `docs/documentation.md` no longer lists `KOKORO_SERVICE_URL` in the env reference and the quick-start `docker compose --profile tts up -d` note has been replaced by a pointer to the Hub wizard.

### Tenant isolation hardening — skill-integrations routes (2026-04-19)

A tenant-isolation audit performed while planning the Gmail / Google Calendar / Shell Beacon / Sandboxed Tools / Web Search setup wizards surfaced two pre-existing cross-tenant defects in `backend/api/routes_skill_integrations.py`. The wizards would have scaled the impact of both bugs by turning these endpoints into the primary call path for every tenant that opted into guided setup. Both bugs are now fixed with a parametrized SQL-compile regression test that runs offline and covers every affected subclass.

**BUG-608 — `GET /api/skill-providers/{skill_type}` leaked integrations across tenants.** Every per-subclass query (`CalendarIntegration`, `GmailIntegration`, `AsanaIntegration`, `GoogleFlightsIntegration`, `AmadeusIntegration`) previously filtered only by `is_active == True`. Any tenant member with `agents.read` could list every other tenant's active integrations — owner email, integration id, health status. Fixed: each query now joins `HubIntegration` on the shared primary-key id and filters `HubIntegration.tenant_id == ctx.tenant_id`. Per-row `HubIntegration` lookups that re-queried the parent table were removed; the already-joined polymorphic subclass row exposes `.name` / `.health_status` directly.

**BUG-609 — `PUT /api/agents/{agent_id}/skill-integrations/{skill_type}` accepted cross-tenant `integration_id`.** The route validated integration existence without checking tenant ownership (`HubIntegration.id == request.integration_id` only). An attacker who obtained a foreign integration id (trivially reachable through BUG-608) could wire that integration to one of their own agents. Fixed: lookup now requires both `HubIntegration.id == request.integration_id` and `HubIntegration.tenant_id == ctx.tenant_id`. The route returns `404` (not `400`) so integration existence cannot be probed across tenants via the error string.

**Regression coverage.** `backend/tests/test_skill_integration_tenant_isolation.py` (newly tracked — previously every `backend/tests/*` was local-only) contains 7 assertions that compile the exact SQLAlchemy queries used inside the route and check for `tenant_id = <caller>` in the rendered SQL. Run with `docker exec tsushin-backend python -m pytest tests/test_skill_integration_tenant_isolation.py -v --no-cov`. The SQL-compile approach matches the existing `test_memory_tenant_scoping.py` pattern — no database fixture or HTTP stack needed.

**Rebuild.** Backend-only: `docker-compose build --no-cache backend` + `docker-compose up -d backend`. WhatsApp / MCP sessions preserved.

### Kokoro TTS Hub consolidation + Config.tenant_id fix (2026-04-19)

Kokoro TTS management was split across two pages (`/settings/tts` for per-tenant instances + `/hub` for the legacy global compose service), which made the UX inconsistent with Ollama's in-Hub auto-provision flow and confused users who couldn't tell which page was authoritative. This change collapses everything into the existing Hub Kokoro card, mirroring the Ollama pattern, and fixes a latent `Config.tenant_id` AttributeError that was crashing `GET/PUT /api/settings/tts/default` at runtime.

**Backend — Config.tenant_id bug fix.** `backend/services/tts_instance_service.py` (`get_config_default` and `set_default`) and `backend/agent/skills/audio_tts_skill.py` (TTS base_url resolution path) were filtering `Config` rows with `.filter(Config.tenant_id == tenant_id)`, but the `Config` model has no `tenant_id` column — it is a singleton. That meant every call to the default-TTS endpoints and every Kokoro message with per-tenant override resolution would crash with `AttributeError: type object 'Config' has no attribute 'tenant_id'`. Fixed by querying `db.query(Config).first()` (the single row) and keeping tenant isolation on the INSTANCE side: `set_default` still validates that the target `TTSInstance.tenant_id == ctx.tenant_id` before accepting it, and `audio_tts_skill` now adds a `TTSInstance.tenant_id == tenant_id` filter as defense-in-depth so a globally-configured default cannot leak another tenant's instance. The `SELECT ... FOR UPDATE` row-lock in `set_default` is preserved; it now locks by `Config.id` instead of by `tenant_id`. The `default_tts_instance_id` FK is effectively global for v0.7.0; a schema migration adding per-tenant Config defaults can follow later.

**Frontend — consolidation.**

- `frontend/app/settings/tts/page.tsx` — **deleted**. The standalone page and its classic single-form modal no longer exist.
- `frontend/app/settings/page.tsx` — removed the "TTS / Speech Synthesis" settings card and the now-orphaned `tts` icon definition. The settings hub no longer links to a dedicated TTS page.
- `frontend/app/hub/page.tsx` — extended the existing Kokoro card (AI Providers tab) with a "Per-Tenant Instances" section above the demoted "Legacy (global compose Kokoro)" collapsed panel. New card UX:
  - `+ Setup with Wizard` CTA opens `KokoroSetupWizard` (unchanged 4-step flow — reused verbatim from the deleted page).
  - Instance list shows name + vendor + auto-provisioned + default badges, container status chip (running / creating / stopped / error), base_url in mono, and per-instance actions: Default radio (click to set as tenant default), Start / Stop / Restart (for auto-provisioned), Logs toggle with inline drawer + Refresh, Delete with remove-volume confirm dialog.
  - Container status for `creating` / `provisioning` instances polls `GET /api/tts-instances/{id}/container/status` every 3 s until terminal state, then triggers a full instance refresh.
  - Empty state renders "No Kokoro instances yet." with a Setup-with-Wizard button.
  - The legacy global-compose toggle (previously the only thing on the card) is still available but collapsed behind a "Legacy (global compose Kokoro)" expandable details section — preserved for installs still using the `docker compose --profile tts` pattern.
- The `KokoroSetupWizard.tsx` component was unchanged; only its mount point moved from `/settings/tts` to the Hub card. `onComplete` now triggers a full Kokoro instance list refresh on the Hub page.

**Backend warning text.** `tts_instance_service.provision_instance` fail-open warning text updated from "You can retry from Settings > TTS Instances." to "You can retry from Hub > AI Providers > Kokoro TTS." to match the new UX.

**Verified.**

- `docker exec tsushin-backend python -c "from services.tts_instance_service import TTSInstanceService; ..."` — confirmed both service methods no longer reference `Config.tenant_id`.
- Direct API tests (as `test@example.com`, tenant owner): `POST /api/tts-instances` (create) → `PUT /api/settings/tts/default` (set default — previously crashed) → `GET /api/settings/tts/default` (returns default with `is_default:true`) → `DELETE /api/tts-instances/{id}` → `GET /api/settings/tts/default` (returns `{default_tts_instance_id: null}` — FK auto-cleared by the delete). Full round-trip passes.
- Browser walkthrough via Playwright: `/hub` renders the consolidated Kokoro card with "Per-Tenant Instances" heading, `+ Setup with Wizard` CTA, empty state, and the collapsed "Legacy (global compose Kokoro)" toggle. Clicking "Setup with Wizard" opens the 4-step modal (What is Kokoro → Configure → Link Agents → Review & Create) with the step indicator tracking correctly. `/settings/tts` returns 404 as expected. `/settings` no longer lists the TTS card.

No schema changes, no volume impact. Backend + frontend rebuilt safely via `docker compose up -d --no-deps --build backend` and `docker compose build --no-cache frontend`.

### Kokoro TTS & Ollama setup wizards (2026-04-19)

Added guided multi-step creation wizards for the two local-container providers so users no longer have to juggle the classic single-form modal, the container lifecycle APIs, and the agent-skill configuration separately.

**Backend — two new "assign to agent" endpoints.**

- `POST /api/tts-instances/{id}/assign-to-agent` — body `{agent_id, voice?, speed?, language?, response_format?}`. Upserts the `audio_response` `AgentSkill` row for the target agent with `config = {provider: "kokoro", tts_instance_id, voice, language, speed, response_format}` and `is_enabled = true`. Tenant isolation is double-guarded on both the TTS instance and the agent; cross-tenant access returns 404 (same shape as missing resource to avoid leaking existence). Permission: `org.settings.write`. [`backend/api/routes_tts_instances.py`](backend/api/routes_tts_instances.py).
- `POST /api/provider-instances/{id}/assign-to-agent` — body `{agent_id, model_name}`. Sets `Agent.provider_instance_id`, `Agent.model_name`, and `Agent.model_provider` (to the instance vendor — typically `"ollama"`) in one call. Same double-guard tenant isolation pattern. Empty `model_name` returns 400. Permission: `org.settings.write`. [`backend/api/routes_provider_instances.py`](backend/api/routes_provider_instances.py).

**Frontend — two new wizard components.**

- `frontend/components/tts/KokoroSetupWizard.tsx` — 4-step modal (mirrors `MCPServerWizard.tsx`): What-is-Kokoro card → Configure (instance name, auto-provision, memory limit, voice/speed/language/format, set-as-default) → Link agents (multi-select with "Select all"/"Skip") → Review & Create. On submit: `createTTSInstance` → optional `setDefaultTTSInstance` → poll `/container/status` every 3 s until `running` (or `error`) → `assignTTSInstanceToAgent` per selected agent → close with success toast. Error states surface a Retry button. Keyboard: ESC closes, Enter advances on config/link/review steps.
- `frontend/components/ollama/OllamaSetupWizard.tsx` — 5-step modal: What-is-Ollama card → Configure container (instance name, GPU checkbox, memory limit) → Choose model (curated list of 7 models with params/disk/summary, plus Custom) → Link agents (multi-select) → Review & Provision. Orchestration: `ensureOllamaInstance` → `provisionOllamaContainer(gpu, mem)` → poll `/container/status` → `pullOllamaModel` → poll pull job (2 s tick, live % progress bar) → `assignOllamaInstanceToAgent` per selected agent → close. Three-stage progress indicator (Provision → Pull → Assign) with per-stage active/done states.

**Frontend — CTAs wired into existing pages.**

- `frontend/app/settings/tts/page.tsx` now shows two buttons in the header: "Create with Wizard" (primary teal) + "Advanced: Add Manually" (secondary, opens the existing classic modal). The wizard is a *supplement*, not a replacement — power users who know exactly what they want keep the single-form path.
- `frontend/app/hub/page.tsx` adds a "Setup with Wizard" button at the top of the Ollama card above the host/auto-provision radio. The existing inline auto-provision panel stays intact for users already past first-run onboarding.

**API client additions.**

- `api.assignTTSInstanceToAgent(id, data)` and `api.assignOllamaInstanceToAgent(id, data)` added to `frontend/lib/client.ts`, returning the updated skill or agent summary.

**Verified.**

- `docker exec tsushin-backend python -c "import api.routes_tts_instances; import api.routes_provider_instances"` → OK.
- Direct API tests (as `test@example.com`, tenant owner): 404 paths for missing instance / agent / wrong-tenant agent all return the expected `{"detail": "..."}` shape; empty `model_name` returns 400; valid assignments return 200 with the correct upserted row/agent config. Re-running an assignment on an agent that already has an `audio_response` skill updates the existing row (skill_id preserved) instead of creating a duplicate.
- Browser walkthrough via Playwright: both wizards open, step indicator advances (1 → ✓, current step highlighted), agent multi-select shows all tenant agents (9 in test tenant), review screen renders Instance / Voice Defaults / Agent Assignments / Container / Model sections with the current selections. ESC / X / backdrop close work. No new TypeScript errors in the Next build.

No schema changes, no volume impact. Safe per-service rebuild.

### Bug-Fix Sprint — BUG-594 to BUG-607 resolved (2026-04-19)

Closed the 11 remaining Open items on `develop` across the 2026-04-18 UI-Only Playground/Mini/Graph sweep, Sentinel + MemGuard audit, and Flows UI-First sweep. Per-bug evidence in [`BUGS.md`](../BUGS.md) under the matching Resolved entries.

**Fixed (grouped by root cause).**

- **DB pool exhaustion via `/api/readiness` — BUG-604, BUG-607, BUG-594.** `backend/api/routes.py:145–154` built a per-call `sessionmaker(bind=_engine)` and closed the session with **no `db.rollback()`** before `db.close()`. Under rapid readiness probing that leaked one `idle in transaction` connection per call — eventually saturating the pool, stalling `/api/auth/me` and `/api/auth/login` (BUG-604), and presenting the "edge hangs while containers report healthy" state (BUG-607) because `/api/health` is DB-free. The six post-login 502s in BUG-594 were downstream — the Caddy proxy reported upstream-unreachable while the Watcher dashboard fired six queries in parallel. Replaced the per-call sessionmaker with the module-level `get_session_factory()` (same factory FastAPI's `Depends(get_db)` uses) and added an explicit rollback-before-close. `for i in {1..200}; do curl -sk https://localhost/api/readiness; done` now leaves only 1 idle-in-transaction (the in-flight probe) versus unbounded growth before. [`backend/api/routes.py`](backend/api/routes.py).
- **Sentinel LLM call had no outer timeout — BUG-601.** Both `_call_llm` invocations in `backend/services/sentinel_service.py` (per-detection at `:1049` and unified at `:1340`) are now wrapped in `asyncio.wait_for(coro, timeout=config.timeout_seconds)`. The existing fail-closed (block mode) / fail-open (non-block mode) handler from BUG-LOG-020 catches `asyncio.TimeoutError` naturally, so a stalled Sentinel provider can no longer pin the Playground request's DB session indefinitely and amplify pool pressure. Added `import asyncio` at module top. [`backend/services/sentinel_service.py`](backend/services/sentinel_service.py).

**Fixed (localized).**

- **Flow tool config — BUG-605.** Flow-engine tool step merges both `parameters` and `tool_parameters` from the node config with `parameters = {**(_p), **(_tp)}` (later wins). The previous `config.get("parameters", config.get("tool_parameters", {}))` `dict.get` fallback never fired when the UI wrote **both** keys (the common case — `parameters={}` plus `tool_parameters={"query": "..."}`), so the built-in `google_search` step ran with `query=""` and returned HTTP 422. [`backend/flows/flow_engine.py`](backend/flows/flow_engine.py).
- **`asana_tasks` built-in removed — BUG-606.** The UI offered `Asana Tasks` in the Tool-step picker at two sites in `frontend/app/flows/page.tsx` and the backend declared its metadata in `backend/api/routes_flows.py:1296–1315`, but `FlowEngine._execute_builtin_tool` only dispatches `google_search` and `web_scraping` — everything else raised `Unknown built-in tool: asana_tasks`. Went with the graceful fix (removing the option from the UI + metadata) rather than wiring a new dispatcher: adding a real Asana task creator to the flow engine is a feature for v0.7.0, not a bug fix. Tenants who need Asana from flows today can use the scheduler skill, which is already backed by `backend/agent/skills/scheduler/asana_provider.py`. [`frontend/app/flows/page.tsx`](frontend/app/flows/page.tsx), [`backend/api/routes_flows.py`](backend/api/routes_flows.py).
- **Playground first-paint empty state — BUG-596.** Added `isLoadingAgents` (`true` initially, `false` in `loadAgents()`'s `finally`) and gated the "Select an Agent" empty state behind `!isLoadingAgents` in `ExpertMode`. Shows a dedicated "Loading agents…" spinner during the cached-then-fresh hydration instead of flashing `Agents 0` + a disabled selector. [`frontend/app/playground/page.tsx`](frontend/app/playground/page.tsx), [`frontend/components/playground/ExpertMode.tsx`](frontend/components/playground/ExpertMode.tsx).
- **Onboarding re-open / `/flows` overlay trap — BUG-595, BUG-603.** Two changes. (1) `OnboardingContext` auto-start timer now re-reads localStorage at fire time (`getCompletedForUser(key)`) before flipping `isActive=true` — refs can go out of sync on route changes but localStorage is the persistent source of truth. (2) `UserGuidePanel` backdrop/panel raised to `z-[200]` / `z-[201]` so route-level modals (Modal.tsx `z-50`, flow page modals `z-50`) can't stack over the Close Guide button. `OnboardingWizard` now short-circuits to `null` on auth/setup routes and when `state.hasCompletedOnboarding` is true (belt-and-suspenders). [`frontend/contexts/OnboardingContext.tsx`](frontend/contexts/OnboardingContext.tsx), [`frontend/components/UserGuidePanel.tsx`](frontend/components/UserGuidePanel.tsx), [`frontend/components/OnboardingWizard.tsx`](frontend/components/OnboardingWizard.tsx).
- **Graph View playground glow — BUG-597.** Pipeline verified correct end-to-end with Playwright + `MutationObserver` on `.react-flow__edge` / `.react-flow__node` class attributes during two independent live Playground Mini sends. Captured lifecycle on every send: T+0 `edge-active-cyan` + `agent-node-processing` applied → T+5s (MIN_AGENT_GLOW_DURATION) transitions to `edge-fading-cyan` + `agent-node-fading` + `channel-node-fading` → T+8s cleanup removes all classes. Earlier polling-based QA checks found 0 because they ran after the full 8-second cycle had already completed (agent responds in ~1-5s, glow minimum is 5s). No code change required. Original 2026-04-18 audit's 0-count observation is a derivative of Cluster B's backend instability (WebSocket drop during pool exhaustion eliminates events).
- **Sentinel benchmark dev-test script — BUG-600.** `backend/dev_tests/sentinel_fast_benchmark.py` called the removed `SentinelService._get_config()` and passed `content=` where the public `analyze_prompt` API expects `prompt=`. Replaced both with `sentinel.get_tenant_config() or sentinel.get_system_config()` and corrected the kwarg. The benchmark now runs past preflight and makes live Gemini calls per test case.

No schema migrations, no public API v1 contract changes, no volume recreation. Safe per-service rebuild; WhatsApp/MCP sessions preserved.

### Global-admin invitation flow + independent platform Google SSO (2026-04-18)

**Problem.** Three related gaps on the global-admin side. (1) The "Invite Member" UI in the tenant settings page returned an invitation link built from the *hashed* token stored in the DB instead of the raw token sent in the email, so the copy-link button in the success panel was broken. (2) Global-admin user management (`/system/users`) had no invite flow at all — only direct "+ Create User" with a plaintext password — and no way to pre-provision Google-SSO users. (3) Platform-wide Google SSO lived only in env-vars (`GOOGLE_SSO_CLIENT_ID/SECRET`), with no DB storage, no UI, no allowed-domains list, and no per-scope independence from tenant credentials.

**Added.**
- **`UserInvitation` schema extension** (Alembic `0036_invitation_scope_and_global_sso.py`). `tenant_id` and `role_id` became nullable; new columns `is_global_admin BOOLEAN NOT NULL DEFAULT false` and `auth_provider VARCHAR(16) NOT NULL DEFAULT 'local'`. The old `uq_tenant_email` hard unique index was replaced by a PostgreSQL partial unique index `uq_invitation_tenant_email_pending ON (tenant_id, email) WHERE accepted_at IS NULL` so the same address can be re-invited after an old invite accepts/expires. Two `CHECK` constraints (`ck_invitation_scope`, `ck_invitation_auth_provider`) encode the scope/shape invariants in the DB as well as the ORM. [`backend/alembic/versions/0036_invitation_scope_and_global_sso.py`](backend/alembic/versions/0036_invitation_scope_and_global_sso.py), [`backend/models_rbac.py`](backend/models_rbac.py).
- **`GlobalSSOConfig` singleton table** (same migration). Platform-wide Google SSO configuration — `google_sso_enabled`, `google_client_id`, `google_client_secret_encrypted` (Fernet, identifier `sso_client_secret_global`), `allowed_domains` (JSON array), `auto_provision_users` (stays `false` by default — global admins must be explicitly invited), `default_role_id`. Seeded with one empty row on upgrade; belt-and-suspenders startup hook in `backend/app.py` re-seeds if the row is ever deleted.
- **`POST /api/team/invite` accepts `auth_provider`.** `local` (default, user creates a password on accept) or `google` (user must accept via Google SSO with matching email). [`backend/api/routes_team.py`](backend/api/routes_team.py).
- **Global-admin invitation endpoints** at `/api/admin/invitations` (require_global_admin). `POST /` accepts `{email, tenant_id?, role?, is_global_admin, auth_provider, message?}`; enforces the scope shape in code and catches IntegrityError from the partial unique index as HTTP 409. `GET /` lists pending invitations with `is_global_admin`/`tenant_id`/`email_contains` filters. `DELETE /{id}` cancels. Audit-logged via `log_admin_action`. [`backend/api/routes_admin_invitations.py`](backend/api/routes_admin_invitations.py).
- **Global-admin SSO config endpoints** at `/api/admin/sso-config` (require_global_admin). `GET` masks the client secret by default; `?include_secret=true` returns the decrypted value. `PUT` upserts the singleton; secret is Fernet-encrypted using the same `encryption_key_service` path as `TenantSSOConfig`. [`backend/api/routes_admin_sso.py`](backend/api/routes_admin_sso.py).
- **Frontend — tenant invite form (`/settings/team/invite`)** gained a **Sign-in method** radio. The "Google SSO" option is disabled with a tooltip when the tenant has no Google SSO configured (prevents creating an invite the invitee can't accept). [`frontend/app/settings/team/invite/page.tsx`](frontend/app/settings/team/invite/page.tsx).
- **Frontend — global-admin `/system/users`** gained a primary **"Invite User"** button alongside the break-glass "+ Create User". Modal fields: email, role (includes **Global Admin**), tenant (hidden when role=Global Admin), auth method, optional message. Success view mirrors the tenant flow with a copy-able invitation link. A **Pending Invitations** section lists all outstanding invites (scope / role / auth / expires / Cancel). [`frontend/app/system/users/page.tsx`](frontend/app/system/users/page.tsx).
- **Frontend — accept page (`/auth/invite/[token]`)** rewrites the header to "Join Tsushin as Global Admin" + admin badge + "Platform-wide" organization row when the invitation is global-scoped. When `auth_provider === 'google'` the password form is hidden and only "Continue with Google" remains (with a tagline stating the Google email must match). A red dead-end banner replaces the button when a Google-only invite lands on a platform with Google SSO disabled. [`frontend/app/auth/invite/[token]/page.tsx`](frontend/app/auth/invite/[token]/page.tsx).
- **Frontend — global `/system/integrations`** gained a real **Platform-wide Google SSO** configuration section (distinct from the per-tenant settings page). Fields: `google_sso_enabled`, `google_client_id`, `google_client_secret` (write-only; shows `••• (unchanged)` placeholder when already set), `allowed_domains` (comma-separated ↔ JSON array), `auto_provision_users` (with bold-red warning copy — disabled by default), `default_role_id` (shown only when auto-provision is on). Setup-instructions card shows the OAuth redirect URI. [`frontend/app/system/integrations/page.tsx`](frontend/app/system/integrations/page.tsx).

**Changed.**
- **Fixed.** `backend/api/routes_team.py::invitation_to_response` now accepts a `raw_token` kwarg; `invite_team_member` and `resend_invitation` pass the raw token through so the UI-returned `invitation_link` is actually valid. Previously the link was built from `invitation.invitation_token` which is the SHA-256 hash stored in the DB — the emailed link worked but the copy-from-UI link did not.
- **`GoogleSSOService.get_oauth_credentials`** resolution order is now tenant `GoogleOAuthCredentials` → `GlobalSSOConfig` (when enabled) → `GOOGLE_SSO_CLIENT_ID`/`_SECRET` env-var fallback. Decrypting the global secret uses the `sso_client_secret_global` Fernet identifier; failure raises `GoogleSSOError` with a remediation hint instead of silently returning the ciphertext. [`backend/auth_google.py`](backend/auth_google.py).
- **Accept flow** (`POST /auth/invitation/{token}/accept` and `GoogleSSOService.find_or_create_user`) branches on invite fields: `auth_provider=google` rejects password-accept with 400; `is_global_admin=true` creates a user with `tenant_id=null`, `is_global_admin=true`, no `UserRole` row; Google-SSO accept of a `google` invite enforces `invitation.email == google.email` case-insensitively. An existing-user email match while presenting a global-admin invitation token is explicitly rejected so the invite cannot be used to silently upgrade a pre-existing account. [`backend/auth_routes.py`](backend/auth_routes.py), [`backend/auth_google.py`](backend/auth_google.py).
- **`/settings/integrations`** — removed the "Coming Soon" Microsoft 365 + Slack placeholder cards. Slack has had its own integration for several versions; Microsoft 365 is not on the near-term roadmap.

**Migration & fresh-install impact.** Existing rows default `auth_provider='local'` and `is_global_admin=false` at the DB (`server_default`), ORM (`default='local'`), and application (`invitation.auth_provider or "local"`) layers — pre-migration invites accept unchanged. Fresh installs run `alembic upgrade head` (via `init_database`) which includes `0036` and seeds the `global_sso_config` row; the startup hook in `app.py` re-seeds if the row is ever deleted. `install.py` is unchanged (only bootstraps `.env` + Docker).

**Tests.** `backend/tests/test_invitation_scope.py` — 14 pytest cases covering: raw-token link fix, Google-provider invite rejects password-accept, default `auth_provider='local'`, invalid `auth_provider` rejected, global-admin invite round-trip, shape/uniqueness/CHECK constraint enforcement, re-invite after accept, Google-SSO accept email mismatch, `GlobalSSOConfig` singleton GET/PUT, `require_global_admin` rejection for tenant owners. All passing.

### Invitation link portability — multi-tenant + ingress-aware (2026-04-19)

**Problem.** The invitation link returned to the UI and sent in emails was a bare path `"/auth/invite/<token>"` in API responses and `f"{FRONTEND_URL}/auth/invite/<token>"` in the email body. Under Cloudflare named tunnels (e.g. `https://tsushin.archsec.io`) the link either resolved to the wrong host (when the frontend prepended `window.location.origin` correctly but the backend's env-based email URL was stale) or leaked an internal hostname. Under multi-tenant deployments where one tenant has a `public_base_url` override and another does not, the backend used the *calling admin's* context instead of the *invitation's own tenant*.

**Added.**
- **`resolve_invitation_base_url(request, tenant=None)`** helper in `backend/services/public_ingress_resolver.py`. Multi-tenant-aware precedence chain: `tenant.public_base_url` (valid override) → platform Cloudflare tunnel → request origin (honoring `X-Forwarded-Proto` / `X-Forwarded-Host` so the named-tunnel hostname survives the Caddy reverse proxy) → `FRONTEND_URL` env → last-resort string. Always returns a non-empty origin with no trailing slash so callers can concatenate the token path directly.
- **`backend/tests/test_invitation_link_portability.py`** — 9 pytest cases covering override precedence, trailing-slash normalization, tunnel fallback, global-admin (no-tenant) path, `X-Forwarded-*` honoring, `http://localhost:3030` dev mode, invalid-override graceful fallthrough, and the non-None last-resort contract.

**Changed.**
- **`invitation_to_response`** (`backend/api/routes_team.py`) and **`_invitation_to_response`** (`backend/api/routes_admin_invitations.py`) now accept a `request` argument and return an **absolute `invitation_link`** built with the resolver. The invitation's OWN `tenant_id` is looked up — never the calling admin's context — so a global admin inviting Tenant-A users gets Tenant-A's public URL, not their own. Global-admin invites (`tenant=None`) skip the override branch entirely.
- **`send_invitation_email`** (`backend/services/email_service.py`) gained an optional `base_url` kwarg. Callers in both invite routes pass the resolved URL; the env-based `FRONTEND_URL` is now only a last-resort default.
- **`GET /api/auth/google/status`** (`backend/auth_routes.py`) now counts `GlobalSSOConfig` as "platform-configured" in addition to the legacy `GOOGLE_SSO_CLIENT_ID`/`_SECRET` env vars. Without this bridge, the tenant invite page's "Google SSO" radio was incorrectly disabled when the platform was configured only via the new global-admin UI.
- **Frontend** (`frontend/app/system/users/page.tsx`, `frontend/app/settings/team/invite/page.tsx`) now uses the absolute URL from the response verbatim, falling back to `window.location.origin` only when the backend returns a legacy relative path.

**Verification.** All 23 pytest cases pass (14 original + 9 new portability cases). Live API confirms `https://localhost` → `https://localhost/auth/invite/…`; direct backend with `X-Forwarded-Proto: https, X-Forwarded-Host: tsushin.archsec.io` → `https://tsushin.archsec.io/auth/invite/…`. Browser E2E covered global-admin invites (local + Google-only), tenant invites, and the platform-SSO section.

### Public Ingress Resolver — unified tenant-facing ingress URL (2026-04-18)

**Problem.** Three features each solved "what public HTTPS URL reaches this backend?" differently: `tenant.public_base_url` was a free-text string (no validation, no reachability check); the global Remote Access tunnel exposed its live `public_url` only to global admins; and `WebhookSetupModal` used `window.location.origin` at copy time, silently breaking when admins browsed via LAN IP. A running platform tunnel never benefited the features that needed it, and a tenant admin could paste any string into `public_base_url` with no guardrails.

**Added.**
- **`GET /api/tenant/me/public-ingress`** — authoritative resolver for tenant-facing callers. Returns `{url, source, warning, override_url}` where `source ∈ {override, tunnel, dev, none}`. Precedence: tenant override (when format-valid) > platform tunnel (when running) > `TSN_DEV_PUBLIC_BASE_URL` env (dev escape hatch) > none. Decoupled from the login-entitlement flag `tenant.remote_access_enabled` — ingress and login gating are now separate concerns. [`backend/services/public_ingress_resolver.py`](backend/services/public_ingress_resolver.py), [`backend/api/routes_tenant_settings.py`](backend/api/routes_tenant_settings.py).
- **Stricter `PATCH /api/tenant/me/settings` validation.** `http://` rejected unless `TSN_DEV_PUBLIC_BASE_URL` is set (dev flag); `user:pass@host` credential-laced URLs rejected explicitly; hostname must be a public FQDN (`localhost` / single-label rejected); DNS pre-resolution via async `loop.getaddrinfo` with a 2s timeout catches typos at save time instead of letting Slack/Discord deliveries fail silently later. Audit log entry added on every mutation via `log_tenant_event(..., TenantAuditActions.SETTINGS_UPDATE, ...)` with URL credentials scrubbed before logging (defense-in-depth).
- **`TSN_DEV_PUBLIC_BASE_URL` env var** for local dev without a Cloudflare tunnel. Process-start only. Wired through `docker-compose.yml`.

**Changed.**
- **`PublicBaseUrlCard`** renamed to **"Ingress Override (Advanced)"** and demoted to a collapsible `<details>` inside a status card. Always shows the currently-resolved URL and its source ("via platform tunnel" / "tenant override" / "dev environment"), with an amber banner and auto-expanded override input when `source === 'none'`. Resolver warnings (invalid stored override) surfaced inline. [`frontend/components/PublicBaseUrlCard.tsx`](frontend/components/PublicBaseUrlCard.tsx).
- **`SlackSetupWizard` + `DiscordSetupWizard`** now call `api.getMyPublicIngress()` instead of reading `tenant.public_base_url` directly. Both render a small source badge next to the detected URL. HTTP-mode banners point the user at the override card or Remote Access depending on the failure mode. [`frontend/components/SlackSetupWizard.tsx`](frontend/components/SlackSetupWizard.tsx), [`frontend/components/DiscordSetupWizard.tsx`](frontend/components/DiscordSetupWizard.tsx).
- **Webhook channel.** `frontend/app/hub/page.tsx` fetches the resolver-provided URL once and feeds both the inline "Inbound:" copy button (previously concatenated `window.location.origin`) and `WebhookSetupModal`'s `apiBase` prop.

**No schema / migration changes.** Existing tenants with an override preserve it automatically (`source=override`). Only new writes are subject to the stricter validation.

**Verification.** End-to-end on `develop`: resolver returns correct source in all precedence branches; PATCH rejects `http://` outside dev mode, credential-laced URLs, non-FQDN hostnames, and unresolvable DNS, while accepting valid `https://` URLs. UI verified via Playwright: Ingress Override card, Slack HTTP wizard, Discord welcome step, Webhook setup modal all render the resolver's URL and source badge.

### UI Recovery & Local Auth Stability (2026-04-18)

- **Stale-session recovery login:** frontend auth bootstrap now times out `GET /api/auth/me` after 8s and hard-redirects to `/auth/login?force=1&reason=session-recovery` instead of leaving protected routes stuck on `Loading Tsushin...`. The login page shows a recovery banner and performs a best-effort logout without blocking sign-in. [`frontend/contexts/AuthContext.tsx`](frontend/contexts/AuthContext.tsx), [`frontend/app/auth/login/page.tsx`](frontend/app/auth/login/page.tsx), [`frontend/lib/client.ts`](frontend/lib/client.ts), [`frontend/middleware.ts`](frontend/middleware.ts)
- **Local HTTP + HTTPS Google SSO parity:** auth cookies now derive the `Secure` flag from the actual request scheme, Google OAuth callback URLs are built from the request origin, and loopback HTTP entrypoints fall back to the configured local HTTPS callback when self-signed HTTPS is enabled. This keeps `https://localhost` Google SSO working and lets `http://127.0.0.1:3030` initiate the same flow without a separate Google redirect URI registration. Also removed a duplicate `TSN_SSL_MODE` compose env entry that blanked the backend SSL mode. [`backend/auth_routes.py`](backend/auth_routes.py), [`backend/auth_google.py`](backend/auth_google.py), [`docker-compose.yml`](docker-compose.yml), [`backend/tests/test_auth_security_fixes.py`](backend/tests/test_auth_security_fixes.py)
- **Postgres pool guardrail for stale tabs:** backend Postgres connections now set `idle_in_transaction_session_timeout` (default `15000ms`) so leaked read transactions from stale browser tabs cannot pin the full pool long enough to break `/api/auth/me` or Google SSO. [`backend/db.py`](backend/db.py), [`backend/settings.py`](backend/settings.py), [`docker-compose.yml`](docker-compose.yml), [`backend/tests/test_db_connection_guards.py`](backend/tests/test_db_connection_guards.py)

### Bug-Fix Sprint — BUG-589 to BUG-593 (2026-04-18)

Remediated the five `Open` findings from the 2026-04-17 UI-First Fresh-Install audit on `develop`:

- **BUG-589 — Remote Access public-hostname probe.** Named-tunnel start now runs a retrying `HEAD https://<tunnel_hostname>/api/health` probe (up to ~30 s) **after** `cloudflared_tunnel_ha_connections > 0` and gates the `state="running"` transition on it returning non-5xx. While the probe is outstanding the snapshot stays in a new `state="verifying"` with a clear message; on probe failure the tunnel is stopped and the admin sees the real error instead of a false "running" badge. [backend/services/cloudflare_tunnel_service.py](backend/services/cloudflare_tunnel_service.py), [backend/api/routes_remote_access.py](backend/api/routes_remote_access.py), [frontend/app/system/remote-access/page.tsx](frontend/app/system/remote-access/page.tsx), [frontend/lib/client.ts](frontend/lib/client.ts).
- **BUG-590 — Flow tool nodes accept slug strings.** `FlowEngine._execute_sandboxed_tool` now resolves non-numeric `tool_id` values via `SandboxedTool.name` (tenant-scoped, enabled-only — same lookup `routes_flows.py` uses at create/update time). Digit-string legacy ids still cast via `int()`. Mismatches raise a clean `"Sandboxed tool 'X' not found or disabled for tenant Y"` error instead of the cryptic `invalid literal for int()` crash. Verified end-to-end with an API v1 flow whose tool node declared `tool_name="webhook"` — flow ran to `status=completed`. [backend/flows/flow_engine.py](backend/flows/flow_engine.py).
- **BUG-591 — WhatsApp wizard stops flashing "Connected" before QR is scanned.** `WhatsAppWizardContext.setInstanceData()` no longer writes `stepsCompleted[2]=true` as a side-effect of instance creation — only the polling handler's `markStepComplete(2)` call (fired when `health.authenticated=true`) marks the step done. `StepCreateInstance` also re-verifies `/api/mcp/instances/{id}/health` before short-circuiting into the success state for a previously-created instance; if health reports not-authenticated it falls back to the QR-scan UI and resumes polling. Verified via Playwright against `https://localhost` — 23 DOM snapshots at 100 ms over 23 s after "Create", **0** "WhatsApp Connected!" frames. [frontend/contexts/WhatsAppWizardContext.tsx](frontend/contexts/WhatsAppWizardContext.tsx), [frontend/components/whatsapp-wizard/StepCreateInstance.tsx](frontend/components/whatsapp-wizard/StepCreateInstance.tsx).
- **BUG-592 — Playground image URLs persist across thread reload.** The image-cache block in `PlaygroundService` (sync-chat + streaming paths, skill-only AND full-agent branches) now runs **before** `memory_manager.add_message(...)` and injects `image_url`/`image_urls` into `memory_metadata`. `playground_thread_service._get_thread(...)` and `playground_service.get_conversation_history(...)` mirror the existing `audio_url` pattern: they surface `image_url`/`image_urls` from the message dict or `msg["metadata"]` on read. Verified via Playwright: image rendered on first send, then survived a navigate-away + hard reload; `GET /api/playground/threads/{id}` now returns the persisted URLs for the assistant message. [backend/services/playground_service.py](backend/services/playground_service.py), [backend/services/playground_thread_service.py](backend/services/playground_thread_service.py).
- **BUG-593 — Shellboy boots with the shell skill enabled.** `shell_skill_seeding` gained `_shell_is_enabled_default_for(db, agent)` which looks up the agent's `Contact.friendly_name` and, for names in `SHELL_ENABLED_AGENT_NAMES` (currently just `"shellboy"`), creates the `agent_skill(skill_type='shell')` row with `is_enabled=True`. Every other seeded agent keeps the default `is_enabled=False` opt-in posture. Both `seed_shell_skill_for_tenant` (fresh-install) and `backfill_shell_skill_all_tenants` (boot-time migration) apply the override — the backfill also flips any pre-existing disabled Shellboy rows. Verified via `SELECT ... FROM agent_skill` post-rebuild: Shellboy's `shell.is_enabled` is now `t`. [backend/services/shell_skill_seeding.py](backend/services/shell_skill_seeding.py), [backend/services/agent_seeding.py](backend/services/agent_seeding.py).

No schema migrations, no public API v1 contract changes, no volume recreation. All verification done against the local `develop` stack with a safe per-service `--no-cache` rebuild; WhatsApp/MCP sessions preserved.

### Playground Mini — floating quick-test bubble on every page (2026-04-17)

**Added: Playground Mini** — a compact floating chat bubble available on every authenticated page (Watcher, Studio, Hub, Flows, Core, Settings, System) so operators can fire a quick test against any agent without leaving their current page. Particularly useful while exploring the Watcher Graph view, editing a Flow, or inspecting a dashboard, where the friction of a full page switch used to discourage mid-task validation.

**Surface area & UX:**
- Circular FAB in the bottom-right (bottom-6 right-6, z-[70]) on every authenticated page. Route-gated: hidden on `/playground`, `/auth/*`, `/setup` so the full Playground is never duplicated.
- Expands to a 380×560 panel (mobile: inset-x-4 bottom-4 top-16) with `animate-scale-in`. `role="dialog"` `aria-modal="false"` (non-blocking — the page behind stays interactive).
- Header packs: agent dropdown, project dropdown (`(No project)` + all non-archived projects — selecting a project scopes the thread list to that `folder`), thread selector, new-thread ("+"), expand-to-full-Playground, close.
- Composer: auto-grow textarea (up to 4 rows). Enter = send, Shift+Enter = newline, Ctrl/Cmd+Enter = send. Disabled during in-flight.
- Assistant messages render through `react-markdown` + `remark-gfm` with a dedicated `.mini-markdown` stylesheet (compact p/h1–h4/strong/em/a/ul/ol/blockquote/code/pre/table/hr styles tuned for the tight bubble). User messages remain plain-text to preserve input.
- Pending state: three pulsing `tsushin-accent` dots in an assistant-style bubble while `sendMessage` is in-flight (sync HTTP — no WS state machine in the Mini, avoids a second always-on WebSocket connection from every page).
- Global hotkey: **Ctrl/Cmd + Shift + L** toggles the Mini (ignored when any `[role="dialog"][aria-modal="true"]` is focused). ESC closes the panel when focus is inside it and returns focus to the FAB.

**Expand handover — conversation carries over intact.** Clicking the expand icon navigates the user to `/playground?thread=<id>&agent=<id>&project=<id>`. The full Playground consumes those params on mount and lands the user on the exact same thread with the same messages already rendered, then strips the query string via `window.history.replaceState` without a React remount so future navigation works normally. Multiple iterations were required to get this right:
- Initial implementation used `router.replace('/playground', { scroll: false })` which invalidated the segment cache and remounted the page, wiping the `pendingThreadFromUrlRef` and causing the wrong (empty) thread to be auto-selected. Replaced with `window.history.replaceState(null, '', '/playground')` which updates the URL bar without triggering React.
- Second race: `loadAgents()`' default-agent auto-pick fired before the URL-sync effect populated the pending thread, so `initializeThreads` ran for the wrong agent. Fixed by seeding `selectedAgentId` from `window.location.search` via a lazy `useState` initializer at mount — beats `loadAgents()` by one render.
- Third race: the pending-thread consumption was split across two effects (`useSearchParams` + `[threads]`), so the ref could be null when `initializeThreads` checked it. Consolidated the claim inside `initializeThreads` itself: it reads `window.location.search` directly (not via `useSearchParams`), looks up the thread in the just-fetched `agentThreads`, selects it, strips the URL, and bails out before the empty-thread auto-pick / auto-create logic. A module-local `lastConsumedHandoverThreadRef` de-dupes repeat consumption within one session while still allowing a later expand with a different thread to work.

**Multi-tenant safety.** All data operations reuse the existing tenant-scoped endpoints (`GET /api/playground/agents`, `GET /api/projects`, `GET/POST /api/playground/threads`, `GET /api/playground/threads/:id`, `POST /api/playground/chat?sync=true`) — no new backend, no new auth paths. Selection state is persisted in sessionStorage keyed by userId (`tsushin:playground-mini:v1:<userId>`), and `AuthContext.logout()` clears it. Messages are never persisted client-side: they re-fetch from `api.getThread(activeThreadId)` on panel mount, which re-validates tenant ownership on every call.

**Thread auto-creation before send.** The first message sent when no thread is active creates a thread synchronously via `api.createThread(...)` before the chat POST, so the handover URL always has a valid `?thread=<id>` to deep-link into.

**Onboarding tour integration.** Bumped `TOTAL_STEPS` from 12 → 13. Added a new tour step 12 ("New: Playground Mini") targeting `[data-testid="playground-mini"]`. When the step becomes active the wizard applies the existing `.tour-highlight` class AND the new `.playground-mini-tour-glow` keyframe — a 1.4s × 3-iterations strong box-shadow pulse using `tsushin-accent` + `tsushin-indigo` that draws the eye to the FAB. The step's "Open Playground Mini" action dispatches `tsushin:playground-mini:open`, which `PlaygroundMini` listens for and re-applies the glow to the open panel. A MutationObserver on the FAB watches for the wizard's `.tour-highlight` toggle and triggers the glow automatically, so it also lights up if the wizard is relaunched from the header `?` button and advanced back to the Mini step. If the user happens to be on an excluded route (`/playground`, `/auth/*`, `/setup`) when they click the step's action button, the wizard first `router.push('/')` before dispatching the open event so the Mini actually renders.

**Files added:**
- [frontend/components/playground/mini/PlaygroundMini.tsx](frontend/components/playground/mini/PlaygroundMini.tsx)
- [frontend/components/playground/mini/PlaygroundMiniPanel.tsx](frontend/components/playground/mini/PlaygroundMiniPanel.tsx)
- [frontend/components/playground/mini/MiniHeader.tsx](frontend/components/playground/mini/MiniHeader.tsx)
- [frontend/components/playground/mini/MiniMessageList.tsx](frontend/components/playground/mini/MiniMessageList.tsx)
- [frontend/components/playground/mini/MiniStreamingMessage.tsx](frontend/components/playground/mini/MiniStreamingMessage.tsx)
- [frontend/components/playground/mini/MiniComposer.tsx](frontend/components/playground/mini/MiniComposer.tsx)
- [frontend/components/playground/mini/usePlaygroundMini.ts](frontend/components/playground/mini/usePlaygroundMini.ts)
- [frontend/lib/playgroundMiniSessionStore.ts](frontend/lib/playgroundMiniSessionStore.ts)

**Files modified:**
- [frontend/app/layout.tsx](frontend/app/layout.tsx) — mount `<PlaygroundMini />` beside `<ToastContainer />` inside `ToastProvider`.
- [frontend/app/playground/page.tsx](frontend/app/playground/page.tsx) — URL-seeded `selectedAgentId`, handover consumption inside `initializeThreads`, de-dupe ref, `history.replaceState` URL strip.
- [frontend/components/OnboardingWizard.tsx](frontend/components/OnboardingWizard.tsx) — new step 12 "New: Playground Mini" with action button dispatching `tsushin:playground-mini:open`.
- [frontend/contexts/OnboardingContext.tsx](frontend/contexts/OnboardingContext.tsx) — `TOTAL_STEPS: 12 → 13`.
- [frontend/app/globals.css](frontend/app/globals.css) — `.playground-mini-tour-glow` keyframe + `.mini-markdown` typography block.
- [frontend/contexts/AuthContext.tsx](frontend/contexts/AuthContext.tsx) — `logout()` clears Playground Mini sessionStorage.

**Verification:** Full E2E via Playwright against `https://localhost` covered 16 scenarios — FAB visibility scoping, open/close + animation, hotkey toggle with modal guard, ESC close + focus restoration, agent switch refreshes thread list, project switch filters threads by folder, new-thread button focuses composer, send/receive round-trip with thread auto-rename, markdown rendering (real `<ul><li><strong><code>` elements in the DOM — not raw Markdown text), expand handover preserves thread+messages on both cold URL navigation AND client-side `router.push` from the Mini, URL stripped post-consumption, no stray `POST /api/playground/threads` during handover, persistence across `/flows` navigation + hard refresh, second handover during the same session, zero frontend/backend errors, and the wizard glow trigger via both the active-step detection and the `tsushin:playground-mini:open` event. Non-audio agents only (Tsushin, Gemini1) per the QA spec. The only console noise is the pre-existing Playground WebSocket reconnect event (unrelated).

No backend changes. No schema changes. No new dependencies — `react-markdown` and `remark-gfm` were already in `frontend/package.json`.

### Flows — Create-from-Template modal: surface load errors (2026-04-17)

The "Create Flow from Template" modal previously rendered the same empty-state message ("No templates available.") whether the backend returned an empty list or the fetch failed (401, 403, 5xx, network). The `.catch` handler wrote the failure to `submitError`, but that state was only rendered inside the `preview` step, so on the initial `pick` step any failure was silently indistinguishable from an empty catalog. [frontend/components/flows/CreateFromTemplateModal.tsx](frontend/components/flows/CreateFromTemplateModal.tsx) now renders a red error banner in the `pick` step when `submitError` is set, and gates the "No templates available." message on `!submitError` so the two conditions are visually distinct.

No backend changes — flow templates remain a code-defined catalog in [backend/services/flow_template_seeding.py](backend/services/flow_template_seeding.py) (7 templates) exposed via `GET /api/flows/templates` and are not DB-seeded by design.

### Watcher Graph — BUG-596 fix + live-activity edge-glow scoping (2026-04-17)

**BUG-596 resolved.** `transformBatchToAgentsGraphData()` in [frontend/components/watcher/graph/hooks/useGraphData.ts](frontend/components/watcher/graph/hooks/useGraphData.ts) now gates the synthetic "WhatsApp Unassigned" placeholder behind `showWhatsAppUnassignedPlaceholder = tenantHasWhatsAppInstances || hasStaleWhatsAppBinding`. On a truly fresh tenant (zero WhatsApp instances, no stale `whatsapp_integration_id` pointing at a missing instance) the placeholder node and its dotted amber edges are suppressed. The placeholder still surfaces as a warning signal when a real stale binding exists. The gate wraps both the edge push and the node creation for defense-in-depth.

**Graph live-glow accuracy tightening (same change set).** The Watcher Graph previously rendered a perpetual dashed-marching stroke on every Playground→agent edge (via `animated: true` baked into the edge), implying constant fan-out communication that's physically impossible (Playground talks to one agent at a time). The dynamic activity-glow path at [GraphCanvas.tsx](frontend/components/watcher/graph/GraphCanvas.tsx) also used a loose `activeChannels.has(channel) || processingAgents.has(agent)` OR, which lit *every* edge on the active channel when *any* agent was responding. Four surgical changes:

- **Fix B — drop the static `animated` flag on Playground→agent edges.** The Playground edge now relies on CSS (`edge-active-cyan`) applied by the live-activity path, not a static animation. WhatsApp/Telegram/Webhook edges remain animated (instance-scoped channels are a reasonable "this connection exists" cue).
- **Fix C — channel→agent glow scoped to the `(channel, agent)` pair.** [useWatcherActivity.ts](frontend/hooks/useWatcherActivity.ts) now derives a `processingAgentChannels: Map<agentId, channelType>` from the same `processingSessions` map that already tracks per-agent state. [GraphCanvas.tsx](frontend/components/watcher/graph/GraphCanvas.tsx) checks `processingAgentChannels.get(targetAgentId) === channelType` instead of the loose OR, so only the one `channel-X → agent-Y` edge where agent Y is actually responding to a message on channel X glows.
- **Fix D — agent→skill glow scoped to skills actually invoked.** The agent→skill edge glow now matches `recentSkillUse.get(agentId).skillType` to the *specific* skill node's `skillType` (built into a per-node lookup via `getNodes()`), not every skill the agent owns. Category-level and provider-level glow apply the same match so the teal highlight traces the actual tool invocation path.
- **Type wiring.** `ActivityState` in [frontend/components/watcher/graph/GraphCanvas.tsx](frontend/components/watcher/graph/GraphCanvas.tsx) gained an optional `processingAgentChannels?: Map<number, string>`; [GraphViewTab.tsx](frontend/components/watcher/GraphViewTab.tsx) threads the new map through the `activityState` useMemo and its dependency array.

No backend changes — the WebSocket stream at `/ws/watcher/activity` already carried `channel` on `agent_processing` events ([backend/services/playground_service.py](backend/services/playground_service.py), [backend/agent/router.py](backend/agent/router.py), [backend/services/watcher_activity_service.py](backend/services/watcher_activity_service.py)); the gap was purely in the frontend render-decision layer.

Verification: Fix A validated via live API intercept in the browser against the current tenant's `/api/v2/agents/graph-preview` response — simulating the fresh-install scenario (`channels.whatsapp: []`, all 7 agents with `whatsapp_binding_status: 'unassigned'`) resolves `showWhatsAppUnassignedPlaceholder` to `false`; simulating the stale-binding scenario (0 instances, 1 agent with `whatsapp_integration_id = 999` pointing at a missing instance) resolves it to `true`; current-tenant baseline (1 instance, all agents explicitly bound) is unchanged. Frontend rebuilt `--no-cache` and container reports healthy. Noted an unrelated pre-existing issue where React Flow renders 0 edge paths despite the hook returning 14 edges (same behavior on the unchanged baseline codebase — not part of this fix; tracked separately).

### Ubuntu VM fresh-install audit — docs and bug-log update only (2026-04-17)

Completed an audit-only regression pass against a fresh Ubuntu 24.04 VM install of `develop` using the interactive installer, self-signed HTTPS on `https://10-211-55-5.sslip.io`, browser automation, direct API checks, and a generated API v1 client. The install path itself succeeded, `/setup` completed normally, hosted-provider setup passed for Gemini/OpenAI/Anthropic/Vertex plus Brave/Tavily/SerpAPI, and the audit confirmed working baseline behavior for API v1 auth/chat, vector-store auto-provisioning, isolated/shared memory, knowledge-base retrieval, A2A communication, Watcher Security, Watcher A2A Comms, and the Shell Command Center UI.

The session produced tracker/playbook updates only; no product code changed. New findings were recorded in the internal bug tracker as BUG-589 through BUG-596: Tavily runtime search mismatch, two broken shipped flow templates, `/api/v2/agents/` returning 500, webhook queue contract/provider-instance regressions, shell-beacon self-signed TLS failure, and Graph View rendering `WhatsApp Unassigned` on a zero-instance install. The run also reconfirmed open BUG-538 (`tsushin-toolbox:base` still missing on fresh install), which surfaced in-browser as `GET /api/toolbox/status` returning 500 and continued to block script skills, MCP stdio flows, and sandboxed tool execution.

Updated the internal deployment test playbook to cover self-signed HTTPS first-run installs, runtime-vs-Hub provider checks, Graph negative assertions, webhook dead-letter inspection, shell-beacon TLS behavior, flow-template execution, generated-client verification, and protected API v2 smokes. Added a durable operator note to [docs/documentation.md](docs/documentation.md) explaining that shell beacons do not bypass TLS validation on self-signed HTTPS installs and therefore require trusted certificates or a local HTTP-only smoke path for QA.

### QueuePool exhaustion hardening — BUG-588 resolved (2026-04-17)

Eliminated a long-standing `QueuePool limit of size 20 overflow 30 reached, connection timed out` backend deadlock that wedged every request after ~3 h of uptime. Root cause: SQLAlchemy 2.0 `autobegin` starts an implicit transaction on the first SELECT; if the request path never commits/rolls back, the connection returns to the pool in `idle in transaction` state because `pool_reset_on_return='rollback'` only fires on checkin — and every `def get_db()` duplicate in the per-router modules built a fresh `sessionmaker` on each call, extending the Session object's lifetime enough to keep the connection pinned. In real traffic the backend eventually exhausted all 50 slots and every `/api/auth/me` hung → the frontend sat on "Loading Tsushin..." indefinitely for any browser with an auth cookie (incognito worked because no cookie → fast 401 → no DB lookup).

Fix applied at three layers:

1. **Architectural (one root-cause change).** `backend/db.py` now caches a single module-level `_global_session_factory` inside `set_global_engine()` instead of rebuilding a `sessionmaker` per-call. `get_db()` always runs `try: db.rollback(); except: pass` in `finally` before `db.close()` so the implicit transaction ends cleanly. A new `session_scope()` context manager (commits on clean exit, rolls back on exception, always closes) is now the canonical helper for background tasks and non-request code paths.
2. **Per-router safety-net.** The 28 `backend/api/routes_*.py` modules that define their own local `def get_db()` copy received the same rollback-before-close guard, so even routers that don't migrate to the global dependency yet are protected.
3. **Background-service safety-net.** `channel_health_service._check_all_instances()` and `mcp_server_health_service._check_all_servers()` both now rollback before `close()` in their finally blocks — prevents the health-loop itself from contributing to the leak it's supposed to detect.

Verified: pool stays at `(active,1) (idle,20) (idle in transaction,≤1)` under 25-parallel load, zero `QueuePool` errors for 10+ min post-rebuild, `/api/health` + `/api/readiness` + OAuth2 + v1 agent/skill/tool/persona/tone-preset sweeps all 200, `/tool dig` sandboxed tool returns correct DNS records, WhatsApp tester→bot round-trip confirmed, browser normal-mode UI renders past the loading splash in <2s (previously stuck indefinitely). Files: [backend/db.py](backend/db.py), [backend/services/channel_health_service.py](backend/services/channel_health_service.py), [backend/services/mcp_server_health_service.py](backend/services/mcp_server_health_service.py), plus 28 router modules under [backend/api/](backend/api/). Documented as BUG-588 in [BUGS.md](BUGS.md).

### Onboarding wizard — v0.6.0 "What's New" showcase (2026-04-17)

The fresh-install onboarding tour now opens with four showcase pages covering the features shipped in v0.6.0 before the existing Watcher → Studio → Hub → Channels → Flows → Playground walkthrough begins. `TOTAL_STEPS` moved from 8 → 12; the auto-start trigger, localStorage keys, and user-guide coordination are unchanged so existing users who already completed the tour are **not** re-prompted (they can relaunch from the `?` button in the header). Each showcase page was written from a live inventory of the v0.6.0 codebase so the copy names the *actual* capabilities (providers, transports, auth modes, vector-store vendors, memory types, etc.) rather than a reductive summary.

- **Step 2 — Nine AI Providers, One Hub.** Covers all nine LLM vendors (Anthropic, OpenAI, Gemini, Vertex AI, Groq, Grok, DeepSeek, OpenRouter, Ollama) plus the three TTS engines (OpenAI TTS, Kokoro, ElevenLabs), multi-instance-per-vendor, System AI split, Fernet-encrypted credentials, SSRF validation, model discovery, ProviderConnectionAudit, and model-pricing-driven Billing. Action: `/hub?tab=ai-providers`.
- **Step 3 — Slack, Discord, Webhooks & More.** Covers the six active channel adapters (WhatsApp MCP Docker, Telegram, Slack Socket/HTTP, Discord Gateway with Ed25519 verification, HMAC-signed Webhooks, Playground), per-channel health + circuit breakers, per-agent `enabled_channels` routing, group/number filters, dm_auto_mode, inline Sentinel, and Cloudflare Tunnel remote access. Action: `/hub?tab=communication`.
- **Step 4 — Custom Skills & MCP Servers.** Covers all three skill variants (Instruction markdown, Script in the sandboxed Toolbox container in Python/Bash/Node, MCP Server over SSE / HTTP-streamable / stdio), execution modes (tool, hybrid, passive, instruction), semantic versioning, Sentinel scanning, trust levels, MCP tool-discovery namespacing, per-tenant isolation, and the built-in `/tool` runner. Action: `/agents/custom-skills`.
- **Step 5 — A2A & Long-Term Memory.** Covers the AgentCommunicationSkill (ask / list_agents / delegate with depth guards), all four vector store vendors — Qdrant and MongoDB *both* auto-provisioned in Docker locally, MongoDB Atlas and Pinecone BYO, ChromaDB as built-in fallback — plus OKG memory types (fact/episodic/semantic/procedural/belief), MemGuard audit, SharedMemory ACL, MMR reranking + temporal decay, isolation modes, knowledge-base document ingestion (PDF/DOCX/TXT/CSV/JSON), and per-agent VS override. Action: `/hub?tab=vector-stores`.

Files: [frontend/components/OnboardingWizard.tsx](frontend/components/OnboardingWizard.tsx) (four new `TourStep` entries inserted between the Welcome step and the Watcher step, plus renumbered `// Step N` comments on the seven remaining steps) and [frontend/contexts/OnboardingContext.tsx](frontend/contexts/OnboardingContext.tsx) (`TOTAL_STEPS = 12` with a v0.6.0 comment alongside the existing BUG-319 note). `docs/documentation.md` "Setup Wizard" entry 5 updated to reflect the new 12-step structure and enumerate the showcase pages.

### Bug-Fix Sprint (2026-04-17) — BUG-582 to BUG-587 resolved

All six findings from the same-day dual-stack fresh-install audit were remediated end-to-end on `develop`. Per-bug verification (curl + SQL + simulated installer run) passed and regression smoke tests (health, readiness, OAuth2, v1 sync chat, sandboxed-tool `/tool dig`, UI playground `/help`) came back clean with zero backend ERROR/CRITICAL/Traceback post-rebuild (only a pre-existing `Qdrant (q1) connection failed` that was already present and correctly falls back to ChromaDB — unrelated to this sprint).

- **BUG-582 — Installer volume-collision guard.** `install.py` `run_docker_compose()` now calls `_check_postgres_volume_collision()` before any Docker action. If the stack's postgres volume already exists and the current `.env` did **not** preserve a POSTGRES_PASSWORD from a previous install (per the BUG-566 helper), the installer aborts with a clear three-option remediation message: copy the original `.env`, isolate via `TSN_STACK_NAME=<alt>`, or destroy the volume after backing up. Non-destructive — we never remove the volume on the user's behalf.
- **BUG-583 — `/help` routes through the central registry.** Removed `/help` + `/ajuda` from `ProjectCommandService.BUILTIN_PATTERNS` and from `seed_project_command_patterns` in `backend/db.py`. The seeder also gained a drift-fix that rewrites the stored regex on startup when it diverges from the seed, so already-installed tenants pick up the new behavior on restart. `routes_playground.py` was also corrected to read the `"message"` dict key (`"response"` never existed on these service returns, so the old fallback always fired). `/help` now returns the full 36-command registry grouped by category; bare `project help` / `ajuda do projeto` still render the project-specific help template.
- **BUG-584 — `/inject` parser isolation.** `_handle_inject` consumes only the **first** whitespace-delimited token as the command arg (the multi-token loop that let later tokens overwrite earlier ones is gone). A `=`-containing first token surfaces a friendly error explaining that `/inject` replays recorded tool executions and does not set context variables — pointing users at `/inject list`, `/inject <id>`, `/inject <tool_name>`. Regression-safe: `/inject list`, `/inject clear`, `/inject 42`, `/inject #42`, `/inject toolname` all continue to work.
- **BUG-585 — Custom-skills schema hardening.** `CustomSkillCreate` and `CustomSkillUpdate` in `backend/api/routes_custom_skills.py` now declare `class Config: extra = "forbid"`. `instructions_md` accepts `instruction` as a Pydantic v2 `validation_alias=AliasChoices("instructions_md", "instruction")` so the common misspelling still produces a usable record. Verified: unknown fields → 422 `extra_forbidden`; `instruction` alias → 201 with `instructions_md` correctly populated.
- **BUG-586 — Seed agents wired to default vector store.** In the setup-wizard path (`backend/auth_routes.py`, Step 7), right after `create_default_setup_instance()` succeeds **and** no provisioning warning was raised, every tenant agent with `vector_store_instance_id IS NULL` is linked to the fresh default VS's id. Wrapped in try/except that rolls back and logs on failure without blocking setup. New fresh-install tenants now have long-term memory wired automatically.
- **BUG-587 — Flow schema hardening.** Added `class Config: extra = "forbid"` to `FlowCreate`/`FlowUpdate` in `backend/schemas.py` and `FlowDefinitionCreate`/`FlowDefinitionUpdate` in `backend/api/routes_flows.py`. Legacy `POST /api/flows` now returns 422 for `steps`/`trigger_type` instead of silently dropping them; v2 `POST /api/flows/create` (which accepts `steps`) continues to return 201.

Documentation updates: `BUGS.md` header bumped to 537 resolved, each bug's status flipped to Resolved with a **Fix (2026-04-17)** block describing the patch + verification. `docs/documentation.md` section on slash commands + API schemas updated below.

### macOS v0.6.0 Dual-Stack UI-First Fresh-Install Regression (2026-04-17) — 6 new findings (BUG-582 to BUG-587)

Second consecutive audit against `develop @ 6d0ad48` (the v0.6.0 release line). Original production stack stopped via `docker compose stop` + `docker stop` on dynamic MCP/toolbox containers so WhatsApp session state + all 24 `tsushin-*` volumes were preserved. Fresh install provisioned into an isolated `TSN_STACK_NAME=tsushin-fresh` stack on alternate ports 8091/3091; installer still crashes against the default stack name whenever `tsushin-postgres-data` already exists (BUG-582). Original stack fully restored at end of run — fingerprint matches pre-flight snapshot byte-for-byte and WhatsApp agent session auto-reconnected without a QR loop.

Validated this pass: 5 LLM/search providers configured + 4 LIVE `POST /test-connection` (Gemini / Anthropic / OpenAI / Vertex AI 1.3–2.5 s), auto-provisioned default Qdrant VS, playground chat round-trip with Gemini response, Sentinel prompt-injection + memory-poisoning both triggered (threat_score=0.9, `action=allowed` in detect-only mode), `/tool dig lookup domain=example.com` returned correct A-records, API client creation → OAuth2 token → X-API-Key `/api/v1/agents/{id}/chat` sync chat OK, Cloudflare tunnel orchestration (cloudflared live PID + public URL edge resolves), MCP agent + tester containers provisioned with QR generation in < 30 s. WhatsApp round-trip scan-and-send skipped (autonomous run; previously covered by BUG-575..581 sprint against same codebase).

All six new bugs **open**, queued for the next remediation sweep. Full detail in `BUGS.md`.

- **BUG-582** (Critical) — Fresh installer fails with `FATAL: password authentication failed for user "tsushin"` on stack `tsushin` when the postgres volume already exists from a prior install. BUG-566's password-preservation fix only reads the same directory's `.env`, not cross-worktree state. Work-around: set `TSN_STACK_NAME=tsushin-fresh` + `COMPOSE_PROJECT_NAME=tsushin-fresh` + alt ports in generated `.env`.
- **BUG-583** (Medium) — `/help` slash command only lists `/list, /enter, /exit, /help`. `/tool`, `/inject`, `/skill`, `/agent`, `/thread`, `/bookmark` are implemented and functional but invisible to new users.
- **BUG-584** (Medium) — `/inject secret_code=alpha-bravo-9 then what is the secret_code?` parses to `No "secret_code?" executions found` — argument parser fuses trailing punctuation into the key and treats the natural-language suffix as a separate command lookup.
- **BUG-585** (Medium) — `POST /api/custom-skills` with `instruction` field returns `201` but persists `instructions_md: null` and `script_content: null`. Field name mismatch silently drops payload; `Config.extra` not `forbid`.
- **BUG-586** (High) — Seeded agents have `vector_store_instance_id=NULL` despite `vector_store_mode='override'` — the auto-provisioned default Qdrant VS is not wired to Tsushin/Kokoro/etc. Long-term memory dead out-of-the-box for every first-time user.
- **BUG-587** (Medium) — `POST /api/flows` with `steps: [...]` returns `201` with `node_count: 0`. `FlowCreate` schema doesn't declare `steps`/`nodes`, so the array is silently dropped.

Environment fully reverted at end of run — `docker ps | grep tsushin` matches the pre-flight fingerprint; 24 `tsushin-*` volumes unchanged; WhatsApp agent MCP reports `✅ Connected to WhatsApp` + keepalive on startup (no QR re-auth required).

### Bug-Fix Sprint (2026-04-16) — BUG-575 to BUG-581 resolved

Seven bugs surfaced by the same-day fresh-install regression were remediated and validated under a full regression sweep on the restored production stack. Zero backend errors during the run; Cloudflare tunnel now starts cleanly and `https://tsushin.archsec.io` serves the app end-to-end through the new Caddy reverse proxy.

- **BUG-575 — Migration 0034 idempotency.** `backend/alembic/versions/0034_add_tenant_public_base_url.py` wrapped in `inspect(bind).get_columns("tenant")` guards for both `upgrade()` and `downgrade()`, matching the pattern already used by 0035. Fresh installs and replayed upgrades both no-op correctly when the column is already present.
- **BUG-576 — Caddy reverse proxy shipped in base compose.** New `proxy` service (caddy:2-alpine, container `${TSN_STACK_NAME:-tsushin}-proxy`) added to `docker-compose.yml` with `depends_on` on backend+frontend healthy and a wget-based healthcheck. New `proxy/Caddyfile` routes `/api/*` + `/ws/*` → `backend:8081` and everything else → `frontend:3030` using `handle` matchers (no prefix-stripping/rewrite round-trip). `docker-compose.ssl.yml` slimmed to an SSL overlay only — `volumes: !override` replaces the Caddyfile/certs mount set cleanly so no duplicate `/etc/caddy/Caddyfile` mount points. Cloudflare named-tunnel `POST /api/admin/remote-access/start` now resolves `http://<stack>-proxy:80` and the live public URL responds 200.
- **BUG-577 — Vertex AI field normaliser.** New `backend/utils/vertex_config.py` exposes `normalise_vertex_config(api_key, extra_config)` + `VERTEX_CONFIG_ERROR`. Accepts `api_key` as either raw PEM or a full service-account JSON blob (extracting `private_key`/`client_email`/`project_id` from the JSON) and accepts both `sa_email`/`service_account_email` and `region`/`location` aliases in `extra_config`. Both call sites in `backend/agent/ai_client.py` (instance + flat-config path) and the test-connection branch in `backend/api/routes_provider_instances.py` use the helper + shared error constant. Error message now names the actual accepted fields.
- **BUG-578 — 8-char dev credentials everywhere.** `backend/ops/create_test_users.py` seeds `test1234` / `admin1234` / `member1234`. All test fixtures (`test_api_v1_e2e.py`, `test_new_providers.py`, `test_auth_security_fixes.py`) and all pushed docs (`.claude/agents/qa-tester.md`, `methodology/METHODOLOGY.md`, `methodology/commands/fire_{,_full_}regression.md`, `deployment-test-playbook.md`) updated to match the setup wizard's own 8-char minimum.
- **BUG-579 — Cross-origin cookie.** Resolved by the BUG-570 same-origin rewrite (see the Post-Install Bug Sweep entry above); re-verified on this sprint's post-fix stack via the public tunnel URL (0 console errors, clean login round-trip).
- **BUG-580 — Flow templates `required_params` populated.** `backend/services/flow_template_seeding.py` `FlowTemplate.to_summary()` now emits a `required_params` array derived from the subset of `params_schema` where `required=True`, listing `{name, type, label, description}` for each. Single source of truth — the same `params_schema` still drives `_validate_template_params`, so metadata and validation cannot drift.
- **BUG-581 — `POST /api/clients` scopes shorthand honored.** `backend/api/routes_api_clients.py` request schemas gain an optional `scopes: List[str]` field. New `_resolve_scopes_shorthand(...)` helper: single-element list containing a known role → `role=<that_name>`; multi-element list → `role="custom"` + `custom_scopes=<list>`; invalid shorthand → HTTP 400. Explicit `role`/`custom_scopes` override the shorthand. Existing service-layer escalation guard still enforces "you cannot grant scopes you don't hold". Update path now fetches `AuthService.get_user_permissions` once instead of twice.

**Verification:** full regression sweep on the restored production stack — infrastructure 3/3, tenant sweep 26/26, admin sweep 5/5, API v1 OAuth + sync chat OK, sandboxed-tool `dig google.com A` OK, WhatsApp round-trip (tester → agent → tester) OK, UI login via public Cloudflare tunnel with 0 console errors. Backend logs: zero ERROR/CRITICAL/Traceback post-rebuild.

### macOS v0.6.0 Fresh-Install Full Regression (2026-04-16)

Autonomous end-to-end regression on a clean `git clone --branch v0.6.0` running under an isolated `tsushin-fresh` stack (ports 8091/3091). The local production stack was stopped and later restored bit-for-bit; volume `tsushin-postgres-data` was never touched. Coverage: installer idempotency, setup wizard, LLM provider onboarding (Anthropic / OpenAI / Gemini / Ollama all healthy; Vertex deferred), auto-provisioned Qdrant vector store, memory recall, knowledge-base upload, Sentinel prompt-injection detection, sandboxed-tool execution (`dig` command), custom skills, A2A permissioning, API v1 OAuth2 + sync chat, programmatic flow creation, full UI sweep of Watcher / Studio / Hub / Flows / Playground / Core (0 console errors when accessed via same-origin LAN IP), WhatsApp QR onboarding for both agent + tester instances, and a full WhatsApp round-trip (`Hi Tsushin` → `Hello!` and `/tool dig lookup domain=example.com` → rendered dig output back on the tester phone). 21 feature rows exercised; 34/35 admin + tenant API endpoints returned 2xx.

Seven new bugs were filed (BUG-575 through BUG-581) — all open, queued for the next remediation sweep. See `BUGS.md` for full detail.

- **BUG-575** (Critical) — Alembic migration `0034_add_tenant_public_base_url.py` is non-idempotent; blocks `python3 install.py --defaults --http` on a pristine v0.6.0 clone (`DuplicateColumn` on `tenant.public_base_url`). Patched inline during this run so the rest of the matrix could execute; a proper fix needs to land in `develop` before the next release tag.
- **BUG-576** (High) — Cloudflare named-tunnel feature cannot start on a fresh install: `docker-compose.yml` ships no Caddy/NGINX proxy service, but `cloudflare_tunnel_service.py` hard-refuses any `target_url` other than `http://<stack>-proxy:80`.
- **BUG-577** (Medium) — Vertex AI test-connection error message names fields (`service_account_email`) that the code does not actually read (expects `extra_config.sa_email`, `extra_config.region`, raw PEM in `api_key`); onboarding stalls for users who follow the error verbatim.
- **BUG-578** (Low) — `CLAUDE.md` documents 7-char dev passwords (`test123` / `admin123`) but the setup wizard enforces an 8-char minimum, breaking copy-paste onboarding.
- **BUG-579** (High, resolved) — Installer auto-detects the host LAN IP and bakes it into `NEXT_PUBLIC_API_URL`; browsers that open `http://localhost:3091` then hit cross-origin 401s on every API call because the session cookie was set on the LAN-IP origin. Already fixed by the same-origin Next rewrites under BUG-570 (see the Post-Install Bug Sweep entry below); kept on record against the shipped v0.6.0 tag.
- **BUG-580** (Medium) — Every entry from `GET /api/flows/templates` returns `required_params: []`, but `/instantiate` surfaces required fields one at a time (`name`, `agent_id`, `recipient`, …), making programmatic instantiation a guessing game.
- **BUG-581** (Medium) — `POST /api/clients` silently discards the requested `scopes` array and always assigns the `api_agent_only` role; `api_owner` capability cannot be provisioned through the API itself.

Environment fully restored at end of run — `docker ps` matches the pre-flight snapshot (backend, frontend, postgres, docker-proxy, proxy, agent + tester MCP containers, toolbox, qdrant-vs all running). No commits to release artifacts in this session; documentation-only change.

### Post-Install Bug Sweep (2026-04-16)

Nine bugs surfaced by a clean `python3 install.py --defaults --http` run on commit `5bf7b03` of `develop`, grouped into four remediation phases and validated end-to-end in real Chrome before ship.

### Backend — installer idempotency, missing migrations, search observability

- **BUG-1 — Installer now preserves secrets across re-runs.** `install.py:1299-1339` reads the existing `.env` (via the pre-existing `_read_env_file_vars()` helper at `install.py:241-255`) and only generates fresh values for `POSTGRES_PASSWORD`, `JWT_SECRET_KEY`, and `ASANA_ENCRYPTION_KEY` when those keys are missing. Previously every re-run rolled the postgres password while the postgres data volume still had the old one — producing `FATAL: password authentication failed for user "tsushin"` and a backend crash loop. Also protects every Fernet-encrypted secret in the DB from being orphaned by a rotated `ASANA_ENCRYPTION_KEY`.
- **BUG-2 + BUG-3 — Missing Alembic migration for two live model columns.** New migration `backend/alembic/versions/0035_add_missing_provider_whatsapp_columns.py` idempotently adds `provider_instance.extra_config` (JSON, default `{}`) and `whatsapp_mcp_instance.display_name` (VARCHAR(100)) using the `Inspector.get_columns()` guard pattern from `0006_add_provider_instances.py:81-88`. Fresh installs were masked by `0001_initial_baseline.py`'s call to `Base.metadata.create_all()`; upgrades from any prior version 500'd on Hub → add-LLM-provider, on agent config loading, and on the channel health monitor crash-looping every cycle.
- **BUG-9 — Web search now logs the provider.** A single `🔍 Web search: provider={name}, query={query[:120]}` line is emitted at INFO level (plus `print()` for docker-stdout visibility) from all three search code paths: `backend/services/search_command_service.py:146`, `backend/agent/skills/search_skill.py:210/594`, and `backend/agent/tools/search_tool.py:62`. Matches the existing `🤖 AIClient.generate(): provider=…` convention at `backend/agent/ai_client.py:377`. Ops can now tell whether a query went to Brave, SerpAPI, or Tavily without digging through provider-registry state.

### Frontend — cross-origin cookie fix (BUG-5, BUG-7, BUG-8) and WebSocket same-origin

Root cause for all three was `NEXT_PUBLIC_API_URL` being baked into the build as an absolute URL (e.g. `http://127.0.0.1:8081`). Browser requests went cross-origin when the user accessed the frontend on a different host/port, and the httpOnly session cookie was silently dropped → 401 cascade. Fix makes all client-side API calls **same-origin relative** through a Next.js 16.2.2 rewrite layer.

- `frontend/next.config.mjs` — new `async rewrites()` proxies `/api/:path*` and `/ws/:path*` to `BACKEND_INTERNAL_URL` (defaults to `http://backend:8081`) over the internal Docker network. Works for both HTTP and WebSocket upgrades.
- `frontend/lib/client.ts:19-30` — `resolveApiUrl()` returns `''` in the browser so every existing `${API_URL}/api/foo` call becomes a relative `/api/foo` request with zero call-site changes. SSR keeps the absolute URL for internal-network rendering.
- `frontend/hooks/useWatcherActivity.ts:197-205` and `frontend/lib/websocket.ts:38-50` — build WS URLs from `window.location.host` so the upgrade stays same-origin. `WebSocket('')` is guarded.
- **20 files** updated to drop the baked `process.env.NEXT_PUBLIC_API_URL || 'http://…:8081'` prefix: all of `app/hub/**/page.tsx`, `app/settings/{security,model-pricing,integrations,ai-configuration}/page.tsx`, `app/playground/page.tsx`, `app/auth/sso-callback/page.tsx`, every component in `components/playground/*`, `components/{LayoutContent,ContactManager,ApiKeyManager}.tsx`, and `components/watcher/BillingTab.tsx`.
- `frontend/components/playground/MemoryInspector.tsx:124-131` — replaced `new URL(…)` (which throws `Invalid URL` when the base is an empty string) with `URLSearchParams` + plain-string path construction.
- `docker-compose.yml` — added `BACKEND_INTERNAL_URL` to the frontend service environment.

With the rewrite layer in place, **Bug 6 (Graph View activity glow) required no code change** — the Watcher activity WebSocket at `/ws/watcher/activity` now rides the session cookie through the proxy and the frontend hook (`useWatcherActivity`) registers as a listener. Backend emits `agent_processing start/end` events with `listeners=1`, and the React Flow canvas at `components/watcher/graph/GraphCanvas.tsx` applies the `animate-pulse` glow class to the active agent node. Verified live: glow appeared on `agent-1` during a Playground message and cleared when processing ended.

### Frontend — auth redirect (BUG-4) + stale-cookie loop

The root spinner ("Loading Tsushin…") stalled indefinitely whenever `/api/auth/me` returned 401 because `LayoutContent` treated `loading=false, user=null` identically to `loading=true`, and never redirected to `/auth/login`.

- `frontend/lib/public-paths.ts` **(new)** — shared `PUBLIC_PATH_PREFIXES = ['/auth', '/setup']` and `isPublicPath(pathname)` helper used by both the client-side AuthContext and the Edge-runtime middleware. Framework-agnostic (no `'use client'`, no `next/*` imports).
- `frontend/contexts/AuthContext.tsx:85-114` — on 401 in `loadUser()`, hard-redirect to `/auth/login` via `window.location.href` (matches the logout pattern referenced by BUG-544, avoids `router.push` races with the spinner). **Critical loop fix:** when the cookie is STALE (present-but-invalid — typical on a reinstall where the DB got wiped but the browser still has the old JWT), the middleware redirects `/auth/login` → `/` while AuthContext would redirect `/` → `/auth/login`, ping-ponging forever. The fix calls `api.logout()` before the hard redirect so the backend sets `Set-Cookie: tsushin_session=""; Max-Age=0` — the next request is truly unauthenticated and the middleware stops bouncing. Required making the backend `/api/auth/logout` endpoint auth-OPTIONAL at `backend/auth_routes.py:1076-1091` (from `get_current_user_required` → `get_current_user_optional`) so the clear-cookie call works when the JWT is already expired.
- `frontend/components/LayoutContent.tsx:187-214` — spinner condition split: `if (loading)` renders the premium spinner; `if (!user)` returns `null` (hard redirect is already in flight).
- `frontend/middleware.ts:20-33` — server-side belt-and-braces redirect: if `tsushin_session` cookie is absent and the path is not public / `_next/*` / `favicon.ico`, respond with `307 → /auth/login` before client JS even runs. `isPublicPath` short-circuits both sides so no loop is possible.
- `frontend/contexts/AuthContext.tsx:252-260` — `useRequireAuth()` is now a no-op (AuthContext is the single redirect source).

### Files changed

Backend: `install.py`, `backend/auth_routes.py`, `backend/services/search_command_service.py`, `backend/agent/skills/search_skill.py`, `backend/agent/tools/search_tool.py`, new `backend/alembic/versions/0035_add_missing_provider_whatsapp_columns.py`, new `backend/dev_tests/test_env_preservation.py` (gitignored).

Frontend: `frontend/next.config.mjs`, `frontend/lib/client.ts`, `frontend/lib/websocket.ts`, `frontend/hooks/useWatcherActivity.ts`, `frontend/middleware.ts`, `frontend/contexts/AuthContext.tsx`, `frontend/components/LayoutContent.tsx`, new `frontend/lib/public-paths.ts`, and the 20 `NEXT_PUBLIC_API_URL` migrations listed above.

Ops: `docker-compose.yml` (frontend gains `BACKEND_INTERNAL_URL`).

### Verification evidence

- Infrastructure: `/api/health` 200, `/api/readiness` 200, backend `/metrics` 200.
- Auth: tenant login 200, admin login 200, API v1 OAuth2 `client_credentials` grant 200.
- API v1 sweep: `agents`, `skills`, `tools`, `personas`, `tone-presets`, `security-profiles` — all 200.
- Tenant UI walk (Hub, Playground Debug + Memory, Agents, Flows, Settings, Watcher → Graph View): 153 API calls, 151 returned 200. The two pre-existing 500s (`/api/mcp/instances/tester/status`, `/api/hub/integrations?refresh_health=true`) predate this patch and are unrelated.
- Sandboxed tool: `/tool dig lookup domain=example.com` → 200 with IPs, 125 ms execution.
- WhatsApp round-trip: tester (5527999616279) → bot (5527988290533) → bot responded "Hello Vini! How can I help you today?" → stored back on tester.
- Per-bug: env preservation unit test PASS, `alembic current = 0035`, schema probes show both new columns, search provider log emits, Graph View glow appears on `agent-1` for 3s during `agent_processing start/end` and clears immediately after.

### Docs sweep — close v0.6.0 coverage gaps (`develop`, 2026-04-16)

Targeted documentation patch so `docs/documentation.md` and `docs/user-guide.md` reflect headline v0.6.0 features that the README already advertises. No code changes.

**`docs/documentation.md` additions:**
- §7.5 Multi-Agent Orchestration — corrected Agent Switcher `execution_mode` to `hybrid` (v0.6.0 default) and added a mode matrix (`tool` / `legacy` / `hybrid`).
- §13 Flows — BUG-559 callout: `flows_skill` now queries `AgentSkillIntegration` first, so per-agent provider bindings (e.g., Google Calendar) take precedence over config defaults.
- §15.1.1 (new) Migration: LID support (v0.6.0) — contact auto-linking, UserAgentSession phone-number fallback, ContactAgentMapping dual-key lookup.
- §19.6 (new) Anthropic Prompt Caching — 3-breakpoint `cache_control` with relocation trick, 40–65% input-token cost cut, default model `claude-haiku-4-5`.
- §19.4/19.5 — fixed duplicate numbering (Model Pricing is now §19.5).

**`docs/user-guide.md` additions:**
- §1 — new "For Administrators: Installer Options" callout covering `--le-staging`, IP-address SAN handling, and frontend rebuild on `NEXT_PUBLIC_API_URL` change.
- §2 — Anthropic prompt caching note in the provider section; default model reference to `claude-haiku-4-5`.
- §3 Multi-Agent Orchestration — Agent Switcher hybrid mode callout.
- §6 WhatsApp — "Upgrading from 0.5.x — WhatsApp LID migration" callout with re-linking steps.
- §18 (new) Remote Access (System Administrators) — Cloudflare Tunnel pointer with Quick vs Named mode table, setup steps, and security posture.
- TOC updated to include §18.

**Files changed:**
- `docs/documentation.md` (+~60 lines, additive)
- `docs/user-guide.md` (+~60 lines, additive)
- `docs/changelog.md` (this entry)

## v0.6.0-patch.4 (2026-04-16)

Promotion of `develop` → `main`. Consolidates all post-patch.3 work (channels, installer SSL, memory scoping, sentinel parser, skill fixes, UX wizards, regression results) into the v0.6.0 release line. README refreshed with v0.6.0 highlights.

### Slack & Discord setup wizards (`develop`, 2026-04-16)

Replaces the bare `SlackSetupModal` / `DiscordSetupModal` (5 fields and a Save button with no context) with guided multi-step wizards modeled on `WhatsAppSetupWizard`. Surfaced because multiple QA testers got stuck on "where do I find a bot token?" / "what scopes do I need?" / "where does the webhook URL go?" — the bare modals demanded values without telling users where they live on Slack/Discord.

**SlackSetupWizard** (`frontend/components/SlackSetupWizard.tsx`, 5 steps):
1. **Welcome** — pick mode (Socket Mode recommended vs HTTP Events) with the trade-offs explained side-by-side. Yellow warning if HTTP mode is chosen while `tenant.public_base_url` is unset, with the `cloudflared` command inline.
2. **Create App** — exact `api.slack.com/apps` clicks, plus the full Slack manifest JSON pre-filled with every required scope and bot event (with a Copy button). One paste covers OAuth scopes (`chat:write`, `channels:read/history`, `groups:history`, `im:read/write/history`, `mpim:history`, `files:write`, `users:read`, `app_mentions:read`), bot events, and the Socket Mode toggle.
3. **Get Tokens** — branches on mode: Socket path walks through generating an App-Level Token with `connections:write`; HTTP path lists App ID + Signing Secret on Basic Information. Each step references the exact Slack menu location.
4. **Paste & Save** — credentials form + DM policy + format validation (xoxb- / xapp- / hex), with HTTP-mode URL preview before saving.
5. **Done** — for HTTP mode shows the exact Events Request URL (`{public_base_url}/api/channels/slack/{id}/events`) with a Copy button to paste back into Slack's Event Subscriptions; explains how to `/invite @bot` and assign an agent.

**DiscordSetupWizard** (`frontend/components/DiscordSetupWizard.tsx`, 6 steps):
1. **Welcome** — explains the HTTP Interactions architecture (vs Gateway), with a green ✓ if `public_base_url` is detected or amber warning + `cloudflared tunnel --url http://localhost:8081` inline if missing.
2. **Create App** — Discord Dev Portal walkthrough including the captcha note.
3. **Get Credentials** — three values (Application ID, Public Key, Bot Token) with where to find each, the Bot-page Privileged Intents toggle, AND the Installation-page scope/permissions config (`bot` + `applications.commands` scopes, with all 8 bot permissions enumerated and explained: View Channels, Send Messages, Send Messages in Threads, Read Message History, Embed Links, Attach Files, Add Reactions, Use Slash Commands).
4. **Paste & Save** — credentials form with Ed25519 hex format validation (64 chars).
5. **Set Webhook URL** — surfaces the exact `{public_base_url}/api/channels/discord/{id}/interactions` URL with a Copy button and the three Discord-portal clicks to paste it back. Explains the PING-PONG verification (only succeeds if Tsushin's per-tenant Ed25519 signature handler returns Type 1 to Discord's verification PING).
6. **Invite Bot** — surfaces **both** install paths: Server Install (recommended, requires Manage Server) AND User Install fallback (no server permission needed — for personal Discord accounts that can't add bots to any guild). The User Install fallback was added because real-world testing on `iamveene` confirmed the dropdown shows "No items to show" when the user lacks Manage Server in any guild — historically a hard wall, now a one-click alternate path.

**Hub crash fix:**
- `frontend/app/hub/page.tsx` lines 3162 and 3243 were reading `integration.allowed_channels.length` and `integration.allowed_guilds.length` directly. Both fields became optional in `client.ts` after the first wave of channel work (matches what backend returns when no allowlist is configured), so the unguarded `.length` access crashed the entire Hub page with "Cannot read properties of undefined (reading 'length')" — manifesting as Chrome's "This page couldn't load" the moment any Slack or Discord integration existed without an allowlist. Fixed both with `?.length ?? 0`.

**Files changed:**
- `frontend/components/SlackSetupWizard.tsx` (new, 470 lines)
- `frontend/components/DiscordSetupWizard.tsx` (new, 360 lines)
- `frontend/components/SlackSetupModal.tsx` (deleted, superseded)
- `frontend/components/DiscordSetupModal.tsx` (deleted, superseded)
- `frontend/app/hub/page.tsx` (imports renamed + `.length` safety)

### Slack & Discord channels — first complete E2E (`develop`, 2026-04-16)

First-ever end-to-end test of the Slack and Discord channels surfaced multiple regressions and design gaps that blocked production use. Closes V060-CHN-001/002/031, BUG-313 frontend half, plus a previously hidden token-encryption defect that affected both channels.

**Slack — Socket Mode worker (V060-CHN-002)**
- New `backend/channels/slack/socket_worker.py` and `backend/services/slack_socket_mode_manager.py`. Spins up one `slack_sdk.socket_mode.aiohttp.SocketModeClient` per active `SlackIntegration` with `mode='socket'`. Wired into `app.py` lifespan (mirrors `TelegramWatcherManager`) and into `routes_slack.py` create/update/delete so workers start/stop on integration CRUD without a backend restart.
- Listener signature fix: slack-sdk passes `(client, request)` to `socket_mode_request_listeners`, not `(request,)` — a one-arg callback raised `TypeError` on every event.
- Filter: ignore non-message events, bot-authored messages (prevents reply loops), and events without `user`/`text`.

**Slack — HTTP Events routing (V060-CHN-002 partial → fully wired)**
- `routes_channel_webhooks.py` `slack_events()` now enqueues `event_callback` payloads to `message_queue` with `channel='slack'` (was a no-op TODO). Added the same bot/empty-message filter as Socket Mode.

**Slack — `thread_ts` preservation (V060-CHN-031)**
- `AgentRouter.route_message()` now stashes the inbound message's `thread_ts` (or `ts` if not already in a thread) on the router instance. `_send_message()` auto-injects `thread_ts` for outbound Slack adapter calls so replies thread under the original message instead of starting a new one. Verified visually in #new-channel ("Test 4 → Hello from Slack!" delivered as a threaded reply).

**Discord — Interactions endpoint routing (was a stub)**
- `routes_channel_webhooks.py` `discord_interactions()` was returning a Type 5 deferred ack and dropping the message. Now resolves the bound agent (via `Agent.discord_integration_id`), enqueues to `message_queue` with `channel='discord'`, then ACKs Discord within the 3-second window. The QueueWorker `_process_discord_message` dispatcher routes to AgentRouter via the existing DiscordChannelAdapter.

**Token encryption symmetry (silent multi-tenant decrypt failure)**
- `routes_slack.py` and `routes_discord.py` had been encrypting tokens with raw `Fernet(master_key)` while `AgentRouter._register_slack_adapter` / `_register_discord_adapter` and the new Slack Socket Mode worker decrypt via `TokenEncryption(master_key).decrypt(token, tenant_id)` (which derives a per-tenant Fernet key via PBKDF2). Net result: every saved Slack/Discord token failed to decrypt at use time with `Token decryption failed (invalid key or corrupted data)`. This was hidden until something actually tried to *use* the tokens. All four call sites (Slack create, Slack update, Discord create, Discord update) and the Slack signing-secret decryption in `routes_channel_webhooks.py` now use `TokenEncryption` consistently.

**Queue worker message envelope (Slack/Discord dead-lettered with KeyError 'id')**
- `_process_slack_message` and `_process_discord_message` now inject `id`, `chat_id`, and `timestamp` into the router message envelope. The router uses `message["id"]` as `MessageCache.source_id` (raised `KeyError: 'id'`) and `chat_id`-with-fallback-to-`sender` to pick the outbound recipient (was sending replies to the user-key namespace, not the Slack channel/Discord channel).

**Tenant `public_base_url` (no in-app tunnel; clear UX guidance)**
- New `tenant.public_base_url` column (nullable, alembic migration `0034_add_tenant_public_base_url.py`). New `/api/tenant/me/settings` endpoints (`GET` + `PATCH`) for tenant-self-service config, gated by `org.settings.write` for writes.
- New `frontend/components/PublicBaseUrlCard.tsx` rendered in Hub → Communication. Tells the user: HTTPS URL where Slack HTTP Events / Discord Interactions can reach the backend; explicitly notes Socket Mode does not need this; suggests `cloudflared tunnel --url http://localhost:8081` for local dev.
- The Slack and Discord setup modals query `/api/tenant/me/settings` on open and render the exact webhook URL (`{public_base_url}/api/channels/slack/<id>/events` and `…/discord/<id>/interactions`) the user must paste back into the third-party portal. Modals show a yellow inline warning when `public_base_url` is unset and HTTP/Interactions mode is selected.

**Discord modal — missing `public_key` field (BUG-313 frontend gap)**
- The Discord setup modal didn't collect `public_key`. Backend `DiscordIntegrationCreate` requires it (64 hex chars, Ed25519). Form submissions silently failed. Field added with format validation; instructions updated to point users to Discord Dev Portal → General Information → Public Key. `DiscordIntegrationCreate` TS type updated.

**Slack modal — wrong field name `app_token` vs `app_level_token`**
- Frontend was sending `app_token` but backend Pydantic field is `app_level_token`, so Socket Mode setup silently dropped the token. Fixed in `client.ts` interface and in the modal form payload.

**Agent assignment UI — Slack & Discord were missing**
- `frontend/components/AgentChannelsManager.tsx` only knew about playground/whatsapp/telegram/webhook in `AVAILABLE_CHANNELS`. Slack and Discord cards were never rendered, so users could not bind an agent to a Slack workspace or Discord bot via the UI even though the backend FKs (`Agent.slack_integration_id`, `Agent.discord_integration_id`) had existed since v0.6.0. Both channels now appear with the same instance-selector pattern as Telegram (loads `getSlackIntegrations()` / `getDiscordIntegrations()`, renders a radio list, persists via `api.updateAgent()`). `Agent` interface in `client.ts` gained `slack_integration_id` and `discord_integration_id`.

**Branch hygiene + Next.js 16 config delta cherry-pick**
- Cherry-picked the missing 5-file Next.js 16 config delta from the abandoned `codex-next16-upgrade` branch onto `develop` (commit 6888a2f): `next.config.mjs` adds `outputFileTracingRoot` and `turbopack.root` to silence workspace-detection warnings; `next-env.d.ts` adds the typed-routes reference. Build script and TS config were already on develop.
- Deleted three stale local branches that had diverged from old `main`: `feature/remote-access-auth-hardening` (already an ancestor of develop), `pr-4` (image analysis skill — already in develop as commit 9d3a8ef), `codex-next16-upgrade` (config delta cherry-picked above).

**Verification**
- Slack Socket Mode end-to-end round-trip in #new-channel of the Archsec workspace, four sequential messages — final reply correctly threaded. `slack_socket_mode_manager` started a `SocketModeClient` for integration id=3 immediately on POST; backend log: `[STARTUP] Slack Socket Mode Manager initialized` then per-event ACK + enqueue.
- Discord app `1494431647062298664` created with Public Key captured (Ed25519, 64 hex chars) and Message Content Intent enabled. Bot token reset and integration setup (E2E) require Discord MFA password reauth — left to the operator since the safety policy forbids auto-typing passwords.

**Files changed (backend):** `backend/api/routes_channel_webhooks.py`, `backend/api/routes_slack.py`, `backend/api/routes_discord.py`, `backend/api/routes_tenant_settings.py` (new), `backend/agent/router.py`, `backend/services/queue_worker.py`, `backend/services/slack_socket_mode_manager.py` (new), `backend/channels/slack/socket_worker.py` (new), `backend/app.py`, `backend/models_rbac.py`, `backend/alembic/versions/0034_add_tenant_public_base_url.py` (new).

**Files changed (frontend):** `frontend/lib/client.ts`, `frontend/components/SlackSetupModal.tsx`, `frontend/components/DiscordSetupModal.tsx`, `frontend/components/AgentChannelsManager.tsx`, `frontend/components/PublicBaseUrlCard.tsx` (new), `frontend/app/hub/page.tsx`, `frontend/next-env.d.ts`, `frontend/next.config.mjs`.

### Installer SSL/TLS hardening (`feature/installer-ssl-validation`, 2026-04-16)

Addresses concrete gaps in `install.py`'s HTTP, self-signed, Let's Encrypt, and manual-CA SSL modes. Reverse proxy remains Caddy — no certbot introduced (Caddy's built-in ACME client continues to handle Let's Encrypt issuance and renewal).

- **Fixed self-signed SAN for IP-address installs:** When the configured domain is an IP literal (e.g., `10.211.55.5` — the Parallels VM case), the `-addext subjectAltName=` argument previously emitted `DNS:10.211.55.5`, which is invalid per RFC 5280 and is rejected by browsers/curl with strict verification. The SAN list now branches on `_is_ip(domain)` and emits `IP:10.211.55.5,DNS:localhost,IP:127.0.0.1,IP:::1` for IPs and `DNS:<host>,DNS:localhost,IP:127.0.0.1,IP:::1` for hostnames. Caddyfile generation was also updated — `default_sni` now falls back to `localhost` when the domain is an IP (Caddy rejects IP literals in `default_sni`), while the site-block label is still the IP.
- **Manual-cert pre-flight validation:** `_prompt_manual_certs` now runs a new `_validate_cert_pair` helper (using the already-imported `cryptography` library) before copying files into `caddy/<stack>/certs/`. Checks: key/cert public-key match, not expired (warn if <30 days to expiry), SAN/CN covers the configured domain (prompts for confirmation if not), optional chain file parses and chains correctly. Hard errors now fail fast with actionable messages instead of deploying a broken cert and waiting for Caddy to crash with cryptic logs.
- **Manual-cert chain/intermediate support:** New optional prompt `Path to certificate chain/intermediate bundle (optional, Enter to skip)`. When provided, the chain is appended to the leaf cert in `caddy/<stack>/certs/cert.pem` (Caddy reads a single bundled PEM). Resolves deployment failures with CAs that require an intermediate bundle (Sectigo, GoDaddy, etc.).
- **Let's Encrypt pre-flight reachability:** `_validate_domain_dns` now additionally compares the server's public IP (fetched via ipify) against the domain's A/AAAA records and runs a plain HTTP HEAD against port 80 (the ACME HTTP-01 challenge path). Mismatches and unreachable hosts surface as warnings with a confirm prompt rather than blocking — CDN/Cloudflare/NAT setups remain valid.
- **Let's Encrypt staging environment (`--le-staging` / interactive prompt):** Injects `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` into the Caddy global block. Lets operators test the full LE flow without consuming production rate-limit budget (5 failed validations per hostname per hour). Staging certificates are untrusted by browsers — the installer warns accordingly.
- **Frontend rebuild on API URL change:** `NEXT_PUBLIC_API_URL` is baked into the Next.js image at build time. When re-running the installer with a changed SSL mode or domain, the installer now detects the change by diffing the previous `.env` and runs `docker compose build --no-cache frontend` before `up -d`. Without this, a cached image silently shipped the old URL and manifested as CORS errors or 404s at runtime.
- **`_sync_cert_files` helper:** Collapses the three inline duplications that mirrored cert assets from `caddy/<stack>/certs/` to the legacy `caddy/certs/` path. Reduces the drift risk introduced by the IP-SAN and manual-cert changes.
- **New unit tests:** `backend/tests/test_installer_ssl.py` (22 cases). Covers IP vs DNS SAN branching, Caddyfile generation for all four modes including staging, `_validate_cert_pair` against match / mismatch / expired / near-expiry / domain-mismatch / valid-chain / bad-chain fixtures, and the stale-IP-SAN detection + auto-regeneration migration path. All green locally.
- **New CLI flag:** `--le-staging` (requires `--domain`).
- **New `.env` keys:** `SSL_LE_STAGING`, `SSL_CERT_PATH`, `SSL_KEY_PATH`, `SSL_CERT_CHAIN_PATH` — all persisted so non-interactive re-runs (where the installer reads config from `.env` rather than prompting) retain the operator's SSL choices. Without this, re-runs silently flipped LE staging back to production and KeyError'd when `SSL_MODE=manual`.
- **Stale IP-SAN auto-migration:** existing installs affected by the pre-fix DNS-for-IP SAN bug are detected on installer re-run — the old cert is deleted and regenerated with the correct `IP:<addr>` SAN. Without this, users upgrading over a broken cert would continue to hit `NET::ERR_CERT_COMMON_NAME_INVALID` until they manually removed the stale files.
- **Files changed:** `install.py`, `backend/tests/test_installer_ssl.py` (new), `docs/changelog.md`, `docs/documentation.md`, `README.md`.

### Bug Sprint: Logout Spinner + Memory Tenant Scoping + Sentinel Parser (`develop`, 2026-04-16)

Closes the last three open items in `BUGS.md` (BUG-544, BUG-LOG-015, V060-SEC-001).

- **BUG-544 fix (logout from `/` stuck on "Loading Tsushin…" spinner):** The `logout()` handler in `AuthContext.tsx` called `router.push('/auth/login')` after `setUser(null)`. While the async Next.js router transition was in flight, the current `/` route re-rendered with `user=null`, hitting `LayoutContent.tsx:188` (`if (loading || !user)`) and showing the loading spinner. Any delay or failure in the router transition left the user stuck on that spinner indefinitely. Replaced with a hard navigation (`window.location.href = '/auth/login'`) guarded by `typeof window !== 'undefined'` (SSR-safe), with a `router.push` fallback retained for the server-render branch. Hard-navigating kills all stale React state and forces a clean bootstrap at `/auth/login`.
- **BUG-LOG-015 fix (Memory tenant-scoping on read paths):** The `Memory` model already had a non-null `tenant_id` column (alembic 0024) populated on every write path, but several read/delete query sites were still filtering by `agent_id` alone. Each was valid in practice (routes pre-validate the agent's tenant), but DB-level defense-in-depth was missing. Added `Memory.tenant_id == <tenant>` filters to every remaining read/delete site:
  - `agent_memory_system.py` — load-all, get-by-sender, delete-by-sender.
  - `memory_management_service.py` — `__init__` now accepts a required `tenant_id`; every internal Memory query filters by it (list / stats / get / delete / clean-old / reset-all).
  - `routes_memory.py` — all 6 callers updated to pass `agent.tenant_id` (now captured from `verify_agent_access`'s return value).
  - `playground_message_service.py` + `playground_thread_service.py` — memory lookups now filter by `thread.tenant_id`.
  - `routes_playground.py:get_memory_layers` — filters by `current_user.tenant_id`.
- **V060-SEC-001 fix (stale sentinel parser docstring + missing regression test):** The fix to derive `valid_types` dynamically from `DETECTION_REGISTRY.keys()` was already in `sentinel_service.py:1464` (from an earlier commit) but the docstring still advertised only 5 of the 9 valid threat types, and there was no unit test asserting that every registered detection type round-trips through `_parse_unified_response`. Rewrote the docstring to reference `DETECTION_REGISTRY` as the source of truth and added `backend/tests/test_sentinel_unified_parse.py` with 10 cases (8 parametrized dynamically over the registry + `none` + bogus) that will fail if any future refactor re-introduces a hard-coded allowlist.
- **New tests:** `backend/tests/test_sentinel_unified_parse.py` (10 cases) and `backend/tests/test_memory_tenant_scoping.py` (7 cases). Added to the `.gitignore` allowlist so they ship in the repo. Both suites green (17/17 pass) against the rebuilt backend image.
- **Files changed:** `frontend/contexts/AuthContext.tsx`, `backend/agent/memory/agent_memory_system.py`, `backend/agent/memory/memory_management_service.py`, `backend/api/routes_memory.py`, `backend/api/routes_playground.py`, `backend/services/playground_message_service.py`, `backend/services/playground_thread_service.py`, `backend/services/sentinel_service.py`, `.gitignore`, `backend/tests/test_sentinel_unified_parse.py`, `backend/tests/test_memory_tenant_scoping.py`.

### Skills Ship with Empty Default Keywords (`develop`, 2026-04-16)

- **Cleared default keyword arrays** in `get_default_config()` across 6 skills: `flows_skill`, `gmail_skill`, `agent_switcher_skill`, `browser_automation_skill`, `flight_search_skill`, `search_skill`. Keywords are now a legacy mechanism — with tool-based execution (LLM decides), they caused false-positive skill activations. Users can still configure their own keywords if needed.
- **Web search provider switching tested E2E:** Brave Search (5 results from usatoday.com, nextspaceflight.com) then switched to Google/SerpAPI (5 results from wikipedia.org, reuters.com, uefa.com). Provider config correctly persisted and both providers returned different result sets.
- **Flight search tested E2E:** Google Flights provider via SerpAPI returned 23 real flight options for JFK→LHR on 2026-05-15 with pricing (BRL 2000-2071), durations (6h 55m direct), and recommendations.

### Email/Calendar & Hub Integration Fixes (`develop`, 2026-04-16)

- **BUG-558 fix (Hub integrations endpoint 500):** `/api/hub/integrations` crashed with 500 when a `shell` type integration existed (leftover from BUG-510 probe). The `IntegrationResponse` model only handles asana/calendar/gmail. Now skips unknown types.
- **BUG-559 fix (Google Calendar provider ignored):** Two issues: (1) `SchedulerSkill` passed `skill_type="scheduler"` to the factory but DB stores `"flows"`. (2) `FlowsSkill._get_provider()` checked `config.get('scheduler_provider')` before DB lookup, but `get_default_config()` hardcodes `scheduler_provider="flows"`, so the DB record (with `google_calendar`) was never reached. Fixed by always querying `AgentSkillIntegration` first. Now Google Calendar events return correctly (5 real events verified).
- **Gmail Email skill tested E2E:** Gemini1 agent with Gmail (mv@archsec.io) successfully listed real emails via Playground UI.
- **Google Calendar tested E2E:** Gemini1 agent with Calendar (movl2007@gmail.com) listed 5 real events (Visit Mother's Day, Lavar carro, Sync Kees, Consulta Dr Eliud, Consulta Dr Giovanni Grossi).
- **Files changed:** `backend/api/routes_hub.py`, `backend/agent/skills/scheduler_skill.py`, `backend/agent/skills/flows_skill.py`

### Automation Skill Quote-Stripping Fix (`develop`, 2026-04-16)

- **BUG-557 fix (Automation flow_identifier with embedded quotes):** LLMs frequently send `flow_identifier` as `"\"3\""` instead of `"3"`, causing "Flow not found" errors. Added quote-stripping before flow lookup.
- **Files changed:** `backend/agent/skills/automation_skill.py`

### Knowledge Sharing Post-Response Hook Fix (`develop`, 2026-04-16)

- **BUG-556 fix (Knowledge sharing not firing from Playground UI):** The WebSocket streaming service (`playground_websocket_service.py`) never invoked `_invoke_post_response_hooks()`, so knowledge sharing fact extraction and OKG auto-capture never ran when chatting via the Playground. Only the HTTP sync fallback had the hook. Added hook invocation after streaming completes.
- **Files changed:** `backend/services/playground_websocket_service.py`

### A2A Graph View Target Node Glow (`develop`, 2026-04-16)

- **BUG-555 fix (A2A target node not glowing):** During inter-agent communication, the target agent's node in Graph View did not glow — only the A2A edge glowed amber. Now the target agent node pulses (`animate-pulse`) for the duration of the A2A session, with proper min-glow duration and coordinated fade-out.
- **Files changed:** `frontend/hooks/useWatcherActivity.ts`

### Agent Switching & WhatsApp LID Migration Fix (`develop`, 2026-04-16)

- **BUG-559 fix (Kira can't switch agents):** Agent switcher's `execution_mode` was set to `"tool"` (LLM-only), disabling the keyword trigger path. When AI fallback classification failed (e.g., missing API key), the switch silently dropped. Changed default to `"hybrid"` so both keyword and LLM tool paths work. Also improved `_identify_sender` to normalize `@s.whatsapp.net` suffixes before contact lookup.
- **BUG-560 fix (agent switch responses sent as audio):** In tool mode, the switch_agent result goes through the LLM response pipeline, which applies TTS if the agent has audio_tts enabled. Added `_skip_tts` check in the router's TTS section: when `tool_used` is `"skill:switch_agent"`, TTS is bypassed and the confirmation is sent as text.
- **BUG-561 fix (UI agent assignment not taking effect):** `UserAgentSession` (from previous agent-switcher invocations) has absolute routing priority over `ContactAgentMapping` (set by UI). Changing the assigned agent in the UI updated the mapping but not the session, so messages kept going to the old agent. Added `_sync_user_agent_session()` helper that updates/creates/deletes the session whenever the ContactAgentMapping API is called.
- **BUG-562 fix (WhatsApp LID sender format breaking contact identification):** WhatsApp transitioned from phone-based sender IDs (e.g., `5527999616279`) to Linked IDs (e.g., `259029628641423`). This broke contact lookup, UserAgentSession matching, and agent switching. Fixed with three changes: (1) auto-link LID as `whatsapp_id` on Contact when resolved via name matching, (2) UserAgentSession lookup falls back to contact's phone number and migrates the session identifier to the current LID, (3) `_sync_user_agent_session` searches by both phone and LID.
- **Files changed:** `agent_switcher_skill.py`, `router.py`, `routes_agents.py`

### Graph View Glowing & A2A Edge Regression Fix (`develop`, 2026-04-16)

- **BUG-555 fix (WebSocket TLS + reconnection):** Graph View glow animations stopped working because Chrome's self-signed TLS cert trust didn't extend to WebSocket `wss://` connections (close code 1006). Fixed by importing Caddy root CA into macOS system Keychain. Also removed WebSocket reconnection limit — now retries indefinitely with 10s backoff cap. Added `visibilitychange` listener to auto-reconnect when user switches back to the tab.
- **BUG-556 fix (streaming event cleanup):** Playground streaming path emitted an orphaned `agent_processing: start` event before delegating to `send_message()`, which emitted its own start/end pair. Removed the duplicate; `send_message()` now solely manages AI-path events. Added explicit start for skill-only streaming path.
- **BUG-559 fix (stale A2A edges):** Removing the `agent_communication` skill from an agent left orphan A2A permission records, causing the Graph View to show stale amber edges to the old agent. Added auto-cleanup: disabling the A2A skill now deletes all related permissions.
- **BUG-558 fix (tester delete button):** Added Delete button to QA Tester card in Hub for both runtime instances and compose-managed orphans.
- **BUG-557 fix (glow brightness):** Increased all glow animation brightness 33% (opacity 0.6→0.8 close, 0.3→0.4 far). Added `inset` inner glow and `border-width: 2px` during active state for better visibility on dark backgrounds.
- **BUG-558 fix (tester delete button):** Added Delete button to QA Tester card in Hub. Handles runtime tester instances (API delete) and compose-managed orphans (dismiss card). Resolves catch-22 where container was gone but config card remained without any way to remove it.

### OKG & MCP Skill Regression Fixes (`develop`, 2026-04-16)

- **BUG-551 fix (OKG multi-tool registration):** The deprecated `get_skill_tool_definitions()` method (used by the main agent pipeline) only registered `okg_store` via the single-tool `get_mcp_tool_definition()` call, leaving `okg_recall` and `okg_forget` invisible to the LLM. Added multi-tool branch that checks `get_all_mcp_tool_definitions()` and registers all tools when count > 1.
- **BUG-552 fix (string-to-array coercion):** LLMs frequently send `tags` fields as comma-separated strings instead of JSON arrays, causing `"Field 'tags' must be an array"` validation errors. Added automatic string-to-array coercion in `_validate_arguments()`.
- **BUG-553 fix (string-to-boolean coercion):** LLMs send boolean fields like `include_symbols` as string `"true"`/`"false"` instead of native booleans, causing validation errors. Added string-to-boolean coercion.
- **BUG-554 fix (MCP SSRF blocking Docker containers):** The MCP connection manager's SSRF validator blocked private IPs (Docker network addresses) during `get_or_connect()`, even though the creation route already allowed them via `allow_private=True`. Added `allow_private=True` to the connection manager's SSRF check for consistency.
- **Files changed:** `skill_manager.py`, `connection_manager.py`

### TTS Audio Response Regression Fix (`develop`, 2026-04-16)

- **BUG-548 fix (Kokoro TTS):** Kokoro TTS container was not running — it requires `docker-compose --profile tts` to start. Started the container; verified synthesis and WhatsApp audio delivery working.
- **BUG-549 fix (OpenAI TTS / tenant_id not propagated):** The TTS pipeline never passed `tenant_id` from the router through the TTS skill to the TTS provider's `get_api_key()` call. Only system-wide keys (tenant_id=NULL) were searched, making tenant-specific keys invisible. Fixed by adding `tenant_id` parameter across the full chain: `TTSProvider` base class → `TTSProviderRegistry.get_provider()` → `AudioTTSSkill.process_response()` → `router.py`.
- **BUG-550 fix (Provider instance key not used for TTS):** `get_api_key()` only checked the `api_key` table (Service API Keys), but users configure OpenAI keys as Provider Instances in Hub → AI Providers. Added Step 3 fallback to `get_api_key()`: when no service API key exists, resolves the default `provider_instance` for the matching vendor. This allows TTS to reuse the same OpenAI key configured for LLM chat without requiring a separate Service API Key entry.
- **Files changed:** `tts_provider.py`, `tts_registry.py`, `audio_tts_skill.py`, `router.py`, `openai_tts_provider.py`, `elevenlabs_tts_provider.py`, `kokoro_tts_provider.py`, `api_key_service.py`

### Fact Extraction Visibility Fix (`develop`, 2026-04-16)

- **BUG-546 fix:** Knowledge list endpoint (`GET /api/agents/{id}/knowledge`) now returns all facts across all users when no `user_id` filter is provided. Previously returned empty due to unimplemented stub.
- **BUG-547 fix:** Playground Memory Inspector now correctly displays extracted facts. The inspector queried facts using the bare sender key (`playground_u1_a17_t44`) while facts were stored with a `sender_` prefix (`sender_playground_u1_a17_t44`). Added fallback prefix resolution to match both formats.
- **New method:** `KnowledgeService.get_all_agent_facts()` for bulk fact retrieval across all users.

### UX Wizards & Skill Error Handling (`develop`, 2026-04-15)

- **Per-Agent Vector Store Selector:** Added a "Vector Store" section to the Agent Configuration page (Studio > Agent > Configuration) with a dropdown to select a specific vector store instance for the agent, overriding the tenant default. Includes a mode selector (Override/Complement/Shadow) and a status indicator showing whether the agent uses a per-agent override, tenant default, or built-in ChromaDB.
- **Vector Store Creation Wizard — Attach to Agents:** After creating a new vector store in Hub > Vector Stores, a wizard step appears to optionally assign the new store to one or more existing agents directly from the modal. Eliminates the need to navigate to each agent's configuration page separately.
- **MCP Server Creation Wizard:** After creating a new MCP server in Hub > MCP Servers, a 3-step wizard guides users through: (1) reviewing discovered tools, (2) creating a custom skill linked to an MCP tool, and (3) assigning the skill to agents. Each step is skippable.
- **Improved Skill Error Handling:** Backend skill operations now return specific error messages (ValueError for validation issues) instead of a generic "Skill operation failed" message. Frontend displays the actual error detail to users.

### Comprehensive Regression Results (`develop`, 2026-04-15)

Full platform regression covering infrastructure, auth, Studio, Hub, Flows, Playground, Settings, API v1, and WhatsApp.

| Phase | Scope | Result |
|-------|-------|--------|
| A | Infrastructure (health, readiness, metrics) | PASS |
| A | Auth — tenant owner, global admin, member RBAC | PASS |
| A | Navigation — all 6 nav links | PASS |
| B | Studio — agent list, configuration (inc. new Vector Store section), all 7 tabs | PASS |
| B | Studio — add every built-in skill to agent | PASS |
| B | Studio — agent creation, sub-pages (contacts, personas, projects, security, builder, custom skills) | PASS |
| C | Hub — all tabs (AI Providers, WhatsApp, Telegram, Slack, Discord, Webhooks, MCP, Vector Stores) | PASS |
| C | Flows — list, detail/editor | PASS |
| C | Playground — agent chat (sync HTTP) | PASS |
| C | Settings — all sub-pages (org, team, integrations, system-ai, sentinel, vector-stores, slash-commands, api-clients, billing, advanced) | PASS |
| API | v1 — OAuth2 token, agents, chat, skills, personas, tone-presets, security-profiles, tools | 8/8 PASS |
| WhatsApp | Session active, messages processing | PASS |

**Issues found:** BUG-543 (Hub integrations 500, pre-existing), BUG-544 (logout redirect, pre-existing, low).

### Playground & AI Client Fixes (`develop`, 2026-04-15)

- **Playground stuck at "Processing your message..." when WebSocket unavailable (CRITICAL):** The HTTP fallback path used async queue mode, which depends on WebSocket for result delivery. When `wss://` fails (e.g. self-signed cert not trusted for programmatic WebSocket connections), the queue result notification never reaches the frontend. Fixed: HTTP fallback now uses `?sync=true` when WebSocket is disconnected, so the LLM response returns inline in the HTTP response. No WebSocket dependency for basic chat functionality.
- **Gemini 2.5 "thinking" models return empty responses:** Multi-part response extraction failed for Gemini 2.5 thinking models that return `thought` parts alongside text parts. The `response.text` quick accessor raises `ValueError`, and the fallback extraction used `hasattr(part, 'text')` which doesn't handle all SDK variations. Fixed: robust extraction that skips `thought` parts and uses `getattr()` safely with inner exception handling.

### Seed & Init Fixes (`develop`, 2026-04-15)

- **Subscription plans not seeded on PostgreSQL fresh installs (CRITICAL):** Plans were only inserted via the SQLite-only migration (`migrations/add_plans_and_sso.py`), leaving the `subscription_plan` table empty on every Postgres-backed deployment. Added `backend/services/plan_seeding.py` with the canonical plan definitions and wired it into `db.init_database()` so plans are seeded idempotently on every startup for both backends. Migration `0033` backfills `tenant.plan_id` for tenants created before this fix.
- **`tenant.plan_id` FK not set on signup:** `auth_service.signup()` set the legacy `plan` string but left `plan_id` NULL. Updated to resolve the `free` plan row and populate `plan_id` on tenant creation.
- **Default agent limit raised to 10:** Existing tenants capped at 5 agents (old model default) are bumped to 10 via migration `0032`. `auth_service.py` and `models_rbac.py` defaults already reflect 10 for new installs.
- **Dynamic provider/model dropdowns:** Provider and model selectors in all agent creation UIs (`/agents` Create modal, Studio `+` button, `AgentConfigurationManager`, Playground config panel) now fetch from configured Hub instances at runtime. No more hardcoded vendor lists — adding a new provider in Hub > AI Providers automatically makes it available everywhere. Shared `VENDOR_LABELS` map exported from `client.ts`.

### Ubuntu VM v0.6.0 Full E2E Audit (`develop`, 2026-04-15)

Comprehensive fresh-install end-to-end QA on Ubuntu 24.04 aarch64 (VM `10.211.55.5`, HTTP mode). All AI providers configured: Gemini (default), OpenAI, Anthropic, Vertex AI (us-east5), Brave Search, Tavily.

**Test Coverage (all TCs completed):**

| TC | Feature | Result |
|----|---------|--------|
| TC-1 | Health/readiness/metrics | PASS |
| TC-2/3 | Auth — tenant admin + global admin | PASS |
| TC-4–11 | Core UI pages (Dashboard, Agents, Playground, Flows, Hub, Settings, System) | PASS |
| TC-14/21 | LLM provider matrix (Gemini, OpenAI, Anthropic, Vertex AI, Brave, Tavily) | PASS |
| TC-15 | Web Search (Brave Search — 5 results) | PASS |
| TC-16 | Image Generation | PASS |
| TC-17 | ACME Sales KB — CSV upload + price recall | PASS |
| TC-18/19 | A2A delegation (Tsushin → ACME Sales) | PASS |
| TC-25 | Sentinel — injection + poisoning detected | PASS |
| TC-26 | Custom Skills — instruction, script, MCP-backed | PASS |
| TC-27 | Shell beacon + slash commands (/shell, /inject, /tool, /status, /clear) | PASS |
| TC-28 | API v1 — OAuth2, sync/async chat, thread retrieval | PASS |
| TC-29 | Flows — notification + agentic | PASS |
| TC-30 | Projects KB — upload + semantic recall (similarity=0.85) | PASS |
| TC-23 | Memory isolation — isolated PASS; shared PARTIAL (OKG vector store gap) | PARTIAL |
| TC-24 | Vector Stores — auto-provisioned Qdrant healthy, manual instance created | PASS |
| TC-31 | A2A Graph View — 9 nodes, 14 connections | PASS |

**New bugs filed:** BUG-538 (toolbox not built by installer), BUG-539 (Sentinel DetachedInstanceError in shell), BUG-540 (OKG no vector store provider on fresh install).
**Previously fixed confirmed:** BUG-531, BUG-532, BUG-534 — all PASS.

---

### Docs Structure Reorganization (`develop`, 2026-04-15)

Moved the canonical markdown documentation set into `docs/` to keep the repository root focused on runtime and project-entry files. Added `docs/README.md` as the docs index, standardized canonical markdown filenames under `docs/` to lowercase kebab-case, updated repository and tooling references to point at the canonical `docs/` paths, kept root compatibility stubs for older links, and repointed the backend help-panel mount so `/app/USER_GUIDE.md` still resolves inside containers.

### Bug Fixes — BUG-531 through BUG-537 (`develop`, 2026-04-15)

Resolved all 7 open bugs surfaced by the fresh-install v0.6.0 regression audit.

**Backend fixes:**
- **BUG-531** — `GET /api/personas` (no trailing slash) was issuing a 307 redirect that dropped the `Authorization` header. Fixed by stacking a second `@router.get("", include_in_schema=False)` decorator on the list endpoint in `routes_personas.py` and setting `redirect_slashes=False` on the router. Both `/api/personas` and `/api/personas/` now return 200 directly.
- **BUG-532** — `GET /api/personas/` and `GET /api/tones` returned empty lists because the `filter_by_tenant` call was missing `include_shared=True`, excluding system presets with `tenant_id = NULL`. Added `include_shared=True` to `routes_personas.py:184` and `routes_agents.py:286`.
- **BUG-534** — `GET /api/tenants/` and `GET /api/admin/users/` returned entity-keyed pagination objects (`tenants`, `users`) instead of the standard `items` key. Renamed fields in `TenantListResponse` and `GlobalUserListResponse` and updated all callers in the frontend (`client.ts`, `system/tenants/page.tsx`, `system/users/page.tsx`).

**Frontend fixes:**
- **BUG-536** — The onboarding tour re-appeared on every page reload because `tourStartedRef` (an in-memory ref) was reset on each mount. Fixed by persisting a `tsushin_onboarding_started:{userId}` key to localStorage when the tour first auto-starts, reading it back on mount to restore `tourStartedRef`, and clearing it on dismiss/skip/complete. Fix in `frontend/contexts/OnboardingContext.tsx`.

**Documentation fixes:**
- **BUG-533** — Added a path-correction table to `docs/documentation.md` §25.4 mapping each legacy 404 path to its actual working equivalent.
- **BUG-535** — Added explicit `-H "Content-Type: application/x-www-form-urlencoded"` to the OAuth2 curl examples in both `CLAUDE.md` and `docs/documentation.md` §25.1. Omitting this header causes FastAPI to return a misleading 422.
- **BUG-537** — Added a "Fresh-install note" to `docs/documentation.md` §27 explaining that the tester MCP is not bundled by default and documenting the manual provisioning steps via Hub → Communication → WhatsApp.

### Documentation Alignment Pass (`develop`, 2026-04-15)

Aligned the repository docs with the current `develop` runtime and setup flow. Updated the README, comprehensive docs, user guide, Docker deployment guide, and backend service docs to reflect Next.js 16, the current `/setup` behavior, Docker Compose v2 rebuild syntax, the absence of a root `testing` profile, current provider/tester surfaces, and the external `tsushin-network` rebuild caveats.

### Fresh Install v0.6.0 E2E Validation — LAN/HTTP Mode (`develop`, 2026-04-15)

Full fresh-install QA on macOS (LAN IP `192.168.15.2`, HTTP mode, stack name `tsushin-fi`). Install via `python install.py --defaults --http`. All AI providers configured via API (Anthropic, OpenAI, Gemini, Brave Search, Tavily).

**API Test Results (43 tests via dedicated tester agent):**
- Infrastructure, auth (tenant + admin + wrong-password rejection), agent CRUD, OAuth2 v1, sync/async chat with queue polling, flows, vector stores, and admin authorization: all PASS
- Bugs found: BUG-531 (personas redirect drops auth header), BUG-532 (system personas/tones return empty for tenant), BUG-533 (6 documented API paths return 404), BUG-534 (admin pagination uses entity keys not `items`), BUG-535 (OAuth2 token requires explicit Content-Type)

**Browser Test Results (Playwright):**
- Login, Dashboard/Watcher, Agent Studio (all tabs: Agents, Contacts, Personas, Projects, Security/Sentinel, Builder, Custom Skills): PASS
- Playground AI chat (`FRESH_INSTALL_OK` confirmed): PASS
- Flows page, Integration Hub (all tabs incl. Vector Stores with Qdrant auto-provisioned): PASS
- Settings, Shell Command Center (`/hub/shell`), Remote Access (`/system/remote-access`, cloudflared binary confirmed): PASS
- New bugs found: BUG-536 (User Guide tour re-appears on every page navigation per new user), BUG-537 (tester MCP not in fresh install compose)

**WhatsApp:** Skipped — tester MCP container not included in fresh install stack; WhatsApp instance provisioning UI confirmed functional (dialog loads, communication tab renders). Documented as BUG-537.

**Verdict:** Fresh install is **PASSING** for all automated test categories. 7 new bugs logged (BUG-531 to BUG-537), all LOW/MEDIUM severity. Core functionality fully operational on fresh HTTP install.

---

### Build Performance Quick-Wins (`develop`, 2026-04-15)

Five Dockerfile optimizations to reduce cold-build times and BuildKit cache churn:

- **Item 1 — Toolbox pip cache mount:** Added `--mount=type=cache,target=/root/.cache/pip` to `Dockerfile.toolbox` pip install (previously used `--no-cache-dir`, defeating BuildKit layer caching).
- **Item 2 — Split requirements (already done):** `requirements-base.txt`, `requirements-app.txt`, `requirements-optional.txt`, `requirements-phase4.txt` already in place; verified all user-listed optional packages (`kubernetes`, `google-cloud-secret-manager`, `qdrant-client`, `pinecone`, `pymongo`) are controlled by the existing `INSTALL_OPTIONAL_DEPS` ARG.
- **Item 3 — Playwright base image:** Runtime stage switched from `python:3.11-slim` to `mcr.microsoft.com/playwright/python:v1.48.0-jammy`. Removes the 14-package Playwright system-dep `apt-get` block and the `playwright install chromium` step (~1.1 GB browser download) — Chromium + all deps are pre-installed in the base layer. `PLAYWRIGHT_BROWSERS_PATH` updated from `/opt/playwright-browsers` to `/ms-playwright` (base-image path).
- **Item 4 — Optional deps behind build args (already done):** `INSTALL_OPTIONAL_DEPS=true` ARG confirmed to cover all five optional packages; no change needed.
- **Item 5 — Nuclei (and all PD tools) download cache mount:** `Dockerfile.toolbox` now caches all four ProjectDiscovery binary downloads (nuclei, katana, httpx, subfinder) via `--mount=type=cache,target=/tmp/pd-cache` with a file-existence check. Subsequent builds reuse cached zips instead of re-downloading from GitHub Releases.

Also added `# syntax=docker/dockerfile:1.4` header to `Dockerfile.toolbox` to enable BuildKit cache-mount syntax.

### Bug Sprint — `BUG-514` to `BUG-525` resolved (`develop`, 2026-04-11)

Closed the 12 open bugs from `BUGS.md` in four coordinated clusters covering frontend auth/onboarding UX, Remote Access, backend app logic, and MCP runtime/tester/toolbox behavior.

- **Cluster 1 — Frontend UX/Auth (`BUG-514`, `BUG-515`, `BUG-516`):** Replaced browser-native email gating with app-managed validation that still preserves autofill/mobile keyboard behavior; made onboarding persistence user-scoped and resilient to auth-context reloads; replaced the affected Memory Inspector and Hub confirmation/alert flows with app toasts and modals.
- **Cluster 2 — Remote Access (`BUG-517`, `BUG-519`):** Made the fallback migration Postgres-safe, changed defaults/backfills to the stack proxy target (`http://tsushin-proxy:80` / stack-aware equivalent), aligned the System UI copy, and fail-closed tunnel startup when the proxy/Caddy layer is unavailable.
- **Cluster 3 — Backend app logic (`BUG-518`, `BUG-520`, `BUG-521`, `BUG-522`):** Added exact-match-first plus suffix-stripping fallback for A2A agent names; made blank-stdout script tests fail closed; preserved transcript integrity for Sentinel `detect_only` flows while still filtering transcript-only turns from reusable memory; added curated Vertex AI discovery fallbacks.
- **Cluster 4 — MCP runtime / tester / toolbox (`BUG-523`, `BUG-524`, `BUG-525`):** Added short DNS-safe aliases for runtime WhatsApp containers, switched tester fallback to real runtime instance fields with `source=runtime` preservation, made the Hub tester card source-aware, and aligned the stdio launcher story around the shipped toolbox `uvx` runtime.

**Validation:** Preflight disk/docker checks, safe no-cache rebuild of `backend` and `frontend`, health/readiness verification, focused backend suites plus an integrated 41-test regression slice, toolbox `uvx` verification inside `tsushin-toolbox:base`, browser automation for `.local` login/error handling, onboarding persistence across users/routes/refresh, Memory Inspector toast/modal flows, and Hub API-key confirmation modal behavior.

### Fresh Install v0.6.0 Audit (`develop`, 2026-04-11)

Recorded the disposable fresh-install audit run from `.private/installations/fresh-install-v060-20260411-081937/tsushin`, including restore-manifest handling, API plus Playwright coverage, Quick Tunnel validation, provider/vector-store setup, and the user-directed skip of the final WhatsApp message exchange after QR blockers were reproduced.

- **New bugs logged:** `BUG-519` through `BUG-524` in `BUGS.md`
- **Revalidated open:** `BUG-515` (Welcome Tour persistence) and `BUG-516` (User Guide dialog interference)
- **Highest-impact findings:** Quick Tunnel still defaults to `http://frontend:3030` and leaves public `/api/*` routes unreachable; script custom-skill tests can return `success=true` with blank output; Playground thread detail/memory inspector can lose the user turn; Vertex AI discovery returns zero models on a healthy provider instance; runtime WhatsApp QR/health resolution breaks on long stack-prefixed MCP names; dedicated tester QR controls still target missing compose `tester-mcp` instead of the active runtime tester instance.

### Ubuntu VM v0.6.0 Fresh-Install Regression Audit (`develop`, 2026-04-11)

Full interactive fresh-install QA on Ubuntu 24.04 aarch64 (`10.211.55.5`). All 31 TCs executed via API (curl) and browser automation (Playwright). Install path: `/home/parallels/code2/tsushin-v060-20260411-084511/`. All integrations configured: Gemini (default/gemini-2.5-flash), OpenAI, Anthropic, Ollama (reconfigured to `0.0.0.0:11434` for Docker bridge access), Brave Search, Tavily.

**Pass summary (evidence screenshots in `output/playwright/`):**
- TC-0: Setup wizard — org `Tsushin QA`, tenant admin `test@example.com`, providers auto-configured, global admin credentials displayed
- TC-1/2/3: Health/readiness, tenant login (no System section), global admin verified via API (browser blocked by BUG-514)
- TC-4–TC-10: Dashboard/Watcher tabs, Studio (7 agents including ACME Sales), Playground chat, Memory Inspector, Flows page, Hub page, all 15 Core sub-pages
- TC-11: System admin endpoints via API (`/api/tenants/`, `/api/system/status`, `/api/admin/remote-access/tenants`) — all 200
- TC-14/TC-21: AI providers (Gemini/OpenAI/Anthropic/Ollama) + Tool APIs (Brave Search/Tavily saved via API workaround due to BUG-516)
- TC-15: Brave web search — live results from Reuters, TIME, ScienceDaily returned in Playground
- TC-16: Image generation — "Image generated successfully!" confirmed in Playground
- TC-17: ACME Sales agent + KB (`acme_products.csv`) — "The Laptop Pro X (SKU: LPX-001) is priced at $1299." with "1 doc used (Agent)" tag
- TC-18/TC-19: A2A permission (Tsushin→ACME Sales, depth=2, 10RPM) + delegation — "The ErgoMouse has a price of $55 and an SKU of EMX-002."
- TC-25: Sentinel config enabled with all detection types active; 0 events in log (no attacks in session)
- TC-27: Sandboxed tools via API — `/tool dig lookup domain=example.com` returns DNS IPs; `/status` returns agent/session state
- TC-28: API v1 — OAuth2 token exchange, X-API-Key auth, all `/api/v1/*` endpoints 200, sync chat responding
- TC-29: Flows page rendered; 2 flows created (notification + agentic/workflow)
- TC-30: Project "ACME QA Project" created + conversation started
- TC-31: A2A sessions API confirms 1 completed session, 100% success rate, 2091ms avg response time
- TC-13: 0 ERROR/CRITICAL backend log lines across the full test run

**Findings: 6 new bugs (BUG-514 through BUG-518, BUG-525):**
- `BUG-514` — `.local` TLD silently rejected by frontend email validator (blocks global admin browser login)
- `BUG-515` — Welcome Tour modal reappears on every page navigation (state not persisted)
- `BUG-516` — `window.alert()` suppressed by native `<dialog>` User Guide (blocks fact creation and API key save UI)
- `BUG-517` — `add_remote_access` migration startup WARN: `enabled` boolean/integer mismatch (non-blocking)
- `BUG-518` — A2A skill agent lookup fails when user appends " agent" suffix in natural language query
- `BUG-525` — `uvx` binary absent from backend Docker image; stdio MCP servers non-functional on fresh installs without manual ad-hoc install

**Supplemental coverage (continued session):**
- TC-23: Memory isolation verified — isolated memory blocks cross-user access (user_B cannot see user_A facts on isolated agent), shared memory pool functional (23 tenant-wide facts visible)
- TC-26: MCP server (stdio `uvx mcp-server-fetch`) registered and connected, `fetch` tool discovered, Sentinel scan clean; all 3 custom skill types created (instruction/script/mcp_server), instruction skill invocation confirmed ("Hello from custom skill!" prefix); `uvx` required manual container install (BUG-525)
- TC-31: Graph View browser-verified — 12 nodes / 20 connections, live green indicator; A2A Comms tab shows `Tsushin → ACME Sales` session as completed (depth 1/2, 2 msgs). Screenshots: `output/playwright/tc31-graph-view.png`, `output/playwright/tc31-a2a-comms.png`

### Bug Sprint — 8 bugs resolved (`develop`, 2026-04-10 evening)

Closeout of the remaining open bugs from the 2026-04-10 Ubuntu VM fresh-install QA.

- **BUG-506 — API v1 `model_provider` now accepts `vertex_ai`:** Added `vertex_ai` to the pattern on both `AgentCreateRequest` (`backend/api/v1/routes_agents.py:100`) and `AgentUpdateRequest` (line 163), matching the internal/tenant API. Regenerated `docs/openapi.json` from the live backend so generated SDKs stop rejecting Vertex AI as an invalid provider.
- **BUG-507 — Ollama health fallback:** Wrapped `getOllamaHealth()` in `frontend/lib/client.ts` in a try/catch that returns `{available: false, models: []}` on any fetch/HTTP error. Optional Ollama checks on `/agents`, `/hub`, and Playground config panels no longer surface red console errors on healthy installs.
- **BUG-508 — `/agents/communication` no longer crashes:** Guarded the dynamic `frontend/app/agents/[id]/page.tsx` route with a `Number.isFinite` check on the parsed id. Non-numeric segments (like `communication`) now `router.replace('/agents')` immediately instead of firing `/api/agents/NaN`, raising an alert, and redirecting.
- **BUG-509 — Instruction custom skills execute properly at runtime:** `CustomSkillAdapter.execute_tool` now routes instruction-variant skills through `execute_instruction_with_llm`, matching the `/api/custom-skills/{id}/test` behavior. Raw-prompt injection of `instructions_md` via `SkillManager.get_custom_skill_instructions` is now limited to `execution_mode == 'passive'` skills, so tool/hybrid instruction skills run through the LLM adapter instead of leaking their template. `SkillManager.execute_tool_call` now writes `CustomSkillExecution` history for every runtime custom-skill invocation, mirroring the `/test` endpoint pattern.
- **BUG-510 — `/shell` output now reaches `/inject`:** `ToolExecution` gained optional `pending`/`source`/`source_ref` fields; `ToolOutputBuffer` gained `list_pending_executions` and `update_execution_output` helpers. `_handle_shell` buffers completed stdout/stderr immediately for `wait_for_result=True` and writes a pending stub tagged `source='shell_command'` (keyed by the beacon command id) for fire-and-forget. A new `SlashCommandService._resolve_pending_shell_executions` runs at the top of `_handle_inject` and lazily pulls updated `ShellCommand` results via `ShellCommandService.get_command_result`, capping at 10 pending entries per call.
- **BUG-511 — Project chat propagates tool-only responses:** Promoted the BUG-504 helper into a shared module `backend/agent/response_helpers.py::extract_response_text`. `backend/api/v1/routes_chat.py` now imports it, and `ProjectService.send_message` uses the same helper to populate both the appended assistant message and the final response envelope. Project conversations no longer return `{"message":null}` when the agent answered with tool output only.
- **BUG-512 — Stdio MCP test auto-starts toolbox:** `MCPConnectionManager.get_or_connect` now calls `ToolboxContainerService.ensure_container_running(tenant_id, db)` for `transport_type == 'stdio'` before constructing the transport. First-time `/test` calls and first-time runtime stdio invocations create/start the tenant toolbox container on demand instead of erroring with `Container not found for tenant ... Please start it first.`
- **BUG-513 — Hub Vertex AI Test button blocks unsaved drafts:** Added a `vertexDirty` state flag in `frontend/app/hub/page.tsx` that flips on any form edit and resets on successful save. `Test Connection` is disabled while dirty and renders helper text `"Save configuration before testing — the Test Connection button validates the currently saved credentials, not the fields above."` Prevents the misleading "test passes but my new values are ignored" trap during first-time setup.

**Validation:** Safe rebuild (`docker-compose build --no-cache backend frontend` → `docker-compose up -d backend frontend` — compose stack stayed up, WhatsApp/MCP sessions preserved). Per-bug source-level probes (adapter behavior, buffer state transitions, OpenAPI schema inspection, shared helper imports), Playwright verification of the 3 frontend fixes using real per-character keystrokes, and a platform-wide regression via `/fire_regression`.

### Remote Access Auth Hardening Follow-up (`feature/remote-access-auth-hardening`, 2026-04-10)

- Hardened `POST /api/provider-instances/discover-models-raw` so it stays anonymous only while `/api/auth/setup-status` reports `needs_setup=true`; once the first user exists it now requires a fully validated session with `org.settings.write`. The shared strict optional-auth helper now enforces the same disabled-user and password-invalidated-token checks as required auth, closing the old ad hoc token-decoding path.
- Hardened `GET /api/skills/available` behind `agents.read`, removing an unauthenticated inventory endpoint that exposed installed skill types and schemas over public Remote Access deployments.
- Hardened shell-beacon distribution endpoints: `GET /api/shell/beacon/version` now requires a valid `X-API-Key` for an active `ShellIntegration`, while `GET /api/shell/beacon/download` now accepts either that API key or a signed-in session with `shell.read` so the browser download button still works.
- Hardened `GET /api/ollama/health` behind authenticated-session access and updated the Hub, Agents, and Playground callers to use the shared authenticated client path so same-origin tunneled requests keep sending the session cookie.
- Updated the shell install snippets and beacon README to include `X-API-Key` on curl-based download flows, and documented the intentional public-vs-gated remote-access-adjacent endpoint allowlist plus the accepted UUID capability URLs for Playground audio/image assets.

### Remote Access (Cloudflare Tunnel) — v0.6.0 feature (`develop`, 2026-04-10)

- Added a new enterprise-grade Remote Access feature that exposes Tsushin through a Cloudflare Tunnel (quick or named mode), managed entirely from the Global Admin UI and persisted in the database (no `.env` knobs). The tunnel runs as a supervised subprocess inside the backend container with a bounded restart policy (3 attempts, 5s/15s/30s backoff) and a real readiness probe via `cloudflared`'s Prometheus metrics endpoint (no more `sleep 1`).
- New single-row DB table `remote_access_config` (Alembic `0031_add_remote_access.py` + SQLite fallback `backend/migrations/add_remote_access.py`) stores tunnel mode, hostname, protocol, encrypted token, autostart, and cross-restart metadata (`last_started_at`, `last_stopped_at`, `last_error`). The tunnel token is encrypted at rest via `TokenEncryption` using a new dedicated `remote_access_encryption_key` on the `config` table (MED-001 envelope pattern, `TSN_MASTER_KEY`-wrapped).
- New per-tenant entitlement: `Tenant.remote_access_enabled` (indexed boolean, defaults `false`). The global admin grants access per tenant either from the new `/system/remote-access` page or from the tenant detail page. Both streams (`GlobalAdminAuditLog` and tenant-scoped `AuditEvent`) are recorded on every toggle.
- **Login gate:** `backend/auth_routes.py::_enforce_remote_access_gate` is called from both `login()` and `exchange_sso_code()`. When a login request arrives on the configured tunnel hostname and the user's tenant is not enabled, the backend returns `403` with a structured `detail = {error_code: "REMOTE_ACCESS_TENANT_DISABLED", message, tenant_id}` and writes `auth.remote_access.denied` with `severity=warning`. Already-issued JWTs continue to work until expiry.
- **New admin REST API** (all `require_global_admin`): `GET/PUT /api/admin/remote-access/config`, `POST /api/admin/remote-access/start|stop`, `GET /api/admin/remote-access/status`, `GET /api/admin/remote-access/tenants`, `PUT /api/admin/remote-access/tenants/{tenant_id}`, `GET /api/admin/remote-access/callbacks`. Config PUTs use optimistic concurrency via `expected_updated_at` (409 on conflict, second-precision tz-stripped comparison). The token is write-only in the API — responses only surface `tunnel_token_configured: bool`.
- **New Global Admin UI page** `frontend/app/system/remote-access/page.tsx` with four cards: live Tunnel Status (5s polling gated by `document.visibilityState`), Tunnel Configuration form (mode radio, FQDN-validated hostname, password-masked token with clear-on-save flow, autostart + protocol + target URL advanced options), Google OAuth Callbacks (copyable URIs for GCP whitelisting with amber warning banner), and per-Tenant entitlement toggle table. Tenant detail page gains a `RemoteAccessTenantCard`. The System Administration overview gains a Remote Access card with a globe icon.
- **Docker:** `backend/Dockerfile` now installs the arch-aware `cloudflared` binary before the non-root user switch; the tunnel subprocess runs under UID 1000 with outbound-only connectivity (no privileged ports).
- **Caddy:** `install.py::generate_caddyfile` now emits a reusable `(tsushin_routes)` snippet plus an additional `:80` site block imported by the same snippet. The `:80` block is the upstream for cloudflared (Cloudflare terminates TLS at the edge, then forwards plain HTTP to `tsushin-proxy:80`). `caddy/Caddyfile.template` documents the new structure. Without this, tunnel requests would bypass Caddy's `/api/*` routing and the frontend's API calls would 502.
- **Frontend API resolver:** `frontend/lib/client.ts::resolveApiUrl` now returns `window.location.origin` when the page is loaded over HTTPS, so both `https://localhost` and the Cloudflare tunnel hostname use same-origin API calls that flow through Caddy.
- **CORS:** backend startup now dynamically appends `https://{tunnel_hostname}` to the allow list when an explicit list is configured (best-effort, gracefully skips if the `remote_access_config` table does not exist yet on fresh install).
- **Validation:** full E2E via Claude-in-Chrome against the live public URL `https://tsushin.archsec.io` (cloudflared named tunnel bound to the `tsushin` tunnel in the `archsec.io` Cloudflare zone, routed to `http://tsushin-proxy:80`). Verified: quick-tunnel subprocess lifecycle (start → running → stop), named-tunnel readiness via metrics probe, per-tenant gate (blocked tenant → `REMOTE_ACCESS_TENANT_DISABLED` 403 with friendly error + audit event), enabled tenant login succeeds, CORS origins reflect both `https://localhost` and `https://tsushin.archsec.io`, optimistic concurrency returns 409 on stale `expected_updated_at`.

### Bug Sprint — 12 bugs resolved (`develop`, 2026-04-10)

- Fixed Playground memory normalization for `isolated`, `channel_isolated`, and `shared` modes by centralizing sender-key/chat-id resolution across sync chat, queue/streaming, history, memory inspector, thread detail, and websocket auto-rename. Playground history and memory reads now accept optional `thread_id` and return the same canonical thread-scoped data used on writes.
- Fixed `/tool` buffering so sandboxed-tool results are added exactly once in the shared slash-command execution path and are immediately visible to `/inject`.
- Fixed agentic chat regressions by promoting A2A `list_agents` delegate intents into real communication sessions and by returning tool/custom-skill output from `/api/v1/agents/{id}/chat` when the assistant body would otherwise be empty.
- Fixed Sentinel audit semantics to use the real `sentinel_analysis_log` write path, always log threat analyses, and only log benign analyses when `log_all_analyses=true`.
- Fixed setup/runtime regressions by auto-creating `Qdrant (Default)` during setup through the shared vector-store provisioning helper, surfacing fail-open setup warnings with a manual recovery path, and resolving Kokoro through stack-scoped `KOKORO_SERVICE_URL` defaults derived from `TSN_STACK_NAME`.
- Fixed flow and Playground UX regressions by normalizing `recipient`/`recipients` in message steps, rejecting image uploads in the Playground document flow with explicit supported-type copy, and keeping the `/flows` creation wizard open when a step type is selected even with onboarding/user-guide overlays present.
- Validation: rebuilt `backend` and `frontend` without cache, verified health/readiness plus authenticated API smoke, ran the combined focused regression slice (`16 passed`), and used Playwright to validate Playground document rejection, threaded Playground history/memory, and flow-wizard step selection stability.

### macOS v0.6.0 Targeted Regression (`develop`, 2026-04-10)

- Executed a full v0.6.0 targeted regression test on the production macOS dev stack (`develop` branch, `https://localhost`) covering all 22 TCs from the v0.6.0 test matrix. Both API (`X-API-Key` / OAuth2) and browser automation (Playwright) paths tested. LLM providers configured before test: Anthropic (`claude-sonnet-4-6`, id=2), OpenAI (`gpt-4o-mini`, id=3), Gemini (pre-configured, id=4).
- **Smoke Tests (PASS):** Backend health (`/api/health` → 200), frontend loads, login (`test@example.com`/`test123`), dashboard.
- **TC-1 — Vector Stores (FAIL):** `vector_store_instance` table empty; no ChromaDB containers running. BUG-499 revalidated open.
- **TC-2/3 — Memory Isolation/Shared (PASS):** `isolated` mode stored/retrieved correctly per-thread; `shared` mode accessible across agents in same tenant.
- **TC-5 — Sentinel (PARTIAL):** Sentinel runs (`operation=sentinel_analysis` in logs), intercepts messages. `sentinel_audit_log` never written — **BUG-505 new**.
- **TC-6 — MemGuard (PASS):** Prompt injection detected and sanitized (MemGuard integrated in sentinel profile).
- **TC-7 — Playground Chat (PASS):** Text message → agent responds with memory context via API v1.
- **TC-11 — MCP Server Create (PASS):** Created `regression-mcp-server` (SSE transport) via `POST /api/mcp-servers`; appears in list.
- **TC-13 — Custom Skill Create (PASS):** Created `test-regression-skill` (instruction type) via `POST /api/custom-skills`; verified in list.
- **TC-14 — Custom Skill Use (FAIL):** Skill assigned correctly; `/skill test-regression-skill` via chat returns `{message:null, response:null}` despite consuming 5,791 tokens — **BUG-504 new**.
- **TC-16 — Sandboxed Tools (PASS):** `/tool dig lookup domain=example.com` returns DNS results via API chat.
- **TC-17 — Slash Commands (PASS):** 28 commands listed; `/status` executed, confirmed agent name/model returned.
- **TC-18 — /inject (PASS):** `POST /api/playground/inject` injects context; verified in next chat response.
- **TC-19/20 — API Clients (PASS):** Client created via `POST /api/clients`; OAuth2 token exchange succeeds; `POST /api/v1/agents/{id}/chat` with generated key returns valid response.
- **TC-21 — Flows Programmatic (PARTIAL):** Flow 3 (`QA Gate Flow`) executes; gate condition false (expected). `SummarizationStepHandler` BUG-496 previously fixed and holds.
- **TC-22 — Flows Agentic (FAIL):** Flow 4 (`QA Notification Flow`) step 3 (message/notification) fails. BUG-422 revalidated open.
- **API v1 E2E pytest:** 24/29 pass; 5 failures in `TestAgentDescription` due to tenant `max_agents=5` constraint (pre-existing; agent limit hit).
- **Browser tests:** Deferred — Chrome required restart for newly-installed Caddy `tls internal` CA cert to take effect (cert added to macOS system keychain).
- **New Bugs:** BUG-504 (custom skill null response), BUG-505 (sentinel audit log never written).
- **Revalidated Open:** BUG-499, BUG-422, BUG-495 (prior session).

### Ubuntu VM Fresh-Install QA (`develop`, 2026-04-10)

- Executed the final real-user Ubuntu 24.04 VM audit on `10.211.55.5` from a fresh clone at `/home/parallels/code/tsushin-v060-audit-20260410-164252`, using the interactive installer (`python3 install.py`), `/setup` via Playwright, and dual-surface API + browser validation with evidence captured under `.private/qa/ubuntu-vm-20260410/reports/` and `output/playwright/`.
- **Install + setup (PASS):** Interactive install completed on ports `8081` / `3030` in HTTP-only remote mode, `/setup` finished successfully for tenant `Tsushin QA`, and the generated global-admin credentials were captured privately.
- **Provider + runtime matrix (PASS):** Gemini, OpenAI, Anthropic, Brave Search, Tavily, Vertex AI (`us-east5`), and Ollama were configured and exercised successfully; the VM Ollama service was exposed on `0.0.0.0:11434`, reachable from the backend via Docker host networking, and served `llama3.2`.
- **Memory + vector stores (PASS):** The setup-time default Qdrant vector store was auto-provisioned and healthy before any manual vector-store creation, and API/UI checks confirmed `isolated`, `shared`, and `channel_isolated` memory behavior on the audited tenant.
- **A2A + Graph View (PASS):** Backend A2A sessions completed successfully and Graph View rendered the corresponding live edge/activity, so the earlier `BUG-503` backend/session regression remained fixed on the final Ubuntu pass.
- **Shell + API v1 (PASS):** A real Ubuntu beacon registered and completed an approved shell command, auth burst sanity hit the expected `30/minute` throttle threshold, `/api/v1/openapi.json` generated a working SDK, and live generated-client calls succeeded while `/openapi.json` was checked for drift.
- **New bugs found (8):** `BUG-506` (public API v1 schema still omits `vertex_ai`), `BUG-507` (agents UI probes nonexistent frontend-local Ollama health route), `BUG-508` (`/agents/communication` falls through to `/api/agents/NaN`), `BUG-509` (assigned instruction custom skills leak raw instructions in Playground chat), `BUG-510` (completed `/shell` executions still do not surface to `/inject`), `BUG-511` (project chat returns success without an assistant reply even with saved fact/knowledge), `BUG-512` (stdio MCP testing still requires undiscoverable toolbox bootstrap), and `BUG-513` (Vertex AI modal tests only saved config, not current unsaved form values).
- **Not reproduced / corrected:** `BUG-388`, `BUG-419`, `BUG-499`, and `BUG-500` remained fixed on the final audit pass. Tenant-admin `403` on `/system/tenants` stayed an expected RBAC boundary, and the public API thread retrieval contract remains `GET /api/v1/agents/{agent_id}/threads/{thread_id}/messages`.

### Bug Fix Sprint — BUG-495 to BUG-498 (`develop`, 2026-04-09)

- **BUG-495 (Medium):** Fixed flow execution engine rejecting `"AgentNode"` step type. Added `"AgentNode"` as an alias for `ConversationStepHandler` in `flow_engine.py`. Users can now create and run flows with `AgentNode` step types without a "No handler" runtime failure.
- **BUG-496 (Low):** Fixed `SummarizationStepHandler` silently ignoring `text`/`content` keys in `config_json`. Added inline text extraction before falling back to `source_step`/`previous_step`. Updated fallback error message to mention `text`/`content` as valid config keys. Users can now summarize arbitrary inline text without requiring a preceding conversation step.
- **BUG-497 (Medium):** Fixed NumPy boolean array ambiguity error in `vector_store.py` `search_similar_with_embeddings`. Replaced bare ndarray boolean check with explicit `is not None and len(...) > 0` guard. Also wrapped `np.linalg.norm()` results with `float()` in `embedding_service.py` and `temporal_decay.py`. Semantic memory recall no longer emits the non-fatal "truth value of an array is ambiguous" error.
- **BUG-498 (Low):** Fixed `script_entrypoint` validation in `routes_custom_skills.py` rejecting bare function names. Both CREATE and UPDATE now accept function names (e.g., `"run"`) and auto-append the extension based on `script_language` (python→`.py`, bash→`.sh`, nodejs→`.js`).

### macOS v0.6.0 Full Feature Regression (`develop`, 2026-04-09)

- Executed comprehensive v0.6.0 full feature regression on macOS (fresh install of `develop` branch), covering all 23 test cases (TC-01 to TC-23) via API and Playwright browser automation.
- **Install & Setup:** `TSN_STACK_NAME=tsushin-fresh python3 install.py --defaults --http`; stack healthy; 6 LLM providers configured (Gemini 2.5-flash, Anthropic, OpenAI, Vertex AI, Brave, Tavily).
- **Infrastructure (PASS):** Health/readiness/metrics 200. Toolbox auto-provisioned (`tsushin-fresh-toolbox-*`).
- **Auth & RBAC (PASS):** Tenant owner login, OAuth2 client_credentials, X-API-Key auth, logout, global admin panel.
- **Playground & Memory (PASS):** Chat, memory recall across sessions ("QATestUser" recalled correctly), /status + /inject + /clear slash commands, browser automation skill (navigated example.com).
- **A2A Communications (PASS):** Permission created, playground A2A delegation from Tsushin → Kira confirmed with response "Hello! How can I help you?".
- **Sandboxed Tools (PASS):** `/tool dig lookup domain=google.com` and `/tool nmap quick_scan target=scanme.nmap.org` both returned results.
- **API v1 (PASS):** OAuth2 token exchange, sync/async chat, X-API-Key header auth, agents/skills/personas/tone-presets listing (returns `data` key, not `items`).
- **Sentinel (PASS):** 5 profiles (Off/Permissive/Moderate/Aggressive/Custom); profile assignment and effective config verified; injection attempt detected by LLM (detection_mode=detect_only).
- **Custom Skills (PARTIAL):** Instruction-type skill created successfully; script-type blocked by confusing `script_entrypoint` field validation (BUG-498).
- **Flows (PARTIAL):** 7 templates listed; flow create/node-add/run works; `AgentNode` type causes executor failure (BUG-495); Summarization step ignores inline text (BUG-496).
- **Vector Stores, Webhook, KB, Channel Health (PASS):** Qdrant VS instance created; webhook integration created with inbound URL; agent KB facts stored/retrieved (26 facts); channel health summary endpoint responds.
- **Memory (PARTIAL):** Semantic search emits NumPy array ambiguity error in vector_store (BUG-497, non-fatal but degrades recall).
- **New Bugs Found (4):** BUG-495, BUG-496, BUG-497, BUG-498.

### Ubuntu VM Fresh Install Full QA — v0.6.0 (`develop`, 2026-04-09)

- Executed full automated fresh-install QA on Ubuntu 24.04 VM (10.211.55.5) — fresh clone of `develop` branch, interactive installer, full 31-case test suite via Playwright browser automation and API curl.
- **Install & Setup:** Installer completed, Docker Compose stack healthy. Setup wizard created tenant org "Tsushin QA". All 6 LLM providers configured (Gemini, Anthropic, OpenAI, Brave Search, Tavily, Vertex AI).
- **Infrastructure (PASS):** Health/readiness/metrics all 200. Auth throttle: 12 rapid logins, no 429.
- **Auth & RBAC (PASS):** Tenant + global admin login, sidebar isolation, member user created — System nav hidden, `/system/tenants` redirect enforced.
- **Core UI (PASS):** All Watcher tabs, Studio, Playground chat, Memory Inspector (facts CRUD), Flows, Hub, all 13 Settings pages, System Admin.
- **Advanced Features (PASS):** Web Search (Brave), Image Generation, Knowledge Base (CSV → 2 chunks, semantic recall correct), Custom Skills ("QA Greeting Skill" created + tested), Sentinel (injections blocked), API v1 (OAuth2, X-API-Key, sync/async), Graph View (8 nodes, 12 connections), A2A Comms (Tsushin→Kokoro permission + delegation session logged as "completed").
- **Partial/Fail:** TC-22 — PNG upload silently accepted but LLM cannot process (BUG-465). TC-29 — Flow message step fails with `'NoneType' object is not iterable` (BUG-466). Flow creation wizard Step 2 closes prematurely (BUG-467).
- **Log check:** 0 ERROR/CRITICAL in backend.
- **New Bugs Found (3):** BUG-465, BUG-466, BUG-467.

### Bug Sprint — BUG-459 to BUG-464 resolved (`develop`, 2026-04-09)

- **BUG-459 (Medium):** Fixed Docker Compose project name collision between parallel installs. The installer now writes `COMPOSE_PROJECT_NAME` to `.env` derived from `TSN_STACK_NAME`, so each install gets a unique project name and won't recreate stopped containers from another install.
- **BUG-460 (Medium):** Fixed 401 cascade when accessing HTTP-only installs via `localhost` instead of LAN IP. Frontend `client.ts` now dynamically resolves `API_URL` to match `window.location.hostname` on HTTP installs, ensuring the httpOnly session cookie scope always matches the API endpoint origin.
- **BUG-461 (Low):** Fixed `kokoro-tts` container name to follow the `${TSN_STACK_NAME:-tsushin}-kokoro-tts` naming convention used by all other services in `docker-compose.yml`.
- **BUG-462 (Medium):** Fixed `/inject` slash command not being recognized via Playground API chat. Added `SlashCommandService` interception in both sync (`routes_playground.py`) and async (`queue_worker.py`) Playground chat paths before `PlaygroundService.send_message()`, mirroring the existing WhatsApp/Telegram router pattern.
- **BUG-463 (Medium):** Fixed `/status` slash command treated as regular text in Playground chat. Same root cause and fix as BUG-462 — all slash commands are now intercepted in the Playground path.
- **BUG-464 (Low):** Fixed facts text overflow in Playground Memory Inspector. Added `break-words min-w-0` Tailwind classes to the fact value span in `MemoryInspector.tsx`. The `min-w-0` overrides the flex child `min-width: auto` default, allowing `overflow-wrap: break-word` to constrain long unbreakable strings.

### macOS Fresh Install Automated QA (`develop`, 2026-04-09)

- Executed full automated fresh-install QA on macOS with `TSN_STACK_NAME=fresh-v060-tsushin` and `--defaults --http` mode. Covered 32+ test cases across API and Playwright browser automation.
- **All core features validated:** Setup wizard, auth (tenant + global admin), Watcher dashboard (8 tabs + Graph View), Studio (6 agents), Playground (chat, memory inspector, facts CRUD), Hub (AI Providers, Tool APIs, MCP Servers), all 15 Settings pages, 4 System Admin pages, Sentinel security, vector stores (Qdrant auto-provision), custom skills, sandboxed tools (dig), API v1 (agents, sync chat, OAuth), flows, projects.
- **New Bugs Found (6):** `BUG-459` (Docker Compose project name collision removes stopped original containers), `BUG-460` (localhost access causes 401 cascade due to cross-origin httpOnly cookie), `BUG-461` (kokoro-tts naming inconsistency), `BUG-462` (`/inject` slash command not recognized via Playground sync API), `BUG-463` (`/status` slash command treated as regular text), `BUG-464` (facts text overflow in Memory Inspector panel).
- Environment restored to pre-test state after cleanup.

### Bug Fix — BUG-453 (`develop`, 2026-04-09)

- **BUG-453 (Low):** Completed the `BUG-443` auth-throttling fix for fresh installs by wiring runtime env propagation all the way into the backend container. `docker-compose.yml` now passes `TSN_STACK_NAME`, `TSN_AUTH_RATE_LIMIT`, `TSN_DISABLE_AUTH_RATE_LIMIT`, and `TSN_SSL_MODE` into `tsushin-backend`; `auth_routes.py` now resolves login/signup/setup/reset/SSO limits from env; and `install.py` persists/backfills the new auth-throttle settings in `.env`.
- **Live VM verification:** On the Ubuntu audit stack (`TSN_STACK_NAME=tsushin-fresh-20260408`), the backend received the expected env overrides, 12 rapid login attempts completed without `429` when `TSN_DISABLE_AUTH_RATE_LIMIT=true`, and an auto-provisioned Qdrant instance used the correct `tsushin-fresh-20260408-vs-*` runtime naming prefix.

### Ubuntu VM Fresh-Install Follow-up Audit (`develop`, 2026-04-09)

- Re-ran the real-user Ubuntu VM audit on `10.211.55.5` against the disposable `tsushin-fresh-20260408` stack, preserving the interactive installer flow and validating the live runtime with both API checks and browser automation.
- Reconfirmed the provider/tool matrix after setup: Gemini, OpenAI, Anthropic, Vertex AI (`us-east5`), Brave Search, and Ollama (`host.docker.internal:11434`) were all exercised successfully on the fresh VM.
- **New Bugs Found (4):** `BUG-454` (backend no-cache rebuild fails hard when Hugging Face model prewarm is unavailable), `BUG-455` (Tavily still absent from Hub Tool APIs despite backend service plumbing), `BUG-456` (live `/openapi.json` remains awkward for generated client round-trips), and `BUG-457` (setup accepts sub-8-character admin passwords that later auth flows reject).
- **Still Unproven / Follow-up:** Tavily still lacks a stable tenant-facing validation path in the Hub, and release-quality generated-client validation remains dependent on manual cleanup around the exported OpenAPI surface.

### Bug Fix — BUG-454 to BUG-458 follow-up (`develop`, 2026-04-09)

- **BUG-454 (High):** Hardened the backend Docker image prewarm so transient Hugging Face failures no longer abort `docker-compose build --no-cache backend`. The build now retries and degrades to a warning with runtime lazy-download fallback.
- **BUG-455 (Medium):** Restored Tavily to the Hub `Tool APIs` UI, including the built-in tools copy and Tavily-specific configure modal path, so the frontend matches the backend-supported provider list.
- **BUG-456 (Medium):** Added typed health/readiness schemas, introduced dedicated public API v1 response models to avoid schema collisions, and exposed `/api/v1/openapi.json` plus `/api/v1/docs` for reliable SDK generation.
- **BUG-457 (Medium):** Re-validated unified 8-character password enforcement across setup, signup, reset-password, and change-password flows with browser and API coverage on the rebuilt local stack.
- **BUG-458 (Medium):** Fixed fresh-install setup wizard error handling so a short tenant-admin password now returns a validation `400` instead of a generic `500`, and added a focused regression test for that path.

### Bug Fix — BUG-452 (`develop`, 2026-04-08)

- **BUG-452 (Medium):** Fixed MCP Server creation via Hub UI returning 400 Bad Request for localhost/private URLs. The SSRF validator was blocking private/loopback IPs where MCP servers typically run. Applied `allow_private=True` (matching Ollama pattern) and relaxed HTTPS+auth requirement for local URLs while preserving it for public URLs. Cloud metadata endpoints remain blocked.

### Bug Sprint — BUG-444 to BUG-450 resolved (`develop`, 2026-04-08)

- **BUG-444 (Medium):** Fixed HTTP-only fresh installs redirecting `localhost` to `https://localhost/setup`. Removed stale `NEXT_PUBLIC_API_URL` build-time check from middleware SSL condition; SSL redirect now depends solely on runtime `TSN_SSL_MODE`.
- **BUG-445 (Medium):** Fixed installer CORS generation to always include loopback origins (`localhost`, `127.0.0.1`) for both frontend and backend ports on HTTP installs, preventing CORS failures when accessing via `127.0.0.1`.
- **BUG-446 (High):** Fixed project knowledge-base lookups falling back to web search. `ProjectService.send_message()` now passes `project_id` through `PlaygroundService` to `AgentService`, ensuring `CombinedKnowledgeService` is initialized with project context.
- **BUG-447 (Medium):** Restricted MCP stdio allowed binaries to `[“uvx”]` only, matching what ships in the toolbox container. `npx`/`node` were removed from the allowlist since they aren't installed. Improved error message with clear guidance.
- **BUG-448 (Medium):** Runtime-created containers (MCP, vector store, toolbox) now use `TSN_STACK_NAME` in their naming prefix instead of hardcoded values, enabling full isolation for side-by-side installs.
- **BUG-449 (Medium):** Instruction custom-skill test endpoint now executes through the tenant's LLM instead of returning raw instruction text. Added `execute_instruction_with_llm()` to `CustomSkillAdapter`.
- **BUG-450 (Low):** Watcher dashboard vector store card now shows external store health (Qdrant, MongoDB) instead of “Not configured”. Backend `/api/stats/memory` queries `VectorStoreInstance` table unconditionally.

### E2E Fresh Install Testing & QA Audit (`develop`, 2026-04-08)

- Conducted a comprehensive fresh install audit on Ubuntu VM (10.211.55.5) using `--defaults --http`.
- Completed setup wizard and initialization successfully via Playwright browser automation.
- Validated Vector Store provisioning, Flows (Workflow) creation, and Shared Knowledge (A2A) integration natively via Playwright UI automation.
- Discovered **BUG-450**: `/api/clients` returning 500 Internal Server Error when creating a new API client, causing the backend worker connection to drop.
- Discovered **BUG-451**: Sentinel config endpoint `/api/config` returning 404 Not Found, breaking API access to Sentinel settings.
- Discovered **BUG-452**: MCP Server creation via UI returning 400 Bad Request, blocking UI-based SSE server registration.

### Ubuntu VM Interactive Fresh-Install Audit (`develop`, 2026-04-08)

- Completed a real-user interactive installer audit on Ubuntu VM `10.211.55.5` using `python3 install.py` with backend `8081`, frontend `3030`, remote access, HTTP-only mode, and disposable stack `TSN_STACK_NAME=tsushin-fresh-20260408`.
- **Setup + Auth:** Finished `/setup` through browser automation, captured the generated global-admin credentials privately, and re-verified tenant-admin vs global-admin login/RBAC separation on the fresh tenant.
- **Provider Matrix:** Validated Gemini, OpenAI, Anthropic, Vertex AI (`us-east5`), and Ollama (`llama3.2`) end to end, along with Brave Search key usage. Tavily is accepted by the backend service list but remains absent from the Hub Tool APIs surface.
- **Feature Coverage:** Re-validated Qdrant auto-provisioning, long-term memory recall, isolated/shared memory behavior, ACME Sales knowledge-base upload + retrieval, A2A permissions and watcher Graph View, MCP server registration, instruction/script/MCP custom skills, Shell Command Center, sandboxed tools, slash commands including `/inject`, project chat, Public API v1 (API key + OAuth), async queue polling, and generated Python SDK calls against the live `/openapi.json`.
- **New Bugs Found (10):** `BUG-476` through `BUG-485` covering Tavily Hub visibility, User Guide overlay persistence, shared-memory cross-thread recall, A2A auto-skill wiring, MCP toolbox bootstrap, conversation search drift, `/shell` vs `/inject` inconsistency, KB search UX, project-scoped memory loss, and UI execution of input-dependent flows.
- **Still Unproven / Follow-up:** Tavily still lacks a first-class Hub validation path, external public-site fetch via the MCP `fetch` server was not proven beyond internal URLs, and the one-click UI Run path for input-dependent flows remains unsuitable for release-quality validation until it can collect trigger context.

### macOS Loopback & Runtime Isolation Audit (`develop`, 2026-04-08)

- Ran a second macOS fresh-install audit from a disposable clone using `TSN_STACK_NAME=freshinstall-tsushin` and `python3 install.py --defaults --http`, after stopping the original runtime to avoid container/name collisions.
- Re-validated the release 0.6.0 surface with mixed API and browser coverage across provider setup (Gemini/OpenAI/Anthropic/Ollama/Vertex), auto-provisioned Qdrant vector stores, sandboxed tools, shell beacons, slash commands, API v1 sync/async chat, isolated/shared memory, playground chat + image upload, A2A flows, and MCP-backed custom skills.
- Logged 7 new fresh-install regressions in the local bug tracker for follow-up: `BUG-444` (HTTP install still redirects `localhost` to HTTPS), `BUG-445` (generated `.env` breaks `127.0.0.1` via LAN-only API/CORS settings), `BUG-446` (project KB falls back to web search instead of uploaded project docs), `BUG-447` (toolbox image lacks `npx`/`node` even though MCP stdio accepts them), `BUG-448` (runtime containers ignore `TSN_STACK_NAME`), `BUG-449` (instruction custom-skill test echoes instructions), and `BUG-450` (Watcher reports vector store “Not configured” despite healthy default Qdrant).
- Confirmed fresh-install runtime naming remains inconsistent beyond the compose stack: the disposable run created `freshinstall-tsushin-*` core services alongside global `tsushin-*` vector/toolbox resources and `mcp-*` WhatsApp resources, which is why the original install still had to be brought down before realistic side-by-side validation.

### macOS Fresh Install QA (`develop`, 2026-04-08)

- Completed a 33+ test-case fresh-install QA on macOS (Darwin) using `TSN_STACK_NAME=tsushin-fresh` with `install.py --defaults --http` on `develop` HEAD, with isolated containers/volumes while original install was stopped.
- **Installation:** Installer ran fully unattended with `--defaults --http`, built all images (backend, frontend, WhatsApp MCP, Toolbox), passed health checks. `TSN_STACK_NAME=tsushin-fresh` correctly prefixed all containers and volumes.
- **Setup Wizard:** Completed via Playwright browser automation with 3 LLM providers (Gemini, OpenAI, Anthropic), global admin credentials captured. 6 default agents seeded.
- **Provider Matrix:** All 3 SaaS providers connected successfully. Ollama auto-detected with 9 local models. Brave/Tavily not configured during this run (reserved for post-setup).
- **Core Features Validated:** Playground chat (Gemini 2.5 Flash — correct response), Memory Inspector (fact CRUD — create/verify/delete), Knowledge Base (ACME Sales CSV upload + price retrieval with SKU), Sentinel/MemGuard (injection 90%, poisoning 90%, benign 0%), A2A communication permission (Tsushin→ACME Sales), slash commands (/status, /memory status), vector store config (ChromaDB default), flow creation (notification type), project creation, API v1 (client creation, API-key auth, OAuth token exchange, sync chat "2+2"→"4", async chat + queue poll → completed), 22 UI pages (all passed), RBAC (tenant admin 403 on /system/*, global admin 200), WhatsApp instances (bot authenticated, tester QR not visible in UI), log review (0 backend errors).
- **New Bugs Found (7):** BUG-437 (CORS mismatch localhost — Medium), BUG-438 (HTTP redirect on localhost — Medium), BUG-439 (tester not visible in Hub UI — Medium), BUG-440 (API v1 agents empty — Low), BUG-441 (Sentinel enabled=None — Low), BUG-442 (POST /api/flows 307 — Low), BUG-443 (login rate limit 5/min — Low).
- **Environment Revert:** Fresh install cleaned up (containers, volumes, images, .fresh-install/ folder removed), original containers restored and verified healthy.

### Ubuntu VM Fresh Install Full QA (`develop`, 2026-04-08)

- Completed a 45-test-case fresh-install QA on Ubuntu VM (10.211.55.5) using `install.py --defaults --http` on `develop` HEAD, covering all v0.6.0 features via both browser automation and API curl.
- **Installation:** Installer ran fully unattended, built all images (backend, frontend, WhatsApp MCP, Toolbox) on ARM64 Ubuntu 24.04, passed health checks. Ollama installed with llama3.2.
- **Setup Wizard:** Completed via browser with 3 LLM providers (Gemini, OpenAI, Anthropic), global admin credentials captured. 6 default agents seeded.
- **Provider Matrix:** All 4 SaaS providers (Gemini, OpenAI, Anthropic) connected successfully. Ollama local model discovered. Brave Search and Tavily API keys configured.
- **Core Features Validated:** Playground chat (Gemini 2.5 Flash, correct responses), Memory Inspector (working memory populated), Knowledge Base (ACME Sales CSV upload + price retrieval with SKU), Sandboxed Tools (dig 107ms, nmap 2.6s), MCP Server registration (stdio), Custom Skills (instruction type), API v1 (client creation, API-key auth, OAuth token exchange, sync chat, async chat + queue polling), Vector Store auto-provisioning (Qdrant healthy + container running), Project creation, Flow creation, 28 slash commands seeded, A2A permission creation, all 15 settings pages 200, all 4 system admin pages 200.
- **New Bugs Found (3):** BUG-434 (setup wizard global admin missing tenant_id/role — Critical), BUG-435 (setup completion button no-op — Low), BUG-436 (A2A delegation not triggered via API chat — Medium).

### Bug Sprint — BUG-434 to BUG-443 resolved (`develop`, 2026-04-08)

- **BUG-434 (Critical):** Fixed setup/auth tenant bootstrap so initial admin creation no longer leaves the account without tenant context/owner role, and tenant-scoped auth-side logging now fails safely instead of cascading into login 500s.
- **BUG-435 (Low):** Fixed the setup completion CTA so the "Continue to Login" action now performs an explicit redirect to `/auth/login`.
- **BUG-436 (Medium):** Fixed API v1 A2A delegation by auto-managing the `agent_communication` skill when permissions are created/updated, allowing sync chat to trigger inter-agent tool usage.
- **BUG-437 (Medium):** Fixed installer-generated CORS defaults for local installs by including localhost/127.0.0.1 origins for HTTP setups and `https://localhost` for SSL setups.
- **BUG-438 (Medium):** Fixed localhost redirect handling by keeping HTTP-only installs on the non-redirect path while preserving HTTPS redirects only for SSL-enabled deployments.
- **BUG-439 (Medium):** Fixed Hub Communication so runtime tester instances are visible in the WhatsApp list while compose tester controls remain available for QA.
- **BUG-440 (Low):** Revalidated the repaired install path so `/api/v1/agents` once again returns the tenant's seeded agents instead of the empty payload seen in the failing fresh-install QA run; no API v1 route contract change was required.
- **BUG-441 (Low):** Fixed Sentinel config aliasing so the legacy `enabled` field resolves to the effective boolean state alongside `is_enabled`.
- **BUG-442 (Low):** Fixed flows routing so both `/api/flows` and `/api/flows/` work without 307 redirect surprises, and verified UI flow CRUD against the restored instance.
- **BUG-443 (Low):** Fixed development auth throttling defaults so `disabled`/`selfsigned` installs use `30/minute` unless an explicit override is provided.
- Added stack-scoped Caddy upstream generation (`{stack}-frontend` / `{stack}-backend`) plus a live proxy hardening update for the restored HTTPS install, preventing `https://localhost` from drifting onto another running Tsushin stack on the shared Docker network.
- Preserved-instance revalidation passed after restoring the original stack data: login succeeded for the known accounts, `GET /api/flows` and Sentinel/A2A/API v1 checks passed, Playwright covered Watcher, Hub Communication, Flows CRUD, Sentinel settings, and API Clients, and the restored data baseline remained `users=3`, `agents=22`, `flows=59`, `api_clients=39`.

### Bug Sprint — 6 bugs resolved (`develop`, 2026-04-08)

- **BUG-433 (High):** Fixed queue item poll (`GET /api/queue/item/{id}`) returning completed status without the agent's response text. Added `result` field extraction from `item.payload` to the response dict.
- **BUG-428 (High):** Fixed intermittent HTTP 500 on API client creation (`POST /api/clients`). Made `created_at`/`updated_at` Optional in the `ApiClientResponse` Pydantic model to prevent validation failure when datetime is None before DB refresh.
- **BUG-431 (Medium):** Fixed project creation (`POST /api/projects`) returning empty response. Added defensive error handling around `ProjectResponse` serialization in both create and update endpoints with explicit error messages.
- **BUG-430 (Medium):** Fixed setup wizard accordion not scrollable. Changed outer container from `flex items-center justify-center` to `flex flex-col items-center` with `my-auto` on inner container for natural browser scrolling.
- **BUG-429 (Medium):** Fixed Ollama systemd override instructions using non-portable `echo -e`. Replaced with POSIX-compliant `printf` in installer post-install output.
- **BUG-432 (Low):** Fixed vector store instances endpoint returning empty response on fresh install. Added null guard `(instances or [])` to ensure valid JSON array is always returned.

### v0.6.0 Comprehensive E2E Audit (`develop`, 2026-04-08)

- Completed a full fresh-install E2E audit on Ubuntu VM (10.211.55.5) using `install.py --defaults --http` on `develop` HEAD, covering 37 test cases via both browser automation and API curl.
- **Installation:** Installer ran unattended, built all 5 Docker images (backend, frontend, WhatsApp MCP, Toolbox) on ARM64, passed health checks within 20 minutes.
- **Setup Wizard:** Completed via browser with 3 LLM providers (Gemini, OpenAI, Anthropic), captured global admin credentials, created 6 default agents.
- **Provider Matrix:** Gemini, OpenAI, Anthropic, and local Ollama (llama3.2) all tested and connected successfully. Vertex AI instance created.
- **Core Features Validated:** Playground chat (text + response streaming), Memory Inspector (fact CRUD), Sentinel/MemGuard (injection detected at 0.9, poisoning at 0.9, benign at 0.0), A2A permissions, 28 slash commands, custom instruction skill creation, flow creation, 28 page routes all returning 200.
- **New Bugs Found (6):** BUG-428 (API client creation 500), BUG-429 (Ollama systemd override malformed), BUG-430 (setup accordion not scrollable), BUG-431 (project API empty response), BUG-432 (vector store empty response), BUG-433 (queue poll missing response text).

### Fresh Install Stabilization Closeout (`develop`, 2026-04-08)

- Hardened fresh-install memory extraction so manual fact extraction can recover conversation history from canonical aliases (`playground`, API user, and API client sender-key variants) while still using the configured provider instance for inference.
- Added a lexical fallback for project knowledge retrieval when Chroma collections are absent or empty on fresh installs, and seeded built-in English/Portuguese project command patterns so project entry/exit/list/upload/help flows are available without manual setup.
- Improved stdio MCP resilience by adding a retry path for transient `No JSON-RPC response received` failures and extending the short-lived tool-call keepalive window used by toolbox-hosted servers.
- Fixed fresh-install frontend/runtime regressions by waiting for a resolved pathname before public auth bootstrap, standardizing Playground tool and custom-tool calls on the backend base URL, and preserving `TSN_STACK_NAME` when the installer writes a new `.env`.
- Fixed Playground conversation search on Postgres by skipping SQLite-only FTS probes on non-SQLite dialects and rolling back failed probes/searches before falling back to LIKE mode.
- Added WhatsApp QA guardrails: tester and tenant agent status now warn when they share the same phone number, and MCP instance creation rejects duplicate numbers already owned by another agent instance or by the authenticated tester session.
- Final audit note: the disposable fresh install completed end-to-end, but a true tester-to-agent WhatsApp round-trip could not be proven in this run because the user authenticated both tester and agent against the same WhatsApp number. The product now warns and blocks that configuration for future validations.

### QA Audit — Ubuntu VM Fresh Install (`develop`, 2026-04-07)

- Completed a real-user fresh-install audit on `root@10.211.55.5` using the interactive installer (`python3 install.py`) on `develop` HEAD with backend `8081`, frontend `3030`, remote access, and HTTP-only setup.
- Completed `/setup` through browser automation at `http://10.211.55.5:3030/setup`, created the tenant admin, captured the auto-generated global-admin credentials, and validated both tenant and global admin login paths.
- Re-validated the major release-0.6.0 surfaces that now work on a fresh VM: hosted provider setup (Gemini/OpenAI/Anthropic), local Ollama connectivity, A2A delegation + Graph View visibility, Qdrant auto-provisioning as tenant default, Sentinel/MemGuard detections, shell beacon + sandbox tooling, direct project chat, API v1 direct-key and OAuth auth, sync/async chat, and generated-client communication against the live `/openapi.json`.
- Expanded `deployment-test-playbook.md` with the Ubuntu VM audit profile plus new cases for setup/onboarding, provider matrix, memory-mode validation, vector-store coverage, Sentinel/MemGuard, MCP/custom skills, shell/sandbox/slash commands, API v1/generated clients, flows, projects, and A2A graph monitoring.
- Logged newly confirmed fresh-install regressions in the bug tracker for follow-up:
  - Setup and onboarding: `BUG-402`, `BUG-403`, `BUG-404`, `BUG-405`, `BUG-406`
  - Agent/chat/memory: `BUG-407`, `BUG-408`, `BUG-409`, `BUG-417`, `BUG-418`, `BUG-419`
  - Skills, search, vector-store, and tooling: `BUG-410`, `BUG-411`, `BUG-412`, `BUG-413`, `BUG-414`, `BUG-415`, `BUG-416`, `BUG-420`
  - Projects and flows: `BUG-421`, `BUG-422`

### Bug Fixes — Setup / Dashboard / Auth (`develop`, 2026-04-07)

- **BUG-402 / BUG-403 — Public auth/setup pages were noisy before login:** Public setup/login surfaces now suppress unauthenticated bootstrap polling and ship a real favicon, eliminating pre-login `401`/`404` console noise on fresh installs.
- **BUG-404 — Setup only provisioned the first provider key:** The setup wizard now creates provider instances for every supported provider configured during onboarding instead of silently downgrading secondary providers to service-key-only state.
- **BUG-405 / BUG-406 — First-login onboarding panel and charts were unstable:** The User Guide panel now dismisses reliably in the default viewport, and dashboard charts mount only after valid dimensions exist, removing the negative-dimension warnings on first login.

### Bug Fixes — Agents / Memory / API Threads (`develop`, 2026-04-07)

- **BUG-407 — Agent contact reassignment could 500:** The protected agent update path now validates tenant ownership and contact uniqueness cleanly instead of crashing during contact swaps.
- **BUG-408 / BUG-409 — Real Playground traffic could destabilize health and log sender fallback warnings:** Playground/API chat identity is now built from canonical thread/channel keys, which keeps health checks stable under real threaded traffic and removes `Contact not found` fallback noise for normal Playground usage.
- **BUG-417 / BUG-418 / BUG-419 — Thread retrieval and memory isolation semantics drifted from the product contract:** API v1 now persists canonical thread recipients for message lookup, `isolated` mode is truly per-thread for threaded API chats, and `channel_isolated` Playground memory now carries across threads inside the same channel while preserving per-thread history.

### Bug Fixes — API Clients / MCP / Slash Commands / Search (`develop`, 2026-04-07)

- **BUG-410 — API client create-then-list drift:** Newly created API clients now appear immediately in the list endpoint instead of only through direct lookup.
- **BUG-411 / BUG-412 / BUG-413 — MCP-backed custom skills were inconsistent across authoring, listing, and discovery:** MCP custom skills now execute correctly, round-trip through the agent assignment APIs, and appear in `/tools` output alongside built-in capabilities.
- **BUG-414 — `/shell` dispatch mismatched seeded metadata:** Shell slash commands now execute through the seeded `system` category path instead of returning an empty error payload.
- **BUG-415 / BUG-416 — Tooling metrics and MCP stdio discovery were misleading:** Empty Qdrant stats normalize to `0`, and stdio MCP discovery/test/list/call now works reliably against toolbox-hosted `uvx` servers.
- **BUG-420 — Legacy `google_search` ignored tenant Brave credentials:** The built-in flow search tool now resolves tenant-scoped Brave keys through the same key service as the newer web-search path.

### Bug Fixes — Projects / Flows / Vertex (`develop`, 2026-04-07)

- **BUG-421 — Small project KB uploads could hang/crash the backend:** Fixed the shared document chunker so trailing chunks always advance even when the remaining text is shorter than the configured overlap. Project KB uploads now reuse the safe chunking path and only do the final status commit when the processing path has not already committed it.
- **BUG-422 — API v1 notification steps accepted invalid configs that failed at runtime:** Added create/update validation for notification steps so they fail fast unless they include a recipient and message content. Legacy `message` input is normalized to `message_template`, and the local public API regression script now uses a valid notification example.
- **BUG-423 — Saved Vertex AI provider-instance tests diverged from runtime and crashed on response parsing:** Saved provider-instance connection tests now execute through `provider_instance_id`, matching the real runtime credential/config resolution path. OpenAI-compatible response parsing was hardened so Vertex Gemini responses with non-string or empty `message.content` no longer raise `AttributeError`.

## v0.6.0-patch.3 (2026-04-07)

### Bug Fixes — Fresh Install QA Sprint (15 open → 0 open)

**Critical**
- BUG-391: Custom skill registry no longer poisons unrelated agent chats — all `get_mcp_tool_definition()` call sites now use skill instances instead of classes

**High — Playground & Memory**
- BUG-387: Playground chat now passes `provider_instance_id` so instance-scoped credentials work
- BUG-388: Shared-memory agents use stable `"shared"` sender_key for cross-thread recall
- BUG-392: `/inject` now applies to next message (fixed sender_key mismatch between commands API and playground)
- BUG-398: New thread creation no longer leaks prior thread data (immediate ref update + cross-thread guard)

**High — Flows**
- BUG-393: Flow skill nodes respect explicit `use_tool_mode: true` even when agent config says legacy
- BUG-394: Keyword-triggered flows no longer get stuck in "running" (robust commit/retry on finalization)

**High — Platform**
- BUG-389: KB document uploads properly reach "completed" status (commit before embeddings)
- BUG-390: Toolbox Dockerfile now includes `uv` package for `uvx` MCP server support
- BUG-395: Hub Communication tab surfaces runtime tester instances with source badge
- BUG-396: Project detail page no longer crashes (replaced undefined `PROJECT_ICONS` with `PROJECT_ICON_MAP`)

**Medium**
- BUG-385: Installer frontend recovery uses `TSN_STACK_NAME` for custom stack names
- BUG-386: Setup wizard persists selected model on provider instance (`available_models` no longer empty)
- BUG-397: Memory Inspector senderKey stripped of thread suffix to match memory storage key
- BUG-399: Shared Knowledge stat cards show correct counts (query accessible-to, not shared-by)
- BUG-400: Fresh install KB document upload no longer OOM-crashes — sentence-transformer model pre-downloaded in Docker image + graceful fallback if model unavailable

### QA Validation
- Fresh install end-to-end: setup wizard, provider config, playground chat, memory recall, sandboxed tools, custom skills, knowledge base, flows — all passing
- Dual-surface coverage: API tests + browser automation

## v0.6.0-patch.2 (2026-04-07)

### Bug Fixes — VM Fresh Install Retest

- BUG-382: detect_only Sentinel mode no longer stores prompt injections in working memory (prevents memory poisoning persistence)
- BUG-383: Setup wizard now links all seeded agents to the primary provider instance (provider_instance_id was null)
- BUG-384: Web search skill correctly resolves tenant-scoped Brave Search API keys (fixed null tenant_id injection check)

## v0.6.0-patch.1 (2026-04-07)

### Bug Fixes — Full Sprint (41 open → 0 open)

**Critical Memory Pipeline**
- V060-MEM-021: WhatsApp/Telegram/Slack/Discord messages now properly indexed in ChromaDB

**Playground Core UX**
- BUG-376: WebSocket streaming replies now appear without page refresh (stale closure fix)
- BUG-378: Playground chats now create agent_run records for Watcher dashboard
- BUG-372/377: Memory Inspector correctly queries shared memory for shared-mode agents
- BUG-381: Uploaded documents/images now injected into chat context via document search

**API v1 Isolation**
- BUG-366: Isolated-mode agents no longer leak memory across API clients
- BUG-367: API v1 threads scoped per API client (api_client_id column)

**Backend Logic & Tenant Context**
- BUG-370: Flow skill steps now inject tenant_id for provider resolution
- BUG-371: /shell slash command seeded on fresh installs (idempotent seeding)
- BUG-379: A2A communication inherits target agent's full memory recall stack

**MCP & Infrastructure**
- BUG-374/368: Invalid stdio MCP servers properly fail connection/health checks
- BUG-369: Vector store container names capped at 63 chars (DNS label fix)
- BUG-373: Provider instance defaults atomically cleared on create/update

**Memory/OKG Subsystem**
- V060-MEM-022: Added GET /agents/{id}/memory/search endpoint
- V060-MEM-023: Port allocator checks running Docker containers
- V060-MEM-024: OKG decay uses agent-configured lambda
- V060-MEM-025: OKG MemGuard defaults to block mode (okg_detection_mode)

**Install/Setup/Config**
- BUG-365: Setup wizard reveals global admin credentials on completion
- BUG-362: Docker compose services labeled (tsushin.managed, lifecycle, service)
- BUG-363: Container/volume names parameterized via TSN_STACK_NAME
- BUG-380: QA Tester shortcuts resolve runtime instances as fallback

**Documentation**
- BUG-375: Tavily documented as unsupported in v0.6.0

### Database Migrations
- 0029: Add api_client_id column to conversation_thread
- 0030: Add okg_detection_mode column to sentinel_profile

## [0.6.0] - 2026-04-07

### Bug Fixes

#### Fresh-Install Dual-Surface Audit Summary — 2026-04-07

- **Disposable fresh-install validation completed:** Ran a real installer + real `/setup` audit in an isolated git-excluded clone of `develop` at `bef22daa0b475c374eb7baa21c8496a7294edfc1`, using browser automation and direct API checks together where they exercised different paths.
- **Validated working fresh-install surfaces:** Confirmed installer/setup, provider onboarding (Gemini, OpenAI, Anthropic, Ollama, Brave Search), knowledge base upload/use, custom skills create/test, sandboxed tools, slash commands including `/inject`, shell command center, Sentinel baseline protections, programmatic flows, project conversations, and Playground document/image upload-list behavior.
- **Fresh-install regressions documented in tracker:** Logged/confirmed fresh-install issues around Docker naming and install isolation (`BUG-362`, `BUG-363`), hidden global-admin creation (`BUG-365`), missing `/shell` on fresh PostgreSQL installs (`BUG-371`), Memory Inspector / Watcher mismatches (`BUG-372`, `BUG-377`, `BUG-378`), provider-default drift (`BUG-373`), false-positive stdio MCP health (`BUG-374`), Tavily absence (`BUG-375`), A2A memory loss (`BUG-379`), QA tester shortcut hard-coding (`BUG-380`), and detached Playground file/image context (`BUG-381`).
- **Environment restore completed:** Removed the disposable fresh-install containers, fresh volumes, fresh images, and the temporary clone folder, then restored the original local Tsushin runtime and its previously running runtime-managed containers. WhatsApp QR/E2E messaging was skipped for this closeout at user request.

#### Installer & QA Hardening — 2026-04-07

- **Installer remote HTTP health checks:** `install.py` now probes backend/frontend health on `127.0.0.1` instead of `localhost`, which avoids false frontend failures when localhost-only redirect logic is active. For HTTP remote installs, the success output now prints the configured public host/IP instead of `localhost`.

#### VM Retest Bug Sprint (BUG-348, BUG-349, BUG-350, BUG-352, BUG-353, BUG-356, BUG-360, BUG-361) — 2026-04-07

- **BUG-348 — HTTP redirect breaks remote installs (CRITICAL):** Middleware now only redirects `localhost` HTTP to HTTPS, preserving remote HTTP access for IP-based installs.
- **BUG-349 — ops/ excluded from Docker image (MEDIUM):** Removed `ops/` exclusion from `.dockerignore` so test-user helpers are available inside the container.
- **BUG-350 — create_test_users.py stale against RBAC schema (MEDIUM):** Added required `tenant_id` and `assigned_by` to `UserRole` creation.
- **BUG-352 — Memory Inspector still failed without manual key (HIGH):** Moved `playground_u{uid}_a{aid}` to FIRST position in memory inspector `possible_keys` list.
- **BUG-353 — Custom skills still failed with Tool not found (HIGH):** Root cause was `register_custom_skills()` was never called. Added call in `agent_service.py` before custom tool def collection.
- **BUG-356 — Flows reminders failed with invalid recipient (HIGH):** Added playground recipient detection in scheduler — `playground_u*_a*` recipients are treated as delivered without WhatsApp routing.
- **BUG-360 — Thread list showed message_count=0 (MEDIUM):** Fixed sender_key lookup in `list_threads` to strip thread suffix before querying Memory table.
- **BUG-361 — Image uploads could abort connection (HIGH):** Image processing now inlines text generation, uses `try/finally` for `db.commit()`, prevents documents stuck in "processing".

#### Fresh-Install QA Bug Sprint (BUG-351 through BUG-359) — 2026-04-07

- **BUG-351 — `PUT /api/agents/{id}` silently dropped `provider_instance_id` (HIGH):** Added `provider_instance_id` to `UPDATABLE_AGENT_FIELDS` allowlist, `AgentUpdate`/`AgentResponse` Pydantic schemas, and both GET/list response dicts so the field persists and is returned in API responses.
- **BUG-352 — Playground History/Memory Inspector returned empty results (HIGH):** `get_conversation_history()` used `playground_user_{id}` while messages were stored under `playground_u{uid}_a{aid}`. Aligned history and memory inspector to use the same sender_key format as `send_message()`.
- **BUG-353 — Instruction-style custom skills failed with `Tool not found` (HIGH):** Custom skill tool names (`custom_{slug}`) weren't resolved through the skill manager because dynamically created subclasses lack the `_record` for `get_mcp_tool_definition()`. Added fallback in `_find_skill_by_tool_name()` to resolve `custom_` prefixed names via registry key.
- **BUG-354 — Browser automation blocked benign URLs on Sentinel LLM failure (HIGH):** When Sentinel's LLM is unavailable, it returned fail-closed blocks for all URLs. Browser automation now fails-open when Sentinel returns "Security analysis unavailable", relying on pattern-based SSRF validator as fallback.
- **BUG-355 — Shell beacon check-ins stalled backend health checks (CRITICAL):** `wait_for_completion_async()` created a new `sessionmaker` on every poll iteration (up to 120x), exhausting the connection pool. Moved `sessionmaker` creation outside the loop and simplified beacon check-in to reuse the injected session with `expire_all()`.
- **BUG-356 — Flows reminder creation resolved to failed notifications (HIGH):** The flows provider built NOTIFICATION payloads without `sender_key`, so the scheduler couldn't resolve the recipient. Passed `sender_key=message.sender_key` through both `create_event()` call sites and added it to the notification payload.
- **BUG-357 — Audio transcription ignored tenant-scoped OpenAI keys (HIGH):** `AudioTranscriptSkill` created its own DB session and called `get_api_key("openai", db)` without `tenant_id`. Now uses the caller-provided session and passes `tenant_id` from config.
- **BUG-358 — Audio errors wrapped in Pydantic validation instead of real cause (MEDIUM):** Error return paths in `process_audio()` were missing `timestamp` field, causing `PlaygroundAudioResponse(**result)` to raise a Pydantic validation error. Added timestamp to all 5 error return paths.
- **BUG-359 — Playground had no image upload path (MEDIUM):** Added image extensions (.jpg/.jpeg/.png/.webp/.gif) to `SUPPORTED_EXTENSIONS` in document service, added image-specific processing that skips heavy embedding, and updated frontend file input accept list.

#### Release Re-Validation Fixes (BUG-345, BUG-346, BUG-347) — 2026-04-07

- **BUG-345 — API v1 agent creation bypassed tenant `max_agents` cap (HIGH):** The `POST /api/v1/agents` endpoint did not enforce the tenant agent cap, allowing unlimited agent creation through the public API while the standard route correctly returned 409. Added the same `Tenant.max_agents` enforcement from the standard route to the v1 route before contact/agent creation.
- **BUG-346 — Create Agent modal defaulted to Anthropic instead of tenant's default provider (MEDIUM):** The `getSmartDefaults()` function used `providerInstances[0]` (first in list) instead of the instance marked `is_default=true`. Updated to find the default provider instance and use its `available_models[0]` for the model name, with a useEffect to apply defaults when instances load.
- **BUG-347 — Hub API v1 tooling surface non-functional for Gmail/Calendar/Flights (HIGH):** Added `INTEGRATION_CAPABILITIES` matrix to define per-type support for health_check, tools, and tool_execution. Integration summaries and provider listings now include a `capabilities` dict. Health, tool listing, and execution endpoints check capabilities upfront with clear error messages. Added `google_flights` to the providers list. The service factory now handles `google_flights` with an informative error instead of a generic "unsupported type".

#### Post-Sprint Regression Fixes — 2026-04-07

- **BUG-334 follow-up — `skipTour` used `window.confirm()` blocking browser events:** The "Skip Tour" button called `window.confirm()` which blocks all browser events, preventing programmatic dismissal and breaking automated tests. Replaced with direct localStorage persist matching the same pattern used by `dismissTour()` and the Escape key handler. Tour is now immediately dismissed without a confirmation dialog.
- **Perfection audit fixes:** (1) `client.ts` 409 error guard changed from message-string comparison (`!== 'Unexpected end of JSON input'`) to `!(jsonErr instanceof SyntaxError)` — prevents HTML error bodies from surfacing raw SyntaxError text to users; (2) `agent_switcher_skill.py` `_find_agent_by_name()` and `_get_available_agents()` now apply `tenant_id` filter to prevent cross-tenant agent resolution in multi-tenant deployments; (3) `routes_flows.py` `create_flow_v2` endpoint now re-raises `HTTPException` before the generic `except Exception` catch (matching `create_flow` pattern); (4) `GoogleCredentials` TypeScript interface in `settings/integrations/page.tsx` and `settings/security/page.tsx` now includes `configured?: boolean` for type safety.

#### Playground & Flows Bug Fixes (BUG-331, BUG-335, BUG-336, BUG-344) — 2026-04-07

- **BUG-344 — `/api/health` reported stale version v0.5.0 while frontend showed v0.6.0 (LOW):** Changed `SERVICE_VERSION = "0.5.0"` to `SERVICE_VERSION = "0.6.0"` in `backend/settings.py`. The health and readiness endpoints now correctly return `"version": "0.6.0"`, matching the frontend footer.

- **BUG-335 — Playground created a new empty thread on every page load (LOW):** `initializeThreads()` in `frontend/app/playground/page.tsx` only checked if the most-recent thread was empty. If the most-recent thread had messages (normal after any use), a new thread was created on every subsequent page load, accumulating orphan threads. Fixed by searching ALL threads for any with `message_count === 0` (or undefined). A new thread is now only created when every existing thread already has messages. Verified: navigating to Playground 3 times kept the thread count stable.

- **BUG-336 — Flow keyword triggers did not intercept messages in the Playground channel (MEDIUM):** Flows with `execution_method='keyword'` only fired on external channel messages (WhatsApp, Telegram); Playground messages were routed directly to the AI instead. Implemented full end-to-end keyword-trigger support: (1) Added `KEYWORD = "keyword"` to `ExecutionMethod` enum in `schemas.py`; (2) Added `trigger_keywords` JSON column to `FlowDefinition` model with Alembic migration `0028`; (3) Updated `routes_flows.py` to accept/store/return `trigger_keywords` in all create, patch, and response paths; (4) Added `_check_keyword_flow_triggers()` method in `PlaygroundService` — queries active keyword flows for the tenant, matches message text against configured keywords (slash-command prefix match or substring match), and fires matching flows via `FlowEngine.run_flow()`; (5) Injected keyword-trigger check at "STEP 2.5" in both `send_message()` (sync) and `process_message_streaming()` (streaming) paths, returning/yielding a flow acknowledgement before any AI processing; (6) Added keyword UI in Flows page — list badge with hash icon, and keyword textarea in create/edit modals.

- **BUG-331 — Ollama unreachable from Docker backend (binds to 127.0.0.1 by default) (MEDIUM):** Users connecting Ollama to Tsushin got "Cannot connect to Ollama" because the Ollama service binds to `127.0.0.1:11434` by default, which is unreachable from the Docker container. Added a persistent "Docker Networking Note" guidance block in `frontend/app/hub/page.tsx` in the Ollama section, showing the correct Docker gateway URL (`http://172.18.0.1:11434`) and the `OLLAMA_HOST=0.0.0.0:11434` systemd override command. Also added an "Local Ollama (optional)" section to the installer success output in `install.py` with the same step-by-step instructions.

#### Onboarding UX Overhaul — Fragmented Experiences Unified (BUG-318, 319, 320, 321, 322, 323, 325, 334) — 2026-04-07

Eight overlapping onboarding UX bugs resolved in a coordinated fix across `OnboardingContext.tsx`, `OnboardingWizard.tsx`, `WhatsAppWizardContext.tsx`, `GettingStartedChecklist.tsx`, and `LayoutContent.tsx`:

- **BUG-318 — Three sequential onboarding experiences on fresh install (MEDIUM):** Removed the `tsushin:onboarding-complete` event dispatch from `completeTour()` and the auto-launch listener from `WhatsAppWizardContext`. The WhatsApp wizard now only opens when explicitly triggered: via the Getting Started Checklist "Connect a Channel" button (`forceOpenWizard`) or tour step 5 action button (`openWizard`).

- **BUG-319 — Tour step 9 duplicated Getting Started Checklist (LOW):** Removed tour step 9 ("Setup Checklist") entirely. `TOTAL_STEPS` reduced from 9 to 8. New step 8 ("You're All Set!") is a brief completion message pointing users to the Getting Started Checklist on the dashboard. Tour now shows "Step 1 of 8".

- **BUG-320 — Getting Started Checklist visible beneath tour modal (LOW):** `GettingStartedChecklist.tsx` now imports `useOnboarding` and returns `null` immediately when `onboardingState.isActive` is true. Checklist is completely hidden while the tour is running.

- **BUG-321 — Tour step 5 and WhatsApp Wizard covered the same task (MEDIUM):** Tour step 5 action button now calls `openChannelsWizard()` which launches the WhatsApp Setup Wizard directly. When the wizard closes, `tsushin:whatsapp-wizard-closed` event fires and the tour auto-advances to step 6 (Flows).

- **BUG-322 — "Connect a Channel" link couldn't relaunch dismissed wizard (LOW):** Added `forceOpenWizard()` to `WhatsAppWizardContext` that clears `tsushin_whatsapp_wizard_dismissed` before opening. Getting Started Checklist "Connect a Channel" item is now a button calling `forceOpenWizard()` instead of a Link to `/hub?tab=communication`. Hub page also updated to use `forceOpenWizard`.

- **BUG-323 — Tour steps 4 and 5 both navigated to /hub with no context (LOW):** Step 5 now launches the WhatsApp wizard directly via `openChannelsWizard()`. This provides clear channel-specific UX instead of re-showing the generic Hub page.

- **BUG-325 — Tour auto-started on top of open User Guide panel (MEDIUM):** `OnboardingContext` tracks `isUserGuideOpen` via event listeners for `tsushin:open-user-guide` / `tsushin:close-user-guide`. Auto-start skips if User Guide is open (using ref to avoid stale closure race). `LayoutContent.tsx` dispatches `tsushin:close-user-guide` when the panel closes. Tour step 1 "Open User Guide" button is disabled with updated label when the guide is already open.

- **BUG-334 — Tour overlay reappeared on every page navigation (MEDIUM):** Added dedicated `dismissTour()` function that calls `localStorage.setItem('tsushin_onboarding_completed', 'true')` SYNCHRONOUSLY before any React state update. Modal's `onClose` prop and Escape key handler both call `dismissTour()`. A `tourDismissedRef` prevents deferred auto-start from restarting the tour after dismissal. Verified: programmatic Escape key immediately sets localStorage; navigation to `/agents` does not reshow the tour.

#### Settings & Admin Navigation UX (BUG-326, BUG-327, BUG-330) — 2026-04-07

- **BUG-326 — `/settings/filtering` orphaned from Settings hub (MEDIUM):** Added a "Message Filtering" card to the advanced settings section of `frontend/app/settings/page.tsx`. The card includes a filter funnel icon, links to `/settings/filtering`, and requires `org.settings.write` permission. The page (group filters, DM allowlists, keywords, auto-response rules) was previously only discoverable by direct URL.

- **BUG-327 — Global-admin landing page was a placeholder (MEDIUM):** Replaced the placeholder content in `frontend/app/system/integrations/page.tsx` with a proper "System Administration" overview dashboard featuring four navigation cards: Tenant Management, User Management, Plans & Limits, and Platform Integrations. Removed all "This page will contain" placeholder text. Cards use consistent glass-card styling with purple theme.

- **BUG-330 — No admin UI for `max_agents` / tenant plan limits (LOW):** Added an "Edit" modal to `frontend/app/system/tenants/page.tsx`. The modal exposes editable fields for `max_agents`, `max_users`, `max_monthly_requests`, `plan`, and `status`, with current usage stats shown inline. The "View" button in the tenant table is replaced with "Edit". Uses existing backend `PUT /api/tenants/{id}` endpoint which already supports global-admin updates to all plan limit fields.

#### Skills, Memory & Sentinel Bug Fixes (BUG-328, BUG-329, BUG-332, BUG-333, BUG-341) — 2026-04-07

- **BUG-341 — Web search `serpapi` provider key rejected at runtime (MEDIUM):** The skill registry registers SerpAPI under the key `"google"`, but users who configured the skill with `"serpapi"` got a silent failure. Added `PROVIDER_ALIASES = {"serpapi": "google"}` normalization at the start of both `process()` and `execute_tool()` in `search_skill.py` so both provider names work identically at runtime.

- **BUG-333 — Web search skill silently fails with no user guidance when unconfigured (LOW):** When `web_search` skill was enabled but no search API key was configured, the LLM fabricated a misleading "I can't directly search" response. Added three detection points in `search_skill.py` (both `process()` and `execute_tool()`): no available providers, provider not found, or API key not configured — all now return: "Web search is not configured for this agent. Please set up a search provider in the Hub (Settings > Hub > Web Search) and link it to this agent's skill integrations."

- **BUG-329 — Cross-thread memory recall fails in Playground — new thread sees empty memory (MEDIUM):** Each playground thread used a thread-specific sender key (`playground_u{uid}_a{aid}_t{tid}`), so new threads started with empty memory and couldn't recall facts from previous threads. Changed `playground_service.py` to use a stable per-user-per-agent sender key (`playground_u{user_id}_a{agent_id}`) for all threads. Verified: told agent "my favorite number is 42" in thread 26, then started thread 27 and confirmed agent recalled "Yes, I remember! Your favorite number is 42."

- **BUG-328 — Sentinel falsely flags "remember this" as memory poisoning (MEDIUM):** Benign user preference requests ("please remember I prefer dark mode") triggered `memory_poisoning` detection, flooding logs with false-positive warnings. Rewrote all three aggressiveness-level `memory_poisoning` prompts in `sentinel_detections.py` to explicitly distinguish adversarial attacks (credential injection, AI identity override, jailbreak persistence, security bypass) from legitimate user preference storage. Updated unified classification prompts at all levels. Changed detect-only mode threat log from `WARNING` to `DEBUG` in `agent_service.py` to reduce noise.

- **BUG-332 — `CombinedKnowledgeService NOT initialized` WARN fires on every message (LOW):** The `[KB FIX] ❌ CombinedKnowledgeService NOT initialized` log was emitted at `WARN` level on every single agent message for agents without a linked project (the default). Changed `agent_service.py` to log at `DEBUG` when `project_id=None` (expected case) and only log at `WARN` when `project_id` is set but initialization fails.

#### A2A Playground Agent Switching & Flow Type Assignment (BUG-338, BUG-342) — 2026-04-07

- **BUG-338 — A2A agent switching fails in Playground with contact profile error (HIGH):** `AgentSwitcherSkill` required a Contact DB record to complete agent switching but Playground users have no such record (their sender is `playground_user_{id}`). Added `_is_playground_context(message)` helper that detects playground sessions via sender prefix or channel field. Both `process()` and `execute_tool()` now bypass the contact-required check for playground sessions and persist the switch via `UserAgentSession` using the sender_key directly (same approach as slash command service). `ContactAgentMapping` is only updated when a real Contact exists. Verified: `execute_tool()` returns `success=True, "Successfully switched to agent Kokoro"` for playground users.

- **BUG-342 — `POST /api/flows/` ignores `flow_type` parameter (MEDIUM):** The internal `POST /api/flows/` endpoint used `FlowDefinitionCreate` which lacked `flow_type` and `execution_method` fields, causing both to be hardcoded as `"workflow"` and `"immediate"`. Added `flow_type` and `execution_method` optional fields to `FlowDefinitionCreate`. Added `VALID_FLOW_TYPES` and `VALID_EXECUTION_METHODS` constant sets with input validation that returns HTTP 422 for unknown values. Re-raised `HTTPException` before the generic `except Exception` catch so validation errors are no longer silently swallowed as 500s. Verified: `POST /api/flows/` with `"flow_type": "notification"` now returns `"flow_type": "notification"`; unknown types return `422 {"detail": "Invalid flow_type ..."}`.

- **BUG-339 — Create Agent UI form hangs on 409 plan-limit error (HIGH):** When the Create Agent modal received a 409 "Agent limit reached" response, the button remained stuck in "Creating..." indefinitely with no error shown. Added `createError` state to the form — errors are now displayed inline inside the modal. Updated `client.ts` to extract the specific `detail` string from 409 JSON responses before falling back to the generic conflict message, giving users a meaningful error like "Agent limit reached. Your plan allows a maximum of X agents."

- **BUG-340 — Seeded agents (6) exceed free-plan default limit (5) on fresh install (HIGH):** Fresh-install tenants were created with `max_agents=5` but the seed script creates 6 default agents, immediately blocking the user from creating their first custom agent. Increased `max_agents` default to 10 in `models_rbac.py`, `auth_service.py`, and `routes_tenants.py`. Also corrected `max_users` (1→5) and `max_monthly_requests` (1000→10000) model defaults to match realistic free-plan values.

#### Direct Port HTTP Redirect & Hub Fresh-Install 404s (BUG-324, BUG-343) — 2026-04-07

- **BUG-324 — HTTP direct port redirects to HTTPS (HIGH):** Added Next.js middleware (`frontend/middleware.ts`) that issues a 301 redirect from any HTTP direct-port access (`http://<host>:3030`) to `https://localhost`. When `NEXT_PUBLIC_API_URL=https://localhost`, visiting the app over HTTP caused CORS failures and mixed-content blocks because the browser page (HTTP) was calling an API on a different HTTPS origin. The middleware skips the redirect for Docker internal health checks (`127.0.0.1` host) so the container health check remains green. All other HTTP-to-direct-port requests are redirected to the canonical HTTPS URL.
- **BUG-343 — Hub 404 console errors on fresh install (MEDIUM):** Two-part fix. (1) Slack/Discord 404s (`GET /api/integrations/slack/`, `GET /api/integrations/discord/`) were already resolved in commit `2ad1c1f` by updating route paths to match the Phase 23 backend structure. (2) Google credentials 404 on fresh install fixed by changing `GET /api/hub/google/credentials` to return `200 {"configured": false}` instead of HTTP 404 when no Google OAuth credentials are configured for the tenant. The `GoogleCredentialsResponse` Pydantic model now includes a `configured` boolean field. All three frontend consumers (`hub/page.tsx`, `settings/integrations/page.tsx`, `settings/security/page.tsx`) updated to check `data.configured === false` and treat it as null (unconfigured). Verified: Hub page loads with 0 console errors and all integration API calls return 200.

#### Onboarding Tour Navigation Takeover (BUG-337) — 2026-04-07

- **BUG-337 — Onboarding tour redirects Watcher/Flows/Settings on fresh install (CRITICAL):** The onboarding `navigateToStep()` function in `OnboardingContext.tsx` called `router.push()` automatically whenever the user clicked Next/Previous in the wizard, forcibly navigating away from pages the user had intentionally opened. This made `/` (Watcher/Dashboard), `/flows`, and `/settings/integrations` inaccessible on fresh installs where the tour was active. Removed the entire `navigateToStep()` function and all `router.push()` calls from `nextStep()`, `previousStep()`, and `goToStep()`. Wizard step advancement now only increments the step counter. Action buttons within individual steps (e.g., "Set Up Channels in Hub") remain as opt-in navigation, giving users full control. Also removed the now-unused `useRouter` import.

### Bug Fixes (BUG-309 through BUG-317 — Ship-Gate + Security Audit Sprint)

- **BUG-309:** Added RBAC permission checks (`hub.read`/`hub.write`) to all 14 Google integration routes, preventing privilege escalation from member to integration admin.
- **BUG-310:** Secured legacy `/ws` WebSocket endpoint with JWT authentication and tenant-scoped connection tracking. Replaced global `broadcast()` with `broadcast_to_tenant()` to eliminate cross-tenant information disclosure.
- **BUG-311:** Discord interaction signature verification now uses per-integration `public_key` stored in the database instead of a global environment variable, ensuring multi-tenant isolation.
- **BUG-312:** Slack HTTP Events `url_verification` handshake now works correctly — `app_id` stored per-integration for reliable resolution, `signing_secret` required when `mode="http"`. New CRUD API at `/api/slack/integrations/`.
- **BUG-313:** Discord inbound interactions are now fully configurable via the integration API — `public_key` is a required field on create. New CRUD API at `/api/discord/integrations/` and inbound webhook at `/api/channels/discord/{id}/interactions`.
- **BUG-314:** Tenant `max_agents` plan limits are now enforced on agent creation in both standard and v2 API routes, returning HTTP 409 when the limit is reached.
- **BUG-315:** Fixed Playwright browser path in Docker container — set `PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers` so the non-root `tsushin` user can find Chromium at runtime.
- **BUG-316:** Normalized Google Flights date parameters with 3-layer defense (dataclass stripping, provider regex+validation, format fallback parsing) to prevent SerpApi 400 errors from quoted date strings.
- **BUG-317:** Fixed skill test endpoint to apply persisted config, database session, and agent context to skill instances before calling `can_handle()`, eliminating false-negatives for config-driven skills like `web_search`.

### Security

- **Next.js 16 upgrade (PR [#5](https://github.com/iamveene/Tsushin/pull/5) revival, originally by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Upgraded frontend from Next.js 14.2.33 to 16.2.2, React 18.2.0 to 19.2.0, ESLint 8 to 9 (flat config). Resolves CVE-2025-29927, CVE-2024-34351, CVE-2024-46982, CVE-2024-51479. Applied fixes for Google Fonts Docker build failure (--webpack flag), removed unnecessary monorepo boilerplate from next.config.mjs, migrated ESLint to flat config (eslint.config.mjs), updated TypeScript JSX mode to react-jsx. Removed stale pnpm-lock.yaml and added it to .dockerignore.

### Community Contributions

- **WhatsApp contact name enrichment (PR [#6](https://github.com/iamveene/Tsushin/pull/6) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Improved WhatsApp DM contact name resolution across all layers. The Go MCP bridge now uses a richer fallback chain (FullName → PushName → FirstName → BusinessName → message PushName → sender) and detects raw numeric identifiers to force re-resolution. The API reader reuses human-readable `chat_name` as `sender_name` for DMs when contact mappings miss. The messages API endpoint enriches responses via `CachedContactService`, replacing raw @lid identifiers with friendly names in both `sender_name` and `chat_name` columns.
- **WhatsApp LID contact agent routing (PR [#8](https://github.com/iamveene/Tsushin/pull/8) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Fixed DM routing for contacts using WhatsApp LID identifiers. Extracted contact resolution into `_resolve_direct_message_contact()` with a richer fallback chain: `CachedContactService` → chat_id metadata → fuzzy name matching → WhatsApp auto-discovery. The auto-discovery service now records newly observed LID aliases as `ContactChannelMapping` entries instead of discarding them, ensuring contact-agent mappings are preserved across identifier changes.
- **Sanitize leaked tool-call markup (PR [#9](https://github.com/iamveene/Tsushin/pull/9) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** Local/Ollama models sometimes emit pseudo `[TOOL_CALL]` markup instead of plain replies. Added `_sanitize_unexecuted_tool_output()` to `AgentService` that extracts the user-facing message from `action: respond` blocks and strips unresolved fenced tool blocks before delivery.
- **AgentSwitcher contact resolution for WhatsApp aliases (PR [#10](https://github.com/iamveene/Tsushin/pull/10) by [offsecop](https://github.com/offsecop) — Thiago Oliveira):** `AgentSwitcherSkill._identify_sender()` now uses `ContactService` with `sender_key` and `chat_name` parameters for consistent contact resolution. Falls back through channel mappings, fuzzy name matching, and WhatsApp auto-discovery — matching the main router's resolution strategy.

### Improvements

#### Setup Wizard & Onboarding Tour Enhancements (2026-04-06)

- **System AI auto-assigned during initial setup:** The setup wizard now creates a ProviderInstance for the primary AI provider and automatically assigns it as the System AI. Previously, System AI had to be manually configured in the Hub after setup, leaving system operations (intent classification, skill routing, flow processing) without a provider until manually configured.
- **Onboarding tour updated with mandatory configuration guidance:** Revised all 9 tour steps to cover mandatory setup requirements. The tour now points users to the User Guide (accessible via ? button), explains that System AI is auto-configured, highlights communication channel setup as a required step with actionable buttons, and ends with a setup checklist summarizing completed and pending configuration items.
- **Communication Channels step made actionable:** The tour's Channels step now navigates to the Hub and includes a "Set Up Channels in Hub" action button, making it clear that connecting WhatsApp/Telegram is required for agents to communicate outside the Playground.

#### Dynamic Ollama Model Discovery (2026-04-06)

- **Ollama models now fetched dynamically from running instance:** Replaced all hardcoded Ollama model lists across 6 files (3 backend, 3 frontend) with dynamic discovery from the configured Ollama instance via `/api/tags`. Agent creation, agent configuration manager, playground config panel, Sentinel LLM providers, token tracker, and model pricing routes now all reflect the actual models available on the user's Ollama instance. Hub already showed dynamic models — now the agent creation and configuration selectors are consistent with it. Ollama models are automatically treated as free ($0) in pricing/cost tracking without needing to be individually listed.
- **SSRF validation now sends vendor context for Ollama URL validation:** The provider instance creation modal was blocking `host.docker.internal` URLs for Ollama because the frontend URL validation didn't pass the `vendor` parameter to the backend. Fixed `validateProviderUrl()` to pass the current vendor so Ollama/custom providers correctly allow Docker internal hostnames.
- **Ollama "Manage Instance" button on Hub Local Services card:** Added a "Manage Instance" link to the Ollama card in the Hub's Local Services section, allowing users to open the full provider instance edit modal to modify URL, API key, models, and other settings directly from the card.

### Bug fixes

#### Provider Instance Test Connection — Deprecated Model Fix (2026-04-06)

- **BUG-308 — Test connection uses deprecated/wrong model (HIGH):** The "Test Connection" button on provider instances ignored the user-selected model and fell back to hardcoded model IDs. For Anthropic, the fallback was `claude-3-5-haiku-20241022` (deprecated), causing a 404 error. Fixed by: passing the user's selected model from the frontend to both test connection endpoints (raw and saved), adding model priority chain (request > saved > fallback), and updating all hardcoded fallbacks to current models. Also updated all model selector lists, pricing tables, and discovery fallbacks across the platform to include Claude 4.6 series (Opus, Sonnet, Haiku) and removed deprecated Claude 3 Haiku / 3.5 Haiku entries.

#### Provider Instance Validation (2026-04-06)

- **BUG-305 — Provider instance model required validation:** Provider instances could be created without any models, making them unusable. Added frontend validation (disabled save button, red required asterisk, auto-add of typed model text on save) and backend validation (HTTP 400 if `available_models` is empty).

#### Data Loss Prevention & Custom Skills UX (2026-04-06)

- **BUG-302 — Database volume protection (CRITICAL):** PostgreSQL named volume `tsushin-postgres-data` was destroyed and recreated, wiping all tenant-created custom skills and MCP server configurations. Added explicit "Database Volume Protection" section to `CLAUDE.md` listing forbidden commands (`docker-compose down -v`, `docker volume rm`, `docker system prune --volumes`) with safe alternatives. Created `backend/scripts/backup_db.sh` for periodic pg_dump backups with automatic retention of the last 10 backups.
- **BUG-303 — Agent custom skills inline management:** The "Manage Custom Skills" button in the agent config Custom Skills tab redirected to the studio page instead of providing inline management. Replaced with an inline "Create Custom Skill" form for instruction-based skills (creates + auto-assigns to agent), a secondary "Custom Skills Studio" link for advanced types, and a persistent "New Skill" button in the header.

#### Bug Fixes (E2E validated 2026-04-06)

- **Summarization source_step field mapping:** `SummarizationStepHandler` now resolves `output` and `message` fields from slash_command/skill steps (previously only checked `raw_output`)
- **Summarization tenant_id:** Both summarization paths (conversation + raw text) now pass `tenant_id` to `AIClient` for proper API key resolution
- **Gate tenant_id:** Agentic gate handler passes `tenant_id` to `AIClient` for API key resolution
- **WhatsApp MCP registration:** Flow notification steps now resolve MCP URL from registered `WhatsAppMCPInstance` records
- **WhatsApp reliability hardening:** Added instance metadata reconciliation for stale `container_id` / path / URL state, health-check fallback from `container_id` to `container_name`, startup watcher preference for API-reader bootstrap, tenant-safe auto-binding metadata for Graph/Studio, Hub QR degraded-state recovery actions, and a dedicated QA Tester status surface. The tester Docker health probe now targets `GET /api/health`, and both WhatsApp bridges use supervised reconnect loops plus logout-triggered QR regeneration instead of one-shot reconnect attempts.
- **Systemic tenant_id audit (11 instances across 6 files):** Fixed remaining `tenant_id` resolution gaps found via full-codebase audit. **AIClient instantiation** (8 fixes): `SchedulerService` (5 methods: `_analyze_conversation`, `_generate_agent_reply`, `_generate_opening_message`, `_generate_closing_message`, `provide_conversation_guidance`), `ConversationKnowledgeService._call_agent_llm`, `AISummaryService.__init__`, `FactExtractor._get_ai_client` — all now pass `tenant_id` for proper per-tenant API key resolution. **Router cross-tenant agent queries** (3 fixes): `_select_agent` keyword match, default agent fallback, and slash-command default agent now filter by `Agent.tenant_id` to prevent cross-tenant routing. Updated all callers (6 files) to thread `tenant_id` through constructor chains.

### Implementations

#### System AI Configuration Simplification

- **Provider-instance-based System AI config:** The AI Configuration settings page (`/settings/ai-configuration`) now points to an existing Provider Instance from the Hub instead of maintaining its own duplicated provider/model lists. Added `system_ai_provider_instance_id` FK column to Config table (migration 0027). The backend resolves vendor, API key, and base URL from the linked ProviderInstance at runtime, with legacy fallback to the old `system_ai_provider`/`system_ai_model` columns. The frontend was rewritten to show a card selector of active Provider Instances with model picker from the instance's `available_models`, eliminating the hardcoded model catalog that went stale. Manual model entry is supported for instances with no discovered models.

#### Flow Execution UX

- **Async flow execution with live progress modal:** The `POST /api/flows/{flow_id}/execute` endpoint now returns immediately (HTTP 202) with a pending FlowRun, executing steps in a background task. The frontend ViewRunModal opens instantly on click and polls every 2s for live updates — showing a progress bar, per-step status with execution times, a pulsing "Live" header indicator, and a remaining-steps counter. Previously the modal only appeared after the entire flow finished executing, leaving users with no feedback.

#### UX Friction Reduction

- **WhatsApp Instance Creation Mode Selector:** Clicking "+ Create WhatsApp Instance" now opens a selection modal with two options: Guided Setup (8-step wizard, recommended) and Advanced Setup (manual form). Removes the previously hard-to-notice standalone "Setup Wizard" button. Empty state consolidated to a single button that also opens the selector.
- **WhatsApp Wizard Welcome Auto-Fit:** Moved "Let's Get Started" button to a pinned modal footer so it's always visible. Added `autoHeight` prop to Modal component for flexible sizing (`max-h-[calc(100vh-2rem)]`).
- **WhatsApp Setup Wizard (7→8 steps):** Added "About You" step (Step 3) that collects the user's name and phone number, auto-creates a contact with DM Trigger enabled, and links it to the bound agent. Step 2 now includes an optional "Instance Name" field that auto-creates a bot contact. Steps 4-5 (DM/Group settings) have Simple/Advanced mode toggle for progressive disclosure. Step 8 (Confirmation) shows enhanced summary with green/amber indicators for completed/skipped items.
- **Image Analysis skill:** Added a dedicated multimodal image-analysis skill for inbound media. It uses Gemini vision models to describe screenshots/photos, answer captioned image questions, and hand off edit-style captions back to the image editing skill instead of double-handling them.
- **Getting Started Checklist:** New dashboard widget on the Watcher page showing 5 setup milestones (Configure Agent, Connect Channel, Add Contacts, Test in Playground, Create Flow) with progress bar, action links, and dismiss button. Auto-hides when all items are complete.
- **Hub Integration Summary Banner:** Compact status strip above the Hub tab bar showing connection counts for AI Providers, WhatsApp, Telegram, Slack, Discord, and Webhooks with colored dots. Clickable to switch tabs.
- **WhatsApp Instance Display Name:** New `display_name` column on WhatsApp instances. Shown as primary title on Hub cards with phone number as subtitle. Passed via wizard's Instance Name field.
- **Settings Progressive Disclosure:** Settings page now groups cards into "Essential" (Organization, Team Members, System AI, Integrations) always visible, and "Advanced" (8 more) collapsed by default with persistent preference.
- **Agent Creation Smart Defaults:** 4 system prompt template buttons (General Assistant, Customer Support, Sales Outreach, Technical Support) above the textarea. Model provider auto-populates from first configured provider instance. InfoTooltip on model provider field.
- **Playground Default Agent:** Auto-selects the agent marked `is_default` instead of always picking the first in the list.
- **Empty States Standardization:** New `no-contacts` EmptyState variant with address-book SVG. Applied to Agents and Contacts pages, replacing ad-hoc inline empty markup.
- **Backend:** Added `is_default` to PlaygroundAgentInfo API response. Fixed `dm_auto_mode` default from `False` to `True` in MCPInstanceResponse schema.

#### Documentation

- **DOC-001:** Comprehensive documentation overhaul of `DOCUMENTATION.md` — full accuracy audit against codebase
- **DOC-002:** Document 11 missing slash commands: email (6), search, shell, thread (3) — total now 37 commands
- **DOC-003:** Add §26.1 usage examples for all 37 slash commands organized by category
- **DOC-004:** Add channel configuration reference tables — WhatsApp (`group_keywords`, `is_group_handler`, `api_secret`), Slack (`dm_policy`, `allowed_channels`), Discord (`dm_policy`, `allowed_guilds`, `guild_channel_config`)
- **DOC-005:** Add E2E setup guides for all 5 external channels (WhatsApp, Telegram, Slack, Discord, Webhook)
- **DOC-006:** Document per-agent trigger/context override fields (`trigger_dm_enabled`, `trigger_group_filters`, `trigger_number_filters`, `context_message_count`, `context_char_limit`) in §7.3
- **DOC-007:** Expand §9.3 custom skills with subsections for Instruction, Script, and MCP Server variants including creation examples and resource quotas
- **DOC-008:** Expand §9.4 sandboxed tools with full command/parameter tables from all 9 YAML manifests
- **DOC-009:** Formalize FlowRun and FlowNodeRun status lifecycle enums in §13.5
- **DOC-010:** Add OKG merge mode reference table (`replace`, `prepend`, `merge`) in §10.3
- **DOC-011:** Add §16.4 contact usage examples (multi-channel mapping, system user linking, per-contact agent assignment)
- **DOC-012:** Update README.md feature highlights and documentation map to reflect new content
- **DOC-013:** Rename `documentation.md` → `DOCUMENTATION.md` (uppercase convention for all root MD files)
- **DOC-014:** Create `USER_GUIDE.md` — practical user-facing guide covering getting started, channels setup, agents, skills, flows, scheduler, contacts, playground, security, settings, slash commands, API, and audit

### Implementations

#### Added

- **Gate Node Step Type** — New conditional flow control node with two modes:
  - *Programmatic* (zero LLM cost): 15+ operators for numeric, string, regex, existence, and count conditions with AND/OR logic
  - *Agentic* (AI-driven): LLM evaluates pass/fail using natural language criteria
  - Configurable on-fail actions: silent skip or send notification
  - Full UI in flow builder: mode toggle, dynamic condition builder, operator dropdowns
  - Step output variables: `gate_result`, `gate_mode`, `conditions_evaluated`, `reasoning`
- **Zero-Cost Inbox Monitor Template** — Fully programmatic email monitoring (Gmail poll → gate → WhatsApp delivery) with zero AI token cost. "Zero AI Cost" badge in template wizard
- **Smart Email Filter Template** — AI-powered email filtering (Gmail poll → agentic gate → summarization → delivery). Gate criteria configurable (financial, project-specific, etc.)

### Bug fixes

#### Security

- **BUG-SEC-008 (CRITICAL):** Block privilege escalation in `update_client` — non-`api_owner` callers can no longer elevate to `api_owner` role
- **BUG-LOG-020 (CRITICAL):** Sentinel fail-closed on exceptions — security analysis now blocks content when Sentinel crashes instead of silently bypassing
- **BUG-SEC-010:** Revoke existing JWT tokens on API client secret rotation
- **BUG-SEC-016:** Pass `tenant_id` to `check_commands` in shell skill — per-tenant command policies now enforced
- **BUG-SEC-019:** Add magic bytes file type validation for uploads (PDF, DOCX, XLSX, images) — no longer extension-only
- **BUG-278:** Bump Next.js 14.1.0 → 14.2.33 — patches CVE-2025-29927, CVE-2024-34351, CVE-2024-46982, CVE-2024-51479

#### Fixed

- **BUG-299:** Fix agent detail 500 — add missing `parse_enabled_channels` import in `routes_agents.py`
- **BUG-300:** Fix agent list returning null for `enabled_channels` and all integration IDs — add channel/vector-store fields to list endpoint dict builder
- **BUG-301:** Remove duplicate `apply_agent_whatsapp_binding_policy` import in `routes_studio.py`
- **BUG-298:** Pass `tenant_id` to `AgentService` in `AgentRouter.__init__`
- **BUG-293:** Circuit breaker state now persisted to DB on transitions — survives backend restarts
- **BUG-LOG-004:** Tenant-scoped project knowledge chunk queries (defense-in-depth)
- **BUG-LOG-006:** A2A `comm_depth` now injected into skill config — depth limit functional
- **BUG-LOG-007:** Stale flow runs cleaned up on engine startup — no more stuck "running" state
- **BUG-LOG-010:** DB-level unique constraint on `flow_node_run.idempotency_key` (migration 0026)
- **BUG-LOG-011:** `cancel_run` now interrupts in-flight steps via 5s polling loop
- **BUG-LOG-012:** `ContactAgentMapping` now has `tenant_id` column (migration 0025) — prevents cross-tenant agent assignment
- **BUG-LOG-018:** Anonymous contact creation uses SHA-256 instead of Python `hash()` — deterministic IDs across restarts

#### v0.6.0 Comprehensive Audit Remediation (2026-04-06)
99-finding security and quality audit across 11 teams, 51 fixes applied in 41 files.

**Security & Auth (Group A):**
- Add authentication to 3 public Sentinel endpoints (LLM providers, models, detection-types)
- Add RBAC guards to Sentinel exception, prompts, and channel health endpoints
- Seed 6 missing RBAC permissions (channel_health, agent_communication, vector_stores)
- SSRF-validate browser proxy URL and alert webhook URL
- Fix X-Forwarded-For header bypass on webhook IP allowlist
- Validate global admin password minimum length in setup wizard

**Tenant Isolation (Group B):**
- SharedMemoryPool update/delete/share now enforce tenant_id filters
- VectorStoreRegistry cache keyed by (instance_id, tenant_id) — prevents cross-tenant access
- SkillContextService cache keyed by tenant_id:agent_id — prevents cross-tenant pollution
- SentinelEffectiveConfig returns deep copy from cache — prevents exemption bleed

**Sentinel & Detection (Group C):**
- Replace stale hardcoded valid_types with dynamic DETECTION_REGISTRY derivation — restores vector_store_poisoning, agent_escalation, browser_ssrf detection
- Fix BUG-279: cleanup_poisoned_memory now logs error (Memory model has no message_id column)

**Channels & Circuit Breaker (Group D):**
- Circuit breaker: implement half_open_max_failures, extract try_recover() from should_probe()
- Prevent duplicate Slack/Discord workspace registration (HTTP 409)
- SSRF-validate channel alert dispatcher webhook URLs
- Fix Slack adapter deprecated asyncio.get_event_loop() → get_running_loop()
- Bump aiohttp floor to >=3.10.11 (CVE-2024-52304, CVE-2024-23334)
- Fix pinecone-client → pinecone package name

**Memory, OKG & A2A (Group E):**
- Clamp decay_lambda, apply_decay_to_score, and mmr_lambda to valid ranges
- Add user_id check to OKG forget ownership validation
- Fix missing await on A2A vector store search
- Align OKG _compute_decay unknown-timestamp fallback with temporal_decay.py

**Browser Automation (Group F):**
- Per-tenant browser session cap (prevents cross-tenant DoS)
- Thread-safe singleton creation with double-checked locking
- Fix open_tab TOCTOU race and page leak on navigation failure
- extract()/screenshot() return BrowserResult instead of raising exceptions
- go_back()/go_forward() handle None response (no history)
- Cleanup loop releases lock before provider.cleanup()

**Skills, Flows & Build (Group G):**
- Fix critical NameError: router.py tenant_id → self.tenant_id on DM messages
- Scope flow stale cleanup to flow_definition_id (prevents cross-tenant damage)
- Remove nuclei from Dockerfile (BUG-278 — runs in toolbox container)
- Replace hardcoded agent ID 7 with config flag in scheduler_skill
- Fix VectorStoreInstance nullable mismatches vs migration definitions

### Implementations

#### WhatsApp Post-Install Setup Wizard + Inline Helpers (2026-04-05)
Guided 7-step wizard that walks non-technical users through the full WhatsApp onboarding flow end-to-end, replacing the previous "figure it out across 3 pages" experience.

- **Setup Wizard** (`frontend/components/whatsapp-wizard/`): Step 1 Welcome → Step 2 Create instance + inline QR scan with live polling → Step 3 DM Auto Mode + number allowlist → Step 4 Group filters + trigger keywords → Step 5 Contact creation with DM Trigger toggle → Step 6 Agent-to-channel binding → Step 7 Summary with next-steps guidance.
- **Auto-launch**: Fires after the main onboarding tour completes if no WhatsApp instances exist. Uses `tsushin:onboarding-complete` CustomEvent from `OnboardingContext` — no coupling between contexts.
- **Manual triggers**: "Setup Wizard" button in Hub WhatsApp section header (always visible), plus "Guided Setup" / "Manual Setup" split CTA in the empty state.
- **Reusable `InfoTooltip` component** (`frontend/components/ui/InfoTooltip.tsx`): Click-to-toggle popover with title + body text, click-outside/Escape dismiss, dark-mode aware.
- **6 inline helpers placed**: Hub filters modal (Group Filters, Number Filters, Group Keywords, DM Auto Mode), Contacts page (DM Trigger checkbox), Agent Channels (WhatsApp Integration heading).
- **Self-contained state**: `WhatsAppWizardContext` manages wizard lifecycle and accumulated data independently from `OnboardingContext`. Each step calls real APIs immediately — partial setup is usable if the user exits mid-flow.

#### Flow Creation Wizard — Pre-built Hybrid Automations (2026-04-05)
New "From Template" button on `/flows` opens a 3-step wizard (pick → configure → preview) for instantiating common hybrid (programmatic + agentic) flows in one click. Showcases the platform's hybrid value prop: deterministic/cheap programmatic fetch steps gate into agentic summarization steps, avoiding LLM spend when there's no data.

- **5 templates shipped**: Daily Email Digest, Weekly Calendar Summary, Summarize on Demand, Proactive Watcher, New-Contact Welcome.
- **Architecture**: `backend/services/flow_template_seeding.py` defines templates as code (pure `build(params, tenant_id) → FlowCreate` functions); `GET /api/flows/templates` and `POST /api/flows/templates/{id}/instantiate` endpoints in `routes_flows.py`. No new DB primitives — reuses existing FlowDefinition/FlowNode step types and `on_failure="skip"` as the conditional-gate mechanism.
- **Security hardening**: `_validate_template_params` enforces required/options/min/max from each template's declarative schema, with numeric clamping (e.g. `max_emails` clamped to 1–100 server-side regardless of client input). `_validate_tenant_refs` verifies every `agent_id`, `persona_id`, and sandboxed `tool_name` referenced in the generated flow belongs to the caller's tenant — blocks cross-tenant resource leaks at instantiate time (422 response). Option whitelists enforced on select/channel params.
- **Scheduling correctness**: `_first_scheduled_at` uses pytz to compute UTC-naive `scheduled_at` from the user's wall-clock HH:MM in their chosen timezone (verified: 08:00 São Paulo → 11:00 UTC).
- **Frontend**: `CreateFromTemplateModal.tsx` dynamically renders parameter forms from each template's `params_schema`. Matches existing design system (slate-800 shell, teal/cyan accents, rounded-2xl, backdrop-blur).

#### Changed

##### WhatsApp filter typeahead + Studio Contacts UX overhaul (2026-04-05, branch `wpp`)
Replaced free-text entry in Hub > Communications > WhatsApp "Message Filters" (Group Filters + DM Allowlist) with live-autocomplete dropdowns, and streamlined the Studio > Contacts add/edit workflow so users no longer have to manage WhatsApp IDs or click resolve buttons.

**Hub filter typeahead**
- New `TypeaheadChipInput` component (`frontend/components/hub/TypeaheadChipInput.tsx`) with 250 ms debounce, arrow-key nav, free-text fallback, chip × removal.
- New WhatsApp MCP endpoints (`backend/whatsapp-mcp/main.go`): `GET /api/groups` lists joined groups from the local chats store; `GET /api/contacts` merges the whatsmeow address book with DM chats, with `?q=` substring/phone-prefix filter.
- New backend proxy routes (`backend/api/routes_mcp_instances.py`): `GET /api/mcp/instances/{id}/wa/groups` and `…/wa/contacts`, tenant-scoped via `context.can_access_resource`, using `MCPAuthService` Bearer auth.
- Frontend: `api.searchWhatsAppGroups()` / `searchWhatsAppContacts()` and the typeahead wired into both Group Filters and DM Allowlist fields in `hub/page.tsx`.

**Studio > Contacts**
- Removed "Resolve All WhatsApp" header button and per-row "Resolve WA" button — resolution is now silent/automatic.
- Removed manual "WhatsApp ID" text field from the add/edit form (users no longer need to know this value).
- Added "Default Agent" dropdown to the contact add/edit form (only for `role=user`); creates/updates/deletes a `ContactAgentMapping` on save.
- Helper text under Phone Number: *"WhatsApp ID will be auto-detected from the phone number after saving."*
- Contacts page schedules a `loadData()` refresh 2.5 s after create/update to surface server-side resolution without manual reload.

### Bug fixes

#### WhatsApp proactive resolver missing Bearer auth (2026-04-05, branch `wpp`)
`services/whatsapp_proactive_resolver.py` was calling the MCP `/check-numbers` endpoint without an `Authorization` header, causing auto-resolution to fail with **HTTP 401** after Phase Security-1 enabled `MCP_API_SECRET` enforcement. Both single-number and batch resolution paths now pull the instance's `api_secret` via `get_auth_headers()` and include the Bearer token. Verified end-to-end: creating a contact with phone `+5527998701042` auto-populates `whatsapp_id=5527998701042` within ~2 s.

### Implementations

#### Performance
##### Backend image optimization — dependency hygiene + opt-out flags (2026-04-05)
Follow-up to commit `c2402bd` (CPU-only torch). Removed declared-but-unused dependencies, deduped conflicting pytest declarations, split test deps into a dev-only tier, removed system packages that belong in the `toolbox` sandbox container, and added opt-out ARG flags for heavy optional assets. Default image preserves every existing feature; new lean build variant drops ~2.05 GB.

**Dependency removals & reshuffling:**
- **Removed `slack-bolt>=1.20.0`** from `backend/requirements-app.txt` — declared but zero imports. Slack adapter uses `slack-sdk` exclusively (verified in `backend/channels/slack/adapter.py` and `backend/api/routes_slack.py`).
- **Removed duplicate pytest stack** from production tiers: `pytest`, `pytest-asyncio` deleted from `requirements-base.txt`; `pytest`, `pytest-asyncio`, `pytest-cov` deleted from `requirements-phase4.txt`. Conflicting version floors (`>=7.4.4` vs `>=7.4.0`) resolved.
- **New `backend/requirements-dev.txt`** — unified dev/CI testing deps (pytest, pytest-asyncio, pytest-cov), NOT installed in the production Docker image. Run locally: `pip install -r backend/requirements-dev.txt`.
- **Moved `docker>=7.0.0`** from `requirements-base.txt` → `requirements-app.txt` with accurate usage comment (Phase 8 MCP container lifecycle via `services/container_runtime.py`).
- **Bumped `google-generativeai>=0.4.0` → `>=0.8.0`** — ancient floor (Jan 2024) replaced with current floor.

**System packages:**
- **Removed `nmap` and `whois`** from `backend/Dockerfile` apt install — sandboxed tools run in the per-tenant `toolbox` container (`backend/containers/Dockerfile.toolbox`), not in the backend image. Backend Python code references them only as string tokens for routing.

**New Docker build flags (both default=true, zero behavior change by default):**
- **`INSTALL_PLAYWRIGHT=true`** — gates `playwright install chromium` (~1.1 GB Chromium binary) and Chromium system libs (libnss3, libatk, libcups2, etc.). Set `false` if the deployment does not use browser automation skills.
- **`INSTALL_FFMPEG=true`** — gates ffmpeg (~250 MB). Required by Kokoro TTS for WAV→Opus conversion (`backend/hub/providers/kokoro_tts_provider.py:457`). Set `false` if TTS is not used.

**Example lean build:**
```bash
docker build --build-arg INSTALL_PLAYWRIGHT=false --build-arg INSTALL_FFMPEG=false \
  -t tsushin-backend:lean backend/
```

**Measured results (multi-arch arm64 image):**

| Variant | Image Size | vs Baseline | Notes |
|---------|-----------|-------------|-------|
| Baseline (pre-c2402bd) | 4.89 GB | — | Before CPU-only torch fix landed |
| Default (after this change) | 4.84 GB | −50 MB | Playwright + ffmpeg still installed |
| Lean (both flags false) | 2.79 GB | **−2.10 GB (−43%)** | No Chromium, no ffmpeg |

Build time (no-cache, BuildKit pip mounts intact): ~3m 23s for default rebuild.

**Verified end-to-end:** backend health + readiness endpoints return 200; API v1 `/agents` sweep returns 200; `slack_sdk`/`docker`/`google.generativeai`/`playwright`/`ffmpeg`/`sentence-transformers` all importable; `import pytest` + `import slack_bolt` correctly raise `ModuleNotFoundError` in production image; torch remains `2.11.0+cpu` (no CUDA regression); Kokoro TTS provider imports; Slack adapter imports; per-tenant toolbox container still reachable with nmap + dig available.

### Bug fixes
#### BUG-275 — Global refresh button did not reliably update lists across pages (2026-04-05)
The header global refresh button dispatches a `tsushin:refresh` CustomEvent that pages subscribe to in `useEffect`. Audit found 9 pages registered the listener with empty deps `[]`, capturing the FIRST render's `loadData` closure — the listener kept calling that stale closure forever, so loaders executed with initial state values instead of current state.

- **New hook** `frontend/hooks/useGlobalRefresh.ts` uses a ref-of-callback pattern so the listener ALWAYS invokes the latest callback. Eliminates stale-closure bugs once and for all.
- **Migrated 9 pages/components**: `flows`, `hub`, `agents`, `agents/contacts`, `agents/personas`, `hub/sandboxed-tools`, `settings/organization`, `watcher/ConversationsTab`, `watcher/DashboardTab`, `watcher/FlowsTab`.
- **Pagination snapback** on Flows: when a delete drops the total below the current page's offset, the page auto-corrects to the last non-empty page without clobbering the list in between.
- **Validated** via Playwright: clicking refresh on flows/agents/contacts/settings/hub fires a fresh `GET` on every click, zero stale data.

#### BUG-LOG-015 — Memory table now has tenant_id for DB-level isolation (2026-04-05)
Previously the `Memory` table enforced tenant isolation only via `agent_id` — every query site had to remember to scope by `agent_ids ∈ tenant's agents`. A missed site would be a cross-tenant leak. This change enforces isolation at the row level.

- **Alembic migration 0024** adds `tenant_id VARCHAR(50) NOT NULL` with backfill from `Agent.tenant_id`, deletes orphan rows (28 in dev DB), and adds composite index `(tenant_id, agent_id, sender_key)`.
- **Write paths** populate tenant_id on every INSERT: `agent_memory_system.save_to_db` (via lazy-caching `_get_tenant_id` helper — deduplicated with the pre-existing MemGuard helper), `playground_message_service.branch_conversation`.
- **Read paths simplified**: `conversation_knowledge_service._get_thread_messages`, `conversation_search_service._search_like`, and `routes.py` stats now filter Memory directly on `tenant_id`, replacing the Agent-JOIN and tenant-agent-id-IN-list patterns.
- **Validated**: 422 rows backfilled with correct tenant_id, 0 NULLs; live chat test creates Memory rows with tenant_id populated; backend starts clean with `alembic upgrade head 0023 → 0024`.

#### /flows double-fire on global refresh (BUG-275 follow-up, 2026-04-05)
Perfection QA caught that `frontend/app/flows/page.tsx` still used the raw `addEventListener('tsushin:refresh')` pattern INSIDE the `useEffect([currentPage, pageSize])` that loaded data. Every pagination change re-attached the listener, and on refresh click the page's three loader GETs (`flows/`, `flows/runs`, `conversations/active`) fired twice. Migrated flows/page.tsx to the `useGlobalRefresh` hook with an empty-deps mount registration — single subscription per mount.

#### BUG-276 — Force-delete of flows with completed runs blocked by conversation_thread FK (2026-04-05)
Three stress-test flows (IDs 140/139/123) could not be force-deleted. Root cause: conversation_thread rows 596/597/598 had `status='timeout'` referencing FlowNodeRun IDs — the force-delete path only nullified `flow_step_run_id` for threads with `status='active'`, so non-active threads kept the FK reference and blocked the FlowNodeRun cascade, rolling the transaction back under a generic 500.

- **Fix** in `backend/api/routes_flows.py` delete_flow: after the state transition on `status='active'` threads, widen the nullification to `flow_step_run_id = NULL` for ALL statuses referencing the flow's step runs. History preserved on threads, FK cleared, cascade proceeds.
- **Observability**: included `{e}` in the `logger.exception` format string so future delete failures surface the DB constraint name.
- **Validated**: all three stuck flows deleted successfully (HTTP 204); threads retained `status='timeout'` with `flow_step_run_id=NULL`; zero dangling FKs. UI round-trip confirmed.

#### BUG-277 — WhatsApp agent silent-drop regression (2026-04-05)
Two compounding regressions silently broke the WhatsApp agent: the bot would receive DMs into its MCP container but never route them through the agent or respond. Watcher logs showed neither `Found N new messages` nor any Gemini call, leaving the user to believe the bot had hung.

- **`backend/app.py` — `CachedContactService` missing `tenant_id`**: after V060-CHN-006 made the service fail-closed when `tenant_id` is unset, every `identify_sender()` lookup returned `None`. The MessageFilter relies on `contact.is_dm_trigger` to decide whether to wake the agent on DMs; with every contact lookup returning `None`, DMs fell through to `dm_auto_mode` (`False`) and the watcher silently advanced `last_timestamp` without routing. Fixed by creating a per-tenant `CachedContactService` scoped to `instance.tenant_id`, cached in `app.state.contact_services` (dict keyed by tenant). Same fix applied to the Telegram callback path, which now passes `bot_instance.tenant_id`.
- **`backend/agent/router.py` — `UnboundLocalError: cannot access local variable 'os'`**: two redundant `import os` statements inside `route_message()` made `os` a function-local name across the entire 1200-line function, shadowing the module-level import. The CB-queue check at line 1297 (`elif os.getenv("TSN_CB_QUEUE_ENABLED", ...)`) runs before those inner imports and crashed with `UnboundLocalError` on every message. Fixed by deleting the two redundant inner imports; the module-level `import os` at the top of `router.py` is used everywhere.

Validated with a tester → bot → Gemini → tester WhatsApp round-trip: bot responded with `"Olá, Vini! Tudo bem por aqui também. CUSTOM_SKILL_ACTIVE. Como posso te ajudar com este teste pós correção?"` and the tester instance received the response.

#### v0.6.0 Critical Remediation — 11 Audit Findings (2026-04-05)
Coordinated fix sweep for 11 CRITICAL/HIGH findings from the v0.6.0 audit, grouped into 5 remediation domains. Each fix programmatically verified; full regression (infrastructure + auth + API v1 sweep + tenant endpoint sweep + agent chat + 6-screen browser QA) passed zero new errors.

**Group A — Auth & Security Hardening** (commits 2327bb6 + 829877b)
- `V060-API-004`: `/api/v1/*` UI-JWT path now enforces password-reset invalidation (`password_changed_at` vs `token.iat`), parity with SEC-001/BUG-134 UI path. Missing `iat` claim rejected with 401, closing a JWT-stripping bypass. Same hardening backported to `auth_dependencies.py`.
- `V060-HLT-005`: `PUT /api/channel-health/alerts/config` now SSRF-validates the webhook URL via `utils.ssrf_validator.validate_url()`. Blocks `file://`, cloud metadata IPs (`169.254.169.254`, etc.), localhost, private ranges, and non-http(s) schemes. `HTTPException` re-raise prevents 400→500 downgrade.
- `V060-SKL-002`: MCP server create/update now require HTTPS whenever `auth_type != 'none'` (bearer/header/api_key). Prevents plaintext transmission of credentials over HTTP; rejects downgrade attempts on existing HTTPS+auth configs.

**Group B — Tenant Isolation + Queue Safety** (commits 7971b4e + 1e5e241)
- `V060-CHN-006`: `CachedContactService` and base `ContactService` now accept `tenant_id` and filter `Contact`/`ContactChannelMapping` queries by tenant. Cache keys prefixed per tenant. Fail-closed on missing tenant_id. `AgentRouter` threads tenant_id to CachedContactService from all 6 call sites (queue_worker, watcher_manager, routes.py, app.py). Follow-up extends to `SchedulerService` (12 sites) and `FlowEngine._resolve_contact_to_phone` — closes cross-tenant leaks in scheduled messages and flow recipient resolution.
- `V060-HLT-003`: `QueueWorker._poll_and_dispatch` now consults `ChannelHealthService.is_circuit_open()` for whatsapp/telegram channels before dispatching. When CB is OPEN, dispatch is deferred (item remains pending, no retry burn, no 500ms re-enqueue spiral). Router's CB-enqueue guard skipped when `trigger_type=='queue'`. Instance-id resolution now uses agent's explicit `whatsapp_integration_id`/`telegram_integration_id` FK instead of tenant-wide `.first()`.

**Group C — Slack/Discord Channel Integration** (commit e1c1949)
- `V060-CHN-001`: `AgentRouter` now registers `SlackChannelAdapter` and `DiscordChannelAdapter` with the channel registry when a tenant has exactly one active integration (or when explicit integration_id is passed). Bot tokens decrypted via `TokenEncryption` + per-channel encryption key, matching existing routes_slack/routes_discord patterns.
- `V060-CHN-002`: New public router `backend/api/routes_channel_webhooks.py` exposes two unauthenticated endpoints gated by cryptographic signature verification:
  - `POST /api/slack/events` — HMAC-SHA256 verification against `signing_secret_encrypted`, 5-minute timestamp skew for replay protection, `url_verification` challenge handled.
  - `POST /api/discord/interactions` — Ed25519 verification via PyNaCl, type-1 PING handshake, type-5 deferred response.
  - Verified events enqueue to `message_queue` with channel='slack'/'discord'; QueueWorker's new `_process_slack_message`/`_process_discord_message` handlers instantiate AgentRouter with tenant_id + integration_id threaded through.
- **Dep added:** `PyNaCl>=1.5.0` for Ed25519 signature verification.

**Group D — Memory (OKG) + Provider Wiring** (commit 36d694c)
- `V060-MEM-001`: `ProviderBridgeStore._records_to_dicts` now preserves the full metadata dict under a nested `'metadata'` key. OKG recall post-filter reads `record.get('metadata',{}).get('is_okg')` and was seeing `{}` for every record — so every OKG record was skipped, making OKG recall return zero results with any external vector store. Flat spread retained for backwards compat.
- `V060-PRV-001`: `AIClient.__init__` now accepts an optional `api_key` kwarg that bypasses DB/env lookup. Raw test-connection in first-time-setup wizard (tenant with no provider key) previously failed at AIClient construction with "No API key found" before the route handler could apply the user's credential. Now the raw key is passed directly.
- `V060-PRV-002`: Saved-instance test-connection now passes the instance's own decrypted api_key to AIClient (falling back to tenant key only when instance has none). Previously the resolved api_key was never applied, so a valid tenant key masked a broken instance key and produced a false success.

**Group E — Custom Skill Security** (commit cc0de12)
- `V060-SKL-001`: New `_scan_skill_content()` helper concatenates `instructions_md` + `script_content` into a single analyzable blob and submits to `SentinelService.analyze_skill_instructions`. Both `create_custom_skill` and `update_custom_skill` now invoke this helper whenever either field is present/changed. Previously script-type skills with empty instructions landed as `scan_status='clean'` without Sentinel ever seeing the code — an attacker could upload a script that reads `OPENAI_API_KEY` + `/etc/passwd` and exfiltrates via HTTP and it would auto-enable in the agent sandbox. The network-import advisory is retained as an augmenting signal, no longer the primary defense.

### Implementations

#### Added

#### Webhook-as-a-Channel (v0.6.0)
- **New first-class channel type** alongside WhatsApp/Telegram/Slack/Discord/Playground. Bidirectional HTTP integration for CRMs, Zapier, custom apps, ticketing systems.
- **Inbound endpoint**: `POST /api/webhooks/{id}/inbound` (public, HMAC-gated). Accepts `X-Tsushin-Signature: sha256=<hex>` (HMAC-SHA256 over `timestamp + "." + body`) and `X-Tsushin-Timestamp` (±5 min replay window). Cryptographically authenticated, no bearer token.
- **Outbound callbacks**: agent replies POSTed back to customer-provided callback URL (optional, enabled per integration). SSRF-validated on create via existing `utils.ssrf_validator`. HMAC-signed. 10s timeout, no redirects, 64 KB response cap.
- **Defense-in-depth**: per-webhook rate limit (default 30 rpm), optional CIDR IP allowlist, configurable payload size cap (default 1 MB), generic 403 on auth failures (no detail leak).
- **Management API** (`/api/webhook-integrations`, tenant-scoped via `filter_by_tenant`): POST create (returns plaintext secret ONCE), GET list/detail (masked `whsec_XXXX…` preview only), PATCH update, POST rotate-secret (returns new plaintext once, invalidates old), DELETE.
- **Encryption at rest**: `webhook_encryption_key` in Config + Fernet per-tenant workspace key derivation via `TokenEncryption`. New `get_webhook_encryption_key()` helper in `encryption_key_service`.
- **Agent binding**: `Agent.webhook_integration_id` FK (one webhook → one agent). `enabled_channels` accepts `"webhook"`. `AgentRouter` registers `WebhookChannelAdapter` per instance; `_is_agent_valid_for_channel` enforces binding.
- **Queue dispatch**: `QueueWorker._process_webhook_message` normalizes payload into channel-agnostic message dict, routes through AgentRouter with `webhook_instance_id`, persists LLM result for `GET /api/v1/queue/{id}` polling.
- **Security tested**: 13-point adversarial suite verifies HMAC verify, missing/wrong signature, replay, nonexistent webhook, oversized payload, rate limit, SSRF, unauthenticated access, secret rotation. All passing.
- **UI integration**: Hub → Communication section ("Webhook Integrations" cards with Rotate Secret + Delete), `WebhookSetupModal` two-phase flow (form → secret reveal with copy-to-clipboard + signing instructions), Agent Channels tab toggle + radio selector, Studio/Graph channel nodes (cyan palette, reuses existing `isGlowing`/`isFading` animations identical to WhatsApp/Telegram), Flows step targeting, ChannelHealthTab, dashboard distribution chart color.
- **Alembic 0023**: `webhook_integration` table + `agent.webhook_integration_id` FK + `config.webhook_encryption_key`.
- **Graph View integration**: webhook channels now render as first-class nodes alongside WhatsApp/Telegram/Playground (cyan palette, integration name as subtitle). `/api/v2/agents/graph-preview` exposes `channels.webhook[]` with `WebhookChannelInfo` schema + `agent.webhook_integration_id`; `useGraphData.ts` creates webhook→agent edges; `GraphCanvas.getChannelType()` recognizes `channel-webhook-*` so the existing edge-glow/fade activity pipeline fires identically to other channels on inbound message activity.
- **RBAC**: `integrations.webhook.{read,write}` permission scopes (owner/admin/member get write, readonly gets read). All 6 webhook CRUD routes gated by `require_permission()` matching the Slack/Discord pattern.
- **Tenant binding validation**: `routes_agents.py` create/update handlers validate that the supplied `webhook_integration_id` resolves to a WebhookIntegration in the caller's tenant before persisting the FK, closing a cross-tenant binding gap.
- **Emergency stop integration**: webhook inbound endpoint honors `Config.emergency_stop` and returns 503 at ingress (before enqueueing) when the global stop is active. Circuit breaker queuing in `AgentRouter` also maps `webhook_instance_id` for deferred-message tenant/agent resolution.

#### Live Provider Model Discovery
- **Self-updating model dropdowns**: `/setup` and the provider-instance modal now auto-refresh their model lists against the provider's real `/models` endpoint whenever a user pastes an API key — no more hand-maintained Gemini/OpenAI/etc. lists going stale when Google or OpenAI ship new models.
- **New endpoint** `POST /api/provider-instances/discover-models-raw`: accepts `{vendor, api_key, base_url?}`, performs a single outbound request to the provider, returns the live model list. API key is used once and never stored.
- **Gemini live discovery**: backend calls Google's `/v1beta/models` with pagination, filters to `generateContent`-capable models, strips the `models/` prefix. Works on both saved instances (Auto-detect button) and pre-save (as the user types their key).
- **Unified static fallback**: the previously-inlined `KNOWN_MODELS` dict in `discover_models` was replaced by a module-level `PREDEFINED_MODELS` registry consumed by the new public `GET /api/provider-instances/predefined-models` endpoint — used as a suggestion fallback when no API key is available yet.
- **Supported vendors for live pre-save discovery**: gemini, openai, groq, grok, deepseek, openrouter. Anthropic keeps the static list (no public `/models` endpoint).
- **Refreshed Gemini static fallback**: added Gemini 3.x preview IDs (`gemini-3.1-pro-preview`, `gemini-3-flash-preview`, `gemini-3.1-flash-lite-preview`) and 2.5 stable (`gemini-2.5-flash-lite`) for the "no key entered yet" case.
- **Datalist UX**: instance-modal model input now uses a `<datalist>` bound to the current vendor, so users get vendor-specific autocomplete while retaining free-text entry for custom IDs.

#### Flows Bulk Actions & Page Size Selector
- **Bulk actions bar**: Multi-select flows to Enable, Disable, or Delete them in bulk. Bar appears above the table when rows are selected with selection count and Clear selection link.
- **Page size selector**: Per-page dropdown (10/25/50/100) added to the pagination footer, replacing the hardcoded 25-per-page limit. Changing page size resets to page 1 and clears any selection.
- **Force-delete fallback**: Bulk delete detects flows with existing runs and prompts once to force-delete the affected set.

#### OKG Term Memory Skill (v0.6.0)
- **Ontological Knowledge Graph skill**: New `okg_term_memory` skill providing structured long-term memory with typed metadata (subject/relation/type/confidence). First multi-tool skill in Tsushin.
- **Three LLM-callable tools**: `okg_store` (store memory with ontological metadata), `okg_recall` (search by query + metadata filters with temporal decay), `okg_forget` (delete by doc_id).
- **Auto-capture hook**: Post-response FactExtractor integration auto-stores durable facts from conversations with `source=auto_capture`.
- **Auto-recall (Layer 5)**: `OKGContextInjector` hooks into `AgentMemorySystem.get_context()` to inject relevant OKG memories as XML-tagged `<long_term_memory>` blocks. HTML-escaped content prevents prompt injection.
- **SkillManager multi-tool support**: `get_all_mcp_tool_definitions()`, `_current_tool_name` dispatch, multi-tool schema validation. All existing single-tool skills unaffected.
- **OKGMemoryAuditLog table**: Full audit trail of store/recall/forget/auto_capture operations with MemGuard block tracking.

#### MemGuard Vector Store Defense (v0.6.0)
- **New pattern categories**: `embedding_manipulation` (weight 0.80) detects raw float arrays, metadata overrides, distance manipulation. `cross_tenant_leak` (weight 0.75) detects tenant metadata smuggling and namespace confusion.
- **Batch poisoning detection**: `detect_batch_poisoning()` with configurable thresholds (max 50 docs / 60s window / 0.95 similarity). Immediate block for batches exceeding max_batch_write_size.
- **Post-retrieval scanning (Layer C)**: `validate_retrieved_content()` scans retrieved vector store results at lower threshold (0.5 vs 0.7) and verifies tenant_id metadata isolation.
- **Per-store security config**: `VectorStoreInstance.security_config` JSON column with configurable thresholds, rate limits, and cross-tenant check toggle.
- **Rate limiter**: `VectorStoreRateLimiter` singleton with sliding-window enforcement for reads (per agent) and writes (per tenant).
- **Bridge security hooks**: `ProviderBridgeStore` accepts optional `security_context` for automatic post-retrieval MemGuard validation.

#### Sentinel Vector Store Detection (v0.6.0)
- **New detection type**: `vector_store_poisoning` in DETECTION_REGISTRY with `applies_to: ["vector_store"]`, severity "high", default enabled.
- **LLM prompts**: 3 aggressiveness levels for vector store content analysis (instruction-bearing docs, embedding manipulation, batch saturation, cross-tenant leakage).
- **Unified classification update**: `vector_store_poisoning` added to all 3 UNIFIED_CLASSIFICATION_PROMPT levels with proper priority ordering.
- **Schema**: `detect_vector_store_poisoning` toggle on SentinelConfig, `vector_store_poisoning_prompt` custom prompt, `vector_store_access_enabled` + `vector_store_allowed_configs` on SentinelAgentConfig.
- **Frontend**: Toggle in Sentinel Settings General tab, Layer C card in MemGuard tab, prompt editor in Prompts tab.
- **Seed defaults**: System config seeds with `detect_vector_store_poisoning=True`.


#### Vector Store Auto-Provisioning
- **One-click container deployment**: Auto-provision Docker containers for Qdrant and MongoDB directly from the Hub UI. Toggle "Auto-Provision" during creation to have Tsushin spawn, configure, and health-check a container automatically.
- **Container lifecycle management**: Start, stop, restart auto-provisioned containers from the Vector Store card. Container status (running/stopped/error) displayed with real-time indicators.
- **Port allocation**: Dedicated port range 6300-6399 for vector store containers (separate from MCP 8080-8180).
- **Named volumes**: Data persists across container restarts via Docker named volumes (`tsushin-vs-{vendor}-{tenant}-{id}`).
- **Resource limits**: Configurable memory limits (512MB/1GB/2GB/4GB) per container.

#### Default Vector Store Settings Page
- **Global tenant default**: New Settings > Vector Stores page with dropdown selector to choose the tenant-wide default vector store. Replaces the confusing per-instance `is_default` toggle.
- **Three-tier resolution**: Agent override > Tenant default (Settings) > ChromaDB (built-in). Agents without an explicit vector store assignment now use the tenant default.
- **Settings API**: `GET/PUT /api/settings/vector-stores/default` for managing the default selection.

#### MongoDB Local Mode for Vector Stores
- **Local cosine similarity fallback**: MongoDB adapter now supports self-hosted MongoDB 7.0+ without Atlas Vector Search. Toggle "Local Mode" in the UI to use Python-side cosine similarity instead of Atlas `$vectorSearch` aggregation.
- **Registry integration**: `use_native_search` config option passed from `extra_config` through the provider registry.
- **UI toggle**: MongoAtlasConfigForm has a "Local Mode" toggle that sets `use_native_search: false`.

#### A2A Communication Memory Enrichment
- **Cross-agent memory retrieval**: When Agent A asks Agent B via A2A communication, Agent B's vector store is now searched for relevant memories and injected into the A2A prompt context. This enables agents to recall facts from their external vector stores (Qdrant, MongoDB) during inter-agent conversations.
- **disable_skills flag**: Target agents in A2A calls no longer have access to skills/tools, preventing recursive tool invocations. Pure LLM-only responses using memory context.

#### Dynamic Vector Store Vendor Labels
- **MongoDB vs Atlas badges**: Vector Store cards in the Hub UI now show "MongoDB" badge for local mode instances and "Atlas" for native Atlas Vector Search instances.
- **Vendor dropdown**: Changed from "MongoDB Atlas" to "MongoDB" in the vendor selector.

### Fixed
- **Agent API response**: `vector_store_instance_id` and `vector_store_mode` fields were missing from the `GET /api/agents/{id}` response.
- **A2A memory search**: Use `get_shared_embedding_service()` singleton instead of creating a new `EmbeddingService()` per call (prevents model reload).
- **MongoDB adapter async safety**: Local cosine search methods now run in `asyncio.to_thread()` to prevent blocking the event loop.
- **MongoDB adapter memory**: Added projection to `_local_cosine_search_with_embeddings` to prevent loading entire documents into memory.
- **Frontend toggle**: Fixed Local Mode toggle treating `undefined` as local mode on first click.

---

## [0.6.0] - 2026-04-01

### Implementations

#### Temporal Memory Decay Frontend (Item 37)

- **Agent Studio decay configuration**: New "Temporal Decay" section in Agent Builder Memory Config with enable toggle, decay rate slider (0.001-1.0), archive threshold slider (0-1.0), and MMR diversity slider (0-1.0). Decay fields persisted via builder save endpoint with float validation and rounding.
- **Memory Inspector freshness badges**: Per-fact colored dots (green=fresh, yellow=fading, orange=stale, gray=archived) with decay factor percentage. Freshness distribution summary bar when decay is enabled.
- **Archive decayed facts**: Dry-run preview with fact count, then confirm to archive. Clears on agent/thread switch to prevent wrong-context operations.

#### Channel Health Tab in Watcher (Item 38)

- **New Watcher tab**: "Channel Health" tab with summary bar (total, healthy, unhealthy, open circuits), instance cards grid with circuit breaker state visualization, and per-instance Probe/Reset actions.
- **Event history**: Expandable per-instance event timeline showing circuit breaker state transitions with timestamps and reasons.
- **Alert configuration**: Collapsible panel with webhook URL, email recipients, cooldown settings, and enable/disable toggle.
- **8 API client methods**: Full frontend integration with all channel health backend endpoints.

#### Test Connection on Provider Instance Create (Item 27b)

- **New backend endpoint**: `POST /api/provider-instances/test-connection` accepts raw credentials (vendor, base_url, api_key) without requiring a saved instance. SSRF validation on base_url, falls back to tenant-level API key.
- **Create mode button**: Test Connection button now visible during instance creation (previously edit-only). Disabled when no API key entered (except Ollama).

#### Inline Screenshots in Playground (Item 35)

- **Multi-image support**: Backend now returns all `media_paths` images (previously only first). New `image_urls` array in response alongside backward-compatible `image_url`.
- **Image grid + lightbox**: Multiple images render in a 2-column grid. Click any image to open full-screen lightbox overlay with close on backdrop click or Escape key.

#### Message Queuing on Circuit Breaker OPEN (Item 38)

- **Router circuit breaker check**: `route_message()` now checks channel circuit breaker state before processing. If the channel's circuit breaker is OPEN, messages are enqueued via `MessageQueueService` instead of being processed immediately. Guarded by `TSN_CB_QUEUE_ENABLED` env var (default: true). Fail-safe: if enqueue fails, falls through to normal processing.

#### Changed

- **Docker env passthrough**: Added `GROQ_API_KEY`, `GROK_API_KEY`, `ELEVENLABS_API_KEY` to docker-compose.yml backend environment.
- **Docker Compose v2 required**: Installer no longer supports `docker-compose` v1. Reverts the BUG-271 `DOCKER_BUILDKIT=0` workaround (installer would force-disable BuildKit for v1 compatibility). The backend Dockerfile now requires BuildKit for pip/nuclei cache mounts. Docker Compose v2 (`docker compose`) is bundled with Docker Desktop ≥20.10 and is the CLAUDE.md convention. Installer errors out with a clear upgrade message if only v1 is detected.

#### Backend Container Build Optimization (2026-04-04)

- **Backend image size: 11.5 GB → 4.89 GB (-58%)**. Full `--no-cache` build time: 14m22s → 3m59s (-72%). Layer export: 93s → 32s (-66%).
- **Root cause**: `sentence-transformers` → default `torch` wheel was pulling ~4.3 GB of NVIDIA/CUDA/triton binaries (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`, `triton`, etc.) that never execute — embeddings run on CPU via `asyncio.to_thread()`.
- **Fix**: Install torch from the CPU-only index (`https://download.pytorch.org/whl/cpu`) as a dedicated step before `requirements-phase4.txt`. Saves 4.3 GB of unused CUDA runtime per image.
- **BuildKit cache mounts**: Added `# syntax=docker/dockerfile:1.4` + `--mount=type=cache,target=/root/.cache/pip` to all pip install steps and the nuclei download. Wheels persist across `--no-cache` rebuilds.
- **Tiered requirements**: Split `requirements.txt` into `requirements-base.txt` (stable core: fastapi, sqlalchemy, pydantic, security deps), `requirements-app.txt` (volatile integrations: anthropic, openai, google-*, slack, discord, telegram), and `requirements-optional.txt` (kubernetes, gcp-secret-manager, qdrant, pinecone, pymongo). Iterative rebuilds only invalidate the changed tier + below.
- **Optional deps build arg**: New `INSTALL_OPTIONAL_DEPS` ARG (default: `true`). Local dev can build with `--build-arg INSTALL_OPTIONAL_DEPS=false` to skip K8s/GCP/vector clients (~50 MB saved). All five optional deps are lazy-imported at runtime, so disabling is safe as long as the corresponding feature isn't activated.
- **Nuclei download cache**: Cached across builds, saving ~5-10s per full rebuild.
- **Updated references**: `.github/workflows/gke-deploy.yml` and `ops/manage_servers.py` now reference the tiered requirements files.

### Bug fixes

#### Pre-Release Security Audit (2026-04-03)

- **Error detail leaking**: Sanitized 40 `HTTPException(500, detail=str(e))` calls across 10 API route files (`routes_scheduler`, `routes_skills`, `routes_memory`, `routes_custom_skills`, `routes_hub`, `routes_skill_integrations`, `routes_google`, `routes_telegram_instances`, `routes_provider_instances`, `routes_knowledge_base`). All now return generic context-appropriate messages instead of raw Python exception strings. Added missing `logger.error()` calls for 3 Telegram instance routes.
- **Dev/debug scripts in git**: Removed 13 internal development scripts from git tracking (`check_*.py`, `debug_*.py`, `fix_shell_wait.py`, `e2e_test_results.txt`). Added gitignore patterns to prevent re-tracking.
- **Inconsistent tenant isolation**: Standardized `list_runs` endpoint in `routes_flows.py` to use `filter_by_tenant()` instead of manual `tenant_id` check, matching all other flow endpoints.

#### Installer Refactor & Security Hardening (2026-04-03)

- **(BUG-269) XSS token theft via localStorage**: SEC-005 Phase 3 — removed all `localStorage` JWT token storage from the frontend. Auth now relies entirely on the httpOnly `tsushin_session` cookie. Backend WebSocket handlers (playground + watcher) updated to authenticate from cookie without requiring first-message token. Setup wizard and SSO exchange endpoints now set the httpOnly cookie. All auth fetch calls include `credentials: 'include'`.
- **(BUG-270) CORS origin wrong for remote HTTP installs**: Installer set `TSN_CORS_ORIGINS` to `http://localhost:3030` for remote installs, blocking all API calls from the actual IP. Fixed by using the public host for `frontend_url` and CORS origins.
- **(BUG-271) docker-compose v1 ContainerConfig error**: BuildKit images lack the `ContainerConfig` key that docker-compose v1 expects on container recreate. Installer now sets `DOCKER_BUILDKIT=0` for both `run_docker_compose()` and `build_additional_images()` when using docker-compose v1.
- **(BUG-272) Setup wizard loses API key if "Add" not clicked**: Users who typed an API key but clicked "Complete Setup" without clicking "Add" lost the key. `handleSubmit` now auto-includes any uncommitted key from the text field.

#### Installer Redesign (2026-04-03)

- **Infrastructure-only installer**: Removed all 7 API key prompts and 8 tenant/admin credential prompts from the installer. User/org creation and AI provider configuration are now handled exclusively by the `/setup` UI wizard after install.
- **`--defaults` mode simplified**: No longer generates random passwords or bootstraps users. Just sets up `.env`, Docker containers, and SSL — then directs user to `/setup`.
- **argparse with `--help`**: Added proper CLI flags: `--defaults`, `--http`, `--domain`, `--email`, `--port`, `--frontend-port` with validation and usage examples.
- **Let's Encrypt via Caddy**: SSL is handled by Caddy with built-in ACME support (no certbot needed). `--domain` flag requires `--email` for Let's Encrypt notifications.

#### Async Embeddings Migration (2026-04-02)

- **Event loop blocking**: Migrated all 12 sync `embed_text()` / `embed_batch_chunked()` call sites to async variants (`embed_text_async()`, `embed_batch_chunked_async()`) using `asyncio.to_thread()`. Health checks and WebSocket connections no longer stall during embedding-heavy agent processing.
- **SentenceTransformer singleton consolidation**: Removed 4 services that bypassed the shared `EmbeddingService` singleton and instantiated their own `SentenceTransformer` model (combined_knowledge_service, project_memory_service, playground_document_service, project_service). All embedding calls now route through `get_shared_embedding_service()`.
- **Thread-safe singleton**: Added double-checked locking with `threading.Lock` to `get_shared_embedding_service()` to prevent race conditions from concurrent `asyncio.to_thread()` calls.
- **Dockerfile workers**: Reverted `--workers 2` to `--workers 1` — async embeddings eliminate the need for a second worker, halving model memory usage.

#### Fresh Install QA (2026-04-02)

**Install Flow (3 fixes):**
- **(BUG-248) /setup page**: Created frontend setup wizard at `/setup` for first-run account creation. Login page auto-redirects to `/setup` when database is empty. Added `GET /api/auth/setup-status` endpoint.
- **(BUG-249) --defaults auto-bootstrap**: `python3 install.py --defaults` now creates tenant + admin with random credentials and displays them post-install.
- **(BUG-250) .local email validation**: Patched `email-validator` to allow `.local` TLD for dev environments.

**Installer Security (1 fix):**
- **(BUG-256) HTTPS default**: Self-signed HTTPS is now the default for localhost installs, Let's Encrypt for remote. HTTP requires explicit opt-in with plaintext credential warning. `TSN_CORS_ORIGINS` and `TSN_SSL_MODE` auto-configured in `.env`.

**UI/UX (6 fixes):**
- **(BUG-251) Tenant display name**: Header shows tenant name instead of raw ID slug (`tenant_2026...`).
- **(BUG-252) Markdown rendering**: Playground renders markdown in agent responses (bold, bullets, code blocks) via ReactMarkdown.
- **(BUG-253) Thread titles**: Smarter auto-naming strips greetings and extracts topic instead of truncating first 50 chars.
- **(BUG-254) Console noise**: Expected 401 errors downgraded to `console.debug`, verbose playground logs gated behind `NODE_ENV`.
- **(BUG-255) Tour highlighting**: Onboarding tour now highlights target UI elements with pulsing teal outline.
- **(BUG-257) Tour content**: Updated with current AI providers, channel setup guidance, Sentinel security, and API v1 access.

#### Google SSO Enrollment Fixes (2026-04-01)

- **(BUG-246) Soft delete locks SSO re-enrollment**: Team member removal now uses hard delete instead of soft delete. Soft delete left `google_id` linked to a deactivated record, permanently blocking re-enrollment. SSO lookups now also filter `deleted_at` as defense-in-depth. Comprehensive FK cleanup across 12+ tables on user removal.
- **(BUG-247) Avatar URL exceeds column length**: Google profile avatar URLs can exceed 800 characters. `avatar_url` column changed from `VARCHAR(500)` to `TEXT`. Generic SSO error handler now surfaces actual error detail instead of opaque "Authentication failed".

### Changed

#### Google SSO Auto-Provisioning UI (2026-04-01)

- Auto-provision defaults to **off** (pre-registration required). Users must be added via Team > Invite before signing in with Google SSO.
- Added contextual disclaimer in Settings > Security explaining enrollment behavior for both modes (auto-provision on vs off).
- Updated "How Google Sign-In Works" info section with complete enrollment flow documentation.

#### Critical/High Bug Remediation Sprint (2026-03-31)

**Security (5 fixes):**
- **(SEC-005) httpOnly Cookie Auth — Phase 1 + Phase 2**: Phase 1: Backend sets `tsushin_session` httpOnly cookie on login/signup/invite-accept. `auth_dependencies.py` checks cookie first, Bearer token as fallback. WebSocket accepts cookie auth from upgrade request. Logout endpoint clears cookie. Phase 2: Migrated all 19 frontend files (~84 fetch calls) from manual `localStorage.getItem('tsushin_auth_token')` to centralized `authenticatedFetch()`. Removed all `getAuthHeaders()` helpers. Token only read in 3 intentional locations (AuthContext lifecycle, authenticatedFetch fallback, WebSocket auth).
- **(SEC-010) API Client JWT Revocation on Secret Rotation**: Added `secret_rotated_at` column to `ApiClient`. JWT claim includes rotation timestamp. `_resolve_api_client_jwt` rejects tokens issued before last rotation. DB migration included.
- **(SEC-019) File Upload Magic Bytes Validation**: PDF and DOCX uploads validated via `filetype` library magic bytes check. ZIP bomb protection for DOCX with 100MB uncompressed size limit. Extension-only validation for text formats (txt/csv/json).
- **(LOG-020) Sentinel Configurable Fail Behavior**: Sentinel pre-check exception handling now supports `sentinel_fail_behavior` config field (`"open"` | `"closed"`). Fail-closed blocks message and logs structured error instead of silently allowing.
- **CORS Hardening**: Replaced wildcard `"*"` with origin reflection (`allow_origin_regex=".*"`) for `credentials: true` support. Restricted `allow_methods` and `allow_headers` from `"*"` to explicit lists. Exception handlers updated to match.

**Multi-Tenancy Isolation (6 fixes):**
- **(LOG-002) Cross-Tenant Subflow Execution**: `SubflowStepHandler` validates target flow belongs to same tenant before execution. `run_flow()` accepts optional `tenant_id` filter.
- **(LOG-003) Cross-Tenant Memory Query Leakage**: `_get_thread_messages()` in `conversation_knowledge_service.py` now scopes Memory queries by agent_ids belonging to the caller's tenant.
- **(LOG-004) Cross-Tenant Document Chunk IDOR**: `get_project_knowledge_chunks()` verifies `doc_id` belongs to the verified `project_id` before returning chunks.
- **(LOG-012) ContactAgentMapping Tenant Isolation**: Added `tenant_id` column with DB migration + backfill from agent's tenant. Router contact lookup scoped by MCP instance's tenant.
- **(LOG-014) Cross-Tenant Agent-to-Project Assignment**: `update_project_agents()` validates each `agent_id` belongs to the caller's tenant before creating `AgentProjectAccess` records.
- **(LOG-018) Anonymous Contact Hash Fallback**: Replaced `hash(sender) % 1000000` phantom ID fallback with re-raise. Callers use sender-string-based memory key.

**Flow Engine (3 fixes):**
- **(LOG-007) Stale Flow Run Recovery**: `run_flow()` resets "running" flows older than 1 hour to "failed" on startup. `on_failure=continue` with failed steps now reports `"completed_with_errors"` instead of `"completed"`.
- **(LOG-010) Step Idempotency TOCTOU**: SELECT FOR UPDATE with `skip_locked=True` + IntegrityError handling prevents concurrent step execution race.
- **(LOG-011) Flow Cancellation**: `db.refresh(flow_run)` between steps detects external cancellation and breaks the execution loop.

**Logic (2 fixes):**
- **(LOG-006) A2A Depth Limit Enforcement**: `SkillManager.execute_tool_call()` propagates `comm_depth` and `comm_parent_session_id` from message metadata into skill config for chained delegation depth tracking.
- **Already fixed (validated):** SEC-001 (admin password reset JWT invalidation), SEC-008 (update_client privilege escalation check), SEC-016 (shell queue_command tenant policies).

---

## [0.6.0-rc1] - 2026-03-30

### Added

#### AI Providers
- **Groq LLM Provider**: Ultra-fast LLM inference via OpenAI-compatible API. Models: Llama 3.3 70B Versatile, Llama 3.1 8B Instant, Mixtral 8x7B 32K, Gemma2 9B IT. Full streaming support.
- **Grok (xAI) LLM Provider**: xAI's Grok models via OpenAI-compatible API. Models: Grok 3, Grok 3 Mini, Grok 2. Full streaming support.
- **DeepSeek LLM Provider**: Full backend + Hub integration. Models: DeepSeek-V3, DeepSeek-R1 (reasoning). OpenAI-compatible endpoint.
- **ElevenLabs TTS (complete implementation)**: Premium voice AI synthesis. Dynamic voice list from API, 29+ languages, emotional tone control, character-based usage tracking, health check via subscription endpoint.
- **OpenAI-Compatible URL Rebase & Multi-Instance Providers**: Configure custom OpenAI-compatible base URLs for LiteLLM, vLLM, LocalAI, Azure OpenAI, or any proxy. Multiple named instances of the same vendor with independent API keys and model lists. Agent-level instance selection via dropdown.
- **Settings > Integrations UI**: Branded provider cards for Groq, Grok, ElevenLabs, and DeepSeek. Configure/Edit/Remove modals, Test Connection with inline results, encryption at rest, multi-tenancy key isolation.
- **Test Connection Endpoints**: `POST /api/integrations/{service}/test` for all providers. Provider-specific validation (ElevenLabs via `/v1/user`, Groq/Grok via minimal test message).
- **Hub AI Providers UX Cleanup**: ElevenLabs added to vendor lists and instance modal. Grok/Groq now have distinct icons. API key precedence indicator (legacy vs instance key).
- **Vertex AI Provider (Phase 1+2)**: Google Cloud Model Garden integration. Phase 1: Gemini models via Vertex AI endpoint (us-east5 region). Phase 2: Claude models via Google Cloud (Anthropic-on-Vertex). Service account auth with Application Default Credentials. Region-aware endpoint routing. Full streaming support. Hub integration with Vertex AI provider card.
- **Hub Local Services Management**: Kokoro TTS start/stop/status controls via Docker API. Ollama auto-create/enable/disable toggle, inline URL editing, test connection, model refresh. Ollama removed from Provider Instances vendor list (only in Local Services).

#### Security
- **Sentinel Security Profiles**: Granular security profiles with custom configuration per protection rule. Hierarchical inheritance at tenant → agent → skill level — lower-level overrides inherit from higher. Full CRUD UI in Settings > Sentinel > Profiles (create/edit/clone/delete). Tenant-level assignment in General tab, agent-level in Agents > Security modal, skill-level via SkillSecurityPanel. Hierarchy visualization tab.
- **MemGuard — Memory Poisoning Detection**: Fifth Sentinel detection type (`memory_poisoning`). Layer A: pre-storage regex pattern matching (EN + PT) blocks poisoned messages. Layer B: fact validation gate blocks credential injection, command patterns, and contradictions before SemanticKnowledge writes. Zero-migration integration via `detection_overrides` inheritance in Security Profiles. Dedicated MemGuard tab in Sentinel settings with branded UI.
- **Custom Skill Scanning — Dedicated Sentinel Profile**: Context-aware LLM prompt that understands skill instructions modify behavior by design. "Custom Skill Scanning" card in Settings > Sentinel > General with profile picker. Scan detail popover showing rejection reason, detection type, threat score, and profile. Gray "unknown" badge for unscanned skills. Auto-open popover after re-scan. Rejected skills cannot be used by agents until re-scanned clean.
- **SSRF Protection for Browser Automation**: Comprehensive Server-Side Request Forgery protection for the browser automation skill. New `browser_ssrf` Sentinel detection type with LLM-based intent analysis at 3 aggressiveness levels. DNS-resolution-based URL validation blocks private IPs, cloud metadata, Docker/Kubernetes internals, CGNAT ranges, and loopback addresses. Per-tenant URL allowlist/blocklist in BrowserConfig. Sentinel `analyze_browser_url()` pre-navigation check integrated into both legacy and MCP tool paths. Browser SSRF toggle in Sentinel settings UI (critical severity, enabled by default). Automatic DB migration for existing installations.
- **API v1 Security Hardening & OpenAPI Documentation**: OAuth token endpoint rate limiting (10 req/min per IP). HTML sanitization validators on Persona, Contact, and Agent fields (stored XSS prevention). Phone number E.164 validation. Shared v1 schemas module with 20+ reusable Pydantic models. `response_model=` wired on all 40 v1 endpoints. Error documentation (401/403/404/422/429) on all endpoints. `X-API-Version: v1` response header. Static `docs/openapi.json` export (435 paths, 413 schemas).
- **Slash Command Hardening**: sender_key spoofing fix (always derive from JWT), email cache cross-user isolation (keyed by agent_id + sender_key), agent-level sandboxed tool authorization check, pattern cache language scoping, permission_required field enforcement warning.

#### Custom Skills & MCP Integration
- **Custom Skills — Phase 1: Instruction Skills**: Tenant-authored instruction-based skills that inject domain knowledge and behavioral rules into agent system prompts. DB migration with `custom_skill`, `custom_skill_version`, `agent_custom_skill`, `custom_skill_execution` tables. `CustomSkillAdapter(BaseSkill)` for instruction injection. CRUD API with full tenant isolation. Full Settings > Custom Skills UI (library list, skill cards, form modal with Definition/Trigger/Instructions sections). New RBAC permissions: `skills.custom.create/read/execute/delete`.
- **Custom Skills — Phase 2: Script Skills + Container Hardening**: Tenant-authored Python/Bash/Node.js scripts executed inside per-tenant toolbox containers. Container security hardening: `no-new-privileges:true`, `cap_drop=["ALL"]`, `pids_limit=256`. `CustomSkillDeployService` with SHA-256 hash checking and auto-redeploy. Static network import scan. `/deploy`, `/scan`, `/test` endpoints. Script editor UI (language selector, parameters builder, timeout setting).
- **Custom Skills — Phase 3: Agent Assignment + Flow Integration**: Wire custom skills into agent configuration and flow builder. Agent custom skill assignment endpoints. `AssignCustomSkillModal`, `SkillConfigForm` (schema-driven form renderer). Custom Skills section in agent skills manager. Custom skills in flow builder skill picker under "Custom Skills" separator.
- **Custom Skills — Phase 4: MCP Server Integration**: External MCP servers as tool providers. Transport abstraction: `SSETransport` (generalized from AsanaMCPClient), `StreamableHTTPTransport`. `MCPConnectionManager` singleton with per-tenant connection pools (limit 10), background health checks (60s), exponential backoff reconnect. `MCPDispatcher` routing by namespaced tool name (`{server}__{tool}`). `MCPSentinelGate` with trust-level-based I/O scanning. Tool description pre-storage Sentinel scan. Hub MCP Servers tab with server cards, tool browser, log viewer.
- **Custom Skills — Phase 5: Stdio Transport + Network Hardening**: Stdio MCP servers running inside tenant containers. `StdioTransport` with JSON-RPC 2.0. Binary allowlist (uvx, npx, node) validated at config time. Path traversal rejection. `idle_timeout_sec` watchdog (300s). Process resource limits: `ulimit -v 1048576 -t 60`. DNS egress policy (explicit 8.8.8.8/8.8.4.4). MCP Server Periodic Health Check Service with 3-min interval and circuit breaker sync.
- **MCP Server → Custom Skill UI Wiring**: "MCP Server" as a third skill type in Custom Skills modal. MCP Server dropdown from Hub-configured servers, tool selector with discovered tools, auto-fill from tool metadata. Hub MCP Servers "Create Skill" shortcut button.

#### Channels
- **Channel Abstraction Layer**: Formal channel abstraction layer decoupling agent logic from transport-specific code. `ChannelAdapter` ABC, `ChannelRegistry`, `InboundMessage`/`SendResult`/`HealthResult` types. `WhatsAppChannelAdapter`, `TelegramChannelAdapter`, `PlaygroundChannelAdapter`. Router `_send_message()` dispatches via registry.
- **Slack Channel Integration**: Full Slack workspace integration via Socket Mode (no public URL required). Bot Token + App Token auth stored Fernet-encrypted per tenant. Message threading, rich Block Kit formatting. DM policy (open/allowlist/disabled), channel allowlist. Reconnection with exponential backoff (2s → 30s max, 12 attempts). Non-recoverable error detection (token_revoked, invalid_auth). Hub Channels section: Slack card with connect/disconnect and workspace name.
- **Discord Channel Integration**: Full Discord bot integration via Gateway API v10. Bot token Fernet-encrypted per tenant. Guild/channel allowlists, DM policies, thread support, embed support, slash command bridge (`/tsushin <command>`), emergency stop. Message deduplication TTL cache. Gateway supervisor for non-recoverable errors (4014, token revoked). Hub Channels section: Discord card with connect/disconnect and bot name.
- **Telegram Channel for Flow Steps**: Telegram as available channel for flow notification/message steps. `_resolve_telegram_sender()` helper. chat_id recipient validation. Multi-recipient support in MessageStepHandler. Removed "Coming Soon" badge in flow channel options.
- **Multi-Channel Contact Identity — Slack & Discord**: Contact resolution across Slack and Discord via `ContactChannelMapping`. `ensure_contact_from_slack()` and `ensure_contact_from_discord()` auto-create contacts from messages. Channel badges in contact list (Slack purple, Discord indigo). "Channel Identities" management section in edit modal — view/add/remove channel mappings for all 6 channel types.
- **Channel Health Monitor with Circuit Breakers**: Unified health monitoring for all channels. 30s background probe loop. `CircuitBreaker` state machine: CLOSED → OPEN → HALF_OPEN. WhatsApp, Telegram, Slack, Discord probes. State transition handler: DB persist, audit event, WebSocket emit, Prometheus metric, alert dispatch. Webhook alert system with per-instance cooldown. 4 new Prometheus metrics. 7 REST API endpoints for health status, history, manual probe, circuit reset, and alert config.

#### Messaging & Queuing
- **Message Queuing System**: Async message queue for all channels (WhatsApp, Telegram, Playground). `MessageQueue` table with SELECT FOR UPDATE SKIP LOCKED for concurrent safety. Dead-letter queue after 3 retries. Ordered delivery guarantees. Playground async/sync modes (`?sync=true`). Frontend WebSocket queue events. QueueWorker asyncio background processor.
- **WebSocket Streaming**: Token-by-token response streaming via WebSocket. `/ws/playground` endpoint with secure first-message auth. Animated typing indicators via `StreamingMessage` component. `PlaygroundWebSocket` client with auto-reconnect and exponential backoff. Heartbeat ping/pong (30s intervals). Queue event integration.

#### Browser Automation Enhancements
- **Session Persistence**: `BrowserSessionManager` keyed by `(tenant_id, agent_id, sender_key)`. Reuse existing browser/page across conversation turns. Idle timeout (300s configurable). Background cleanup task. `session_ttl_seconds` column added to browser_automation_integration.
- **Rich Action Set**: 19 total actions including: scroll (page/element/to_element), select_option, hover, wait_for, go_back, go_forward, get_attribute, get_url, type (character-by-character with delay), open_tab, switch_tab, close_tab, list_tabs.
- **Multi-Tab Support**: Full browser tab lifecycle management. Tabs tracked per session. Max tabs configurable via BrowserConfig.
- **CDP Host Browser Mode**: Connect to Chrome running on the host machine via DevTools Protocol (`http://host.docker.internal:9222`). Allows agents to use authenticated browser sessions.
- **Structured Error Feedback**: `BrowserActionError` with `error_type` (element_not_found/timeout/navigation_failed/security_blocked), actionable `suggestion` per error type, current page URL and title in error context.

#### Platform & Infrastructure
- **Public API v1**: Full programmatic REST API for external applications. OAuth2 Client Credentials (`POST /api/v1/oauth/token`) and Direct API Key (`X-API-Key` header). 40 endpoints across 7 route files: Agent CRUD, Chat (sync + async + SSE), Thread management, resource listing (skills/tools/personas/security-profiles/tone-presets), profile assignment, Flows (13 endpoints), Hub (6 endpoints), Studio (3 endpoints). Per-client RPM rate limiting with `X-RateLimit-*` headers. Request audit log (`api_request_log` table). 5 API roles: api_agent_only, api_readonly, api_member, api_admin, api_owner. Settings > API Clients management page (create/rotate/revoke). Swagger UI at `/docs`. 44/44 E2E tests passing.
- **GKE Readiness — Cloud-Native Infrastructure**: `/api/readiness` endpoint for Kubernetes readiness gates. Prometheus `/metrics` endpoint (`http_requests_total`, `http_request_duration_seconds`, `tsn_service_info`). `TSN_LOG_FORMAT` toggle (text/JSON structured logging). `ContainerRuntime` abstraction with `DockerRuntime` (default) and full `K8sRuntime` (maps Docker ops to K8s Deployments/Services/exec API). `SecretProvider` abstraction with `EnvSecretProvider` and `GCPSecretProvider` (Secret Manager with TTL cache). Helm chart (`k8s/tsushin/`) with 16 templates. CI/CD pipeline for GKE (`gke-deploy.yml`, manual trigger). Network policies, HPA, managed TLS, WebSocket ingress support.
- **SSL Encryption During Installation**: Caddy reverse proxy with 3 SSL modes: Let's Encrypt (auto-enrollment), manual certificates, and self-signed (`tls internal`). `docker-compose.ssl.yml` override. Installer prompts for domain, SSL mode, certificate paths. `ProxyHeadersMiddleware` for real client IP. HTTP→HTTPS redirect (308). WSS auto-detection.
- **Audit Logs — Tenant-Scoped Event Capture**: `AuditEvent` PostgreSQL model with JSONB details, tenant isolation, composite indexes. 30+ event types via `TenantAuditActions` enum (auth, agents, flows, contacts, settings, security, api_clients, skills, mcp, team). `TenantAuditService` with export, stats, and per-tenant retention. Background retention worker (24h daemon, per-tenant configurable). Enhanced audit logs page: stats bar, 5-filter panel, CSV export, 30+ event icons, expandable detail rows, severity dots, click-to-filter.
- **Syslog Streaming for Audit Events**: RFC 5424 syslog forwarding via TCP, UDP, or TLS to external syslog servers. `TenantSyslogConfig` with Fernet-encrypted TLS certs. Per-tenant circuit breaker (5 failures → 60s cooldown). Event category filtering (10 categories). Syslog Forwarding card in Settings > Audit Logs with server config, TLS section, test connection.
- **PostgreSQL Migration**: Full migration from SQLite to PostgreSQL 16 as primary database. Alembic migrations, all queries updated for PostgreSQL compatibility, tone presets visibility and playground search fixed.
- **Flows server-side pagination**: Flows list page now uses server-side pagination to efficiently handle large numbers of flows.

#### Agent Studio & UX
- **Agent Studio — Visual Agent Builder**: React Flow canvas in Watcher for visual agent building. Palette panel with 7 profile categories: Persona, Channels, Skills, Sandboxed Tools, Security Profiles, Knowledge Base, Memory. Drag-and-drop with ghost images and category-colored group node glows. Avatars, expandable nodes, tree layout, inline config editing via slide-out panels. Batch builder endpoints. Remove attached items: hover-reveal X button, keyboard Delete, warning toast for last channel removal.
- **Active Chain Edge Glow (Graph View)**: Edges connecting active nodes glow during real-time processing. Edge glow color matches target node type: cyan (channel→agent), blue (agent chain), teal (skill), violet (KB). Pulse animation synchronized with node glow. Fade-out coordinated with 3s post-processing fade.
- **Flow Step Variable Reference Panel**: Collapsible `{x} Variable Reference` panel below template textareas. 4 sections: Previous Steps (with type-specific output field chips), Helper Functions (11 helpers), Conditionals (if/else with operators), Flow Context (global variables). `TemplateTextarea` wrapper with cursor-position-aware variable insertion. `CursorSafeInput`/`CursorSafeTextarea` components prevent cursor position loss on re-renders across 22+ text fields.
- **Smart UX Features**: Auto-save drafts (debounced localStorage per thread). Smart paste auto-detects JSON and code blocks and wraps them in markdown fences. `useDraftSave` hook and `formatPastedContent` utility.
- **WhatsApp Group Slash Commands via Agent Mention**: Trigger slash commands in WhatsApp groups by mentioning the agent: `@agentname /tool nmap quick_scan target=scanme.nmap.org`. All existing slash command types supported.
- **Granular Slash Command Permissions per Contact**: Per-contact slash command access control. `slash_commands_enabled` column on Contact, `slash_commands_default_policy` on Tenant. Hierarchical resolution: tenant default → per-contact override. 3-state dropdown UI in Contacts page. Applies across all channels.
- **Agent-to-Agent Communication**: Agents within the same tenant can communicate directly. 3 actions: `ask` (sync Q&A), `list_agents` (discover capabilities), `delegate` (full handoff with context). Permission management (per-pair grants), rate limiting (per-pair + global), loop detection (parent_session_id chain), depth limiting (default 3). Sentinel `agent_escalation` detection type. "Communication" tab in Agent Studio with session log, permissions CRUD, statistics dashboard.
- **Billing Structure Audit & Cost Tracking**: Token tracking propagated to all 13 previously-missing AIClient call sites across skills and services (FlowsSkill, SchedulerSkill, SearchSkill, BrowserAutomationSkill, FlightSearchSkill, SchedulerService, FactExtractor, ConversationKnowledgeService, AISummaryService, SentinelService). OpenAI streaming uses `stream_options={"include_usage": True}` for actual token counts. Gemini streaming captures `usage_metadata`. Fixed Gemini token estimation.
- **Permission Matrix Update**: All 170+ endpoints audited. Scheduler permissions seeded (entire scheduler was returning 403). Frontend `billing.manage` → `billing.write` mismatch fixed. Sentinel profile read endpoints secured. Knowledge base RBAC guards added. Slack/Discord integration permissions seeded.

#### Memory
- **Temporal Memory Decay with MMR Reranking**: Exponential decay (`e^(-λ × days)`) applied at retrieval time — older memories receive lower relevance scores. MMR reranking for result diversity. Auto-archive facts below configurable threshold. Freshness labels: fresh/fading/stale/archived. Applied to Layer 2 (Episodic/ChromaDB), Layer 3 (Semantic Knowledge), and Layer 4 (Shared Pool). `memory_decay_enabled`, `memory_decay_lambda`, `memory_decay_archive_threshold`, `memory_decay_mmr_lambda` fields on Agent. `last_accessed_at` tracking on SemanticKnowledge and SharedMemory.

#### Image Generation
- **Image generation for Playground channel**: Generated images from the `generate_image` tool are rendered inline in Playground chat messages. Images can be clicked to open in a new tab.
- **Image generation for Telegram channel**: Generated images sent as photos via the Telegram Bot API with optional captions.
- **Image serving endpoint**: New `GET /api/playground/images/{image_id}` endpoint serves generated images to the Playground frontend.
- **WebSocket image delivery**: Image URLs propagated through the WebSocket streaming pipeline for real-time image display.

#### Other
- `ROADMAP.md` for tracking planned features and releases.
- `CHANGELOG.md` for documenting changes across releases.

---

### Changed
- **Legacy keyword triggering deprecated**: All hybrid skills are now tool-only execution mode. Web scraping skill deprecated and replaced by browser_automation skill.
- **Weather skill removed**: Deprecated and fully removed from backend, frontend, Hub, and README.
- **iOS-style toggle switches**: All enable/disable toggles across the entire platform unified to a consistent iOS-style `ToggleSwitch` component.
- **Agent list performance**: N+1 API calls reduced from 92 requests (~2 per agent for skills) to ~6 requests for a 46-agent list. Agent cards now use `skills_count` from the list response.
- **Sandboxed Tools config moved to Skills modal**: Dedicated Sandboxed Tools tab removed; config integrated into the Skills modal for a cleaner UI.
- **Skills UI overhaul**: Separate sections for built-in and custom skills, emoji icons removed, "Add Skill" pattern added.
- **Design system migration**: Auth pages and Agent Detail page migrated to Tsushin design system tokens. Login page updated with Tsushin kitsune banner.
- **Watcher Threats by Type**: Compacted from separate cards to inline pill badges for a denser, more scannable layout.
- **Sentinel default profile**: System default changed from Moderate (block) to Permissive (detect_only) to reduce false positives on fresh installs.
- **ImageSkill default config**: `enabled_channels` now includes `"telegram"` in addition to `"whatsapp"` and `"playground"`.
- **TelegramSender**: Added `send_photo()` method for sending images via the Telegram Bot API.
- **PlaygroundService**: Skill results and agent service results now propagate `media_paths` as cached `image_url` values in both regular and streaming response paths.
- **PlaygroundWebSocketService**: `done` events now include `image_url` field when images are generated.
- **PlaygroundChatResponse**: Added `image_url` field to the API response model.
- **PlaygroundMessage**: Added `image_url` field to the message model (both backend and frontend).
- **ExpertMode component**: Message bubbles now render generated images with responsive sizing and click-to-open behavior.

---

### Fixed

#### UI/UX QA Audit (BUG-121 to BUG-130)
- **(BUG-121) Onboarding tour auto-navigates users away**: Removed race condition; tour only activates via explicit `startTour()` call.
- **(BUG-122) Tour appears on unauthenticated pages**: Added `usePathname()` guard — returns null on `/auth/*` routes.
- **(BUG-123) Agent list makes 92 API calls for 46 agents (N+1)**: Removed per-agent skills fetch; use `skills_count` from list response. Reduced to ~6 requests.
- **(BUG-124) System Admin pages fail with mixed content on HTTPS**: Browser-side `API_URL` changed to empty string (relative paths via proxy). Added trailing slashes to admin endpoints to prevent FastAPI 307 redirects.
- **(BUG-125) Sandboxed Tools "Access Denied" for Owner role**: Created `tools.read` permission, assigned to all roles.
- **(BUG-126) No "System" navigation link for Global Admin users**: Added conditional System nav item visible only when `isGlobalAdmin`.
- **(BUG-127) Messages sender column shows "-" for all rows**: Fixed sender column display logic.
- **(BUG-128) Footer shows copyright year "2025" instead of "2026"**: Updated copyright year.
- **(BUG-129) Agent list stale refs cause navigation to wrong pages**: Fixed stale reference issues in agent list.
- **(BUG-130) Organization usage shows 720% over plan limit with no warning**: Added over-limit warning display.

#### Security Audit (BUG-131 to BUG-145)
- **(BUG-131) Password reset token exposed in API response body**: Removed `reset_token` from response model. Uniform message regardless of email existence.
- **(BUG-132) Path traversal via unsanitized tenant_id in workspace path construction**: Added regex validation for tenant_id; `Path.resolve()` + bounds check applied.
- **(BUG-133) Gemini prompt injection via merged system+user prompt**: Fixed by using `system_instruction` parameter in `GenerativeModel` constructor at the API protocol level.
- **(BUG-134) JWT tokens not invalidated after password change**: Added `password_changed_at` claim comparison on every authenticated request.
- **(BUG-135) Docker socket mounted in backend container (container escape risk)**: Documented `docker-socket-proxy` requirement for production.
- **(BUG-136) SSRF bypass via HTTP redirect in webhook handler**: Replaced custom check with `validate_url()` from `ssrf_validator`. Added `follow_redirects=False`.
- **(BUG-137) SSO `redirect_after` allows open redirect**: Added validation that `redirect_after` is a relative path only.
- **(BUG-138) `require_global_admin` dependency doesn't return user object**: Added `return current_user`; updated call sites.
- **(BUG-139) Container `workdir` parameter accepts arbitrary paths**: Added regex pattern constraint restricting to paths under `/workspace`.
- **(BUG-140 to BUG-143) Four implementation review bugs**: Local get_current_user bypass, and related auth/CORS issues fixed.
- **(BUG-144) React hooks violation**: Fixed conditional hook usage in playground component.
- **(BUG-145) CORS gap**: Fixed missing CORS headers on specific endpoints.

#### Slash Command Hardening (BUG-147 to BUG-149)
- **(BUG-147) sender_key spoofing on /api/commands/execute**: Always derive sender_key from authenticated JWT. Never accept from request body.
- **(BUG-148) Email cache cross-user data leakage**: Cache key changed from `agent_id` to `(agent_id, sender_key)` tuple.
- **(BUG-149) Agent-level sandboxed tool authorization bypass**: Added `AgentSandboxedTool` authorization check before execution.

#### RBAC Permission Matrix Audit (BUG-150 to BUG-153)
- **(BUG-150) Scheduler permissions not seeded — entire scheduler API returns 403**: Added 4 scheduler permissions to `seed_rbac_defaults` with proper role assignments.
- **(BUG-151) Billing page inaccessible — billing.manage vs billing.write mismatch**: Frontend permission check corrected to `billing.write`.
- **(BUG-152) Sentinel profile read endpoints missing RBAC**: Added `org.settings.read` guard to 5 read endpoints.
- **(BUG-153) Knowledge base routes missing RBAC**: Added `knowledge.read/write/delete` guards to all 8 endpoints.

#### Channel Abstraction Code Review (BUG-154 to BUG-155)
- **(BUG-154) WhatsApp channel adapter behavioral regression**: Mirrored original router logic — allow sends for None/default URL, check only `connected` flag.
- **(BUG-155) Telegram adapter health_check crash on non-dict response**: Added `isinstance(me, dict)` guard with `getattr` fallback.

#### v0.6.0 Perfection Team Audit — 45 Bugs (BUG-156 to BUG-200)

**Critical (11):**
- **(BUG-156) Custom skill script_entrypoint shell injection**: Added regex validation on save; `shlex.quote()` at execution.
- **(BUG-157) TSUSHIN_INPUT env var unquoted shell injection**: Applied `shlex.quote()` around the JSON string.
- **(BUG-158) stdio_binary allowlist bypass via PUT update endpoint**: Added same allowlist + path traversal + metacharacter checks from POST to PUT endpoint.
- **(BUG-159) Anthropic AsyncAnthropic coroutine passed to asyncio.to_thread**: Replaced `asyncio.to_thread(...)` with `await self.client.messages.create(...)`.
- **(BUG-160) Provider instance API key encryption identifier mismatch**: Unified encryption identifiers; routes now delegate to `ProviderInstanceService._encrypt_key/_decrypt_key`.
- **(BUG-161) Missing permission on /sentinel/cleanup-poisoned-memory**: Added `require_permission("org.settings.write")`.
- **(BUG-162) Unauthenticated /metrics endpoint exposes telemetry**: Added IP allowlist / bearer token check to Prometheus endpoint.
- **(BUG-163) thread_id not validated for tenant ownership in API v1 chat**: Added thread ownership validation before passing to service layer.
- **(BUG-164) Discord media upload sends invalid JSON via repr()**: Replaced `repr()` with `json.dumps({"content": text or ""})`.
- **(BUG-165) Discord media upload file handle never closed**: Added context manager `with open(media_path, "rb") as f:`.
- **(BUG-166) WebSocket onMessageComplete stale closure**: Changed to read from `activeThreadIdRef.current`; functional `setMessages(prev => ...)`.

**High (21):**
- **(BUG-167) Cross-tenant SentinelProfile access via user-controlled ID**: Added `(is_system == True) | (tenant_id == self.tenant_id)` filter.
- **(BUG-168) OpenRouter discover-models SSRF — no URL validation**: Added `validate_url(base_url)` before HTTP call.
- **(BUG-169) SlashCommandService._pattern_cache never invalidated**: Added TTL and invalidation on command write operations.
- **(BUG-170) NameError in Ollama SSRF rejection path**: Fixed bare `logger` reference to `self.logger`.
- **(BUG-171) BrowserAutomationSkill token tracker attribute mismatch**: Fixed `self._token_tracker` → `self.token_tracker`.
- **(BUG-172) AgentCustomSkill assignment update missing tenant isolation**: Added `CustomSkill.tenant_id == ctx.tenant_id` filter; return 404 if skill gone.
- **(BUG-173) StdioTransport.list_tools() always returns empty list**: Implemented JSON-RPC `tools/list` via stdin.
- **(BUG-174) MCPDiscoveredTool listing missing tenant_id filter**: Added `.filter(MCPDiscoveredTool.tenant_id == ctx.tenant_id)`.
- **(BUG-175) Slack WebClient blocking I/O in async methods**: Replaced with `AsyncWebClient`.
- **(BUG-176) Channel alert cooldown key missing tenant_id**: Added `tenant_id` to key: `(tenant_id, channel_type, instance_id)`.
- **(BUG-177) Phase 21 @agent /command uses wrong tenant's permission policy**: Added `agent.tenant_id == self._router_tenant_id` validation.
- **(BUG-178) WhatsApp adapter blocking httpx.get() in async send_message**: Replaced with `httpx.AsyncClient` with `await`.
- **(BUG-179) Agent comm skill always passes depth=0 — depth limit ineffective**: Fixed `depth` and `parent_session_id` forwarding from calling context.
- **(BUG-180) API v1 sender_key computed but never passed to service**: Passed `sender_key` to `send_message()` and `process_message_streaming()`.
- **(BUG-181) API v1 list_agents loads all agents into memory**: Pushed search filter to DB `ilike`, applied `offset`/`limit` in SQL.
- **(BUG-182) HSTS header missing from all Caddyfile SSL modes**: Added `Strict-Transport-Security` header to all SSL mode templates.
- **(BUG-183) Syslog TLS temp file descriptors leak**: Added `os.close(cert_fd)` and `os.close(key_fd)` to `finally` block.
- **(BUG-184) Flow step agent_id/persona_id not validated for tenant isolation**: Added tenant ownership check on `agent_id`/`persona_id` in flow step create/update.
- **(BUG-185) Playground fetchAvailableTools/Agents hardcoded HTTP URL**: Replaced raw `fetch()` calls with `api.*` methods from `client.ts`.
- **(BUG-186) Dead API_URL constant in contacts page with unsafe fallback**: Removed unused `API_URL` constant.
- **(BUG-187) Agent Studio updateNodeConfig doesn't set isDirty**: Added `next.isDirty = true` in all three node type branches.

**Medium (13):**
- **(BUG-188) system_prompt/keywords missing HTML sanitization in API v1**: Added `@field_validator("system_prompt")` with `strip_html_tags`.
- **(BUG-189) MemGuard warn_only mode doesn't send threat notification**: Added `send_threat_notification` call analogous to Sentinel's warned path.
- **(BUG-190) _scan_instructions silently returns clean on any exception**: Changed to return `scan_status='pending'` on LLM outage.
- **(BUG-191) Grok test model grok-3-mini not in PROVIDER_MODELS**: Updated test model to `grok-3`.
- **(BUG-192) validate-url endpoint rejects valid private IPs for local providers**: Consistent private IP handling with create/update endpoints.
- **(BUG-193) Custom skill deploy service entrypoint path injection**: Applied same validation as BUG-156 fix.
- **(BUG-194) Custom skill assignment update crashes on deleted skill**: Added None check; returns 404 if skill deleted.
- **(BUG-195) Network import scan only covers Python — misses bash/nodejs**: Added language-aware patterns for bash (`nc`, `ncat`, `/dev/tcp`) and Node.js (`require('http')`, etc.).
- **(BUG-196) Rate limiter _windows dict grows without bound**: Added periodic eviction of keys with empty lists after expiry pruning.
- **(BUG-197) Audit retention worker no per-tenant rollback on failure**: Wrapped each tenant purge in per-iteration `try/except` with `session.rollback()`.
- **(BUG-198) API client update allows role escalation without permission check**: Added `updater_permissions` parameter and scope subset check to `update_client`.
- **(BUG-199) Readiness probe _engine may be None on cold path**: Added null-check; returns 503 with engine-not-initialized message.
- **(BUG-200) CursorSafeTextarea in flows missing blur-flush**: Added `onValueChange(localValue)` in `onBlur` handler.

#### Other Fixes
- **Flow step cursor position loss and pending edits lost on save**: `CursorSafeInput`/`CursorSafeTextarea` components created with local state that only syncs from parent when not focused. Flush-on-unmount added so pending edits are not lost when modal closes.
- **Flow step Notification field mapping mismatch**: Fixed `content` vs `message_template` field read/write inconsistency.
- **Flow step backend schema missing fields**: `FlowStepConfig` Pydantic model now includes all fields for skill, summarization, and slash_command step types.
- **[object Object] error toast in Studio**: `handleApiError` now properly extracts Pydantic validation error arrays. All ~200 API methods in `client.ts` now use `handleApiError` for consistent error display.
- **Contact form "external" role 422 error**: Contact form now supports the `external` role.
- **Agent Studio builder save**: Persona and channel changes now persist correctly on builder save.
- **Playground NoneType len() error**: Resolved and improved error handling.
- **Google credential save crash**: Preserved `tenant_id` for admins to fix credential encryption failures.
- **Browser skill session manager wiring**: Session manager properly wired, structured errors fixed, value leak resolved.

#### VM Fresh Install Regression
- **RBAC seeding crash loop on first boot**: Added orphan-permissions guard at the start of `seed_rbac_defaults` — if permissions exist but no roles exist, permissions are cleared before re-seeding. Prevents `UniqueViolation` crash-restart loop on the first backend startup.
- **Global admin login returns 500 — NULL tenant_id in audit logging**: Added early-return guard in `log_tenant_event()` when `tenant_id is None`. Global admins have no tenant affiliation; their actions are handled by `GlobalAdminAuditService` separately.
- **(BUG-201) Installer leaves frontend unhealthy — docker-compose v1 health dependency race**: Installer now waits for backend to become healthy before starting the frontend container, working around docker-compose v1.29.2 `service_healthy` condition race on Ubuntu 24.04.
- **(BUG-202) Browser API calls use relative paths incompatible with HTTP-only installs**: Fixed `client.ts` API URL resolution so installations without Caddy proxy (SSL disabled) work correctly. Relative `/api/*` paths now resolve against the correct origin.

---

## [0.5.0-beta] - 2026-02-01

### Added
- Initial beta release
- Multi-agent architecture with intelligent routing
- Skills-as-Tools system with MCP compliance
- 16 built-in skills
- WhatsApp channel via MCP bridge
- Telegram channel integration
- Playground web interface with WebSocket streaming
- 4-layer memory system
- Knowledge base with document ingestion
- RBAC with multi-tenant support
- Watcher dashboard with analytics
- Sentinel security system
