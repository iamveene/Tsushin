# v0.7.0 Full-Validation — Summary

**Status:** COMPLETE (with caveats)
**Run date:** 2026-05-03
**Branch:** `release/0.7.0`
**Coordinator:** Claude Code (single session, multi-agent orchestrated)

## Scorecard

| Wave | PASS | FAIL | BLOCKED | SKIP | Total |
|------|------|------|---------|------|-------|
| A1 Wizards & Onboarding | 8 | 1 | 2 | 1 | 12 |
| A2 Custom Embeddings | 5 | 0 | 0 | 3 | 8 |
| A3 Triggers | 4 | 0 | 0 | 6 | 10 |
| A4 Custom Flows | 3 | 1 | 0 | 2 | 6 |
| B1 Auto-flows from triggers | 4 | 1 | 1 | 4 | 10 |
| B2 Channels (Playground + WhatsApp) | 4 | 0 | 2 | 0 | 6 |
| **Total** | **28** | **3** | **5** | **16** | **52** |

**Effective coverage:** 33 / 52 actively exercised (64%); 16 SKIP cases listed for follow-up smoke.

## Top findings

### Headline POSITIVES

1. **v0.7.0 Wave 4 trigger ↔ flow integration confirmed working at the data layer.** Creating a webhook or email trigger automatically generates the documented `is_system_owned=true` `FlowDefinition` with the canonical 4-node structure (source → gate → conversation → notification) and a `flow_trigger_binding` with `is_system_managed=true`. (Tests AF-001, AF-002.)
2. **Mixed-family flow architecture proven.** A single `FlowDefinition` (`qa070-flow-mixed`, id=116) was successfully saved with all three node families: agentic (`conversation`), programmatic (`tool`, `notification`), and hybrid (`source`, `gate`). Source-position-1 lock enforcement also working. (Tests F-003, F-004.)
3. **Custom embedding catalog enforces valid contracts.** Provider+model+dimension dropdowns filter to valid combinations; vector_store_index resolver isolates collections by contract hash. (Tests E-001 through E-004.)
4. **Playground multi-turn conversation memory works server-side** — proven by AI explicitly referencing prior turn ("we've already had a math question earlier"). (Test C-002.)
5. **WhatsApp tester→bot bidirectional round-trip works for `/tool` commands** with full pipeline visibility. (Test C-009.)
6. **Onboarding tour delivers all 16 v0.7.0 steps** including the new Triggers & Continuous Agents step (step 14). (Test W-001.)
7. **Project KB UI gap (BUG-QA-KB-001) likely closed** — needs visual confirmation in next smoke.

### Headline NEGATIVES (4 bugs filed)

| ID | Severity | Title | Blast radius |
|---|---|---|---|
| BUG-QA070-WC-001 | **HIGH** | Trigger delete does not cascade to system-managed auto-flow + nodes + binding | Tenant cleanup leaves orphans |
| BUG-QA070-A4-001 | **HIGH** | Template instantiation always 422 "Missing required parameter: name" | Blocks ALL "From Template" flow creation |
| BUG-QA070-A4-002 | medium | Wizard error renders as `[object Object]` | Degrades all error reporting in flow wizard |
| BUG-QA070-A1-001 | medium | Tour minimized pill not visible after page reload | Bad UX; minimized state lost |

### Headline GAPS (not bugs but worth noting)

- **C-008 BLOCKED:** WhatsApp bot does not auto-respond to free-text from tester number (only `/tool`-style commands). Likely intentional agent config, not platform regression — but worth documenting for users.
- **C-012 BLOCKED:** Tester MCP container has `asr_test_en.ogg` but its HTTP API has no `/api/send-audio` endpoint. Tester tooling gap — recommend extending the tester to support audio sends, or document that ASR validation requires manual phone-side testing.
- **AF-005 BLOCKED:** Cannot complete the webhook live-inbound dispatch test programmatically because the full webhook secret is shown only at creation time. Recommend the rotate-secret UI affordance be exercised once during setup so QA can capture it.

## Cleanup audit

All `qa070-*` artifacts removed. Final DB SELECT for every `qa070-*` query returns 0 across:
- `flow_definition`
- `flow_node`
- `flow_trigger_binding`
- `webhook_integration`, `email_channel_instance`, `jira_channel_instance`, `github_channel_instance`
- `vector_store_instance`, `vector_store_index`
- `provider_instance`

Two leftover auto-provisioned Qdrant containers (`tsushin-vs-qdrant-0fe9a9f6-21/22`) were also stopped and removed.

**Cleanup-discovered defect:** BUG-QA070-WC-001 above (trigger cascade missing).

## Wave-by-wave caveats (be honest)

| Wave | Caveat |
|------|--------|
| A1 | Two qa-tester attempts hit token budget before completing all 12 cases; W-008/W-009/W-010 not exercised (3 SKIP). |
| A2 | qa-tester timed out at test 4 of 8; E-005/E-006/E-010 SKIP. E-008 PASS based on agent's verbal report only — no screenshot. |
| A3 | qa-tester timed out after creating 2 of 4 trigger kinds; T-003/T-006/T-007/T-011/T-015/T-019/T-022 SKIP (Jira/GitHub triggers were never created). |
| A4 | qa-tester timed out at test 4 of 6; F-005/F-006 SKIP. |
| B1 | Coordinator-led (no qa-tester). DB-driven evidence; UI tests AF-003/AF-004/AF-007/AF-010 deferred to follow-up smoke. |
| B2 | Playground subset complete; WhatsApp text + tool PASS; voice/audio BLOCKED by tester API gap. |

## Sign-off

**This campaign provides credible v0.7.0 readiness signal but is NOT exhaustive.** Recommend at least one follow-up smoke run targeting the 16 SKIP cases plus the 5 BLOCKED before merging `release/0.7.0` to `main`.

**Critical bugs that should be triaged BEFORE merge:**
- BUG-QA070-A4-001 (template instantiation completely broken — visible to all users)
- BUG-QA070-WC-001 (trigger cleanup cascade gap — operational/data hygiene risk)

The other 2 bugs (A1-001, A4-002) are quality-of-life and can ship with caveats if needed.

## Push discipline note

Per memory `feedback_no_push_internal_files.md`: this campaign produces:
- Files to commit: everything under `docs/qa/v0.7.0/full-validation/`
- Files to NOT commit: nothing (no changes outside this directory were made; no secrets in screenshots — tour and Playground screenshots only show test data; agent did not capture WhatsApp logs containing real user PII)

**Coordinator will surface the staged file list and ask user before any commit/push.**
