"""
Beacon Configuration Management

Handles configuration loading from multiple sources with priority:
1. CLI arguments (highest priority)
2. Environment variables
3. YAML config file
4. Default values (lowest priority)

Configuration file location: ~/.tsushin/beacon.yaml
"""

import os
import sys
import argparse
import platform
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

try:
    import yaml
except ImportError:
    yaml = None  # Will be caught at runtime


@dataclass
class ServerConfig:
    """Server connection configuration."""
    url: str = "http://localhost:8000/api/shell"
    api_key: str = ""


@dataclass
class ConnectionConfig:
    """Connection behavior configuration."""
    mode: str = "http"  # "http" (polling) or "websocket" (real-time)
    poll_interval: int = 5  # Seconds between check-ins
    heartbeat_interval: int = 15  # WebSocket heartbeat interval
    reconnect_delay: int = 5  # Initial reconnect delay
    max_reconnect_delay: int = 300  # Max reconnect delay (5 minutes)
    request_timeout: int = 10  # HTTP request timeout (reduced from 30 to avoid long blocks)


@dataclass
class ExecutionConfig:
    """Command execution configuration."""
    shell: str = "/bin/bash" if platform.system() != "Windows" else "cmd.exe"
    timeout: int = 300  # Command execution timeout
    working_dir: str = ""  # Empty = use current directory


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = ""  # Empty = auto-generate path
    max_size_mb: int = 10
    backup_count: int = 5


@dataclass
class UpdateConfig:
    """Auto-update configuration."""
    enabled: bool = True
    check_on_startup: bool = True
    check_interval_hours: int = 24


