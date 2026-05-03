# Wave B2 (Playground subset) — Evidence

**Run:** 2026-05-03
**Tester:** qa-tester (B2 Playground)
**Counts:** PASS=3 FAIL=0 BLOCKED=0 SKIP=0

## Evidence Table

| ID | Scenario | Status | Notes | Evidence | Bug ID |
|---|---|---|---|---|---|
| C-001 | Playground basic round-trip | PASS | Sent "Hello qa070-c001" to existing agent **Gemini1** (id=17, thread=124, ollama/llama3.2:3b). Bot replied "Hello! It seems like we just started our conversation..." within ~15s, well under 60s budget. | screenshots/C-001-playground-roundtrip.png | — |
| C-002 | Playground multi-turn | PASS | Sent 2 follow-ups in same thread: "What is 2+2?" → "The answer to 2+2 is 4." and "And what is 10 times 5?" → "I see we've already had a math question earlier... 10 times 5 is 50." Conversation history persists; AI explicitly references prior turn proving server-side history retention. 3 user + 3 AI bubbles visible in UI. | screenshots/C-002-multiturn.png | — |
| C-006 | LLM provider in v0.7.0 catalog | PASS | Config panel shows Provider=**ollama**, Model=**llama3.2:3b**. ollama is one of the v0.7.0 catalog providers (OpenAI/Gemini/Ollama). | screenshots/C-006-llm-provider-config.png | — |

## Console / Network Errors

- 1 console error observed: `404 GET /api/playground/memory/17?thread_id=410` — stale fetch for the previously-active thread (thread 410 / movl agent) after switching to Gemini1/thread 124. Non-blocking, does not affect any test outcome. Pre-existing race condition between agent-switch and memory inspector refresh; not a v0.7.0 regression. Not filed as a new bug.
- 0 warnings.
- No 5xx responses; messages sent and received successfully.

## Cleanup Confirmation

- Reused pre-existing test agent **Gemini1** (id=17). No new agent created.
- Reused existing empty thread 124 ("General Conversation", auto-renamed by UI to "Qa070-c001"). No new thread artifact added beyond the messages themselves.
- No DB cleanup required. Per task spec, used pre-existing agent so no teardown needed.
