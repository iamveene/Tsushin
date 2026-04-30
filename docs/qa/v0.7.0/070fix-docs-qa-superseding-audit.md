# v0.7.0 070fix Docs/QA Superseding Audit

Date: 2026-04-28

This note supersedes older docs/QA wording for the 070fix ownership model. It does not rewrite historical QA evidence or screenshots.

## Checked

- Reconciled `.private/070fix_plan.md` into a source-line checklist against every section of `.private/070fix.md`.
- Updated current docs to state the final ownership model:
  - Hub owns configuration: Channels, Triggers, Tool APIs, Productivity.
  - Watcher owns monitoring: Wake Events and Continuous Agents.
  - Studio owns agent creation, including the continuous-agent wake-mode entry point.
  - Flows own scheduled/recurring execution and trigger output configuration.
- Removed current user-facing guidance for standalone schedule triggers, trigger-local GitHub credentials, and legacy trigger-local notification cards.
- Left older changelog and QA evidence intact when it is clearly historical.

## Remaining Risk Areas

- Backend/frontend code was intentionally not edited in this docs-only slice.
- Historical QA screenshots and old changelog entries still show pre-070fix routes and labels.
- Compatibility redirects or deprecated service references may still exist in runtime code and must be judged by final product behavior, not by docs search alone.

## Final Validation Expectations

- Browser smoke on the active stack confirms Hub > Channels and Hub > Triggers contain only their owned configuration surfaces.
- Browser smoke confirms Watcher exposes Wake Events at `/wake-events` and Continuous Agents as monitoring/operations surfaces.
- Browser smoke confirms Studio New Agent is the creation path for continuous agents.
- Browser/API checks confirm Flows own scheduled/recurring execution and no standalone schedule-trigger product appears.
- Browser/API checks confirm Jira/GitHub trigger creation links existing or newly-created Hub integrations, with no trigger-local credential fields or trigger-level connection-test buttons.
- Browser/API checks confirm trigger output configuration is handled by wired/generated Flows, with no legacy notification card on Jira or Email trigger details.
