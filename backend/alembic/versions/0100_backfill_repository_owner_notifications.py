"""backfill repository team notifications from tenant owners

Revision ID: 0100
Revises: 0099
Create Date: 2026-05-21
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "0100"
down_revision: Union[str, None] = "0099"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        WITH owner_contacts AS (
            SELECT DISTINCT ON (app_user.tenant_id)
                app_user.tenant_id,
                contact.id AS contact_id
            FROM "user" AS app_user
            JOIN user_role AS user_role ON user_role.user_id = app_user.id
            JOIN role AS role ON role.id = user_role.role_id
            JOIN user_contact_mapping AS mapping ON mapping.user_id = app_user.id
            JOIN contact AS contact ON contact.id = mapping.contact_id
            WHERE role.name = 'owner'
              AND app_user.is_active IS TRUE
              AND contact.tenant_id = app_user.tenant_id
              AND contact.is_active IS TRUE
              AND COALESCE(contact.role, 'user') <> 'agent'
              AND (
                  NULLIF(BTRIM(contact.phone_number), '') IS NOT NULL
                  OR NULLIF(BTRIM(contact.whatsapp_id), '') IS NOT NULL
              )
            ORDER BY
                app_user.tenant_id,
                app_user.last_login_at DESC NULLS LAST,
                app_user.id ASC
        )
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
                owner_contacts.contact_id::text,
                ']'
            ),
            updated_at = NOW()
        FROM owner_contacts
        WHERE owner_contacts.tenant_id = team.tenant_id
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
          AND COALESCE(description, '') ILIKE 'Automated repository review team for %'
        """
    )
