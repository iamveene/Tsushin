"""
V060-MEM-025: Add okg_detection_mode to sentinel_profile for OKG-specific blocking.

Fresh installs default detect_only for general chat, but OKG persistent stores
need stricter protection. This separate field allows blocking OKG memory poisoning
even when chat analysis is in detect-only mode.

Revision ID: 0030
Revises: 0029
"""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('sentinel_profile')]

    if 'okg_detection_mode' not in columns:
        op.add_column(
            'sentinel_profile',
            sa.Column(
                'okg_detection_mode',
                sa.String(20),
                nullable=False,
                server_default='block',
                comment='V060-MEM-025: OKG-specific detection mode (default: block)'
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('sentinel_profile')]

    if 'okg_detection_mode' in columns:
        op.drop_column('sentinel_profile', 'okg_detection_mode')
