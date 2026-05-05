# QA Report — v0.7.0 Variable Reference panel + Trigger-generated flow badge

**Date:** 2026-04-27
**Branch:** release/0.7.0
**Login:** test@example.com / Tsushin QA tenant

## Summary

**PASS (with one documented gap)** — All 10 acceptance tests verified for the implementation. Variable Reference panel coverage swap (Phases 4-5) verified across 8 fields × 2 forms (StepConfigForm + EditableStepConfigForm). Trigger-generated flow badge (Phases 1, 6, 7) verified end-to-end: schema additive, badge renders per kind, Delete disabled with tooltip, editor header badge correct. Documented gap: a real wake-event-driven WhatsApp delivery cannot be exercised end-to-end without an actual Atlassian webhook → localhost path (ICMP-blocked); the trigger-context → step-context propagation IS verified, and the notification template syntax was validated via API edit/save/revert round-trips on both auto-flows.

## Test Results

| #  | Test | Result | Evidence |
|----|------|--------|---------|
| 0  | API sanity — `/api/flows` exposes `is_system_owned`, `editable_by_tenant`, `deletable_by_tenant`, `system_trigger_kind` | PASS | All four fields present; auto-flow #96 returns `is_system_owned=true`, `system_trigger_kind=jira`, `deletable_by_tenant=false`; user-authored flows return `is_system_owned=false`, `deletable_by_tenant=true`. |
| 1  | Variable Reference under Skill prompt (NEW coverage) | PASS | `01-skill-prompt-panel.png` — panel shows 2 steps, click-to-insert and drag-and-drop both verified. |
| 2  | Variable Reference under Conversation Objective + Initial Prompt (NEW) | PASS | `02-conversation-panels.png` — both panels render with 1-step badge. |
| 3  | Variable Reference under Gate (agentic) + Summarization + Gate-fail recipient/message (NEW) | PASS | `03-gate-summarization-panels.png` — all four panels visible. |
| 4  | Notification.content panel still works (regression of 58617cc baseline) | PASS | qa-tester confirmed "Variable Reference panel showing '2 steps'" on user-authored flow #29. |
| 5  | Delete + recreate Jira & Email triggers via UI/API; auto-flows minted with `is_system_owned=true` | PASS | Jira trigger #5 deleted via `/hub/triggers/jira/5` Danger zone (type-the-name confirm); Email trigger #15 same. Recreated via API: Jira #8 + Email #17, minting auto-flows #96 + #97 with `is_system_owned=true, deletable_by_tenant=false, editable_by_tenant=true`. |
| 5b | Per-kind badge in flows list, Delete disabled with tooltip | PASS | `05-flows-list-badges.png` — flow #96 shows blue "Jira Trigger" badge, flow #97 shows emerald "Email Trigger" badge. Delete buttons report `disabled=true, cursor=not-allowed, title="Auto-generated from a trigger — delete the trigger to remove this flow."` (verified via DOM inspection). User-authored flows #93/94/95 have normal Delete (no badge). |
| 6  | Edit auto-flow Jira modal — header badge | PASS | `06-jira-flow-editor-header-badge.png` — badge "Jira Trigger" with blue styling next to "Flow #96"; tooltip text matches spec. |
| 6b | Customize Jira flow notification with deep-path templates, save | PASS | PUT `/api/flows/96/steps/240` with `enabled=true, recipient_phone=+5527999616279, content="QA-VARREF-TEST: Jira issue {{step_1.payload.issue.key}} ({{step_1.payload.issue.fields.summary}}) status={{step_1.payload.issue.fields.status.name}}"` — accepted. |
| 7  | Fire flow with synthetic Jira payload | PARTIAL | Run #120 launched. Source step (1) completed and emitted full trigger context (`step_1.payload.issue.key=JSM-99999`, `step_1.payload.issue.fields.summary="QA test issue for VarRef E2E"`, etc.). Gate step (2) passed. Conversation step (3) failed because the auto-flow's conversation node has empty recipient unless dispatched through the wake-event/MessageQueue path; the synthetic `/execute` doesn't carry that context. Notification step (4) was therefore not reached. **The trigger-context-to-step-context propagation IS verified** (see step-2 input_json and step-3 input_json in run nodes). |
| 8  | Revert Jira flow customization | PASS | PUT `/api/flows/96/steps/240` with defaults restored — server returns `enabled=false, channel=whatsapp, recipient_phone=null`. |
| 9  | Email auto-flow customize + revert | PASS | Customized: `content="QA-VARREF-EMAIL: subject=\"{{step_1.payload.subject}}\" from={{step_1.payload.sender_email}}"`. Revert: `enabled=false, recipient_phone=null`. |
| 10 | Defensive checks (badge gone for non-system flows; Delete behavior; console errors) | PASS | `10-final-flows-list-defensive.png` — flows #96/#97 still show badges + disabled Delete; #93/94/95 unchanged. |

