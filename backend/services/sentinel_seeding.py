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
            detect_memory_poisoning=True,

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
        # MemGuard (memory poisoning) detection
        ("detect_memory_poisoning", "BOOLEAN DEFAULT 1 NOT NULL"),
        ("memory_poisoning_prompt", "TEXT"),
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


# ============================================================================
# Phase v1.6.0: Sentinel Security Profiles Migration
# ============================================================================

def create_sentinel_profile_tables(db: Session) -> bool:
    """
    Create sentinel_profile and sentinel_profile_assignment tables.

    Uses raw SQL for CREATE TABLE IF NOT EXISTS to handle the partial unique
    index on is_default (SQLAlchemy can't express WHERE clause on indexes
    declaratively for SQLite).

    Idempotent: safe to run multiple times.

    Args:
        db: Database session

    Returns:
        True if tables exist (created or already existed)
    """
    try:
        # Let SQLAlchemy create the tables from model definitions
        from models import SentinelProfile, SentinelProfileAssignment
        SentinelProfile.__table__.create(bind=db.get_bind(), checkfirst=True)
        SentinelProfileAssignment.__table__.create(bind=db.get_bind(), checkfirst=True)

        # Create partial unique index for is_default uniqueness per tenant
        # This ensures at most one default profile per tenant (including system scope)
        try:
            db.execute(text(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sentinel_profile_one_default "
                "ON sentinel_profile(COALESCE(tenant_id, '__system__')) WHERE is_default = 1"
            ))
            db.commit()
            logger.debug("Created partial unique index idx_sentinel_profile_one_default")
        except Exception as e:
            db.rollback()
            if "already exists" in str(e).lower():
                logger.debug("Partial unique index idx_sentinel_profile_one_default already exists")
            else:
                logger.warning(f"Could not create partial unique index: {e}")

        logger.info("Sentinel profile tables ready")
        return True

    except Exception as e:
        logger.error(f"Failed to create Sentinel profile tables: {e}", exc_info=True)
        db.rollback()
        return False


