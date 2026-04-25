"""Make audit_event append-only via PostgreSQL triggers (BUG-704).

Adds BEFORE UPDATE / BEFORE DELETE triggers on audit_event so any DML attempt
raises an exception, satisfying the SOC2/HIPAA immutability bar for the v0.7.0
enterprise hardening track.

Bypass mechanism: any session that explicitly sets
`app.audit_event_retention_purge=true` (or `app.audit_event_user_fk_cleanup=true`)
can update/delete rows. This lets retention scripts and FK-nulling-on-user-
delete code paths operate without disabling the trigger globally. All other
code paths (and ad-hoc psql sessions) hit the RAISE EXCEPTION.

INSERTs are unaffected — only UPDATE and DELETE are guarded.

Revision ID: 0063
Revises: 0062
Create Date: 2026-04-25
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0063"
down_revision: Union[str, None] = "0062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# SQL — trigger functions and triggers
# ---------------------------------------------------------------------------

# Both functions consult two GUCs:
#   * app.audit_event_retention_purge   — for retention purges (DELETE only)
#   * app.audit_event_user_fk_cleanup   — for nulling user_id on user deletion
#                                          (UPDATE only, narrow allowance)
#
# `current_setting(name, true)` returns NULL if the setting is unset rather
# than raising — that's why we use the two-arg form. We explicitly compare to
# the lowercase string "true" so accidental boolean-y values don't bypass.
_REJECT_UPDATE_FN = """
CREATE OR REPLACE FUNCTION audit_event_reject_update()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('app.audit_event_user_fk_cleanup', true) = 'true' THEN
        -- Privileged FK-cleanup path used when a user is hard-deleted.
        -- Allowed columns: user_id may be set to NULL. Anything else raises.
        IF NEW.tenant_id     IS DISTINCT FROM OLD.tenant_id
        OR NEW.action        IS DISTINCT FROM OLD.action
        OR NEW.resource_type IS DISTINCT FROM OLD.resource_type
        OR NEW.resource_id   IS DISTINCT FROM OLD.resource_id
        OR NEW.details       IS DISTINCT FROM OLD.details
        OR NEW.ip_address    IS DISTINCT FROM OLD.ip_address
        OR NEW.user_agent    IS DISTINCT FROM OLD.user_agent
        OR NEW.channel       IS DISTINCT FROM OLD.channel
        OR NEW.severity      IS DISTINCT FROM OLD.severity
        OR NEW.created_at    IS DISTINCT FROM OLD.created_at
        OR NEW.id            IS DISTINCT FROM OLD.id
        OR NEW.user_id       IS NOT NULL THEN
            RAISE EXCEPTION
                'audit_event is append-only - UPDATE rejected '
                '(only user_id->NULL allowed under app.audit_event_user_fk_cleanup)';
        END IF;
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'audit_event is append-only - UPDATE rejected';
END;
$$;
"""

_REJECT_DELETE_FN = """
CREATE OR REPLACE FUNCTION audit_event_reject_delete()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF current_setting('app.audit_event_retention_purge', true) = 'true' THEN
        RETURN OLD;
    END IF;

    RAISE EXCEPTION 'audit_event is append-only - DELETE rejected';
END;
$$;
"""

_CREATE_UPDATE_TRIGGER = """
DROP TRIGGER IF EXISTS audit_event_reject_update_trg ON audit_event;
CREATE TRIGGER audit_event_reject_update_trg
BEFORE UPDATE ON audit_event
FOR EACH ROW
EXECUTE FUNCTION audit_event_reject_update();
"""

_CREATE_DELETE_TRIGGER = """
DROP TRIGGER IF EXISTS audit_event_reject_delete_trg ON audit_event;
CREATE TRIGGER audit_event_reject_delete_trg
BEFORE DELETE ON audit_event
FOR EACH ROW
EXECUTE FUNCTION audit_event_reject_delete();
"""

_DROP_TRIGGERS_AND_FNS = """
DROP TRIGGER IF EXISTS audit_event_reject_update_trg ON audit_event;
DROP TRIGGER IF EXISTS audit_event_reject_delete_trg ON audit_event;
DROP FUNCTION IF EXISTS audit_event_reject_update();
DROP FUNCTION IF EXISTS audit_event_reject_delete();
"""


def upgrade() -> None:
    """Install append-only triggers on audit_event (Postgres only, no-op on SQLite)."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # The platform runs on Postgres in production; SQLite is only used for
        # in-memory unit tests where DDL triggers aren't supported anyway.
        print("[Migration 0063] Skipping audit_event triggers — non-Postgres dialect")
        return

    op.execute(_REJECT_UPDATE_FN)
    op.execute(_REJECT_DELETE_FN)
    op.execute(_CREATE_UPDATE_TRIGGER)
    op.execute(_CREATE_DELETE_TRIGGER)
    print("[Migration 0063] Installed append-only triggers on audit_event")


def downgrade() -> None:
    """Remove the append-only triggers and functions."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute(_DROP_TRIGGERS_AND_FNS)
    print("[Migration 0063] Removed audit_event append-only triggers and functions")
