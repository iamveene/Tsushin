"""Add custom skills tables for tenant-created skills.

Phase 22: Custom Skills Foundation.
Creates custom_skill, custom_skill_version, agent_custom_skill, and
custom_skill_execution tables, plus RBAC permissions for custom skill management.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create custom skill tables and add RBAC permissions (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. custom_skill
    if 'custom_skill' not in existing_tables:
        op.create_table(
            'custom_skill',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('source', sa.String(20), nullable=False, server_default='tenant'),
            sa.Column('slug', sa.String(100), nullable=False),
            sa.Column('name', sa.String(200), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('icon', sa.String(10), nullable=True),
            sa.Column('skill_type_variant', sa.String(20), nullable=False, server_default='instruction'),
            sa.Column('execution_mode', sa.String(20), nullable=False, server_default='tool'),
            sa.Column('instructions_md', sa.Text(), nullable=True),
            sa.Column('script_entrypoint', sa.String(50), nullable=True),
            sa.Column('script_content', sa.Text(), nullable=True),
            sa.Column('script_language', sa.String(20), nullable=True),
            sa.Column('script_content_hash', sa.String(64), nullable=True),
            sa.Column('input_schema', sa.JSON(), server_default='{}'),
            sa.Column('output_schema', sa.JSON(), nullable=True),
            sa.Column('config_schema', sa.JSON(), server_default='[]'),
            sa.Column('trigger_mode', sa.String(20), server_default='llm_decided'),
            sa.Column('trigger_keywords', sa.JSON(), server_default='[]'),
            sa.Column('priority', sa.Integer(), server_default='50'),
            sa.Column('sentinel_profile_id', sa.Integer(), nullable=True),
            sa.Column('timeout_seconds', sa.Integer(), nullable=False, server_default='30'),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('scan_status', sa.String(20), server_default='pending'),
            sa.Column('last_scan_result', sa.JSON(), nullable=True),
            sa.Column('version', sa.String(20), nullable=False, server_default='1.0.0'),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'slug', name='uq_custom_skill_tenant_slug'),
        )

    # 2. custom_skill_version
    if 'custom_skill_version' not in existing_tables:
        op.create_table(
            'custom_skill_version',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('custom_skill_id', sa.Integer(),
                       sa.ForeignKey('custom_skill.id', ondelete='CASCADE'),
                       nullable=False, index=True),
            sa.Column('version', sa.String(20), nullable=False),
            sa.Column('snapshot_json', sa.JSON(), nullable=False),
            sa.Column('changed_by', sa.Integer(), nullable=True),
            sa.Column('changed_at', sa.DateTime(), server_default=sa.func.now()),
        )

    # 3. agent_custom_skill
    if 'agent_custom_skill' not in existing_tables:
        op.create_table(
            'agent_custom_skill',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('agent_id', sa.Integer(),
                       sa.ForeignKey('agent.id', ondelete='CASCADE'),
                       nullable=False, index=True),
            sa.Column('custom_skill_id', sa.Integer(),
                       sa.ForeignKey('custom_skill.id', ondelete='CASCADE'),
                       nullable=False, index=True),
            sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('config', sa.JSON(), server_default='{}'),
            sa.Column('priority_override', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('agent_id', 'custom_skill_id', name='uq_agent_custom_skill'),
        )

    # 4. custom_skill_execution
    if 'custom_skill_execution' not in existing_tables:
        op.create_table(
            'custom_skill_execution',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('agent_id', sa.Integer(), nullable=True),
            sa.Column('custom_skill_id', sa.Integer(),
                       sa.ForeignKey('custom_skill.id', ondelete='SET NULL'),
                       nullable=True),
            sa.Column('skill_name', sa.String(200), nullable=True),
            sa.Column('input_json', sa.JSON(), nullable=True),
            sa.Column('output', sa.Text(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
            sa.Column('execution_time_ms', sa.Integer(), nullable=True),
            sa.Column('sentinel_result', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )

    # 5. RBAC permissions for custom skills
    _seed_custom_skill_permissions(bind)


def _seed_custom_skill_permissions(bind):
    """Add RBAC permissions for custom skills (idempotent)."""
    from sqlalchemy.orm import Session
    session = Session(bind=bind)

    try:
        from models_rbac import Permission, Role, RolePermission

        permissions_data = [
            ("skills.custom.create", "skills.custom", "create", "Create custom skills"),
            ("skills.custom.read", "skills.custom", "read", "View custom skills"),
            ("skills.custom.execute", "skills.custom", "execute", "Execute custom skills"),
            ("skills.custom.delete", "skills.custom", "delete", "Delete custom skills"),
        ]

        # owner and admin get all 4 permissions; member gets read + execute
        role_assignments = {
            "owner": ["skills.custom.create", "skills.custom.read", "skills.custom.execute", "skills.custom.delete"],
            "admin": ["skills.custom.create", "skills.custom.read", "skills.custom.execute", "skills.custom.delete"],
            "member": ["skills.custom.read", "skills.custom.execute"],
        }

        for name, resource, action, description in permissions_data:
            existing_perm = session.query(Permission).filter(Permission.name == name).first()
            if not existing_perm:
                perm = Permission(name=name, resource=resource, action=action, description=description)
                session.add(perm)
                session.flush()

                for role_name, role_perms in role_assignments.items():
                    if name in role_perms:
                        role = session.query(Role).filter(Role.name == role_name).first()
                        if role:
                            rp = RolePermission(role_id=role.id, permission_id=perm.id)
                            session.add(rp)
            else:
                # Ensure permission is assigned to correct roles
                for role_name, role_perms in role_assignments.items():
                    if name in role_perms:
                        role = session.query(Role).filter(Role.name == role_name).first()
                        if role:
                            existing_mapping = session.query(RolePermission).filter(
                                RolePermission.role_id == role.id,
                                RolePermission.permission_id == existing_perm.id
                            ).first()
                            if not existing_mapping:
                                rp = RolePermission(role_id=role.id, permission_id=existing_perm.id)
                                session.add(rp)

        session.commit()
    except Exception as e:
        session.rollback()
        print(f"[RBAC] Warning: Failed to seed custom skill permissions: {e}")
    finally:
        session.close()


def downgrade() -> None:
    """Remove custom skill tables."""
    op.drop_table('custom_skill_execution')
    op.drop_table('agent_custom_skill')
    op.drop_table('custom_skill_version')
    op.drop_table('custom_skill')
