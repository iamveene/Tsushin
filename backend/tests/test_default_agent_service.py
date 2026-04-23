from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "default_agent_service.py"
MODULE_SPEC = importlib.util.spec_from_file_location("default_agent_service_test_module", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
svc = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(svc)


def _first_truthy(_db, _tenant_id, *agent_ids):
    return next((agent_id for agent_id in agent_ids if agent_id), None)


def test_channel_resolution_prefers_explicit_agent(monkeypatch):
    monkeypatch.setattr(svc, "is_default_agent_v2_enabled", lambda: True)
    monkeypatch.setattr(svc, "_first_active_agent", _first_truthy)
    monkeypatch.setattr(svc, "_resolve_contact_mapping", lambda *args, **kwargs: 11)
    monkeypatch.setattr(svc, "_resolve_user_channel_default_agent", lambda *args, **kwargs: 22)
    monkeypatch.setattr(svc, "_resolve_instance_default_agent", lambda *args, **kwargs: 33)
    monkeypatch.setattr(svc, "_resolve_legacy_bound_agent", lambda *args, **kwargs: 44)
    monkeypatch.setattr(svc, "_resolve_tenant_default_agent", lambda *args, **kwargs: 55)

    resolved = svc.get_default_agent(
        db=None,
        tenant_id="tenant-a",
        channel_type="whatsapp",
        instance_id=9,
        user_identifier="+5511999999999",
        contact_id=7,
        explicit_agent_id=99,
    )

    assert resolved == 99


def test_channel_resolution_prefers_user_default_over_instance_default(monkeypatch):
    monkeypatch.setattr(svc, "is_default_agent_v2_enabled", lambda: True)
    monkeypatch.setattr(svc, "_first_active_agent", _first_truthy)
    monkeypatch.setattr(svc, "_resolve_contact_mapping", lambda *args, **kwargs: None)
    monkeypatch.setattr(svc, "_resolve_user_channel_default_agent", lambda *args, **kwargs: 22)
    monkeypatch.setattr(svc, "_resolve_instance_default_agent", lambda *args, **kwargs: 33)
    monkeypatch.setattr(svc, "_resolve_legacy_bound_agent", lambda *args, **kwargs: 44)
    monkeypatch.setattr(svc, "_resolve_tenant_default_agent", lambda *args, **kwargs: 55)

    resolved = svc.get_default_agent(
        db=None,
        tenant_id="tenant-a",
        channel_type="whatsapp",
        instance_id=9,
        user_identifier="+5511999999999",
    )

    assert resolved == 22


def test_trigger_resolution_prefers_instance_default_then_tenant(monkeypatch):
    monkeypatch.setattr(svc, "is_default_agent_v2_enabled", lambda: True)
    monkeypatch.setattr(svc, "_first_active_agent", _first_truthy)
    monkeypatch.setattr(svc, "_resolve_instance_default_agent", lambda *args, **kwargs: 33)
    monkeypatch.setattr(svc, "_resolve_legacy_bound_agent", lambda *args, **kwargs: 44)
    monkeypatch.setattr(svc, "_resolve_tenant_default_agent", lambda *args, **kwargs: 55)

    resolved = svc.get_default_agent(
        db=None,
        tenant_id="tenant-a",
        channel_type="webhook",
        instance_id=9,
    )

    assert resolved == 33


def test_feature_flag_falls_back_to_tenant_default(monkeypatch):
    monkeypatch.setattr(svc, "is_default_agent_v2_enabled", lambda: False)
    monkeypatch.setattr(svc, "_resolve_tenant_default_agent", lambda *args, **kwargs: 55)

    resolved = svc.get_default_agent(
        db=None,
        tenant_id="tenant-a",
        channel_type="webhook",
        instance_id=9,
        explicit_agent_id=99,
    )

    assert resolved == 55
