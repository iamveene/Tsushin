"""Add MCP server integration tables.

Phase 22.4: MCP Server Integration.
Creates mcp_server_config, mcp_discovered_tool, and mcp_server_health
tables, plus RBAC permission for MCP server management.

Revision ID: 0008
Revises: 0007
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create MCP server tables and add RBAC permissions (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. mcp_server_config
    if 'mcp_server_config' not in existing_tables:
        op.create_table(
            'mcp_server_config',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('server_name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('transport_type', sa.String(20), nullable=False),
            sa.Column('server_url', sa.String(500), nullable=True),
            sa.Column('auth_type', sa.String(20), server_default='none'),
            sa.Column('auth_token_encrypted', sa.Text(), nullable=True),
            sa.Column('auth_header_name', sa.String(100), nullable=True),
            sa.Column('stdio_binary', sa.String(100), nullable=True),
            sa.Column('stdio_args', sa.JSON(), server_default='[]'),
            sa.Column('trust_level', sa.String(20), server_default='untrusted'),
            sa.Column('connection_status', sa.String(20), server_default='disconnected'),
            sa.Column('max_retries', sa.Integer(), server_default='3'),
            sa.Column('timeout_seconds', sa.Integer(), server_default='30'),
            sa.Column('idle_timeout_seconds', sa.Integer(), server_default='300'),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('last_connected_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'server_name', name='uq_mcp_server_tenant_name'),
        )

    # 2. mcp_discovered_tool
    if 'mcp_discovered_tool' not in existing_tables:
        op.create_table(
            'mcp_discovered_tool',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('server_id', sa.Integer(),
                       sa.ForeignKey('mcp_server_config.id', ondelete='CASCADE'),
                       nullable=False, index=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('tool_name', sa.String(200), nullable=False),
            sa.Column('namespaced_name', sa.String(300), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('input_schema', sa.JSON(), server_default='{}'),
            sa.Column('is_enabled', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('scan_status', sa.String(20), server_default='pending'),
            sa.Column('discovered_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('server_id', 'tool_name', name='uq_mcp_tool_server_name'),
        )

    # 3. mcp_server_health
    if 'mcp_server_health' not in existing_tables:
        op.create_table(
            'mcp_server_health',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('server_id', sa.Integer(),
                       sa.ForeignKey('mcp_server_config.id', ondelete='CASCADE'),
                       nullable=False, index=True),
            sa.Column('check_type', sa.String(20), nullable=False),
            sa.Column('success', sa.Boolean(), nullable=False),
            sa.Column('latency_ms', sa.Integer(), nullable=True),
            sa.Column('error_message', sa.Text(), nullable=True),
            sa.Column('checked_at', sa.DateTime(), server_default=sa.func.now()),
        )

    # 4. RBAC permission for MCP server management
    _seed_mcp_server_permissions(bind)


def _seed_mcp_server_permissions(bind):
    """Add RBAC permission for MCP server management (idempotent)."""
    from sqlalchemy.orm import Session
    session = Session(bind=bind)

    try:
        from models_rbac import Permission, Role, RolePermission

        permissions_data = [
            ("skills.mcp_server.manage", "skills.mcp_server", "manage", "Manage MCP server connections and tools"),
        ]

        # owner and admin get manage permission
        role_assignments = {
            "owner": ["skills.mcp_server.manage"],
            "admin": ["skills.mcp_server.manage"],
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
        print(f"[RBAC] Warning: Failed to seed MCP server permissions: {e}")
    finally:
        session.close()


def downgrade() -> None:
    """Remove MCP server tables."""
    op.drop_table('mcp_server_health')
    op.drop_table('mcp_discovered_tool')
    op.drop_table('mcp_server_config')