def seed_system_profiles(db: Session) -> list:
    """
    Seed 4 built-in system profiles for Sentinel.

    System profiles (is_system=True, tenant_id=NULL):
    - off: Sentinel disabled
    - permissive: Log-only, moderate sensitivity (DEFAULT)
    - moderate: Block threats, moderate sensitivity
    - aggressive: Block all, max sensitivity

    Idempotent: skips profiles that already exist (matched by slug).

    Args:
        db: Database session

    Returns:
        List of created or existing SentinelProfile instances
    """
    from models import SentinelProfile

    SYSTEM_PROFILES = [
        {
            "name": "Off",
            "slug": "off",
            "description": "Sentinel protection disabled. No analysis or blocking performed.",
            "is_enabled": True,  # Profile itself is "enabled" but mode=off means no analysis
            "detection_mode": "off",
            "aggressiveness_level": 0,
            "is_default": False,
        },
        {
            "name": "Permissive",
            "slug": "permissive",
            "description": "Log-only mode with moderate sensitivity. Threats are detected and logged but not blocked.",
            "is_enabled": True,
            "detection_mode": "detect_only",
            "aggressiveness_level": 1,
            "is_default": True,  # System-wide default fallback — detect-only so admins can evaluate before enabling blocking
        },
        {
            "name": "Moderate",
            "slug": "moderate",
            "description": "Balanced protection. Blocks detected threats with moderate sensitivity. Recommended for production.",
            "is_enabled": True,
            "detection_mode": "block",
            "aggressiveness_level": 1,
            "is_default": False,
        },
        {
            "name": "Aggressive",
            "slug": "aggressive",
            "description": "Maximum protection. Blocks all potential threats with highest sensitivity. May produce more false positives.",
            "is_enabled": True,
            "detection_mode": "block",
            "aggressiveness_level": 3,
            "is_default": False,
        },
    ]

    created_profiles = []

    for profile_data in SYSTEM_PROFILES:
        try:
            # Check if profile already exists
            existing = db.query(SentinelProfile).filter(
                SentinelProfile.tenant_id.is_(None),
                SentinelProfile.slug == profile_data["slug"],
            ).first()

            if existing:
                logger.debug(f"System profile '{profile_data['slug']}' already exists")
                created_profiles.append(existing)
                continue

            # Create system profile with defaults for all other fields
            profile = SentinelProfile(
                tenant_id=None,
                is_system=True,
                # Identity
                name=profile_data["name"],
                slug=profile_data["slug"],
                description=profile_data["description"],
                # Global settings
                is_enabled=profile_data["is_enabled"],
                detection_mode=profile_data["detection_mode"],
                aggressiveness_level=profile_data["aggressiveness_level"],
                is_default=profile_data["is_default"],
                # Component toggles (all enabled by default)
                enable_prompt_analysis=True,
                enable_tool_analysis=True,
                enable_shell_analysis=True,
                enable_slash_command_analysis=True,
                # LLM (defaults)
                llm_provider="gemini",
                llm_model="gemini-2.5-flash-lite",
                llm_max_tokens=256,
                llm_temperature=0.1,
                # Performance (defaults)
                cache_ttl_seconds=300,
                max_input_chars=5000,
                timeout_seconds=5.0,
                # Actions
                block_on_detection=True,
                log_all_analyses=False,
                # Notifications
                enable_notifications=True,
                notification_on_block=True,
                notification_on_detect=False,
                # Empty overrides = all detections use registry defaults
                detection_overrides="{}",
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)

            logger.info(f"Seeded system profile: {profile_data['name']} (slug={profile_data['slug']})")
            created_profiles.append(profile)

        except Exception as e:
            logger.error(f"Failed to seed system profile '{profile_data['slug']}': {e}")
            db.rollback()

    # Migration: ensure "permissive" is the system default (not "moderate")
    # This fixes existing DBs where "moderate" was seeded as is_default=True.
    # Must be done in two commits to avoid UNIQUE constraint violation on the
    # partial index (idx_sentinel_profile_one_default) which enforces one
    # default per tenant scope.
    try:
        moderate = db.query(SentinelProfile).filter(
            SentinelProfile.tenant_id.is_(None),
            SentinelProfile.slug == "moderate",
            SentinelProfile.is_default == True,
        ).first()

        if moderate:
            permissive = db.query(SentinelProfile).filter(
                SentinelProfile.tenant_id.is_(None),
                SentinelProfile.slug == "permissive",
            ).first()

            if permissive:
                # Step 1: unset moderate as default
                moderate.is_default = False
                db.commit()
                # Step 2: set permissive as default
                permissive.is_default = True
                db.commit()
                logger.info(
                    "Migrated system default profile: moderate -> permissive "
                    "(detect_only mode aligns with legacy SentinelConfig)"
                )
    except Exception as e:
        logger.error(f"Failed to migrate default profile: {e}")
        db.rollback()

    return created_profiles


def _build_detection_overrides(config) -> str:
    """
    Build detection_overrides JSON from legacy SentinelConfig columns.

    Only non-default values are written to keep JSON sparse.
    Default is all detections enabled with no custom prompts.

    Args:
        config: SentinelConfig instance (legacy flat config)

    Returns:
        JSON string for detection_overrides column
    """
    import json

    overrides = {}

    # Map legacy boolean columns to detection type keys
    detection_map = {
        "prompt_injection": {
            "enabled_col": "detect_prompt_injection",
            "prompt_col": "prompt_injection_prompt",
        },
        "agent_takeover": {
            "enabled_col": "detect_agent_takeover",
            "prompt_col": "agent_takeover_prompt",
        },
        "poisoning": {
            "enabled_col": "detect_poisoning",
            "prompt_col": "poisoning_prompt",
        },
        "shell_malicious": {
            "enabled_col": "detect_shell_malicious_intent",
            "prompt_col": "shell_intent_prompt",
        },
        "memory_poisoning": {
            "enabled_col": "detect_memory_poisoning",
            "prompt_col": "memory_poisoning_prompt",
        },
    }

    for det_type, cols in detection_map.items():
        enabled = getattr(config, cols["enabled_col"], True)
        custom_prompt = getattr(config, cols["prompt_col"], None)

        # Only write non-default values
        if not enabled or custom_prompt:
            override = {}
            if not enabled:
                override["enabled"] = False
            if custom_prompt:
                override["custom_prompt"] = custom_prompt
            overrides[det_type] = override

    return json.dumps(overrides)


