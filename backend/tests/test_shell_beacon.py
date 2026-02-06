"""
Tests for Shell Beacon Client (Phase 18 - Phase 2)

Tests cover:
- Configuration loading (YAML, CLI, environment variables)
- Command executor (stacked execution, cd tracking)
- Beacon HTTP polling
- Result reporting
"""

import os
import sys
import json
import tempfile
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

# Add shell_beacon to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shell_beacon.config import (
    BeaconConfig,
    ServerConfig,
    ConnectionConfig,
    ExecutionConfig,
    LoggingConfig,
    UpdateConfig,
    load_config,
    create_argument_parser,
    generate_sample_config
)
from shell_beacon.executor import (
    CommandExecutor,
    CommandResult,
    StackedResult,
    get_os_info
)


# ============================================================================
# Configuration Tests
# ============================================================================

class TestBeaconConfig:
    """Tests for BeaconConfig class."""

    def test_default_config(self):
        """Test default configuration values."""
        config = BeaconConfig()

        assert config.server.url == "http://localhost:8000/api/shell"
        assert config.server.api_key == ""
        assert config.connection.poll_interval == 5
        assert config.connection.reconnect_delay == 5
        assert config.execution.timeout == 300
        assert config.logging.level == "INFO"
        assert config.update.enabled == True

    def test_config_from_yaml(self):
        """Test loading configuration from YAML file."""
        yaml_content = """
server:
  url: "https://test.example.com/api/shell"
  api_key: "shb_test_key"
connection:
  poll_interval: 10
  reconnect_delay: 15
execution:
  shell: "/bin/zsh"
  timeout: 600
logging:
  level: "DEBUG"
  file: "/tmp/test.log"
update:
  enabled: false
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write(yaml_content)
            f.flush()

            try:
                config = BeaconConfig.from_yaml(Path(f.name))

                assert config.server.url == "https://test.example.com/api/shell"
                assert config.server.api_key == "shb_test_key"
                assert config.connection.poll_interval == 10
                assert config.connection.reconnect_delay == 15
                assert config.execution.shell == "/bin/zsh"
                assert config.execution.timeout == 600
                assert config.logging.level == "DEBUG"
                assert config.logging.file == "/tmp/test.log"
                assert config.update.enabled == False
            finally:
                os.unlink(f.name)

    def test_config_env_vars(self):
        """Test environment variable overrides."""
        config = BeaconConfig()

        with patch.dict(os.environ, {
            'TSUSHIN_SERVER_URL': 'https://env.example.com/api/shell',
            'TSUSHIN_API_KEY': 'shb_env_key',
            'TSUSHIN_POLL_INTERVAL': '20',
            'TSUSHIN_LOG_LEVEL': 'WARNING'
        }):
            config.apply_env_vars()

        assert config.server.url == "https://env.example.com/api/shell"
        assert config.server.api_key == "shb_env_key"
        assert config.connection.poll_interval == 20
        assert config.logging.level == "WARNING"

    def test_config_cli_args(self):
        """Test CLI argument overrides."""
        config = BeaconConfig()

        # Mock argparse namespace
        args = Mock()
        args.server = "https://cli.example.com/api/shell"
        args.api_key = "shb_cli_key"
        args.poll_interval = 30
        args.shell = "/bin/bash"
        args.timeout = 120
        args.working_dir = None
        args.log_level = "ERROR"
        args.log_file = None
        args.no_auto_update = True

        config.apply_cli_args(args)

        assert config.server.url == "https://cli.example.com/api/shell"
        assert config.server.api_key == "shb_cli_key"
        assert config.connection.poll_interval == 30
        assert config.execution.shell == "/bin/bash"
        assert config.execution.timeout == 120
        assert config.logging.level == "ERROR"
        assert config.update.enabled == False

    def test_config_validation_missing_api_key(self):
        """Test validation fails without API key."""
        config = BeaconConfig()
        config.server.api_key = ""

        errors = config.validate()

        assert len(errors) > 0
        assert any("API key" in e for e in errors)

    def test_config_validation_success(self):
        """Test validation passes with valid config."""
        config = BeaconConfig()
        config.server.api_key = "shb_valid_key"
        config.server.url = "https://test.com/api/shell"

        errors = config.validate()

        assert len(errors) == 0

    def test_config_to_dict_redacts_api_key(self):
        """Test API key is partially redacted in dict output."""
        config = BeaconConfig()
        config.server.api_key = "shb_this_is_a_secret_key"

        result = config.to_dict()

        assert "shb_this_i..." in result["server"]["api_key"]
        assert "secret_key" not in result["server"]["api_key"]

    def test_generate_sample_config(self):
        """Test sample config generation."""
        sample = generate_sample_config()

        assert "server:" in sample
        assert "api_key:" in sample
        assert "poll_interval:" in sample
        assert "execution:" in sample
        assert "logging:" in sample


class TestArgumentParser:
    """Tests for CLI argument parser."""

    def test_parser_creation(self):
        """Test argument parser is created correctly."""
        parser = create_argument_parser()

        assert parser.prog == "tsushin-beacon"

    def test_parser_server_args(self):
        """Test server argument parsing."""
        parser = create_argument_parser()
        args = parser.parse_args([
            "--server", "https://test.com/api/shell",
            "--api-key", "shb_test"
        ])

        assert args.server == "https://test.com/api/shell"
        assert args.api_key == "shb_test"

    def test_parser_connection_args(self):
        """Test connection argument parsing."""
        parser = create_argument_parser()
        args = parser.parse_args(["--poll-interval", "15"])

        assert args.poll_interval == 15

    def test_parser_version_flag(self):
        """Test version flag."""
        parser = create_argument_parser()
        args = parser.parse_args(["--version"])

        assert args.version == True

    def test_parser_dump_config_flag(self):
        """Test dump-config flag."""
        parser = create_argument_parser()
        args = parser.parse_args(["--dump-config"])

        assert args.dump_config == True


# ============================================================================
# Executor Tests
# ============================================================================

class TestCommandExecutor:
    """Tests for CommandExecutor class."""

    def test_executor_initialization(self):
        """Test executor initializes correctly."""
        executor = CommandExecutor(
            shell="/bin/bash",
            timeout=60,
            initial_working_dir="/tmp"
        )

        assert executor.shell == "/bin/bash"
        assert executor.timeout == 60
        assert "/tmp" in executor.working_dir

    def test_simple_command_execution(self):
        """Test executing a simple command."""
        executor = CommandExecutor()

        result = executor.run("echo 'hello world'")

        assert result.exit_code == 0
        assert "hello world" in result.stdout
        assert result.execution_time_ms >= 0

    def test_command_with_error(self):
        """Test command that fails."""
        executor = CommandExecutor()

        result = executor.run("exit 1")

        assert result.exit_code == 1

    def test_cd_command_changes_working_dir(self):
        """Test cd command updates working directory."""
        executor = CommandExecutor()
        original_dir = executor.working_dir

        result = executor.run("cd /tmp")

        assert result.exit_code == 0
        assert result.is_cd_command == True
        assert executor.working_dir == "/tmp" or "tmp" in executor.working_dir.lower()
        assert result.new_working_dir is not None

    def test_cd_to_home(self):
        """Test cd without arguments goes to home."""
        executor = CommandExecutor(initial_working_dir="/tmp")

        result = executor.run("cd")

        assert result.exit_code == 0
        assert result.is_cd_command == True
        # Should go to home directory
        assert executor.working_dir == os.path.expanduser("~")

    def test_cd_with_tilde(self):
        """Test cd with ~ path expansion."""
        executor = CommandExecutor(initial_working_dir="/tmp")

        result = executor.run("cd ~")

        assert result.exit_code == 0
        assert executor.working_dir == os.path.expanduser("~")

    def test_cd_to_nonexistent_dir_fails(self):
        """Test cd to nonexistent directory fails."""
        executor = CommandExecutor()
        original_dir = executor.working_dir

        result = executor.run("cd /nonexistent/path/that/does/not/exist")

        assert result.exit_code == 1
        assert result.is_cd_command == True
        assert "No such file or directory" in result.stderr or "does not exist" in result.error_message
        # Working dir should not change
        assert executor.working_dir == original_dir

    def test_stacked_execution(self):
        """Test executing multiple commands in sequence."""
        executor = CommandExecutor(initial_working_dir="/tmp")

        result = executor.run_stacked([
            "echo 'first'",
            "echo 'second'",
            "echo 'third'"
        ])

        assert result.final_exit_code == 0
        assert len(result.results) == 3
        assert "first" in result.aggregated_stdout
        assert "second" in result.aggregated_stdout
        assert "third" in result.aggregated_stdout

    def test_stacked_execution_with_cd(self):
        """Test stacked execution with cd commands."""
        executor = CommandExecutor()

        result = executor.run_stacked([
            "cd /tmp",
            "pwd"
        ])

        assert result.final_exit_code == 0
        assert "/tmp" in result.aggregated_stdout or "tmp" in result.aggregated_stdout.lower()
        assert result.final_working_dir == "/tmp" or "tmp" in result.final_working_dir.lower()

    def test_stacked_execution_stops_on_error(self):
        """Test stacked execution stops on first error."""
        executor = CommandExecutor()

        result = executor.run_stacked([
            "echo 'before'",
            "exit 1",
            "echo 'after'"  # Should not run
        ], stop_on_error=True)

        assert result.final_exit_code == 1
        assert len(result.results) == 2  # Only 2 commands ran
        assert "before" in result.aggregated_stdout
        assert "after" not in result.aggregated_stdout
        assert result.failed_at_command == 1

    def test_stacked_execution_continues_on_error(self):
        """Test stacked execution continues when stop_on_error=False."""
        executor = CommandExecutor()

        result = executor.run_stacked([
            "echo 'before'",
            "exit 1",
            "echo 'after'"
        ], stop_on_error=False)

        assert len(result.results) == 3  # All 3 commands ran
        assert "before" in result.aggregated_stdout
        assert "after" in result.aggregated_stdout

    def test_command_timeout(self):
        """Test command times out."""
        executor = CommandExecutor(timeout=1)

        result = executor.run("sleep 10", timeout=1)

        assert result.exit_code == 124  # Timeout exit code
        assert "timeout" in result.error_message.lower() or "timed out" in result.stderr.lower()

    def test_empty_command_skipped(self):
        """Test empty command is skipped."""
        executor = CommandExecutor()

        result = executor.run("")

        assert result.exit_code == 0
        assert result.execution_time_ms == 0

    def test_comment_command_skipped(self):
        """Test comment command is skipped."""
        executor = CommandExecutor()

        result = executor.run("# this is a comment")

        assert result.exit_code == 0

    def test_stacked_result_to_dict(self):
        """Test StackedResult.to_dict() method."""
        executor = CommandExecutor()

        result = executor.run_stacked(["echo 'test'"])
        result_dict = result.to_dict()

        assert "exit_code" in result_dict
        assert "stdout" in result_dict
        assert "stderr" in result_dict
        assert "full_result_json" in result_dict
        assert isinstance(result_dict["full_result_json"], list)

    def test_reset_working_dir(self):
        """Test resetting working directory."""
        executor = CommandExecutor()
        executor.run("cd /tmp")

        executor.reset_working_dir()

        assert executor.working_dir == os.getcwd()


class TestOsInfo:
    """Tests for OS info gathering."""

    def test_get_os_info(self):
        """Test OS info is gathered correctly."""
        info = get_os_info()

        assert "hostname" in info
        assert "system" in info
        assert "release" in info
        assert "machine" in info
        assert "python_version" in info

        # Verify values are strings
        for key, value in info.items():
            assert isinstance(value, str)


# ============================================================================
# Beacon HTTP Tests (with mocked requests)
# ============================================================================

class TestBeaconHTTP:
    """Tests for Beacon HTTP operations."""

    @pytest.fixture
    def mock_config(self):
        """Create a mock configuration."""
        config = BeaconConfig()
        config.server.url = "https://test.example.com/api/shell"
        config.server.api_key = "shb_test_key"
        config.connection.poll_interval = 5
        return config

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_initialization(self, mock_session_class, mock_config):
        """Test beacon initializes correctly."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)

        assert beacon.config == mock_config
        assert beacon._running == False
        assert beacon._registered == False

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_registration_success(self, mock_session_class, mock_config):
        """Test successful beacon registration."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "registered",
            "integration_id": 123,
            "poll_interval": 10
        }
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)
        result = beacon._register()

        assert result == True
        assert beacon._registered == True
        assert beacon._integration_id == 123
        assert beacon.config.connection.poll_interval == 10

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_registration_invalid_key(self, mock_session_class, mock_config):
        """Test registration with invalid API key."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)
        result = beacon._register()

        assert result == False
        assert beacon._registered == False

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_checkin_returns_commands(self, mock_session_class, mock_config):
        """Test check-in returns pending commands."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "ok",
            "poll_interval": 5,
            "pending_commands": [
                {"id": "cmd-1", "commands": ["echo 'test'"], "timeout": 60}
            ]
        }
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)
        pending = beacon._checkin()

        assert pending is not None
        assert len(pending) == 1
        assert pending[0]["id"] == "cmd-1"

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_result_reporting(self, mock_session_class, mock_config):
        """Test reporting command results."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_session.request.return_value = mock_response
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)
        result = beacon._report_result("cmd-1", {
            "exit_code": 0,
            "stdout": "test output",
            "stderr": "",
            "execution_time_ms": 100
        })

        assert result == True

    @patch('shell_beacon.beacon.requests.Session')
    def test_beacon_graceful_stop(self, mock_session_class, mock_config):
        """Test graceful shutdown."""
        from shell_beacon.beacon import Beacon

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        beacon = Beacon(mock_config)
        beacon._running = True

        beacon.stop()

        assert beacon._shutdown_requested == True


# ============================================================================
# Integration Tests (requires running backend)
# ============================================================================

@pytest.mark.integration
class TestBeaconIntegration:
    """
    Integration tests that require a running backend.

    Run with: pytest tests/test_shell_beacon.py -v -m integration
    """

    def test_full_polling_cycle(self):
        """Test a full register -> checkin -> execute -> report cycle."""
        # This test requires a running backend
        # Skip if not in integration mode
        pytest.skip("Integration test - requires running backend")
