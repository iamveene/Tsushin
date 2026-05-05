# Release 0.7.0 KB Custom Embedding Lead Regression

Date: 2026-05-03
Lead tester: Codex
Mode: browser automation, report only. No product fixes were made.

## Final Run

Final evidence directory:

`docs/qa/v0.7.0/kb-custom-embedding-lead-regression/evidence/final-run-2026-05-03T16-31-10-017Z/`

Primary evidence JSON:

`docs/qa/v0.7.0/kb-custom-embedding-lead-regression/evidence/final-run-2026-05-03T16-31-10-017Z/lead-browser-regression-evidence.json`

Automation script:

`backend/dev_tests/kb_custom_embedding_lead_browser_regression.js`

Two earlier lead attempts were intentionally discarded as acceptance evidence:

- `final-run-2026-05-03T16-26-14-279Z`: login selector missed the email field because the UI uses `type="text"`.
- `final-run-2026-05-03T16-28-08-401Z`: onboarding tour appeared after route load and intercepted clicks.

The final script handles both issues and produced 29 screenshots, 36 passing assertions, and no failed assertions.

## Environment

- Stack: existing Docker Compose stack from `/Users/vinicios/code/tsushin`.
- Health after run: backend, frontend, postgres, proxy healthy.
- Frontend: `https://localhost`
- Backend health: `{"status":"healthy","service":"tsn-core","version":"0.7.0"}`
- Browser automation: Playwright Chromium.
- Tenant/user: `test@example.com`, tenant `tenant_20260406004333855618_c58c99`.
- Agent: `CustomerService` (`agent_id=6`).
- External vector store: Qdrant instance `gemini-1536` (`vector_store_instance_id=19`).

## Results Matrix

| Scenario | Result | Evidence |
|---|---:|---|
| Agent KB exposes Gemini Embedding 2 options for `1536` and `768` | PASS | JSON `api.embedding_options` |
| Agent KB with Gemini Embedding 2, `1536d`, external Qdrant | PASS | `10-1536-*` screenshots |
| Agent KB search returns `1536d` canary | PASS | `10-1536-07-agent-kb-search-ui.png` |
| Playground answers from `1536d` KB canary | PASS | `10-1536-09-playground-answer.png` |
| Agent KB with Gemini Embedding 2, `768d`, same external Qdrant | PASS | `20-768-*` screenshots |
| Agent KB search returns `768d` canary | PASS | `20-768-07-agent-kb-search-ui.png` |
| Playground answers from `768d` KB canary | PASS | `20-768-09-playground-answer.png` |
| Mixed-dimension KB documents remain searchable after config change | PASS | `30-coexistence-two-doc-contracts.png`, JSON `coexistence_search_after_768` |
| KB and case memory coexist in Qdrant without collection/dimension conflict | PASS | Qdrant checks below |
| Project KB custom provider/model/dimension/vector store | FAIL | `41-project-create-modal-kb-controls.png`, `44-project-detail-kb-controls.png` |
| Long-term memory custom Gemini Embedding 2 `1536/768` via UI | FAIL / BLOCKED | `50-agent-configuration-vector-store-memory.png`, `51-agent-memory-management-tab.png`, `52-settings-vector-stores.png` |

## Agent KB Details

### 1536 Dimensions

The browser selected:

- Embedding provider: `gemini:4`
- Model: `gemini-embedding-2`
- Dimensions: `1536`
- Vector storage: Qdrant `vector_store_instance_id=19`

The embedding test passed in the UI. Uploading `lead-kb-1536-2026-05-03T16-31-10-017Z.txt` created document `id=10` with:

- provider/model/dims: `gemini / gemini-embedding-2 / 1536`
- collection: `kb_e1f9f2d476_6_1536`
- namespace: `kb:tenant_20260406004333855618_c58c99:6:1536`

The Playground answer included the expected canary facts: `Selene Vega`, `argent-lane`, `2026-05-03`, and `LEAD-1536-QUARTZ`.

