"""End-to-end dedupe round-trip for financial storage primitives.

Exercises the real `FinancialAutomationService._upsert_bill` and
`store_financial_record` paths against the live Postgres DB. Both methods are
the survivors after the legacy `financial_utility_automation` step deletion —
the migrated Finan flows hit them on every run, so the dedupe contract is
load-bearing.

Tests use synthetic per-test tenant IDs so they don't collide with real
tenants. Cleanup is best-effort via the unique-tenant scope.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Pre-load every model module so SQLAlchemy mapper-configuration finds the
# User class referenced from ShellSecurityPattern's relationship() string.
import models  # noqa: E402, F401
import models_rbac  # noqa: E402, F401


DATABASE_URL = (
    os.environ.get("TSN_TEST_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or "postgresql://tsushin:tsushin_dev@tsushin-postgres:5432/tsushin"
)


def _is_postgres(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


pytestmark = pytest.mark.skipif(
    not _is_postgres(DATABASE_URL),
    reason="dedupe round-trip relies on the unique constraint, which only Postgres enforces here",
)


@pytest.fixture
def db_session():
    from services.financial_automation_service import FinancialAutomationService  # noqa: F401

    engine = create_engine(DATABASE_URL, future=True)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture
def tenant_id():
    return f"test-dedupe-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def cleanup_tenant_rows(db_session, tenant_id):
    yield
    db_session.execute(
        text("DELETE FROM financial_utility_bill WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    db_session.execute(
        text("DELETE FROM financial_automation_record WHERE tenant_id = :t"),
        {"t": tenant_id},
    )
    db_session.commit()


def _utility_payload(barcode: str = "1" * 47):
    return {
        "record_kind": "utility_bill",
        "automation_key": "consigaz_visible_flow",
        "provider": "consigaz",
        "unit_id": "UNIT-A",
        "asset": "Test Asset",
        "address": "Test Address",
        "reference_month": "05/2026",
        "due_date": "10/05/2026",
        "amount_cents": 12345,
        "status": "Aberto",
        "barcode": barcode,
    }


def test_upsert_bill_dedupe_round_trip(db_session, tenant_id):
    from services.financial_automation_service import FinancialAutomationService

    service = FinancialAutomationService(db_session, tenant_id=tenant_id)
    config = {"financial_unit_id": "UNIT-A", "financial_provider": "consigaz"}

    first = service._upsert_bill(_utility_payload(), config, flow_run_id=1)
    assert first["created"] is True
    assert first["updated"] is False
    record_id = first["record"].id

    second = service._upsert_bill(_utility_payload(), config, flow_run_id=2)
    assert second["created"] is False
    assert second["updated"] is True
    assert second["record"].id == record_id, "second run must update the same row"
    assert second["barcode_changed"] is False, "identical payload must not flip barcode_changed"

    new_barcode = "9" * 47
    third = service._upsert_bill(_utility_payload(barcode=new_barcode), config, flow_run_id=3)
    assert third["created"] is False
    assert third["record"].id == record_id
    assert third["barcode_changed"] is True, "different barcode digits must flip barcode_changed"


def test_store_financial_record_dedupe_round_trip(db_session, tenant_id):
    from services.financial_automation_service import FinancialAutomationService

    service = FinancialAutomationService(db_session, tenant_id=tenant_id)
    record = {
        "record_kind": "tax_obligation",
        "automation_key": "iptu_main",
        "provider": "pmvv",
        "subject_key": "INSCR-42",
        "period_key": "2026",
        "external_id": "ext-1",
        "title": "IPTU 2026",
        "status": "Aberto",
        "amount_cents": 50000,
        "due_date": "15/03/2026",
    }
    config = {
        "financial_record_dedupe_key": f"tax_obligation:pmvv:INSCR-42:2026:{tenant_id}",
    }

    first = service.store_financial_record(record, config=config, flow_run_id=1)
    assert first["dedupe"]["created"] is True
    assert first["dedupe"]["updated"] is False

    second = service.store_financial_record(record, config=config, flow_run_id=2)
    assert second["dedupe"]["created"] is False
    assert second["dedupe"]["updated"] is True
    assert second["amount_cents"] == 50000

    record["amount_cents"] = 51000
    third = service.store_financial_record(record, config=config, flow_run_id=3)
    assert third["dedupe"]["created"] is False
    assert third["amount_cents"] == 51000, "row must be mutated, not duplicated"


def test_upsert_bill_isolates_tenants(db_session):
    from services.financial_automation_service import FinancialAutomationService

    tenant_a = f"test-iso-a-{uuid.uuid4().hex[:8]}"
    tenant_b = f"test-iso-b-{uuid.uuid4().hex[:8]}"
    payload = _utility_payload()
    config = {"financial_unit_id": "UNIT-A", "financial_provider": "consigaz"}

    try:
        a = FinancialAutomationService(db_session, tenant_id=tenant_a)._upsert_bill(payload, config, flow_run_id=1)
        b = FinancialAutomationService(db_session, tenant_id=tenant_b)._upsert_bill(payload, config, flow_run_id=1)
        assert a["created"] is True
        assert b["created"] is True, "same payload under a different tenant must NOT dedupe"
        assert a["record"].id != b["record"].id
    finally:
        db_session.execute(
            text("DELETE FROM financial_utility_bill WHERE tenant_id IN (:a, :b)"),
            {"a": tenant_a, "b": tenant_b},
        )
        db_session.commit()
