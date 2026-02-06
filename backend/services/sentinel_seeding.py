"""
Sentinel Security Agent Seeding Service - Phase 20

Seeds default Sentinel configuration for fresh installs.
Called from db.py init_database() - runs on every startup,
but only creates config if none exists (idempotent).

This ensures that:
1. Fresh installs have Sentinel enabled by default
2. Sentinel cannot be deleted (only disabled)
3. Default settings are sensible and security-focused
4. Fresh installs use detect_only mode (safe default - logs threats without blocking)

Phase 20 Enhancement:
5. Migrate existing DBs to add detection_mode and exception support
6. Seed default exceptions for common testing scenarios

Note: Existing databases migrating keep detection_mode='block' to preserve behavior.
Fresh installs get detection_mode='detect_only' for safer initial deployment.
"""

import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)


def seed_sentinel_config(db: Session) -> Optional["SentinelConfig"]:
    """
    Seed default Sentinel configuration for fresh installs.

    Creates a system-wide config (tenant_id=NULL) with sensible defaults.
    This is the base configuration that all tenants inherit from.

    Idempotent: skips if config already exists.

    Args:
        db: Database session

    Returns:
        The created or existing SentinelConfig, or None on error
    """
    from models import SentinelConfig

    try:
        # Check if system config already exists
        existing = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

        if existing:
            logger.debug("Sentinel system config already exists, skipping seeding")
            return existing

        logger.info("Seeding default Sentinel configuration...")

        # Create default system config
        config = SentinelConfig(
            tenant_id=None,  # System-wide default

            # Master toggle - enabled by default for security
            is_enabled=True,

            # Component toggles - all enabled by default
            enable_prompt_analysis=True,
            enable_tool_analysis=True,
            enable_shell_analysis=True,

            # Detection types - all enabled by default
            detect_prompt_injection=True,
            detect_agent_takeover=True,
            detect_poisoning=True,
            detect_shell_malicious_intent=True,

            # Moderate aggressiveness (1) - balanced false positive/detection rate
            # 0=Off, 1=Moderate, 2=Aggressive, 3=Extra Aggressive
            aggressiveness_level=1,

            # LLM config - use fast/cheap model for low latency
            # Using gemini-2.5-flash-lite as gemini-2.0-flash-lite is deprecated
            llm_provider="gemini",
            llm_model="gemini-2.5-flash-lite",
            llm_max_tokens=256,
            llm_temperature=0.1,  # Low temperature for consistent analysis

            # No custom prompts - use defaults from sentinel_detections.py
            prompt_injection_prompt=None,
            agent_takeover_prompt=None,
            poisoning_prompt=None,
            shell_intent_prompt=None,

            # Performance settings
            cache_ttl_seconds=300,  # 5-minute cache
            max_input_chars=5000,   # Truncate long inputs
            timeout_seconds=5.0,    # LLM call timeout

            # Action settings
            block_on_detection=True,  # When detection_mode='block', this controls blocking
            log_all_analyses=False,  # Only log threats to reduce storage

            # Detection mode - detect_only by default for fresh installs
            # This allows admins to see what Sentinel would block before enabling blocking
            detection_mode="detect_only",

            # Notification settings - notify on blocked threats by default
            enable_notifications=True,
            notification_on_block=True,
            notification_on_detect=False,  # Don't notify in detect_only mode by default
            notification_recipient=None,  # Must be configured by admin
            notification_message_template=None,  # Use default template
        )

        db.add(config)
        db.commit()

        logger.info("Sentinel default configuration seeded successfully")
        return config

    except Exception as e:
        logger.error(f"Failed to seed Sentinel config: {e}", exc_info=True)
        db.rollback()
        return None


def get_sentinel_seeding_stats(db: Session) -> dict:
    """
    Get statistics about Sentinel seeding status.

    Returns:
        Dict with seeding status information
    """
    from models import SentinelConfig

    try:
        system_config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

        tenant_configs = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.isnot(None)
        ).count()

        return {
            "system_config_exists": system_config is not None,
            "system_config_enabled": system_config.is_enabled if system_config else False,
            "tenant_config_count": tenant_configs,
            "seeding_complete": system_config is not None,
        }

    except Exception as e:
        logger.error(f"Failed to get Sentinel seeding stats: {e}")
        return {
            "system_config_exists": False,
            "system_config_enabled": False,
            "tenant_config_count": 0,
            "seeding_complete": False,
            "error": str(e),
        }


# ============================================================================
# Phase 20 Enhancement: Detection Mode & Exceptions Migration
# ============================================================================

