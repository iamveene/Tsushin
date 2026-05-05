# v0.7.0 Phase 8 UI Polish QA Summary

Date: 2026-04-24
Branch: `release/0.7.0`

## Scope

Phase 8 completed the trigger/control-plane UI polish wave:

- Trigger detail and criteria polish for Email, Webhook, Jira, Schedule, and GitHub.
- Channel routing-rule UI with modal create/edit/delete plus reorder.
- Wake-event browser and continuous-run watcher cause polish.
- Shared `<Wizard>` retrofit for Slack, Discord, WhatsApp, and MCP setup flows.
- Onboarding step 16 copy, Webhook deprecation absence, and Kokoro/Ollama legacy hygiene docs.

## Programmatic Validation

- Local focused backend tests:
  - `python -m pytest -q -o addopts='' backend/tests/test_continuous_control_plane_phase2.py`
  - Result: `9 passed, 247 warnings in 0.61s`
- Container focused backend tests:
  - `docker-compose exec -T backend python -m pytest -q -o addopts='' tests/test_continuous_control_plane_phase2.py`
  - Result: `9 passed, 2 warnings in 0.72s`
- Targeted frontend ESLint:
  - Trigger criteria/detail/setup files, routing rules panel, wake events, continuous-agent detail, watcher tabs, Slack/Discord/WhatsApp/MCP wizards, onboarding, and visual entrypoints.
  - Result: passed with `--max-warnings 0`.
- Syntax/check hygiene:
  - `git diff --check` passed.
  - `python -m py_compile backend/api/routes_continuous.py backend/api/routes_channel_event_rules.py` passed locally and in the backend container.

## Rebuild and Stack Validation

- Required no-cache root rebuild was executed as the compose-compatible two-step equivalent:
  - `docker-compose build --no-cache backend frontend`
  - `docker-compose up -d backend frontend`
- `docker-compose ps` showed backend, frontend, postgres, and proxy healthy.
- Direct backend health passed: `curl -fsS http://localhost:8081/api/health`.
- HTTPS proxy health passed: `curl -kfsS https://localhost/api/health`.
- Alembic check passed: `current` and `heads` both reported `0055 (head)`.

## Browser and Visual Validation

- Visual regression suite:
  - `PLAYWRIGHT_BASE_URL=https://localhost npm run test:visual`
  - Result: `6 passed`.
- Phase 8 browser evidence:
  - Broad smoke artifact: `.private/qa/v0.7.0/phase-8/browser-smoke/browser-smoke-summary.txt`
  - Follow-up artifact: `.private/qa/v0.7.0/phase-8/browser-smoke/browser-smoke-followup-summary.txt`
  - Screenshots: `.private/qa/v0.7.0/phase-8/browser-smoke/*.png`
- Covered flows:
  - Login and Hub Communication.
  - Slack, Discord, WhatsApp, and MCP shared setup wizards.
  - Routing rule create, edit, delete, and reorder on a temporary Slack integration, with cleanup.
  - `/hub/wake-events` date filters and empty-state/payload-panel layout.
  - `/continuous-agents` list; no continuous-agent detail row existed in this fixture.
  - Webhook trigger detail and criteria template/test path.
  - Onboarding steps 15 and 16.
- Browser notes:
  - Broad smoke reached the routing/wake/wizard surfaces and failed only on a strict Playwright selector for the Webhook criteria `Template` button after the page was already loaded. A targeted follow-up with exact button selection passed Webhook criteria and onboarding with 0 console errors, 0 page errors, 0 request failures, and 0 HTTP errors.
  - The broad run recorded only `net::ERR_ABORTED` route-change/no-content aborts and no HTTP 4xx/5xx responses.

## Known Remaining Risks

- Full frontend `npm run typecheck` remains blocked by pre-existing repo-wide TypeScript debt outside Phase 8. First failures are in older contacts, project, flows, watcher graph, and client type surfaces.
- Fresh-install Ubuntu VM validation is still blocked on external sudo access and remains a Phase 9 release blocker.
- Optional API-agent Gmail send proof remains deferred until API token/agent env vars are available.
