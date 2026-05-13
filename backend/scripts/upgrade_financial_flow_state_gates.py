"""Upgrade existing financial flow gates and notifications to the state-aware format.

Existing flows seeded before the notification_state classifier landed have:
  gate.config.gate_conditions = [{"field": "conditions.should_notify", "operator": "==", "value": true}]
  notification.config.message_template = "<single template>"

This script rewrites them to:
  gate.config.gate_conditions = [{"field": "conditions.notification_state", "operator": "in", "value": [...]}]
  notification.config.message_templates_by_state = {<state>: <template>, ...}

Tenant-scoped: matches flows by name prefix and by node name. Idempotent: skips
flows already on the new format.

Run inside the backend container:
    docker exec tsushin-backend python scripts/upgrade_financial_flow_state_gates.py
    docker exec tsushin-backend python scripts/upgrade_financial_flow_state_gates.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("upgrade_financial_flow_state_gates")

DEFAULT_NOTIFY_STATES = ["new_boleto", "barcode_changed", "pending_no_barcode"]


def _build_templates_by_state(profile_name: str) -> Dict[str, str]:
    return {
        "new_boleto": (
            f"Novo boleto detectado em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}} "
            "vence {{financial_store.due_date}} no valor {{financial_store.amount_display}}. "
            "Linha digitável: {{financial_store.linha_digitavel}}"
        ),
        "barcode_changed": (
            f"Atualização de boleto em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}. "
            "Nova linha digitável: {{financial_store.linha_digitavel}} "
            "(valor {{financial_store.amount_display}}, vence {{financial_store.due_date}})"
        ),
        "pending_no_barcode": (
            f"Conta em aberto em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}} "
            "ainda sem linha digitável disponível no portal. Acesse manualmente para regularizar."
        ),
        "no_pending_bills": (
            f"Sem boleto pendente em {profile_name}: "
            "{{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}"
        ),
        "default": (
            f"Atualização financeira em {profile_name}: "
            "{{financial_store.notification_state}} - {{financial_store.title}}{{financial_store.asset}} "
            "{{financial_store.reference_month}}{{financial_store.period_key}}"
        ),
    }


def _profile_name(flow_name: str) -> str:
    if flow_name.startswith("Finan | "):
        return flow_name.split(" | ", 1)[1]
    return flow_name


def _gate_uses_old_format(gate_conditions: Optional[List[Dict[str, Any]]]) -> bool:
    if not isinstance(gate_conditions, list):
        return False
    for cond in gate_conditions:
        if isinstance(cond, dict) and cond.get("field") == "conditions.should_notify":
            return True
    return False


def _new_gate_conditions() -> List[Dict[str, Any]]:
    return [
        {
            "field": "conditions.notification_state",
            "operator": "in",
            "value": list(DEFAULT_NOTIFY_STATES),
        }
    ]


def upgrade_gate_node(node, dry_run: bool) -> Tuple[bool, str]:
    config: Dict[str, Any] = json.loads(node.config_json or "{}")
    gate_conditions = config.get("gate_conditions")
    if not _gate_uses_old_format(gate_conditions):
        return False, "already-state-aware"
    config["gate_conditions"] = _new_gate_conditions()
    if not dry_run:
        node.config_json = json.dumps(config)
    return True, "rewrote-to-notification-state-in"


def upgrade_notification_node(node, profile_name: str, dry_run: bool) -> Tuple[bool, str]:
    config: Dict[str, Any] = json.loads(node.config_json or "{}")
    if isinstance(config.get("message_templates_by_state"), dict) and config["message_templates_by_state"]:
        return False, "already-has-templates_by_state"
    templates = _build_templates_by_state(profile_name)
    config["message_templates_by_state"] = templates
    fallback = templates.get("new_boleto") or templates.get("default")
    if fallback and not config.get("message_template"):
        config["message_template"] = fallback
    if not dry_run:
        node.config_json = json.dumps(config)
    return True, "added-message_templates_by_state"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print actions without committing")
    parser.add_argument(
        "--name-prefix",
        default="Finan |",
        help="Flow name prefix used to scope which flows to upgrade (default: 'Finan |')",
    )
    args = parser.parse_args()

    sys.path.insert(0, "/app")
    import os
    from db import get_engine, get_global_engine, session_scope, set_global_engine
    from models import FlowDefinition, FlowNode  # noqa: E402

    if get_global_engine() is None:
        db_url = os.getenv("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")
        set_global_engine(get_engine(db_url))

    with session_scope() as db:
        flows = (
            db.query(FlowDefinition)
            .filter(FlowDefinition.name.startswith(args.name_prefix))
            .order_by(FlowDefinition.id)
            .all()
        )
        log.info("Found %d flow(s) matching prefix %r", len(flows), args.name_prefix)
        if not flows:
            return 0

        upgraded_flows = 0
        gate_skips = 0
        notif_skips = 0

        for flow in flows:
            log.info("--- Flow %s | %s (tenant=%s)", flow.id, flow.name, flow.tenant_id)
            gate_node = (
                db.query(FlowNode)
                .filter(FlowNode.flow_definition_id == flow.id, FlowNode.name == "new_record_gate")
                .first()
            )
            notif_node = (
                db.query(FlowNode)
                .filter(FlowNode.flow_definition_id == flow.id, FlowNode.name == "notify_financial_event")
                .first()
            )
            if not gate_node or not notif_node:
                log.warning("  skip: missing new_record_gate or notify_financial_event node")
                continue

            gate_changed, gate_reason = upgrade_gate_node(gate_node, args.dry_run)
            if gate_changed:
                log.info("  gate(%s): %s", gate_node.id, gate_reason)
            else:
                log.info("  gate(%s): %s (no change)", gate_node.id, gate_reason)
                gate_skips += 1

            profile_name = _profile_name(flow.name)
            notif_changed, notif_reason = upgrade_notification_node(notif_node, profile_name, args.dry_run)
            if notif_changed:
                log.info("  notification(%s): %s", notif_node.id, notif_reason)
            else:
                log.info("  notification(%s): %s (no change)", notif_node.id, notif_reason)
                notif_skips += 1

            if gate_changed or notif_changed:
                upgraded_flows += 1

        # session_scope auto-commits on clean exit. Dry-run avoids mutations
        # entirely (upgrade_*_node skip writes when dry_run=True), so commit
        # is a safe no-op.
        if args.dry_run:
            log.info(
                "DRY RUN. Would upgrade %d flow(s). Gate skips: %d. Notification skips: %d.",
                upgraded_flows, gate_skips, notif_skips,
            )
        else:
            log.info(
                "Upgraded %d flow(s). Gate skips: %d. Notification skips: %d.",
                upgraded_flows, gate_skips, notif_skips,
            )
        return 0


if __name__ == "__main__":
    sys.exit(main())