def migrate_sentinel_config_columns(db: Session) -> bool:
    """
    Add new columns to sentinel_config for existing databases.

    Adds:
    - detection_mode: 'block' (default), 'detect_only', or 'off'
    - enable_slash_command_analysis: True (default)

    Idempotent: safe to run multiple times.

    Args:
        db: Database session

    Returns:
        True if migration succeeded or columns already exist
    """
    columns_to_add = [
        ("detection_mode", "VARCHAR(20) DEFAULT 'block' NOT NULL"),
        ("enable_slash_command_analysis", "BOOLEAN DEFAULT 1 NOT NULL"),
        # Notification settings
        ("enable_notifications", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("notification_on_block", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("notification_on_detect", "BOOLEAN DEFAULT 0 NOT NULL"),
        ("notification_recipient", "VARCHAR(100)"),
        ("notification_message_template", "TEXT"),
    ]

    success = True
    for col_name, col_def in columns_to_add:
        try:
            db.execute(text(
                f"ALTER TABLE sentinel_config ADD COLUMN {col_name} {col_def}"
            ))
            db.commit()
            logger.info(f"Added column sentinel_config.{col_name}")
        except Exception as e:
            db.rollback()
            # Column already exists - this is expected
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug(f"Column sentinel_config.{col_name} already exists")
            else:
                logger.warning(f"Could not add sentinel_config.{col_name}: {e}")
                success = False

    return success


def migrate_sentinel_analysis_log(db: Session) -> bool:
    """
    Add exception tracking columns to sentinel_analysis_log for existing databases.

    Adds:
    - exception_applied: Whether an exception rule was matched
    - exception_id: ID of the matched exception
    - exception_name: Name of the matched exception (for audit)
    - detection_mode_used: Detection mode at time of analysis

    Idempotent: safe to run multiple times.

    Args:
        db: Database session

    Returns:
        True if migration succeeded or columns already exist
    """
    columns_to_add = [
        ("exception_applied", "BOOLEAN DEFAULT 0 NOT NULL"),
        ("exception_id", "INTEGER"),
        ("exception_name", "VARCHAR(100)"),
        ("detection_mode_used", "VARCHAR(20)"),
    ]

    success = True
    for col_name, col_def in columns_to_add:
        try:
            db.execute(text(
                f"ALTER TABLE sentinel_analysis_log ADD COLUMN {col_name} {col_def}"
            ))
            db.commit()
            logger.info(f"Added column sentinel_analysis_log.{col_name}")
        except Exception as e:
            db.rollback()
            # Column already exists - this is expected
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug(f"Column sentinel_analysis_log.{col_name} already exists")
            else:
                logger.warning(f"Could not add sentinel_analysis_log.{col_name}: {e}")
                success = False

    return success


def seed_sentinel_exceptions(db: Session) -> List["SentinelException"]:
    """
    Seed default exception rules for Sentinel.

    Creates system-level exceptions (tenant_id=NULL) for common testing scenarios:
    - nmap Official Test Target (scanme.nmap.org)
    - httpbin.org Testing (for webhook/HTTP testing)

    Idempotent: skips exceptions that already exist.

    Args:
        db: Database session

    Returns:
        List of created or existing exceptions
    """
    from models import SentinelException

    # Ensure table exists (for fresh installs)
    try:
        SentinelException.__table__.create(bind=db.get_bind(), checkfirst=True)
    except Exception as e:
        logger.debug(f"SentinelException table creation: {e}")

    # Default exceptions to seed
    DEFAULT_EXCEPTIONS = [
        {
            "name": "nmap Official Test Target",
            "description": "Allow nmap scanning on the official nmap test host (scanme.nmap.org). "
                           "This is a legitimate target provided by nmap.org for testing purposes.",
            "detection_types": "shell_malicious",
            "exception_type": "network_target",
            "pattern": "scanme.nmap.org",
            "match_mode": "exact",
            "action": "skip_llm",
            "priority": 50,
        },
        {
            "name": "httpbin.org Testing",
            "description": "Allow HTTP testing against httpbin.org. "
                           "This is a legitimate testing service for HTTP requests/webhooks.",
            "detection_types": "shell_malicious",
            "exception_type": "domain",
            "pattern": r".*httpbin\.org$",
            "match_mode": "regex",
            "action": "skip_llm",
            "priority": 50,
        },
    ]

    created_exceptions = []

    for exc_data in DEFAULT_EXCEPTIONS:
        try:
            # Check if exception already exists
            existing = db.query(SentinelException).filter(
                SentinelException.tenant_id.is_(None),
                SentinelException.name == exc_data["name"],
            ).first()

            if existing:
                logger.debug(f"Sentinel exception '{exc_data['name']}' already exists")
                created_exceptions.append(existing)
                continue

            # Create new exception
            exception = SentinelException(
                tenant_id=None,  # System-level
                agent_id=None,
                is_active=True,
                **exc_data
            )
            db.add(exception)
            db.commit()
            db.refresh(exception)

            logger.info(f"Seeded Sentinel exception: {exc_data['name']}")
            created_exceptions.append(exception)

        except Exception as e:
            logger.error(f"Failed to seed exception '{exc_data['name']}': {e}")
            db.rollback()

    return created_exceptions


def run_sentinel_migrations(db: Session) -> dict:
    """
    Run all Sentinel migrations and seeding.

    Convenience function that runs all migration steps in order.
    Called from db.py init_database() after seed_sentinel_config().

    Args:
        db: Database session

    Returns:
        Dict with migration results
    """
    results = {
        "config_columns_migrated": False,
        "log_columns_migrated": False,
        "exceptions_seeded": 0,
        "errors": [],
    }

    try:
        results["config_columns_migrated"] = migrate_sentinel_config_columns(db)
    except Exception as e:
        results["errors"].append(f"Config columns migration failed: {e}")
        logger.error(f"Config columns migration failed: {e}", exc_info=True)

    try:
        results["log_columns_migrated"] = migrate_sentinel_analysis_log(db)
    except Exception as e:
        results["errors"].append(f"Log columns migration failed: {e}")
        logger.error(f"Log columns migration failed: {e}", exc_info=True)

    try:
        exceptions = seed_sentinel_exceptions(db)
        results["exceptions_seeded"] = len(exceptions)
    except Exception as e:
        results["errors"].append(f"Exceptions seeding failed: {e}")
        logger.error(f"Exceptions seeding failed: {e}", exc_info=True)

    if not results["errors"]:
        logger.info("Sentinel migrations completed successfully")
    else:
        logger.warning(f"Sentinel migrations completed with {len(results['errors'])} errors")

    return results
