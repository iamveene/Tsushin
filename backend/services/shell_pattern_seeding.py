"""
Shell Security Pattern Seeding Service - Phase 19

Seeds default system security patterns from hardcoded BLOCKED_PATTERNS
and HIGH_RISK_PATTERNS into the database.

Called at app startup to ensure system defaults exist.
"""

import logging
from sqlalchemy.orm import Session
from typing import List, Dict

logger = logging.getLogger(__name__)


# Category mapping for auto-categorization based on keywords
PATTERN_CATEGORIES = {
    # Filesystem
    'rm': 'filesystem',
    'mv': 'filesystem',
    'delete': 'filesystem',
    'mkfs': 'filesystem',
    'fdisk': 'filesystem',
    'dd': 'filesystem',
    'format': 'filesystem',
    # Permissions
    'chmod': 'permissions',
    'chown': 'permissions',
    # System
    'systemctl': 'system',
    'service': 'system',
    'fork': 'system',
    'passwd': 'system',
    'shadow': 'system',
    # Network
    'iptables': 'network',
    'ufw': 'network',
    'netcat': 'network',
    'nc': 'network',
    'wget': 'network',
    'curl': 'network',
    # Package management
    'apt': 'package',
    'yum': 'package',
    'dnf': 'package',
    'pip': 'package',
    # Database
    'mysql': 'database',
    'psql': 'database',
    'mongo': 'database',
    'redis': 'database',
    'drop': 'database',
    # Container
    'docker': 'container',
    'kubectl': 'container',
    # Security
    'credential': 'security',
    'history': 'security',
    'pem': 'security',
    'key': 'security',
    'crt': 'security',
    'env': 'security',
    'printenv': 'security',
    # Disk
    '/dev/sd': 'disk',
    '/dev/nvme': 'disk',
}


def categorize_pattern(pattern: str, description: str) -> str:
    """
    Infer category from pattern or description.

    Args:
        pattern: The regex pattern
        description: Human-readable description

    Returns:
        Category string
    """
    import re as regex_module

    # Use description as primary source (more readable)
    # Then fall back to pattern
    text = description.lower()

    # Check longer/more specific keywords first (sorted by length descending)
    sorted_keywords = sorted(PATTERN_CATEGORIES.items(), key=lambda x: -len(x[0]))

    for keyword, category in sorted_keywords:
        # For description, use simple substring match
        if keyword in text:
            return category

    # If not found in description, check the pattern
    # But be careful with regex characters
    pattern_lower = pattern.lower()
    for keyword, category in sorted_keywords:
        # For patterns with special regex chars, just check if the keyword appears
        # as a distinct token (not as part of another word)
        if len(keyword) <= 3:
            # For short keywords, check if they appear as standalone or at word boundaries
            # in the pattern itself (before regex escaping)
            if regex_module.search(r'(^|[^a-z])' + regex_module.escape(keyword) + r'($|[^a-z])', pattern_lower):
                return category
        elif keyword in pattern_lower:
            return category
            return category
    return 'other'


def seed_default_security_patterns(db: Session) -> List[Dict]:
    """
    Seed default security patterns from hardcoded lists.

    Creates patterns with is_system_default=True and tenant_id=None.
    Idempotent: skips patterns that already exist.

    Args:
        db: Database session

    Returns:
        List of created pattern dicts
    """
    from models import ShellSecurityPattern
    from services.shell_security_service import BLOCKED_PATTERNS, HIGH_RISK_PATTERNS, RiskLevel

    # Get existing system patterns
    existing_patterns = set(
        p for (p,) in db.query(ShellSecurityPattern.pattern)
        .filter(ShellSecurityPattern.is_system_default == True)
        .all()
    )

    created_patterns = []

    try:
        # Seed BLOCKED patterns
        for pattern, description in BLOCKED_PATTERNS:
            if pattern in existing_patterns:
                continue

            sp = ShellSecurityPattern(
                tenant_id=None,
                pattern=pattern,
                pattern_type='blocked',
                risk_level='critical',  # Blocked patterns are always critical
                description=description,
                category=categorize_pattern(pattern, description),
                is_system_default=True,
                is_active=True
            )
            db.add(sp)
            created_patterns.append({
                'pattern': pattern,
                'type': 'blocked',
                'description': description
            })
            logger.info(f"Created system blocked pattern: {description}")

        # Seed HIGH_RISK patterns
        for pattern, risk_level, description in HIGH_RISK_PATTERNS:
            if pattern in existing_patterns:
                continue

            # Convert RiskLevel enum to string
            risk_str = risk_level.value if isinstance(risk_level, RiskLevel) else risk_level

            sp = ShellSecurityPattern(
                tenant_id=None,
                pattern=pattern,
                pattern_type='high_risk',
                risk_level=risk_str,
                description=description,
                category=categorize_pattern(pattern, description),
                is_system_default=True,
                is_active=True
            )
            db.add(sp)
            created_patterns.append({
                'pattern': pattern,
                'type': 'high_risk',
                'risk_level': risk_str,
                'description': description
            })
            logger.info(f"Created system high-risk pattern: {description}")

        db.commit()
        logger.info(f"Seeded {len(created_patterns)} security patterns")
        return created_patterns

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to seed security patterns: {e}", exc_info=True)
        raise


def get_seeding_stats(db: Session) -> Dict:
    """
    Get statistics about seeded patterns.

    Args:
        db: Database session

    Returns:
        Dict with pattern counts
    """
    from models import ShellSecurityPattern

    total = db.query(ShellSecurityPattern).count()
    system_default = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.is_system_default == True
    ).count()
    tenant_custom = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.is_system_default == False
    ).count()
    blocked = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.pattern_type == 'blocked'
    ).count()
    high_risk = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.pattern_type == 'high_risk'
    ).count()
    active = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.is_active == True
    ).count()
    inactive = db.query(ShellSecurityPattern).filter(
        ShellSecurityPattern.is_active == False
    ).count()

    return {
        'total': total,
        'system_default': system_default,
        'tenant_custom': tenant_custom,
        'blocked': blocked,
        'high_risk': high_risk,
        'active': active,
        'inactive': inactive
    }
