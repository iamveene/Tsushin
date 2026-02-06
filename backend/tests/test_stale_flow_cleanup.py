"""
Tests for StaleFlowCleanupService (BUG-FLOWS-002)

Tests the background service that detects and cleans up:
1. Flow runs stuck in "running" state
2. Orphaned step runs
3. Stale conversation threads (flow type only)
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

from flows.stale_flow_cleanup import (
    StaleFlowCleanupService,
    get_stale_flow_cleanup_service,
    start_stale_flow_cleanup,
    stop_stale_flow_cleanup
)


class TestStaleFlowCleanupService:
    """Test suite for StaleFlowCleanupService."""

    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        session = MagicMock()
        session.query.return_value.filter.return_value.all.return_value = []
        session.query.return_value.join.return_value.filter.return_value.all.return_value = []
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create a cleanup service with test configuration."""
        return StaleFlowCleanupService(
            get_db_session=lambda: mock_db_session,
            stale_threshold_seconds=60,  # 1 minute for testing
            check_interval_seconds=10,
            conversation_stale_seconds=30
        )

    def test_service_initialization(self, service):
        """Test service initializes with correct configuration."""
        assert service.stale_threshold == 60
        assert service.check_interval == 10
        assert service.conversation_stale == 30
        assert service._running is False

    def test_default_configuration(self, mock_db_session):
        """Test default configuration values are used when not specified."""
        service = StaleFlowCleanupService(get_db_session=lambda: mock_db_session)
        assert service.stale_threshold == 7200  # 2 hours
        assert service.check_interval == 300    # 5 minutes
        assert service.conversation_stale == 3600  # 1 hour

    @pytest.mark.asyncio
    async def test_cleanup_stale_flow_runs(self, service, mock_db_session):
        """Test that stale flow runs are identified and cleaned up."""
        # Create mock stale flow run
        mock_flow_run = MagicMock()
        mock_flow_run.id = 1
        mock_flow_run.status = "running"
        mock_flow_run.started_at = datetime.utcnow() - timedelta(seconds=120)  # 2 min ago
        mock_flow_run.tenant_id = "test_tenant"
        mock_flow_run.flow_definition_id = 1

        # Mock step runs for this flow
        mock_step_run = MagicMock()
        mock_step_run.id = 10
        mock_step_run.status = "running"

        # Setup query returns
        mock_db_session.query.return_value.filter.return_value.all.side_effect = [
            [mock_flow_run],  # First call for flow runs
            [mock_step_run]   # Second call for step runs
        ]

        # Run cleanup
        cleaned = await service._cleanup_stale_flow_runs(mock_db_session)

        # Verify flow was cleaned up
        assert cleaned == 1
        assert mock_flow_run.status == "timeout"
        assert mock_flow_run.completed_at is not None
        assert "timed out" in mock_flow_run.error_text

        # Verify step was also cleaned up
        assert mock_step_run.status == "timeout"
        assert mock_step_run.completed_at is not None

        # Verify commit was called
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_ignores_recent_flow_runs(self, service, mock_db_session):
        """Test that recently started flows are not cleaned up."""
        # Create mock recent flow run
        mock_flow_run = MagicMock()
        mock_flow_run.id = 1
        mock_flow_run.status = "running"
        mock_flow_run.started_at = datetime.utcnow() - timedelta(seconds=30)  # 30s ago, under threshold

        # Setup query to return empty (filter should exclude recent runs)
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        # Run cleanup
        cleaned = await service._cleanup_stale_flow_runs(mock_db_session)

        # No flows should be cleaned
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_step_runs(self, service, mock_db_session):
        """Test cleanup of step runs whose parent flow is already completed."""
        # Create mock orphaned step run
        mock_step_run = MagicMock()
        mock_step_run.id = 10
        mock_step_run.status = "running"
        mock_step_run.flow_run_id = 1
        mock_step_run.run = MagicMock()
        mock_step_run.run.status = "completed"  # Parent flow is completed

        # Setup query returns
        mock_db_session.query.return_value.join.return_value.filter.return_value.all.return_value = [mock_step_run]

        # Run cleanup
        cleaned = await service._cleanup_stale_step_runs(mock_db_session)

        # Verify step was cleaned up
        assert cleaned == 1
        assert mock_step_run.status == "failed"
        assert mock_step_run.completed_at is not None
        assert "orphaned" in mock_step_run.error_text
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_cleanup_stale_conversation_threads(self, service, mock_db_session):
        """Test cleanup of inactive conversation threads."""
        # Create mock stale thread
        mock_thread = MagicMock()
        mock_thread.id = 100
        mock_thread.status = "active"
        mock_thread.thread_type = "flow"  # Important: must be flow type
        mock_thread.last_activity_at = datetime.utcnow() - timedelta(seconds=60)  # 1 min ago
        mock_thread.flow_step_run_id = 10
        mock_thread.recipient = "+1234567890"

        # Setup query returns
        mock_db_session.query.return_value.filter.return_value.all.return_value = [mock_thread]

        # Run cleanup
        cleaned = await service._cleanup_stale_conversation_threads(mock_db_session)

        # Verify thread was cleaned up
        assert cleaned == 1
        assert mock_thread.status == "timeout"
        assert mock_thread.completed_at is not None
        mock_db_session.commit.assert_called()

    @pytest.mark.asyncio
    async def test_does_not_clean_playground_threads(self, service, mock_db_session):
        """Test that playground threads are NOT cleaned up."""
        # The filter in _cleanup_stale_conversation_threads includes:
        # ConversationThread.thread_type == "flow"
        # So playground threads should never be returned by the query

        # Empty query result means no playground threads will be touched
        mock_db_session.query.return_value.filter.return_value.all.return_value = []

        # Run cleanup
        cleaned = await service._cleanup_stale_conversation_threads(mock_db_session)

        # No threads should be cleaned
        assert cleaned == 0

    @pytest.mark.asyncio
    async def test_start_and_stop(self, service):
        """Test service start and stop lifecycle."""
        # Start service
        await service.start()
        assert service._running is True
        assert service._task is not None

        # Wait briefly for loop to start
        await asyncio.sleep(0.1)

        # Stop service
        await service.stop()
        assert service._running is False

    def test_get_stats(self, service):
        """Test that stats are correctly reported."""
        stats = service.get_stats()

        assert stats["flows_cleaned"] == 0
        assert stats["steps_cleaned"] == 0
        assert stats["threads_cleaned"] == 0
        assert stats["stale_threshold_seconds"] == 60
        assert stats["check_interval_seconds"] == 10
        assert stats["running"] is False

    @pytest.mark.asyncio
    async def test_callback_triggered_on_cleanup(self, mock_db_session):
        """Test that callback is triggered when flow is cleaned up."""
        callback_calls = []

        def on_cleanup(flow_run_id, reason):
            callback_calls.append((flow_run_id, reason))

        service = StaleFlowCleanupService(
            get_db_session=lambda: mock_db_session,
            stale_threshold_seconds=60,
            on_cleanup_triggered=on_cleanup
        )

        # Create mock stale flow run
        mock_flow_run = MagicMock()
        mock_flow_run.id = 42
        mock_flow_run.status = "running"
        mock_flow_run.started_at = datetime.utcnow() - timedelta(seconds=120)
        mock_flow_run.tenant_id = "test"
        mock_flow_run.flow_definition_id = 1

        mock_db_session.query.return_value.filter.return_value.all.side_effect = [
            [mock_flow_run],  # Flow runs
            []  # Step runs
        ]

        # Run cleanup
        await service._cleanup_stale_flow_runs(mock_db_session)

        # Verify callback was called
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 42
        assert "Stale timeout" in callback_calls[0][1]

    @pytest.mark.asyncio
    async def test_handles_db_errors_gracefully(self, service, mock_db_session):
        """Test that database errors don't crash the service."""
        # Setup query to raise an exception
        mock_db_session.query.return_value.filter.return_value.all.side_effect = Exception("DB Error")

        # Run cleanup should not raise
        cleaned = await service._cleanup_stale_flow_runs(mock_db_session)

        # No flows cleaned due to error
        assert cleaned == 0


