"""
Phase 21: Provider Instance Service

CRUD operations, API key encryption, and SSRF validation for provider instances.
Each tenant can configure multiple provider endpoints with independent API keys,
base URLs, and model availability.

Encryption pattern matches api_key_service.py (Fernet via TokenEncryption + encryption_key_service).
SSRF validation uses utils/ssrf_validator.py (DNS-resolution-based IP checking).
"""

import logging
import socket
import threading
from typing import Optional, List
from sqlalchemy.orm import Session
from models import ProviderInstance, ProviderConnectionAudit

logger = logging.getLogger(__name__)


# BUG-663: Linux-safe host resolution for reaching the host Ollama daemon
# from inside the backend container.
#
# `host.docker.internal` is guaranteed on Docker Desktop (macOS/Windows) and
# on recent Linux Docker Engine when the container is started with
# `--add-host=host.docker.internal:host-gateway`. On older Linux hosts or
# setups without that flag it does NOT resolve, causing every Ollama call
# to fail with gaierror. Fall back to the Docker default bridge gateway
# (172.17.0.1), which is reachable from any container on the default bridge
# or an attached user network.
_resolved_ollama_host: Optional[str] = None
_resolve_ollama_host_lock = threading.Lock()


def _resolve_ollama_host() -> str:
    """Return a hostname that reaches the host Ollama daemon from inside a
    container. Resolves once per process and caches the result.

    - If ``host.docker.internal`` resolves via DNS, return it.
    - On ``socket.gaierror`` (Linux hosts without host-gateway), fall back
      to ``172.17.0.1`` (the Docker default bridge gateway).
    """
    global _resolved_ollama_host
    if _resolved_ollama_host is not None:
        return _resolved_ollama_host
    with _resolve_ollama_host_lock:
        if _resolved_ollama_host is not None:
            return _resolved_ollama_host
        try:
            socket.gethostbyname("host.docker.internal")
            _resolved_ollama_host = "host.docker.internal"
        except socket.gaierror:
            logger.warning(
                "_resolve_ollama_host: 'host.docker.internal' did not resolve; "
                "falling back to Docker default-bridge gateway 172.17.0.1"
            )
            _resolved_ollama_host = "172.17.0.1"
        except Exception as e:
            # Defensive: any other socket error → same fallback so we don't
            # crash on exotic network setups.
            logger.warning(
                f"_resolve_ollama_host: unexpected error resolving "
                f"'host.docker.internal' ({e}); falling back to 172.17.0.1"
            )
            _resolved_ollama_host = "172.17.0.1"
        return _resolved_ollama_host


# Default base URLs for vendors (None = resolved at runtime / SDK default)
# BUG-663 follow-up: the Ollama default is resolved lazily via
# get_vendor_default_base_url("ollama") — NOT eagerly at module import —
# so a slow/blocking `host.docker.internal` DNS lookup cannot delay backend
# startup. Consumers that previously read VENDOR_DEFAULT_BASE_URLS["ollama"]
# must call get_vendor_default_base_url(vendor) instead.
VENDOR_DEFAULT_BASE_URLS = {
    "openai": None,
    "anthropic": None,
    "gemini": None,
    "groq": "https://api.groq.com/openai/v1",
    "grok": "https://api.x.ai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": None,  # Lazy: get_vendor_default_base_url("ollama")
    "vertex_ai": None,  # Region-specific — resolved dynamically from credentials
}


def get_vendor_default_base_url(vendor: str) -> Optional[str]:
    """Return the default base URL for a vendor, resolving Ollama lazily.

    Use this instead of direct `VENDOR_DEFAULT_BASE_URLS[vendor]` for code
    paths that need the effective fallback URL — the Ollama host depends
    on runtime DNS (`host.docker.internal` on Docker Desktop, fallback
    `172.17.0.1` on bare Linux).
    """
    if vendor == "ollama":
        return f"http://{_resolve_ollama_host()}:11434"
    return VENDOR_DEFAULT_BASE_URLS.get(vendor)

SUPPORTED_VENDORS = list(VENDOR_DEFAULT_BASE_URLS.keys()) + ["custom"]


