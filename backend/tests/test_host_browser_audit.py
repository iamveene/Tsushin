"""
Unit tests for Host Browser Audit Service (Phase 8)

Tests cover:
- Audit log creation
- URL sanitization
- Result updates
- Query methods
- Action types

Run: pytest backend/tests/test_host_browser_audit.py -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch


class TestHostBrowserAuditServiceInstantiation:
    """Tests for service instantiation."""

    def test_service_instantiation(self):
        """Test creating service instance."""
        from services.host_browser_audit_service import HostBrowserAuditService

        mock_db = MagicMock()
        service = HostBrowserAuditService(mock_db)

        assert service.db == mock_db

    def test_audit_actions_constants(self):
        """Test audit action type constants."""
        from services.host_browser_audit_service import HostBrowserAuditActions

        assert HostBrowserAuditActions.NAVIGATE == "navigate"
        assert HostBrowserAuditActions.CLICK == "click"
        assert HostBrowserAuditActions.FILL == "fill"
        assert HostBrowserAuditActions.EXTRACT == "extract"
        assert HostBrowserAuditActions.SCREENSHOT == "screenshot"
        assert HostBrowserAuditActions.EXECUTE_SCRIPT == "execute_script"

    def test_security_action_constants(self):
        """Test security-related action constants."""
        from services.host_browser_audit_service import HostBrowserAuditActions

        assert HostBrowserAuditActions.SENSITIVE_DOMAIN_BLOCKED == "sensitive_domain_blocked"
        assert HostBrowserAuditActions.UNAUTHORIZED_ACCESS_ATTEMPT == "unauthorized_access_attempt"
        assert HostBrowserAuditActions.SESSION_STARTED == "session_started"
        assert HostBrowserAuditActions.SESSION_ENDED == "session_ended"


class TestHostBrowserAuditServiceURLSanitization:
    """Tests for URL sanitization."""

    @pytest.fixture
    def service(self):
        """Create service instance for testing."""
        from services.host_browser_audit_service import HostBrowserAuditService

        mock_db = MagicMock()
        return HostBrowserAuditService(mock_db)

    def test_sanitize_url_removes_token_param(self, service):
        """Test that token query parameter is redacted."""
        url = "https://example.com/api?token=secret123&page=1"
        sanitized = service._sanitize_url(url)

        assert "secret123" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "page=1" in sanitized

    def test_sanitize_url_removes_api_key_param(self, service):
        """Test that api_key query parameter is redacted."""
        url = "https://example.com?api_key=supersecret&data=public"
        sanitized = service._sanitize_url(url)

        assert "supersecret" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "data=public" in sanitized

    def test_sanitize_url_removes_password_param(self, service):
        """Test that password query parameter is redacted."""
        url = "https://example.com/login?username=user&password=mypassword"
        sanitized = service._sanitize_url(url)

        assert "mypassword" not in sanitized
        assert "[REDACTED]" in sanitized
        assert "username=user" in sanitized

    def test_sanitize_url_removes_multiple_sensitive_params(self, service):
        """Test that multiple sensitive parameters are redacted."""
        url = "https://example.com?token=abc&secret=def&auth=ghi&normal=ok"
        sanitized = service._sanitize_url(url)

        assert "abc" not in sanitized
        assert "def" not in sanitized
        assert "ghi" not in sanitized
        assert "normal=ok" in sanitized
        assert sanitized.count("[REDACTED]") == 3

    def test_sanitize_url_preserves_normal_params(self, service):
        """Test that normal parameters are preserved."""
        url = "https://example.com/search?q=hello&page=2&limit=10"
        sanitized = service._sanitize_url(url)

        assert sanitized == url  # No changes

    def test_sanitize_url_handles_none(self, service):
        """Test that None URL returns None."""
        assert service._sanitize_url(None) is None

    def test_sanitize_url_handles_empty_string(self, service):
        """Test that empty URL returns None."""
        assert service._sanitize_url("") is None

    def test_sanitize_url_handles_malformed_url(self, service):
        """Test that malformed URL is handled gracefully."""
        # Should not crash, returns something safe
        result = service._sanitize_url("not a valid url at all!!!")
        assert result is not None


class TestHostBrowserAuditServiceLogAction:
    """Tests for log_action method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance for testing."""
        from services.host_browser_audit_service import HostBrowserAuditService

        return HostBrowserAuditService(mock_db)

    def test_log_action_creates_entry(self, service, mock_db):
        """Test that log_action creates audit log entry."""
        entry = service.log_action(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="navigate",
            mcp_tool="browser_navigate",
            url="https://example.com",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    def test_log_action_with_all_params(self, service, mock_db):
        """Test log_action with all parameters."""
        entry = service.log_action(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="click",
            mcp_tool="browser_click",
            url="https://example.com/page",
            target_element="button.submit",
            params={"ref": "button.submit", "force": True},
            session_id="session-123",
            ip_address="192.168.1.1",
            agent_id=5,
        )

        # Verify entry was created
        mock_db.add.assert_called_once()
        added_entry = mock_db.add.call_args[0][0]

        assert added_entry.tenant_id == "tenant-1"
        assert added_entry.user_key == "+5511999999999"
        assert added_entry.action == "click"
        assert added_entry.mcp_tool == "browser_click"
        assert added_entry.agent_id == 5

    def test_log_action_sanitizes_url(self, service, mock_db):
        """Test that URL is sanitized in log entry."""
        entry = service.log_action(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="navigate",
            mcp_tool="browser_navigate",
            url="https://example.com?token=secret123",
        )

        added_entry = mock_db.add.call_args[0][0]
        assert "secret123" not in added_entry.url
        assert "[REDACTED]" in added_entry.url

    def test_log_action_hashes_params(self, service, mock_db):
        """Test that params are hashed for privacy."""
        entry = service.log_action(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="fill",
            mcp_tool="browser_type",
            params={"text": "sensitive_password"},
        )

        added_entry = mock_db.add.call_args[0][0]

        # Should have hash but not actual value
        assert added_entry.mcp_params_hash is not None
        assert len(added_entry.mcp_params_hash) == 64  # SHA256 hex

    def test_log_action_sets_success_false(self, service, mock_db):
        """Test that initial success is False (before execution)."""
        entry = service.log_action(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="navigate",
            mcp_tool="browser_navigate",
        )

        added_entry = mock_db.add.call_args[0][0]
        assert added_entry.success is False


class TestHostBrowserAuditServiceUpdateResult:
    """Tests for update_result method."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        db = MagicMock()
        db.commit = MagicMock()
        db.refresh = MagicMock()
        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance for testing."""
        from services.host_browser_audit_service import HostBrowserAuditService

        return HostBrowserAuditService(mock_db)

    def test_update_result_success(self, service, mock_db):
        """Test updating result with success."""
        mock_entry = MagicMock()
        mock_entry.success = False

        updated = service.update_result(
            log_entry=mock_entry,
            success=True,
            duration_ms=150,
        )

        assert mock_entry.success is True
        assert mock_entry.duration_ms == 150
        assert mock_entry.error_message is None
        mock_db.commit.assert_called_once()

    def test_update_result_failure(self, service, mock_db):
        """Test updating result with failure."""
        mock_entry = MagicMock()
        mock_entry.success = False

        updated = service.update_result(
            log_entry=mock_entry,
            success=False,
            duration_ms=5000,
            error_message="Timeout waiting for element",
        )

        assert mock_entry.success is False
        assert mock_entry.duration_ms == 5000
        assert mock_entry.error_message == "Timeout waiting for element"


class TestHostBrowserAuditServiceQueries:
    """Tests for query methods."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        from models import HostBrowserAuditLog

        db = MagicMock()

        # Create mock query chain
        mock_query = MagicMock()
        mock_query.filter = MagicMock(return_value=mock_query)
        mock_query.order_by = MagicMock(return_value=mock_query)
        mock_query.offset = MagicMock(return_value=mock_query)
        mock_query.limit = MagicMock(return_value=mock_query)
        mock_query.all = MagicMock(return_value=[])
        mock_query.count = MagicMock(return_value=0)

        db.query = MagicMock(return_value=mock_query)

        return db

    @pytest.fixture
    def service(self, mock_db):
        """Create service instance for testing."""
        from services.host_browser_audit_service import HostBrowserAuditService

        return HostBrowserAuditService(mock_db)

    def test_get_logs_no_filters(self, service, mock_db):
        """Test get_logs without filters."""
        logs = service.get_logs()

        mock_db.query.assert_called_once()

    def test_get_logs_with_tenant_filter(self, service, mock_db):
        """Test get_logs with tenant filter."""
        logs = service.get_logs(tenant_id="tenant-1")

        mock_query = mock_db.query.return_value
        mock_query.filter.assert_called()

    def test_get_logs_with_multiple_filters(self, service, mock_db):
        """Test get_logs with multiple filters."""
        logs = service.get_logs(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="navigate",
            success=True,
        )

        mock_query = mock_db.query.return_value
        # Filter should be called multiple times
        assert mock_query.filter.call_count >= 1

    def test_get_logs_with_pagination(self, service, mock_db):
        """Test get_logs with pagination."""
        logs = service.get_logs(limit=50, offset=100)

        mock_query = mock_db.query.return_value
        mock_query.offset.assert_called_with(100)
        mock_query.limit.assert_called_with(50)

    def test_get_logs_with_date_range(self, service, mock_db):
        """Test get_logs with date range filter."""
        from_date = datetime.utcnow() - timedelta(days=7)
        to_date = datetime.utcnow()

        logs = service.get_logs(from_date=from_date, to_date=to_date)

        mock_query = mock_db.query.return_value
        # Should have two date filter calls
        assert mock_query.filter.call_count >= 1

    def test_get_log_count(self, service, mock_db):
        """Test get_log_count method."""
        count = service.get_log_count(tenant_id="tenant-1")

        mock_query = mock_db.query.return_value
        mock_query.count.assert_called_once()

    def test_get_recent_logs_for_user(self, service, mock_db):
        """Test get_recent_logs_for_user helper method."""
        logs = service.get_recent_logs_for_user(
            tenant_id="tenant-1",
            user_key="+5511999999999",
            limit=5,
        )

        mock_query = mock_db.query.return_value
        mock_query.limit.assert_called()

    def test_get_failed_actions(self, service, mock_db):
        """Test get_failed_actions helper method."""
        logs = service.get_failed_actions(tenant_id="tenant-1", limit=20)

        mock_query = mock_db.query.return_value
        # Should filter by success=False
        mock_query.filter.assert_called()


