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
- Tightened Gmail OAuth/send behavior so outbound calls fail closed unless the integration includes `gmail.send`.
- Updated Gmail Hub/API reauthorization flows to request the expanded send scope.
- Updated Hub wizard and skill copy so Gmail is described as read + outbound instead of read-only.

## Validation

- `docker-compose build --no-cache backend frontend`
- `docker-compose up -d backend frontend`
- `curl -fsS http://localhost:8081/api/health` -> healthy
- `curl -fsS http://localhost:8081/api/readiness` -> ready
- `docker exec tsushin-backend python -m pytest -q -o addopts='' tests/test_gmail_send_phase3_checkpoint.py` -> `6 passed, 2 warnings`
- Headed Playwright validation on `https://localhost/hub` confirmed:
  - Gmail setup wizard copy advertises `Read + outbound (gmail.readonly + gmail.send)`
  - reauthorization guidance explains how legacy read-only integrations upgrade
  - 0 browser console errors; only repeated CSS preload warnings

Private evidence was saved under `.private/qa/v0.7.0/phase-3-1-checkpoint/`.

## Remaining before Phase 3.1 is complete

- Live outbound verification against the Phase 0.5 Gmail account
- API or agent-chat proof that a sent message lands in Sent and is discoverable through Gmail read surfaces
- The downstream Email Trigger + triage managed-flow work remains blocked on later Phase 3 slices
