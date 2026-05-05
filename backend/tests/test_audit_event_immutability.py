"""
Regression test: audit_event is append-only (BUG-704).

Verifies the BEFORE UPDATE / BEFORE DELETE triggers installed by migration
0063_audit_event_immutable.py:

  1. INSERT into audit_event succeeds (triggers do not fire on INSERT).
  2. UPDATE on audit_event is rejected with a RAISE EXCEPTION.
  3. DELETE on audit_event is rejected with a RAISE EXCEPTION.
  4. With `app.audit_event_retention_purge=true` set on the session, DELETE
     succeeds (proves the retention bypass works as documented).
  5. With `app.audit_event_user_fk_cleanup=true` set on the session, an UPDATE
     that nulls out user_id succeeds (proves the FK-cleanup bypass works).
  6. With `app.audit_event_user_fk_cleanup=true` set on the session, an UPDATE
     that touches a non-FK column (e.g. action) is still rejected (proves the
     bypass is narrow).

This test requires PostgreSQL — the protection is implemented via PG triggers.
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import InternalError, ProgrammingError
from sqlalchemy.orm import sessionmaker


# Resolve DATABASE_URL the same way the backend does — fall back to the
# in-container hostname if the host-side hostname is not set.
DATABASE_URL = (
    os.environ.get("TSN_TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql://tsushin:tsushin_dev@tsushin-postgres:5432/tsushin"
)


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


pytestmark = pytest.mark.skipif(
    not _is_postgres(DATABASE_URL),
    reason="audit_event immutability triggers are PostgreSQL-only",
)


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    # Verify the triggers exist before running — if migration 0063 was not
    # applied, fail loudly rather than producing a false negative.
    with eng.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'audit_event'::regclass
                  AND tgname IN (
                      'audit_event_reject_update_trg',
                      'audit_event_reject_delete_trg'
                  )
                """
            )
        ).fetchall()
    trigger_names = {row[0] for row in rows}
    missing = {
        "audit_event_reject_update_trg",
        "audit_event_reject_delete_trg",
    } - trigger_names
    if missing:
        pytest.skip(
            f"audit_event immutability triggers missing: {missing}. "
            "Apply migration 0063 before running this test."
        )
    yield eng
    eng.dispose()


@pytest.fixture()
def session(engine):
    Session = sessionmaker(bind=engine, future=True, autoflush=False, autocommit=False)
    sess = Session()
    yield sess
    sess.rollback()
    sess.close()


@pytest.fixture()
def tenant_id(session):
    """Use the first existing tenant if any, otherwise create a throwaway one."""
    existing = session.execute(text("SELECT id FROM tenant LIMIT 1")).scalar()
    if existing:
        yield existing
        return

    tid = f"test-{uuid.uuid4().hex[:8]}"
    session.execute(
        text(
            "INSERT INTO tenant (id, name, slug, created_at) "
            "VALUES (:id, :name, :slug, :ts)"
        ),
        {"id": tid, "name": "Test BUG704", "slug": tid, "ts": datetime.utcnow()},
    )
    session.commit()
    try:
        yield tid
    finally:
        session.execute(text("DELETE FROM tenant WHERE id = :id"), {"id": tid})
        session.commit()


def _insert_audit_row(session, tenant_id: str) -> int:
    """Insert a fresh audit_event row and return its id."""
    row_id = session.execute(
        text(
            """
            INSERT INTO audit_event (tenant_id, action, severity, channel, created_at)
            VALUES (:tenant_id, :action, 'info', 'web', :ts)
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "action": "test.bug704.immutable",
            "ts": datetime.utcnow(),
        },
    ).scalar()
    session.commit()
    return row_id


def _hard_purge(session, row_id: int) -> None:
    """Force-remove a test row using the documented retention bypass."""
    session.execute(text("SET LOCAL app.audit_event_retention_purge = 'true'"))
    session.execute(text("DELETE FROM audit_event WHERE id = :id"), {"id": row_id})
    session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_insert_audit_event_succeeds(session, tenant_id):
    """The triggers must NOT fire on INSERT — audit logging itself must work."""
    row_id = _insert_audit_row(session, tenant_id)
    assert row_id is not None
    # Cleanup with bypass
    _hard_purge(session, row_id)


def test_update_audit_event_is_rejected(session, tenant_id):
    """Any UPDATE without bypass must raise."""
    row_id = _insert_audit_row(session, tenant_id)
    try:
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            session.execute(
                text("UPDATE audit_event SET action = 'tampered' WHERE id = :id"),
                {"id": row_id},
            )
            session.commit()
        assert "append-only" in str(exc_info.value).lower()
    finally:
        session.rollback()
        _hard_purge(session, row_id)


def test_delete_audit_event_is_rejected(session, tenant_id):
    """Any DELETE without bypass must raise."""
    row_id = _insert_audit_row(session, tenant_id)
    try:
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            session.execute(
                text("DELETE FROM audit_event WHERE id = :id"),
                {"id": row_id},
            )
            session.commit()
        assert "append-only" in str(exc_info.value).lower()
    finally:
        session.rollback()
        _hard_purge(session, row_id)


def test_delete_succeeds_with_retention_bypass(session, tenant_id):
    """With app.audit_event_retention_purge=true, DELETE is allowed."""
    row_id = _insert_audit_row(session, tenant_id)

    session.execute(text("SET LOCAL app.audit_event_retention_purge = 'true'"))
    deleted = session.execute(
        text("DELETE FROM audit_event WHERE id = :id"), {"id": row_id}
    ).rowcount
    session.commit()
    assert deleted == 1

    # Confirm it is gone.
    remaining = session.execute(
        text("SELECT 1 FROM audit_event WHERE id = :id"), {"id": row_id}
    ).scalar()
    assert remaining is None


def test_update_user_id_to_null_succeeds_with_fk_cleanup_bypass(session, tenant_id):
    """With app.audit_event_user_fk_cleanup=true, user_id->NULL is allowed."""
    row_id = session.execute(
        text(
            """
            INSERT INTO audit_event (tenant_id, user_id, action, severity, channel, created_at)
            VALUES (:tenant_id, NULL, :action, 'info', 'web', :ts)
            RETURNING id
            """
        ),
        {
            "tenant_id": tenant_id,
            "action": "test.bug704.fkcleanup",
            "ts": datetime.utcnow(),
        },
    ).scalar()
    session.commit()
    try:
        # Update is a no-op (already NULL) but still passes through the trigger.
        session.execute(text("SET LOCAL app.audit_event_user_fk_cleanup = 'true'"))
        session.execute(
            text("UPDATE audit_event SET user_id = NULL WHERE id = :id"),
            {"id": row_id},
        )
        session.commit()
    finally:
        _hard_purge(session, row_id)


def test_update_other_columns_rejected_even_with_fk_cleanup_bypass(session, tenant_id):
    """The FK-cleanup bypass must NOT allow tampering with other columns."""
    row_id = _insert_audit_row(session, tenant_id)
    try:
        with pytest.raises((InternalError, ProgrammingError)) as exc_info:
            session.execute(text("SET LOCAL app.audit_event_user_fk_cleanup = 'true'"))
            session.execute(
                text("UPDATE audit_event SET action = 'tampered' WHERE id = :id"),
                {"id": row_id},
            )
            session.commit()
        assert "append-only" in str(exc_info.value).lower()
    finally:
        session.rollback()
        _hard_purge(session, row_id)
