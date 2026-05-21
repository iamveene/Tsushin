"""backfill repository team completion notifications

Revision ID: 0099
Revises: 0098
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0099"
down_revision: Union[str, None] = "0098"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE agent_team AS team
        SET
            description = CONCAT(
                BTRIM(
                    REGEXP_REPLACE(
                        COALESCE(NULLIF(BTRIM(team.description), ''), 'Automated repository review team.'),
                        '\\s*\\[notify:contact:\\d+\\]\\s*',
                        ' ',
                        'g'
                    )
                ),
                ' [notify:contact:',
                contact.id::text,
                ']'
            ),
            updated_at = NOW()
        FROM user_contact_mapping AS mapping
        JOIN contact AS contact ON contact.id = mapping.contact_id
        WHERE team.created_by_user_id = mapping.user_id
          AND contact.tenant_id = team.tenant_id
          AND contact.is_active IS TRUE
          AND (
              NULLIF(BTRIM(contact.phone_number), '') IS NOT NULL
              OR NULLIF(BTRIM(contact.whatsapp_id), '') IS NOT NULL
          )
          AND team.status <> 'archived'
          AND COALESCE(team.description, '') !~ '\\[notify:contact:\\d+\\]'
          AND COALESCE(team.description, '') ILIKE 'Automated repository review team for %'
          AND EXISTS (
              SELECT 1
              FROM agent_team_trigger AS trigger
              WHERE trigger.tenant_id = team.tenant_id
                AND trigger.team_id = team.id
                AND trigger.trigger_kind IN ('github', 'gitlab')
                AND trigger.is_enabled IS TRUE
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE agent_team
        SET
            description = NULLIF(
                BTRIM(
                    REGEXP_REPLACE(
                        description,
                        '\\s*\\[notify:contact:\\d+\\]\\s*',
                        ' ',
                        'g'
                    )
                ),
                ''
            ),
            updated_at = NOW()
        WHERE COALESCE(description, '') ~ '\\[notify:contact:\\d+\\]'
        """
    )
