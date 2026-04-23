# v0.7.0 Phase 3.1 Gmail Send Checkpoint Summary

Date: 2026-04-23
Branch: `release/0.7.0`
Merged checkpoint: `merge: Track G Gmail send checkpoint`

## Scope landed

- Added Gmail outbound primitives in `backend/hub/google/gmail_service.py`:
  - `send_message(...)`
  - `reply_to_message(...)`
  - `create_draft(...)`
- Extended `backend/services/email_command_service.py` and `backend/agent/skills/gmail_skill.py` so agent tools can send, reply to, and draft Gmail messages.
- Tightened Gmail OAuth/send behavior so send/reply calls fail closed unless the integration includes `gmail.send` or another send-compatible Gmail write scope.
- Tightened draft behavior so `create_draft(...)` fails closed unless the integration includes `gmail.compose`, `gmail.modify`, or `mail.google.com/`.
- Updated Gmail Hub/API reauthorization flows to request `gmail.send + gmail.compose` for full outbound send/reply/draft support.
- Updated Hub wizard and skill copy so Gmail is described as read + outbound instead of read-only.

## Validation

- `docker-compose build --no-cache backend frontend`
- `docker-compose up -d backend frontend`
- `curl -fsS http://localhost:8081/api/health` -> healthy
- `curl -fsS http://localhost:8081/api/readiness` -> ready
- `docker exec tsushin-backend python -m pytest -q -o addopts='' tests/test_gmail_send_phase3_checkpoint.py` -> `6 passed, 2 warnings`
- Headed Playwright validation on `https://localhost/hub` confirmed:
  - Gmail setup wizard copy advertises `Read + outbound (gmail.readonly + gmail.send + gmail.compose)`
  - reauthorization guidance explains how legacy read-only integrations upgrade
  - 0 browser console errors; only repeated CSS preload warnings

Private evidence was saved under `.private/qa/v0.7.0/phase-3-1-checkpoint/`.

## Remaining root-only validation before Phase 3.1 is complete

- Re-authorize the Phase 0.5 Gmail fixture account with `gmail.compose` or a broader Gmail write scope.
- Run the opt-in live gate from the repository root with `TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1`; the gate intentionally fails if the fixture still has only `gmail.readonly + gmail.send`.
- Run the optional full API/agent-chat scaffold with `TSN_RUN_GMAIL_AGENT_CHAT_LIVE_GATE=1`, `TSN_GMAIL_AGENT_CHAT_BASE_URL`, `TSN_GMAIL_AGENT_CHAT_API_TOKEN`, and `TSN_GMAIL_AGENT_CHAT_AGENT_ID` so a public chat call sends mail and Sent visibility is proven.
- The downstream Email Trigger + triage managed-flow work remains blocked on later Phase 3 slices

## Phase 3.1 exit-proof update

Follow-up live validation on 2026-04-23 against the dedicated Phase 0.5 Gmail fixture account found:

- Direct `GmailService.send_message(...)` succeeds and Sent visibility is real.
- Direct `GmailService.reply_to_message(...)` succeeds and remains threaded.
- `GmailSkill.execute_tool({"action":"send", ...})` succeeds against the live integration and the sent mail is visible in `in:sent`.
- `GmailService.create_draft(...)` does **not** work on the current fixture account because the integration only has `gmail.readonly + gmail.send`. Gmail's `users.drafts.create` requires `gmail.compose`, `gmail.modify`, or `mail.google.com/`, so the product now fails fast with an explicit reauthorization error instead of surfacing Gmail's raw `403 Forbidden`.

This means Track G's code is corrected for Gmail's real scope model, but the full Phase 3.1 live exit proof is still blocked on re-authorizing the fixture integration with `gmail.compose`.

This checkpoint is safe to merge before reauthorization, but it is not a Phase 3.1 completion claim.
