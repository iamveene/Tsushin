# Wave A4 — Bugs

## BUG-QA070-A4-001 — Template instantiation fails with `Missing required parameter: name`

**Severity:** High
**Page/Feature:** Flows / Create Flow from Template (Daily Email Digest)
**Endpoint:** `POST /api/flows/templates/daily_email_digest/instantiate`

**Repro:**
1. UI: `/flows` → "From Template" → pick "Daily Email Digest"
2. Fill all required fields: Flow name `qa070-flow-template-1`, Agent `Tsushin (id=1)`, Channel `playground`, Recipient `+15551234567`, Time `08:00`, Timezone `America/Sao_Paulo`, Max emails `20`
3. Click Preview → Create Flow

**Expected:** Flow saves and lands in `/flows` list.
**Actual:** API returns `422 {"detail":"Missing required parameter: name"}`. Modal shows error rendered as `[object Object]` (also a UI bug — see BUG-QA070-A4-002).

**Verified the API rejects multiple body shapes** (top-level `name`, top-level `flow_name`, `parameters.name`, etc.), all 422 same message. Either the template registry expects a different parameter key (e.g., `flow_name` mapped to a `name` parameter inside template definition), or the route validator is broken.

## BUG-QA070-A4-002 — Error toast renders as `[object Object]`

**Severity:** Medium
**Page/Feature:** Flows / Template Wizard error display
**Repro:** trigger any failed `/instantiate` (see BUG-QA070-A4-001). Error banner inside modal shows literal text `[object Object]` instead of `error.detail`.

**Expected:** human-readable message from API (`"Missing required parameter: name"`).
**Actual:** stringified object.
