"""Sentinel provider-instance binding tests.

These tests keep the new Sentinel LLM linkage tenant-scoped and verify the
runtime still forwards the selected ProviderInstance into AIClient.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker


_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401, E402  — register Tenant/User tables
from models import Base, ProviderInstance, SentinelConfig, SentinelProfile  # noqa: E402
from services.sentinel_effective_config import SentinelEffectiveConfig  # noqa: E402
from services.sentinel_profiles_service import SentinelProfilesService  # noqa: E402
from services.sentinel_service import SentinelService  # noqa: E402
from services.provider_instance_service import ProviderInstanceService  # noqa: E402
from api.routes_sentinel import (  # noqa: E402
    SentinelConfigUpdate,
    _get_active_provider_instance_or_400,
    update_sentinel_config,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _make_instance(
    db,
    tenant_id: str,
    vendor: str = "gemini",
    *,
    name: str = "Gemini prod",
    is_active: bool = True,
    models: list[str] | None = None,
) -> ProviderInstance:
    instance = ProviderInstance(
        tenant_id=tenant_id,
        vendor=vendor,
        instance_name=name if name != "Gemini prod" else f"{vendor} prod",
        base_url=f"https://example.test/{vendor}",
        is_default=True,
        is_active=is_active,
        available_models=models or ["gemini-2.5-flash-lite"],
        health_status="healthy",
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def _make_system_sentinel_config(db) -> SentinelConfig:
    config = SentinelConfig(
        tenant_id=None,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def test_active_provider_instance_lookup_is_tenant_scoped(db):
    instance = _make_instance(db, "tenant-a")

    found = _get_active_provider_instance_or_400(db, "tenant-a", instance.id)

    assert found.id == instance.id
    with pytest.raises(HTTPException) as cross_tenant:
        _get_active_provider_instance_or_400(db, "tenant-b", instance.id)
    assert cross_tenant.value.status_code == 400


def test_active_provider_instance_lookup_rejects_inactive_rows(db):
    instance = _make_instance(db, "tenant-a", is_active=False)

    with pytest.raises(HTTPException) as exc:
        _get_active_provider_instance_or_400(db, "tenant-a", instance.id)

    assert exc.value.status_code == 400


def test_sentinel_config_update_links_provider_instance_and_syncs_legacy_provider(db):
    _make_system_sentinel_config(db)
    instance = _make_instance(db, "tenant-a", vendor="openai", models=["gpt-5-mini"])

    result = asyncio.run(
        update_sentinel_config(
            update=SentinelConfigUpdate(
                provider_instance_id=instance.id,
                llm_provider="gemini",
                llm_model="gpt-5-mini",
            ),
            current_user=SimpleNamespace(id=1),
            ctx=SimpleNamespace(tenant_id="tenant-a"),
            db=db,
        )
    )

    config = db.query(SentinelConfig).filter(SentinelConfig.tenant_id == "tenant-a").one()
    assert result.provider_instance_id == instance.id
    assert config.provider_instance_id == instance.id
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-5-mini"


def test_sentinel_profile_create_and_update_validate_provider_instance_binding(db):
    gemini = _make_instance(db, "tenant-a", vendor="gemini")
    openai = _make_instance(db, "tenant-a", vendor="openai", models=["gpt-5-mini"])
    other_tenant = _make_instance(db, "tenant-b", vendor="anthropic")
    service = SentinelProfilesService(db, "tenant-a")

    profile = service.create_profile(
        {
            "name": "Strict",
            "slug": "strict",
            "provider_instance_id": gemini.id,
            "llm_provider": "openai",
            "llm_model": "gemini-2.5-flash-lite",
            "detection_overrides": "{}",
        },
        created_by=1,
    )

    assert profile.provider_instance_id == gemini.id
    assert profile.llm_provider == "gemini"

    updated = service.update_profile(
        profile.id,
        {
            "provider_instance_id": openai.id,
            "llm_model": "gpt-5-mini",
        },
        updated_by=1,
    )
    assert updated is not None
    assert updated.provider_instance_id == openai.id
    assert updated.llm_provider == "openai"
    assert updated.llm_model == "gpt-5-mini"

    with pytest.raises(ValueError):
        service.update_profile(profile.id, {"provider_instance_id": other_tenant.id})


def test_sentinel_effective_profile_includes_provider_instance_id(db):
    instance = _make_instance(db, "tenant-a", vendor="gemini")
    service = SentinelProfilesService(db, "tenant-a")
    profile = service.create_profile(
        {
            "name": "Default",
            "slug": "default",
            "is_default": True,
            "provider_instance_id": instance.id,
            "llm_model": "gemini-2.5-flash-lite",
            "detection_overrides": "{}",
        }
    )
    service.assign_profile(profile.id)

    effective = service.get_effective_config()

    assert effective is not None
    assert effective.provider_instance_id == instance.id
    assert effective.llm_provider == "gemini"


def test_sentinel_runtime_passes_provider_instance_id_to_ai_client(db, monkeypatch):
    captured: dict[str, object] = {}

    class FakeAIClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.db = kwargs.get("db")

        async def generate(self, **_kwargs):
            return {"content": "{\"is_threat_detected\": false}"}

    import agent.ai_client as ai_client

    monkeypatch.setattr(ai_client, "AIClient", FakeAIClient)
    service = SentinelService(db, tenant_id="tenant-a")
    config = SentinelEffectiveConfig(
        provider_instance_id=123,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
        llm_temperature=0.1,
        llm_max_tokens=256,
    )

    result = asyncio.run(service._call_llm("system", "user", config))

    assert captured["provider_instance_id"] == 123
    assert captured["tenant_id"] == "tenant-a"
    assert captured["provider"] == "gemini"
    assert result["content"] == "{\"is_threat_detected\": false}"


def test_provider_instance_delete_reassigns_sentinel_config_and_profiles(db):
    source = _make_instance(
        db,
        "tenant-a",
        vendor="gemini",
        name="Gemini source",
        models=["gemini-2.5-flash-lite"],
    )
    target = _make_instance(
        db,
        "tenant-a",
        vendor="openai",
        name="OpenAI target",
        models=["gpt-5-mini"],
    )
    config = SentinelConfig(
        tenant_id="tenant-a",
        provider_instance_id=source.id,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
    )
    profile = SentinelProfile(
        tenant_id="tenant-a",
        name="Tenant strict",
        slug="tenant-strict",
        provider_instance_id=source.id,
        llm_provider="gemini",
        llm_model="gemini-2.5-flash-lite",
        detection_overrides="{}",
    )
    db.add_all([config, profile])
    db.commit()

    usage = ProviderInstanceService.get_instance_usage(source.id, "tenant-a", db)
    result = ProviderInstanceService.delete_instance_with_reassign(
        source.id,
        "tenant-a",
        db,
        reassign_to_instance_id=target.id,
    )

    db.refresh(source)
    db.refresh(config)
    db.refresh(profile)
    assert usage["dependent_count"] == 2
    assert usage["sentinel_configs"][0]["id"] == config.id
    assert usage["sentinel_profiles"][0]["id"] == profile.id
    assert source.is_active is False
    assert result["reassigned_count"] == 2
    assert config.provider_instance_id == target.id
    assert config.llm_provider == "openai"
    assert config.llm_model == "gpt-5-mini"
    assert profile.provider_instance_id == target.id
    assert profile.llm_provider == "openai"
    assert profile.llm_model == "gpt-5-mini"