@dataclass
class BeaconConfig:
    """Complete beacon configuration."""
    server: ServerConfig = field(default_factory=ServerConfig)
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    update: UpdateConfig = field(default_factory=UpdateConfig)

    # Runtime state
    config_file_path: Optional[str] = None
    hostname: str = field(default_factory=platform.node)

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default configuration file path."""
        if platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path.home()
        return base / ".tsushin" / "beacon.yaml"

    @classmethod
    def get_default_log_path(cls) -> Path:
        """Get the default log file path."""
        if platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", Path.home()))
        else:
            base = Path.home()
        return base / ".tsushin" / "beacon.log"

    @classmethod
    def from_yaml(cls, path: Path) -> "BeaconConfig":
        """Load configuration from a YAML file."""
        if yaml is None:
            raise ImportError("PyYAML is required. Install with: pip install pyyaml")

        config = cls()
        config.config_file_path = str(path)

        if not path.exists():
            return config

        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Parse server config
        if 'server' in data:
            server_data = data['server']
            if 'url' in server_data:
                config.server.url = server_data['url']
            if 'api_key' in server_data:
                config.server.api_key = server_data['api_key']

        # Parse connection config
        if 'connection' in data:
            conn_data = data['connection']
            if 'poll_interval' in conn_data:
                config.connection.poll_interval = int(conn_data['poll_interval'])
            if 'reconnect_delay' in conn_data:
                config.connection.reconnect_delay = int(conn_data['reconnect_delay'])
            if 'max_reconnect_delay' in conn_data:
                config.connection.max_reconnect_delay = int(conn_data['max_reconnect_delay'])
            if 'request_timeout' in conn_data:
                config.connection.request_timeout = int(conn_data['request_timeout'])

        # Parse execution config
        if 'execution' in data:
            exec_data = data['execution']
            if 'shell' in exec_data:
                config.execution.shell = exec_data['shell']
            if 'timeout' in exec_data:
                config.execution.timeout = int(exec_data['timeout'])
            if 'working_dir' in exec_data:
                config.execution.working_dir = exec_data['working_dir']

        # Parse logging config
        if 'logging' in data:
            log_data = data['logging']
            if 'level' in log_data:
                config.logging.level = log_data['level'].upper()
            if 'file' in log_data:
                config.logging.file = log_data['file']
            if 'max_size_mb' in log_data:
                config.logging.max_size_mb = int(log_data['max_size_mb'])
            if 'backup_count' in log_data:
                config.logging.backup_count = int(log_data['backup_count'])

        # Parse update config
        if 'update' in data:
            update_data = data['update']
            if 'enabled' in update_data:
                config.update.enabled = bool(update_data['enabled'])
            if 'check_on_startup' in update_data:
                config.update.check_on_startup = bool(update_data['check_on_startup'])
            if 'check_interval_hours' in update_data:
                config.update.check_interval_hours = int(update_data['check_interval_hours'])

        return config

    def apply_env_vars(self) -> None:
        """Apply environment variable overrides."""
        # Server configuration
        if env_url := os.environ.get("TSUSHIN_SERVER_URL"):
            self.server.url = env_url
        if env_key := os.environ.get("TSUSHIN_API_KEY"):
            self.server.api_key = env_key

        # Connection configuration
        if env_poll := os.environ.get("TSUSHIN_POLL_INTERVAL"):
            self.connection.poll_interval = int(env_poll)

        # Execution configuration
        if env_shell := os.environ.get("TSUSHIN_SHELL"):
            self.execution.shell = env_shell
        if env_timeout := os.environ.get("TSUSHIN_TIMEOUT"):
            self.execution.timeout = int(env_timeout)
        if env_workdir := os.environ.get("TSUSHIN_WORKING_DIR"):
            self.execution.working_dir = env_workdir

        # Logging configuration
        if env_log_level := os.environ.get("TSUSHIN_LOG_LEVEL"):
            self.logging.level = env_log_level.upper()
        if env_log_file := os.environ.get("TSUSHIN_LOG_FILE"):
            self.logging.file = env_log_file

        # Update configuration
        if env_auto_update := os.environ.get("TSUSHIN_AUTO_UPDATE"):
            self.update.enabled = env_auto_update.lower() in ("true", "1", "yes")

    def apply_cli_args(self, args: argparse.Namespace) -> None:
        """Apply CLI argument overrides."""
        if hasattr(args, 'server') and args.server:
            self.server.url = args.server
        if hasattr(args, 'api_key') and args.api_key:
            self.server.api_key = args.api_key
        if hasattr(args, 'mode') and args.mode:
            self.connection.mode = args.mode
        if hasattr(args, 'poll_interval') and args.poll_interval:
            self.connection.poll_interval = args.poll_interval
        if hasattr(args, 'heartbeat_interval') and args.heartbeat_interval:
            self.connection.heartbeat_interval = args.heartbeat_interval
        if hasattr(args, 'shell') and args.shell:
            self.execution.shell = args.shell
        if hasattr(args, 'timeout') and args.timeout:
            self.execution.timeout = args.timeout
        if hasattr(args, 'working_dir') and args.working_dir:
            self.execution.working_dir = args.working_dir
        if hasattr(args, 'log_level') and args.log_level:
            self.logging.level = args.log_level.upper()
        if hasattr(args, 'log_file') and args.log_file:
            self.logging.file = args.log_file
        if hasattr(args, 'no_auto_update') and args.no_auto_update:
            self.update.enabled = False

    def validate(self) -> list[str]:
        """Validate configuration and return list of errors."""
        errors = []

        if not self.server.api_key:
            errors.append("API key is required. Set via --api-key, TSUSHIN_API_KEY, or config file.")

        if not self.server.url:
            errors.append("Server URL is required.")

        if self.connection.poll_interval < 1:
            errors.append("Poll interval must be at least 1 second.")

        if self.execution.timeout < 1:
            errors.append("Execution timeout must be at least 1 second.")

        return errors

    def finalize(self) -> None:
        """Finalize configuration (set defaults for empty values)."""
        # Set default log file path
        if not self.logging.file:
            self.logging.file = str(self.get_default_log_path())
        else:
            # Expand ~ in path
            self.logging.file = str(Path(self.logging.file).expanduser())

        # Expand ~ in working directory
        if self.execution.working_dir:
            self.execution.working_dir = str(Path(self.execution.working_dir).expanduser())

        # Ensure log directory exists
        log_dir = Path(self.logging.file).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for logging/debugging)."""
        return {
            "server": {
                "url": self.server.url,
                "api_key": f"{self.server.api_key[:10]}..." if len(self.server.api_key) > 10 else "***"
            },
            "connection": {
                "poll_interval": self.connection.poll_interval,
                "reconnect_delay": self.connection.reconnect_delay,
                "max_reconnect_delay": self.connection.max_reconnect_delay,
                "request_timeout": self.connection.request_timeout
            },
            "execution": {
                "shell": self.execution.shell,
                "timeout": self.execution.timeout,
                "working_dir": self.execution.working_dir or "(current directory)"
            },
            "logging": {
                "level": self.logging.level,
                "file": self.logging.file,
                "max_size_mb": self.logging.max_size_mb,
                "backup_count": self.logging.backup_count
            },
            "update": {
                "enabled": self.update.enabled,
                "check_on_startup": self.update.check_on_startup,
                "check_interval_hours": self.update.check_interval_hours
            }
        }


