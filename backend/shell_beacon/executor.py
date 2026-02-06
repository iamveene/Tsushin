"""
Command Executor for Tsushin Shell Beacon

Handles:
- Stacked command execution (multiple commands in sequence)
- Working directory tracking (cd commands update state)
- Timeout handling
- Output capture (stdout/stderr)
- Per-command result aggregation
"""

import os
import re
import time
import subprocess
import platform
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of a single command execution."""
    command: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    execution_time_ms: int = 0
    is_cd_command: bool = False
    new_working_dir: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class StackedResult:
    """Result of executing a stack of commands."""
    results: List[CommandResult] = field(default_factory=list)
    final_exit_code: int = 0
    final_working_dir: str = ""
    total_execution_time_ms: int = 0

    # Aggregated output (all commands)
    aggregated_stdout: str = ""
    aggregated_stderr: str = ""

    # Error info (if any command failed)
    error_message: Optional[str] = None
    failed_at_command: Optional[int] = None  # Index of failed command

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "exit_code": self.final_exit_code,
            "stdout": self.aggregated_stdout,
            "stderr": self.aggregated_stderr,
            "execution_time_ms": self.total_execution_time_ms,
            "final_working_dir": self.final_working_dir,
            "error_message": self.error_message,
            "full_result_json": [
                {
                    "command": r.command,
                    "exit_code": r.exit_code,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                    "time_ms": r.execution_time_ms,
                    "is_cd": r.is_cd_command,
                    "new_dir": r.new_working_dir
                }
                for r in self.results
            ]
        }


class CommandExecutor:
    """
    Executes shell commands with working directory tracking.

    Handles `cd` commands specially to maintain state across
    stacked command execution.
    """

    # Regex patterns for cd commands
    CD_PATTERNS = [
        r'^cd\s+(.+)$',           # cd /path/to/dir
        r'^cd$',                   # cd (go to home)
        r'^pushd\s+(.+)$',        # pushd /path
        r'^popd$',                 # popd
    ]

    def __init__(
        self,
        shell: str = "/bin/bash",
        timeout: int = 300,
        initial_working_dir: Optional[str] = None
    ):
        """
        Initialize the command executor.

        Args:
            shell: Shell to use for command execution
            timeout: Default timeout in seconds
            initial_working_dir: Starting directory (None = current dir)
        """
        self.shell = shell
        self.timeout = timeout
        self.is_windows = platform.system() == "Windows"

        # Track working directory
        if initial_working_dir:
            self.working_dir = str(Path(initial_working_dir).resolve())
        else:
            self.working_dir = os.getcwd()

        # Directory stack for pushd/popd
        self._dir_stack: List[str] = []

        logger.debug(f"Executor initialized: shell={shell}, timeout={timeout}, cwd={self.working_dir}")

    def _is_cd_command(self, command: str) -> bool:
        """Check if command is a directory change command."""
        command = command.strip()
        for pattern in self.CD_PATTERNS:
            if re.match(pattern, command, re.IGNORECASE):
                return True
        return False

    def _resolve_cd_path(self, command: str) -> Tuple[str, Optional[str]]:
        """
        Resolve the target directory for a cd command.

        Returns:
            Tuple of (cd_type, resolved_path)
            cd_type: 'cd', 'pushd', 'popd'
            resolved_path: Absolute path or None for errors
        """
        command = command.strip()

        # Handle plain 'cd' (go to home)
        if command == "cd":
            home = os.path.expanduser("~")
            return ("cd", home)

        # Handle 'cd <path>'
        cd_match = re.match(r'^cd\s+(.+)$', command, re.IGNORECASE)
        if cd_match:
            target = cd_match.group(1).strip()
            # Remove quotes if present
            target = target.strip('"\'')
            # Handle special paths
            if target == "-":
                # cd - not supported in this context
                return ("cd", None)
            if target == "~" or target.startswith("~/"):
                target = os.path.expanduser(target)
            elif not os.path.isabs(target):
                target = os.path.join(self.working_dir, target)
            # Resolve to absolute path
            resolved = str(Path(target).resolve())
            return ("cd", resolved)

        # Handle 'pushd <path>'
        pushd_match = re.match(r'^pushd\s+(.+)$', command, re.IGNORECASE)
        if pushd_match:
            target = pushd_match.group(1).strip().strip('"\'')
            if target == "~" or target.startswith("~/"):
                target = os.path.expanduser(target)
            elif not os.path.isabs(target):
                target = os.path.join(self.working_dir, target)
            resolved = str(Path(target).resolve())
            return ("pushd", resolved)

        # Handle 'popd'
        if command.lower() == "popd":
            if self._dir_stack:
                return ("popd", self._dir_stack[-1])
            return ("popd", None)

        return ("unknown", None)

    def _execute_cd(self, command: str) -> CommandResult:
        """
        Execute a cd/pushd/popd command by updating working directory state.

        Returns:
            CommandResult with success/failure and new working dir
        """
        start_time = time.time()

        cd_type, new_dir = self._resolve_cd_path(command)

        if new_dir is None:
            if cd_type == "popd" and not self._dir_stack:
                return CommandResult(
                    command=command,
                    exit_code=1,
                    stderr="popd: directory stack empty",
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    is_cd_command=True,
                    error_message="Directory stack is empty"
                )
            return CommandResult(
                command=command,
                exit_code=1,
                stderr=f"cd: could not resolve path",
                execution_time_ms=int((time.time() - start_time) * 1000),
                is_cd_command=True,
                error_message="Could not resolve path"
            )

        # Check if directory exists
        if not os.path.isdir(new_dir):
            return CommandResult(
                command=command,
                exit_code=1,
                stderr=f"cd: {new_dir}: No such file or directory",
                execution_time_ms=int((time.time() - start_time) * 1000),
                is_cd_command=True,
                error_message=f"Directory does not exist: {new_dir}"
            )

        # Update state based on command type
        old_dir = self.working_dir

        if cd_type == "pushd":
            self._dir_stack.append(self.working_dir)
            self.working_dir = new_dir
            stdout = f"{new_dir} {' '.join(self._dir_stack[::-1])}"
        elif cd_type == "popd":
            self._dir_stack.pop()
            self.working_dir = new_dir
            stdout = f"{new_dir} {' '.join(self._dir_stack[::-1])}" if self._dir_stack else new_dir
        else:  # cd
            self.working_dir = new_dir
            stdout = ""

        logger.debug(f"Directory changed: {old_dir} -> {new_dir}")

        return CommandResult(
            command=command,
            exit_code=0,
            stdout=stdout,
            execution_time_ms=int((time.time() - start_time) * 1000),
            is_cd_command=True,
            new_working_dir=new_dir
        )

    # Defense-in-depth: Block obvious injection patterns at beacon level
    # Primary security is in the backend, this is a last-line defense
    BEACON_BLOCKED_PATTERNS = [
        # Fork bombs
        r':\(\)\s*{\s*:\|:\s*&\s*}\s*;',
        r':\s*\(\s*\)\s*\{',
        # Direct filesystem destruction
        r'rm\s+-rf\s+/\s*$',
        r'rm\s+-rf\s+/\*',
        r'>\s*/dev/sd[a-z]',
        r'mkfs.*\s+/dev/sd[a-z]',
        # Root deletion attempts
        r'rm\s+-rf\s+/$',
    ]

    def _sanitize_command(self, command: str) -> str:
        """
        Defense-in-depth: Check command for obvious injection patterns.

        This is a LAST-LINE defense - primary security checks happen in the backend.
        This method catches obvious malicious patterns that somehow bypassed
        the backend security service.

        Args:
            command: Command to check

        Returns:
            The command unchanged if it passes checks

        Raises:
            ValueError: If command matches a blocked pattern
        """
        for pattern in self.BEACON_BLOCKED_PATTERNS:
            if re.search(pattern, command, re.IGNORECASE):
                logger.error(
                    f"BEACON SECURITY: Blocked command matching pattern '{pattern}': "
                    f"{command[:100]}..."
                )
                raise ValueError(f"Command blocked by beacon security: matches pattern {pattern}")

        return command

    def _execute_command(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """
        Execute a single shell command.

        Args:
            command: Command to execute
            timeout: Timeout in seconds (None = use default)

        Returns:
            CommandResult with exit code, stdout, stderr
        """
        if timeout is None:
            timeout = self.timeout

        start_time = time.time()

        try:
            # Defense-in-depth: Check for obvious injection patterns
            try:
                command = self._sanitize_command(command)
            except ValueError as sec_error:
                return CommandResult(
                    command=command,
                    exit_code=126,  # Command cannot execute
                    stderr=str(sec_error),
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    error_message=str(sec_error)
                )

            # Build the command based on OS
            if self.is_windows:
                # Windows: use cmd /c
                full_command = f'cmd /c "{command}"'
            else:
                # Unix: use shell directly
                full_command = command

            logger.debug(f"Executing: {command} (cwd: {self.working_dir})")

            result = subprocess.run(
                full_command,
                shell=True,
                cwd=self.working_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy()
            )

            execution_time = int((time.time() - start_time) * 1000)

            return CommandResult(
                command=command,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_time_ms=execution_time
            )

        except subprocess.TimeoutExpired:
            execution_time = int((time.time() - start_time) * 1000)
            return CommandResult(
                command=command,
                exit_code=124,  # Standard timeout exit code
                stderr=f"Command timed out after {timeout} seconds",
                execution_time_ms=execution_time,
                error_message=f"Timeout after {timeout}s"
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            logger.error(f"Command execution error: {e}")
            return CommandResult(
                command=command,
                exit_code=1,
                stderr=str(e),
                execution_time_ms=execution_time,
                error_message=str(e)
            )

    def run(self, command: str, timeout: Optional[int] = None) -> CommandResult:
        """
        Execute a single command.

        Handles cd commands specially by updating internal state.

        Args:
            command: Command to execute
            timeout: Timeout in seconds

        Returns:
            CommandResult
        """
        command = command.strip()

        if not command or command.startswith("#"):
            # Empty or comment line
            return CommandResult(
                command=command,
                exit_code=0,
                execution_time_ms=0
            )

        if self._is_cd_command(command):
            return self._execute_cd(command)

        return self._execute_command(command, timeout)

    def run_stacked(
        self,
        commands: List[str],
        timeout_per_command: Optional[int] = None,
        stop_on_error: bool = True
    ) -> StackedResult:
        """
        Execute multiple commands in sequence.

        Maintains working directory state across commands.
        cd commands update the state for subsequent commands.

        Args:
            commands: List of commands to execute
            timeout_per_command: Timeout for each command
            stop_on_error: Stop execution on first non-zero exit code

        Returns:
            StackedResult with aggregated results
        """
        result = StackedResult(final_working_dir=self.working_dir)

        stdout_parts = []
        stderr_parts = []

        for i, command in enumerate(commands):
            cmd_result = self.run(command, timeout_per_command)
            result.results.append(cmd_result)
            result.total_execution_time_ms += cmd_result.execution_time_ms

            # Aggregate output
            if cmd_result.stdout:
                stdout_parts.append(f"$ {command}\n{cmd_result.stdout}")
            if cmd_result.stderr:
                stderr_parts.append(f"$ {command}\n{cmd_result.stderr}")

            # Check for failure
            if cmd_result.exit_code != 0:
                result.final_exit_code = cmd_result.exit_code
                result.error_message = cmd_result.error_message or f"Command failed: {command}"
                result.failed_at_command = i

                if stop_on_error:
                    logger.warning(f"Stopping execution at command {i+1}: {command}")
                    break

        result.aggregated_stdout = "\n".join(stdout_parts)
        result.aggregated_stderr = "\n".join(stderr_parts)
        result.final_working_dir = self.working_dir

        return result

    def reset_working_dir(self, path: Optional[str] = None) -> None:
        """
        Reset working directory.

        Args:
            path: New working directory (None = current process dir)
        """
        if path:
            self.working_dir = str(Path(path).resolve())
        else:
            self.working_dir = os.getcwd()
        self._dir_stack.clear()
        logger.debug(f"Working directory reset to: {self.working_dir}")


def get_os_info() -> Dict[str, str]:
    """
    Get detailed OS information for beacon registration.

    Returns:
        Dictionary with OS details
    """
    import socket

    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = platform.node()

    info = {
        "hostname": hostname,
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
    }

    # Add Linux-specific info
    if platform.system() == "Linux":
        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["distro"] = line.split("=")[1].strip().strip('"')
                        break
        except Exception:
            pass

    return info
