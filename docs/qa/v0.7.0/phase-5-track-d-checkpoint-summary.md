# v0.7.0 Phase 5 Track D Checkpoint Summary

Date: 2026-04-23
Branch: `release/0.7.0`
Merged checkpoint: `merge: Track D Whisper ASR checkpoint`

## Scope landed

- Landed the backend-only Track D checkpoint for Whisper/Speaches ASR:
  - Added the ASR provider abstraction in `backend/hub/providers/{asr_provider.py,asr_registry.py,openai_asr_provider.py,whisper_asr_provider.py}` and wired it into the app lifespan in `backend/app.py`.
  - Added Alembic `0048_add_asr_instances.py` plus the tenant-scoped `ASRInstance` model in `backend/models.py`.
  - Added `backend/services/whisper_instance_service.py` and `backend/services/whisper_container_manager.py` for instance lifecycle, authenticated warm-up, startup reconciliation, and managed-container orchestration on the reserved `6400-6499` Whisper/Speaches port range.
  - Added `backend/api/routes_asr_instances.py` for `/api/asr/instances/*`.
  - Updated `backend/agent/skills/audio_transcript.py` so the skill prefers a configured tenant `asr_instance_id` and falls back to the existing OpenAI Whisper path on misses or runtime failures.
- Added focused backend regression coverage in:
  - `backend/tests/test_whisper_container_manager.py`
  - `backend/tests/test_audio_transcript_skill_asr.py`

## Validation

- Asserted the SSL compose pin via `.env`:
  - `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml`
- `docker compose build --no-cache backend` -> completed successfully
- `docker compose up -d backend`
- `docker compose ps` -> backend healthy
- `curl -fsS http://localhost:8081/api/health` -> healthy
- `curl -fsS http://localhost:8081/api/readiness` -> ready
- `docker logs --tail 200 tsushin-backend | rg "ERROR|Traceback|CRITICAL|FATAL"` -> no matches in the reviewed startup window
- `docker exec tsushin-backend python -m pytest -q -p no:cacheprovider -o addopts='' tests/test_whisper_container_manager.py tests/test_audio_transcript_skill_asr.py` -> `11 passed, 1 warning`

Private evidence was saved under `.private/qa/v0.7.0/phase-5-track-d-checkpoint/`.

## Remaining before Phase 5 is complete

- Frontend client and UI delivery for `/settings/asr` and the agent/audio selector flows
- End-to-end tenant verification that an unchanged tenant still uses OpenAI Whisper by default
- End-to-end tenant verification that a provisioned local Speaches/Whisper instance is selected and used successfully
- Fresh-install validation for Whisper/Speaches provisioning on the Ubuntu VM path
