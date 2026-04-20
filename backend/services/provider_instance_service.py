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
