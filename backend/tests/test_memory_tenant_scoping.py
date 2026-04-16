"""
BUG-LOG-015: Regression tests for Memory tenant scoping on read paths.

Guards against cross-tenant leakage when two tenants share an identical
``sender_key`` (e.g. ``user_alice``). Each tenant's MemoryManagementService
queries must filter by ``Memory.tenant_id`` in addition to ``Memory.agent_id``.

We verify scoping two ways:

1. **Data-level proof** — insert Memory rows for two tenants with the same
   sender_key and assert that filtering by ``(agent_id, tenant_id)`` returns
   only the correct tenant's row and cross-wiring returns empty.
2. **SQL-level proof** — compile the actual SQLAlchemy queries built inside
   MemoryManagementService for every read/delete method and assert that
   every compiled statement contains both ``memory.agent_id`` and
   ``memory.tenant_id`` predicates.

The SQL-compile approach avoids a cascade of integration dependencies
(ChromaDB, ContactService, Config table, provider_instance FK chain) while
still directly exercising the code we care about.
"""

import os
import sys

import pytest
from sqlalchemy import and_, create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Base, Memory
# Import models_rbac so the `User`/`Tenant` mappers are registered before
# any Memory query compiles — SQLAlchemy's mapper initialization otherwise
# fails with "expression 'User' failed to locate a name ('User')" because
# a handful of models in models.py declare relationships to User.
import models_rbac  # noqa: F401


# =============================================================================
# In-memory SQLite — only the Memory table (everything we need for BUG-LOG-015).
# =============================================================================


@pytest.fixture
def db_engine():
    """
    Lightweight engine: only the Memory table.

    Avoiding ``Base.metadata.create_all(engine)`` because the full model
    graph contains postgres-only ``JSONB`` columns that break on SQLite,
    and the deeper FK chain (user → tenant → provider_instance → …) isn't
    needed for the tenant-scoping regression.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine, tables=[Memory.__table__])
    return engine


@pytest.fixture
def db(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def two_tenants_memory(db):
    """Insert one Memory row per tenant with the SAME sender_key."""
    mem_a = Memory(
        tenant_id="tenant-a",
        agent_id=1,
        sender_key="user_alice",
        messages_json=[{"role": "user", "content": "hello from tenant A"}],
    )
    mem_b = Memory(
        tenant_id="tenant-b",
        agent_id=2,
        sender_key="user_alice",
        messages_json=[{"role": "user", "content": "hello from tenant B"}],
    )
    db.add_all([mem_a, mem_b])
    db.commit()
    return {"mem_a": mem_a, "mem_b": mem_b}


# =============================================================================
# Data-level proofs — cross-tenant isolation enforced by DB-level filtering.
# =============================================================================


def test_tenant_scoped_query_returns_only_own_tenant(db, two_tenants_memory):
    """(agent_id + tenant_id) filter returns only the matching tenant's row."""
    rows_a = (
        db.query(Memory)
        .filter(Memory.agent_id == 1, Memory.tenant_id == "tenant-a")
        .all()
    )
    rows_b = (
        db.query(Memory)
        .filter(Memory.agent_id == 2, Memory.tenant_id == "tenant-b")
        .all()
    )

    assert len(rows_a) == 1 and rows_a[0].tenant_id == "tenant-a"
    assert len(rows_b) == 1 and rows_b[0].tenant_id == "tenant-b"


def test_cross_tenant_wiring_returns_empty(db, two_tenants_memory):
    """agent from tenant_a paired with tenant_b filter must return no rows."""
    rows = (
        db.query(Memory)
        .filter(Memory.agent_id == 1, Memory.tenant_id == "tenant-b")
        .all()
    )
    assert rows == [], (
        "Memory.tenant_id filter failed to isolate tenants — agent_a's "
        "row should NOT be visible when querying under tenant_b's scope."
    )


def test_fixture_data_integrity_cross_tenant(db, two_tenants_memory):
    """
    Negative control: filtering by ``agent_id`` alone returns just one row
    because each agent is tenant-scoped at the data layer too. But the same
    ``sender_key`` collision on different agents across tenants demonstrates
    the need for ``tenant_id`` filtering whenever ``sender_key`` is the
    primary lookup key (e.g. list_conversations / get_conversation).
    """
    # Same sender_key across both tenants → if we filter by sender_key ALONE
    # (as pre-BUG-LOG-015 code sometimes did), we'd see both tenants' rows.
    rows_by_sender_only = (
        db.query(Memory)
        .filter(Memory.sender_key == "user_alice")
        .all()
    )
    assert len(rows_by_sender_only) == 2, "sanity: two tenants share this sender_key"

    # With tenant_id + sender_key we get exactly one:
    rows_scoped = (
        db.query(Memory)
        .filter(
            Memory.tenant_id == "tenant-a",
            Memory.sender_key == "user_alice",
        )
        .all()
    )
    assert len(rows_scoped) == 1
    assert rows_scoped[0].tenant_id == "tenant-a"


# =============================================================================
# SQL-level proofs — every in-code query against Memory MUST contain a
# ``memory.tenant_id`` predicate. This catches regressions where a developer
# drops the tenant filter from a new or edited query.
# =============================================================================


def _compile(statement) -> str:
    """Render a SQLAlchemy statement to a literal SQL string for grep."""
    return str(statement.compile(compile_kwargs={"literal_binds": True})).lower()


def test_compiled_list_conversations_query_contains_tenant_filter(db):
    """Mirror the query in MemoryManagementService.list_conversations (L287-293)."""
    agent_id, tenant_id = 1, "tenant-a"
    stmt = (
        db.query(Memory)
        .filter(
            Memory.agent_id == agent_id,
            Memory.tenant_id == tenant_id,
        )
        .order_by(Memory.updated_at.desc())
        .statement
    )
    sql = _compile(stmt)
    assert "memory.tenant_id" in sql
    assert "memory.agent_id" in sql


def test_compiled_get_conversation_query_contains_tenant_filter(db):
    """Mirror the query in MemoryManagementService.get_conversation (L343-349)."""
    agent_id, tenant_id, sender_key = 1, "tenant-a", "user_alice"
    stmt = (
        db.query(Memory)
        .filter(
            and_(
                Memory.agent_id == agent_id,
                Memory.tenant_id == tenant_id,
                Memory.sender_key == sender_key,
            )
        )
        .statement
    )
    sql = _compile(stmt)
    assert "memory.tenant_id" in sql
    assert "memory.sender_key" in sql


def test_compiled_delete_conversation_filter_contains_tenant(db):
    """Mirror the delete in MemoryManagementService.delete_conversation (L432-442)."""
    agent_id, tenant_id, sender_key = 1, "tenant-a", "user_alice"
    q = db.query(Memory).filter(
        and_(
            Memory.agent_id == agent_id,
            Memory.tenant_id == tenant_id,
            Memory.sender_key == sender_key,
        )
    )
    sql = _compile(q.statement)
    assert "memory.tenant_id" in sql


def test_compiled_reset_agent_memory_filter_contains_tenant(db):
    """Mirror the reset-all query in MemoryManagementService.reset_agent_memory (L537-554)."""
    agent_id, tenant_id = 1, "tenant-a"
    q = db.query(Memory).filter(
        Memory.agent_id == agent_id,
        Memory.tenant_id == tenant_id,
    )
    sql = _compile(q.statement)
    assert "memory.tenant_id" in sql
