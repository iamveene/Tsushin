"""
v0.6.0-patch.5: TTS Instance Service

CRUD + default-setting logic for per-tenant TTS instances (currently Kokoro only).
Mirrors VectorStoreInstanceService, adapted for the simpler TTS data model (no
external credentials to encrypt — Kokoro runs locally and is reached via
container DNS; Whisper/speaches vendors in v0.7.x may introduce credentials).
"""

import logging
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import TTSInstance, Config

logger = logging.getLogger(__name__)

SUPPORTED_VENDORS = {"kokoro"}
AUTO_PROVISIONABLE_VENDORS = {"kokoro"}


class TTSInstanceService:

    # ------------------------------------------------------------------ list/get

    @staticmethod
    def list_instances(
        tenant_id: str,
        db: Session,
        vendor: Optional[str] = None,
        active_only: bool = True,
    ) -> List[TTSInstance]:
        query = db.query(TTSInstance).filter(TTSInstance.tenant_id == tenant_id)
        if active_only:
            query = query.filter(TTSInstance.is_active == True)
        if vendor:
            query = query.filter(TTSInstance.vendor == vendor)
        return query.order_by(
            TTSInstance.vendor,
            TTSInstance.is_default.desc(),
            TTSInstance.instance_name,
        ).all()

    @staticmethod
    def get_instance(
        instance_id: int, tenant_id: str, db: Session
    ) -> Optional[TTSInstance]:
        return (
            db.query(TTSInstance)
            .filter(
                TTSInstance.id == instance_id,
                TTSInstance.tenant_id == tenant_id,
            )
            .first()
        )

    # ------------------------------------------------------------------ create

    @staticmethod
    def create_instance(
        tenant_id: str,
        vendor: str,
        instance_name: str,
        db: Session,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        is_default: bool = False,
        default_voice: Optional[str] = None,
        default_speed: Optional[float] = None,
        default_language: Optional[str] = None,
        default_format: Optional[str] = None,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
    ) -> TTSInstance:
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(
                f"Unsupported vendor: {vendor}. Must be one of: {sorted(SUPPORTED_VENDORS)}"
            )

        if is_default:
            db.query(TTSInstance).filter(
                TTSInstance.tenant_id == tenant_id,
                TTSInstance.is_default == True,
            ).update({"is_default": False})

        kwargs = dict(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            description=description,
            base_url=base_url,
            is_default=is_default,
        )
        if default_voice is not None:
            kwargs["default_voice"] = default_voice
        if default_speed is not None:
            kwargs["default_speed"] = default_speed
        if default_language is not None:
            kwargs["default_language"] = default_language
        if default_format is not None:
            kwargs["default_format"] = default_format
        if mem_limit is not None:
            kwargs["mem_limit"] = mem_limit
        if cpu_quota is not None:
            kwargs["cpu_quota"] = cpu_quota

        instance = TTSInstance(**kwargs)
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    # ------------------------------------------------------------------ provision

    @staticmethod
    def mark_pending_auto_provision(instance: TTSInstance, db: Session) -> TTSInstance:
        """BUG-651: mirror Ollama's pattern. Flip `is_auto_provisioned=True`
        and `container_status='provisioning'` synchronously so the immediate
        HTTP response reports the correct state — not the pre-provision
        defaults. Safe to call from the route before kicking off the
        background provisioning worker.
        """
        instance.is_auto_provisioned = True
        instance.container_status = "provisioning"
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def provision_instance(
        instance: TTSInstance,
        db: Session,
        *,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        fail_open_on_error: bool = False,
        warning_context: Optional[str] = None,
    ) -> Optional[str]:
        if instance.vendor not in AUTO_PROVISIONABLE_VENDORS:
            raise ValueError(
                f"Auto-provisioning not supported for vendor: {instance.vendor}"
            )

        if mem_limit is not None:
            instance.mem_limit = mem_limit
        if cpu_quota is not None:
            instance.cpu_quota = cpu_quota
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)

        from services.kokoro_container_manager import KokoroContainerManager

        try:
            KokoroContainerManager().provision(instance, db)
            db.refresh(instance)
            return None
        except Exception as e:
            logger.warning(
                "TTS auto-provisioning failed for tenant=%s instance=%s: %s",
                instance.tenant_id,
                instance.instance_name,
                e,
            )
            db.refresh(instance)
            if not fail_open_on_error:
                raise

            context = warning_context or f"TTS instance '{instance.instance_name}'"
            error_detail = getattr(instance, "health_status_reason", None) or str(e)
            return (
                f"{context} could not be auto-provisioned. "
                "You can retry from Hub > AI Providers > Kokoro TTS. "
                f"Error: {error_detail}"
            )

    @staticmethod
    def create_instance_with_optional_provisioning(
        tenant_id: str,
        vendor: str,
        instance_name: str,
        db: Session,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        is_default: bool = False,
        default_voice: Optional[str] = None,
        default_speed: Optional[float] = None,
        default_language: Optional[str] = None,
        default_format: Optional[str] = None,
        auto_provision: bool = False,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        fail_open_on_provision_error: bool = False,
        warning_context: Optional[str] = None,
    ) -> Tuple[TTSInstance, Optional[str]]:
        instance = TTSInstanceService.create_instance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            db=db,
            description=description,
            base_url=base_url,
            is_default=is_default,
            default_voice=default_voice,
            default_speed=default_speed,
            default_language=default_language,
            default_format=default_format,
            mem_limit=mem_limit,
            cpu_quota=cpu_quota,
        )

        # BUG-651: mirror Ollama's pattern — if the caller asked to auto-provision,
        # set `is_auto_provisioned=True` and surface a `provisioning` container
        # status BEFORE the provisioning RPC runs. The HTTP route returns
        # immediately after this call (or after kicking off a background worker),
        # so without this flip the initial response reports `is_auto_provisioned:
        # false` and only flips on the next poll.
        if auto_provision:
            instance.is_auto_provisioned = True
            instance.container_status = "provisioning"
            instance.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(instance)

        warning = None
        if auto_provision:
            warning = TTSInstanceService.provision_instance(
                instance,
                db,
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                fail_open_on_error=fail_open_on_provision_error,
                warning_context=warning_context,
            )
            db.refresh(instance)

        return instance, warning

    # ------------------------------------------------------------------ update

    @staticmethod
    def update_instance(
        instance_id: int, tenant_id: str, db: Session, **kwargs
    ) -> Optional[TTSInstance]:
        instance = TTSInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None

        if kwargs.get("is_default"):
            db.query(TTSInstance).filter(
                TTSInstance.tenant_id == tenant_id,
                TTSInstance.id != instance_id,
                TTSInstance.is_default == True,
            ).update({"is_default": False})

        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)

        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)
        return instance

    # ------------------------------------------------------------------ delete

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        """Soft-delete the instance. Container lifecycle is managed separately.

        If the deleted instance is the tenant's default (Config.default_tts_instance_id),
        clear that FK too.
        """
        instance = TTSInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False

        instance.is_active = False
        instance.is_default = False
        instance.updated_at = datetime.utcnow()

        # Clear Config.default_tts_instance_id if it points to this instance.
        # Config is a singleton (no tenant_id column) — only one row exists,
        # and the default_tts_instance_id FK is effectively global.
        cfg = db.query(Config).first()
        if cfg and cfg.default_tts_instance_id == instance_id:
            cfg.default_tts_instance_id = None

        db.commit()
        return True

    # ------------------------------------------------------------------ default

    @staticmethod
    def set_default(
        instance_id_or_none: Optional[int],
        tenant_id: str,
        db: Session,
    ) -> Optional[int]:
        """Atomically set the default TTS instance.

        NOTE: Config is a singleton (no tenant_id column). The
        default_tts_instance_id FK is therefore effectively global across the
        platform for v0.7.0. Tenant isolation is preserved on the INSTANCE
        side: callers can only point the default at a TTSInstance they own
        (validated below) and per-tenant TTSInstance.is_default flags are
        still scoped by tenant_id. Per-tenant Config defaults can be added
        later as a schema migration.

        Peer review fix A-H3 (adapted): lock the Config row with SELECT ...
        FOR UPDATE so a concurrent setter cannot race us on both the Config
        FK and the TTSInstance is_default flags. If we hit an IntegrityError
        (e.g. dangling FK on a concurrent delete), retry once.
        """
        for attempt in range(2):
            try:
                cfg = db.query(Config).first()
                if not cfg:
                    raise ValueError("Config row not found (singleton)")

                # Lock the single Config row by id to serialize concurrent
                # default-setters.
                db.execute(
                    text("SELECT id FROM config WHERE id = :id FOR UPDATE"),
                    {"id": cfg.id},
                )

                # Validate target instance (if not clearing) — tenant ownership
                # is enforced here so a tenant cannot point the global default
                # at another tenant's instance.
                if instance_id_or_none is not None:
                    instance = (
                        db.query(TTSInstance)
                        .filter(
                            TTSInstance.id == instance_id_or_none,
                            TTSInstance.tenant_id == tenant_id,
                            TTSInstance.is_active == True,
                        )
                        .first()
                    )
                    if not instance:
                        raise ValueError(
                            f"TTS instance {instance_id_or_none} not found for tenant"
                        )

                # Clear is_default on all rows for this tenant (per-tenant flag)
                db.query(TTSInstance).filter(
                    TTSInstance.tenant_id == tenant_id,
                ).update({"is_default": False})

                # Apply the new per-tenant default flag
                if instance_id_or_none is not None:
                    db.query(TTSInstance).filter(
                        TTSInstance.id == instance_id_or_none,
                        TTSInstance.tenant_id == tenant_id,
                    ).update({"is_default": True})

                cfg.default_tts_instance_id = instance_id_or_none
                cfg.updated_at = datetime.utcnow()

                db.commit()
                return instance_id_or_none

            except IntegrityError as e:
                db.rollback()
                if attempt == 0:
                    logger.warning(
                        f"set_default IntegrityError for tenant={tenant_id}, retrying: {e}"
                    )
                    continue
                logger.error(
                    f"set_default failed after retry for tenant={tenant_id}: {e}"
                )
                raise

        return instance_id_or_none

    @staticmethod
    def get_config_default(
        tenant_id: str, db: Session
    ) -> Tuple[Optional[int], Optional[TTSInstance]]:
        """Return (default_tts_instance_id, instance_or_none) from Config FK.

        Config is a singleton (no tenant_id column), so the FK is globally
        shared for v0.7.0. We still filter the resolved TTSInstance by
        tenant_id as defense-in-depth — a tenant that doesn't own the
        globally-configured default will see (id, None) and the resolver
        will fall back to the provider's own service URL.
        """
        cfg = db.query(Config).first()
        if not cfg or not cfg.default_tts_instance_id:
            return None, None

        instance = (
            db.query(TTSInstance)
            .filter(
                TTSInstance.id == cfg.default_tts_instance_id,
                TTSInstance.tenant_id == tenant_id,
                TTSInstance.is_active == True,
            )
            .first()
        )
        return cfg.default_tts_instance_id, instance
