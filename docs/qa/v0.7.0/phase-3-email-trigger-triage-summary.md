# v0.7.0 Phase 3 Email Trigger/Triage Checkpoint Summary

Date: 2026-04-24

## Scope

This summary records the Phase 3 Email Trigger + Email Triage runtime checkpoint and exit-gate evidence on `release/0.7.0`. Live Gmail evidence is scoped to the allowed fixture accounts `mv@archsec.io` and `movl2007@gmail.com`; the committed fixture currently uses `mv@archsec.io`.

## Implemented

- Gmail-backed Email trigger runtime in `backend/channels/email/trigger.py`.
- Active trigger polling through `EmailTrigger.poll_active()`, called by the scheduler worker after schedule-trigger polling.
- Gmail list/search delta fetch, full message normalization, stable `internalDate:id` cursor advancement, and deterministic `gmail:{message_id}` dedupe keys.
- Tenant-safety checks for missing tenant context, missing Gmail integration, foreign Gmail integration ownership, unsupported provider, and disconnected integrations.
- Managed Email Triage subscription endpoint at `POST /api/triggers/email/{id}/triage-subscription`.
- System-owned continuous agent/subscription creation for `email.message.received`, using the existing default-agent resolution path.
- Fail-closed managed triage enablement: the backend now rejects cross-tenant, inactive/disconnected, missing-token, and send-only Gmail integrations before creating system-owned routing.
- Managed draft creation through `GmailSkill` with `continuous_agent_context`, so the existing Sentinel continuous-action approval gate applies.
- Sentinel-config-gated MemGuard trigger payload pre-check in `TriggerDispatchService`; blocked payloads write `blocked_by_security` and emit no wake/run.
- Alembic `0055_widen_sentinel_detection_type.py` widens Sentinel detection-type fields to 64 characters so `continuous_agent_action_approval` cache/log writes do not truncate.
- Hub Email trigger detail parity: source matching, recent wake events, danger zone, managed triage setup, and `gmail.compose` scope messaging.
- Email trigger setup wizard capability labels now distinguish read-only, send/reply, and draft-capable Gmail integrations so send-only accounts no longer imply draft support.

## Validation Completed

