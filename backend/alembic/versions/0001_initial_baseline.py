"""Initial baseline: create all tables from ORM models.

Revision ID: 0001
Revises: None
Create Date: 2026-03-26
"""
from typing import Sequence, Union
import sys
import os

from alembic import op
import sqlalchemy as sa

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# revision identifiers
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from SQLAlchemy ORM metadata.

    This uses Base.metadata.create_all which is idempotent —
    it only creates tables that don't already exist.
    """
    from models import Base
    import models_rbac  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(bind)


def downgrade() -> None:
    """Drop all ORM-managed tables."""
    from models import Base
    import models_rbac  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind)
