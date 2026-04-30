"""GitHub integration route tests for FK-linked trigger usage."""

from __future__ import annotations

import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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

from api.routes_github_integrations import (  # noqa: E402
    delete_github_integration,
    list_github_integrations,
)
from models import (  # noqa: E402
    Agent,
    AgentSkillIntegration,
    Base,
    Contact,
    GitHubChannelInstance,
    GitHubIntegration,
    HubIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            HubIntegration.__table__,
            GitHubIntegration.__table__,
            GitHubChannelInstance.__table__,
            AgentSkillIntegration.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ctx(tenant_id: str):
    return SimpleNamespace(tenant_id=tenant_id)


def test_github_integration_trigger_count_and_delete_use_fk(db_session):
    db_session.add(Tenant(id="acme", name="Acme", slug="acme"))
    db_session.add(User(id=1, tenant_id="acme", email="owner@example.com", password_hash="x", is_active=True))
    integration = GitHubIntegration(
        id=10,
        tenant_id="acme",
        type="github",
        name="GitHub A",
        display_name="GitHub A",
        provider="github",
        auth_method="pat",
        pat_token_encrypted="encrypted",
        default_owner="unused",
        default_repo="unused",
        is_active=True,
    )
    db_session.add(integration)
    db_session.add(
        GitHubChannelInstance(
            id=20,
            tenant_id="acme",
            integration_name="Repo trigger",
            github_integration_id=10,
            repo_owner="octo",
            repo_name="repo",
            created_by=1,
            events=["push"],
            is_active=True,
            status="active",
        )
    )
    db_session.commit()

    listed = list_github_integrations(ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session)
    assert listed[0].trigger_count == 1

    with pytest.raises(HTTPException) as exc:
        delete_github_integration(10, ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session)
    assert exc.value.status_code == 409
