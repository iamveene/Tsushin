"""
Regression coverage for retiring legacy ``api_key`` runtime credentials.

The only supported use of the legacy table is migration/audit. Runtime callers
must resolve credentials through typed models: ProviderInstance, TTSInstance,
SearchProviderIntegration, GoogleFlightsIntegration, AmadeusIntegration, or
SearxngInstance.
"""

import os
import sys
import types

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub heavy optional deps before models import.
docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")


class _PasswordHasher:
    def hash(self, value):
        return value

    def verify(self, hashed, plain):
        return hashed == plain


argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
argon2_exceptions_stub.VerifyMismatchError = ValueError
argon2_exceptions_stub.InvalidHashError = ValueError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401  # registers RBAC tables on Base before create_all
from models import (  # noqa: E402
    ApiKey,
    Base,
    Config,
    GoogleFlightsIntegration,
    ProviderInstance,
    SearchProviderIntegration,
    SearxngInstance,
    TTSInstance,
)
from models_rbac import Tenant  # noqa: E402
from services import api_key_service  # noqa: E402
from services.google_flights_integration_service import resolve_google_flights_api_key  # noqa: E402
from services.legacy_api_key_migration_service import migrate_active_legacy_api_keys  # noqa: E402
from services.provider_instance_service import ProviderInstanceService  # noqa: E402
from services.search_provider_integration_service import resolve_search_provider_api_key  # noqa: E402
from services.tts_instance_service import TTSInstanceService  # noqa: E402


TENANT_A = "tenant-alpha"
TENANT_B = "tenant-beta"


def _make_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    fernet_key = Fernet.generate_key().decode()
    db.add(Config(messages_db_path="", api_key_encryption_key=fernet_key))
    db.commit()
    return db


def _seed_tenant(db, tenant_id: str, active: bool = True):
    tenant = Tenant(
        id=tenant_id,
        name=tenant_id,
        slug=tenant_id,
        is_active=active,
    )
    db.add(tenant)
    db.commit()
    return tenant


def _seed_legacy_api_key(db, *, tenant_id, service, plaintext, active=True):
    encrypted = api_key_service._encrypt_api_key(plaintext, service, tenant_id, db)
    row = ApiKey(
        service=service,
        api_key=None,
        api_key_encrypted=encrypted,
        is_active=active,
        tenant_id=tenant_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_legacy_runtime_resolver_is_retired():
    db = _make_session()
    try:
        with pytest.raises(RuntimeError, match="Legacy api_key runtime resolver is retired"):
            api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
        assert api_key_service.has_api_key("openai", db, tenant_id=TENANT_A) is False
        with pytest.raises(RuntimeError, match="Legacy api_key writes are retired"):
            api_key_service.store_api_key("openai", "sk-test", TENANT_A, db)
    finally:
        db.close()


def test_migration_backfills_typed_rows_and_disables_legacy_rows():
    db = _make_session()
    try:
        _seed_tenant(db, TENANT_A)
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="openai", plaintext="sk-openai-real")
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="elevenlabs", plaintext="sk-elevenlabs-real")
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="brave_search", plaintext="BSA-brave-real")
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="google_flights", plaintext="serpapi-flights-real")
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="searxng", plaintext="https://search.example.test")

        stats = migrate_active_legacy_api_keys(db)

        assert stats == {
            "legacy_rows_seen": 5,
            "legacy_rows_disabled": 5,
            "typed_rows_touched": 5,
        }
        assert db.query(ApiKey).filter(ApiKey.is_active == True).count() == 0  # noqa: E712

        provider = db.query(ProviderInstance).filter_by(tenant_id=TENANT_A, vendor="openai").one()
        assert ProviderInstanceService.resolve_api_key(provider, db) == "sk-openai-real"

        tts = db.query(TTSInstance).filter_by(tenant_id=TENANT_A, vendor="elevenlabs").one()
        assert tts.api_key_preview == "sk-e...real"
        assert TTSInstanceService.resolve_hosted_api_key("elevenlabs", TENANT_A, db) == "sk-elevenlabs-real"

        search = db.query(SearchProviderIntegration).filter_by(tenant_id=TENANT_A, provider_id="brave").one()
        assert search.api_key_preview == "BSA-...real"
        assert resolve_search_provider_api_key("brave", TENANT_A, db) == "BSA-brave-real"

        flights = db.query(GoogleFlightsIntegration).filter_by(tenant_id=TENANT_A).one()
        assert flights.display_name == "Google Flights"
        assert resolve_google_flights_api_key(TENANT_A, db) == "serpapi-flights-real"

        searxng = db.query(SearxngInstance).filter_by(tenant_id=TENANT_A).one()
        assert searxng.base_url == "https://search.example.test"
    finally:
        db.close()


def test_serpapi_maps_to_search_provider_only():
    db = _make_session()
    try:
        _seed_tenant(db, TENANT_A)
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="serpapi", plaintext="serpapi-search-real")

        stats = migrate_active_legacy_api_keys(db)

        assert stats["legacy_rows_disabled"] == 1
        assert resolve_search_provider_api_key("google", TENANT_A, db) == "serpapi-search-real"
        assert db.query(GoogleFlightsIntegration).filter_by(tenant_id=TENANT_A).count() == 0
    finally:
        db.close()


def test_system_wide_rows_expand_to_each_active_tenant():
    db = _make_session()
    try:
        _seed_tenant(db, TENANT_A)
        _seed_tenant(db, TENANT_B)
        _seed_tenant(db, "inactive-tenant", active=False)
        _seed_legacy_api_key(db, tenant_id=None, service="gemini", plaintext="gemini-system-key")

        stats = migrate_active_legacy_api_keys(db)

        assert stats["legacy_rows_seen"] == 1
        assert stats["legacy_rows_disabled"] == 1
        assert ProviderInstanceService.resolve_default_api_key("gemini", TENANT_A, db) == "gemini-system-key"
        assert ProviderInstanceService.resolve_default_api_key("gemini", TENANT_B, db) == "gemini-system-key"
        assert (
            db.query(ProviderInstance)
            .filter_by(tenant_id="inactive-tenant", vendor="gemini")
            .count()
            == 0
        )
    finally:
        db.close()


def test_unknown_active_legacy_service_blocks_migration():
    db = _make_session()
    try:
        _seed_tenant(db, TENANT_A)
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="mystery", plaintext="secret")

        with pytest.raises(RuntimeError, match="is not mapped"):
            migrate_active_legacy_api_keys(db)

        assert db.query(ApiKey).filter(ApiKey.service == "mystery", ApiKey.is_active == True).count() == 1  # noqa: E712
        assert db.query(ProviderInstance).count() == 0
    finally:
        db.close()


def test_incomplete_amadeus_legacy_row_blocks_migration():
    db = _make_session()
    try:
        _seed_tenant(db, TENANT_A)
        _seed_legacy_api_key(db, tenant_id=TENANT_A, service="amadeus", plaintext="client-id-only")

        with pytest.raises(RuntimeError, match="client_id:client_secret"):
            migrate_active_legacy_api_keys(db)

        assert db.query(ApiKey).filter(ApiKey.service == "amadeus", ApiKey.is_active == True).count() == 1  # noqa: E712
    finally:
        db.close()
