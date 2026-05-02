"""
Track D: Whisper ASR Instance Service

CRUD + provisioning helpers for per-tenant ASR instances backed by
OpenAI-compatible Whisper/Speaches endpoints.
"""

import logging
import secrets
from datetime import datetime
from typing import Optional, List

from sqlalchemy.orm import Session

from hub.security import TokenEncryption
from models import ASRInstance
from services.encryption_key_service import get_api_key_encryption_key

logger = logging.getLogger(__name__)

SUPPORTED_VENDORS = {"speaches", "openai_whisper"}
AUTO_PROVISIONABLE_VENDORS = {"speaches", "openai_whisper"}
DEFAULT_AUTH_USERNAME = "tsushin"
DEFAULT_MODEL_ID = "Systran/faster-distil-whisper-small.en"
# openai/whisper engine takes plain model size names (tiny/base/small/medium/large-v3/turbo).
# The webservice loads the model once at boot and keeps it warm; "base" is
# the safe default for ~1 GB RAM, ~1.5x realtime CPU on a 4-core x86.
DEFAULT_OPENAI_WHISPER_MODEL = "base"


def default_model_for_vendor(vendor: str) -> str:
    if vendor == "openai_whisper":
        return DEFAULT_OPENAI_WHISPER_MODEL
    return DEFAULT_MODEL_ID


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
        resolved_default_model = (
            default_model.strip() if default_model and default_model.strip() else default_model_for_vendor(vendor)
        )
        instance = ASRInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            description=description,
            base_url=base_url,
            auth_username=DEFAULT_AUTH_USERNAME,
            api_token_encrypted=WhisperInstanceService._encrypt_token(api_token, tenant_id, db),
            default_model=resolved_default_model,
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
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> Optional[dict]:
        """Soft-delete the instance and reconcile pinned agent skills.

        Returns ``None`` if the instance was not found, otherwise the cascade
        summary dict (``reassigned``, ``disabled``, ``successor_instance_id``)
        so the API can surface what happened to dependent agents.
        """
        instance = WhisperInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None
        instance.is_active = False
        instance.updated_at = datetime.utcnow()
        cascade = WhisperInstanceService.cascade_agent_skill_pins(instance_id, tenant_id, db)
        db.commit()
        return cascade

    @staticmethod
    def cascade_agent_skill_pins(
        deleted_instance_id: int,
        tenant_id: str,
        db: Session,
    ) -> dict:
        """When an ASR instance is deleted, every agent_skill row that pinned
        it must be reconciled. Strategy:

        1. If the tenant still has another active ASR instance, repoint every
           pinned skill at that instance (lowest-id wins for determinism).
        2. If no other instance exists, disable each pinned audio_transcript
           skill (``is_enabled=false``). The user wants explicit silence rather
           than a silent fallback to cloud OpenAI Whisper, since the original
           pin was a deliberate privacy/cost choice.

        Returns a summary dict so the API layer can surface what happened.
        """
        from models import Agent, AgentSkill

        affected = (
            db.query(AgentSkill)
            .join(Agent, Agent.id == AgentSkill.agent_id)
            .filter(
                Agent.tenant_id == tenant_id,
                AgentSkill.skill_type == "audio_transcript",
                AgentSkill.is_enabled == True,
            )
            .all()
        )
        # Filter to skills actually pinned to the deleted instance.
        pinned = [
            s for s in affected
            if isinstance(s.config, dict)
            and (s.config or {}).get("asr_mode") == "instance"
            and (s.config or {}).get("asr_instance_id") == deleted_instance_id
        ]
        if not pinned:
            return {"reassigned": 0, "disabled": 0, "successor_instance_id": None}

        successor = (
            db.query(ASRInstance)
            .filter(
                ASRInstance.tenant_id == tenant_id,
                ASRInstance.id != deleted_instance_id,
                ASRInstance.is_active == True,
            )
            .order_by(ASRInstance.id.asc())
            .first()
        )

        reassigned = 0
        disabled = 0
        for skill in pinned:
            cfg = dict(skill.config or {})
            if successor is not None:
                cfg["asr_instance_id"] = successor.id
                skill.config = cfg
                reassigned += 1
            else:
                # No successor — disable the skill so the agent stops trying
                # to transcribe via a now-deleted endpoint. The user can
                # re-enable + repin once they create a new ASR instance.
                cfg["asr_instance_id"] = None
                cfg["asr_mode"] = "openai"
                skill.config = cfg
                skill.is_enabled = False
                disabled += 1
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(skill, "config")
            skill.updated_at = datetime.utcnow()

        logger.info(
            "ASR instance %s deletion cascade: reassigned=%d disabled=%d "
            "successor_instance_id=%s",
            deleted_instance_id,
            reassigned,
            disabled,
            successor.id if successor else None,
        )
        return {
            "reassigned": reassigned,
            "disabled": disabled,
            "successor_instance_id": successor.id if successor else None,
        }

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
