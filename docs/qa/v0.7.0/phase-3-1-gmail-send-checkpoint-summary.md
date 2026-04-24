# v0.7.0 Phase 3.1 Gmail Send Checkpoint Summary

Date: 2026-04-23
Phase 8 docs-sync refresh: 2026-04-24
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

## Current remaining validation

- Optional API/agent-chat Gmail send proof remains pending until `TSN_RUN_GMAIL_AGENT_CHAT_LIVE_GATE=1`, `TSN_GMAIL_AGENT_CHAT_BASE_URL`, `TSN_GMAIL_AGENT_CHAT_API_TOKEN`, and `TSN_GMAIL_AGENT_CHAT_AGENT_ID` are available.
- Fresh-install Ubuntu VM validation remains pending on the documented Parallels path because SSH works but `sudo -n true` on `parallels@10.211.55.5` requires a human password.

## Phase 3.1 exit-proof update

Initial follow-up live validation on 2026-04-23 against the dedicated Phase 0.5 Gmail fixture account found:

- Direct `GmailService.send_message(...)` succeeds and Sent visibility is real.
- Direct `GmailService.reply_to_message(...)` succeeds and remains threaded.
- `GmailSkill.execute_tool({"action":"send", ...})` succeeds against the live integration and the sent mail is visible in `in:sent`.
- `GmailService.create_draft(...)` does **not** work on the current fixture account because the integration only has `gmail.readonly + gmail.send`. Gmail's `users.drafts.create` requires `gmail.compose`, `gmail.modify`, or `mail.google.com/`, so the product now fails fast with an explicit reauthorization error instead of surfacing Gmail's raw `403 Forbidden`.

At that checkpoint, Track G's code was corrected for Gmail's real scope model, but the full Phase 3.1 live exit proof was still blocked on re-authorizing the fixture integration with `gmail.compose`.

That checkpoint was safe to merge before reauthorization, but it was not a Phase 3.1 completion claim. The 2026-04-24 refresh below supersedes that blocker.

## Phase 3 exit-proof refresh

Follow-up live validation on 2026-04-24 superseded the draft-scope blocker above:

- Gmail compose reauthorization completed through Hub for integration `4` (`mv@archsec.io`), and `backend/tests/fixtures/gmail_oauth.enc` was re-exported with draft-compatible scope.
- `TSN_GMAIL_REQUIRE_COMPOSE_SCOPE=1 pytest -q -o addopts='' backend/tests/test_gmail_oauth_fixture.py::test_gmail_oauth_fixture_compose_readiness_is_explicit` -> `1 passed`.
- `TSN_RUN_GMAIL_PHASE3_LIVE_GATE=1 pytest -q -o addopts='' tests/test_gmail_send_phase3_live_gate.py` inside the backend container -> `3 passed, 1 skipped`; proved direct send, direct reply, `GmailSkill` send, and live Gmail draft creation. The one skipped case is the optional API/agent-chat proof because API token/agent env vars were not set.
- `TSN_RUN_EMAIL_PHASE3_LIVE_GATE=1 pytest -q --tb=short -o addopts='' tests/test_email_trigger_phase3_live_gate.py` inside the backend container -> `1 passed`; proved one incoming Gmail message creates exactly one wake/run, duplicate polling does not double-fire, managed triage creates a Gmail draft, and Sentinel/MemGuard block mode records `blocked_by_security` with no wake/run.

The Phase 3.1 Gmail send/reply/draft and Phase 3 Email poll/triage/MemGuard live gates have passed for the allowed fixture. Remaining open items are optional API-agent proof and the Ubuntu fresh-install sudo handoff listed above.
