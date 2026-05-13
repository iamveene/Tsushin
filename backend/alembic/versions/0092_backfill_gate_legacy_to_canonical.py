"""Backfill flow_node gate config_json from legacy keys to canonical keys.

Revision ID: 0092
Revises: 0091
Create Date: 2026-05-07

PR #56 (commit 5b3522e) flipped ``services.flow_binding_service.ensure_system_managed_flow_for_trigger``
and the flow editor frontend to write canonical gate keys
``gate_mode`` / ``gate_conditions`` / ``gate_logic``. The runtime reader
``GateStepHandler.execute()`` in ``flows/flow_engine.py`` was already
canonical and has no legacy fallback — pre-PR-#56 gates with the old
``mode`` / ``rules`` / ``logic`` shape silently auto-pass because
``gate_conditions`` defaults to ``[]`` when missing.

This migration renames the legacy keys to canonical on every
``flow_node`` row of ``type = 'gate'``. Two known sources of legacy
rows exist in the wild:

  1. Auto-flows created by ``ensure_system_managed_flow_for_trigger``
     before PR #56.
  2. Auto-flows backfilled by migration 0069 (which writes the legacy
     shape unconditionally — see 0069_backfill_managed_notifications.py:275).

**Conflict policy** — when a gate has both legacy and canonical keys
(e.g. an operator opened the gate in the editor and saved a real rule,
which writes only canonical keys, leaving the legacy keys behind as
orphan dead config), canonical wins. The legacy keys are dropped. Any
operator-authored conditions are preserved.

**Idempotency** — re-running this migration after it completes finds
no legacy keys and skips every row. Safe.

**Downgrade** — reverses the rename on ``type='gate'`` rows. WARNING:
gates created by the post-PR-#56 generator only have canonical keys,
so a downgrade rewrites them to a shape the current ``GateStepHandler``
does not understand (it has no legacy fallback). After downgrade those
gates silently auto-pass on missing ``gate_conditions``. Only run the
downgrade if you are also rolling code back to a pre-PR-#56 reader.
"""

from __future__ import annotations

import json
import logging
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0092"
down_revision: Union[str, None] = "0091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

LEGACY_TO_CANONICAL = {
    "mode": "gate_mode",
    "rules": "gate_conditions",
    "logic": "gate_logic",
}
CANONICAL_TO_LEGACY = {v: k for k, v in LEGACY_TO_CANONICAL.items()}


def _rename_keys(cfg: dict, mapping: dict[str, str]) -> bool:
    """Rename keys in cfg per mapping, dropping source key as orphan when target already present.

    Returns True when at least one rename was applied (cfg mutated).
    """
    changed = False
    for src, dst in mapping.items():
        if src in cfg:
            if dst not in cfg:
                cfg[dst] = cfg[src]
            cfg.pop(src, None)
            changed = True
    return changed


def upgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM flow_node WHERE type = 'gate'")
    ).fetchall()

    updated = 0
    skipped = 0
    malformed = 0

    for row in rows:
        raw = row.config_json
        if not raw:
            skipped += 1
            continue
        try:
            cfg = json.loads(raw)
        except (TypeError, ValueError):
            malformed += 1
            continue
        if not isinstance(cfg, dict):
            skipped += 1
            continue

        if not _rename_keys(cfg, LEGACY_TO_CANONICAL):
            skipped += 1
            continue

        bind.execute(
            sa.text(
                "UPDATE flow_node "
                "SET config_json = :cfg, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"cfg": json.dumps(cfg), "id": row.id},
        )
        updated += 1

    logger.info(
        "0092 backfill: updated=%d skipped=%d malformed=%d",
        updated,
        skipped,
        malformed,
    )


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, config_json FROM flow_node WHERE type = 'gate'")
    ).fetchall()

    reverted = 0
    skipped = 0
    malformed = 0

    for row in rows:
        raw = row.config_json
        if not raw:
            skipped += 1
            continue
        try:
            cfg = json.loads(raw)
        except (TypeError, ValueError):
            malformed += 1
            continue
        if not isinstance(cfg, dict):
            skipped += 1
            continue

        if not _rename_keys(cfg, CANONICAL_TO_LEGACY):
            skipped += 1
            continue

        bind.execute(
            sa.text(
                "UPDATE flow_node "
                "SET config_json = :cfg, updated_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"cfg": json.dumps(cfg), "id": row.id},
        )
        reverted += 1

    logger.info(
        "0092 downgrade: reverted=%d skipped=%d malformed=%d",
        reverted,
        skipped,
        malformed,
    )
