# v0.7.0 Wave 3A Track C/F QA Summary

Date: 2026-04-23
Branch: `release/0.7.0`

## Scope

Wave 3A merged Track C UI readiness and the first Track F agentic-loop core onto `release/0.7.0`.

Track C adds read-only UI/client coverage for continuous agents, continuous runs, wake events, trigger detail pages, conversational channel routing rules, Watcher `continuous_run` activity, and onboarding step 16.

Track F adds the linear `0049 -> 0057 -> 0058` migration continuation, structured tool-result scratchpad support, bounded DATA reuse, follow-up detection, API v1 scratchpad opt-in/redaction, and `max_agentic_rounds=1` compatibility.

## Validation

- Root backend no-cache rebuild completed and backend restarted without using `docker-compose down`.
- Containers healthy: backend, frontend, postgres, proxy.
- `/api/health` passed through direct backend and HTTPS proxy.
- Alembic current/head: `0058 (head)`.
- M-3 audit query found `0` legacy `agent_skill.config` rows using the new Track F toggle keys.
- Track F/provider focused container tests: `20 passed, 4 deselected, 17 warnings`.
- A2/email/default-agent focused container tests: `15 passed, 2 warnings`.
- Live API smoke: `/api/continuous-agents`, `/api/continuous-runs`, `/api/wake-events` all returned `200`.
- Live `movl` two-turn proof: first turn used `skill:gmail_operation`; second turn returned `tool_used=null`; thread scratchpad length remained `1`.
- Browser smoke loaded Hub Communication, `/continuous-agents`, `/hub/wake-events`, webhook trigger detail, `/settings/default-agents`, `/settings/asr`, and Watcher with 0 console errors.
- Targeted ESLint passed for Track C, Watcher, and onboarding files.
- Backend log scan since restart found no `ERROR|CRITICAL|FATAL|Traceback|Exception`.

## Residual Risks

- Full frontend typecheck remains blocked by existing repo-wide TypeScript debt outside this Wave 3A slice.
- Continuous-agent create/edit/delete UI remains deferred until backend write APIs exist.
- Track B trigger adapter implementation remains deferred until this checkpoint is pushed and cleanup is complete.
- Gmail live send/Sent-folder release gate remains blocked until the fixture is reauthorized with `gmail.compose` or a broader compatible scope.
