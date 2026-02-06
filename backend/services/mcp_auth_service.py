"""
MCP API Authentication Service
Phase Security-1: SSRF & Cross-Tenant Prevention

Provides:
- Secret generation and management for MCP instances
- Authentication header generation for API consumers
- Secret rotation support

Usage:
    from services.mcp_auth_service import generate_mcp_secret, get_auth_headers

    # Generate secret for new instance
    secret = generate_mcp_secret()

    # Get headers for API calls
    headers = get_auth_headers(instance.api_secret)
"""

import secrets
import logging
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def generate_mcp_secret() -> str:
    """
    Generate a cryptographically secure 32-byte hex-encoded secret.

    Returns:
        64-character hex string (32 bytes)

    Example:
        >>> secret = generate_mcp_secret()
        >>> len(secret)
        64
    """
    return secrets.token_hex(32)


def get_auth_headers(api_secret: Optional[str]) -> Dict[str, str]:
    """
    Generate authentication headers for MCP API requests.

    Args:
        api_secret: The API secret for the MCP instance (can be None for backward compat)

    Returns:
        Dict with Authorization header, or empty dict if no secret

    Example:
        >>> headers = get_auth_headers("abc123...")
        >>> headers
        {'Authorization': 'Bearer abc123...'}
    """
    if not api_secret:
        return {}
    return {"Authorization": f"Bearer {api_secret}"}


def rotate_instance_secret(db: Session, instance_id: int) -> str:
    """
    Rotate the API secret for an MCP instance.

    Note: This only updates the database. The container must be restarted
    to pick up the new secret via environment variable.

    Args:
        db: Database session
        instance_id: ID of the WhatsAppMCPInstance

    Returns:
        The new secret

    Raises:
        ValueError: If instance not found
    """
    from models import WhatsAppMCPInstance

    instance = db.query(WhatsAppMCPInstance).filter(
        WhatsAppMCPInstance.id == instance_id
    ).first()

    if not instance:
        raise ValueError(f"MCP instance {instance_id} not found")

    old_secret = instance.api_secret
    new_secret = generate_mcp_secret()

    instance.api_secret = new_secret
    instance.api_secret_created_at = datetime.utcnow()
    db.commit()

    logger.info(
        f"Rotated API secret for MCP instance {instance_id} "
        f"(container: {instance.container_name})"
    )

    return new_secret


def ensure_instance_has_secret(db: Session, instance_id: int) -> str:
    """
    Ensure an MCP instance has an API secret, generating one if needed.

    Args:
        db: Database session
        instance_id: ID of the WhatsAppMCPInstance

    Returns:
        The instance's API secret (existing or newly generated)

    Raises:
        ValueError: If instance not found
    """
    from models import WhatsAppMCPInstance

    instance = db.query(WhatsAppMCPInstance).filter(
        WhatsAppMCPInstance.id == instance_id
    ).first()

    if not instance:
        raise ValueError(f"MCP instance {instance_id} not found")

    if instance.api_secret:
        return instance.api_secret

    # Generate new secret
    new_secret = generate_mcp_secret()
    instance.api_secret = new_secret
    instance.api_secret_created_at = datetime.utcnow()
    db.commit()

    logger.info(
        f"Generated API secret for MCP instance {instance_id} "
        f"(container: {instance.container_name})"
    )

    return new_secret


def get_instance_secret(db: Session, instance_id: int) -> Optional[str]:
    """
    Get the API secret for an MCP instance.

    Args:
        db: Database session
        instance_id: ID of the WhatsAppMCPInstance

    Returns:
        The API secret, or None if not set
    """
    from models import WhatsAppMCPInstance

    instance = db.query(WhatsAppMCPInstance).filter(
        WhatsAppMCPInstance.id == instance_id
    ).first()

    if not instance:
        return None

    return instance.api_secret
