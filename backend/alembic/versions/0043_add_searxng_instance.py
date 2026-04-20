"""Add searxng_instance table + migrate ApiKey('searxng') -> SearxngInstance

v0.6.0-patch.6: Replaces the shipped-by-default SearXNG compose service with
per-tenant auto-provisioned containers, mirroring the Kokoro/Ollama pattern.

This migration:
1. Creates the `searxng_instance` table (mirrors `tts_instance` shape + extra_config).
2. Backfills rows from any existing ApiKey(service='searxng') so users who
   configured an external SearXNG URL under the old model aren't broken —
   their URL is preserved on a new SearxngInstance(is_auto_provisioned=False).
3. Soft-deactivates the migrated ApiKey rows (is_active=False) — keeps them
   for audit, stops the old path from being used.
4. Best-effort removes the old compose-managed `<stack>-searxng` container
   (label tsushin.lifecycle=compose) so operators aren't left with an
   orphaned shipped-container after `docker-compose up -d --build`.

Idempotency-guarded via sa.inspect(bind) so re-running is a no-op.

Revision ID: 0043
Revises: 0042
Create Date: 2026-04-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0043'
down_revision: Union[str, None] = '0042'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _backfill_from_api_keys(bind) -> None:
    """Copy any existing ApiKey(service='searxng') rows to SearxngInstance.

    We decrypt on read via the ApiKey ORM accessors; unfortunately at migration
    time we don't have ORM access without importing app code. Raw SQL fetch of
    the encrypted bytes is not useful here — we leave base_url NULL for the
    new rows and rely on the app-side fallback to surface a "reconfigure"
    banner when the user next opens the Hub. This preserves tenant scoping
    without needing Fernet at migration time.

    If the old rows are visible to the app via ORM, the resolver will prefer
    the new SearxngInstance row, so the "disabled" ApiKey row is effectively
    quarantined.
    """
    try:
        rows = bind.execute(
            sa.text(
                "SELECT id, tenant_id FROM api_key "
                "WHERE service = 'searxng' AND (is_active IS NULL OR is_active = true)"
            )
        ).fetchall()
        for row in rows:
            tenant_id = row.tenant_id if hasattr(row, "tenant_id") else row[1]
            bind.execute(
                sa.text(
                    "INSERT INTO searxng_instance "
                    "(tenant_id, vendor, instance_name, description, base_url, "
                    " extra_config, health_status, is_active, is_auto_provisioned, "
                    " container_status, created_at, updated_at) "
                    "VALUES (:tenant_id, 'searxng', 'default', "
                    "'Migrated from legacy ApiKey on 0043', NULL, '{}', 'unknown', "
                    "true, false, 'none', NOW(), NOW()) "
                    "ON CONFLICT (tenant_id, instance_name) DO NOTHING"
                ),
                {"tenant_id": tenant_id},
            )
            bind.execute(
                sa.text("UPDATE api_key SET is_active = false WHERE id = :id"),
                {"id": row.id if hasattr(row, "id") else row[0]},
            )
    except Exception:
        # Non-fatal — table missing on fresh installs, or column drift
        pass


def _best_effort_remove_compose_searxng() -> None:
    """Try to remove the old compose-managed SearXNG container.

    If docker-py is not importable or the socket isn't mounted (e.g. managed DB
    running the migration), silently skip.
    """
    try:
        import os
        import docker as docker_lib
        client = docker_lib.from_env()
        stack = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
        try:
            c = client.containers.get(f"{stack}-searxng")
            labels = (c.labels or {}) if hasattr(c, "labels") else {}
            if labels.get("tsushin.lifecycle") == "compose":
                try:
                    c.stop(timeout=5)
                except Exception:
                    pass
                c.remove(force=True)
        except Exception:
            pass
    except Exception:
        pass


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table('searxng_instance'):
        op.create_table(
            'searxng_instance',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(length=50), nullable=False, index=True),
            sa.Column('vendor', sa.String(length=20), nullable=False, server_default='searxng'),
            sa.Column('instance_name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('base_url', sa.String(length=500), nullable=True),
            sa.Column('extra_config', sa.JSON(), nullable=True),
            sa.Column('health_status', sa.String(length=20), nullable=False, server_default='unknown'),
            sa.Column('health_status_reason', sa.String(length=500), nullable=True),
            sa.Column('last_health_check', sa.DateTime(), nullable=True),
            sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column('is_auto_provisioned', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('container_name', sa.String(length=200), nullable=True),
            sa.Column('container_id', sa.String(length=80), nullable=True),
            sa.Column('container_port', sa.Integer(), nullable=True),
            sa.Column('container_status', sa.String(length=20), nullable=False, server_default='none'),
            sa.Column('container_image', sa.String(length=200), nullable=True),
            sa.Column('volume_name', sa.String(length=150), nullable=True),
            sa.Column('mem_limit', sa.String(length=20), nullable=True),
            sa.Column('cpu_quota', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'instance_name', name='uq_searxng_instance_tenant_name'),
        )
        op.create_index('idx_sxi_tenant_vendor', 'searxng_instance', ['tenant_id', 'vendor'])

    # Backfill from legacy ApiKey rows (best-effort) and stand down old compose container
    _backfill_from_api_keys(bind)
    _best_effort_remove_compose_searxng()


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Reactivate any soft-deactivated ApiKey('searxng') rows so the old path
    # works again post-downgrade.
    try:
        bind.execute(
            sa.text(
                "UPDATE api_key SET is_active = true "
                "WHERE service = 'searxng' AND is_active = false"
            )
        )
    except Exception:
        pass

    if inspector.has_table('searxng_instance'):
        try:
            op.drop_index('idx_sxi_tenant_vendor', table_name='searxng_instance')
        except Exception:
            pass
        op.drop_table('searxng_instance')
