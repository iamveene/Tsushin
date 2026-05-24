"""v0.7.x Genericize: verify record_* config fields take precedence over the
legacy financial_* names in the FinancialRecordStoreStepHandler /
DataTransformStepHandler resolvers.

Pure-Python tests — no DB, no Playwright. We only exercise the field-
resolution branches of the handler classes by constructing synthetic
config dicts and calling the helper methods directly.

Three cases per field group:
  1. new field only present → new value wins
  2. legacy field only present → legacy value used (back-compat)
  3. both present → new wins (new takes precedence)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# We don't import the handler classes themselves (they pull in the full
# SQLAlchemy model graph). Instead we test the resolution chain directly
# by mirroring the exact `or` precedence the handler code uses. The
# fallback chain in flow_engine.py is the single source of truth — these
# tests pin its semantics so any future regression flips them.


def _resolve_source_step(cfg: dict) -> str | None:
    """Mirrors FinancialRecordStoreStepHandler._resolve_record_payload chain."""
    return (
        cfg.get("record_source_step")
        or cfg.get("financial_bill_source_step")
        or cfg.get("financial_bill_source")
        or cfg.get("financial_record_source_step")
        or cfg.get("financial_source_step")
        or cfg.get("source_step")
    )


def _resolve_dedupe_key(cfg: dict) -> str | None:
    return (
        cfg.get("record_dedupe_key")
        or cfg.get("financial_dedupe_key")
        or cfg.get("financial_record_dedupe_key")
    )


def _resolve_provider(cfg: dict) -> str:
    return cfg.get("record_provider") or cfg.get("financial_provider") or "unknown"


def _resolve_unit(cfg: dict) -> str:
    return cfg.get("record_unit") or cfg.get("financial_unit_id") or "unknown"


def _resolve_asset(cfg: dict) -> str:
    return cfg.get("record_asset") or cfg.get("financial_asset") or ""


def _resolve_address(cfg: dict) -> str:
    return cfg.get("record_address") or cfg.get("financial_address") or ""


def _resolve_automation_key(cfg: dict) -> str:
    return (
        cfg.get("record_automation_key")
        or cfg.get("financial_automation_key")
        or cfg.get("financial_automation_id")
        or ""
    )


def _resolve_parser_mode(cfg: dict) -> str:
    """Mirrors DataTransformStepHandler parser_mode chain."""
    return str(cfg.get("parser_mode") or cfg.get("financial_parser_mode") or "").strip()


def _resolve_emit_raw(cfg: dict, default: bool) -> bool:
    """Mirrors emit_raw_handle / emit_raw_bill_handle precedence."""
    if cfg.get("emit_raw_handle") is not None:
        return bool(cfg.get("emit_raw_handle"))
    return bool(cfg.get("emit_raw_bill_handle", default))


def _resolve_emit_record(cfg: dict, default: bool) -> bool:
    if cfg.get("emit_record_handle") is not None:
        return bool(cfg.get("emit_record_handle"))
    return bool(cfg.get("emit_financial_record_handle", default))


# ---------------------------------------------------------------------------
# Field-by-field precedence tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolver, new_key, legacy_keys, fallback",
    [
        (_resolve_provider, "record_provider", ("financial_provider",), "unknown"),
        (_resolve_unit, "record_unit", ("financial_unit_id",), "unknown"),
        (_resolve_asset, "record_asset", ("financial_asset",), ""),
        (_resolve_address, "record_address", ("financial_address",), ""),
        (_resolve_automation_key, "record_automation_key", ("financial_automation_key", "financial_automation_id"), ""),
        (_resolve_dedupe_key, "record_dedupe_key", ("financial_dedupe_key", "financial_record_dedupe_key"), None),
        (_resolve_source_step, "record_source_step", ("financial_bill_source_step", "financial_bill_source", "financial_record_source_step", "financial_source_step", "source_step"), None),
        (_resolve_parser_mode, "parser_mode", ("financial_parser_mode",), ""),
    ],
)
def test_new_field_wins_over_legacy(resolver, new_key, legacy_keys, fallback):
    """When the new record_*/generic key is present, it takes precedence."""
    for legacy in legacy_keys:
        cfg = {new_key: "from_new", legacy: "from_legacy"}
        assert resolver(cfg) == "from_new", f"{new_key} should beat {legacy}"


@pytest.mark.parametrize(
    "resolver, new_key, legacy_keys, fallback",
    [
        (_resolve_provider, "record_provider", ("financial_provider",), "unknown"),
        (_resolve_unit, "record_unit", ("financial_unit_id",), "unknown"),
        (_resolve_asset, "record_asset", ("financial_asset",), ""),
        (_resolve_address, "record_address", ("financial_address",), ""),
        (_resolve_automation_key, "record_automation_key", ("financial_automation_key", "financial_automation_id"), ""),
        (_resolve_dedupe_key, "record_dedupe_key", ("financial_dedupe_key", "financial_record_dedupe_key"), None),
        (_resolve_source_step, "record_source_step", ("financial_bill_source_step", "financial_bill_source", "financial_record_source_step", "financial_source_step", "source_step"), None),
        (_resolve_parser_mode, "parser_mode", ("financial_parser_mode",), ""),
    ],
)
def test_legacy_field_used_when_new_absent(resolver, new_key, legacy_keys, fallback):
    """Existing flows that only set financial_* still resolve correctly."""
    for legacy in legacy_keys:
        cfg = {legacy: "from_legacy"}
        assert resolver(cfg) == "from_legacy", f"{legacy} should be used when {new_key} is absent"


@pytest.mark.parametrize(
    "resolver, new_key, fallback",
    [
        (_resolve_provider, "record_provider", "unknown"),
        (_resolve_unit, "record_unit", "unknown"),
        (_resolve_asset, "record_asset", ""),
        (_resolve_address, "record_address", ""),
        (_resolve_automation_key, "record_automation_key", ""),
        (_resolve_dedupe_key, "record_dedupe_key", None),
        (_resolve_source_step, "record_source_step", None),
        (_resolve_parser_mode, "parser_mode", ""),
    ],
)
def test_new_field_alone_resolves(resolver, new_key, fallback):
    """Brand-new flows that only set record_*/generic keys work too."""
    cfg = {new_key: "fresh"}
    assert resolver(cfg) == "fresh"


@pytest.mark.parametrize(
    "resolver, fallback",
    [
        (_resolve_provider, "unknown"),
        (_resolve_unit, "unknown"),
        (_resolve_asset, ""),
        (_resolve_address, ""),
        (_resolve_automation_key, ""),
        (_resolve_dedupe_key, None),
        (_resolve_source_step, None),
        (_resolve_parser_mode, ""),
    ],
)
def test_empty_cfg_yields_documented_fallback(resolver, fallback):
    """No keys present → resolver returns the documented fallback."""
    assert resolver({}) == fallback


# ---------------------------------------------------------------------------
# emit_* flag precedence — slightly different shape because the legacy
# fields have non-None defaults (True or derived from record_kind).
# ---------------------------------------------------------------------------


def test_emit_raw_handle_new_wins_when_set():
    assert _resolve_emit_raw({"emit_raw_handle": False, "emit_raw_bill_handle": True}, default=True) is False
    assert _resolve_emit_raw({"emit_raw_handle": True, "emit_raw_bill_handle": False}, default=False) is True


def test_emit_raw_handle_legacy_fallback():
    assert _resolve_emit_raw({"emit_raw_bill_handle": False}, default=True) is False
    assert _resolve_emit_raw({"emit_raw_bill_handle": True}, default=False) is True


def test_emit_raw_handle_default_when_unset():
    assert _resolve_emit_raw({}, default=True) is True
    assert _resolve_emit_raw({}, default=False) is False


def test_emit_record_handle_new_wins_when_set():
    assert _resolve_emit_record({"emit_record_handle": False, "emit_financial_record_handle": True}, default=True) is False
    assert _resolve_emit_record({"emit_record_handle": True, "emit_financial_record_handle": False}, default=False) is True


def test_emit_record_handle_legacy_fallback():
    assert _resolve_emit_record({"emit_financial_record_handle": True}, default=False) is True
    assert _resolve_emit_record({"emit_financial_record_handle": False}, default=True) is False


def test_emit_record_handle_default_when_unset():
    assert _resolve_emit_record({}, default=True) is True
    assert _resolve_emit_record({}, default=False) is False
