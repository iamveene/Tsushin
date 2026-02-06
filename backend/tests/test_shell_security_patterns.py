"""
Shell Security Pattern Tests - Phase 19

Tests for:
- ShellSecurityPattern model
- Security pattern seeding
- Security service with DB patterns
- Pattern caching
- API endpoints
"""

import pytest
import re
import time
from datetime import datetime
from unittest.mock import MagicMock, patch

# Test imports
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, ShellSecurityPattern
from services.shell_security_service import (
    ShellSecurityService, RiskLevel, SecurityCheckResult,
    BLOCKED_PATTERNS, HIGH_RISK_PATTERNS
)
from services.shell_pattern_seeding import (
    seed_default_security_patterns, get_seeding_stats, categorize_pattern
)


@pytest.fixture
def db_engine():
    """Create in-memory SQLite database."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session for testing."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_tenant_id():
    """Test tenant ID."""
    return "test-tenant-001"


@pytest.fixture
def security_service():
    """Create a fresh security service instance."""
    return ShellSecurityService()


class TestShellSecurityPatternModel:
    """Tests for ShellSecurityPattern model."""

    def test_create_blocked_pattern(self, db_session, test_tenant_id):
        """Test creating a blocked pattern."""
        pattern = ShellSecurityPattern(
            tenant_id=test_tenant_id,
            pattern=r"rm\s+-rf\s+/custom",
            pattern_type="blocked",
            risk_level="critical",
            description="Custom blocked pattern",
            category="filesystem",
            is_system_default=False,
            is_active=True
        )
        db_session.add(pattern)
        db_session.commit()

        assert pattern.id is not None
        assert pattern.pattern_type == "blocked"
        assert pattern.is_system_default is False
        assert pattern.is_active is True

    def test_create_high_risk_pattern(self, db_session, test_tenant_id):
        """Test creating a high-risk pattern with risk level."""
        pattern = ShellSecurityPattern(
            tenant_id=test_tenant_id,
            pattern=r"my-dangerous-cmd",
            pattern_type="high_risk",
            risk_level="high",
            description="Custom high-risk pattern",
            category="custom",
            is_system_default=False,
            is_active=True
        )
        db_session.add(pattern)
        db_session.commit()

        assert pattern.id is not None
        assert pattern.pattern_type == "high_risk"
        assert pattern.risk_level == "high"

    def test_system_default_pattern(self, db_session):
        """Test creating a system default pattern (no tenant_id)."""
        pattern = ShellSecurityPattern(
            tenant_id=None,  # System default
            pattern=r"fork\s+bomb",
            pattern_type="blocked",
            risk_level="critical",
            description="Fork bomb pattern",
            category="system",
            is_system_default=True,
            is_active=True
        )
        db_session.add(pattern)
        db_session.commit()

        assert pattern.tenant_id is None
        assert pattern.is_system_default is True

    def test_query_by_tenant(self, db_session, test_tenant_id):
        """Test querying patterns by tenant."""
        # Add system pattern
        system_pattern = ShellSecurityPattern(
            tenant_id=None,
            pattern=r"system-pattern",
            pattern_type="blocked",
            description="System pattern",
            is_system_default=True
        )
        # Add tenant pattern
        tenant_pattern = ShellSecurityPattern(
            tenant_id=test_tenant_id,
            pattern=r"tenant-pattern",
            pattern_type="high_risk",
            risk_level="medium",
            description="Tenant pattern",
            is_system_default=False
        )
        db_session.add_all([system_pattern, tenant_pattern])
        db_session.commit()

        # Query should return both
        from sqlalchemy import or_
        patterns = db_session.query(ShellSecurityPattern).filter(
            or_(
                ShellSecurityPattern.tenant_id.is_(None),
                ShellSecurityPattern.tenant_id == test_tenant_id
            )
        ).all()

        assert len(patterns) == 2


class TestPatternSeeding:
    """Tests for pattern seeding service."""

    def test_seed_default_patterns(self, db_session):
        """Test seeding default patterns."""
        created = seed_default_security_patterns(db_session)

        # Should create patterns from BLOCKED_PATTERNS and HIGH_RISK_PATTERNS
        expected_count = len(BLOCKED_PATTERNS) + len(HIGH_RISK_PATTERNS)
        assert len(created) == expected_count

    def test_seeding_is_idempotent(self, db_session):
        """Test that seeding twice doesn't create duplicates."""
        # First seed
        created1 = seed_default_security_patterns(db_session)

        # Second seed
        created2 = seed_default_security_patterns(db_session)

        # Second seed should create nothing (all already exist)
        assert len(created2) == 0

        # Total count should match first seed
        total = db_session.query(ShellSecurityPattern).count()
        assert total == len(created1)

    def test_get_seeding_stats(self, db_session):
        """Test getting seeding statistics."""
        seed_default_security_patterns(db_session)
        stats = get_seeding_stats(db_session)

        assert stats['total'] > 0
        assert stats['system_default'] == stats['total']  # All are system defaults
        assert stats['tenant_custom'] == 0
        assert stats['blocked'] == len(BLOCKED_PATTERNS)
        assert stats['high_risk'] == len(HIGH_RISK_PATTERNS)
        assert stats['active'] == stats['total']
        assert stats['inactive'] == 0

    def test_categorize_pattern(self):
        """Test pattern categorization."""
        # Test categorization by description keywords
        assert categorize_pattern(r"rm\s+-rf", "Delete files") == "filesystem"
        assert categorize_pattern(r"chmod\s+777", "chmod permissions") == "permissions"
        assert categorize_pattern(r"iptables", "Firewall rules") == "network"
        assert categorize_pattern(r"docker\s+rm", "Container") == "container"
        assert categorize_pattern(r"DROP\s+TABLE", "Database drop") == "database"
        assert categorize_pattern(r"unknown-pattern", "Unknown") == "other"
        # Test categorization by pattern keywords when description doesn't match
        assert categorize_pattern(r"chown -R", "Change ownership") == "permissions"
        assert categorize_pattern(r"apt remove", "Package removal") == "package"


