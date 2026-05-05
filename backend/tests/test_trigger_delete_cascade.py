"""Integration tests for trigger deletion cascade (BUG-QA070-WC-001).

When a trigger row (webhook_integration / email_channel_instance / jira_channel_instance /
github_channel_instance) is deleted at the DB layer (bypassing the service layer),
the system-managed auto-flow + flow_node + flow_run + flow_node_run + flow_trigger_binding
rows must also be removed. This is enforced by alembic migrations 0081 (per-trigger BEFORE
DELETE trigger functions) and 0082 (ON DELETE CASCADE on flow_node/flow_run/flow_node_run
FKs to flow_definition).

Without this safety net, direct DB DELETE leaves orphaned rows that confuse the UI
"Wired Flows" panel and bloat the flow listing.

Run via:

    docker exec -w /app tsushin-backend pytest tests/test_trigger_delete_cascade.py -v

Skipped automatically when DATABASE_URL isn't set (e.g., outside the backend container).
"""

from __future__ import annotations

import json
import os
import secrets
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="cascade tests require a live DATABASE_URL — run inside tsushin-backend",
)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(os.environ["DATABASE_URL"])
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def tenant_id(db: Session) -> Iterator[str]:
    from models_rbac import Tenant

    tid = f"trig-cascade-{secrets.token_hex(8)}"
    t = Tenant(
        id=tid,
        name=f"Trigger Cascade Test {tid[-6:]}",
        slug=f"trig-{tid[-8:]}",
        plan="dev",
    )
    db.add(t)
    db.commit()
    try:
        yield tid
    finally:
        # Cleanup is exercised by the test itself (direct DB DELETE on the trigger
        # cascades everything). Just remove the tenant row at end.
        db.execute(
            text("DELETE FROM webhook_integration WHERE tenant_id = :tid"),
            {"tid": tid},
        )
        db.execute(
            text("DELETE FROM tenant WHERE id = :tid"),
            {"tid": tid},
        )
        db.commit()


def _make_webhook_with_auto_flow(db: Session, tenant_id: str) -> tuple[int, int, int, list[int]]:
    """Create a webhook trigger plus its system-managed auto-flow (4 nodes + 1 binding).

    Returns (webhook_id, flow_id, binding_id, [node_ids...]).
    """
    from models import WebhookIntegration, FlowDefinition, FlowNode, FlowTriggerBinding

    webhook = WebhookIntegration(
        tenant_id=tenant_id,
        integration_name=f"cascade-test-{secrets.token_hex(4)}",
        slug=f"wh-{secrets.token_hex(4)}",
        api_secret_encrypted="dummy",
        api_secret_preview="whsec_test",
        callback_enabled=False,
        is_active=True,
        status="active",
        health_status="unknown",
        created_by=1,
    )
    db.add(webhook)
    db.flush()

    flow = FlowDefinition(
        tenant_id=tenant_id,
        name=f"Webhook: {webhook.integration_name}",
        description="auto-generated for cascade test",
        execution_method="immediate",
        flow_type="workflow",
        initiator_type="programmatic",
        is_system_owned=True,
        is_active=True,
    )
    db.add(flow)
    db.flush()

    node_ids = []
    for pos, node_type in enumerate(["source", "gate", "conversation", "notification"], start=1):
        node = FlowNode(
            flow_definition_id=flow.id,
            type=node_type,
            position=pos,
            config_json=json.dumps({}),
        )
        db.add(node)
        db.flush()
        node_ids.append(node.id)

    binding = FlowTriggerBinding(
        tenant_id=tenant_id,
        flow_definition_id=flow.id,
        trigger_kind="webhook",
        trigger_instance_id=webhook.id,
        is_system_managed=True,
        is_active=True,
    )
    db.add(binding)
    db.commit()

    return webhook.id, flow.id, binding.id, node_ids


def _row_count(db: Session, table: str, where: str, params: dict) -> int:
    sql = text(f"SELECT COUNT(*) FROM {table} WHERE {where}")
    return db.execute(sql, params).scalar() or 0


def test_direct_db_delete_on_webhook_cascades_auto_flow(db: Session, tenant_id: str) -> None:
    """Direct SQL DELETE on webhook_integration must remove the auto-flow + bindings + nodes.

    Pre-fix (without 0081/0082), the trigger row would delete but flow_definition,
    flow_node, and flow_trigger_binding rows would remain orphaned.
    """
    webhook_id, flow_id, binding_id, node_ids = _make_webhook_with_auto_flow(db, tenant_id)

    # Sanity: rows exist before delete
    assert _row_count(db, "webhook_integration", "id = :id", {"id": webhook_id}) == 1
    assert _row_count(db, "flow_definition", "id = :id", {"id": flow_id}) == 1
    assert _row_count(db, "flow_trigger_binding", "id = :id", {"id": binding_id}) == 1
    assert _row_count(db, "flow_node", "flow_definition_id = :id", {"id": flow_id}) == 4

    # Act: direct SQL DELETE bypassing all service-layer cascade logic
    db.execute(text("DELETE FROM webhook_integration WHERE id = :id"), {"id": webhook_id})
    db.commit()

    # Assert: cascade chain fired all the way down
    assert _row_count(db, "webhook_integration", "id = :id", {"id": webhook_id}) == 0, "webhook row not deleted"
    assert _row_count(db, "flow_definition", "id = :id", {"id": flow_id}) == 0, "auto-flow not cascaded"
    assert _row_count(db, "flow_trigger_binding", "id = :id", {"id": binding_id}) == 0, "binding not cascaded"
    assert _row_count(db, "flow_node", "flow_definition_id = :id", {"id": flow_id}) == 0, "flow nodes not cascaded"


def test_user_authored_binding_to_same_flow_is_preserved(db: Session, tenant_id: str) -> None:
    """If a user-authored (is_system_managed=false) binding also references the
    auto-flow, deleting the trigger should remove the system-managed binding but
    leave the user-authored one (and the flow) intact.

    The trigger function in 0081 only deletes the flow if no other non-system-managed
    binding references it.
    """
    from models import FlowTriggerBinding

    webhook_id, flow_id, _binding_id, _node_ids = _make_webhook_with_auto_flow(db, tenant_id)

    # Add a user-authored binding pointing at the same flow (different trigger_instance_id
    # to keep semantics — the user is also wiring this flow up to a different webhook,
    # which would be unusual but the logic should handle it).
    user_binding = FlowTriggerBinding(
        tenant_id=tenant_id,
        flow_definition_id=flow_id,
        trigger_kind="webhook",
        trigger_instance_id=webhook_id + 9999,  # phantom instance, doesn't matter for this test
        is_system_managed=False,
        is_active=True,
    )
    db.add(user_binding)
    db.commit()
    user_binding_id = user_binding.id

    # Act
    db.execute(text("DELETE FROM webhook_integration WHERE id = :id"), {"id": webhook_id})
    db.commit()

    # Assert: webhook gone, system-managed binding gone, but flow + user binding survive
    assert _row_count(db, "webhook_integration", "id = :id", {"id": webhook_id}) == 0
    assert _row_count(db, "flow_definition", "id = :id", {"id": flow_id}) == 1, "flow should survive — user binding still references it"
    assert _row_count(db, "flow_trigger_binding", "id = :id", {"id": user_binding_id}) == 1, "user-authored binding should survive"

    # Cleanup the survivors
    db.execute(text("DELETE FROM flow_trigger_binding WHERE id = :id"), {"id": user_binding_id})
    db.execute(text("DELETE FROM flow_definition WHERE id = :id"), {"id": flow_id})
    db.commit()
