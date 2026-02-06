"""
Windows persistence manager using Task Scheduler.
"""

import os
import subprocess
import ctypes
from pathlib import Path
from typing import Optional, Dict, Any

from .base import BasePersistenceManager, PersistenceResult, PersistenceStatus


class WindowsPersistenceManager(BasePersistenceManager):
    """
    Windows persistence manager using Task Scheduler.

    Uses schtasks.exe for maximum compatibility.
    User-level: Runs at user logon
    System-level: Runs at system startup (requires admin)
    """

    TASK_NAME = "TsushinBeacon"

    @property
    def platform_name(self) -> str:
        level = "system startup" if self.system_level else "user logon"
        return f"Windows (Task Scheduler - {level})"

    def get_service_file_path(self) -> str:
        # Task Scheduler doesn't use a file path, but we return a descriptive path
        return f"Task Scheduler\\{self.TASK_NAME}"

    def _is_admin(self) -> bool:
        """Check if running with admin privileges."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception:
            return False

    def _run_schtasks(self, *args) -> tuple[int, str, str]:
        """Run schtasks command and return (returncode, stdout, stderr)."""
        cmd = ["schtasks"] + list(args)

        try:
            # Use shell=True on Windows for better compatibility
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
                shell=True
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    def _get_task_command(self) -> str:
        """Get the command to run for the scheduled task."""
        # Quote paths properly for Windows
        python_path = f'"{self.python_path}"'
        beacon_path = f'"{self.beacon_path}"'
        config_path = f'"{self.config_path}"'

        return f'{python_path} {beacon_path} --config {config_path}'

    def install(self) -> PersistenceResult:
        # Check if we need admin and don't have it
        if self.system_level and not self._is_admin():
            return PersistenceResult(
                success=False,
                message="System-level persistence requires administrator privileges.\n"
                        "Please run as Administrator or use user-level persistence (remove --system flag).",
                status=PersistenceStatus.ERROR
            )

        # Delete existing task if present (ignore errors)
        self._run_schtasks("/delete", "/tn", self.TASK_NAME, "/f")

        # Build the create command
        task_command = self._get_task_command()

        # Create the scheduled task
        if self.system_level:
            # Run at system startup (before any user logs in)
            rc, stdout, stderr = self._run_schtasks(
                "/create",
                "/tn", self.TASK_NAME,
                "/tr", task_command,
                "/sc", "onstart",  # Run at system startup
                "/rl", "highest",  # Run with highest privileges
                "/f"  # Force (overwrite if exists)
            )
        else:
            # Run at user logon
            rc, stdout, stderr = self._run_schtasks(
                "/create",
                "/tn", self.TASK_NAME,
                "/tr", task_command,
                "/sc", "onlogon",  # Run at user logon
                "/rl", "limited",  # Run with limited privileges
                "/f"  # Force (overwrite if exists)
            )

        if rc != 0:
            return PersistenceResult(
                success=False,
                message=f"Failed to create scheduled task: {stderr or stdout}",
                status=PersistenceStatus.ERROR
            )

        # Start the task immediately
        rc, stdout, stderr = self._run_schtasks("/run", "/tn", self.TASK_NAME)
        start_msg = ""
        if rc != 0:
            start_msg = "\n\nNote: Task is scheduled but could not be started immediately."

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Persistence installed successfully\n\n"
                    f"Platform: {self.platform_name}\n"
                    f"Task name: {self.TASK_NAME}\n"
                    f"Status: enabled\n\n"
                    f"The beacon will start automatically on {'system startup' if self.system_level else 'user logon'}."
                    f"{start_msg}\n\n"
                    f"To check status: tsushin-beacon --persistence status\n"
                    f"To remove: tsushin-beacon --persistence uninstall",
            status=PersistenceStatus.INSTALLED,
            details={
                "task_name": self.TASK_NAME,
                "trigger": "onstart" if self.system_level else "onlogon"
            }
        )

    def uninstall(self) -> PersistenceResult:
        # Check if task exists
        rc, stdout, stderr = self._run_schtasks("/query", "/tn", self.TASK_NAME)
        if rc != 0:
            return PersistenceResult(
                success=True,
                message="No persistence mechanism was installed.",
                status=PersistenceStatus.NOT_INSTALLED
            )

        # End the task if running
        self._run_schtasks("/end", "/tn", self.TASK_NAME)

        # Delete the task
        rc, stdout, stderr = self._run_schtasks("/delete", "/tn", self.TASK_NAME, "/f")
        if rc != 0:
            return PersistenceResult(
                success=False,
                message=f"Failed to delete scheduled task: {stderr or stdout}",
                status=PersistenceStatus.ERROR
            )

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Persistence removed successfully\n\n"
                    f"The beacon will no longer start automatically.\n"
                    f"Scheduled task removed: {self.TASK_NAME}\n\n"
                    f"Note: The configuration file was preserved at {self.config_path}",
            status=PersistenceStatus.NOT_INSTALLED,
            details={"task_name": self.TASK_NAME}
        )

    def status(self) -> PersistenceResult:
        # Query the task
        rc, stdout, stderr = self._run_schtasks("/query", "/tn", self.TASK_NAME, "/v", "/fo", "list")

        if rc != 0:
            return PersistenceResult(
                success=True,
                message="[STATUS] Tsushin Beacon Persistence\n\n"
                        "Status: NOT INSTALLED\n\n"
                        "No persistence mechanism is configured.",
                status=PersistenceStatus.NOT_INSTALLED
            )

        # Parse the output
        task_info = self._parse_task_info(stdout)
        details = {"task_name": self.TASK_NAME}
        details.update(task_info)

        # Build status message
        lines = ["[STATUS] Tsushin Beacon Persistence\n"]
        lines.append(f"Platform: {self.platform_name}")
        lines.append(f"Task name: {self.TASK_NAME}")
        lines.append(f"Installation: INSTALLED")

        status_str = task_info.get("status", "Unknown")
        lines.append(f"Task status: {status_str}")

        if task_info.get("last_run"):
            lines.append(f"Last run: {task_info['last_run']}")

        if task_info.get("next_run"):
            lines.append(f"Next run: {task_info['next_run']}")

        # Determine if running
        if status_str.lower() == "running":
            status = PersistenceStatus.RUNNING
        elif "ready" in status_str.lower() or "queued" in status_str.lower():
            status = PersistenceStatus.INSTALLED
        else:
            status = PersistenceStatus.STOPPED

        lines.append(f"\nConfiguration:")
        lines.append(f"  Config file: {self.config_path}")
        lines.append(f"  Server URL: {self.server_url}")
        lines.append(f"  API key: {self._redact_api_key(self.api_key)}")

        return PersistenceResult(
            success=True,
            message="\n".join(lines),
            status=status,
            details=details
        )

    def _parse_task_info(self, output: str) -> Dict[str, Any]:
        """Parse schtasks /query output."""
        info = {}

        for line in output.splitlines():
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower()
                value = value.strip()

                if "status" in key:
                    info["status"] = value
                elif "last run time" in key:
                    info["last_run"] = value
                elif "next run time" in key:
                    info["next_run"] = value
                elif "task to run" in key:
                    info["command"] = value

        return info
