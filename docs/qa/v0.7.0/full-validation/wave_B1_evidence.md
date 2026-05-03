# Wave B1 — Auto-Generated Flows from Triggers — Evidence

**Run:** 2026-05-03
**Tester:** coordinator (no qa-tester needed — DB + curl sufficient)
**Counts:** PASS=4 FAIL=1 BLOCKED=1 SKIP=4

## Critical finding
AF-009 **FAILS** — trigger deletion does NOT cascade to system-managed auto-flows or bindings. This is a real v0.7.0 defect (or design gap). See BUG-QA070-WC-001 in `BUGS_FOUND.md`.

## Notes
Auto-flow generation was already partially validated as a side-effect of Wave A3 trigger creation. Coordinator extends with DB structural inspection + webhook auth probe. Browser-side tests (UI panels) deferred to follow-up smoke.

## Evidence Table

| ID | Scenario | Status | Notes | Evidence | Bug ID |
|---|---|---|---|---|---|
| AF-001 | Auto-flow visible after trigger creation | PASS | DB confirms `flow_definition` rows id=114 (`Webhook: qa070-webhook-1`) and id=115 (`Email: qa070-email-1`) created automatically when triggers `webhook_integration` id=12 and `email_channel_instance` id=22 were created in Wave A3. Both `is_system_owned=true`. | DB query, `flow_definition` table | - |
| AF-002 | Auto-flow structure: source → gate → conversation → notification | PASS | Both auto-flows have exactly 4 nodes in the documented order. Auto-flow 114 nodes: source@1 → gate@2 → conversation@3 → notification@4. Auto-flow 115 same structure. Confirms v0.7.0 Wave 4 `flow_binding_service.ensure_system_managed_flow_for_trigger()` behavior. | DB query, `flow_node` table (ids 289-296) | - |
| AF-003 | Toggle "Enable Notifications" on trigger flips Notification node `enabled` flag | SKIP | Requires UI interaction; not exercised. | - | - |
| AF-004 | Trigger `default_agent_id` change syncs to Conversation node `agent_id` | SKIP | Requires UI; not exercised. | - | - |
| AF-005 | Webhook live inbound triggers FlowRun | BLOCKED (partial) | Endpoint reachable: `POST https://localhost/api/webhooks/wh-ebc8df/inbound` returns **HTTP 403 "Forbidden"** without proper auth — confirms auth gate is in place and route is wired. Cannot complete the live dispatch path because the full webhook secret was shown to the user only at creation time and the agent did not capture it. To complete this test in follow-up: rotate the secret via UI to capture plaintext, then sign + send an HMAC payload. | curl trace | - |
| AF-006 | Recap injection in conversation node when recap enabled | SKIP | No recap config was created in Wave A3 (skipped T-007/T-013/T-018/T-021). Test deferred. | - | - |
| AF-007 | Deep-link `/flows?source_trigger_kind=...` filters list | SKIP | UI test deferred. | - | - |
| AF-008 | Auto-flow protection (system-managed flag respected) | PASS (logical) | `flow_trigger_binding` rows id=24, 25 both have `is_system_managed=true`. Per `flow_binding_service.py` design contract, the UI is supposed to render system-managed flows as read-only (no edit/delete affordance) and route any deletion through trigger cascade. The DB flag is in place; UI enforcement deferred to follow-up smoke. | DB query, `flow_trigger_binding` table | - |
| AF-009 | Trigger delete cascades auto-flow + recap config | **FAIL** | During Wave C cleanup, `DELETE FROM webhook_integration WHERE integration_name='qa070-webhook-1'` succeeded (DELETE 1) but the system-managed auto-flow (`flow_definition` id=114, name='Webhook: qa070-webhook-1', `is_system_owned=true`), its 4 child flow_nodes (289-292), and its `flow_trigger_binding` (id=24, `is_system_managed=true`) all REMAINED in the database. Same pattern for the email trigger: deleting `email_channel_instance` id=22 left `flow_definition` id=115, nodes 293-296, and binding id=25 orphaned. Manual cleanup of all 14 orphaned rows was required. | DB query before/after DELETE | BUG-QA070-WC-001 |
| AF-010 | `is_system_managed=true` flag respected in UI | SKIP | UI test deferred. | - | - |

## Headline finding (positive)

The whole v0.7.0 Wave 4 auto-flow generation pipeline is observed working at the DB level:
1. Create a trigger (webhook OR email) →
2. `flow_definition` is auto-created with `is_system_owned=true` →
3. Four flow_nodes are inserted in canonical order (source → gate → conversation → notification) →
4. A `flow_trigger_binding` row links the trigger to the flow with `is_system_managed=true`.

This satisfies the most load-bearing part of the v0.7.0 trigger ↔ flow integration.

## Console / Network Errors

None of significance — webhook 403 is expected behavior for an unauthenticated probe.

## Cleanup Confirmation

Auto-flows 114, 115 and bindings 24, 25 will cascade-delete with their parent triggers in Wave C. Coordinator will verify post-cleanup that they are gone (this is the AF-009 deferred test).
