# v0.7.0 Phase 0.5 QA Summary

Status: in progress. ASR fixtures and the Gmail release-gate harness are in
place, but Phase 0.5 remains blocked until a dedicated Gmail integration is
re-authorized with `gmail.readonly + gmail.send`, exported to the canonical
fixture path, and validated with zero skips.

| Gate | Result | Evidence |
| --- | --- | --- |
| ASR fixtures generated | PASS | `backend/tests/fixtures/asr_test_en.ogg` and `backend/tests/fixtures/asr_test_pt.ogg` were generated from real speech via macOS `say` and converted to mono Ogg/Opus. |
| ASR probe metadata | PASS | Host/container `ffprobe` reports `codec_name=opus`, `channels=1`, with durations `4.92s` and `6.38s`. |
| ASR non-silence | PASS | `backend/tests/test_phase0_5_fixtures.py` decodes both clips with `ffmpeg` and asserts peak amplitude `> 0.01`. |
| Gmail fixture loader/test harness | PASS | Added `backend/tests/conftest.py`, `backend/tests/test_gmail_oauth_fixture.py`, and `backend/dev_tests/export_gmail_oauth_fixture.py` with a shared canonical fixture path. |
| Gmail release gate semantics | PASS | Missing `TSN_GMAIL_FIXTURE_KEY`, missing `backend/tests/fixtures/gmail_oauth.enc`, or decrypt failure now fail the Gmail fixture test instead of skipping it. |
| Gmail send-scoped re-authorization path | PASS | `POST /api/hub/google/gmail/oauth/authorize?include_send_scope=true`, `POST /api/hub/google/reauthorize/{id}?include_send_scope=true`, and the Hub Gmail re-authorize button now request `gmail.send` in addition to the default Gmail scopes. |
| Gmail send-scoped source token | BLOCKED | Live Gmail integrations `1` and `4` are healthy but only hold `gmail.readonly` scope. The reauthorize flow now reaches a Google consent URL with `gmail.send`, but Google shows the unverified-app warning before consent, so the final grant requires a user handoff. Phase 0.5 cannot close until that grant succeeds and the real token is exported to `backend/tests/fixtures/gmail_oauth.enc`. |
| Backend regression slice | PENDING | Current fail-closed probe is `2 passed, 1 error` with **zero skips** (`pytest -q -o addopts='' backend/tests/test_phase0_5_fixtures.py backend/tests/test_gmail_oauth_fixture.py`); Phase 0.5 closes only after the real fixture turns that final error into a pass. |
| Health / readiness | PASS | After a no-cache backend rebuild from `/Users/vinicios/code/tsushin`, `/api/health` returned `healthy` and `/api/readiness` returned `ready`. |
| Backend log tail | PASS | `docker logs --tail 300 tsushin-backend | rg \"ERROR|Traceback|CRITICAL|FATAL\"` returned no matches in the reviewed window. |
| Visual baseline suite | PASS | `npm --prefix frontend run test:visual` reran cleanly with `5 passed` before and after the no-cache frontend rebuild for the Hub Gmail reauthorize change. |
| Fan-out readiness | BLOCKED | No worktrees or `track/*` branches should be created until the updated Phase 0.5 Gmail gate passes with zero skips. |

Notes:
- This summary is intentionally sanitized and does not expose client secrets,
  refresh tokens, or encryption keys.
- The Google OAuth attempt reached the consent flow for integration `1`
  (`movl2007@gmail.com`) with `gmail.send` requested, but the browser stopped at
  Google's "unverified app" warning. That safety barrier was not bypassed
  automatically.
- Existing repo-wide frontend lint failures remain pre-existing debt and were
  not touched by Phase 0.5 work.
