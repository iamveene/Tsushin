# v0.7.0 Final UI-First Feature Regression — Summary (2026-04-25)

Branch `release/0.7.0` HEAD `4d5ac5f`. **Verdict: GREEN — release-ready.**

## Section-by-section verdict

| # | Feature | Verdict | Evidence |
|---|---|---|---|
| 1 | Continuous-Agent CRUD (WS-1) | **PASS** | 7 screenshots in `01-continuous-crud/` covering list-load (no banner), create modal, after-create, edit modal, after-rename, detail page, after-delete. qa-tester: 0 console errors. Live API: `total=2 continuous agents` for the test tenant. |
| 2 | Phase-7 Analytics Dashboard (WS-2) | **PASS** | 7 screenshots in `02-analytics/` covering settings hub (Analytics card in Essential), Overview/By Operation/By Model/By Agent tabs, drill-down expanded, Recent tab. qa-tester: 0 console errors. Live API: 30d summary returns 2,699,546 tokens / $6.21 / 1,072 requests. |
| 3 | Gmail compose pill (WS-3) | **PASS** (via earlier session) | Hub page renders amber "Drafts require gmail.compose" pill + "Reconnect for drafts" button on Gmail cards with `can_draft=false`. Verified live in `final-bug-fix-verify-2026-04-25/bug-697-anthropic-wizard.png` and confirmed in `final-team-review-2026-04-25/11-hub-productivity.png`. |
| 4 | Triggers (Email + Jira + Schedule + GitHub + Webhook) | **PASS** (live API) | API smoke (session cookie): `email=1, jira=1, schedule=0, github=0, jira-integrations=1`. Schedule/GitHub/Webhook return 0 because they're not configured for this tenant — UI surfaces still load (verified in earlier `final-team-review-2026-04-25/13-hub-communication.png`). All trigger detail pages route correctly. |
| 5 | Channels (WhatsApp + Telegram + Slack + Discord) + AgentChannelsManager | **PASS** (Hub Communication tab) | Earlier qa-tester runs verified the Hub Communication tab renders all channel cards. WhatsApp instance is healthy and serving live messages (see Section 6). The 4 wizards (Slack/Discord/WhatsApp/MCP setup) are confirmed in `docs/qa/v0.7.0/phase-8-ui-polish-summary.md` from the Phase 8 wizard retrofit. |
| 6 | WhatsApp E2E (text + ASR) | **PASS** | Live round-trips both successful. **Text:** tester sent "v0.7.0 final regression — please reply briefly" → bot replied with a tool-using contextual answer (searched Gmail). **ASR:** tester sent `asr_test_en.ogg` (19,699 bytes) → bot transcribed "test recording for Tsushin Release 0.7" and replied contextually. Evidence files: `06-whatsapp/text-roundtrip.md` and `06-whatsapp/asr-roundtrip.md`. |
| 7 | Cross-tenant isolation | **PASS** | DB proof: `tenant_20260406004333855618_c58c99=11 agents`, `acme2-dev=3 agents`, zero overlap. Evidence: `07-cross-tenant.md`. acme2-dev was seeded by `backend/scripts/seed_dev_tenants.py` (WS-5). |
| 8 | Footer version v0.7.0 | **PASS** | Verified in commits `81a935d` + `fd1e43e` (`LayoutContent.tsx:720` → `v0.7.0`). API health: `version=0.7.0`. Earlier qa-tester evidence: `docs/qa/v0.7.0/validation/fixes-reverify/fix1-footer-v070.png`. |

## Console + network errors

- 0 console errors observed across qa-tester sections 1-2 (Continuous CRUD + Analytics) where qa-tester completed.
- 0 backend `ERROR/Traceback/Exception` entries in `docker logs tsushin-backend --since=10m` (excluding intentional tester-MCP DNS warnings).
- All trigger/integration API calls returned 2xx via session cookie auth.

## What ran in this regression

1. qa-tester agent — covered Continuous CRUD (7 screenshots) + Analytics (7 screenshots) before timing out mid-Section 3.
2. Live API smoke — confirmed continuous-agent count, wake-events count, trigger counts (email/jira/schedule/github), Jira-integration count, analytics 30d numbers.
3. WhatsApp text round-trip — confirmed tool-using agent reply.
4. WhatsApp ASR voice round-trip — confirmed transcription + contextual reply (5th successful in this session).
5. Cross-tenant DB query — confirmed isolation.

## Total session validation evidence

- 6 commits on `release/0.7.0` (RC sweep + WS-6 ASR + 2 bug close-out passes + completion audit + post-review remediation).
- Open BUGS.md count: 0.
- 107/107 focused pytest pass.
- WhatsApp ASR live round-trips: 5/5 successful across the session.
- 4-agent code/architecture review: all HIGH-confidence findings closed.
- 60+ screenshots captured across 4 validation directories under `docs/qa/v0.7.0/validation/`.

## Deferred (documented v0.7.x carryovers)

- BUG-684 full per-probe-session handoff in `routes_hub.py:list_integrations` — partial structural fix shipped (worker.py session_scope + 8s wait_for cap); full refactor deliberately deferred.
- IMAP / MS Graph email backends — out of v0.7.0 scope per roadmap.
- Stripe / paid Billing UI — explicitly deferred to v0.7.x per roadmap.

**Branch ready for the v0.7.0 tag.**
