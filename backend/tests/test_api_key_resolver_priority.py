"""
Resolver-priority regression for `services.api_key_service.get_api_key`.

Background — 2026-05-07 incident: an orphaned `ApiKey` row left over from a
QA-070 wave A1 wizard run (`sk-test-qa070-tts-fake-12345`) silently shadowed
the user's visible OpenAI ProviderInstance for weeks. The TTS-cloud branch of
the Provider Wizard wrote that key into the legacy `api_keys` table, the Hub
UI hid the row once a same-vendor ProviderInstance existed, and `get_api_key`
checked the legacy table BEFORE ProviderInstance — so every audio_transcript
call resolved to the fake key and 401'd at OpenAI.

These tests pin the resolver to the new contract: ProviderInstance for the
tenant wins, legacy ApiKey rows only fill in when no instance exists.
"""

import os
import sys
import types

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub heavy optional deps before models import (mirrors test_provider_instance_hardening).
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
from cryptography.fernet import Fernet
from models import ApiKey, Base, Config, ProviderInstance
from services import api_key_service


TENANT_A = "tenant-alpha"
TENANT_B = "tenant-beta"


def _make_session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    # The encryption_key_service auto-generates a Fernet key on first encrypt
    # if Config is empty, but cannot persist it to a fresh sqlite DB without
    # a Config row. Without a stable persisted key, the next call generates
    # a different key and decryption fails. Seed one here so encrypt/decrypt
    # use the same key throughout the test.
    fernet_key = Fernet.generate_key().decode()
    db.add(Config(messages_db_path="", api_key_encryption_key=fernet_key))
    db.commit()
    return db


def _seed_legacy_api_key(db, *, tenant_id, service, plaintext):
    """Insert a legacy ApiKey row using the encryption helpers under test."""
    encrypted = api_key_service._encrypt_api_key(plaintext, service, tenant_id, db)
    row = ApiKey(
        service=service,
        api_key=None,
        api_key_encrypted=encrypted,
        is_active=True,
        tenant_id=tenant_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _seed_provider_instance(
    db,
    *,
    tenant_id,
    vendor,
    plaintext,
    instance_name="op1",
    is_default=True,
    is_active=True,
):
    from services.provider_instance_service import ProviderInstanceService

    encrypted = ProviderInstanceService._encrypt_key(plaintext, tenant_id, db)
    instance = ProviderInstance(
        tenant_id=tenant_id,
        vendor=vendor,
        instance_name=instance_name,
        api_key_encrypted=encrypted,
        is_default=is_default,
        is_active=is_active,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return instance


def test_provider_instance_default_beats_legacy_api_key_row():
    """The exact 2026-05-07 incident: stale legacy row + valid ProviderInstance.

    Before the fix, get_api_key returned the legacy row first. The fix flips
    the priority so the visible ProviderInstance wins.
    """
    db = _make_session()
    try:
        _seed_legacy_api_key(
            db,
            tenant_id=TENANT_A,
            service="openai",
            plaintext="sk-test-qa070-tts-fake-12345",
        )
        _seed_provider_instance(
            db,
            tenant_id=TENANT_A,
            vendor="openai",
            plaintext="sk-real-op1-key",
        )

        resolved = api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
        assert resolved == "sk-real-op1-key", (
            "ProviderInstance default must win over legacy ApiKey row for "
            "the same vendor; otherwise an orphaned legacy row silently "
            "shadows the visible config (incident 2026-05-07)."
        )
    finally:
        db.close()


def test_legacy_api_key_used_when_no_provider_instance_exists():
    """Without a ProviderInstance, the legacy ApiKey row is the only candidate."""
    db = _make_session()
    try:
        _seed_legacy_api_key(
            db,
            tenant_id=TENANT_A,
            service="elevenlabs",
            plaintext="sk-elevenlabs-real",
        )

        resolved = api_key_service.get_api_key("elevenlabs", db, tenant_id=TENANT_A)
        assert resolved == "sk-elevenlabs-real"
    finally:
        db.close()


def test_inactive_provider_instance_falls_through_to_legacy_api_key():
    """An inactive ProviderInstance must NOT block the legacy fallback —
    otherwise disabling an instance would also silently disable the tenant.
    """
    db = _make_session()
    try:
        _seed_provider_instance(
            db,
            tenant_id=TENANT_A,
            vendor="openai",
            plaintext="sk-disabled-instance",
            is_active=False,
        )
        _seed_legacy_api_key(
            db,
            tenant_id=TENANT_A,
            service="openai",
            plaintext="sk-legacy-fallback",
        )

        resolved = api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
        assert resolved == "sk-legacy-fallback"
    finally:
        db.close()


def test_non_default_single_instance_still_wins_over_legacy():
    """If a tenant has exactly one active instance for a vendor (even without
    is_default=True), the resolver still prefers it over a legacy ApiKey row.
    Matches the existing 'only candidate' UX shortcut.
    """
    db = _make_session()
    try:
        _seed_provider_instance(
            db,
            tenant_id=TENANT_A,
            vendor="openai",
            plaintext="sk-single-non-default",
            is_default=False,
        )
        _seed_legacy_api_key(
            db,
            tenant_id=TENANT_A,
            service="openai",
            plaintext="sk-legacy-shadowed",
        )

        resolved = api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
        assert resolved == "sk-single-non-default"
    finally:
        db.close()


def test_resolver_is_tenant_isolated():
    """A ProviderInstance in tenant B must not satisfy a tenant-A lookup,
    and a legacy row scoped to tenant A must not leak to tenant B.
    """
    db = _make_session()
    try:
        _seed_provider_instance(
            db,
            tenant_id=TENANT_B,
            vendor="openai",
            plaintext="sk-tenant-b-instance",
        )
        _seed_legacy_api_key(
            db,
            tenant_id=TENANT_A,
            service="openai",
            plaintext="sk-tenant-a-legacy",
        )

        # Tenant A sees only its legacy row.
        assert (
            api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
            == "sk-tenant-a-legacy"
        )
        # Tenant B sees only its instance.
        assert (
            api_key_service.get_api_key("openai", db, tenant_id=TENANT_B)
            == "sk-tenant-b-instance"
        )
    finally:
        db.close()


def test_system_wide_legacy_key_fills_in_when_nothing_tenant_scoped():
    """System-wide ApiKey (tenant_id=NULL) is the last-resort fallback."""
    db = _make_session()
    try:
        encrypted = api_key_service._encrypt_api_key(
            "sk-system-wide", "openai", None, db
        )
        row = ApiKey(
            service="openai",
            api_key=None,
            api_key_encrypted=encrypted,
            is_active=True,
            tenant_id=None,
        )
        db.add(row)
        db.commit()

        resolved = api_key_service.get_api_key("openai", db, tenant_id=TENANT_A)
        assert resolved == "sk-system-wide"
    finally:
        db.close()
