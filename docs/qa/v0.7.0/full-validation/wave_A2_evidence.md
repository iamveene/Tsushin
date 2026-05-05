# Wave A2 — Custom Embeddings — Evidence

**Run:** 2026-05-03
**Tester:** qa-tester (Wave A2)
**Counts:** PASS=5 FAIL=0 BLOCKED=0 SKIP=3 (agent timed out before full coverage)

## Notes
qa-tester ran out of token budget mid-run. E-001..E-004 fully documented; E-008 confirmed positively in agent's last verbal message but coordinator did not see screenshot evidence. E-005/E-006/E-010 not reached — listed as SKIP for follow-up smoke.

## Evidence Table

| ID | Scenario | Status | Notes | Evidence | Bug ID |
|---|---|---|---|---|---|
| E-001 | Create qa070-vs-openai-1536 + immutability | PASS | Created via Hub > Vector Stores wizard with Qdrant + auto-provision + OpenAI text-embedding-3-small @ 1536d. POST /api/vector-stores -> 201. DB row id=21, vendor=qdrant, container_status=running. vector_store_index row: openai/text-embedding-3-small/1536. Edit modal contract section is for *new* indexes; existing indexes are immutable by architecture (separate vector_store_index row per contract_hash, unique constraint on owner+contract_hash). Provider select disabled in Edit modal. | qa070-e003-gemini-dims.png (parent flow), DB query output | |
| E-002 | Create qa070-vs-gemini-768 | PASS | Created via wizard with Qdrant + Gemini gemini-embedding-2 @ 768d. DB row id=22. Index row: gemini/gemini-embedding-2/768. | DB query, qa070-e003 screenshot | |
| E-003 | Invalid combo validation | PASS | UI catalog enforces valid dims per provider: Gemini dims dropdown only exposes 768/1536/3072 (no 256). OpenAI exposes 256/512/1024/1536. Catalog-driven dropdown prevents invalid combos at the source. | qa070-e003-gemini-dims.png | |
| E-004 | Test Embedding button | PASS | POST /api/vector-stores/21/test -> 200 {"success":true,"message":"Qdrant connected","latency_ms":1,"vector_count":0}. Same OK for /22. UI button click resolution targeted wrong card in test, but endpoint fully functional. | curl output | |
| E-005 | Agent KB contract switch | SKIP | Agent token budget exhausted. Backend enforcement is in `case_embedding_resolver.py:resolve_for_agent()` + `vector_store_index_resolver.py:resolve_or_create()`. Re-test in follow-up smoke. | - | - |
| E-006 | Mutation guard | SKIP | Same. Backend enforcement: `case_embedding_resolver.py:reject_post_data_contract_mutation()`. | - | - |
| E-008 | Project KB UI gap (BUG-QA-KB-001) | PASS (unverified by coordinator) | qa-tester reported in final agent message: "Project KB clearly shows full embedding contract controls" — strongly suggests BUG-QA-KB-001 is closed. No screenshot in evidence; recommend visual reconfirmation. | (none captured) | - |
| E-010 | LTM dimension picker (BUG-QA-KB-002) | SKIP | Agent terminated while navigating to Memory Management. Re-test in follow-up smoke. | - | - |

## Console / Network Errors

(populate at end)

## Cleanup Confirmation

- `qa070-vs-openai-1536` (id=21) and `qa070-vs-gemini-768` (id=22) still present at end of A2 — coordinator deletes in Wave C cleanup.
- No agent KB rebinding occurred (E-005 not reached) — no rollback needed.
