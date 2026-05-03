# Bug-Fix Browser Validation — Evidence

**Run:** 2026-05-03
**Tester:** qa-tester (post-fix validation)
**Counts:** PASS=4 FAIL=1 BLOCKED=0 SKIP=0

## Evidence Table

| ID | Fix | Scenario | Status | Notes | Evidence |
|---|---|---|---|---|---|
| V-001 | A1-001 | Tour pill survives reload | FAIL | localStorage `tsushin_onboarding_minimized:1=true` IS persisted by `minimize()` and survives reload, but on rehydrate the wizard renders the FULL MODAL (Step 1 of 16, "Welcome to Tsushin!"), NOT the "Continue Tour" pill. After reload: `pillCount=0`, modal visible at full size, `Continue Tour` text NOT in DOM. The persistence half of the fix works (localStorage write/read), but the React state rehydrate at `OnboardingContext.tsx:233-237` does not produce a visible minimized state. See bug file. | v001-after-reload.png |
| V-002 | A1-001 | Tour dismiss survives reload | PASS | Clicked X close on wizard. localStorage cleared `started`/`minimized` keys, set `tsushin_onboarding_completed:1=true`. After reload: no pill, no wizard, completed flag persists, `pillCount=0`, `wizardVisible=false`. | DOM scan |
| V-003 | A4-002 | Error message readable not [object Object] | PASS | Submitted Daily Email Digest template (qa070-fix-test, agent=Tsushin, channel=Playground, recipient=+15551234567, time=08:00, tz=America/Sao_Paulo, max=20). Backend returned 400. Error rendered: `"Template 'daily_email_digest' requires credentials that are not configured for this tenant: gmail. Configure them in Settings → Integrations, or pass skip_credential_check: true in params to bypass this check."` NO `[object Object]` substring anywhere in DOM. Fix in `client.ts handleApiError` extracts `data.detail.message` correctly. | v003-error-toast.png + DOM regex scan |
| V-004 | Tour content | New v0.7.0 bullets visible in steps 5/10/12/15 | PASS | Bundled JS (`/app/.next/static/chunks/*.js` + `/app/.next/server/chunks/820.js`) contains all 5 keyword strings: `pluggable embedding providers` (1 chunk), `12 step types` (1 chunk), `Whisper` (8 chunks), `Memory Recap` (4 chunks), `system-managed auto-flow` (1 chunk). Visual confirmation of step 5: rendered bullets include "NEW in v0.7.0: pluggable embedding providers — OpenAI text-embedding-3 (256/512/1024/1536d), Google Gemini embedding-2 (768/1536/3072d), and self-hosted Ollama; legacy MiniLM-L6-v2 still ships as the default" and "NEW in v0.7.0: per-surface embedding contracts". | v004-step5-content.png + grep |
| V-005 | Smoke | No new console errors after rebuild | PASS | Total console errors during run: 1 (intentional — the 400 from V-003 testing the `[object Object]` fix). All other errors in `browser_console_messages all=true` are stale from prior sessions (422 from earlier template attempts, 404 for deleted flow 116, 404 for old playground thread 410). The rebuilt frontend introduces no new error patterns. The serving footer reads `tsn-core v0.7.0`. | console scan |

## Console / Network Errors

Only intentional error during run: `400 https://localhost/api/flows/templates/daily_email_digest/instantiate` — this is the test condition for V-003 (Gmail integration not configured). All `[ERROR]` lines from the cumulative session log are pre-existing stale failures (422s for malformed earlier requests, 404s for deleted resources). No new error patterns attributable to the wave-FIX changes.

## Cleanup Confirmation

- DB query `SELECT id, name FROM flow_definition WHERE name LIKE 'qa070-%'` → 0 rows (no test flow persisted; instantiate failed before commit).
- `tsushin_onboarding_*` localStorage keys cleared at end of run.
- No extra browser tabs / sessions left open.

## Retry after re-fix

| ID | Fix | Scenario | Status | Notes | Evidence |
|---|---|---|---|---|---|
| V-001-r2 | A1-001 (re-fix) | Tour pill survives reload after startTour persistence patch | PASS | After Minimize at step 7, localStorage has both `tsushin_onboarding_started:1=true` and `tsushin_onboarding_minimized:1=true`. After full page reload (https://localhost/), pill "Continue Tour" is still visible bottom-right; full Welcome modal NOT shown. Both keys persisted across reload. Minor: pill counter resets to "(1/16)" instead of preserving "(7/16)" — out of scope for this regression (tour step persistence is a separate concern from minimize survival). | v-001-r2-pill-after-reload.png |
