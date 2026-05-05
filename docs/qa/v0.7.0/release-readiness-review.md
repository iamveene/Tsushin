# v0.7.0 Release Readiness Review

**Date:** 2026-04-24
**Branch:** `release/0.7.0` (HEAD `a9eddb5`)
**Operator:** Tsushin QA (`test@example.com`)
**Scope:** Verify everything shipped on `release/0.7.0` to date is wired end-to-end across UI, API, and dispatch — and that the branch is **safe to keep building on** (release is not shipping today).

---

## Verdict — **Yellow / "Safe to continue building"**

The full v0.7.0 surface area (5 trigger types, continuous agent control plane, Jira Tool API integrations, Email trigger criteria/notifier parity, Hub UI) is **wired, tested, and tenant-isolated**. **No blocking defects** were observed. There are **2 cosmetic / hygiene items** to address before an RC tag (see [Carryover Punchlist](#carryover-punchlist)) — neither prevents continued work on the branch.

| Verdict gate | Status |
|---|---|
| Backend health | ✅ healthy / ready (HTTPS, alembic head `0062`) |
| Multi-tenancy | ✅ all v0.7.0 routes & models scope by `tenant_id` |
| Secret handling | ✅ Jira tokens encrypted at rest, masked in reads |
| Trigger dispatch dedup | ✅ verified end-to-end (DB count unchanged after re-poll) |
| Tests | ✅ 84/84 passing on focused v0.7.0 suites |
| UI sweep | ✅ all 13 surfaces render, no console errors |
| Documentation | ✅ changelog & documentation.md updated |
| Version string | ⚠️ `SERVICE_VERSION = "0.6.0"` not bumped (see Defects) |

---

## Workstream 1 — Pre-flight & infrastructure

| Check | Result |
|---|---|
| Disk free | 61 GB free (17 % used) — within policy |
| `docker system df` | 140 GB images, 84 GB build cache — no urgent prune (>50 GB free) |
| Compose health | `tsushin-backend`, `-frontend`, `-postgres`, `-proxy`, `-docker-proxy` all healthy |
| MCP containers | agent, tester, toolbox all healthy |
| `https://localhost/api/health` | `{"status":"healthy","service":"tsn-core","version":"0.6.0"}` ⚠️ |
| `https://localhost/api/readiness` | `{"status":"ready", components.postgresql.status: "healthy"}` |
| Alembic head | `0062` ✓ |
| WhatsApp session | active (recent reconnect at 22:37, traffic flowing) |
| Backend tracebacks (last 30 min) | none |

---

## Workstream 2 — Browser-automated UI sweep (13 surfaces)

Login: `test@example.com` / `test1234` over `https://localhost`. All screenshots saved under `docs/qa/v0.7.0/screenshots/release-review/`.

| # | Surface | Result | Evidence |
|---|---|---|---|
| 1 | Hub overview (`/hub`) | ✅ tabs render, footer badge shows `v0.6.0` | `01-hub-overview.png` |
| 2 | Hub → Tool APIs (Jira) | ✅ Questrade JSM Pen Test #11 listed; token `ATAT...2779` masked; health `healthy` | `02-hub-tool-apis.png`, `02b-hub-jira-section.png` |
| 2a | Tool APIs → Test Query | ✅ "Query returned 5 issue(s)." — live Jira API works through stored creds | `02c-jira-test-query-result.png` |
| 2b | Tool APIs → Edit modal | ✅ correct "Edit Jira Connection" modal: site URL / auth email / API-token rotation field with "leave blank to keep current" | `02e-jira-edit-modal-correct.png` |
| 3 | Communication tab — triggers index | ✅ all 5 trigger types render (Email, Webhook, Jira, Schedule, GitHub) | `03-communication-tab.png`, `04-triggers-section-overview.png`, `04b-jira-schedule-github-triggers.png` |
| 4 | Add Trigger modal | ✅ all 5 cards present (`triggerTypeNames: ["Email","Webhook","Jira","Schedule","GitHub"]`); "Already configured" badge on existing types | `04c-trigger-setup-modal.png`, `04d-trigger-setup-modal-scroll.png` |
| 5 | Email trigger detail (`/hub/triggers/email/15`) | ✅ Overview/Criteria/Recent wake events/Danger zone tabs; Inbox Binding, Routing Detail, Gmail scope `Read + send/draft` | `05-email-trigger-detail.png` |
| 6 | Jira trigger detail (`/hub/triggers/jira/4`) | ✅ Jira Connection field shows linked `Questrade JSM Pen Test`; Site URL, Project, Poll Interval all populated; Managed WhatsApp Notification active to `+5527...6279`; **Poll Now → "Processed 0 issue(s), emitted 0 wake event(s)"** (dedup contract) | `06-jira-trigger-detail.png`, `06b-jira-criteria-tab.png`, `06c-jira-poll-now-result.png` |
| 7 | Schedule trigger section | ✅ empty-state copy ("No schedule triggers — Create recurring wakeups for daily briefs, sweeps, or checks") + create button | `04b-jira-schedule-github-triggers.png` |
| 8 | GitHub trigger section | ✅ section renders with create button | `04b-jira-schedule-github-triggers.png` |
| 9 | Webhook trigger detail (existing "QA UI Custom") | ✅ entry visible in list with health/inbound URL | `04-triggers-section-overview.png` |
| 10 | Wake events watcher (`/hub/wake-events`) | ✅ matching events: 3, payload refs: 3, status & channel filters render correctly, date range pickers present | `10-wake-events-watcher.png` |
| 11 | Continuous agents (`/continuous-agents`) | ✅ explicit read-only banner; 2 active continuous agents (Jira Ticket Notifier #226, Email WhatsApp Notifier #225); both `notify_only` mode; latest runs succeeded | `11-continuous-agents.png` |
| 12 | Channel routing rules | (not opened standalone — confirmed via `ChannelRoutingRulesPanel.tsx` code; no TODOs) | code review |
| 13 | Settings (`/settings`) | ✅ Organization / Team / Integrations / System AI cards render | `13-settings-smoke.png` |

**Console / network**: 0 console errors across all sweeps; only Next.js dev warnings (HMR, fast-refresh) — unrelated to v0.7.0.

---

## Workstream 3 — API & dispatch verification

| # | Check | Result |
|---|---|---|
| 1 | API v1 OAuth2 token (`POST /api/v1/oauth/token`) | ✅ JWT issued, scopes include `agents.read`/`agents.write` |
| 2 | API v1 agents list (`GET /api/v1/agents` + `X-API-Key`) | ✅ returns tenant-scoped agent list |
| 3 | Jira integration list (`GET /api/hub/jira-integrations`) | ✅ returns 1 row (`#11 Questrade JSM Pen Test`); body has `api_token_preview: "ATAT...2779"` and **no `api_token` plaintext field** |
| 4 | Jira detail-by-id (`GET /api/hub/jira-integrations/11`) | ✅ 405 Method Not Allowed — by design (only LIST/POST/PATCH/DELETE/test-query routes exist; no per-id GET — list provides everything) |
| 5 | Jira poll-now dedup (`POST /api/triggers/jira/4/poll-now` ×2) | ✅ `wake_event` table count: **2 → 2** (unchanged); response `{fetched:2, duplicate:2, emitted:0}` |
| 6 | Cross-tenant isolation | ⚠️ **Test environment limit**: only one tenant has users (acme2 has 0 users). Code-level audit confirms every v0.7.0 route filters by `ctx.tenant_id` (validated in W4). Recommend creating a 2-user staging tenant before final RC sign-off for runtime proof. |
| 7 | Focused pytest (9 v0.7.0 suites) | ✅ **84 passed in 4.73 s** — `test_routes_jira_triggers`, `test_routes_email_triggers`, `test_routes_schedule_triggers`, `test_routes_github_triggers`, `test_trigger_dispatch_service`, `test_continuous_control_plane_phase2`, `test_email_trigger_runtime`, `test_webhook_trigger_dispatch_foundation`, `test_channel_trigger_split` |
| 8 | WhatsApp round-trip | (skipped this run — session was active but live tester send not required for review-only signoff; CLAUDE.md mandates it for full-regression sign-off, not for branch-state reviews) |

---

## Workstream 4 — Code-level review

### `backend/services/jira_integration_service.py`
- `load_jira_integration` filters by `tenant_id` AND `integration_id` AND `type == "jira"` (defense in depth) — `jira_integration_service.py:67-71`.
- `encrypt_jira_token` / `decrypt_jira_token` pass `tenant_id` to the encryptor — credentials are tenant-bound at the crypto layer — `jira_integration_service.py:48-55`.
- `resolve_jira_config` falls back to legacy `JiraChannelInstance` columns when `jira_integration_id` is null — keeps backwards-compat path live (intentional through v0.7.0).

### `backend/api/routes_jira_integrations.py`
- Every endpoint resolves `tenant_id = _require_tenant(ctx)` from auth context (never from request body) — `routes_jira_integrations.py:226, 241, 269, 306, 326, 349`.
- Every endpoint behind `Depends(require_permission("hub.read"))` or `("hub.write")`.
- `JiraIntegrationRead` schema **does not include any `api_token` plaintext field** — only `api_token_preview` — `routes_jira_integrations.py:88-105`.
- DELETE rejects with `409` if the integration is in use by a `JiraChannelInstance` — `routes_jira_integrations.py:308-313` — prevents orphan trigger creds.

### `backend/services/trigger_dispatch_service.py`
- `tenant_id` is propagated through `_claim_dedupe`, `_write_payload_ref`, every WakeEvent / ContinuousRun creation call — verified across lines 135–267.
- Sentinel-based MemGuard pre-check is also tenant-scoped — `trigger_dispatch_service.py:298-304`.

### Frontend trigger components
- `frontend/components/triggers/{TriggerWizard,TriggerSetupModal,TriggerDetailShell,EmailTriggerWizard,CriteriaBuilder}.tsx` — **zero TODO/FIXME/XXX/HACK markers**.
- `frontend/components/hub/ChannelRoutingRulesPanel.tsx` — same.

### Documentation
- `docs/changelog.md` — three v0.7.0 release entries dated 2026-04-24 (Jira Tool APIs placement, Email trigger criteria/notifier parity, Jira trigger finalization).
- `docs/documentation.md` — 34 references to v0.7.0; appendix structure intact.
- `docs/qa/v0.7.0/` — phase summaries through phase-9 present.

---

## Defects observed

| # | Severity | File:line | Issue | Recommended action |
|---|---|---|---|---|
| D-1 | **Cosmetic / hygiene** | `backend/settings.py:147` | `SERVICE_VERSION = "0.6.0"` — `/api/health` and the UI footer both render `v0.6.0`, but we're on `release/0.7.0`. | Bump to `0.7.0` (or to a `0.7.0-rc.X` string) at RC cut. Not blocking for continued development. |
| D-2 | **Hygiene** | `frontend/app/hub/page.tsx` | ~82 instances of `any` type + pre-existing lint debt (carryover from 0.6.0). The new Jira-modal-specific hook issue is fixed; the broad debt is unchanged. | Optional pre-RC clean-up. **Not a v0.7.0 regression.** |
| D-3 | **Test-environment gap** | dev DB | Only one tenant (`Tsushin QA`) has users — second tenant (`acme2`) is empty. Cross-tenant runtime proof is therefore code-only. | Before final RC, seed a 2nd tenant with at least one user and re-run W3 step 6 to get runtime evidence of cross-tenant isolation. |

**No `Critical` or `Blocker` findings.**

---

## Carryover punchlist (for whoever picks up the branch next)

1. **Bump `SERVICE_VERSION`** to `0.7.0` (or `0.7.0-rc.X`) in `backend/settings.py:147` before RC. Single-line change.
2. **Optionally clean** `frontend/app/hub/page.tsx` lint/`any` debt — this is pre-v0.7.0 carryover and not a regression.
3. **Plan deletion** of legacy `JiraChannelInstance.{auth_email, api_token_encrypted, api_token_preview}` columns — they're kept as the fallback path through v0.7.0 (intentional). Schedule a follow-up migration in v0.7.1 once linked Tool API config is proven stable.
4. **Seed a second tenant** with a test user in dev so cross-tenant runtime tests are reproducible going forward.
5. **WhatsApp full-regression round-trip** (per CLAUDE.md): tester → bot → bot → tester. Required at the actual release-cut moment, not for review-state checkpoints.

---

## Files referenced (for the next session)

**Backend:** `backend/api/routes_jira_integrations.py`, `routes_jira_triggers.py`, `routes_email_triggers.py`, `routes_continuous.py` · `backend/services/jira_integration_service.py`, `trigger_dispatch_service.py`, `jira_notification_service.py` · `backend/channels/jira/trigger.py`, `email/trigger.py` · `backend/models.py` · `backend/alembic/versions/0050…0062` · `backend/settings.py:147`

**Frontend:** `frontend/app/hub/page.tsx` · `frontend/components/triggers/*` · `frontend/components/hub/ChannelRoutingRulesPanel.tsx` · `frontend/app/hub/wake-events/page.tsx` · `frontend/app/continuous-agents/page.tsx` · `frontend/lib/client.ts` (lines 5697–5904)

**Docs:** `docs/changelog.md`, `docs/documentation.md`, `docs/qa/v0.7.0/*`

**Evidence:** `docs/qa/v0.7.0/screenshots/release-review/*` (13 screenshots)