### 768 Dimensions

The browser then changed the same agent KB to:

- Embedding provider: `gemini:4`
- Model: `gemini-embedding-2`
- Dimensions: `768`
- Vector storage: same Qdrant instance `19`

The embedding test passed in the UI. Uploading `lead-kb-768-2026-05-03T16-31-10-017Z.txt` created document `id=11` with:

- provider/model/dims: `gemini / gemini-embedding-2 / 768`
- collection: `kb_e1f9f2d476_6_768`
- namespace: `kb:tenant_20260406004333855618_c58c99:6:768`

The Playground answer included `Ilya Moreno`, `verdant-bridge`, `2026-05-03`, and `LEAD-768-CEDAR`.

### Coexistence

After switching active KB config to `768d`, the old `1536d` document remained searchable. The merged search path returned the old `1536d` canary and the new `768d` document without dimension mismatch errors.

Qdrant state during the final run:

- After `1536d` upload: `kb_e1f9f2d476_6_1536` had `1` point.
- After `768d` upload: `kb_e1f9f2d476_6_768` had `1` point.

Qdrant state after cleanup:

- `kb_e1f9f2d476_6_1536`: vector size `1536`, point count `0`.
- `kb_e1f9f2d476_6_768`: vector size `768`, point count `0`.
- `case_memory_tenant_20260406004333855618_c58c99`: vector size `1536`, point count `30`.

This confirms KB and long-term/case memory can coexist in the same Qdrant service when isolated by collections.

## Project KB Gap

Project creation was exercised through the browser. The create modal and project detail Knowledge Base tab still expose only legacy project KB settings:

- embedding model
- chunk size
- chunk overlap

They do not expose:

- embedding provider
- `gemini-embedding-2`
- dimensions `1536` / `768`
- vector storage / external Qdrant selection

Because of this, the requested Project KB custom embedding upload and Playground question flow is blocked from the UI.

## Long-Term Memory Gap

The Agent Configuration tab exposes a long-term-memory vector store selector and lists `gemini-1536 (qdrant)`, but there is no browser-visible control to choose:

- embedding provider
- `gemini-embedding-2`
- dimensions `1536` or `768`

The Memory Management tab also has no custom embedding controls, and Settings > Vector Stores only shows the vector store configuration surface, not a Gemini Embedding 2 contract selector for long-term memory.

I did not force Jira/email trigger custom embedding setup through API because the requested regression source was real browser behavior. Supplemental case-memory API checks did pass: `/api/case-memory` returned `113` rows and semantic search returned `3` items, while Qdrant case memory remained isolated in its own collection.

## Bugs Filed

### BUG-QA-KB-LEAD-001: Project KB lacks custom embedding controls

Severity: High
Area: Project KB UI/API parity

Expected: Project KB can select configured embedding provider, `gemini-embedding-2`, dimensions `1536` and `768`, and external Qdrant vector storage.
Actual: Project create/detail only expose the legacy local embedding model selector and chunk sizing controls.

### BUG-QA-KB-LEAD-002: Long-term memory cannot configure Gemini Embedding 2 dimensions through browser UI

Severity: High
Area: Semantic search / long-term memory / trigger regression

Expected: Agent long-term memory can be configured through the browser to use external vector storage plus Gemini Embedding 2 at `1536d` and `768d` before validating Jira/email trigger recall.
Actual: The UI only selects the vector store instance/mode. It does not expose embedding provider/model/dimensions, so the Jira/email trigger custom-embedding recall scenario is blocked.

## Follow-up Implementation Status — 2026-05-03

The two filed gaps have implementation coverage in the working tree:

- `BUG-QA-KB-LEAD-001`: Project KB now has provider/model/dimension/vector-store configuration, project document snapshots, multi-index vector isolation, and config/options endpoints.
- `BUG-QA-KB-LEAD-002`: Vector Store configuration now owns the default long-term-memory embedding contract, and `VectorStoreIndex` lets a single Qdrant/Chroma/Mongo/Pinecone connection host multiple immutable collections/indexes without creating another Docker container.

