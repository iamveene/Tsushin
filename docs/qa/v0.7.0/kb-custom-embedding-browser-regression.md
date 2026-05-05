# Release 0.7.0 KB Custom Embedding Browser Regression

Date: 2026-05-03
Tester: Codex browser automation
Repository: `/Users/vinicios/code/tsushin`
Mode: testing/report only; no implementation fixes.

## Environment

- Stack: existing `docker-compose` stack, no rebuild required.
- Health at start: backend, frontend, postgres, proxy healthy; Qdrant auto-provisioned container running.
- Frontend: `https://localhost`
- Backend: `http://localhost:8081`
- Browser automation: Playwright Chromium via `frontend/node_modules/@playwright/test`.
- User/tenant: `test@example.com`, tenant `tenant_20260406004333855618_c58c99` / `Tsushin QA`. Password was the documented dev password and is not repeated here.
- Test agent: `CustomerService` (`agent_id=6`).
- External vector store used: `gemini-1536` (`vector_store_instance_id=19`, Qdrant, auto-provisioned, healthy, container `tsushin-vs-qdrant-0fe9a9f6-19`, port `6300`).
- Evidence directory: `docs/qa/v0.7.0/kb-custom-embedding-browser-regression/evidence/`
- Evidence JSON: `docs/qa/v0.7.0/kb-custom-embedding-browser-regression/evidence/browser-regression-evidence.json`

## Provider And Dimension Discovery

The Agent KB UI/API exposed:

| Provider option | Models | Supported dimensions |
|---|---|---|
| `gemini1` (`gemini:4`) | `gemini-embedding-2`, `gemini-embedding-001` | `768`, `1536`, `3072` |
| Built-in local | `all-MiniLM-L6-v2` | `384` |
| OpenAI `op1` | `text-embedding-3-small`, `text-embedding-3-large` | `256`, `512`, `1024`, model max |
| Ollama local | `nomic-embed-text` | detected/custom |

The requested 700-range dimension is exactly `768`.

## Test Matrix

| Scenario | Result | Evidence |
|---|---:|---|
| Existing external auto-provisioned vector store visible in Hub | PASS | `02-hub-vector-stores-existing-qdrant.png` |
| Vector store embedding test route visible in Settings | PASS | `03-settings-vector-store-test-embedding.png` |
| Agent KB, Gemini Embedding 2, 1536d, Qdrant | PASS | `10-1536-*` screenshots |
| Agent KB, Gemini Embedding 2, 768d, Qdrant | PASS | `20-768-*` screenshots |
| Agent KB mixed 1536d + 768d documents remain searchable | PASS | `30-coexist-1536-after-768-06-agent-kb-search.png` |
| Project KB custom provider/model/dimension/vector-store controls | FAIL | `41-project-create-modal-kb-controls.png`, `42-project-detail-kb-controls.png` |
| Long-term memory custom embedding provider/model/dimension controls | FAIL / GAP | `50-agent-configuration-vector-store-memory.png` |
| Pinecone dimension behavior | NOT COVERED | No Pinecone instance was configured in this environment. |

## Agent KB Results

### 1536d Profile

Steps executed through the UI:

1. Opened Agent Knowledge Base for `CustomerService`.
2. Selected provider `gemini1`, model `Gemini Embedding 2`, dimension `1536`, vector storage `gemini-1536 (qdrant)`.
3. Ran `Test Embedding`.
4. Saved settings.
5. Uploaded `kb-gemini-1536-sample.txt`.
6. Waited for completed status.
7. Ran Agent KB search and Playground question.

Results:

- Embedding test passed: `1536 dimensions`, batch `2`, `2255 ms`.
- Document completed with contract:
  - provider `gemini`
  - model `gemini-embedding-2`
  - dims `1536`
  - vector store `19`
  - collection `kb_e1f9f2d476_6_1536`
  - namespace `kb:tenant_20260406004333855618_c58c99:6:1536`
- KB search returned the expected facts: `Mira Solenne`, `LOD-1536-CANARY`, `heliotrope atlas`.
- Playground answer correctly returned owner, date, support queue, and secret phrase.

### 768d Profile

Steps executed through the UI:

1. Reopened Agent Knowledge Base for the same agent.
2. Selected provider `gemini1`, model `Gemini Embedding 2`, dimension `768`, vector storage `gemini-1536 (qdrant)`.
3. Ran `Test Embedding`.
4. Saved settings.
5. Uploaded `kb-gemini-768-sample.txt`.
6. Waited for completed status.
7. Ran Agent KB search and Playground question.

Results:

- Embedding test passed: `768 dimensions`, batch `2`, `1518 ms`.
- Document completed with contract:
  - provider `gemini`
  - model `gemini-embedding-2`
  - dims `768`
  - vector store `19`
  - collection `kb_e1f9f2d476_6_768`
  - namespace `kb:tenant_20260406004333855618_c58c99:6:768`
- KB search returned the expected facts: `Theo Marlowe`, `CPA-768-CANARY`, `saffron signal`.
- Playground answer correctly returned owner, review date, support queue, and secret phrase.

### Dimension Coexistence

After switching the agent KB defaults from `1536` to `768`, both documents remained visible with separate contracts. The post-switch KB search for the 1536 canary returned the 1536 document first and the 768 document second, with no dimension mismatch error.

The 768 Playground answer showed `2 docs used (Agent)`, with `kb_used` metadata referencing both the 768 and 1536 documents. This confirms merged retrieval across profiles. The final post-switch 1536 Playground screenshot was captured before the newest assistant response completed, so the strongest coexistence evidence is the Agent KB search/table plus the 768 Playground `kb_used` metadata.

## Project KB Results

Project creation was exercised through the UI with `QA Custom Embedding Project 2026-05-03T15-58-25-460Z`.

