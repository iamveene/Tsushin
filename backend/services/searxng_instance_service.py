"""
v0.6.0-patch.6: SearXNG Instance Service

Thin CRUD + provisioning wrapper around SearxngInstance. Mirrors
TTSInstanceService. Vendor is fixed to 'searxng'; no external credentials to
encrypt (unlike LLM provider instances) — the base_url is either a DNS alias
pointing at an auto-provisioned container on tsushin-network, or a user-
provided external URL (is_auto_provisioned=False).
"""

import logging
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy.orm import Session

from models import SearxngInstance

logger = logging.getLogger(__name__)

SUPPORTED_VENDORS = {"searxng"}
AUTO_PROVISIONABLE_VENDORS = {"searxng"}


class SearxngInstanceService:

    # ------------------------------------------------------------------ list/get

    @staticmethod
    def list_instances(
        tenant_id: str,
        db: Session,
        active_only: bool = True,
    ) -> List[SearxngInstance]:
        q = db.query(SearxngInstance).filter(SearxngInstance.tenant_id == tenant_id)
        if active_only:
            q = q.filter(SearxngInstance.is_active == True)
        return q.order_by(SearxngInstance.instance_name).all()

    @staticmethod
    def get_instance(
        instance_id: int, tenant_id: str, db: Session
    ) -> Optional[SearxngInstance]:
        return (
            db.query(SearxngInstance)
            .filter(
                SearxngInstance.id == instance_id,
                SearxngInstance.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def get_active_for_tenant(tenant_id: str, db: Session) -> Optional[SearxngInstance]:
        """Resolver helper — the one active SearxngInstance for this tenant,
        if any. Used by SearXNGSearchProvider at search time."""
        return (
            db.query(SearxngInstance)
            .filter(
                SearxngInstance.tenant_id == tenant_id,
                SearxngInstance.is_active == True,
            )
            .order_by(SearxngInstance.id.desc())
            .first()
        )

    # ------------------------------------------------------------------ create

    @staticmethod
    def create_instance(
        tenant_id: str,
        instance_name: str,
        db: Session,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
    ) -> SearxngInstance:
        kwargs = dict(
            tenant_id=tenant_id,
            vendor="searxng",
            instance_name=instance_name,
            description=description,
            base_url=base_url,
            extra_config={},
        )
        if mem_limit is not None:
            kwargs["mem_limit"] = mem_limit
        if cpu_quota is not None:
            kwargs["cpu_quota"] = cpu_quota

        instance = SearxngInstance(**kwargs)
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    # ------------------------------------------------------------------ provision

    @staticmethod
    def mark_pending_auto_provision(instance: SearxngInstance, db: Session) -> SearxngInstance:
        instance.is_auto_provisioned = True
        instance.container_status = "provisioning"
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def provision_instance(
        instance: SearxngInstance,
        db: Session,
        *,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        fail_open_on_error: bool = False,
        warning_context: Optional[str] = None,
    ) -> Optional[str]:
        if instance.vendor not in AUTO_PROVISIONABLE_VENDORS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {instance.vendor}")

        if mem_limit is not None:
            instance.mem_limit = mem_limit
        if cpu_quota is not None:
            instance.cpu_quota = cpu_quota
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)

        from services.searxng_container_manager import SearxngContainerManager

        try:
            SearxngContainerManager().provision(instance, db)
            db.refresh(instance)
            return None
        except Exception as e:
            logger.warning(
                "SearXNG auto-provisioning failed for tenant=%s instance=%s: %s",
                instance.tenant_id, instance.instance_name, e,
            )
            db.refresh(instance)
            if not fail_open_on_error:
                raise
            context = warning_context or f"SearXNG instance '{instance.instance_name}'"
            error_detail = getattr(instance, "health_status_reason", None) or str(e)
            return (
                f"{context} could not be auto-provisioned. "
                "You can retry from Hub > Tool APIs > SearXNG. "
                f"Error: {error_detail}"
            )

    @staticmethod
    def create_with_optional_provisioning(
        tenant_id: str,
        instance_name: str,
        db: Session,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        auto_provision: bool = True,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        fail_open_on_provision_error: bool = True,
        warning_context: Optional[str] = None,
    ) -> Tuple[SearxngInstance, Optional[str]]:
        instance = SearxngInstanceService.create_instance(
            tenant_id=tenant_id,
            instance_name=instance_name,
            db=db,
            description=description,
            base_url=base_url,
            mem_limit=mem_limit,
            cpu_quota=cpu_quota,
        )

        if auto_provision:
            SearxngInstanceService.mark_pending_auto_provision(instance, db)
            warning = SearxngInstanceService.provision_instance(
                instance, db,
                mem_limit=mem_limit, cpu_quota=cpu_quota,
                fail_open_on_error=fail_open_on_provision_error,
                warning_context=warning_context,
            )
            db.refresh(instance)
            return instance, warning

        return instance, None

    # ------------------------------------------------------------------ update / delete

    @staticmethod
    def update_instance(
        instance_id: int, tenant_id: str, db: Session, **kwargs
    ) -> Optional[SearxngInstance]:
        instance = SearxngInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        instance = SearxngInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False
        instance.is_active = False
        instance.updated_at = datetime.utcnow()
        db.commit()
        return True
