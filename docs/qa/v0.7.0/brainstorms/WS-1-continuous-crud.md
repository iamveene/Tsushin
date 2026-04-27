# WS-1: Continuous-Agent CRUD — Implementation Blueprint

**Date:** 2026-04-24
**Branch:** release/0.7.0
**Status:** Design only

---

## 1. Modal Flow Design: Chosen Approach

### Option A — Single-step modal + separate Subscription panel (CHOSEN)

A single `ContinuousAgentSetupModal` collects the four top-level agent fields (name, agent_id, execution_mode, policy refs) and saves in one call. Subscriptions are managed afterward in a dedicated `SubscriptionEditor` panel rendered inside the detail page (`/continuous-agents/[id]`). The same modal is reused for edit, pre-populated with existing values.

**Rationale for choosing A over B:**
- The trigger wizard pattern exists to navigate the user through a type-selection step before reaching config. Continuous agents have no type-selection step. A multi-step wrapper would add navigation chrome with no user benefit.
- `ContinuousSubscription` has its own lifecycle (add/remove while the agent already exists). Embedding subscription management into the creation wizard creates a long-lived half-saved state.
- Shipping A keeps the diff small, matches the existing `TriggerSetupModal` single-step pattern for Jira/Schedule/GitHub.

---

## 2. Backend Endpoint Shapes

All new routes attach to the existing `router` in `backend/api/routes_continuous.py` and use `write_agents_caller = _continuous_caller_dependency("agents.write")`.

### POST `/api/continuous-agents`

```
Request: ContinuousAgentCreate
  name:                Optional[str]         max_length=128, strip whitespace
  agent_id:            int                   required, ge=1
  execution_mode:      str = "hybrid"        in {"autonomous","hybrid","notify_only"}
  delivery_policy_id:  Optional[int]         ge=1
  budget_policy_id:    Optional[int]         ge=1
  approval_policy_id:  Optional[int]         ge=1
  status:              str = "active"        in {"active","paused","disabled"}

Response: ContinuousAgentRead   HTTP 201
```

Validation:
1. Confirm `agent_id` row exists and `agent.tenant_id == caller.tenant_id` (404 if not, 422 if cross-tenant).
2. Confirm policy IDs each belong to the tenant when provided (`_load_policy_or_403`).
3. Reject `status="error"` on create.
4. `is_system_owned` always `False` on user-created agents — never accepted from request body.

### PATCH `/api/continuous-agents/{id}`

```
Request: ContinuousAgentUpdate  (all fields Optional)
  name, execution_mode, delivery_policy_id, budget_policy_id, approval_policy_id, status

Response: ContinuousAgentRead   HTTP 200
```

Guard: if `row.is_system_owned`, reject `status="disabled"` (allow `"paused"`); block agent_id changes (not in Update schema). Use `payload.model_dump(exclude_unset=True)`.

### DELETE `/api/continuous-agents/{id}`

```
Response: HTTP 204 (or HTTP 409 if pending wake events without ?force=true)
```

Sequence:
1. `_load_owned_or_forbidden`.
2. If `row.is_system_owned`, HTTP 403.
3. Check `pending`/`claimed` WakeEvents for this agent. If any, HTTP 409 unless `?force=true`. On force, set those rows to `status="filtered"` first.
4. Explicitly delete child `ContinuousSubscription` rows first (no DB cascade).
5. `db.delete(row)` — `ContinuousRun` cascades; `WakeEvent.continuous_agent_id` SET NULL.

### POST `/api/continuous-agents/{id}/subscriptions`

```
Request: ContinuousSubscriptionCreate
  channel_type:          str             max_length=32
  channel_instance_id:   int             ge=1
  event_type:            Optional[str]   max_length=64
  delivery_policy_id:    Optional[int]
  action_config:         Optional[dict]
  status:                str = "active"  in {"active","paused"}

Response: ContinuousSubscriptionRead   HTTP 201
```

Validation:
1. Parent agent ownership.
2. `_validate_channel_instance(db, tenant_id, channel_type, channel_instance_id)` dispatches against the right instance table; HTTP 400 on miss.
3. Dedupe: `(continuous_agent_id, channel_type, channel_instance_id, event_type)` unique → HTTP 409 on conflict.

### PATCH `/api/continuous-agents/{id}/subscriptions/{sub_id}`

Same nested-ownership check; system-owned subs block status="disabled".

### DELETE `/api/continuous-agents/{id}/subscriptions/{sub_id}`

System-owned subs return HTTP 403.

### GET `/api/continuous-agents/{id}/subscriptions`

New paginated list endpoint so the detail page can populate `SubscriptionEditor` independently.

### ContinuousSubscriptionRead shape (new)

```
id, tenant_id, continuous_agent_id, channel_type, channel_instance_id,
event_type, delivery_policy_id, action_config, status, is_system_owned,
created_at, updated_at
```

---

## 3. Edge Cases

