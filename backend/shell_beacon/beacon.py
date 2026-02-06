#!/usr/bin/env python3
"""
Tsushin Shell Beacon - Main Client

HTTP polling beacon client that:
1. Registers with the Tsushin backend
2. Polls for pending commands
3. Executes commands locally
4. Reports results back to the backend

Part of the Shell Skill C2 architecture (Phase 18).
"""

import sys
import time
import signal
import logging
import json
from typing import Optional, Dict, Any
from logging.handlers import RotatingFileHandler
from datetime import datetime
import traceback

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__
from .config import BeaconConfig, load_config, create_argument_parser
from .executor import CommandExecutor, get_os_info

logger = logging.getLogger("tsushin.beacon")


class Beacon:
    """
    Shell Beacon Client

    Implements the beacon polling loop:
    1. Register with server (first run)
    2. Check-in periodically
    3. Execute received commands
    4. Report results
    5. Handle graceful shutdown
    """

    def __init__(self, config: BeaconConfig):
        """
        Initialize the beacon.

        Args:
            config: Beacon configuration
        """
        self.config = config
        self._running = False
        self._shutdown_requested = False
        self._current_reconnect_delay = config.connection.reconnect_delay

        # Initialize executor
        self.executor = CommandExecutor(
            shell=config.execution.shell,
            timeout=config.execution.timeout,
            initial_working_dir=config.execution.working_dir or None
        )

        # HTTP session with retry logic
        self.session = self._create_session()

        # Registration state
        self._registered = False
        self._integration_id: Optional[int] = None

        # Stats
        self._commands_executed = 0
        self._last_checkin: Optional[datetime] = None
        self._start_time: Optional[datetime] = None

        logger.info(f"Beacon initialized (version {__version__})")

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry configuration."""
        session = requests.Session()

        # Retry strategy - reduced retries to prevent long blocks
        # With total=1 and 10s timeout, max block time is ~10s instead of 60+s
        retry_strategy = Retry(
            total=1,  # Only 1 retry (reduced from 3) to avoid long blocks
            backoff_factor=0.5,  # Faster backoff
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default headers
        session.headers.update({
            "User-Agent": f"TsushinBeacon/{__version__}",
            "X-API-Key": self.config.server.api_key,
            "Content-Type": "application/json"
        })

        return session

    def _reset_session(self) -> None:
        """Reset HTTP session to clear any stuck connections."""
        logger.debug("[BEACON-SESSION] Resetting HTTP session to clear stuck connections")
        _flush_handlers()
        try:
            self.session.close()
        except Exception:
            pass
        self.session = self._create_session()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Optional[requests.Response]:
        """
        Make an HTTP request with error handling.

        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (relative to server URL)
            data: Request body data

        Returns:
            Response object or None on error
        """
        url = f"{self.config.server.url.rstrip('/')}/{endpoint.lstrip('/')}"
        request_start = datetime.utcnow()

        logger.debug(f"[BEACON-REQ] Starting {method} {endpoint} at {request_start.isoformat()}")
        _flush_handlers()

        try:
            response = self.session.request(
                method=method,
                url=url,
                json=data,
                timeout=self.config.connection.request_timeout
            )

            request_duration = (datetime.utcnow() - request_start).total_seconds()
            logger.debug(f"[BEACON-REQ] Completed {method} {endpoint} in {request_duration:.2f}s - HTTP {response.status_code}")
            _flush_handlers()

            # Reset reconnect delay on success
            self._current_reconnect_delay = self.config.connection.reconnect_delay

            return response

        except requests.exceptions.Timeout:
            request_duration = (datetime.utcnow() - request_start).total_seconds()
            logger.warning(f"[BEACON-REQ] TIMEOUT on {endpoint} after {request_duration:.2f}s")
            _flush_handlers()
            return None

        except requests.exceptions.ConnectionError as e:
            request_duration = (datetime.utcnow() - request_start).total_seconds()
            logger.warning(f"[BEACON-REQ] CONNECTION ERROR on {endpoint} after {request_duration:.2f}s: {e}")
            _flush_handlers()
            return None

        except Exception as e:
            request_duration = (datetime.utcnow() - request_start).total_seconds()
            logger.error(f"[BEACON-REQ] ERROR on {endpoint} after {request_duration:.2f}s: {e}")
            logger.debug(traceback.format_exc())
            _flush_handlers()
            return None

    def _register(self) -> bool:
        """
        Register beacon with the server.

        Returns:
            True if registration successful
        """
        os_info = get_os_info()

        logger.info(f"Registering beacon: {os_info.get('hostname', 'unknown')}")

        response = self._make_request("POST", "/register", {
            "hostname": os_info.get("hostname", "unknown"),
            "os_info": os_info
        })

        if response is None:
            return False

        if response.status_code == 401:
            logger.error("Registration failed: Invalid API key")
            return False

        if response.status_code != 200:
            logger.error(f"Registration failed: HTTP {response.status_code}")
            try:
                error = response.json()
                logger.error(f"Error details: {error}")
            except Exception:
                pass
            return False

        try:
            data = response.json()
            self._registered = True
            self._integration_id = data.get("integration_id")
            poll_interval = data.get("poll_interval", self.config.connection.poll_interval)

            # Update poll interval from server
            self.config.connection.poll_interval = poll_interval

            logger.info(f"Registration successful: integration_id={self._integration_id}, poll_interval={poll_interval}s")
            return True

        except Exception as e:
            logger.error(f"Failed to parse registration response: {e}")
            return False

    def _checkin(self) -> Optional[list]:
        """
        Perform a check-in with the server.

        Returns:
            List of pending commands or None on error
        """
        checkin_start = datetime.utcnow()
        logger.debug(f"[BEACON-CHECKIN] Starting checkin at {checkin_start.isoformat()}")
        _flush_handlers()

        os_info = get_os_info()

        response = self._make_request("POST", "/checkin", {
            "hostname": os_info.get("hostname"),
            "os_info": os_info
        })

        if response is None:
            return None

        if response.status_code == 401:
            logger.error("Check-in failed: Invalid API key - re-registration may be needed")
            self._registered = False
            return None

        if response.status_code != 200:
            logger.warning(f"Check-in failed: HTTP {response.status_code}")
            return None

        try:
            data = response.json()
            self._last_checkin = datetime.utcnow()

            # Update poll interval if server changed it
            if "poll_interval" in data:
                self.config.connection.poll_interval = data["poll_interval"]

            pending = data.get("pending_commands", [])

            checkin_duration = (datetime.utcnow() - checkin_start).total_seconds()
            if pending:
                logger.info(f"[BEACON-CHECKIN] Received {len(pending)} pending command(s) in {checkin_duration:.2f}s")
            else:
                logger.debug(f"[BEACON-CHECKIN] No pending commands (took {checkin_duration:.2f}s)")
            _flush_handlers()

            return pending

        except Exception as e:
            logger.error(f"[BEACON-CHECKIN] Failed to parse response: {e}")
            _flush_handlers()
            return None

    def _report_result(self, command_id: str, result: Dict[str, Any]) -> bool:
        """
        Report command execution result to server.

        Args:
            command_id: UUID of the command
            result: Execution result dictionary

        Returns:
            True if result reported successfully
        """
        response = self._make_request("POST", "/result", {
            "command_id": command_id,
            "exit_code": result.get("exit_code", 1),
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "execution_time_ms": result.get("execution_time_ms", 0),
            "final_working_dir": result.get("final_working_dir", ""),
            "full_result_json": result.get("full_result_json", []),
            "error_message": result.get("error_message")
        })

        if response is None:
            logger.warning(f"Failed to report result for command {command_id}")
            return False

        if response.status_code != 200:
            logger.warning(f"Result report failed: HTTP {response.status_code}")
            return False

        logger.debug(f"Result reported for command {command_id}")
        return True

    def _handle_system_command(self, command_id: str, system_cmd: str) -> Dict[str, Any]:
        """
        Handle special system commands from the server.

        System commands start with '__beacon_' and control beacon behavior.

        Args:
            command_id: UUID of the command
            system_cmd: The system command string

        Returns:
            Result dictionary with exit_code, stdout, stderr
        """
        logger.info(f"Handling system command: {system_cmd}")

        if system_cmd == "__beacon_shutdown__":
            # Graceful shutdown - stop the beacon
            logger.info("Received shutdown command from server")
            self._shutdown_requested = True
            return {
                "exit_code": 0,
                "stdout": "Beacon shutdown initiated",
                "stderr": "",
                "execution_time_ms": 0
            }

        elif system_cmd == "__beacon_persistence_install__":
            # Install persistence
            try:
                from .persistence import handle_persistence_command
                result_code = handle_persistence_command("install", self.config, system_level=False)
                return {
                    "exit_code": result_code,
                    "stdout": "Persistence installed successfully" if result_code == 0 else "Persistence installation failed",
                    "stderr": "",
                    "execution_time_ms": 0
                }
            except Exception as e:
                logger.error(f"Failed to install persistence: {e}")
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": f"Failed to install persistence: {e}",
                    "execution_time_ms": 0
                }

        elif system_cmd == "__beacon_persistence_uninstall__":
            # Uninstall persistence
            try:
                from .persistence import handle_persistence_command
                result_code = handle_persistence_command("uninstall", self.config, system_level=False)
                return {
                    "exit_code": result_code,
                    "stdout": "Persistence uninstalled successfully" if result_code == 0 else "Persistence uninstall failed",
                    "stderr": "",
                    "execution_time_ms": 0
                }
            except Exception as e:
                logger.error(f"Failed to uninstall persistence: {e}")
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": f"Failed to uninstall persistence: {e}",
                    "execution_time_ms": 0
                }

        elif system_cmd == "__beacon_persistence_status__":
            # Check persistence status
            try:
                from .persistence import get_persistence_manager, _detect_beacon_path, _get_default_config_path
                import sys

                beacon_path = _detect_beacon_path()
                config_path = getattr(self.config, 'config_file_path', None) or _get_default_config_path()

                manager = get_persistence_manager(
                    beacon_path=beacon_path,
                    config_path=config_path,
                    python_path=sys.executable,
                    server_url=self.config.server.url,
                    api_key=self.config.server.api_key,
                    system_level=False
                )
                result = manager.status()
                return {
                    "exit_code": 0 if result.success else 1,
                    "stdout": result.message,
                    "stderr": "",
                    "execution_time_ms": 0,
                    "full_result_json": [{"persistence_status": result.status.value if result.status else "unknown", "details": result.details}]
                }
            except Exception as e:
                logger.error(f"Failed to get persistence status: {e}")
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": f"Failed to get persistence status: {e}",
                    "execution_time_ms": 0
                }

        else:
            logger.warning(f"Unknown system command: {system_cmd}")
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": f"Unknown system command: {system_cmd}",
                "execution_time_ms": 0
            }

    def _execute_commands(self, pending_commands: list) -> None:
        """
        Execute pending commands and report results.

        Args:
            pending_commands: List of command dicts from server
        """
        for cmd_info in pending_commands:
            if self._shutdown_requested:
                logger.info("Shutdown requested, stopping command execution")
                break

            command_id = cmd_info.get("id")
            commands = cmd_info.get("commands", [])
            timeout = cmd_info.get("timeout", self.config.execution.timeout)

            # Check if this is a system command (single command starting with __beacon_)
            if len(commands) == 1 and commands[0].startswith("__beacon_"):
                logger.info(f"Processing system command {command_id}")
                result = self._handle_system_command(command_id, commands[0])
                self._report_result(command_id, result)
                continue

            logger.info(f"Executing command {command_id}: {len(commands)} command(s)")

            # Execute stacked commands
            result = self.executor.run_stacked(
                commands=commands,
                timeout_per_command=timeout,
                stop_on_error=True
            )

            self._commands_executed += 1

            # Log result summary
            if result.final_exit_code == 0:
                logger.info(f"Command {command_id} completed successfully ({result.total_execution_time_ms}ms)")
            else:
                logger.warning(f"Command {command_id} failed with exit code {result.final_exit_code}")

            # Report result to server
            self._report_result(command_id, result.to_dict())

    def _exponential_backoff(self) -> None:
        """Apply exponential backoff on connection failure."""
        logger.info(f"Waiting {self._current_reconnect_delay}s before retry...")
        time.sleep(self._current_reconnect_delay)

        # Increase delay with cap
        self._current_reconnect_delay = min(
            self._current_reconnect_delay * 2,
            self.config.connection.max_reconnect_delay
        )

    def run(self) -> None:
        """
        Main beacon loop.

        Runs until shutdown is requested via signal or error.
        """
        self._running = True
        self._start_time = datetime.utcnow()

        logger.info("Starting beacon polling loop...")

        # Registration loop
        while self._running and not self._registered:
            if self._shutdown_requested:
                break

            if self._register():
                break

            self._exponential_backoff()

        # Main polling loop
        while self._running and not self._shutdown_requested:
            try:
                # Check-in and get pending commands
                pending = self._checkin()

                if pending is None:
                    # Connection issue
                    self._exponential_backoff()
                    continue

                # Execute any pending commands
                if pending:
                    self._execute_commands(pending)

                # Wait for next poll
                if not self._shutdown_requested:
                    time.sleep(self.config.connection.poll_interval)

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                self._shutdown_requested = True

            except Exception as e:
                logger.error(f"Unexpected error in polling loop: {e}", exc_info=True)
                self._exponential_backoff()

        self._running = False
        self._log_stats()
        logger.info("Beacon stopped")

    def stop(self) -> None:
        """Request graceful shutdown."""
        logger.info("Shutdown requested...")
        self._shutdown_requested = True

    def _log_stats(self) -> None:
        """Log beacon statistics."""
        if self._start_time:
            uptime = datetime.utcnow() - self._start_time
            logger.info(f"Session stats: uptime={uptime}, commands_executed={self._commands_executed}")


def _flush_handlers():
    """Flush all handlers to ensure logs are written immediately."""
    for handler in logging.getLogger("tsushin").handlers:
        handler.flush()


def setup_logging(config: BeaconConfig) -> None:
    """
    Configure logging with file rotation.

    Args:
        config: Beacon configuration
    """
    # Get log level - use DEBUG for detailed timing info
    log_level = getattr(logging, config.logging.level, logging.INFO)

    # Create formatter with milliseconds for precise timing
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Root logger for beacon
    root_logger = logging.getLogger("tsushin")
    root_logger.setLevel(log_level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # File handler with rotation - NO BUFFERING for immediate writes
    file_handler = RotatingFileHandler(
        config.logging.file,
        maxBytes=config.logging.max_size_mb * 1024 * 1024,
        backupCount=config.logging.backup_count
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Also log to console for interactive use
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Reduce noise from requests library
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def setup_signal_handlers(beacon: Beacon) -> None:
    """
    Set up signal handlers for graceful shutdown.

    Args:
        beacon: Beacon instance to stop on signal
    """
    def signal_handler(signum, frame):
        signal_name = signal.Signals(signum).name
        logger.info(f"Received {signal_name}, initiating graceful shutdown...")
        beacon.stop()

    # Register handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Platform-specific signals
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, signal_handler)


def main() -> int:
    """
    Main entry point for the beacon.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Parse arguments
    parser = create_argument_parser()
    args = parser.parse_args()

    # Handle version flag
    if args.version:
        print(f"Tsushin Shell Beacon v{__version__}")
        return 0

    # Handle persistence commands (before full config validation)
    if hasattr(args, 'persistence') and args.persistence:
        from .persistence import handle_persistence_command

        # Load config with relaxed validation for persistence commands
        try:
            config = load_config(args)
        except Exception as e:
            # For status command, we can proceed with defaults
            if args.persistence == 'status':
                config = BeaconConfig()
            else:
                print(f"Configuration error: {e}", file=sys.stderr)
                return 1

        system_level = getattr(args, 'persistence_system', False)
        return handle_persistence_command(args.persistence, config, system_level)

    # Load configuration
    try:
        config = load_config(args)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    # Handle dump-config flag
    if args.dump_config:
        print(json.dumps(config.to_dict(), indent=2))
        return 0

    # Validate configuration
    errors = config.validate()
    if errors:
        for error in errors:
            print(f"Configuration error: {error}", file=sys.stderr)
        return 1

    # Setup logging
    try:
        setup_logging(config)
    except Exception as e:
        print(f"Failed to setup logging: {e}", file=sys.stderr)
        return 1

    # Log configuration (redacted)
    logger.info(f"Tsushin Shell Beacon v{__version__} starting...")
    logger.info(f"Configuration: {json.dumps(config.to_dict(), indent=2)}")

    # Create beacon
    try:
        beacon = Beacon(config)
    except Exception as e:
        logger.error(f"Failed to initialize beacon: {e}")
        return 1

    # Setup signal handlers
    setup_signal_handlers(beacon)

    # Check for updates on startup
    if config.update.enabled and config.update.check_on_startup:
        try:
            from .updater import BeaconUpdater
            updater = BeaconUpdater(config.server.url, config.server.api_key)
            if updater.check_and_apply():
                logger.info("Update applied, please restart the beacon")
                return 0
        except ImportError:
            logger.debug("Updater not available")
        except Exception as e:
            logger.warning(f"Update check failed: {e}")

    # Run beacon based on mode
    try:
        if config.connection.mode == "websocket":
            # WebSocket mode - real-time communication
            logger.info("Starting in WebSocket mode...")

            try:
                from .websocket_client import WebSocketBeaconClient
            except ImportError:
                logger.error("WebSocket mode requires 'websockets' library. Run: pip install websockets")
                return 1

            # Convert HTTP URL to WebSocket URL
            server_url = config.server.url
            if server_url.startswith("http://"):
                ws_url = server_url.replace("http://", "ws://")
            elif server_url.startswith("https://"):
                ws_url = server_url.replace("https://", "wss://")
            else:
                ws_url = server_url

            # Remove /api/shell suffix if present, add /ws/beacon/0 (integration_id from auth)
            if ws_url.endswith("/api/shell"):
                ws_url = ws_url[:-len("/api/shell")]
            ws_url = f"{ws_url.rstrip('/')}/ws/beacon/0"  # 0 = will be resolved during auth

            import asyncio

            ws_client = WebSocketBeaconClient(
                server_url=ws_url,
                api_key=config.server.api_key,
                heartbeat_interval=config.connection.heartbeat_interval,
                reconnect_delay=config.connection.reconnect_delay,
                max_reconnect_delay=config.connection.max_reconnect_delay,
                executor=beacon.executor
            )

            # Setup signal handlers for WebSocket mode
            def ws_signal_handler(signum, frame):
                signal_name = signal.Signals(signum).name
                logger.info(f"Received {signal_name}, initiating graceful shutdown...")
                asyncio.create_task(ws_client.stop())

            signal.signal(signal.SIGINT, ws_signal_handler)
            signal.signal(signal.SIGTERM, ws_signal_handler)

            asyncio.run(ws_client.run())
            return 0
        else:
            # HTTP polling mode (default)
            logger.info("Starting in HTTP polling mode...")
            beacon.run()
            return 0

    except Exception as e:
        logger.error(f"Beacon error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
