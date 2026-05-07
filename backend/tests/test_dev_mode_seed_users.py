"""Tests for the dev-mode user-seeding hook.

The hook in ``db._seed_dev_mode_users`` re-applies canonical passwords
to ``test@example.com`` / ``testadmin@example.com`` / ``member@example.com``
so the documented dev credentials always work after a backend boot, even
if some other code path rotated the hashes. The hook only fires when
``TSN_DEV_MODE_SEED_USERS=true`` is set; production stays untouched.
"""

from __future__ import annotations

import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub heavy optional deps before importing models — same shim style used
# by tests/test_flow_binding_service_gate_schema.py.
docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")


class _PasswordHasher:
    def hash(self, value):
        return f"hash::{value}"

    def verify(self, hashed, plain):
        return hashed == f"hash::{plain}"


argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
argon2_exceptions_stub.VerifyMismatchError = ValueError
argon2_exceptions_stub.InvalidHashError = ValueError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from models_rbac import Tenant, User  # noqa: E402
from models import Base  # noqa: E402
from config.feature_flags import dev_mode_seed_users_enabled  # noqa: E402
from db import _seed_dev_mode_users  # noqa: E402
from auth_utils import hash_password, verify_password  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[Tenant.__table__, User.__table__],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db.add(
        User(
            id=1,
            tenant_id="tenant-a",
            email="test@example.com",
            password_hash=hash_password("rotated-test-password"),
            is_active=True,
        )
    )
    db.add(
        User(
            id=2,
            email="testadmin@example.com",
            password_hash=hash_password("rotated-admin-password"),
            is_global_admin=True,
            is_active=True,
        )
    )
    db.add(
        User(
            id=3,
            tenant_id="tenant-a",
            email="member@example.com",
            password_hash=hash_password("rotated-member-password"),
            is_active=True,
        )
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()


def test_seeder_resets_known_dev_users(db_session):
    _seed_dev_mode_users(db_session)

    pairs = (
        ("test@example.com", "test1234"),
        ("testadmin@example.com", "admin1234"),
        ("member@example.com", "member1234"),
    )
    for email, expected_password in pairs:
        user = db_session.query(User).filter(User.email == email).one()
        assert verify_password(user.password_hash, expected_password), (
            f"{email} should accept the canonical dev password after seed"
        )


def test_seeder_skips_missing_users(db_session):
    # Ensure missing rows are tolerated — a fresh DB without testadmin must
    # not crash the boot path.
    db_session.query(User).filter(User.email == "testadmin@example.com").delete()
    db_session.commit()

    _seed_dev_mode_users(db_session)

    remaining = db_session.query(User).filter(User.email == "testadmin@example.com").first()
    assert remaining is None
    test_user = db_session.query(User).filter(User.email == "test@example.com").one()
    assert verify_password(test_user.password_hash, "test1234")


def test_seeder_does_not_touch_other_users(db_session):
    db_session.add(
        User(
            id=99,
            tenant_id="tenant-a",
            email="someone-else@example.com",
            password_hash=hash_password("operator-managed-secret"),
            is_active=True,
        )
    )
    db_session.commit()

    _seed_dev_mode_users(db_session)

    other = db_session.query(User).filter(User.email == "someone-else@example.com").one()
    assert verify_password(other.password_hash, "operator-managed-secret"), (
        "non-seeded users must keep their existing password hash"
    )


def test_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("TSN_DEV_MODE_SEED_USERS", raising=False)
    assert dev_mode_seed_users_enabled() is False


def test_feature_flag_respects_env(monkeypatch):
    monkeypatch.setenv("TSN_DEV_MODE_SEED_USERS", "true")
    assert dev_mode_seed_users_enabled() is True
    monkeypatch.setenv("TSN_DEV_MODE_SEED_USERS", "1")
    assert dev_mode_seed_users_enabled() is True
    monkeypatch.setenv("TSN_DEV_MODE_SEED_USERS", "no")
    assert dev_mode_seed_users_enabled() is False