def create_argument_parser() -> argparse.ArgumentParser:
    """Create the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="tsushin-beacon",
        description="Tsushin Shell Beacon - Remote Command Execution Agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with API key from command line
  tsushin-beacon --server https://tsushin.example.com/api/shell --api-key shb_xxxxx

  # Run with config file
  tsushin-beacon --config ~/.tsushin/beacon.yaml

  # Run with environment variables
  TSUSHIN_API_KEY=shb_xxxxx TSUSHIN_SERVER_URL=https://... tsushin-beacon

Configuration priority (highest to lowest):
  1. CLI arguments
  2. Environment variables
  3. Config file
  4. Default values
"""
    )

    # Server options
    server_group = parser.add_argument_group("Server Options")
    server_group.add_argument(
        "-s", "--server",
        metavar="URL",
        help="Tsushin server URL (e.g., https://tsushin.example.com/api/shell)"
    )
    server_group.add_argument(
        "-k", "--api-key",
        metavar="KEY",
        help="Beacon API key (starts with 'shb_')"
    )

    # Connection options
    conn_group = parser.add_argument_group("Connection Options")
    conn_group.add_argument(
        "-m", "--mode",
        choices=["http", "websocket"],
        default=None,
        help="Connection mode: 'http' (polling) or 'websocket' (real-time) (default: http)"
    )
    conn_group.add_argument(
        "-p", "--poll-interval",
        type=int,
        metavar="SECONDS",
        help="Polling interval in seconds (default: 5)"
    )
    conn_group.add_argument(
        "--heartbeat-interval",
        type=int,
        metavar="SECONDS",
        help="WebSocket heartbeat interval in seconds (default: 15)"
    )

    # Execution options
    exec_group = parser.add_argument_group("Execution Options")
    exec_group.add_argument(
        "--shell",
        metavar="PATH",
        help="Shell to use for command execution (default: /bin/bash)"
    )
    exec_group.add_argument(
        "--timeout",
        type=int,
        metavar="SECONDS",
        help="Command execution timeout in seconds (default: 300)"
    )
    exec_group.add_argument(
        "--working-dir",
        metavar="PATH",
        help="Initial working directory for commands"
    )

    # Logging options
    log_group = parser.add_argument_group("Logging Options")
    log_group.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    log_group.add_argument(
        "--log-file",
        metavar="PATH",
        help="Log file path (default: ~/.tsushin/beacon.log)"
    )

    # Config file
    parser.add_argument(
        "-c", "--config",
        metavar="FILE",
        help="Configuration file path (default: ~/.tsushin/beacon.yaml)"
    )

    # Update options
    parser.add_argument(
        "--no-auto-update",
        action="store_true",
        help="Disable automatic updates"
    )

    # Persistence options
    persistence_group = parser.add_argument_group("Persistence Options")
    persistence_group.add_argument(
        "--persistence",
        choices=["install", "uninstall", "status"],
        metavar="ACTION",
        help="Manage auto-start persistence (install, uninstall, status)"
    )
    persistence_group.add_argument(
        "--system",
        action="store_true",
        dest="persistence_system",
        help="Use system-level persistence (requires admin/root privileges)"
    )

    # Other options
    parser.add_argument(
        "-v", "--version",
        action="store_true",
        help="Show version and exit"
    )
    parser.add_argument(
        "--dump-config",
        action="store_true",
        help="Dump effective configuration and exit"
    )

    return parser


def load_config(args: Optional[argparse.Namespace] = None) -> BeaconConfig:
    """
    Load configuration from all sources in priority order.

    Args:
        args: CLI arguments (if None, will parse sys.argv)

    Returns:
        Fully loaded and validated BeaconConfig
    """
    if args is None:
        parser = create_argument_parser()
        args = parser.parse_args()

    # Determine config file path
    if hasattr(args, 'config') and args.config:
        config_path = Path(args.config).expanduser()
    else:
        config_path = BeaconConfig.get_default_config_path()

    # Load from YAML (or create default)
    config = BeaconConfig.from_yaml(config_path)

    # Apply environment variables
    config.apply_env_vars()

    # Apply CLI arguments (highest priority)
    config.apply_cli_args(args)

    # Finalize (set defaults, expand paths)
    config.finalize()

    return config


def generate_sample_config() -> str:
    """Generate a sample YAML configuration file."""
    return """# Tsushin Beacon Configuration
# Location: ~/.tsushin/beacon.yaml

server:
  url: "https://your-tsushin-server.com/api/shell"
  api_key: "shb_your_api_key_here"

connection:
  poll_interval: 5        # Seconds between check-ins
  reconnect_delay: 5      # Initial reconnect delay on error
  max_reconnect_delay: 300  # Max reconnect delay (5 minutes)
  request_timeout: 30     # HTTP request timeout

execution:
  shell: "/bin/bash"      # Shell to use (Windows: cmd.exe)
  timeout: 300            # Command timeout in seconds
  working_dir: ""         # Initial working directory (empty = current)

logging:
  level: "INFO"           # DEBUG, INFO, WARNING, ERROR
  file: "~/.tsushin/beacon.log"  # Log file path
  max_size_mb: 10         # Rotate at this size
  backup_count: 5         # Keep this many rotated files

update:
  enabled: true           # Enable auto-update
  check_on_startup: true  # Check for updates on startup
  check_interval_hours: 24  # Check for updates every N hours
"""
