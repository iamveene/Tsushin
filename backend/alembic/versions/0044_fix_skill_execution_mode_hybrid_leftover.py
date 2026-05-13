"""Fix stale execution_mode="hybrid" leftover in agent_skill.config

Commit b1b1bb9 (2026-03-29) deprecated legacy keyword triggering by flipping
the class-level execution_mode attribute from "hybrid" to "tool" on 10 skills.
However, for four of those skills (gmail, flight_search, image, search) the
commit left the value "hybrid" inside get_default_config() / get_config_schema(),
so any agent whose skill row was seeded from that default ended up with
config.execution_mode == "hybrid" persisted in the DB.

At runtime, config.get('execution_mode', self.execution_mode) returns "hybrid"
(the stored value wins over the class attr), which re-activates the legacy
keyword-routing path — the whole reason that commit existed in the first place.

Symptom: mentioning "email" to an agent with Gmail skill caused the skill to
fire in legacy mode, which short-circuits the LLM (skip_ai=True) and dumps a
hardcoded 10-email list. Follow-up reasoning ("qual desses é importante?")
never reached the LLM because the keyword "email" re-triggered the skill.

This migration:
1. Updates existing rows where config.execution_mode = 'hybrid' for the four
   affected skill types to 'tool'. Preserves the rest of the config intact.
2. Leaves rows where execution_mode is explicitly set to 'legacy' or 'hybrid'
   by the user via the Skill config UI untouched IF they are of skill types
   that are legitimately hybrid (agent_switcher, shell, etc.) — we scope this
   migration by skill_type so only the four known-stale defaults are swept.

Agent_switcher, shell, and any future legitimately-hybrid skill are NOT
touched — we match on skill_type explicitly.

Revision ID: 0044
Revises: 0043
Create Date: 2026-04-22
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0044'
down_revision: Union[str, None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


AFFECTED_SKILLS = ('gmail', 'flight_search', 'image', 'web_search')


def upgrade() -> None:
    """
    Flip config.execution_mode from 'hybrid' to 'tool' on the four stale-default
    skill types. Uses JSONB cast since agent_skill.config is declared as
    Column(JSON) in models.py (not JSONB), but PostgreSQL allows casting both
    ways for path operations.

    The update is idempotent: re-running is a no-op because the WHERE clause
    filters on the current 'hybrid' value.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        # JSONB path update. Cast to jsonb for jsonb_set, cast back to json
        # to match the declared column type.
        bind.exec_driver_sql(
            """
            UPDATE agent_skill
            SET config = jsonb_set(
                    config::jsonb,
                    '{execution_mode}',
                    '"tool"'::jsonb,
                    false
                )::json,
                updated_at = now()
            WHERE skill_type = ANY(%(skills)s)
              AND config IS NOT NULL
              AND (config::jsonb ->> 'execution_mode') = 'hybrid'
            """,
            {'skills': list(AFFECTED_SKILLS)}
        )
    else:
        # SQLite fallback: JSON1 extension is usually compiled in. If it's not,
        # this will error and the operator can update manually — SQLite is only
        # used for dev/CI and the symptoms are obvious enough.
        skills_csv = ','.join(f"'{s}'" for s in AFFECTED_SKILLS)
        bind.exec_driver_sql(
            f"""
            UPDATE agent_skill
            SET config = json_set(config, '$.execution_mode', 'tool'),
                updated_at = CURRENT_TIMESTAMP
            WHERE skill_type IN ({skills_csv})
              AND config IS NOT NULL
              AND json_extract(config, '$.execution_mode') = 'hybrid'
            """
        )


def downgrade() -> None:
    """
    Revert: flip execution_mode back to 'hybrid' on the same four skill types.
    Matches the original buggy state. Provided for completeness; in practice
    there is no reason to downgrade this — the hybrid default was a bug.
    """
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == 'postgresql':
        bind.exec_driver_sql(
            """
            UPDATE agent_skill
            SET config = jsonb_set(
                    config::jsonb,
                    '{execution_mode}',
                    '"hybrid"'::jsonb,
                    false
                )::json,
                updated_at = now()
            WHERE skill_type = ANY(%(skills)s)
              AND config IS NOT NULL
              AND (config::jsonb ->> 'execution_mode') = 'tool'
            """,
            {'skills': list(AFFECTED_SKILLS)}
        )
    else:
        skills_csv = ','.join(f"'{s}'" for s in AFFECTED_SKILLS)
        bind.exec_driver_sql(
            f"""
            UPDATE agent_skill
            SET config = json_set(config, '$.execution_mode', 'hybrid'),
                updated_at = CURRENT_TIMESTAMP
            WHERE skill_type IN ({skills_csv})
              AND config IS NOT NULL
              AND json_extract(config, '$.execution_mode') = 'tool'
            """
        )
