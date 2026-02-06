"""
Phase 10.1.1: Telegram Bot Service

Manages Telegram bot instances (creation, validation, health checks).
Unlike WhatsApp MCP, no Docker containers are needed - direct API calls only.
"""

import logging
import os
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from models import TelegramBotInstance
from hub.security import TokenEncryption

logger = logging.getLogger(__name__)


class TelegramBotService:
    """
    Service for managing Telegram bot instances.

    Responsibilities:
    - Bot token validation
    - Instance creation and deletion
    - Health checking
    - Token encryption/decryption
    """

    def __init__(self, db: Session):
        self.db = db
        self.logger = logging.getLogger(__name__)

        # Get Telegram-specific encryption key from database (MED-001 security fix)
        from services.encryption_key_service import get_telegram_encryption_key
        encryption_key = get_telegram_encryption_key(db)
        if not encryption_key:
            # Fallback to TELEGRAM_ENCRYPTION_KEY env var
            encryption_key = os.getenv("TELEGRAM_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError(
                "TELEGRAM_ENCRYPTION_KEY not configured in database or environment. "
                "Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        self.encryption = TokenEncryption(encryption_key.encode())

    async def create_instance(
        self,
        tenant_id: str,
        bot_token: str,
        created_by: int
    ) -> TelegramBotInstance:
        """
        Create and validate new Telegram bot instance.

        Args:
            tenant_id: Tenant ID
            bot_token: Bot token from @BotFather
            created_by: User ID creating the instance

        Returns:
            Created TelegramBotInstance

        Raises:
            ValueError: If token is invalid or bot already exists
        """
        # Validate token format
        if not bot_token or ":" not in bot_token:
            raise ValueError("Invalid bot token format. Expected format: '123456789:ABCdef...'")

        # Validate token with Telegram API
        try:
            # Import here to avoid circular imports during startup
            from telegram_integration.client import TelegramClient

            client = TelegramClient(bot_token)
            bot_info = await client.get_me()

            bot_username = bot_info["username"]
            bot_name = bot_info.get("first_name", bot_username)
            bot_id = str(bot_info["id"])

            self.logger.info(f"Validated Telegram bot: @{bot_username} (ID: {bot_id})")

        except Exception as e:
            self.logger.error(f"Failed to validate Telegram bot token: {e}")
            raise ValueError(f"Invalid bot token or Telegram API error: {str(e)}")

        # Check if bot already exists for this tenant
        existing = self.db.query(TelegramBotInstance).filter(
            TelegramBotInstance.tenant_id == tenant_id,
            TelegramBotInstance.bot_username == bot_username
        ).first()

        if existing:
            raise ValueError(f"Telegram bot @{bot_username} already exists for this tenant")

        # Encrypt token
        encrypted_token = self.encryption.encrypt(bot_token, tenant_id)

        # Create instance
        instance = TelegramBotInstance(
            tenant_id=tenant_id,
            bot_token_encrypted=encrypted_token,
            bot_username=bot_username,
            bot_name=bot_name,
            bot_id=bot_id,
            status="inactive",
            health_status="unknown",
            created_by=created_by
        )

        self.db.add(instance)
        self.db.commit()
        self.db.refresh(instance)

        self.logger.info(f"Created Telegram bot instance {instance.id} for tenant {tenant_id}")
        return instance

    async def start_instance(self, instance_id: int):
        """
        Mark instance as active.

        Args:
            instance_id: Instance ID
        """
        instance = self.db.query(TelegramBotInstance).get(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        instance.status = "active"
        instance.error_message = None
        self.db.commit()

        self.logger.info(f"Started Telegram bot instance {instance_id}")

    async def stop_instance(self, instance_id: int):
        """
        Mark instance as inactive.

        Args:
            instance_id: Instance ID
        """
        instance = self.db.query(TelegramBotInstance).get(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        instance.status = "inactive"
        self.db.commit()

        self.logger.info(f"Stopped Telegram bot instance {instance_id}")

    def delete_instance(self, instance_id: int):
        """
        Delete Telegram bot instance.

        Args:
            instance_id: Instance ID
        """
        instance = self.db.query(TelegramBotInstance).get(instance_id)
        if not instance:
            raise ValueError(f"Instance {instance_id} not found")

        tenant_id = instance.tenant_id
        bot_username = instance.bot_username

        self.db.delete(instance)
        self.db.commit()

        self.logger.info(f"Deleted Telegram bot instance {instance_id} (@{bot_username}) for tenant {tenant_id}")

    async def health_check(self, instance: TelegramBotInstance) -> Dict[str, Any]:
        """
        Check Telegram bot health.

        Args:
            instance: TelegramBotInstance

        Returns:
            Health status dictionary
        """
        try:
            # Decrypt token
            token = self._decrypt_token(instance.bot_token_encrypted, instance.tenant_id)

            # Import here to avoid circular imports during startup
            from telegram_integration.client import TelegramClient

            # Check bot status
            client = TelegramClient(token)
            bot_info = await client.get_me()

            # Update health status
            instance.health_status = "healthy"
            instance.last_health_check = datetime.utcnow()
            instance.error_message = None
            self.db.commit()

            return {
                "status": "healthy",
                "bot_username": bot_info["username"],
                "api_reachable": True,
                "error": None
            }

        except Exception as e:
            self.logger.error(f"Health check failed for instance {instance.id}: {e}")

            # Update health status
            instance.health_status = "unhealthy"
            instance.last_health_check = datetime.utcnow()
            instance.error_message = str(e)
            self.db.commit()

            return {
                "status": "unhealthy",
                "bot_username": instance.bot_username,
                "api_reachable": False,
                "error": str(e)
            }

    def _decrypt_token(self, encrypted_token: str, tenant_id: Optional[str] = None) -> str:
        """
        Decrypt bot token.

        Args:
            encrypted_token: Encrypted token
            tenant_id: Tenant ID (if None, will try to infer)

        Returns:
            Decrypted token
        """
        if not tenant_id:
            # If tenant_id not provided, we can't decrypt
            raise ValueError("Tenant ID required for token decryption")

        return self.encryption.decrypt(encrypted_token, tenant_id)

    # =========================================================================
    # MED-002 Security Fix: Webhook Secret Encryption
    # =========================================================================

    def encrypt_webhook_secret(self, webhook_secret: str, tenant_id: str) -> str:
        """
        Encrypt webhook secret using tenant-specific key derivation.

        Args:
            webhook_secret: Plaintext webhook secret
            tenant_id: Tenant ID for key derivation

        Returns:
            Encrypted webhook secret (Fernet format)
        """
        if not webhook_secret:
            raise ValueError("Webhook secret cannot be empty")
        if not tenant_id:
            raise ValueError("Tenant ID required for encryption")

        return self.encryption.encrypt(webhook_secret, tenant_id)

    def decrypt_webhook_secret(self, encrypted_secret: str, tenant_id: str) -> str:
        """
        Decrypt webhook secret.

        Args:
            encrypted_secret: Encrypted webhook secret
            tenant_id: Tenant ID for key derivation

        Returns:
            Decrypted webhook secret
        """
        if not encrypted_secret:
            raise ValueError("Encrypted secret cannot be empty")
        if not tenant_id:
            raise ValueError("Tenant ID required for decryption")

        return self.encryption.decrypt(encrypted_secret, tenant_id)

    def set_webhook_secret(self, instance: TelegramBotInstance, webhook_secret: str) -> None:
        """
        Set encrypted webhook secret for a Telegram bot instance.

        Args:
            instance: TelegramBotInstance to update
            webhook_secret: Plaintext webhook secret to encrypt and store
        """
        encrypted = self.encrypt_webhook_secret(webhook_secret, instance.tenant_id)
        instance.webhook_secret_encrypted = encrypted
        self.db.commit()
        self.logger.info(f"Set webhook secret for Telegram bot instance {instance.id}")

    def get_webhook_secret(self, instance: TelegramBotInstance) -> Optional[str]:
        """
        Get decrypted webhook secret for a Telegram bot instance.

        Args:
            instance: TelegramBotInstance to get secret from

        Returns:
            Decrypted webhook secret, or None if not set
        """
        if not instance.webhook_secret_encrypted:
            return None

        return self.decrypt_webhook_secret(
            instance.webhook_secret_encrypted,
            instance.tenant_id
        )