class TestStaleFlowCleanupIntegration:
    """Integration tests with real database models."""

    @pytest.fixture
    def integration_db(self):
        """Create test database with real models."""
        import tempfile
        import os
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from models import Base

        # Create temporary database
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        engine = create_engine(f'sqlite:///{db_path}')
        Base.metadata.create_all(engine)

        SessionLocal = sessionmaker(bind=engine)
        session = SessionLocal()

        yield session, SessionLocal

        # Cleanup
        session.close()
        os.close(db_fd)
        os.unlink(db_path)

    @pytest.mark.asyncio
    async def test_real_stale_flow_cleanup(self, integration_db):
        """Test cleanup with real database models."""
        session, SessionLocal = integration_db

        from models import FlowDefinition, FlowRun, FlowNode, FlowNodeRun

        # Create flow definition
        flow_def = FlowDefinition(
            id=1,
            name="Test Flow",
            flow_type="workflow",
            tenant_id="test-tenant"
        )
        session.add(flow_def)
        session.commit()

        # Create stale flow run (started 3 hours ago)
        stale_run = FlowRun(
            id=1,
            flow_definition_id=1,
            tenant_id="test-tenant",
            status="running",
            started_at=datetime.utcnow() - timedelta(hours=3),
            total_steps=1
        )
        session.add(stale_run)
        session.commit()

        # Create service with 1 hour threshold
        service = StaleFlowCleanupService(
            get_db_session=SessionLocal,
            stale_threshold_seconds=3600,  # 1 hour
            check_interval_seconds=10
        )

        # Run cleanup
        await service._run_cleanup()

        # Verify flow was cleaned up
        session.refresh(stale_run)
        assert stale_run.status == "timeout"
        assert stale_run.completed_at is not None
        assert "timed out" in stale_run.error_text


class TestModuleHelpers:
    """Test module-level helper functions."""

    @pytest.mark.asyncio
    async def test_start_and_stop_global_service(self):
        """Test global service start/stop functions."""
        mock_session = MagicMock()

        # Start service
        await start_stale_flow_cleanup(
            get_db_session=lambda: mock_session,
            stale_threshold_seconds=60,
            check_interval_seconds=10
        )

        # Get the service and verify it's running
        service = get_stale_flow_cleanup_service(lambda: mock_session)
        assert service._running is True

        # Stop service
        await stop_stale_flow_cleanup()
        assert service._running is False
