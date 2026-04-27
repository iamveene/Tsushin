# v0.7.0 Track B Dispatch Foundation QA Summary

Date: 2026-04-24
Branch: `mv/v0.7.0-track-b-dispatch-foundation` merged into `release/0.7.0`

## Scope

This checkpoint starts Track B with a shared trigger dispatch foundation only. It does not add Jira, Schedule, or GitHub trigger instance migrations.

The slice adds a reusable trigger dispatch path for future trigger adapters, preserves existing signed webhook queue behavior, writes dedupe/wake/run evidence for matching continuous-agent subscriptions, and keeps trigger payload content out of API rows by storing only `payload_ref`.

## Validation

- Local focused tests in the Track B worktree:
  - `python -m pytest -q -o addopts='' backend/tests/test_trigger_dispatch_service.py backend/tests/test_webhook_trigger_dispatch_foundation.py` -> `11 passed`
  - `python -m pytest -q -o addopts='' backend/tests/test_trigger_dispatch_service.py backend/tests/test_webhook_trigger_dispatch_foundation.py backend/tests/test_channel_trigger_split.py backend/tests/test_phase0_foundation.py backend/tests/test_continuous_control_plane_phase2.py backend/tests/test_routes_email_triggers.py backend/tests/test_default_agent_service.py` -> `43 passed`
  - `python -m py_compile backend/services/trigger_dispatch_service.py backend/api/routes_webhook_inbound.py backend/channels/types.py backend/tests/test_trigger_dispatch_service.py backend/tests/test_webhook_trigger_dispatch_foundation.py` -> passed
  - `git diff --check` -> clean
- Integrated root validation after merge:
  - `python -m pytest -q -o addopts='' backend/tests/test_trigger_dispatch_service.py backend/tests/test_webhook_trigger_dispatch_foundation.py backend/tests/test_channel_trigger_split.py backend/tests/test_phase0_foundation.py backend/tests/test_continuous_control_plane_phase2.py backend/tests/test_routes_email_triggers.py backend/tests/test_default_agent_service.py` -> `43 passed, 383 warnings`
  - `./node_modules/.bin/eslint app/hub/wake-events/page.tsx --max-warnings 0` -> passed
  - `docker-compose up -d --build --no-cache backend` was attempted first from the repository root; this compose version does not support `--no-cache` on `up`, so the root-safe equivalent `docker-compose build --no-cache backend && docker-compose up -d backend` was used.
  - Backend no-cache rebuild completed; backend, frontend, postgres, and proxy containers were healthy.
  - Direct `http://localhost:8081/api/health` and HTTPS `https://localhost/api/health` returned healthy.
  - `docker exec tsushin-backend alembic current` -> `0058 (head)`; `docker exec tsushin-backend alembic heads` -> `0058 (head)`.
  - Backend log scan over the latest 300 lines found no `ERROR`, `CRITICAL`, `FATAL`, `Traceback`, or `Exception` entries.
  - Live API smoke passed for `/api/triggers`, `/api/wake-events`, `/api/continuous-runs`, signed webhook inbound, duplicate signed webhook inbound, payload redaction, and cross-tenant wake detail denial. The duplicate webhook returned the same queue id (`45`), and the temporary wake/run evidence was cleaned up afterward.
  - Browser smoke covered Hub Communication, `/hub/wake-events`, `/continuous-agents`, webhook trigger detail, email trigger detail, and Watcher Dashboard with 0 console errors, 0 page errors, 0 failed requests, and 0 HTTP 4xx/5xx responses after filtering benign aborted Next.js `_rsc` prefetches.

## Residual Risks

- Jira, Schedule, and GitHub adapter tables/wizards are deferred until the foundation is validated.
- Webhook trigger criteria storage is deferred; this slice uses existing trigger/subscription contracts only.
- Gmail live send/Sent-folder proof remains blocked until OAuth is reauthorized with a compose-capable scope.