def migrate_legacy_configs_to_profiles(db: Session) -> dict:
    """
    Migrate existing SentinelConfig and SentinelAgentConfig to profile system.

    Steps (all idempotent):
    1. System config: Update the seeded "Moderate" profile with legacy values
    2. Tenant configs: Create "{tenant} Custom" profiles + tenant-level assignments
    3. Agent overrides: Create "Agent {id} Override" profiles + agent-level assignments

    Args:
        db: Database session

    Returns:
        Dict with migration statistics
    """
    from models import SentinelConfig, SentinelAgentConfig, SentinelProfile, SentinelProfileAssignment

    results = {
        "system_migrated": False,
        "tenant_profiles_created": 0,
        "agent_profiles_created": 0,
        "errors": [],
    }

    # Step 1: Migrate system config to "Moderate" profile
    try:
        system_config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

        if system_config:
            moderate_profile = db.query(SentinelProfile).filter(
                SentinelProfile.tenant_id.is_(None),
                SentinelProfile.slug == "moderate",
            ).first()

            if moderate_profile:
                # Update moderate profile with legacy system config values
                moderate_profile.is_enabled = system_config.is_enabled
                moderate_profile.enable_prompt_analysis = system_config.enable_prompt_analysis
                moderate_profile.enable_tool_analysis = system_config.enable_tool_analysis
                moderate_profile.enable_shell_analysis = system_config.enable_shell_analysis
                moderate_profile.aggressiveness_level = system_config.aggressiveness_level
                moderate_profile.llm_provider = system_config.llm_provider
                moderate_profile.llm_model = system_config.llm_model
                moderate_profile.llm_max_tokens = system_config.llm_max_tokens
                moderate_profile.llm_temperature = system_config.llm_temperature
                moderate_profile.cache_ttl_seconds = system_config.cache_ttl_seconds
                moderate_profile.max_input_chars = system_config.max_input_chars
                moderate_profile.timeout_seconds = system_config.timeout_seconds
                moderate_profile.block_on_detection = system_config.block_on_detection
                moderate_profile.log_all_analyses = system_config.log_all_analyses

                # Phase 20 columns (may not exist on very old DBs, use getattr)
                detection_mode = getattr(system_config, 'detection_mode', 'block')
                moderate_profile.detection_mode = detection_mode or 'block'

                enable_slash = getattr(system_config, 'enable_slash_command_analysis', True)
                moderate_profile.enable_slash_command_analysis = enable_slash if enable_slash is not None else True

                # Notification settings
                moderate_profile.enable_notifications = getattr(system_config, 'enable_notifications', True)
                moderate_profile.notification_on_block = getattr(system_config, 'notification_on_block', True)
                moderate_profile.notification_on_detect = getattr(system_config, 'notification_on_detect', False)
                moderate_profile.notification_recipient = getattr(system_config, 'notification_recipient', None)
                moderate_profile.notification_message_template = getattr(system_config, 'notification_message_template', None)

                # Build detection_overrides from legacy boolean + prompt columns
                moderate_profile.detection_overrides = _build_detection_overrides(system_config)

                db.commit()
                results["system_migrated"] = True
                logger.info("Migrated system config to Moderate profile")

    except Exception as e:
        results["errors"].append(f"System config migration: {e}")
        logger.error(f"Failed to migrate system config: {e}", exc_info=True)
        db.rollback()

    # Step 2: Migrate tenant configs
    try:
        tenant_configs = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.isnot(None)
        ).all()

        for config in tenant_configs:
            try:
                tenant_id = config.tenant_id
                slug = f"{tenant_id}-custom"

                # Check if profile already exists for this tenant
                existing = db.query(SentinelProfile).filter(
                    SentinelProfile.tenant_id == tenant_id,
                    SentinelProfile.slug == slug,
                ).first()

                if existing:
                    logger.debug(f"Tenant profile '{slug}' already exists")
                    continue

                # Create tenant custom profile
                profile = SentinelProfile(
                    name=f"{tenant_id} Custom",
                    slug=slug,
                    description=f"Migrated from legacy config for tenant {tenant_id}",
                    tenant_id=tenant_id,
                    is_system=False,
                    is_default=False,
                    is_enabled=config.is_enabled,
                    detection_mode=getattr(config, 'detection_mode', 'block') or 'block',
                    aggressiveness_level=config.aggressiveness_level,
                    enable_prompt_analysis=config.enable_prompt_analysis,
                    enable_tool_analysis=config.enable_tool_analysis,
                    enable_shell_analysis=config.enable_shell_analysis,
                    enable_slash_command_analysis=getattr(config, 'enable_slash_command_analysis', True) or True,
                    llm_provider=config.llm_provider,
                    llm_model=config.llm_model,
                    llm_max_tokens=config.llm_max_tokens,
                    llm_temperature=config.llm_temperature,
                    cache_ttl_seconds=config.cache_ttl_seconds,
                    max_input_chars=config.max_input_chars,
                    timeout_seconds=config.timeout_seconds,
                    block_on_detection=config.block_on_detection,
                    log_all_analyses=config.log_all_analyses,
                    enable_notifications=getattr(config, 'enable_notifications', True),
                    notification_on_block=getattr(config, 'notification_on_block', True),
                    notification_on_detect=getattr(config, 'notification_on_detect', False),
                    notification_recipient=getattr(config, 'notification_recipient', None),
                    notification_message_template=getattr(config, 'notification_message_template', None),
                    detection_overrides=_build_detection_overrides(config),
                )
                db.add(profile)
                db.flush()  # Get profile.id

                # Create tenant-level assignment
                existing_assign = db.query(SentinelProfileAssignment).filter(
                    SentinelProfileAssignment.tenant_id == tenant_id,
                    SentinelProfileAssignment.agent_id.is_(None),
                    SentinelProfileAssignment.skill_type.is_(None),
                ).first()

                if not existing_assign:
                    assignment = SentinelProfileAssignment(
                        tenant_id=tenant_id,
                        agent_id=None,
                        skill_type=None,
                        profile_id=profile.id,
                    )
                    db.add(assignment)

                db.commit()
                results["tenant_profiles_created"] += 1
                logger.info(f"Migrated tenant config for {tenant_id}")

            except Exception as e:
                results["errors"].append(f"Tenant {config.tenant_id}: {e}")
                logger.error(f"Failed to migrate tenant config {config.tenant_id}: {e}")
                db.rollback()

    except Exception as e:
        results["errors"].append(f"Tenant config query: {e}")
        logger.error(f"Failed to query tenant configs: {e}", exc_info=True)

    # Step 3: Migrate agent overrides
    try:
        agent_overrides = db.query(SentinelAgentConfig).all()

        for agent_config in agent_overrides:
            try:
                agent_id = agent_config.agent_id

                # Get agent's tenant_id
                from models import Agent
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent:
                    logger.warning(f"Agent {agent_id} not found, skipping override migration")
                    continue

                tenant_id = agent.tenant_id
                slug = f"agent-{agent_id}-override"

                # Check if profile already exists
                existing = db.query(SentinelProfile).filter(
                    SentinelProfile.tenant_id == tenant_id,
                    SentinelProfile.slug == slug,
                ).first()

                if existing:
                    logger.debug(f"Agent override profile '{slug}' already exists")
                    continue

                # Resolve effective config by merging tenant + agent override
                # (replicating old _merge_configs logic)
                system_config = db.query(SentinelConfig).filter(
                    SentinelConfig.tenant_id.is_(None)
                ).first()

                tenant_config = db.query(SentinelConfig).filter(
                    SentinelConfig.tenant_id == tenant_id
                ).first()

                # Start with system config as base
                base = system_config or SentinelConfig()

                # Overlay tenant config if present
                if tenant_config:
                    base = tenant_config

                # Apply agent overrides (only non-None values)
                is_enabled = agent_config.is_enabled if agent_config.is_enabled is not None else base.is_enabled
                enable_prompt = agent_config.enable_prompt_analysis if agent_config.enable_prompt_analysis is not None else base.enable_prompt_analysis
                enable_tool = agent_config.enable_tool_analysis if agent_config.enable_tool_analysis is not None else base.enable_tool_analysis
                enable_shell = agent_config.enable_shell_analysis if agent_config.enable_shell_analysis is not None else base.enable_shell_analysis
                aggressiveness = agent_config.aggressiveness_level if agent_config.aggressiveness_level is not None else base.aggressiveness_level

                profile = SentinelProfile(
                    name=f"Agent {agent_id} Override",
                    slug=slug,
                    description=f"Migrated from legacy agent override for agent {agent_id}",
                    tenant_id=tenant_id,
                    is_system=False,
                    is_default=False,
                    is_enabled=is_enabled,
                    detection_mode=getattr(base, 'detection_mode', 'block') or 'block',
                    aggressiveness_level=aggressiveness,
                    enable_prompt_analysis=enable_prompt,
                    enable_tool_analysis=enable_tool,
                    enable_shell_analysis=enable_shell,
                    enable_slash_command_analysis=getattr(base, 'enable_slash_command_analysis', True) or True,
                    llm_provider=base.llm_provider,
                    llm_model=base.llm_model,
                    llm_max_tokens=base.llm_max_tokens,
                    llm_temperature=base.llm_temperature,
                    cache_ttl_seconds=base.cache_ttl_seconds,
                    max_input_chars=base.max_input_chars,
                    timeout_seconds=base.timeout_seconds,
                    block_on_detection=base.block_on_detection,
                    log_all_analyses=base.log_all_analyses,
                    enable_notifications=getattr(base, 'enable_notifications', True),
                    notification_on_block=getattr(base, 'notification_on_block', True),
                    notification_on_detect=getattr(base, 'notification_on_detect', False),
                    notification_recipient=getattr(base, 'notification_recipient', None),
                    notification_message_template=getattr(base, 'notification_message_template', None),
                    detection_overrides=_build_detection_overrides(base),
                )
                db.add(profile)
                db.flush()

                # Create agent-level assignment
                existing_assign = db.query(SentinelProfileAssignment).filter(
                    SentinelProfileAssignment.tenant_id == tenant_id,
                    SentinelProfileAssignment.agent_id == agent_id,
                    SentinelProfileAssignment.skill_type.is_(None),
                ).first()

                if not existing_assign:
                    assignment = SentinelProfileAssignment(
                        tenant_id=tenant_id,
                        agent_id=agent_id,
                        skill_type=None,
                        profile_id=profile.id,
                    )
                    db.add(assignment)

                db.commit()
                results["agent_profiles_created"] += 1
                logger.info(f"Migrated agent override for agent {agent_id}")

            except Exception as e:
                results["errors"].append(f"Agent {agent_config.agent_id}: {e}")
                logger.error(f"Failed to migrate agent override {agent_config.agent_id}: {e}")
                db.rollback()

    except Exception as e:
        results["errors"].append(f"Agent override query: {e}")
        logger.error(f"Failed to query agent overrides: {e}", exc_info=True)

    if not results["errors"]:
        logger.info(
            f"Legacy migration complete: system={results['system_migrated']}, "
            f"tenants={results['tenant_profiles_created']}, agents={results['agent_profiles_created']}"
        )
    else:
        logger.warning(f"Legacy migration completed with {len(results['errors'])} errors")

    return results


