"""
v0.6.0: Vector Store Instance Service

CRUD operations, credential encryption, SSRF validation, and health checking
for external vector store connections (MongoDB Atlas, Pinecone, Qdrant).

Follows ProviderInstanceService pattern: Fernet encryption, tenant isolation,
single-default enforcement, soft-delete with FK cleanup.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict
from sqlalchemy.orm import Session
from models import VectorStoreInstance, Agent

logger = logging.getLogger(__name__)

SUPPORTED_VENDORS = {"mongodb", "pinecone", "qdrant"}


class VectorStoreInstanceService:

    @staticmethod
    def list_instances(
        tenant_id: str, db: Session, vendor: str = None, active_only: bool = True
    ) -> List[VectorStoreInstance]:
        query = db.query(VectorStoreInstance).filter(
            VectorStoreInstance.tenant_id == tenant_id
        )
        if active_only:
            query = query.filter(VectorStoreInstance.is_active == True)
        if vendor:
            query = query.filter(VectorStoreInstance.vendor == vendor)
        return query.order_by(
            VectorStoreInstance.vendor,
            VectorStoreInstance.is_default.desc(),
            VectorStoreInstance.instance_name,
        ).all()

    @staticmethod
    def get_instance(
        instance_id: int, tenant_id: str, db: Session
    ) -> Optional[VectorStoreInstance]:
        return (
            db.query(VectorStoreInstance)
            .filter(
                VectorStoreInstance.id == instance_id,
                VectorStoreInstance.tenant_id == tenant_id,
            )
            .first()
        )

    @staticmethod
    def get_default_instance(
        tenant_id: str, db: Session
    ) -> Optional[VectorStoreInstance]:
        return (
            db.query(VectorStoreInstance)
            .filter(
                VectorStoreInstance.tenant_id == tenant_id,
                VectorStoreInstance.is_default == True,
                VectorStoreInstance.is_active == True,
            )
            .first()
        )

    @staticmethod
    def create_instance(
        tenant_id: str,
        vendor: str,
        instance_name: str,
        db: Session,
        description: str = None,
        base_url: str = None,
        credentials: Dict = None,
        extra_config: Dict = None,
        security_config: Dict = None,
        is_default: bool = False,
    ) -> VectorStoreInstance:
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(f"Unsupported vendor: {vendor}. Must be one of: {SUPPORTED_VENDORS}")

        # SSRF validate base_url (skip for mongodb+srv:// which uses a non-HTTP scheme)
        if base_url:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            if parsed.scheme in ("http", "https"):
                from utils.ssrf_validator import validate_url, SSRFValidationError
                try:
                    # Allow private IPs for self-hosted Qdrant
                    validate_url(base_url, allow_private=(vendor == "qdrant"))
                except SSRFValidationError as e:
                    raise ValueError(f"URL validation failed: {e}")
            elif parsed.scheme not in ("mongodb", "mongodb+srv"):
                raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        # Encrypt credentials
        credentials_encrypted = None
        if credentials:
            credentials_encrypted = VectorStoreInstanceService._encrypt_credentials(
                credentials, tenant_id, db
            )

        # Enforce single default per tenant
        if is_default:
            db.query(VectorStoreInstance).filter(
                VectorStoreInstance.tenant_id == tenant_id,
                VectorStoreInstance.is_default == True,
            ).update({"is_default": False})

        instance = VectorStoreInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            description=description,
            base_url=base_url,
            credentials_encrypted=credentials_encrypted,
            extra_config=extra_config or {},
            security_config=security_config or {},
            is_default=is_default,
        )
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def update_instance(
        instance_id: int, tenant_id: str, db: Session, **kwargs
    ) -> Optional[VectorStoreInstance]:
        instance = VectorStoreInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None

        # SSRF validate new base_url
        if "base_url" in kwargs and kwargs["base_url"]:
            from urllib.parse import urlparse
            parsed = urlparse(kwargs["base_url"])
            if parsed.scheme in ("http", "https"):
                from utils.ssrf_validator import validate_url, SSRFValidationError
                try:
                    validate_url(kwargs["base_url"], allow_private=(instance.vendor == "qdrant"))
                except SSRFValidationError as e:
                    raise ValueError(f"URL validation failed: {e}")
            elif parsed.scheme not in ("mongodb", "mongodb+srv"):
                raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

        # Handle credentials update
        if "credentials" in kwargs:
            creds = kwargs.pop("credentials")
            if creds:
                instance.credentials_encrypted = (
                    VectorStoreInstanceService._encrypt_credentials(creds, tenant_id, db)
                )

        # Enforce single default
        if kwargs.get("is_default"):
            db.query(VectorStoreInstance).filter(
                VectorStoreInstance.tenant_id == tenant_id,
                VectorStoreInstance.id != instance_id,
                VectorStoreInstance.is_default == True,
            ).update({"is_default": False})

        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)

        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)

        # Evict from registry cache so next access uses updated credentials
        try:
            from agent.memory.providers.registry import VectorStoreRegistry
            VectorStoreRegistry().evict(instance_id)
        except Exception:
            pass

        return instance

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        instance = VectorStoreInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False

        # Clear FK on affected agents (tenant-scoped to prevent cross-tenant mutation)
        db.query(Agent).filter(
            Agent.vector_store_instance_id == instance_id,
            Agent.tenant_id == tenant_id,
        ).update({"vector_store_instance_id": None})

        instance.is_active = False
        instance.updated_at = datetime.utcnow()
        db.commit()

        # Evict from registry
        try:
            from agent.memory.providers.registry import VectorStoreRegistry
            VectorStoreRegistry().evict(instance_id)
        except Exception:
            pass

        return True

    @staticmethod
    def resolve_credentials(instance: VectorStoreInstance, db: Session) -> Dict:
        if not instance.credentials_encrypted:
            return {}
        return VectorStoreInstanceService._decrypt_credentials(
            instance.credentials_encrypted, instance.tenant_id, db
        )

    @staticmethod
    async def test_connection(
        instance_id: int, tenant_id: str, db: Session
    ) -> Dict:
        instance = VectorStoreInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return {"success": False, "message": "Instance not found"}

        try:
            from agent.memory.providers.registry import VectorStoreRegistry
            registry = VectorStoreRegistry()
            # Evict to force fresh connection with latest credentials
            registry.evict(instance_id)
            provider = registry.get_provider(instance_id, db, tenant_id=tenant_id)
            result = await provider.health_check()

            # Update health status
            instance.health_status = "healthy" if result.healthy else "unavailable"
            instance.health_status_reason = result.message
            instance.last_health_check = datetime.utcnow()
            db.commit()

            return {
                "success": result.healthy,
                "message": result.message,
                "latency_ms": result.latency_ms,
                "vector_count": result.vector_count,
            }
        except Exception as e:
            logger.error(f"Vector store connection test failed for instance {instance_id}: {e}")
            instance.health_status = "unavailable"
            instance.health_status_reason = str(e)[:500]  # Stored for admin diagnostics
            instance.last_health_check = datetime.utcnow()
            db.commit()
            return {"success": False, "message": "Connection test failed. Check credentials and endpoint configuration."}

    @staticmethod
    async def get_stats(
        instance_id: int, tenant_id: str, db: Session
    ) -> Dict:
        instance = VectorStoreInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return {"error": "Instance not found"}

        try:
            from agent.memory.providers.registry import VectorStoreRegistry
            provider = VectorStoreRegistry().get_provider(instance_id, db, tenant_id=tenant_id)
            return await provider.get_stats()
        except Exception as e:
            logger.error(f"Vector store stats failed for instance {instance_id}: {e}")
            return {"error": "Failed to retrieve stats"}

    @staticmethod
    def mask_credentials(instance: VectorStoreInstance, db: Session) -> str:
        """Return masked credentials preview."""
        if not instance.credentials_encrypted:
            return ""
        try:
            creds = VectorStoreInstanceService._decrypt_credentials(
                instance.credentials_encrypted, instance.tenant_id, db
            )
            # Mask the first credential value found
            for key in ("api_key", "connection_string", "password"):
                if key in creds and creds[key]:
                    val = creds[key]
                    if len(val) > 8:
                        return f"{val[:4]}...{val[-4:]}"
                    return "****"
            return "configured"
        except Exception:
            return "encrypted"

    @staticmethod
    def _encrypt_credentials(credentials: Dict, tenant_id: str, db: Session) -> str:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for vector store credential encryption")
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"vector_store_{tenant_id}"
        return encryptor.encrypt(json.dumps(credentials), identifier)

    @staticmethod
    def _decrypt_credentials(encrypted: str, tenant_id: str, db: Session) -> Dict:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for vector store credential decryption")
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"vector_store_{tenant_id}"
        return json.loads(encryptor.decrypt(encrypted, identifier))
