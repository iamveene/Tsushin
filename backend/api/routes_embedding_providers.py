"""Embedding provider options and diagnostics API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, require_permission
from services.embedding_provider_service import EmbeddingProviderService

router = APIRouter()

_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


def get_db():
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.rollback()
        except Exception:
            pass
        db.close()


class EmbeddingProviderTestRequest(BaseModel):
    provider: str = Field(default="local")
    provider_instance_id: Optional[int] = None
    model: str
    dimensions: Optional[int] = None
    text: str = "hello world"


@router.get("/embedding-providers/options", tags=["Embedding Providers"])
def list_embedding_provider_options(
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    return EmbeddingProviderService.list_options(ctx.tenant_id, db)


@router.post("/embedding-providers/test", tags=["Embedding Providers"])
async def test_embedding_provider(
    request: EmbeddingProviderTestRequest,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    return await EmbeddingProviderService.test_embedding(
        tenant_id=ctx.tenant_id,
        provider=request.provider,
        provider_instance_id=request.provider_instance_id,
        model=request.model,
        dimensions=request.dimensions,
        text=request.text,
        db=db,
    )