- `python -m py_compile backend/channels/email/trigger.py backend/services/email_triage_service.py backend/services/trigger_dispatch_service.py backend/api/routes_email_triggers.py backend/scheduler/worker.py`
- `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py`
- `pytest -q -o addopts='' backend/tests/test_trigger_dispatch_service.py backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py`
- `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py backend/tests/test_trigger_dispatch_service.py backend/tests/test_gmail_send_phase3_checkpoint.py`
- Follow-up hardening check: `pytest -q -o addopts='' backend/tests/test_routes_email_triggers.py` -> `10 passed`, including cross-tenant, disconnected, and send-only Gmail triage rejection.
- Phase 3 exit-targeted local bundle after the fail-closed hardening commit: `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py backend/tests/test_trigger_dispatch_service.py backend/tests/test_gmail_send_phase3_checkpoint.py backend/tests/test_email_trigger_phase3_live_gate.py` -> `40 passed, 1 skipped`.
- Gmail compose reauthorization completed through Hub for integration `4` (`mv@archsec.io`), and `backend/tests/fixtures/gmail_oauth.enc` was re-exported with draft-compatible scope.
- `TSN_GMAIL_REQUIRE_COMPOSE_SCOPE=1 pytest -q -o addopts='' backend/tests/test_gmail_oauth_fixture.py::test_gmail_oauth_fixture_compose_readiness_is_explicit` -> `1 passed`.
- `TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1 pytest -q -o addopts='' tests/test_gmail_send_phase3_live_gate.py` inside the backend container -> `3 passed, 1 skipped`; proved direct send, direct reply, `GmailSkill` send, and live Gmail draft creation. Optional API agent-chat proof skipped because API token/agent env vars were not set.
- `TSN_RUN_EMAIL_PHASE3_LIVE_GATE=1 pytest -q --tb=short -o addopts='' tests/test_email_trigger_phase3_live_gate.py` inside the backend container -> `1 passed`; proved one incoming Gmail message creates exactly one wake/run, duplicate polling does not double-fire, managed triage creates a Gmail draft, and Sentinel/MemGuard block mode records `blocked_by_security` with no wake/run.
- Container-targeted post-migration bundle: `python -m py_compile models.py alembic/versions/0055_widen_sentinel_detection_type.py tests/test_email_trigger_phase3_live_gate.py && pytest -q -o addopts='' tests/test_email_trigger_runtime.py tests/test_routes_email_triggers.py tests/test_trigger_dispatch_service.py tests/test_gmail_send_phase3_checkpoint.py tests/test_email_trigger_phase3_live_gate.py tests/test_phase0_foundation.py::test_sentinel_detection_type_and_idempotent_seed` -> `41 passed, 1 skipped`.
- `cd frontend && ./node_modules/.bin/eslint 'app/hub/triggers/email/[id]/page.tsx' --max-warnings 0`
- `cd frontend && ./node_modules/.bin/eslint components/triggers/EmailTriggerWizard.tsx --max-warnings 0`
- `cd frontend && ./node_modules/.bin/eslint lib/client.ts --max-warnings 0 --rule '@typescript-eslint/no-explicit-any: off' --rule '@typescript-eslint/no-empty-object-type: off'`
- `git diff --check`
- `docker-compose build --no-cache backend frontend && docker-compose up -d backend frontend`
- `docker-compose build --no-cache frontend && docker-compose up -d frontend` after the final setup-wizard wording adjustment
- Exit-gate backend refresh after Sentinel `0055`: `docker-compose build --no-cache backend` then `docker-compose up -d backend`.
- `docker-compose ps` after the refresh showed backend, frontend, postgres, and proxy healthy.
- `docker-compose exec -T backend alembic current` -> `0055 (head)`
- `docker-compose exec -T backend alembic heads` -> `0055 (head)`
- `information_schema.columns` confirmed `sentinel_analysis_log.detection_type` and `sentinel_analysis_cache.detection_type` are length `64`.
- Direct and proxy health checks passed: `http://localhost:8081/api/health`, `https://localhost/api/health`
- Backend log scan over the rebuilt service tail found no `ERROR`, `CRITICAL`, `FATAL`, `Traceback`, or `Exception` lines.
- Browser smoke passed with zero unexpected console/page/network errors. Covered Hub Communication, Email trigger create/detail/pause/resume/delete, setup/detail `gmail.compose` messaging, triage disabled state without compose scope, Wake Events filtering, and Continuous Agents read-only surface. Navigation-aborted Next.js and Hub background requests were filtered as expected route-change noise. Private evidence is under `.private/qa/v0.7.0/phase-3-exit/browser-email-trigger-smoke.json`.

## Remaining Gates

- Optional API agent-chat Gmail send proof remains pending until the API token/agent live-gate env vars are available.
- Fresh-install Ubuntu VM validation remains pending on the documented Parallels path because SSH works but `sudo -n true` on `parallels@10.211.55.5` requires a human password. Resume with `bash deploy-to-vm.sh`, SSH to the VM, then `sudo python3 install.py` from `~/tsushin`.
- Phase 3.4 template-promotion UI remains deferred and should not block the core Phase 3 ship bar unless it is reclassified.

## Evidence References

- `docs/qa/v0.7.0/phase-3-1-gmail-send-checkpoint-summary.md`
- `docs/qa/v0.7.0/track-b-dispatch-foundation-summary.md`
- `docs/qa/v0.7.0/phase-4-track-b-breadth-summary.md`
- `docs/changelog.md` Unreleased Phase 3 and Track B entries
- `docs/documentation.md` sections 2.6, 2.7, 2.12, and 15.5
