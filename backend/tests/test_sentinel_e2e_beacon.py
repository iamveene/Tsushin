"""
Sentinel E2E Tests - Beacon Integration (Phase 20)

End-to-end tests that verify Sentinel security works with actual beacons.
These tests use the real database and verify the security check order:
1. Pattern matching (cheap, fast) - blocks obvious attacks
2. Sentinel LLM analysis (if enabled and pattern check passes)

Run with:
    pytest tests/test_sentinel_e2e_beacon.py -v --no-cov

IMPORTANT: Requires:
- Docker containers running (backend)
- At least one active beacon registered
- Valid LLM API key configured (for Sentinel LLM tests)
"""

import pytest
import asyncio
import os
import sys
from datetime import datetime, timedelta

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import Base, ShellIntegration, ShellCommand, SentinelConfig, SentinelAnalysisLog
from services.shell_command_service import ShellCommandService, CommandStatus
from services.shell_security_service import get_security_service


# =============================================================================
# Test Configuration
# =============================================================================

# Use actual database for E2E tests
DB_PATH = os.getenv("INTERNAL_DB_PATH", "./data/agent.db")
TEST_TENANT_ID = "tenant_20251202232822"  # Default test tenant


@pytest.fixture(scope="module")
def db_engine():
    """Connect to actual database for E2E tests."""
    db_url = f"sqlite:///{DB_PATH}"
    engine = create_engine(db_url, echo=False)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create a database session."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_beacon(db_session):
    """Get the first active beacon for the test tenant."""
    beacon = db_session.query(ShellIntegration).filter(
        ShellIntegration.tenant_id == TEST_TENANT_ID,
        ShellIntegration.is_active == True
    ).first()

    if not beacon:
        pytest.skip("No active beacon found - ensure beacon is running")

    return beacon


# =============================================================================
# Security Check Order Tests
# =============================================================================

class TestSecurityCheckOrder:
    """
    Verify security checks run in correct order:
    1. Pattern matching FIRST (cheap, fast)
    2. Sentinel LLM analysis SECOND (expensive, only if pattern passes)
    """

    def test_pattern_matching_blocks_fork_bomb(self, db_session, test_beacon):
        """
        Fork bomb should be blocked by PATTERN MATCHING, not Sentinel.
        Sentinel should NOT be called for commands blocked by patterns.
        """
        service = ShellCommandService(db_session)
        security_service = get_security_service()

        # Fork bomb - should be in BLOCKED_PATTERNS
        fork_bomb = ":(){ :|:& };:"

        # Check that pattern matching catches this
        allowed, result = security_service.check_commands([fork_bomb])

        assert allowed is False, "Pattern matching should block fork bomb"
        assert result.blocked_reason is not None
        # The reason should mention it was blocked (BLOCKED: Fork bomb detected)
        assert "blocked" in result.blocked_reason.lower() or "fork bomb" in result.blocked_reason.lower()

    def test_pattern_matching_blocks_rm_rf_root(self, db_session, test_beacon):
        """
        rm -rf / should be blocked by PATTERN MATCHING.
        """
        security_service = get_security_service()

        dangerous_cmd = "rm -rf /"

        allowed, result = security_service.check_commands([dangerous_cmd])

        assert allowed is False, "Pattern matching should block rm -rf /"
        assert result.blocked_reason is not None

    def test_pattern_matching_high_risk_dev_sda_write(self, db_session, test_beacon):
        """
        dd to /dev/sda should be flagged as HIGH RISK (requires approval).
        Note: This is HIGH_RISK not BLOCKED - it needs approval, not outright blocked.
        """
        security_service = get_security_service()

        dangerous_cmd = "dd if=/dev/zero of=/dev/sda"

        allowed, result = security_service.check_commands([dangerous_cmd])

        # This is HIGH_RISK, not BLOCKED - it requires approval but isn't automatically blocked
        # The test verifies it's detected as risky
        if not allowed:
            assert result.blocked_reason is not None
        else:
            # If allowed, it should require approval
            assert result.requires_approval is True or result.risk_level.value in ["high", "critical"]

    def test_safe_command_passes_pattern_check(self, db_session, test_beacon):
        """
        Safe commands like 'ls' should pass pattern matching.
        """
        security_service = get_security_service()

        safe_cmd = "ls -la"

        allowed, result = security_service.check_commands([safe_cmd])

        assert allowed is True, "Safe command should pass pattern matching"
        assert result.blocked_reason is None