class TestSecurityServiceWithDB:
    """Tests for ShellSecurityService with database patterns."""

    def test_get_patterns_for_tenant_empty_db(self, db_session, test_tenant_id, security_service):
        """Test getting patterns when DB is empty (falls back to hardcoded)."""
        blocked, high_risk = security_service.get_patterns_for_tenant(test_tenant_id, db_session)

        # Should return hardcoded fallbacks
        assert len(blocked) == len(BLOCKED_PATTERNS)
        assert len(high_risk) == len(HIGH_RISK_PATTERNS)

    def test_get_patterns_for_tenant_seeded(self, db_session, test_tenant_id, security_service):
        """Test getting patterns after seeding."""
        seed_default_security_patterns(db_session)

        blocked, high_risk = security_service.get_patterns_for_tenant(test_tenant_id, db_session)

        assert len(blocked) == len(BLOCKED_PATTERNS)
        assert len(high_risk) == len(HIGH_RISK_PATTERNS)

    def test_pattern_caching(self, db_session, test_tenant_id, security_service):
        """Test that patterns are cached."""
        seed_default_security_patterns(db_session)

        # First call - populates cache
        blocked1, _ = security_service.get_patterns_for_tenant(test_tenant_id, db_session)

        # Check cache stats
        stats = security_service.get_cache_stats()
        assert stats['total_cached'] == 1
        assert stats['active_caches'] == 1

        # Second call - should use cache (can't easily verify, but stats should be same)
        blocked2, _ = security_service.get_patterns_for_tenant(test_tenant_id, db_session)
        assert len(blocked1) == len(blocked2)

    def test_cache_invalidation(self, db_session, test_tenant_id, security_service):
        """Test cache invalidation."""
        seed_default_security_patterns(db_session)

        # First call - populates cache
        security_service.get_patterns_for_tenant(test_tenant_id, db_session)

        # Invalidate cache
        security_service.invalidate_cache(test_tenant_id)

        # Check cache stats
        stats = security_service.get_cache_stats()
        assert stats['total_cached'] == 0

    def test_check_command_with_db_patterns(self, db_session, test_tenant_id, security_service):
        """Test command checking uses DB patterns."""
        seed_default_security_patterns(db_session)

        # Test blocked command
        result = security_service.check_command(
            "rm -rf /",
            tenant_id=test_tenant_id,
            db=db_session
        )

        assert result.allowed is False
        assert "BLOCKED" in result.blocked_reason

    def test_check_command_high_risk(self, db_session, test_tenant_id, security_service):
        """Test high-risk command detection."""
        seed_default_security_patterns(db_session)

        # Test high-risk command (chmod 777)
        result = security_service.check_command(
            "chmod 777 /var/www",
            tenant_id=test_tenant_id,
            db=db_session
        )

        assert result.allowed is True
        assert result.risk_level >= RiskLevel.HIGH
        assert result.requires_approval is True

    def test_check_command_safe(self, db_session, test_tenant_id, security_service):
        """Test safe command passes."""
        seed_default_security_patterns(db_session)

        result = security_service.check_command(
            "ls -la",
            tenant_id=test_tenant_id,
            db=db_session
        )

        assert result.allowed is True
        assert result.risk_level == RiskLevel.LOW
        assert result.requires_approval is False

    def test_custom_tenant_pattern_blocks(self, db_session, test_tenant_id, security_service):
        """Test that custom tenant pattern blocks commands."""
        seed_default_security_patterns(db_session)

        # Add custom blocked pattern for tenant
        custom = ShellSecurityPattern(
            tenant_id=test_tenant_id,
            pattern=r"my-secret-api",
            pattern_type="blocked",
            risk_level="critical",
            description="Block access to secret API",
            is_system_default=False,
            is_active=True
        )
        db_session.add(custom)
        db_session.commit()

        # Invalidate cache to pick up new pattern
        security_service.invalidate_cache(test_tenant_id)

        # Command should be blocked
        result = security_service.check_command(
            "curl http://my-secret-api.internal",
            tenant_id=test_tenant_id,
            db=db_session
        )

        assert result.allowed is False
        assert "BLOCKED" in result.blocked_reason

    def test_inactive_pattern_ignored(self, db_session, test_tenant_id, security_service):
        """Test that inactive patterns are not used."""
        seed_default_security_patterns(db_session)

        # Add inactive custom pattern
        custom = ShellSecurityPattern(
            tenant_id=test_tenant_id,
            pattern=r"safe-command",
            pattern_type="blocked",
            description="This pattern is inactive",
            is_system_default=False,
            is_active=False  # Inactive
        )
        db_session.add(custom)
        db_session.commit()

        security_service.invalidate_cache(test_tenant_id)

        # Command should NOT be blocked (pattern is inactive)
        result = security_service.check_command(
            "safe-command --flag",
            tenant_id=test_tenant_id,
            db=db_session
        )

        assert result.allowed is True