class TestHostBrowserAuditServiceConvenienceFunction:
    """Tests for log_host_browser_action convenience function."""

    def test_convenience_function(self):
        """Test the convenience function creates service and logs action."""
        from services.host_browser_audit_service import log_host_browser_action

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        entry = log_host_browser_action(
            db=mock_db,
            tenant_id="tenant-1",
            user_key="+5511999999999",
            action="navigate",
            mcp_tool="browser_navigate",
            url="https://example.com",
        )

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


class TestHostBrowserAuditLogModel:
    """Tests for HostBrowserAuditLog model."""

    def test_model_exists(self):
        """Test that HostBrowserAuditLog model exists."""
        from models import HostBrowserAuditLog

        assert HostBrowserAuditLog is not None
        assert HostBrowserAuditLog.__tablename__ == "host_browser_audit_log"

    def test_model_columns(self):
        """Test model has expected columns."""
        from models import HostBrowserAuditLog

        # Check columns exist
        columns = [c.name for c in HostBrowserAuditLog.__table__.columns]

        assert "id" in columns
        assert "timestamp" in columns
        assert "tenant_id" in columns
        assert "user_key" in columns
        assert "agent_id" in columns
        assert "action" in columns
        assert "url" in columns
        assert "target_element" in columns
        assert "mcp_tool" in columns
        assert "mcp_params_hash" in columns
        assert "success" in columns
        assert "error_message" in columns
        assert "duration_ms" in columns
        assert "session_id" in columns

    def test_model_indexes(self):
        """Test model has expected indexes."""
        from models import HostBrowserAuditLog

        indexes = [idx.name for idx in HostBrowserAuditLog.__table__.indexes]

        assert "idx_host_browser_audit_timestamp" in indexes
        assert "idx_host_browser_audit_tenant" in indexes
        assert "idx_host_browser_audit_user" in indexes
        assert "idx_host_browser_audit_action" in indexes
