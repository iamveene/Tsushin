"""
Track D: Whisper ASR Instance Service

CRUD + provisioning helpers for per-tenant ASR instances backed by
OpenAI-compatible Whisper/Speaches endpoints.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional, List, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import ASRInstance
from models_rbac import Tenant
from services.encryption_key_service import get_api_key_encryption_key

logger = logging.getLogger(__name__)

SUPPORTED_VENDORS = {"speaches"}
AUTO_PROVISIONABLE_VENDORS = {"speaches"}
DEFAULT_AUTH_USERNAME = "tsushin"
DEFAULT_MODEL_ID = "Systran/faster-distil-whisper-small.en"


class WhisperInstanceService:
    @staticmethod
    def list_instances(
        tenant_id: str,
        db: Session,
        vendor: Optional[str] = None,
        active_only: bool = True,
    ) -> List[ASRInstance]:
        query = db.query(ASRInstance).filter(ASRInstance.tenant_id == tenant_id)
        if active_only:
            query = query.filter(ASRInstance.is_active == True)
        if vendor:
            query = query.filter(ASRInstance.vendor == vendor)
        return query.order_by(ASRInstance.vendor, ASRInstance.instance_name).all()

    @staticmethod
    def get_instance(instance_id: int, tenant_id: str, db: Session) -> Optional[ASRInstance]:
        return (
            db.query(ASRInstance)
            .filter(
                ASRInstance.id == instance_id,
                ASRInstance.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def create_instance(
        tenant_id: str,
        vendor: str,
        instance_name: str,
        db: Session,
        *,
        description: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
        auto_provision: bool = False,
    ) -> ASRInstance:
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(
                f"Unsupported vendor: {vendor}. Must be one of: {sorted(SUPPORTED_VENDORS)}"
            )

        api_token = secrets.token_urlsafe(32)
        instance = ASRInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            description=description,
            base_url=base_url,
            auth_username=DEFAULT_AUTH_USERNAME,
            api_token_encrypted=WhisperInstanceService._encrypt_token(api_token, tenant_id, db),
            default_model=(default_model or DEFAULT_MODEL_ID).strip(),
            mem_limit=mem_limit,
            cpu_quota=cpu_quota,
            is_auto_provisioned=bool(auto_provision),
            container_status="provisioning" if auto_provision else "none",
        )
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def mark_pending_auto_provision(instance: ASRInstance, db: Session) -> ASRInstance:
        instance.is_auto_provisioned = True
        instance.container_status = "provisioning"
        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def provision_instance(
        instance: ASRInstance,
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

        from services.whisper_container_manager import WhisperContainerManager

        try:
            WhisperContainerManager().provision(instance, db)
            db.refresh(instance)
            return None
        except Exception as e:
            logger.warning(
                "Whisper auto-provisioning failed for tenant=%s instance=%s: %s",
                instance.tenant_id,
                instance.instance_name,
                e,
            )
            db.refresh(instance)
            if not fail_open_on_error:
                raise

            context = warning_context or f"ASR instance '{instance.instance_name}'"
            error_detail = getattr(instance, "health_status_reason", None) or str(e)
            return (
                f"{context} could not be auto-provisioned. "
                "You can retry from Settings > ASR. "
                f"Error: {error_detail}"
            )

    @staticmethod
    def update_instance(
        instance_id: int,
        tenant_id: str,
        db: Session,
        **kwargs,
    ) -> Optional[ASRInstance]:
        instance = WhisperInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None

        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)
        instance.updated_at = datetime.utcnow()
        if instance.is_active is False:
            WhisperInstanceService._clear_tenant_default_if_matches(
                instance_id,
                tenant_id,
                db,
            )
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        instance = WhisperInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False
        instance.is_active = False
        instance.updated_at = datetime.utcnow()
        WhisperInstanceService._clear_tenant_default_if_matches(instance_id, tenant_id, db)
        db.commit()
        return True

    @staticmethod
    def set_tenant_default(
        instance_id_or_none: Optional[int],
        tenant_id: str,
        db: Session,
    ) -> Optional[int]:
        """Atomically set the tenant's default ASR instance.

        ``None`` means "use OpenAI Whisper by default". A concrete instance id
        must belong to the calling tenant and remain active.
        """
        for attempt in range(2):
            try:
                tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
                if not tenant:
                    raise ValueError(f"Tenant {tenant_id} not found")

                db.execute(
                    text("SELECT id FROM tenant WHERE id = :id FOR UPDATE"),
                    {"id": tenant_id},
                )

                if instance_id_or_none is not None:
                    instance = (
                        db.query(ASRInstance)
                        .filter(
                            ASRInstance.id == instance_id_or_none,
                            ASRInstance.tenant_id == tenant_id,
                            ASRInstance.is_active == True,
                        )
                        .first()
                    )
                    if not instance:
                        raise ValueError(
                            f"ASR instance {instance_id_or_none} not found for tenant"
                        )

                tenant.default_asr_instance_id = instance_id_or_none
                tenant.updated_at = datetime.utcnow()
                db.commit()
                return instance_id_or_none

            except IntegrityError as e:
                db.rollback()
                if attempt == 0:
                    logger.warning(
                        "set_tenant_default IntegrityError for tenant=%s, retrying: %s",
                        tenant_id,
                        e,
                    )
                    continue
                logger.error(
                    "set_tenant_default failed after retry for tenant=%s: %s",
                    tenant_id,
                    e,
                )
                raise

        return instance_id_or_none

    @staticmethod
    def get_tenant_default(
        tenant_id: str, db: Session
    ) -> Tuple[Optional[int], Optional[ASRInstance]]:
        """Return the tenant default ASR instance, if one is configured."""
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant or not tenant.default_asr_instance_id:
            return None, None

        instance = (
            db.query(ASRInstance)
            .filter(
                ASRInstance.id == tenant.default_asr_instance_id,
                ASRInstance.tenant_id == tenant_id,
                ASRInstance.is_active == True,
            )
            .first()
        )
        if not instance:
            stale_id = tenant.default_asr_instance_id
            tenant.default_asr_instance_id = None
            tenant.updated_at = datetime.utcnow()
            db.commit()
            logger.info(
                "Cleared stale default ASR instance tenant=%s instance=%s",
                tenant_id,
                stale_id,
            )
            return None, None
        return tenant.default_asr_instance_id, instance

    @staticmethod
    def _clear_tenant_default_if_matches(
        instance_id: int,
        tenant_id: str,
        db: Session,
    ) -> None:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if tenant and tenant.default_asr_instance_id == instance_id:
            tenant.default_asr_instance_id = None
            tenant.updated_at = datetime.utcnow()

    @staticmethod
    def resolve_api_token(instance: ASRInstance, db: Session) -> Optional[str]:
        if not instance.api_token_encrypted:
            return None
        return WhisperInstanceService._decrypt_token(
            instance.api_token_encrypted,
            instance.tenant_id,
            db,
        )

    @staticmethod
    def _encrypt_token(token: str, tenant_id: str, db: Session) -> str:
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for ASR token encryption")
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"asr_instance_token_{tenant_id}"
        return encryptor.encrypt(token, identifier)

    @staticmethod
    def _decrypt_token(encrypted_token: str, tenant_id: str, db: Session) -> str:
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for ASR token decryption")
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"asr_instance_token_{tenant_id}"
        return encryptor.decrypt(encrypted_token, identifier)
