"""v0.7.x — read-only ``/api/feature-flags`` endpoint.

Surfaces the feature flags from ``config/feature_flags.py`` to the
frontend so it can conditionally render UI affordances (e.g. the
case-memory wizard step appears only when ``case_memory_enabled`` is
true) without baking the values into the JS bundle at build time.

Auth model (post-refactor):
  - Authenticated tenant member required. Two of the four flags
    (``case_memory_enabled``, ``case_memory_recap_enabled``) are now
    per-tenant DB-backed booleans (see ``Tenant.case_memory_enabled``
    column added in alembic 0077), so we need ``ctx.tenant_id`` to
    answer correctly. The two ``flows_*`` flags are still env-driven
    globals but we return them on the same payload for symmetry.

Caching:
  - Flag values are read fresh on every request. Env-driven flags are
    a few ``os.getenv`` calls; the per-tenant DB flags are a single
    indexed primary-key lookup against ``tenants``. Both are cheap.
    Avoiding a cache means flipping a tenant's column in the settings
    UI is reflected on the very next request without an eviction step.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context
from db import get_db

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/api/feature-flags", tags=["feature-flags"])


class FeatureFlagsResponse(BaseModel):
    """Snapshot of the feature flags exposed to the frontend.

    Each field maps 1:1 to a function in ``config/feature_flags.py``
    and is read at request time so a settings-UI toggle (per-tenant
    flags) or a backend restart (env-driven flags) is enough to
    propagate a change to every authenticated client.
    """

    case_memory_enabled: bool
    case_memory_recap_enabled: bool
    trigger_binding_enabled: bool
    auto_generation_enabled: bool


@router.get("", response_model=FeatureFlagsResponse)
def get_feature_flags(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
) -> FeatureFlagsResponse:
    """Return the current snapshot of feature flags for the caller's tenant.

    Auth: any authenticated tenant member. The ``case_memory_*`` fields
    reflect the **caller's tenant** row (per-tenant SaaS config); the
    ``flows_*`` fields are global env-driven booleans (operator
    deploy-time config).
    """
    # Lazy import so test stubs that don't import the whole module tree
    # can still import this route module without pulling all of
    # ``config/feature_flags.py`` and its env defaults.
    from config.feature_flags import (
        case_memory_enabled,
        case_memory_recap_enabled,
        flows_auto_generation_enabled,
        flows_trigger_binding_enabled,
    )

    return FeatureFlagsResponse(
        case_memory_enabled=case_memory_enabled(tenant_id=ctx.tenant_id, db=db),
        case_memory_recap_enabled=case_memory_recap_enabled(
            tenant_id=ctx.tenant_id, db=db
        ),
        trigger_binding_enabled=flows_trigger_binding_enabled(),
        auto_generation_enabled=flows_auto_generation_enabled(),
    )