The Project create modal and Project detail Knowledge Base tab do not expose:

- embedding provider selection
- `gemini-embedding-2`
- dimensions
- vector storage
- external auto-provisioned vector store selection

Only the legacy project embedding model selector appears, with:

- `all-MiniLM-L6-v2`
- `all-mpnet-base-v2`
- `paraphrase-multilingual-MiniLM-L12-v2`

Because of that, the requested Project KB 1536d and 768d custom embedding flows could not be executed through the UI.

## Long-Term Memory / Semantic Search

The Agent Configuration tab exposes vector store selection for long-term memory, but it does not expose custom embedding provider/model/dimension controls. The Settings vector store page can run `Test Embedding`, but the existing Qdrant store reports `provider=gemini`, `model=gemini-embedding-001`, `dims=1536`, not `gemini-embedding-2`.

The requested long-term memory checks for `gemini-embedding-2` at `1536` and `768` could not be configured through the UI. I did not force this via API because the requested acceptance source was browser-visible UI behavior.

## Console And Network

- HTTP errors: none.
- Console warnings: one Next.js preload warning for an unused CSS preload.
- Network failures: four `net::ERR_ABORTED` `_rsc` requests during rapid route changes/project cleanup. These were navigation aborts, not user-visible request failures.
- Upload dialogs: both document uploads showed `Document uploaded successfully! Processing will begin shortly.`

## Bugs / Regression Gaps

### BUG-QA-KB-001: Project KB lacks Release 0.7.0 custom embedding controls

Severity: High
Area: Project KB UI/API parity

Repro:

1. Log in as tenant owner.
2. Open `Studio -> Projects`.
3. Click `New Project`.
4. Inspect `Knowledge Base Configuration`.
5. Create a project and open its `Knowledge Base` tab.

Expected: Project KB can select embedding provider, `Gemini Embedding 2`, dimensions `1536` and `768`, and external vector storage like Agent KB.
Actual: Project KB exposes only legacy local embedding model choices and chunk size/overlap. No provider, dimensions, or vector store control is available.

### BUG-QA-KB-002: Long-term memory custom embedding provider/model/dimension is not configurable in UI

Severity: High
Area: Agent semantic memory / vector-store configuration

Repro:

1. Open `Agents -> CustomerService -> Configuration`.
2. Inspect `Vector Store`.
3. Open `Settings -> Vector Stores` and select the Qdrant store.
4. Run `Test Embedding`.

Expected: Long-term memory can be configured to use `gemini-embedding-2` at `1536` and `768`, or the UI clearly indicates the embedding contract bound to the selected store and supports separate dimension profiles.
Actual: Agent Configuration only selects a vector store/mode. Settings test reports the existing store contract as `gemini-embedding-001 / 1536d`; no UI path was visible for `gemini-embedding-2` or `768`.

## Cleanup Performed

- Deleted QA agent KB document `kb-gemini-1536-sample.txt` (`id=6`).
- Deleted QA agent KB document `kb-gemini-768-sample.txt` (`id=7`).
- Restored original `CustomerService` KB config:
  - provider `local`
  - model `all-MiniLM-L6-v2`
  - dims `384`
  - vector store `null`
  - chunk size `800`
  - overlap `100`
- Deleted QA project `QA Custom Embedding Project 2026-05-03T15-58-25-460Z` (`id=4`).
- Verified agent KB document list was empty after cleanup.

## Commands / Automation Run

- `docker-compose ps`
- Playwright Chromium browser automation from `frontend` using `node` and `@playwright/test`.
- Supplemental browser-context API reads for evidence:
  - `/api/auth/me`
  - `/api/embedding-providers/options`
  - `/api/vector-stores`
  - `/api/settings/vector-stores/default`
  - `/api/agents/6/knowledge-base/config`
  - `/api/agents/6/knowledge-base`

No source code fixes were made.

## Lead Audit Double-Check

Date: 2026-05-03
Reviewer: Codex lead follow-up audit

The test looked unusually fast for the breadth requested, so the lead agent audited the report and current runtime state after the worker completed.

Confirmed:

- Evidence artifacts exist for the browser run, including 27 screenshots plus `browser-regression-evidence.json`.
- Artifact timestamps show a compressed but plausible automated browser pass from `12:57:34` to `12:58:28` local time.
- The evidence JSON records real browser/WebSocket Playground sends for agent `6` and real API state for both uploaded KB documents.
- Current API state after cleanup matches the report:
  - Agent `6` KB config restored to `local / all-MiniLM-L6-v2 / 384d`.
  - Agent `6` KB document list is empty.
  - The temporary QA project is no longer returned by project search.
- Current Qdrant state matches the reported isolation contract:
  - `kb_e1f9f2d476_6_1536` exists with vector size `1536`, point count `0`.
  - `kb_e1f9f2d476_6_768` exists with vector size `768`, point count `0`.
  - `case_memory_tenant_20260406004333855618_c58c99` remains separate with vector size `1536`, point count `30`.
- Post-cleanup KB searches for the two QA canary phrases return no results, confirming document cleanup removed the test docs from the app-visible KB path.

Audit caveats:

- The strongest positive coverage is Agent KB custom embeddings. It did exercise provider/model/dimension selection, embedding test, external Qdrant storage, upload, KB search, Playground retrieval, mixed-dimension retrieval, and cleanup.
- Project KB and long-term memory semantic search were not fully executed with custom embeddings because the UI does not expose the required custom embedding controls. These remain real release gaps rather than passing tests.
- The JSON evidence file has `"bugs": []` even though this Markdown report correctly documents `BUG-QA-KB-001` and `BUG-QA-KB-002`. Treat the Markdown bug section as authoritative; the empty JSON bug array is a report-generation inconsistency.