def migrate_to_profiles(db: Session) -> dict:
    """
    Run all Sentinel Security Profile migrations.

    Orchestrator function called from db.py init_database().
    Runs all profile migration steps in order:
    1. Create tables
    2. Seed system profiles
    3. Migrate legacy configs

    All steps are idempotent.

    Args:
        db: Database session

    Returns:
        Dict with combined migration results
    """
    results = {
        "tables_created": False,
        "system_profiles_seeded": 0,
        "legacy_migration": {},
        "errors": [],
    }

    # Step 1: Create tables
    try:
        results["tables_created"] = create_sentinel_profile_tables(db)
    except Exception as e:
        results["errors"].append(f"Table creation: {e}")
        logger.error(f"Profile table creation failed: {e}", exc_info=True)
        return results  # Can't proceed without tables

    # Step 2: Seed system profiles
    try:
        profiles = seed_system_profiles(db)
        results["system_profiles_seeded"] = len(profiles)
    except Exception as e:
        results["errors"].append(f"System profile seeding: {e}")
        logger.error(f"System profile seeding failed: {e}", exc_info=True)

    # Step 3: Migrate legacy configs
    try:
        results["legacy_migration"] = migrate_legacy_configs_to_profiles(db)
    except Exception as e:
        results["errors"].append(f"Legacy migration: {e}")
        logger.error(f"Legacy migration failed: {e}", exc_info=True)

    if not results["errors"]:
        logger.info("Sentinel profile migration completed successfully")
    else:
        logger.warning(f"Sentinel profile migration completed with {len(results['errors'])} errors")

    return results