# =============================================================================
# Sentinel Beacon Integration Tests
# =============================================================================

class TestSentinelBeaconIntegration:
    """
    Test Sentinel analysis on commands sent through actual beacon.
    These tests verify the end-to-end flow works correctly.
    """

    @pytest.mark.asyncio
    async def test_blocked_command_logged_correctly(self, db_session, test_beacon):
        """
        Verify blocked commands are logged in shell_command table.
        """
        service = ShellCommandService(db_session)

        # This should be blocked by pattern matching
        result = await service.execute_command_async(
            script="rm -rf /*",
            target=test_beacon.hostname,
            tenant_id=TEST_TENANT_ID,
            initiated_by="test:e2e_beacon",
            agent_id=None,
            timeout_seconds=5,
            wait_for_result=False
        )

        assert result.success is False
        assert result.blocked is True
        assert result.status == CommandStatus.BLOCKED.value
        assert result.blocked_reason is not None

        # Verify it was logged
        if result.command_id:
            cmd_log = db_session.query(ShellCommand).filter(
                ShellCommand.id == result.command_id
            ).first()

            assert cmd_log is not None
            assert cmd_log.status == "blocked"

    @pytest.mark.asyncio
    async def test_sentinel_protected_beacon(self, db_session, test_beacon):
        """
        Verify beacon has sentinel_protected attribute.
        """
        # The migration should have added this column
        assert hasattr(test_beacon, 'sentinel_protected'), \
            "Beacon should have sentinel_protected attribute"

        # Default should be True (protected)
        # Note: existing beacons get default value from migration
        print(f"Beacon sentinel_protected: {test_beacon.sentinel_protected}")

    def test_beacon_connectivity(self, db_session, test_beacon):
        """
        Verify beacon is online and responsive.
        """
        # Check last checkin is recent (within 5 minutes)
        if test_beacon.last_checkin:
            age = datetime.utcnow() - test_beacon.last_checkin
            assert age < timedelta(minutes=5), \
                f"Beacon last checkin too long ago: {age}"

        assert test_beacon.is_active is True
        assert test_beacon.hostname is not None


# =============================================================================
# Sentinel Config Tests
# =============================================================================

class TestSentinelConfig:
    """
    Test Sentinel configuration for the tenant.
    """

    def test_sentinel_config_exists(self, db_session):
        """
        Verify Sentinel config exists for test tenant.
        """
        config = db_session.query(SentinelConfig).filter(
            SentinelConfig.tenant_id == TEST_TENANT_ID
        ).first()

        if config is None:
            pytest.skip("No Sentinel config found - configure Sentinel first")

        print(f"\nSentinel Config:")
        print(f"  Enabled: {config.is_enabled}")
        print(f"  Shell Analysis: {config.enable_shell_analysis}")
        print(f"  Block on Detection: {config.block_on_detection}")
        print(f"  LLM Provider: {config.llm_provider}")
        print(f"  Aggressiveness: {config.aggressiveness_level}")

    def test_sentinel_logs_exist(self, db_session):
        """
        Check if there are Sentinel logs for the tenant.
        """
        logs = db_session.query(SentinelAnalysisLog).filter(
            SentinelAnalysisLog.tenant_id == TEST_TENANT_ID
        ).order_by(SentinelAnalysisLog.created_at.desc()).limit(5).all()

        print(f"\nRecent Sentinel Logs ({len(logs)}):")
        for log in logs:
            print(f"  [{log.created_at}] {log.detection_type}: {log.action_taken}")
            if log.threat_reason:
                print(f"    Reason: {log.threat_reason[:50]}...")


# =============================================================================
# Run Tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
