"""Route-handler contract tests for the ASR instance routes (G5 gap closure).

Covers the contract surface of ``/api/asr-instances/*`` by calling the route
handler functions directly (rather than via TestClient + auth middleware) —
this isolates the response-shape contract from auth/session concerns. Auth
is enforced separately by the require_permission dependency, which is well
tested elsewhere; here we only care that the handlers themselves return the
right shape and exercise tenant-scoped queries correctly.

Covered:
  * ``DELETE /api/asr-instances/{id}`` returns ``{detail, cascade}`` shape
    where cascade = ``{reassigned, disabled, successor_instance_id}``.
  * ``DELETE`` with a nonexistent id raises HTTPException 404.
  * ``DELETE`` cross-tenant raises HTTPException 404 (BOLA isolation).
  * ``GET /api/asr-instances`` list shape stays stable after a DELETE.
  * Cascade summary ``disabled`` count is non-zero when no successor exists
    and the tenant has at least one pinned audio_transcript skill.

Run inside the backend container:

    docker exec -e DATABASE_URL=postgresql://tsushin:tsushin_dev@tsushin-postgres:5432/tsushin \
        tsushin-backend pytest backend/tests/test_asr_routes_http.py -v
"""

from __future__ import annotations

import os
import secrets
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="route-handler tests require a live DATABASE_URL — run inside tsushin-backend",
)


# --- Helpers ----------------------------------------------------------------


def _make_ctx(tenant_id: str, db: Session):
    """Build a duck-typed TenantContext that the route handlers only read
    ``ctx.tenant_id`` from. The User object isn't introspected by the ASR
    routes, so a SimpleNamespace stub suffices."""
    from auth_dependencies import TenantContext
    fake_user = SimpleNamespace(
        id="test-user-id",
        email="test@example.com",
        tenant_id=tenant_id,
        is_global_admin=False,
        is_active=True,
    )
    return TenantContext(fake_user, db)


def _make_tenant(db: Session, tid: str) -> None:
    from models_rbac import Tenant
    t = Tenant(
        id=tid,
        name=f"HTTP Test {tid[-6:]}",
        slug=f"http-{tid[-10:]}",
        plan="dev",
    )
    db.add(t)
    db.commit()


def _create_asr_instance(db: Session, tenant_id: str, name: str, vendor: str = "openai_whisper") -> int:
    from services.whisper_instance_service import WhisperInstanceService
    inst = WhisperInstanceService.create_instance(
        tenant_id=tenant_id,
        vendor=vendor,
        instance_name=name,
        db=db,
        default_model="base" if vendor == "openai_whisper" else "Systran/faster-distil-whisper-small.en",
        auto_provision=False,
    )
    return inst.id


def _cleanup_tenant(db: Session, tid: str) -> None:
    from models_rbac import Tenant
    from models import ASRInstance, Agent, AgentSkill, Contact

    db.query(AgentSkill).filter(
        AgentSkill.agent_id.in_(
            db.query(Agent.id).filter(Agent.tenant_id == tid)
        )
    ).delete(synchronize_session=False)
    db.query(Agent).filter(Agent.tenant_id == tid).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.tenant_id == tid).delete(synchronize_session=False)
    db.query(ASRInstance).filter(ASRInstance.tenant_id == tid).delete(synchronize_session=False)
    db.query(Tenant).filter(Tenant.id == tid).delete(synchronize_session=False)
    db.commit()


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(os.environ["DATABASE_URL"])
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def tenant_id(db: Session) -> Iterator[str]:
    tid = f"asr-http-{secrets.token_hex(6)}"
    _make_tenant(db, tid)
    try:
        yield tid
    finally:
        _cleanup_tenant(db, tid)


# --- Tests ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_cascade_shape(db, tenant_id):
    from api.routes_asr_instances import delete_asr_instance
    inst_id = _create_asr_instance(db, tenant_id, "whisper-test-1")
    ctx = _make_ctx(tenant_id, db)

    body = await delete_asr_instance(instance_id=inst_id, remove_volume=False, ctx=ctx, db=db)

    assert set(body.keys()) >= {"detail", "cascade"}, f"missing keys: {body!r}"
    cascade = body["cascade"]
    assert isinstance(cascade, dict)
    assert set(cascade.keys()) == {"reassigned", "disabled", "successor_instance_id"}
    assert isinstance(cascade["reassigned"], int)
    assert isinstance(cascade["disabled"], int)
    assert cascade["successor_instance_id"] is None or isinstance(cascade["successor_instance_id"], int)


