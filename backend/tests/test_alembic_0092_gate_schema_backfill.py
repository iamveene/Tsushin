"""Tests for Alembic 0092 — backfill flow_node gate config_json from legacy → canonical.

Locks the upgrade contract end-to-end against an in-memory sqlite DB:
  * legacy-only gates are renamed
  * canonical-only gates are untouched
  * mixed gates honor canonical-wins (legacy dropped as orphan)
  * non-gate rows are never touched, even if they contain legacy keys
  * malformed JSON is skipped, not crashed on
  * second invocation is a no-op (idempotency)
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_MIGRATION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "alembic",
    "versions",
    "0092_backfill_gate_legacy_to_canonical.py",
)
_spec = importlib.util.spec_from_file_location("alembic_0092", _MIGRATION_PATH)
migration_0092 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration_0092)


def _create_flow_node_table(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE flow_node (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                config_json TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )


def _insert(conn: Connection, *, type: str, config: object) -> int:
    if config is None:
        cfg = None
    elif isinstance(config, str):
        cfg = config
    else:
        cfg = json.dumps(config)
    result = conn.execute(
        text("INSERT INTO flow_node (type, config_json) VALUES (:t, :c)"),
        {"t": type, "c": cfg},
    )
    return result.lastrowid


def _config(conn: Connection, row_id: int) -> object:
    raw = conn.execute(
        text("SELECT config_json FROM flow_node WHERE id = :id"), {"id": row_id}
    ).scalar_one()
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return raw


def _seed_fixtures(conn: Connection) -> dict[str, int]:
    return {
        "legacy_only": _insert(
            conn,
            type="gate",
            config={
                "mode": "programmatic",
                "rules": [{"field": "x", "op": "eq", "value": "y"}],
                "logic": "any",
            },
        ),
        "canonical_only": _insert(
            conn,
            type="gate",
            config={
                "gate_mode": "programmatic",
                "gate_conditions": [{"field": "z", "op": "eq", "value": "w"}],
                "gate_logic": "all",
            },
        ),
        "mixed_conflict": _insert(
            conn,
            type="gate",
            config={
                "mode": "programmatic",
                "rules": [{"legacy": True}],
                "logic": "any",
                "gate_mode": "programmatic",
                "gate_conditions": [{"canonical": True}],
                "gate_logic": "all",
            },
        ),
        "non_gate_with_mode": _insert(
            conn,
            type="conversation",
            config={"mode": "ignored", "rules": ["should-not-touch"], "logic": "all"},
        ),
        "malformed_json": _insert(conn, type="gate", config="not json {"),
    }


def _run_upgrade(engine) -> None:
    with engine.begin() as conn:
        with patch.object(migration_0092.op, "get_bind", return_value=conn):
            migration_0092.upgrade()


def _run_downgrade(engine) -> None:
    with engine.begin() as conn:
        with patch.object(migration_0092.op, "get_bind", return_value=conn):
            migration_0092.downgrade()


def test_upgrade_renames_legacy_only_gate():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)

        _run_upgrade(engine)

        with engine.connect() as conn:
            cfg = _config(conn, ids["legacy_only"])

        assert cfg["gate_mode"] == "programmatic"
        assert cfg["gate_conditions"] == [{"field": "x", "op": "eq", "value": "y"}]
        assert cfg["gate_logic"] == "any"
        assert "mode" not in cfg
        assert "rules" not in cfg
        assert "logic" not in cfg
    finally:
        engine.dispose()


def test_upgrade_leaves_canonical_only_gate_untouched():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)
            before = _config(conn, ids["canonical_only"])

        _run_upgrade(engine)

        with engine.connect() as conn:
            after = _config(conn, ids["canonical_only"])

        assert after == before
    finally:
        engine.dispose()


def test_upgrade_canonical_wins_on_mixed_gate():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)

        _run_upgrade(engine)

        with engine.connect() as conn:
            cfg = _config(conn, ids["mixed_conflict"])

        assert cfg["gate_mode"] == "programmatic"
        assert cfg["gate_conditions"] == [{"canonical": True}]
        assert cfg["gate_logic"] == "all"
        assert "mode" not in cfg
        assert "rules" not in cfg
        assert "logic" not in cfg
    finally:
        engine.dispose()


def test_upgrade_skips_non_gate_rows():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)
            before = _config(conn, ids["non_gate_with_mode"])

        _run_upgrade(engine)

        with engine.connect() as conn:
            after = _config(conn, ids["non_gate_with_mode"])

        assert after == before
        assert "mode" in after
        assert "rules" in after
        assert "logic" in after
    finally:
        engine.dispose()


def test_upgrade_skips_malformed_json():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)

        _run_upgrade(engine)

        with engine.connect() as conn:
            raw = conn.execute(
                text("SELECT config_json FROM flow_node WHERE id = :id"),
                {"id": ids["malformed_json"]},
            ).scalar_one()

        assert raw == "not json {"
    finally:
        engine.dispose()


def test_upgrade_is_idempotent():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)

        _run_upgrade(engine)
        with engine.connect() as conn:
            after_first = {k: _config(conn, v) for k, v in ids.items()}

        _run_upgrade(engine)
        with engine.connect() as conn:
            after_second = {k: _config(conn, v) for k, v in ids.items()}

        assert after_first == after_second
    finally:
        engine.dispose()


def test_downgrade_reverses_canonical_to_legacy():
    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as conn:
            _create_flow_node_table(conn)
            ids = _seed_fixtures(conn)

        _run_upgrade(engine)
        _run_downgrade(engine)

        with engine.connect() as conn:
            cfg = _config(conn, ids["legacy_only"])

        assert cfg["mode"] == "programmatic"
        assert cfg["rules"] == [{"field": "x", "op": "eq", "value": "y"}]
        assert cfg["logic"] == "any"
        assert "gate_mode" not in cfg
        assert "gate_conditions" not in cfg
        assert "gate_logic" not in cfg
    finally:
        engine.dispose()
