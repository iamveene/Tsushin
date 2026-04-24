# v0.7.0 Phase 3 Email Trigger/Triage Checkpoint Summary

Date: 2026-04-24

## Scope

This summary records the local Phase 3 Email Trigger + Email Triage runtime checkpoint on `release/0.7.0`. It does not claim the full Phase 3 exit gate because live Gmail draft creation still requires reauthorization with a draft-compatible scope.

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
- Hub Email trigger detail parity: source matching, recent wake events, danger zone, managed triage setup, and `gmail.compose` scope messaging.
- Email trigger setup wizard capability labels now distinguish read-only, send/reply, and draft-capable Gmail integrations so send-only accounts no longer imply draft support.

## Validation Completed

- `python -m py_compile backend/channels/email/trigger.py backend/services/email_triage_service.py backend/services/trigger_dispatch_service.py backend/api/routes_email_triggers.py backend/scheduler/worker.py`
- `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py`
- `pytest -q -o addopts='' backend/tests/test_trigger_dispatch_service.py backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py`
- `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py backend/tests/test_trigger_dispatch_service.py backend/tests/test_gmail_send_phase3_checkpoint.py`
- Follow-up hardening check: `pytest -q -o addopts='' backend/tests/test_routes_email_triggers.py` -> `10 passed`, including cross-tenant, disconnected, and send-only Gmail triage rejection.
- Phase 3 exit-targeted local bundle after the fail-closed hardening commit: `pytest -q -o addopts='' backend/tests/test_email_trigger_runtime.py backend/tests/test_routes_email_triggers.py backend/tests/test_trigger_dispatch_service.py backend/tests/test_gmail_send_phase3_checkpoint.py backend/tests/test_email_trigger_phase3_live_gate.py` -> `40 passed, 1 skipped`.
- Added root-only live gate scaffold: `pytest -q -o addopts='' backend/tests/test_email_trigger_phase3_live_gate.py` -> skipped by default; set `TSN_RUN_EMAIL_PHASE3_LIVE_GATE=1` after Gmail compose reauthorization to prove live poll, duplicate protection, managed triage draft creation, and MemGuard blocking.
- `cd frontend && ./node_modules/.bin/eslint 'app/hub/triggers/email/[id]/page.tsx' --max-warnings 0`
- `cd frontend && ./node_modules/.bin/eslint components/triggers/EmailTriggerWizard.tsx --max-warnings 0`
- `cd frontend && ./node_modules/.bin/eslint lib/client.ts --max-warnings 0 --rule '@typescript-eslint/no-explicit-any: off' --rule '@typescript-eslint/no-empty-object-type: off'`
- `git diff --check`
- `docker-compose build --no-cache backend frontend && docker-compose up -d backend frontend`
- `docker-compose build --no-cache frontend && docker-compose up -d frontend` after the final setup-wizard wording adjustment
- Exit-gate backend refresh after the fail-closed hardening commit: `docker-compose build --no-cache backend && docker-compose up -d backend`.
- `docker-compose ps` after the refresh showed backend, frontend, postgres, and proxy healthy.
- `docker-compose exec -T backend alembic current` -> `0054 (head)`
- `docker-compose exec -T backend alembic heads` -> `0054 (head)`
- Direct and proxy health checks passed: `http://localhost:8081/api/health`, `https://localhost/api/health`
- Backend log scan over the rebuilt service tail found no `ERROR`, `CRITICAL`, `FATAL`, `Traceback`, or `Exception` lines.
- Browser smoke passed with zero unexpected console/page/network errors. Covered Hub Communication, Email trigger create/detail/pause/resume/delete, setup/detail `gmail.compose` messaging, triage disabled state without compose scope, Wake Events filtering, and Continuous Agents read-only surface. Navigation-aborted Next.js and Hub background requests were filtered as expected route-change noise. Private evidence is under `.private/qa/v0.7.0/phase-3-exit/browser-email-trigger-smoke.json`.

## Remaining Gates

- Run `TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1` after Gmail fixture reauthorization with `gmail.compose`, `gmail.modify`, or `mail.google.com/`.
- Run `TSN_RUN_EMAIL_PHASE3_LIVE_GATE=1` after Gmail fixture reauthorization to record live Email poll proof, duplicate protection, managed triage draft proof, and MemGuard block proof.
- Gmail reauthorization is currently at the human Google sign-in/consent step for the fixture account; do not claim live draft/poll proof until the fixture is re-exported and the live gates pass.
- Fresh-install Ubuntu VM validation remains pending on the documented Parallels path: `bash deploy-to-vm.sh`, SSH to the VM, then `sudo python3 install.py` from `~/tsushin`.

## Evidence References

- `docs/qa/v0.7.0/phase-3-1-gmail-send-checkpoint-summary.md`
- `docs/qa/v0.7.0/track-b-dispatch-foundation-summary.md`
- `docs/qa/v0.7.0/phase-4-track-b-breadth-summary.md`
- `docs/changelog.md` Unreleased Phase 3 and Track B entries
- `docs/documentation.md` sections 2.6, 2.7, 2.12, and 15.5
