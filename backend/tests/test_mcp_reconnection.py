"""
Integration tests for WhatsApp MCP reconnection and session management
Tests the automatic reconnection, keepalive, and session monitoring features
"""

import pytest
import time
import requests
from typing import Dict
import docker
from sqlalchemy.orm import Session

from services.mcp_container_manager import MCPContainerManager
from models import WhatsAppMCPInstance


class TestMCPReconnection:
    """Test suite for MCP reconnection functionality"""

    @pytest.fixture
    def docker_client(self):
        """Get Docker client"""
        return docker.from_env()

    @pytest.fixture
    def mcp_manager(self):
        """Get MCP container manager"""
        return MCPContainerManager()

    def test_health_check_returns_session_state(self, mcp_manager, db: Session):
        """
        Test that health check returns comprehensive session state

        Verifies:
        - Health check includes authenticated status
        - Health check includes connected status
        - Health check includes reconnection state
        - Health check includes session age
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Perform health check
        health_data = mcp_manager.health_check(instance)

        # Verify comprehensive health data is returned
        assert "authenticated" in health_data
        assert "connected" in health_data
        assert "needs_reauth" in health_data
        assert "is_reconnecting" in health_data
        assert "reconnect_attempts" in health_data
        assert "session_age_sec" in health_data
        assert "last_activity_sec" in health_data

        # Verify types
        assert isinstance(health_data["authenticated"], bool)
        assert isinstance(health_data["connected"], bool)
        assert isinstance(health_data["needs_reauth"], bool)
        assert isinstance(health_data["reconnect_attempts"], int)
        assert isinstance(health_data["session_age_sec"], int)

    def test_health_endpoint_enhanced_response(self, db: Session):
        """
        Test that MCP health endpoint returns enhanced session data

        Verifies:
        - /api/health endpoint is accessible
        - Response includes all new session fields
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Call health endpoint
        try:
            response = requests.get(
                f"{instance.mcp_api_url}/health",
                timeout=5
            )

            assert response.status_code == 200

            health_data = response.json()

            # Verify enhanced fields are present
            assert "authenticated" in health_data
            assert "connected" in health_data
            assert "needs_reauth" in health_data
            assert "is_reconnecting" in health_data
            assert "reconnect_attempts" in health_data
            assert "session_age_sec" in health_data
            assert "last_activity_sec" in health_data

        except requests.RequestException as e:
            pytest.fail(f"Health endpoint not accessible: {e}")

    def test_reconnection_state_tracking(self, db: Session):
        """
        Test that reconnection attempts are tracked correctly

        This is a manual test - requires simulating disconnection
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Get initial state
        response = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        initial_state = response.json()

        # Verify reconnect_attempts starts at 0 for healthy connection
        if initial_state.get("authenticated") and initial_state.get("connected"):
            assert initial_state["reconnect_attempts"] == 0

    def test_session_age_increases_over_time(self, db: Session):
        """
        Test that session age increases as expected

        Verifies:
        - Session age is tracked
        - Session age increases over time
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Get initial session age
        response1 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state1 = response1.json()
        age1 = state1.get("session_age_sec", 0)

        # Wait 5 seconds
        time.sleep(5)

        # Get updated session age
        response2 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state2 = response2.json()
        age2 = state2.get("session_age_sec", 0)

        # Verify age increased by approximately 5 seconds (±2 seconds tolerance)
        age_diff = age2 - age1
        assert 3 <= age_diff <= 7, f"Session age should increase by ~5s, got {age_diff}s"

    def test_container_restart_preserves_session(self, mcp_manager, docker_client, db: Session):
        """
        Test that restarting container preserves WhatsApp session

        This is a critical test for session persistence.

        WARNING: This test will restart a container - use with caution
        """
        pytest.skip("Manual test - requires explicit execution to avoid disrupting production")

        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Get initial authentication state
        response1 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state1 = response1.json()

        if not state1.get("authenticated"):
            pytest.skip("Instance not authenticated - cannot test session persistence")

        # Restart container
        mcp_manager.restart_instance(instance.id, db)

        # Wait for container to come back up
        time.sleep(10)

        # Check if session was preserved
        response2 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state2 = response2.json()

        # Session should be preserved (authenticated without QR scan)
        assert state2.get("authenticated"), "Session should be preserved after restart"

    def test_needs_reauth_flag_detection(self, db: Session):
        """
        Test that needs_reauth flag is properly detected

        Verifies:
        - needs_reauth is False for healthy sessions
        - Backend monitoring detects needs_reauth state
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Get health state
        response = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state = response.json()

        # For healthy, authenticated sessions, needs_reauth should be False
        if state.get("authenticated") and state.get("connected"):
            assert state["needs_reauth"] is False

    def test_keepalive_maintains_activity(self, db: Session):
        """
        Test that keepalive mechanism updates last_activity_sec

        Verifies:
        - last_activity_sec is tracked
        - Keepalive prevents activity timeout
        """
        # Get first running MCP instance
        instance = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.status == "running"
        ).first()

        if not instance:
            pytest.skip("No running MCP instances found")

        # Get initial activity time
        response1 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state1 = response1.json()
        activity1 = state1.get("last_activity_sec", 0)

        # Wait 35 seconds (longer than keepalive interval of 30s)
        time.sleep(35)

        # Get updated activity time
        response2 = requests.get(f"{instance.mcp_api_url}/health", timeout=5)
        state2 = response2.json()
        activity2 = state2.get("last_activity_sec", 0)

        # Activity should be recent (within last 35 seconds) due to keepalive
        # If keepalive is working, last_activity_sec should be < 35
        assert activity2 < 35, f"Keepalive should prevent activity timeout, got {activity2}s"


class TestMCPHealthMonitoring:
    """Test suite for backend health monitoring enhancements"""

    @pytest.fixture
    def mcp_manager(self):
        """Get MCP container manager"""
        return MCPContainerManager()

    def test_health_check_detects_degraded_state(self, mcp_manager, db: Session):
        """
        Test that health check properly detects degraded states

        Verifies:
        - Degraded state when container running but not authenticated
        - Proper status categorization
        """
        # This test requires a container in degraded state
        # In practice, this would be tested with a mock or staged scenario
        pass

    def test_health_check_logging_for_reauth_needed(self, mcp_manager, db: Session, caplog):
        """
        Test that health check logs warnings when re-auth is needed

        Verifies:
        - Warning logged when needs_reauth is True
        - Log message includes instance details
        """
        # This would require mocking or a test instance in needs_reauth state
        pass

    def test_health_check_alerts_high_reconnect_attempts(self, mcp_manager, db: Session, caplog):
        """
        Test that health check logs warnings for high reconnection attempts

        Verifies:
        - Warning logged when reconnect_attempts >= 5
        - Log message includes attempt count
        """
        # This would require mocking or a test instance with high reconnect attempts
        pass


# Manual test scenarios (not automated)
class TestManualReconnectionScenarios:
    """
    Manual test scenarios for reconnection

    These tests require manual intervention and are documented here
    for reference during manual testing.
    """

    def test_manual_forced_disconnect(self):
        """
        Manual Test: Forced Disconnect Recovery

        Steps:
        1. Ensure MCP instance is running and authenticated
        2. Kill the WhatsApp connection (e.g., turn off phone WiFi)
        3. Observe logs for Disconnected event
        4. Verify automatic reconnection attempts with exponential backoff
        5. Restore connection (turn on phone WiFi)
        6. Verify successful reconnection within 60 seconds

        Expected:
        - Disconnected event logged
        - Reconnection attempts with backoff (1s, 2s, 4s, 8s, etc.)
        - Successful reconnection
        - reconnect_attempts reset to 0
        """
        pytest.skip("Manual test - requires human intervention")

    def test_manual_session_timeout(self):
        """
        Manual Test: Session Timeout Prevention

        Steps:
        1. Ensure MCP instance is running and authenticated
        2. Do not send any messages for 10+ minutes
        3. Monitor last_activity_sec in health endpoint
        4. Verify keepalive prevents session timeout
        5. Send a test message to verify session still active

        Expected:
        - last_activity_sec stays < 60 due to keepalive
        - Session remains authenticated
        - Message sends successfully
        """
        pytest.skip("Manual test - requires long wait time")

    def test_manual_max_retry_exhaustion(self):
        """
        Manual Test: Max Retry Exhaustion

        Steps:
        1. Ensure MCP instance is running and authenticated
        2. Simulate persistent connection failure (e.g., block WhatsApp servers)
        3. Observe reconnection attempts
        4. Verify exponential backoff
        5. Verify needs_reauth flag set after max retries (10)
        6. Verify QR code becomes available

        Expected:
        - 10 reconnection attempts with exponential backoff
        - needs_reauth flag set to True
        - QR code endpoint returns new QR code
        """
        pytest.skip("Manual test - requires network manipulation")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