**System-owned protection** (`is_system_owned=True`):
- DELETE: hard block, HTTP 403.
- PATCH agent: allow name/execution_mode/delivery; block `status="disabled"` (paused OK); block `agent_id`.
- PATCH sub: allow `delivery_policy_id`, `action_config`; block `status="disabled"`.

**Status transitions:** Accept any of `{"active","paused","disabled"}` from PATCH. `error` is runtime-only; user writes return 422. No FSM enforcement — operators must be able to un-pause/un-error agents directly.

**Pending wake events on delete:** Default 409. With `?force=true`, set their status to `"filtered"` and `continuous_agent_id=NULL` to prevent watcher pickup of an orphan reference.

**Subscription cascade:** No DB-level cascade exists on `continuous_subscription`. Add `cascade="all, delete-orphan"` on the ORM relationship AND keep the explicit pre-delete in the handler (belt-and-suspenders). ORM-only change, no migration.

---

## 4. Files to Create / Modify

**Backend**
- Modify `backend/api/routes_continuous.py` — remove deferred-write docstring (lines 1–6), add `write_agents_caller`, add 5 new schemas, add `_load_policy_or_403` and `_validate_channel_instance` helpers, add 7 new route handlers (POST/PATCH/DELETE agent + GET/POST/PATCH/DELETE sub).
- Modify `backend/services/continuous_agent_service.py` — add `validate_channel_instance`, `create_continuous_agent`, `delete_continuous_agent` helpers.
- Modify `backend/models.py` — add `cascade="all, delete-orphan"` to `ContinuousAgent.subscriptions` relationship.
- Create `backend/tests/test_routes_continuous_crud.py` — 14 cases (see Section 5).

**Frontend**
- Modify `frontend/lib/client.ts` — add types `ContinuousAgentCreate`, `ContinuousAgentUpdate`, `ContinuousSubscription{Create,Update,Read}`. Add 7 client methods near line 4384.
- Create `frontend/components/continuous-agents/ContinuousAgentSetupModal.tsx` — single-step modal, reused for create/edit.
- Create `frontend/components/continuous-agents/SubscriptionEditor.tsx` — inline panel for detail page.
- Modify `frontend/app/continuous-agents/page.tsx` — remove banner (lines 120–122); add Create button at line ~109; add edit/delete affordances on each card.
- Modify `frontend/app/continuous-agents/[id]/page.tsx` — add edit/delete actions; render `SubscriptionEditor`.

---

## 5. Test Seams (14 pytest cases)

Same in-memory SQLite + tenant fixture as `test_continuous_control_plane_phase2.py:82–107`. Stub docker/argon2 as in `test_routes_email_triggers.py:18–38`.

1. `create_happy_path` — POST valid → 201, `is_system_owned=False`, `status="active"`.
2. `create_cross_tenant_agent_id` — agent_id from another tenant → 422/404.
3. `create_invalid_execution_mode` — bad enum → 422.
4. `create_status_error_rejected` → 422.
5. `patch_partial_update` — only `name` changes; `updated_at` advances.
6. `patch_system_owned_disable_blocked` → 403.
7. `delete_happy_path` → 204; subscriptions deleted; runs cascaded; wake events SET NULL.
8. `delete_system_owned_blocked` → 403.
9. `delete_pending_wake_events_409` → 409 with `count`.
10. `delete_pending_wake_events_force` → 204; wake events `status="filtered"`, agent_id NULL.
11. `subscription_create_happy_path` → 201.
12. `subscription_create_dedupe` → second call 409.
13. `subscription_create_wrong_channel_instance` → 400.
14. `subscription_delete_system_owned_blocked` → 403.

---

## 6. Build Sequence

1. **Backend writes:** schemas + helpers + 7 handlers in `routes_continuous.py`; ORM cascade in `models.py`; service helpers.
2. **Backend tests:** `pytest backend/tests/test_routes_continuous_crud.py -v` until green.
3. **Frontend client:** types + 7 methods in `lib/client.ts`.
4. **UI components:** `ContinuousAgentSetupModal.tsx`, `SubscriptionEditor.tsx`.
5. **Pages:** modify list and detail.
6. **Rebuild:** `docker-compose build --no-cache backend frontend && docker-compose up -d backend frontend`.
7. **QA:** browser sweep create→edit→delete; cross-tenant 403 via API; pending-wake-event 409.
8. **Docs + commit.**

---

## 7. Critical Details

- Cross-tenant FK violations → 403; missing parent → 404; bad input → 400; enum violations → 422.
- `_validate_channel_instance` dispatch: `{"email": EmailChannelInstance, "jira": JiraChannelInstance, "schedule": ScheduleChannelInstance, "github": GitHubChannelInstance, "webhook": WebhookIntegration, "whatsapp": WhatsAppMCPInstance}`. Unknown channel_type → 400.
- Modal state: `useReducer` for 7 fields + 2 async loading states; reset on `isOpen` flip (mirrors `TriggerSetupModal.tsx:114`).
- `action_config` JSON: validate max 64KB via Pydantic model validator (anti-stuffing).
- **No migration needed** — all tables/columns exist in migration `0047`. ORM cascade is Python-only.
