# v0.7.0 Phase 0.5 QA Summary

Status: complete. ASR fixtures and the Gmail release-gate harness are in
place, the dedicated Gmail integration was re-authorized with
`gmail.readonly + gmail.send`, the canonical encrypted fixture was exported to
`backend/tests/fixtures/gmail_oauth.enc`, and the release-gate slice reran with
zero skips.

| Gate | Result | Evidence |
| --- | --- | --- |
| ASR fixtures generated | PASS | `backend/tests/fixtures/asr_test_en.ogg` and `backend/tests/fixtures/asr_test_pt.ogg` were generated from real speech via macOS `say` and converted to mono Ogg/Opus. |
| ASR probe metadata | PASS | Host/container `ffprobe` reports `codec_name=opus`, `channels=1`, with durations `4.92s` and `6.38s`. |
| ASR non-silence | PASS | `backend/tests/test_phase0_5_fixtures.py` decodes both clips with `ffmpeg` and asserts peak amplitude `> 0.01`. |
| Gmail fixture loader/test harness | PASS | Added `backend/tests/conftest.py`, `backend/tests/test_gmail_oauth_fixture.py`, and `backend/dev_tests/export_gmail_oauth_fixture.py` with a shared canonical fixture path. The exporter now resolves the Google token-encryption key from the configured runtime store when env-only lookup is unavailable. |
| Gmail release gate semantics | PASS | Missing `TSN_GMAIL_FIXTURE_KEY`, missing `backend/tests/fixtures/gmail_oauth.enc`, or decrypt failure now fail the Gmail fixture test instead of skipping it. |
| Gmail send-scoped re-authorization path | PASS | `POST /api/hub/google/gmail/oauth/authorize?include_send_scope=true`, `POST /api/hub/google/reauthorize/{id}?include_send_scope=true`, and the Hub Gmail re-authorize button now request `gmail.send` in addition to the default Gmail scopes. |
| Gmail send-scoped source token | PASS | Live Gmail integration `1` now holds both `gmail.readonly` and `gmail.send`. The canonical fixture export succeeded and wrote `backend/tests/fixtures/gmail_oauth.enc` using the local-only `TSN_GMAIL_FIXTURE_KEY`. |
| Backend regression slice | PASS | `docker exec tsushin-backend /opt/venv/bin/python -m pytest -q -o addopts='' tests/test_phase0_5_fixtures.py tests/test_gmail_oauth_fixture.py` -> `3 passed, 1 warning` with **zero skips**. The live slice authenticated, listed mail, sent a verification email, and confirmed it in Sent. |
| Health / readiness | PASS | After a no-cache backend rebuild from `/Users/vinicios/code/tsushin`, `/api/health` returned `healthy` and `/api/readiness` returned `ready`. |
| Backend log tail | PASS | `docker logs --tail 300 tsushin-backend | rg \"ERROR|Traceback|CRITICAL|FATAL\"` returned no matches in the reviewed window. |
| Visual baseline suite | PASS | `npm --prefix frontend run test:visual` reran cleanly with `5 passed` before and after the no-cache frontend rebuild for the Hub Gmail reauthorize change. |
| Fan-out readiness | PASS | Before unlock, `git worktree list` still showed only the main `release/0.7.0` tree. After the Phase 0.5 slice passed with zero skips, Wave 1 worktrees were created for tracks A, D, E, F, and G under `/Users/vinicios/.claude-worktrees/tsushin/v0.7.0/`. |

Notes:
- This summary is intentionally sanitized and does not expose client secrets,
  refresh tokens, or encryption keys.
- The committed fixture remains encrypted; only the local `TSN_GMAIL_FIXTURE_KEY`
  can decrypt it. No client secrets, refresh tokens, or encryption keys are
  exposed in git.
- Existing repo-wide frontend lint failures remain pre-existing debt and were
  not touched by Phase 0.5 work.