@pytest.mark.asyncio
async def test_delete_nonexistent_raises_404(db, tenant_id):
    from api.routes_asr_instances import delete_asr_instance
    ctx = _make_ctx(tenant_id, db)

    with pytest.raises(HTTPException) as exc:
        await delete_asr_instance(instance_id=999_999_999, remove_volume=False, ctx=ctx, db=db)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_cross_tenant_raises_404_bola(db):
    """BOLA isolation: tenant B cannot delete tenant A's ASR instance.

    Builds two tenants on the same DB session, creates an instance under A,
    then invokes the DELETE handler with B's TenantContext and verifies the
    handler raises 404 (NOT 403 — the existing convention is to return 404
    so we don't leak that the resource exists at all)."""
    from api.routes_asr_instances import delete_asr_instance
    from models import ASRInstance

    tid_a = f"asr-bola-a-{secrets.token_hex(5)}"
    tid_b = f"asr-bola-b-{secrets.token_hex(5)}"
    _make_tenant(db, tid_a)
    _make_tenant(db, tid_b)
    inst_id = _create_asr_instance(db, tid_a, "whisper-tenant-a")

    ctx_b = _make_ctx(tid_b, db)
    try:
        with pytest.raises(HTTPException) as exc:
            await delete_asr_instance(instance_id=inst_id, remove_volume=False, ctx=ctx_b, db=db)
        assert exc.value.status_code == 404, f"BOLA leak: tenant B got {exc.value.status_code}"

        # Verify tenant A's instance is still alive.
        still = db.query(ASRInstance).filter(
            ASRInstance.id == inst_id, ASRInstance.is_active == True,
        ).first()
        assert still is not None, "tenant A's instance was unexpectedly deleted"
    finally:
        _cleanup_tenant(db, tid_a)
        _cleanup_tenant(db, tid_b)


@pytest.mark.asyncio
async def test_list_unaffected_after_delete(db, tenant_id):
    from api.routes_asr_instances import list_asr_instances, delete_asr_instance
    id1 = _create_asr_instance(db, tenant_id, "whisper-keep")
    id2 = _create_asr_instance(db, tenant_id, "whisper-delete")
    ctx = _make_ctx(tenant_id, db)

    before = await list_asr_instances(vendor=None, ctx=ctx, db=db)
    before_ids = {i["id"] for i in before}
    assert id1 in before_ids and id2 in before_ids
    assert all("vendor" in i and "instance_name" in i for i in before)

    await delete_asr_instance(instance_id=id2, remove_volume=False, ctx=ctx, db=db)

    after = await list_asr_instances(vendor=None, ctx=ctx, db=db)
    after_ids = {i["id"] for i in after}
    assert id1 in after_ids
    assert id2 not in after_ids
    assert all("vendor" in i and "instance_name" in i for i in after)


@pytest.mark.asyncio
async def test_delete_cascade_disables_skills_when_no_successor(db, tenant_id):
    """Functional roundtrip — pin a synthetic agent skill to a single
    instance, delete it, confirm the cascade.disabled count reflects the
    pinned skill (no successor → disabled, not reassigned)."""
    from api.routes_asr_instances import delete_asr_instance
    from models import Agent, AgentSkill, Contact
    inst_id = _create_asr_instance(db, tenant_id, "whisper-only-one")

    contact = Contact(tenant_id=tenant_id, friendly_name=f"http-test-{secrets.token_hex(3)}", is_active=True)
    db.add(contact)
    db.flush()
    agent = Agent(tenant_id=tenant_id, contact_id=contact.id, system_prompt="cascade test", is_active=True)
    db.add(agent)
    db.flush()
    skill = AgentSkill(
        agent_id=agent.id,
        skill_type="audio_transcript",
        is_enabled=True,
        config={"asr_mode": "instance", "asr_instance_id": inst_id, "language": "auto"},
    )
    db.add(skill)
    db.commit()

    ctx = _make_ctx(tenant_id, db)
    body = await delete_asr_instance(instance_id=inst_id, remove_volume=False, ctx=ctx, db=db)
    cascade = body["cascade"]

    assert cascade["reassigned"] == 0, f"expected 0 reassigned, got {cascade!r}"
    assert cascade["disabled"] == 1, f"expected 1 disabled, got {cascade!r}"
    assert cascade["successor_instance_id"] is None

    db.refresh(skill)
    assert skill.is_enabled is False
    assert skill.config["asr_mode"] == "openai"
    assert skill.config["asr_instance_id"] is None
