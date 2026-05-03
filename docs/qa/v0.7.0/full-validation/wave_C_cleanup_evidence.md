# Wave C — Cleanup + Audit — Evidence

**Run:** 2026-05-03
**Tester:** coordinator

## Cleanup Summary

| Surface | Pre-cleanup | Post-cleanup | Cascade behavior |
|---|---|---|---|
| `flow_definition` (qa070 + auto-flows) | 3 rows (id=114, 115, 116) | 0 | **No automatic cascade from trigger delete** — required manual DELETE for 114, 115. See BUG-QA070-WC-001. |
| `flow_node` (under qa070 flows) | 13 rows (ids 289-301) | 0 | Did not cascade with parent flow delete via app layer (had to delete manually). |
| `flow_trigger_binding` | 2 rows (id=24, 25) | 0 | No cascade from trigger delete. |
| `flow_run` (qa070 flow runs) | 22 rows (per DELETE count) | 0 | Manual cleanup. |
| `flow_node_run` | 65 rows | 0 | Manual cleanup. |
| `webhook_integration` (qa070-webhook-1) | 1 row | 0 | Direct DB DELETE succeeded. |
| `email_channel_instance` (qa070-email-1) | 1 row | 0 | Direct DB DELETE succeeded. |
| `vector_store_instance` (qa070-vs-*) | 2 rows | 0 | Direct DB DELETE; vector_store_index rows also cleared (2 rows). |
| `vector_store_index` (qa070-bound) | 2 rows | 0 | Cleared. |
| `provider_instance` (qa070-openai-llm) | 1 row | 0 | Direct DB DELETE. |
| Qdrant containers (`tsushin-vs-qdrant-0fe9a9f6-21/22`) | 2 running | 0 | Manually stopped + removed (DB DELETE didn't trigger app-layer container cleanup since we bypassed the API). |

## Final audit query (all return 0)

```
flow_def_qa070: 0
webhook_qa070: 0
email_qa070: 0
jira_qa070: 0
github_qa070: 0
vs_qa070: 0
provider_qa070: 0
flow_node_orphan: 0
flow_binding_orphan: 0
```

## Cleanup-discovered bugs

- **BUG-QA070-WC-001 (HIGH)** — Trigger deletion does NOT cascade to system-managed auto-flows/nodes/bindings. Documented in `BUGS_FOUND.md`. Root cause likely in `flow_binding_service.py` or DB FK constraints (no `ON DELETE CASCADE` on the semantic FK from `flow_trigger_binding.trigger_instance_id` since it's a polymorphic reference).