class TestPatternValidation:
    """Tests for regex pattern validation."""

    def test_valid_patterns(self):
        """Test that valid regex patterns compile."""
        valid_patterns = [
            r"rm\s+-rf",
            r"^/bin/bash",
            r"chmod\s+777",
            r"(wget|curl).*\|\s*sh",
            r"DROP\s+(DATABASE|TABLE)",
        ]
        for pattern in valid_patterns:
            # Should not raise
            compiled = re.compile(pattern)
            assert compiled is not None

    def test_invalid_patterns(self):
        """Test that invalid regex patterns raise error."""
        invalid_patterns = [
            r"[unclosed",
            r"*invalid",
            r"(?P<dup>a)(?P<dup>b)",
        ]
        for pattern in invalid_patterns:
            with pytest.raises(re.error):
                re.compile(pattern)

    def test_blocked_patterns_are_valid(self):
        """Test all hardcoded BLOCKED_PATTERNS are valid regex."""
        for pattern, _ in BLOCKED_PATTERNS:
            compiled = re.compile(pattern)
            assert compiled is not None

    def test_high_risk_patterns_are_valid(self):
        """Test all hardcoded HIGH_RISK_PATTERNS are valid regex."""
        for pattern, _, _ in HIGH_RISK_PATTERNS:
            compiled = re.compile(pattern)
            assert compiled is not None


class TestSecurityCheckResult:
    """Tests for SecurityCheckResult dataclass."""

    def test_blocked_result(self):
        """Test creating a blocked result."""
        result = SecurityCheckResult(
            allowed=False,
            risk_level=RiskLevel.CRITICAL,
            requires_approval=False,
            blocked_reason="Fork bomb detected"
        )

        assert result.allowed is False
        assert result.risk_level == RiskLevel.CRITICAL
        assert result.blocked_reason == "Fork bomb detected"

    def test_approval_required_result(self):
        """Test creating a result that requires approval."""
        result = SecurityCheckResult(
            allowed=True,
            risk_level=RiskLevel.HIGH,
            requires_approval=True,
            matched_patterns=["chmod 777"],
            warnings=["Insecure permissions"]
        )

        assert result.allowed is True
        assert result.requires_approval is True
        assert len(result.matched_patterns) == 1
        assert len(result.warnings) == 1


class TestRiskLevelComparison:
    """Tests for RiskLevel enum comparison."""

    def test_risk_level_ordering(self):
        """Test risk level comparison operators."""
        assert RiskLevel.LOW < RiskLevel.MEDIUM
        assert RiskLevel.MEDIUM < RiskLevel.HIGH
        assert RiskLevel.HIGH < RiskLevel.CRITICAL

        assert RiskLevel.CRITICAL > RiskLevel.HIGH
        assert RiskLevel.HIGH > RiskLevel.MEDIUM
        assert RiskLevel.MEDIUM > RiskLevel.LOW

        assert RiskLevel.HIGH >= RiskLevel.HIGH
        assert RiskLevel.HIGH <= RiskLevel.HIGH

    def test_risk_level_severity(self):
        """Test risk level severity values."""
        assert RiskLevel.LOW.severity == 1
        assert RiskLevel.MEDIUM.severity == 2
        assert RiskLevel.HIGH.severity == 3
        assert RiskLevel.CRITICAL.severity == 4
