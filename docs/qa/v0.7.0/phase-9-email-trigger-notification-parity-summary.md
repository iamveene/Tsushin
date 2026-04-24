# v0.7.0 Phase 9 Email Trigger Notification Parity QA Summary

Date: 2026-04-24

## Scope

- Keep Email setup under Hub → Communication → Triggers.
- Persist the same shared `trigger_criteria` criteria/query/definition envelope for Email triggers that Jira and the other trigger types use.
- Support keyword-style Gmail queries such as `XYZ`, optional JSONPath body matchers, saved query test previews, manual poll-now, and managed WhatsApp notification delivery.
- Preserve existing managed Email Triage draft behavior while adding the WhatsApp notifier as a separate `continuous_subscription.action_config` action.

## Sanitization Notes

- Do not store Gmail OAuth tokens, WhatsApp session material, tenant credentials, or `.env` values in this file.
- Live mailbox samples should be redacted or limited to disposable QA messages.
- Private traces and screenshots belong under `.private/qa/v0.7.0/`.

## Validation Completed

- `python -m pytest -q -o addopts='' backend/tests/test_routes_jira_triggers.py backend/tests/test_routes_email_triggers.py backend/tests/test_email_trigger_runtime.py backend/tests/test_trigger_dispatch_service.py` → `52 passed`.
- `docker-compose exec -T backend python -m pytest -q -o addopts='' tests/test_routes_jira_triggers.py tests/test_routes_email_triggers.py tests/test_email_trigger_runtime.py tests/test_trigger_dispatch_service.py` → `52 passed, 2 warnings` inside the rebuilt backend container.
- `cd frontend && ./node_modules/.bin/eslint 'app/hub/triggers/email/[id]/page.tsx' components/triggers/CriteriaBuilder.tsx components/triggers/EmailTriggerWizard.tsx components/triggers/TriggerBreadthCards.tsx components/triggers/TriggerDetailShell.tsx components/triggers/TriggerSetupModal.tsx components/triggers/TriggerWizard.tsx components/triggers/JiraIssuePreviewList.tsx --max-warnings 0` → clean.
- `docker-compose build --no-cache backend frontend && docker-compose up -d backend frontend` → backend/frontend rebuilt from repo root; backend, frontend, postgres, and proxy healthy.
- Direct and HTTPS-proxy `/api/health` checks returned healthy.
- `docker-compose exec -T backend alembic current` and `docker-compose exec -T backend alembic heads` → `0061 (head)`.
- `PLAYWRIGHT_BASE_URL=https://localhost npm run test:visual` → `6 passed`.
- Direct browser smoke covered Hub Communication, Jira/Email detail notifier inputs, manual poll controls, criteria/test-query controls, and Jira/Email wake-event filters with no console warnings/errors or API/page HTTP failures.
- Browser validation on `/hub/triggers/email/15`:
  - overview displayed the managed Email Agent, Gmail binding, and enabled WhatsApp notifier recipient preview
  - criteria tab showed the Email body keyword helper and shared criteria JSON with `$.message.body_text contains <keyword>`
  - saved test-query returned one sample message with subject/link/preview
  - recent wake events showed the processed `email.message.received` wake event
  - network log was all 200s; console had no errors, only repeated Next.js CSS preload warnings
- `cd frontend && npm run typecheck` remains blocked by pre-existing repo-wide TypeScript debt outside this slice; first failures are in older contacts/projects/flows/playground/watcher/client surfaces.

## Current Evidence

- Backend route coverage verifies Email trigger create/update persistence of `trigger_criteria`, invalid envelope rejection, managed WhatsApp notification subscription creation, action config persistence, and saved query sample previews.
- Backend hardening coverage verifies missing WhatsApp recipients are rejected before notifier creation, corrupt cross-tenant Gmail integration references do not leak foreign account details, criteria-only Email search queries drive Gmail search, and unpadded Gmail base64 bodies decode for previews/body matchers.
- Runtime coverage verifies Gmail search-query polling, cursor suppression, existing triage draft action behavior, WhatsApp notification action behavior, run status updates, and wake-event processed state.
- Dispatch coverage verifies Email keyword criteria can filter or accept payloads through the shared JSONPath criteria evaluator before wake/run creation.
- Live smoke evidence:
  - created a tenant Email trigger with a disposable keyword containing `XYZ`
  - enabled the managed WhatsApp notifier for the existing safe recipient preview
  - sent one self-addressed Gmail smoke message containing the keyword
  - scheduler processed it before manual poll-now, creating wake event `#10` with status `processed`
  - continuous run `#8` finished `succeeded` with `email_whatsapp_notification.success=true`
  - two follow-up poll-now calls returned the already-cursored message as skipped and created no duplicate run
