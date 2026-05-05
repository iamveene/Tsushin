# v0.7.0 Full-Validation — Bug Ledger

Bugs surfaced during the QA campaign on 2026-05-03. Format compatible with root `BUGS.md` for next-session triage.

**Total: 4 bugs (2 high, 2 medium).**

---

### BUG-QA070-A1-001 — Onboarding tour minimized pill not visible after page reload

- **Severity:** medium
- **Category:** wizards
- **Surface:** `frontend/components/OnboardingWizard.tsx`, post-login dashboard
- **Repro steps:**
  1. Login as `test@example.com` with fresh tour state (clear `localStorage.onboarding:tour:*`)
  2. Walk to step 7 of the 16-step tour
  3. Click the minimize button → confirm pill is visible in the corner
  4. Reload the page (F5)
- **Expected:** Minimized "Continue tour" pill remains visible in the corner after reload (state persists across navigation).
- **Actual:** No pill visible after reload — tour appears fully closed despite minimized state being set.
- **Evidence:** `screenshots/W-002-minimized-step7.png` (minimized pre-reload), `screenshots/W-002-after-reload.png` and `screenshots/W-002-FAIL-no-pill-after-reload.png` (post-reload — pill missing).
- **Reported by:** Wave A1
- **Suggested fix area:** Hydration of `onboarding:tour:minimized` localStorage key in OnboardingWizard mount effect. Likely the mount logic checks `dismissed` flag but not `minimized`, so a minimized-but-not-dismissed tour falls through to "hide entirely".

---

### BUG-QA070-A4-001 — Template instantiation always returns `422 Missing required parameter: name`

- **Severity:** **high**
- **Category:** flows / templates
- **Surface:** `POST /api/flows/templates/{template_id}/instantiate` (`backend/api/routes_flows.py`, `backend/services/flow_template_seeding.py`)
- **Repro steps:**
  1. Open `/flows` → "From Template" → pick "Daily Email Digest"
  2. Fill all required parameters: name `qa070-flow-template-1`, agent (id=1), channel `playground`, recipient `+15551234567`, time `08:00`, timezone `America/Sao_Paulo`, max emails `20`
  3. Click Preview → Create Flow
- **Expected:** Flow instance saves and lands in `/flows` list.
- **Actual:** API returns `422 {"detail":"Missing required parameter: name"}`. qa-tester verified that **multiple body shapes were rejected with the same error** (top-level `name`, top-level `flow_name`, `parameters.name`). Likely affects ALL 5 built-in templates since the failure is in the route/service-layer parameter validation, not template-specific.
- **Evidence:** `wave_A4_bugs.md` (qa-tester's investigation log)
- **Reported by:** Wave A4
- **Suggested fix area:** `backend/api/routes_flows.py` instantiate handler — the parameter-name lookup likely expects a different key than what the UI sends. Check whether the template definition's `params_schema` declares `name` as a required field but the route validator parses from the wrong location in the request body.
- **Blocks:** ALL "From Template" flow creation paths.

---

### BUG-QA070-A4-002 — Error toast renders as `[object Object]` instead of error.detail

- **Severity:** medium
- **Category:** flows / wizard UI
- **Surface:** Flow template wizard error handler (frontend)
- **Repro steps:** Trigger any failed `/api/flows/templates/.../instantiate` (e.g. via BUG-QA070-A4-001 above).
- **Expected:** Human-readable message like `"Missing required parameter: name"` (the API's `error.detail` string).
- **Actual:** Modal/toast shows literal `[object Object]`.
- **Evidence:** observed during BUG-QA070-A4-001 reproduction.
- **Reported by:** Wave A4
- **Suggested fix area:** The frontend error handler is doing `err.toString()` or template-string interpolating an Axios error object. Should pull `err.response?.data?.detail` (or wherever the API error message lives in the client lib).
- **Blast radius:** Likely affects every flow wizard error display, not just the template path.

---

### BUG-QA070-WC-001 — Trigger deletion does NOT cascade to system-managed auto-flows or bindings

- **Severity:** **high**
- **Category:** flows / triggers / DB FK
- **Surface:** `flow_binding_service.py` (or DB FK constraints on `flow_trigger_binding.trigger_instance_id` polymorphic FK), trigger DELETE handlers in `backend/api/routes_email_triggers.py` / `routes_jira_triggers.py` / `routes_github_triggers.py` / `routes_webhook_instances.py`
- **Repro steps:**
  1. Create a Webhook trigger via UI (`qa070-webhook-1` → DB row `webhook_integration` id=12)
  2. v0.7.0 Wave 4 logic auto-creates `flow_definition` row (id=114, name='Webhook: qa070-webhook-1', `is_system_owned=true`), 4 child `flow_node` rows (289-292), and `flow_trigger_binding` row (id=24, `is_system_managed=true`).
  3. Delete the trigger row: `DELETE FROM webhook_integration WHERE integration_name='qa070-webhook-1';` → returns DELETE 1.
  4. Same for an Email trigger (`qa070-email-1`, id=22 → auto-flow 115, nodes 293-296, binding 25).
- **Expected (per AF-009 design contract in plan + per `flow_binding_service.py` documentation):** Deleting the trigger cascade-deletes the system-managed auto-flow, all its nodes, and its `flow_trigger_binding` row. UI promises this with a "cascade banner" before delete.
- **Actual:** All 14 child rows (2 flow definitions + 8 flow nodes + 2 bindings + 2 trigger rows = NOT cascaded; only the trigger row itself deleted). After cleanup attempt, `SELECT COUNT(*) FROM flow_definition WHERE id IN (114,115)` returned 2 (orphaned). Required manual `DELETE FROM flow_node WHERE flow_definition_id IN (...)`, `DELETE FROM flow_trigger_binding ...`, `DELETE FROM flow_definition ...` to clean up.
- **Evidence:** `wave_C_cleanup_evidence.md` (DELETE/SELECT trace), `wave_B1_evidence.md` AF-009 row.
- **Reported by:** Wave C cleanup audit
- **Suggested fix area:** Two possible causes —
  1. **Application-layer cascade:** the trigger DELETE handler in `routes_*_triggers.py` should call into `flow_binding_service` to remove the system-managed flow before deleting the trigger row. If this orchestration exists, it didn't fire because the test bypassed the API and went direct to DB DELETE. Recommendation: also add cascade enforcement at the DB layer.
  2. **DB FK constraint:** `flow_trigger_binding.trigger_instance_id` is a polymorphic FK (kind+instance_id pair, not a single ON DELETE FK). PostgreSQL can't natively cascade a polymorphic relation. Recommend either trigger functions per trigger table or moving cascade orchestration to the app layer with a "force_cascade" UI confirmation.
- **Blast radius:** Any tenant cleaning up old triggers could leave orphaned auto-flows behind, accumulating cruft and potentially confusing the UI. Production users likely use the UI delete (which probably DOES cascade via the route handler) — but if anyone uses direct DB cleanup or restore-from-backup paths, this hits.
- **Blocks:** Clean uninstall / tenant offboarding.

---

## Pre-existing bugs verified during this campaign

| Pre-existing bug | Status from this campaign |
|---|---|
| BUG-QA-KB-001 (Project KB UI parity gap) | **Likely closed** — qa-tester (Wave A2) verbally reported "Project KB clearly shows full embedding contract controls". No screenshot captured for independent confirmation. Recommend visual reconfirmation in next smoke. |
| BUG-QA-KB-002 (LTM dim picker missing) | **Status unknown** — Wave A2 timed out before reaching Memory Management section. Re-test in next smoke. |