class ProviderInstanceService:

    @staticmethod
    def ensure_ollama_instance(
        tenant_id: str,
        db: Session,
        auto_provision: bool = False,
    ) -> ProviderInstance:
        """Ensure a default Ollama provider instance exists for the tenant.

        If an active Ollama instance already exists, returns it.
        Otherwise, creates a new default instance using the Ollama base URL
        from the Config table (or the standard default).

        When ``auto_provision=True``, the caller is asking tsushin to manage a
        per-tenant Ollama container. We mark the row ``is_auto_provisioned=True``
        and kick off provisioning in a background thread so the HTTP request
        returns immediately.
        """
        existing = db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == 'ollama',
            ProviderInstance.is_active == True,
        ).first()
        if existing:
            return existing

        if auto_provision:
            # Create a bare auto-provisioned row; base_url is set by the
            # container manager once the DNS alias is known.
            instance = ProviderInstance(
                tenant_id=tenant_id,
                vendor='ollama',
                instance_name='Ollama (Managed)',
                base_url=None,
                is_default=True,
                is_active=True,
                is_auto_provisioned=True,
                container_status='creating',
            )
            db.add(instance)
            db.commit()
            db.refresh(instance)

            # Spawn background provisioning — do NOT block the request.
            instance_id = instance.id

            def _provision_bg():
                try:
                    from db import get_global_engine
                    from sqlalchemy.orm import sessionmaker
                    engine = get_global_engine()
                    if engine is None:
                        logger.error(
                            "ensure_ollama_instance auto_provision: "
                            "no global engine available"
                        )
                        return
                    BgSession = sessionmaker(bind=engine)
                    bg_db = BgSession()
                    try:
                        bg_inst = bg_db.query(ProviderInstance).filter(
                            ProviderInstance.id == instance_id,
                            ProviderInstance.tenant_id == tenant_id,
                        ).first()
                        if not bg_inst:
                            return
                        from services.ollama_container_manager import (
                            OllamaContainerManager,
                        )
                        OllamaContainerManager().provision(bg_inst, bg_db)
                    finally:
                        try:
                            bg_db.close()
                        except Exception:
                            pass
                except Exception as e:
                    logger.error(
                        f"ensure_ollama_instance auto_provision background "
                        f"error (instance={instance_id}): {e}",
                        exc_info=True,
                    )

            threading.Thread(
                target=_provision_bg,
                daemon=True,
                name=f"ollama-ensure-provision-{instance_id}",
            ).start()
            return instance

        # Derive base_url from Config table
        from models import Config
        config = db.query(Config).first()
        base_url = (
            config.ollama_base_url
            if config and config.ollama_base_url
            else f"http://{_resolve_ollama_host()}:11434"
        )

        return ProviderInstanceService.create_instance(
            tenant_id=tenant_id,
            vendor='ollama',
            instance_name='Ollama (Local)',
            db=db,
            base_url=base_url,
            is_default=True,
        )

    @staticmethod
    def provision_container(
        instance_id: int,
        tenant_id: str,
        db: Session,
        *,
        gpu_enabled: bool = False,
        mem_limit: str = "4g",
    ) -> ProviderInstance:
        """
        Prepare an existing Ollama ProviderInstance for container provisioning.

        Validates vendor=='ollama', marks the row as auto-provisioned with the
        requested sizing, commits, and returns the instance. The caller is
        expected to invoke ``OllamaContainerManager().provision(instance, db)``
        (typically in a background thread) using a fresh DB session.
        """
        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Provider instance {instance_id} not found")
        if instance.vendor != "ollama":
            raise ValueError(
                f"provision_container only supports Ollama (got {instance.vendor})"
            )

        instance.gpu_enabled = bool(gpu_enabled)
        instance.mem_limit = mem_limit or "4g"
        instance.is_auto_provisioned = True
        instance.container_status = "creating"
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def list_instances(tenant_id: str, db: Session, vendor: str = None, active_only: bool = True) -> List[ProviderInstance]:
        """List provider instances for a tenant, optionally filtered by vendor."""
        query = db.query(ProviderInstance).filter(ProviderInstance.tenant_id == tenant_id)
        if active_only:
            query = query.filter(ProviderInstance.is_active == True)
        if vendor:
            query = query.filter(ProviderInstance.vendor == vendor)
        return query.order_by(ProviderInstance.vendor, ProviderInstance.is_default.desc(), ProviderInstance.instance_name).all()

    @staticmethod
    def get_instance(instance_id: int, tenant_id: str, db: Session) -> Optional[ProviderInstance]:
        """Get single instance with tenant guard."""
        return db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id
        ).first()

    @staticmethod
    def get_default_instance(vendor: str, tenant_id: str, db: Session) -> Optional[ProviderInstance]:
        """Get default instance for a vendor+tenant."""
        return db.query(ProviderInstance).filter(
            ProviderInstance.vendor == vendor,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.is_default == True,
            ProviderInstance.is_active == True
        ).first()

    @staticmethod
    def create_instance(tenant_id: str, vendor: str, instance_name: str, db: Session,
                        base_url: str = None, api_key: str = None,
                        available_models: list = None, is_default: bool = False) -> ProviderInstance:
        """
        Create a new provider instance.
        - Validates base_url with SSRF validator if provided
        - Encrypts API key with Fernet (same pattern as api_key_service)
        - Enforces single default per (tenant_id, vendor)
        """
        # 1. Validate vendor
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(f"Unsupported vendor: {vendor}")

        # 2. SSRF validate base_url if provided
        if base_url:
            from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
            try:
                if vendor == "ollama":
                    validate_ollama_url(base_url)
                else:
                    validate_url(base_url)
            except SSRFValidationError as e:
                raise ValueError(f"URL validation failed: {e}")

        # 3. Encrypt API key
        api_key_encrypted = None
        if api_key:
            api_key_encrypted = ProviderInstanceService._encrypt_key(api_key, tenant_id, db)

        # 4. Enforce single default per (tenant_id, vendor) — clear BEFORE
        #    creating the new instance and flush to prevent race conditions
        #    where two concurrent creates both end up as default.
        if is_default:
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.vendor == vendor,
                ProviderInstance.is_default == True,
            ).update({"is_default": False}, synchronize_session="fetch")
            db.flush()

        # 5. BUG-670: purge soft-deleted rows with the same
        #    (tenant_id, instance_name) so a prior DELETE → re-create cycle
        #    doesn't hit the UniqueConstraint uq_provider_instance_tenant_name.
        #    Matches the SearXNG pattern in routes_searxng_instances.py.
        db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.instance_name == instance_name,
            ProviderInstance.is_active == False,
        ).delete(synchronize_session="fetch")
        db.flush()

        instance = ProviderInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            available_models=available_models or [],
            is_default=is_default,
        )
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def update_instance(instance_id: int, tenant_id: str, db: Session, **kwargs) -> Optional[ProviderInstance]:
        """Update instance. Re-validates base_url. Blank api_key keeps existing."""
        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None

        if "base_url" in kwargs and kwargs["base_url"]:
            from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
            try:
                if instance.vendor == "ollama":
                    validate_ollama_url(kwargs["base_url"])
                else:
                    validate_url(kwargs["base_url"])
            except SSRFValidationError as e:
                raise ValueError(f"URL validation failed: {e}")

        if "api_key" in kwargs:
            api_key = kwargs.pop("api_key")
            if api_key:  # Non-empty = update
                instance.api_key_encrypted = ProviderInstanceService._encrypt_key(api_key, tenant_id, db)
            # Empty/None = keep existing

        if kwargs.get("is_default"):
            # Clear other defaults BEFORE setting new one and flush
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.vendor == instance.vendor,
                ProviderInstance.id != instance_id,
                ProviderInstance.is_default == True,
            ).update({"is_default": False}, synchronize_session="fetch")
            db.flush()

        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)

        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        """Soft delete: set is_active=False. Clear provider_instance_id on affected agents."""
        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False

        from models import Agent
        db.query(Agent).filter(Agent.provider_instance_id == instance_id).update({"provider_instance_id": None})
        instance.is_active = False
        db.commit()
        return True

    # =========================================================================
    # Catalog / Usage / Cascade-aware delete (v0.7.0 LLM Provider consistency)
    # =========================================================================

    @staticmethod
    def get_catalog(tenant_id: str, db: Session) -> List[dict]:
        """Single source of truth for "what providers can an agent use" UI.

        Returns one dict per supported vendor with the vendor's display info
        and the tenant's active instances. The Studio agent edit modal, the
        agent creation wizard, the playground config panel and the Hub all
        consume this so they never drift apart.

        Each entry has: ``vendor``, ``display_name``, ``default_base_url``,
        ``supports_discovery``, ``creatable`` (always True for now),
        ``instances`` (list of active ProviderInstance dicts).
        """
        # Local import to avoid circulars with the API route module.
        from api.routes_provider_instances import (
            VENDOR_DISPLAY_NAMES,
            VENDORS_WITH_LIVE_DISCOVERY,
            VALID_VENDORS,
        )

        active_instances = (
            db.query(ProviderInstance)
            .filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.is_active == True,  # noqa: E712
            )
            .order_by(
                ProviderInstance.vendor,
                ProviderInstance.is_default.desc(),
                ProviderInstance.instance_name,
            )
            .all()
        )
        by_vendor: dict[str, list[ProviderInstance]] = {}
        for inst in active_instances:
            by_vendor.setdefault(inst.vendor, []).append(inst)

        ordered_vendors = [
            "openai", "anthropic", "gemini", "groq", "grok",
            "openrouter", "deepseek", "vertex_ai", "ollama", "custom",
        ]
        # Tail any extra vendors so nothing is silently hidden if VALID_VENDORS
        # ever expands without this list being updated.
        for v in sorted(VALID_VENDORS):
            if v not in ordered_vendors:
                ordered_vendors.append(v)

        out: list[dict] = []
        for vendor in ordered_vendors:
            if vendor not in VALID_VENDORS:
                continue
            try:
                default_url = get_vendor_default_base_url(vendor)
            except Exception:
                default_url = None
            instances = [
                {
                    "id": inst.id,
                    "instance_name": inst.instance_name,
                    "base_url": inst.base_url,
                    "is_default": bool(inst.is_default),
                    "available_models": list(inst.available_models or []),
                    "health_status": inst.health_status or "unknown",
                    "health_status_reason": inst.health_status_reason,
                    "is_auto_provisioned": bool(getattr(inst, "is_auto_provisioned", False)),
                    "container_status": getattr(inst, "container_status", None),
                }
                for inst in by_vendor.get(vendor, [])
            ]
            out.append({
                "vendor": vendor,
                "display_name": VENDOR_DISPLAY_NAMES.get(vendor, vendor),
                "default_base_url": default_url,
                "supports_discovery": vendor in VENDORS_WITH_LIVE_DISCOVERY,
                "creatable": True,
                "instances": instances,
            })
        return out

    @staticmethod
    def get_instance_usage(instance_id: int, tenant_id: str, db: Session) -> dict:
        """Return the agents currently bound to this provider instance.

        Used by the pre-delete confirmation modal in Hub so the operator can
        choose where to reassign dependents before the instance disappears.
        Tenant-scoped — never leaks cross-tenant data.
        """
        from models import Agent, Contact

        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return {"instance_id": instance_id, "agents": [], "dependent_count": 0}

        rows = (
            db.query(Agent, Contact.friendly_name)
            .join(Contact, Contact.id == Agent.contact_id)
            .filter(
                Agent.tenant_id == tenant_id,
                Agent.provider_instance_id == instance_id,
            )
            .order_by(Contact.friendly_name)
            .all()
        )
        agents = [
            {
                "id": agent.id,
                "name": friendly_name or f"Agent {agent.id}",
                "model_provider": agent.model_provider,
                "model_name": agent.model_name,
                "is_active": bool(agent.is_active),
            }
            for agent, friendly_name in rows
        ]
        return {
            "instance_id": instance_id,
            "vendor": instance.vendor,
            "instance_name": instance.instance_name,
            "agents": agents,
            "dependent_count": len(agents),
        }

    @staticmethod
    def delete_instance_with_reassign(
        instance_id: int,
        tenant_id: str,
        db: Session,
        *,
        reassign_to_instance_id: Optional[int] = None,
        unassign: bool = False,
    ) -> dict:
        """Delete an instance after reassigning all dependent agents.

        Behavior:
        - If there are no dependents, soft-deletes (same as ``delete_instance``).
        - If ``reassign_to_instance_id`` is given, validates that target exists,
          is active, belongs to the same tenant. Vendor mismatch is allowed —
          the caller (UI) is in charge of confirming the model-name change.
        - If ``unassign=True``, sets ``provider_instance_id=None`` on dependents
          so they fall back to the tenant default for their current vendor.
        - If neither flag is provided AND there are dependents, raises
          ``ValueError("dependents_require_decision")``. The caller MUST surface
          this to the operator (no silent orphaning).

        Returns ``{instance_name, deleted, reassigned_count, reassigned_to}``.
        """
        from models import Agent

        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            raise ValueError("instance_not_found")

        dependents_q = db.query(Agent).filter(
            Agent.tenant_id == tenant_id,
            Agent.provider_instance_id == instance_id,
        )
        dependents = dependents_q.all()

        reassigned_to_instance: Optional[ProviderInstance] = None
        if dependents:
            if reassign_to_instance_id is not None:
                if reassign_to_instance_id == instance_id:
                    raise ValueError("reassign_target_is_self")
                target = ProviderInstanceService.get_instance(
                    reassign_to_instance_id, tenant_id, db
                )
                if not target or not target.is_active:
                    raise ValueError("reassign_target_invalid")
                reassigned_to_instance = target
            elif not unassign:
                raise ValueError("dependents_require_decision")

        # Apply reassignment.
        reassigned_count = 0
        if dependents:
            if reassigned_to_instance is not None:
                update_payload: dict = {
                    "provider_instance_id": reassigned_to_instance.id,
                    "model_provider": reassigned_to_instance.vendor,
                }
                # If the target vendor exposes preferred models, snap each
                # agent to the target's first model so the agent doesn't
                # try to use a model the target instance doesn't support.
                target_models = list(reassigned_to_instance.available_models or [])
                if target_models:
                    update_payload["model_name"] = target_models[0]
                reassigned_count = dependents_q.update(update_payload, synchronize_session=False)
            else:
                # Unassign — agent keeps current model_provider / model_name
                # and falls back to the tenant default instance for that vendor
                # (or to the legacy global path if none exists).
                reassigned_count = dependents_q.update(
                    {"provider_instance_id": None}, synchronize_session=False
                )

        instance.is_active = False
        from datetime import datetime as _dt
        instance.updated_at = _dt.utcnow()
        db.commit()

        return {
            "instance_name": instance.instance_name,
            "deleted": True,
            "reassigned_count": int(reassigned_count or 0),
            "reassigned_to": (
                {
                    "id": reassigned_to_instance.id,
                    "instance_name": reassigned_to_instance.instance_name,
                    "vendor": reassigned_to_instance.vendor,
                }
                if reassigned_to_instance is not None
                else None
            ),
            "unassigned": bool(dependents) and reassigned_to_instance is None,
        }

    @staticmethod
    def bootstrap_orphan_vendor_agents(db: Session) -> dict:
        """Boot-time hook: ensure every (tenant, vendor) pair that has agents
        but zero active provider instances gets one materialised.

        This kills the "ghost vendor" inconsistency where the agent worked at
        runtime via the legacy hardcoded fallback (Ollama base_url env var,
        host.docker.internal, etc.) but the Hub UI showed nothing. After this
        runs, the Hub catalogue and the agent runtime see the same instances.

        Today the supported auto-bootstrap is **Ollama only** — for the other
        vendors we don't have an API key and would have to invent one. Those
        agents stay orphan and the runtime returns a clear error pointing the
        operator at Hub instead of silently using the wrong key.

        Returns ``{tenants_processed, instances_created, agents_relinked}``.
        """
        from models import Agent

        rows = (
            db.query(Agent.tenant_id, Agent.model_provider)
            .filter(
                Agent.is_active == True,  # noqa: E712
                Agent.provider_instance_id.is_(None),
            )
            .distinct()
            .all()
        )

        tenants_processed: set[str] = set()
        instances_created = 0
        agents_relinked = 0

        for tenant_id, vendor in rows:
            if not tenant_id or not vendor:
                continue
            existing_active = (
                db.query(ProviderInstance)
                .filter(
                    ProviderInstance.tenant_id == tenant_id,
                    ProviderInstance.vendor == vendor,
                    ProviderInstance.is_active == True,  # noqa: E712
                )
                .first()
            )
            if existing_active:
                # Agent has no FK but an active instance exists — relink to
                # the default (or first active) so the Studio UI shows the
                # binding and the runtime doesn't fall through to the legacy
                # fallback.
                target = (
                    db.query(ProviderInstance)
                    .filter(
                        ProviderInstance.tenant_id == tenant_id,
                        ProviderInstance.vendor == vendor,
                        ProviderInstance.is_active == True,  # noqa: E712
                    )
                    .order_by(ProviderInstance.is_default.desc(), ProviderInstance.id)
                    .first()
                )
                if target:
                    relinked = (
                        db.query(Agent)
                        .filter(
                            Agent.tenant_id == tenant_id,
                            Agent.model_provider == vendor,
                            Agent.provider_instance_id.is_(None),
                            Agent.is_active == True,  # noqa: E712
                        )
                        .update(
                            {"provider_instance_id": target.id},
                            synchronize_session=False,
                        )
                    )
                    if relinked:
                        agents_relinked += int(relinked)
                        tenants_processed.add(tenant_id)
                continue

            # No active instance and we know how to materialise one.
            if vendor == "ollama":
                try:
                    new_inst = ProviderInstanceService.ensure_ollama_instance(
                        tenant_id, db
                    )
                    instances_created += 1
                    relinked = (
                        db.query(Agent)
                        .filter(
                            Agent.tenant_id == tenant_id,
                            Agent.model_provider == "ollama",
                            Agent.provider_instance_id.is_(None),
                            Agent.is_active == True,  # noqa: E712
                        )
                        .update(
                            {"provider_instance_id": new_inst.id},
                            synchronize_session=False,
                        )
                    )
                    agents_relinked += int(relinked or 0)
                    tenants_processed.add(tenant_id)
                    logger.info(
                        "bootstrap_orphan_vendor_agents: tenant=%s vendor=ollama "
                        "auto-created instance %s, relinked %s agent(s)",
                        tenant_id, new_inst.id, relinked,
                    )
                except Exception as exc:
                    logger.error(
                        "bootstrap_orphan_vendor_agents: failed to create Ollama "
                        "instance for tenant=%s: %s",
                        tenant_id, exc,
                    )
            else:
                # Other vendors require user-supplied credentials. Log a
                # one-line WARNING per (tenant, vendor) so the operator
                # notices and creates the instance via Hub.
                logger.warning(
                    "bootstrap_orphan_vendor_agents: tenant=%s has active agent(s) "
                    "for vendor=%s with no provider_instance_id and no active "
                    "instance — agent will fail at runtime until configured in Hub.",
                    tenant_id, vendor,
                )

        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

        return {
            "tenants_processed": len(tenants_processed),
            "instances_created": instances_created,
            "agents_relinked": agents_relinked,
        }

    @staticmethod
    def resolve_api_key(instance: ProviderInstance, db: Session) -> Optional[str]:
        """Decrypt instance key. Falls back to get_api_key() if no instance key."""
        if instance.api_key_encrypted:
            return ProviderInstanceService._decrypt_key(instance.api_key_encrypted, instance.tenant_id, db)
        # Fallback to legacy key resolution
        from services.api_key_service import get_api_key
        return get_api_key(instance.vendor, db, tenant_id=instance.tenant_id)

    @staticmethod
    def log_connection_audit(tenant_id: str, user_id: int, instance_id: int, action: str,
                             base_url: str, success: bool, db: Session,
                             resolved_ip: str = None, error_message: str = None):
        """Log a connection audit entry."""
        entry = ProviderConnectionAudit(
            tenant_id=tenant_id,
            user_id=user_id,
            provider_instance_id=instance_id,
            action=action,
            resolved_ip=resolved_ip,
            base_url=base_url,
            success=success,
            error_message=error_message,
        )
        db.add(entry)
        db.commit()

    @staticmethod
    def mask_api_key(encrypted_key: str, tenant_id: str, db: Session) -> str:
        """Return masked version of key for display: sk-...xyz"""
        if not encrypted_key:
            return ""
        try:
            decrypted = ProviderInstanceService._decrypt_key(encrypted_key, tenant_id, db)
            if len(decrypted) <= 8:
                return "***"
            return f"{decrypted[:3]}...{decrypted[-3:]}"
        except Exception:
            return "***"

    @staticmethod
    def _encrypt_key(api_key: str, tenant_id: str, db: Session) -> str:
        """
        Encrypt API key using Fernet with tenant-specific key derivation.
        Follows the same pattern as api_key_service._encrypt_api_key():
        1. Retrieve master encryption key via encryption_key_service
        2. Instantiate TokenEncryption with master key
        3. Derive workspace-specific key using identifier
        """
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for provider instance API key encryption")

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{tenant_id}"
        return encryptor.encrypt(api_key, identifier)

    @staticmethod
    def _decrypt_key(encrypted_key: str, tenant_id: str, db: Session) -> str:
        """
        Decrypt API key using Fernet with tenant-specific key derivation.
        Mirrors _encrypt_key: retrieves master key, derives workspace key, decrypts.
        """
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for provider instance API key decryption")

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{tenant_id}"
        return encryptor.decrypt(encrypted_key, identifier)
