# v0.7.0 Phase 0 QA Summary

Status: Phase 0 implementation validated with one pre-existing frontend lint
baseline exception.

Private evidence is stored locally under `.private/qa/v0.7.0/` and is not
committed. This sanitized summary is the committed pointer for reviewers.

| Gate | Result | Evidence |
| --- | --- | --- |
| Branch | PASS | Phase 0 began from `develop @ 8135ff1`; final handoff branch is `release/0.7.0`. The accidental `release/0.5.0` push was restored to its prior old-release commit. |
| Preflight | PASS | `docker-compose ps` healthy, `/api/health` healthy, `/api/readiness` ready, Alembic `0044 (head)` before applying 0045. |
| Database backup | PASS | Primary DB backed up before migration to private artifact `.private/qa/v0.7.0/tsushin_phase0_pre0045.dump`. |
| Migration round-trip | PASS | Scratch DB restore completed, then `upgrade 0045`, `downgrade 0044`, `upgrade head`, and `current` reported `0045 (head)`. |
| Live migration | PASS | Rebuilt live backend applied `0044 -> 0045`; `docker exec tsushin-backend /opt/venv/bin/alembic current` reports `0045 (head)`. |
| Backend tests | PASS | `docker exec tsushin-backend python -m pytest -o addopts='' tests/test_phase0_foundation.py tests/test_searxng_container_manager.py -q` -> `17 passed, 2 warnings`. |
| Sentinel endpoint | PASS | Authenticated `GET /api/sentinel/detection-types` returned 9 entries including `continuous_agent_action_approval`. |
| Frontend visual tests | PASS | `npm --prefix frontend run test:visual:update` generated deterministic baselines; `npm --prefix frontend run test:visual` -> `5 passed`. |
| Frontend targeted lint | PASS | `npm exec eslint playwright.config.ts tests/visual --max-warnings=0` from `frontend/` passed for the new visual-test files. |
| Frontend full lint | BASELINE FAIL | `npm --prefix frontend run lint` still fails with the existing repo-wide baseline: 974 errors and 229 warnings, primarily legacy `any` usage and React compiler/ref rules outside the Phase 0 files. |
| Safe rebuild | PASS | `.env` verified `COMPOSE_FILE=docker-compose.yml:docker-compose.ssl.yml`; Compose `up --no-cache` was unavailable, so the equivalent `docker-compose build --no-cache backend frontend` followed by `docker-compose up -d backend frontend` was used from the repository root. |
| Service health | PASS | Post-rebuild `docker-compose ps` shows backend, frontend, postgres, proxy healthy/up; `/api/health` healthy and `/api/readiness` ready. |
| Backend logs | PASS | Post-rebuild backend logs reviewed; no `ERROR`, `Traceback`, `RemoteProtocolError`, `Exception`, `CRITICAL`, or `FATAL` matches in the checked window. Existing warnings include MCP legacy path, Google Generative AI deprecation, and JWT HMAC key length. |
| Diff hygiene | PASS | `git diff --check` passed. |

Notes:
- Existing local log artifacts were left untouched and untracked:
  `console-hub-warnings.txt`, `hub-all-requests.txt`, and
  `hub-network-errors.txt`.
- No `track/*` branches or worktrees were created during Phase 0.
