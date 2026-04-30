"""disable removed schedule trigger bindings/subscriptions

Revision ID: 0074
Revises: 0073
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0074"
down_revision: Union[str, None] = "0073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "flow_trigger_binding" in tables:
        bind.execute(
            sa.text(
                """
                UPDATE flow_trigger_binding
                SET is_active = :inactive,
                    updated_at = CURRENT_TIMESTAMP
                WHERE trigger_kind = 'schedule'
                  AND is_active = :active
                """
            ),
            {"inactive": False, "active": True},
        )

    if "continuous_subscription" in tables:
        bind.execute(
            sa.text(
                """
                UPDATE continuous_subscription
                SET status = 'disabled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE channel_type = 'schedule'
                  AND status != 'disabled'
                """
            )
        )
        bind.execute(
            sa.text(
                """
                UPDATE continuous_subscription
                SET status = 'disabled',
                    updated_at = CURRENT_TIMESTAMP
                WHERE status != 'disabled'
                  AND CAST(action_config AS TEXT) LIKE '%whatsapp_notification%'
                """
            )
        )


def downgrade() -> None:
    # Schedule Trigger was intentionally removed. Re-enabling disabled rows on
    # downgrade could wake agents unexpectedly, so downgrade is conservative.
    return None