Targeted unit/API validation run:

```bash
pytest -o addopts='' backend/tests/test_vector_store_index_resolver.py backend/tests/test_project_kb_custom_embeddings.py backend/tests/test_kb_custom_embeddings.py backend/tests/test_case_memory_embedding_contract.py -q
```

Result after the final backend rebuild: `15 passed`.

Post-rebuild validation:

- `docker-compose build --no-cache backend frontend`: passed.
- `docker-compose up -d backend frontend`: backend and frontend restarted healthy without `docker-compose down`.
- `curl -sk https://localhost/api/health`: returned healthy `tsn-core` `0.7.0`.
- Rebuilt backend container targeted tests: `15 passed`.
- Live Postgres schema check confirmed `vector_store_index`, `project_knowledge_config`, and the new `vector_store_index_id` / `embedding_provider_instance_id` columns.
- Browser smoke artifacts: `output/playwright/multi-index-vector-store-smoke-2026-05-03T17-27-02-238Z/`.

Browser smoke result:

- Project create modal exposes `Embedding Provider`, `Embedding Model`, `Dimensions`, and `Vector Store` controls.
- Hub > Vector Stores create modal exposes `Default Long-Term Memory Contract` with provider/model/dimensions/metric controls.
- Settings > Vector Stores shows default contract/index information.

The canonical multi-index UI-first regression is now:

```bash
node backend/dev_tests/multi_index_external_vector_ui_regression.js
```

It configures Agent KB and Project KB through the browser, uploads documents with `gemini-embedding-2` at `1536d` and `768d`, validates deterministic KB search for old and new contracts, checks that both purposes use the same external Qdrant `VectorStoreInstance`, and confirms `VectorStoreIndex` rows plus Qdrant vector sizes for each physical collection. Evidence is written under `output/playwright/multi-index-external-vector-ui-regression-*/`.

Final UI-first regression result:

- Command: `node backend/dev_tests/multi_index_external_vector_ui_regression.js`
- Evidence: `output/playwright/multi-index-external-vector-ui-regression-2026-05-03T18-05-55-769Z/multi-index-external-vector-ui-regression-evidence.json`
- Assertions: `80`, failed: `0`.
- Agent KB collections:
  - `tsn_te4a672bb_agent_kb_agent_e85566a8_44d704810dde`: `1536d`, returned to `0` points.
  - `tsn_te4a672bb_agent_kb_agent_e85566a8_95b5fc1237df`: `768d`, returned to `0` points.
- Project KB collections:
  - `tsn_te4a672bb_project_kb_project_7c8d3bb5_44d704810dde`: `1536d`, returned to `0` points.
  - `tsn_te4a672bb_project_kb_project_7c8d3bb5_95b5fc1237df`: `768d`, returned to `0` points.
- Orphan Project KB collections from the pre-fix failed run were manually removed from Qdrant and now return `404`.

This closes the two filed gaps for the covered browser flows: Project KB now supports custom embedding/vector-store contracts, and the external vector store behaves as a multi-index container rather than requiring one Docker container per contract.

## Cleanup

- Deleted agent KB documents `id=10` and `id=11`.
- Restored Agent `6` KB config to `local / all-MiniLM-L6-v2 / 384d`, built-in storage.
- Deleted temporary project created by the lead run.
- Verified Agent `6` KB document list is empty.
- Verified no temporary `Lead Custom Embedding Project` remains.
- Verified Qdrant KB collections returned to zero points.

## Commands

- `node backend/dev_tests/kb_custom_embedding_lead_browser_regression.js`
- `docker-compose ps`
- `curl -sk https://localhost/api/health`
- `curl -s http://localhost:6300/collections/kb_e1f9f2d476_6_1536`
- `curl -s http://localhost:6300/collections/kb_e1f9f2d476_6_768`
- `curl -s http://localhost:6300/collections/case_memory_tenant_20260406004333855618_c58c99`
