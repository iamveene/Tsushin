# v0.7.0 Phase 1 Backend Checkpoint Summary

Date: 2026-04-23
Branch: `release/0.7.0`
Merged checkpoints: `merge: Track F0 parser prep`, `merge: Track A backend checkpoint`

## Scope landed

- Track A backend-first Phase 1 checkpoint:
  - Introduced `EntryPoint`, `Channel`, `Trigger`, and `TriggerEvent`.
  - Moved webhook into the trigger catalog as `WebhookTrigger`.
  - Added `GET /api/triggers` and made `/api/triggers/webhook/*` the canonical webhook management surface.
  - Added Alembic `0046_add_default_agent_fks.py` and `backend/services/default_agent_service.py`.
  - Split Hub Communication into **Communication Channels** and **Webhook Triggers**.
  - Removed webhook from the guided `+ Add Channel` flow.
- Track F0 prep checkpoint:
  - Extracted tool-call parser helpers in `backend/agent/agent_service.py`.
  - Added reserved-key collision auditing in `backend/agent/skills/skill_manager.py`.

## Validation

- `docker-compose build --no-cache backend frontend`
- `docker-compose up -d backend frontend`
- `curl -fsS http://localhost:8081/api/health` -> healthy
- `curl -fsS http://localhost:8081/api/readiness` -> ready
- `docker exec tsushin-backend python -m pytest -q -o addopts='' tests/test_channel_trigger_split.py tests/test_default_agent_service.py` -> `6 passed, 2 warnings`
- `python3 -m pytest -q -o addopts='' backend/tests/test_wizard_drift.py -k 'channel_catalog or channels_wizard'` -> `2 passed, 12 deselected`
- `python3 -m pytest -q -o addopts='' backend/tests/test_provider_instance_hardening.py` -> `6 passed, 20 warnings`
- Headed Playwright validation on `https://localhost/hub` confirmed:
  - separate **Communication Channels** and **Webhook Triggers** sections
  - `+ New Webhook Trigger` visible in the trigger section
  - `+ Add Channel` modal offers WhatsApp, Telegram, Slack, Discord, and Gmail (inbound), but not webhook
  - 0 console errors; only repeated CSS preload warnings

Private evidence was saved under `.private/qa/v0.7.0/phase-1-checkpoint/`.

## Remaining before Phase 1 is complete

- `/settings/default-agents` UI and its persistence flows
- shared `Wizard` primitive
- Email Trigger wizard
- final Phase 1 exit-gate rerun, including the trigger inbound smoke expected by the full plan
