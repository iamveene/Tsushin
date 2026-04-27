# v0.7.0 Phase 9 Jira Trigger Finalization QA Summary

Date: 2026-04-24

## Scope

- Finalize Jira triggers from setup/test-query/normalization into live JQL polling.
- Prove once-per-issue dedupe so repeated polls do not create duplicate wake events or continuous runs.
- Validate the managed WhatsApp notifier path for Jira issue events.
- Keep Jira credentials UI-managed under Hub → Tool APIs, encrypted at rest, and represented only by masked previews in API/UI output.
- Preserve Hub → Communication → Triggers placement for Jira trigger rows; WhatsApp remains a conversational channel used only for outbound notification delivery.

## Required Validation

- Backend: active Jira trigger poll fetches matching JQL issues, normalizes payloads, dispatches wake evidence, and updates cursor/activity state.
- Backend: duplicate polling or later updates of the same issue record duplicate/dedupe behavior without creating a second wake/run or a second WhatsApp notification.
- Backend: missing, paused, or cross-tenant WhatsApp notifier configuration fails closed.
- Backend: Jira API tokens are encrypted in storage and never returned from read endpoints beyond masked preview fields.
- Browser: Hub Tool APIs supports Jira credential entry/edit/test-query, while Hub Communication Jira trigger setup/detail supports selecting an existing Jira connection, test-query, active/paused state, wake-event evidence, and any exposed poll-now/manual proof action.
- Browser: managed notifier success, empty state, and error state render without console errors or failed unexpected network requests.

## Validation Completed

- `python -m pytest -q -o addopts='' backend/tests/test_routes_jira_triggers.py backend/tests/test_routes_email_triggers.py backend/tests/test_email_trigger_runtime.py backend/tests/test_trigger_dispatch_service.py` -> `52 passed`.
- `docker-compose build --no-cache backend frontend && docker-compose up -d backend frontend` -> backend/frontend rebuilt from the repository root without tearing down the stack.
- `docker-compose exec -T backend python -m pytest -q -o addopts='' tests/test_routes_jira_triggers.py tests/test_routes_email_triggers.py tests/test_email_trigger_runtime.py tests/test_trigger_dispatch_service.py` -> `52 passed, 2 warnings`.
- Direct/proxy health checks returned healthy; `docker-compose exec -T backend alembic current` and `docker-compose exec -T backend alembic heads` both reported `0062 (head)` after the Jira Tool APIs credential migration.
- The Jira Tool API migration backfilled the existing live trigger credentials into tenant-scoped Jira integration `#11`; API and DB verification showed the site URL, auth email, and masked token preview only.
- Browser validation on Hub → Tool APIs showed the migrated Questrade Jira connection card, health/test metadata, edit modal fields for site URL/auth email/API token rotation, and stored test-query success. Browser validation of Jira trigger creation showed the wizard selecting the existing Jira connection instead of collecting credentials inline.
- `PLAYWRIGHT_BASE_URL=https://localhost npm run test:visual` -> `6 passed`.
- Direct browser smoke covered Hub Communication, Jira detail notifier input, manual Poll Now controls, criteria/test-query controls, Email detail notifier/poll/criteria controls, and Jira/Email wake-event filters. No console warnings/errors or API/page HTTP failures were observed; benign Next.js `_rsc` prefetch aborts were filtered.
- Live Jira saved-query test for `project = JSM AND statusCategory != Done AND type = "Pen Test"` returned two sample issues, including `JSM-193570` and `JSM-189100`.
- Browser validation on `/hub/triggers/jira/4`:
  - overview displayed the normalized Jira site root, active status, healthy health, default `Jira Agent`, masked WhatsApp recipient preview, and active notification subscription `#8`
  - overview displayed a Jira connection link back to Hub → Tool APIs for credential edits
  - criteria tab displayed the exact saved JQL and shared criteria JSON
  - test-query returned two issue previews, including `JSM-193570`, with link, type, status, title, updated timestamp, and short description preview
  - recent wake events tab showed processed `jira.issue.detected` wake events `#12` and `#11`
  - manual Poll Now returned `Status: ok` with `Processed 0 issue(s), emitted 0 wake event(s)` after dedupe had already processed the two matching issues
  - network log was all 200s; console had no errors, only repeated Next.js CSS preload warnings

## Current Evidence

- Live trigger `#4` was created for tenant `tsushin-qa` with the UI-provided Jira base URL normalized from trailing `/jira` input to the canonical Jira site root.
- The saved JQL remained exactly user-authored: `project = JSM AND statusCategory != Done AND type = "Pen Test"`.
- Jira API token storage was verified as encrypted-at-rest with only a masked `api_token_preview` returned by API reads; plaintext token output was not present in the trigger read evidence.
- The managed notifier created/reused the system-owned notification path:
  - normal default agent: `Jira Agent`
  - continuous subscription: `#8`, `event_type = jira.issue.detected`, `action_config.action_type = whatsapp_notification`
  - recipient is supplied by the operator/UI, stored for runtime dispatch, and shown publicly only as a masked preview
- Production code no longer defaults to a hard-coded WhatsApp recipient; omitted notifier recipients are rejected with HTTP 400 before any subscription is created.
- The first live scheduler poll processed the existing matching issues:
  - wake event `#12`: `jira_issue:JSM-193570`, status `processed`
  - wake event `#11`: `jira_issue:JSM-189100`, status `processed`
  - continuous runs `#10` and `#9`: status `succeeded`, each with `jira_whatsapp_notification.success = true`
- Two follow-up manual poll-now calls found the same two matching Jira issues and returned duplicate dispatch statuses, creating no additional wake events, continuous runs, or WhatsApp sends.
- The Jira Cloud REST call now uses the current enhanced JQL search endpoint `/rest/api/3/search/jql`; the previous `/rest/api/3/search` endpoint returned HTTP 410 during live validation.

## Sanitization Notes

- Do not paste Jira API tokens, WhatsApp session material, webhook secrets, tenant credentials, or `.env` values into this file.
- If live Jira evidence is captured, keep external credentials and site/account identifiers redacted. This release summary records issue keys only because `JSM-193570` is the explicit acceptance target for the Jira trigger smoke.
- Store private traces and screenshots under `.private/qa/v0.7.0/`; keep this public summary credential-free.

## Current Documentation State

- `docs/changelog.md` records Jira finalization as validated release work, including the live JQL endpoint fix, managed notifier proof, and duplicate suppression evidence.
- `docs/documentation.md` distinguishes Track B breadth from the final live-polling/notifier contract.
- `README.md` summarizes v0.7.0 channels-vs-triggers placement and points here for the sanitized evidence.
