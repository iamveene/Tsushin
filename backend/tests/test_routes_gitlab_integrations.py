"""GitLab integration route/service tests."""

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

from api import routes_gitlab_integrations  # noqa: E402
from api.routes_gitlab_integrations import (  # noqa: E402
    GitLabIntegrationCreate,
    GitLabIntegrationUpdate,
    create_gitlab_integration,
    delete_gitlab_integration,
    list_gitlab_integrations,
    update_gitlab_integration,
)
from models import (  # noqa: E402
    Agent,
    AgentSkillIntegration,
    Base,
    Contact,
    GitLabChannelInstance,
    GitLabIntegration,
    HubIntegration,
    OAuthToken,
)
from models_rbac import Tenant, User  # noqa: E402
from services.gitlab_integration_service import (  # noqa: E402
    load_gitlab_integration,
    normalize_project_path,
    pat_preview,
)


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
            OAuthToken.__table__,
            GitLabIntegration.__table__,
            GitLabChannelInstance.__table__,
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


def _seed_tenant_user(db, *, tenant_id: str = "acme", user_id: int = 1) -> None:
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{tenant_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )
    db.commit()


def test_gitlab_integration_crud_normalizes_project_path_and_tenant_scope(monkeypatch, db_session):
    _seed_tenant_user(db_session, tenant_id="acme", user_id=1)
    _seed_tenant_user(db_session, tenant_id="other", user_id=2)
    monkeypatch.setattr(
        routes_gitlab_integrations,
        "encrypt_gitlab_pat",
        lambda db, tenant_id, plaintext: f"enc:{tenant_id}:{plaintext}",
    )

    created = create_gitlab_integration(
        GitLabIntegrationCreate(
            integration_name="GitLab Main",
            pat_token="glpat-secret",
            default_namespace="/acme/platform/",
            default_project="tsushin",
        ),
        ctx=_ctx("acme"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert created.provider == "gitlab"
    assert created.pat_token_preview == "glpa...cret"
    assert created.default_project_path == "acme/platform/tsushin"
    assert list_gitlab_integrations(ctx=_ctx("other"), _user=SimpleNamespace(id=2), db=db_session) == []

    loaded = load_gitlab_integration(
        db_session, tenant_id="acme", integration_id=created.id, require_active=True
    )
    assert loaded is not None
    assert loaded.pat_token_encrypted == "enc:acme:glpat-secret"
    assert load_gitlab_integration(db_session, tenant_id="other", integration_id=created.id) is None

    updated = update_gitlab_integration(
        created.id,
        GitLabIntegrationUpdate(default_project_path="acme/infra/tools"),
        ctx=_ctx("acme"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    assert updated.default_project_path == "acme/infra/tools"

    delete_gitlab_integration(created.id, ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session)
    assert list_gitlab_integrations(ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session) == []


def test_gitlab_integration_trigger_count_and_delete_use_fk(db_session):
    _seed_tenant_user(db_session, tenant_id="acme", user_id=1)
    integration = GitLabIntegration(
        id=10,
        tenant_id="acme",
        type="gitlab",
        name="GitLab A",
        display_name="GitLab A",
        provider="gitlab",
        auth_method="pat",
        pat_token_encrypted="encrypted",
        default_project_path="acme/platform",
        is_active=True,
    )
    db_session.add(integration)
    db_session.add(
        GitLabChannelInstance(
            id=20,
            tenant_id="acme",
            integration_name="Repo trigger",
            gitlab_integration_id=10,
            project_path="acme/platform",
            created_by=1,
            events=["push"],
            is_active=True,
            status="active",
        )
    )
    db_session.commit()

    listed = list_gitlab_integrations(ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session)
    assert listed[0].trigger_count == 1

    with pytest.raises(HTTPException) as exc:
        delete_gitlab_integration(10, ctx=_ctx("acme"), _user=SimpleNamespace(id=1), db=db_session)
    assert exc.value.status_code == 409


def test_gitlab_service_helpers_normalize_project_paths():
    assert normalize_project_path(" /group/subgroup/project/ ") == "group/subgroup/project"
    assert normalize_project_path("///") is None
    assert pat_preview("glpat-secret") == "glpa...cret"