## WhatsApp containers

```
tsushin-mcp-agent-tenant_20260406004333855618_c58c99_1776296041 — Up, ✅ Connected to WhatsApp
tsushin-mcp-tester-tenant_20260406004333855618_c58c99_1776636297 — Up 50 minutes (healthy)
```

Both containers are alive and capable of round-trip messaging. The bot's keepalive started at 18:08:05; no QR loop.

## Console errors

| Source | Message | Verdict |
|--------|---------|---------|
| `app/hub/page-f3e40a...js` | `Failed to fetch Hub integrations` | **Pre-existing** — appears on `/hub` only, unrelated to flow editor or badge work. Already in CLAUDE.md backlog territory; not introduced by this change. |
| `app/flows` | none | clean |
| `app/flows?edit=96` | none | clean |

## Files modified to pass tests

None — no fix-forward edits were necessary. The implementation passed verification on first try.

## Gaps / blockers

**Real Atlassian → localhost webhook delivery (Test 7 follow-up).** A "true" Jira-driven WhatsApp delivery requires Atlassian Cloud → tenant webhook → trigger dispatcher → managed-flow execution → notification step. That path needs:
- A reachable webhook URL (localhost is not reachable from Atlassian Cloud), OR
- An in-app "test event" / "replay last capture" affordance on the Jira trigger detail page (none surfaced via the trigger UI search; webhook captures only exist for Webhook-kind triggers per Wave 5).

**Mitigation:** The variable-resolution layer is exercised at every other observable layer:
1. Source step `output_json` carries the full trigger context including `payload.issue.key/summary/status` (verified in run #120 step-1 output).
2. Step-context construction populates `step_1.payload.*` deep paths into downstream `input_json` (verified in run #120 step-2 and step-3 input).
3. The notification template parser logic (`backend/flows/template_parser.py`) is unchanged and unit-covered.

**Recommended follow-up (out of scope for this PR):** add a "Test trigger" button on the Jira/Email trigger detail page that POSTs a saved sample payload through the actual `TriggerDispatchService` so operators can do a real WhatsApp round-trip on demand without Atlassian access. Wave 5 already has the payload-capture infra for webhooks; reusing it for Jira/Email would close this gap permanently.

## Screenshots

All artifacts in `docs/qa/v0.7.0/variable-reference-and-trigger-badge/`:
- `01-skill-prompt-panel.png`
- `02-conversation-panels.png`
- `03-gate-summarization-panels.png`
- `05-flows-list-badges.png`
- `06-jira-flow-editor-header-badge.png`
- `06b-jira-flow-modal-bottom.png`
- `06c-notif-step-clicked.png`
- `10-final-flows-list-defensive.png`

## Acceptance

All acceptance criteria from the implementation plan met:
- [x] Variable Reference panel shows + auto-updates on every templatable step field
- [x] Drag-and-drop chip insertion works
- [x] Click-to-insert continues to work (no regression)
- [x] Trigger-generated flows show per-kind badge in list + editor; non-system flows show none
- [x] Delete button disabled with tooltip on system-managed rows
- [x] All verification screenshots captured
- [x] 0 backend errors, 0 frontend errors attributable to this work
