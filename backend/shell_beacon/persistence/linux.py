"""
Linux persistence manager using systemd (primary) or cron (fallback).
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Tuple

from .base import BasePersistenceManager, PersistenceResult, PersistenceStatus


class LinuxPersistenceManager(BasePersistenceManager):
    """
    Linux persistence manager.

    Primary: systemd user service (~/.config/systemd/user/)
    Fallback: cron @reboot job
    System-level: /etc/systemd/system/ (requires root)
    """

    SERVICE_NAME = "tsushin-beacon"
    CRON_MARKER = "# tsushin-beacon"

    @property
    def platform_name(self) -> str:
        if self._has_systemd():
            level = "system" if self.system_level else "user"
            return f"Linux (systemd {level} service)"
        return "Linux (cron @reboot)"

    def get_service_file_path(self) -> str:
        if self.system_level:
            return f"/etc/systemd/system/{self.SERVICE_NAME}.service"
        return str(Path.home() / ".config" / "systemd" / "user" / f"{self.SERVICE_NAME}.service")

    def _has_systemd(self) -> bool:
        """Check if systemd is available."""
        return shutil.which("systemctl") is not None

    def _has_user_session(self) -> bool:
        """Check if systemd user session is available."""
        if not self._has_systemd():
            return False
        try:
            result = subprocess.run(
                ["systemctl", "--user", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # If it runs without "Failed to connect" error, user session is available
            return "Failed to connect" not in result.stderr
        except Exception:
            return False

    def _generate_systemd_service(self) -> str:
        """Generate systemd service file content."""
        return f"""[Unit]
Description=Tsushin Shell Beacon
Documentation=https://github.com/your-org/tsushin
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={self.python_path} {self.beacon_path} --config {self.config_path}
Restart=always
RestartSec=10
Environment="TSUSHIN_API_KEY={self.api_key}"
Environment="TSUSHIN_SERVER_URL={self.server_url}"

# Security hardening (optional, can be adjusted)
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={Path(self.config_path).parent}

[Install]
WantedBy={"multi-user.target" if self.system_level else "default.target"}
"""

    def _run_systemctl(self, *args, user: bool = True) -> Tuple[int, str, str]:
        """Run systemctl command and return (returncode, stdout, stderr)."""
        cmd = ["systemctl"]
        if user and not self.system_level:
            cmd.append("--user")
        cmd.extend(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return 1, "", "Command timed out"
        except Exception as e:
            return 1, "", str(e)

    def install(self) -> PersistenceResult:
        # Check if systemd is available
        if self._has_systemd():
            if not self.system_level and not self._has_user_session():
                # Try cron fallback
                return self._install_cron()
            return self._install_systemd()
        else:
            # Use cron fallback
            return self._install_cron()

    def _install_systemd(self) -> PersistenceResult:
        """Install using systemd."""
        service_path = Path(self.get_service_file_path())

        # Create directory if needed
        service_path.parent.mkdir(parents=True, exist_ok=True)

        # Write service file
        try:
            service_content = self._generate_systemd_service()

            if self.system_level:
                # Need sudo for system-level
                result = subprocess.run(
                    ["sudo", "tee", str(service_path)],
                    input=service_content,
                    capture_output=True,
                    text=True
                )
                if result.returncode != 0:
                    return PersistenceResult(
                        success=False,
                        message=f"Failed to write service file (requires root): {result.stderr}",
                        status=PersistenceStatus.ERROR
                    )
            else:
                service_path.write_text(service_content)

        except PermissionError:
            return PersistenceResult(
                success=False,
                message=f"Permission denied writing to {service_path}. Use --system with sudo for system-level persistence.",
                status=PersistenceStatus.ERROR
            )
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to write service file: {e}",
                status=PersistenceStatus.ERROR
            )

        # Reload systemd
        user_flag = not self.system_level
        rc, _, stderr = self._run_systemctl("daemon-reload", user=user_flag)
        if rc != 0:
            return PersistenceResult(
                success=False,
                message=f"Failed to reload systemd: {stderr}",
                status=PersistenceStatus.ERROR
            )

        # Enable service
        rc, _, stderr = self._run_systemctl("enable", self.SERVICE_NAME, user=user_flag)
        if rc != 0:
            return PersistenceResult(
                success=False,
                message=f"Failed to enable service: {stderr}",
                status=PersistenceStatus.ERROR
            )

        # Start service
        rc, _, stderr = self._run_systemctl("start", self.SERVICE_NAME, user=user_flag)
        if rc != 0:
            return PersistenceResult(
                success=False,
                message=f"Service enabled but failed to start: {stderr}",
                status=PersistenceStatus.INSTALLED,
                details={"service_file": str(service_path)}
            )

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Persistence installed successfully\n\n"
                    f"Platform: {self.platform_name}\n"
                    f"Service file: {service_path}\n"
                    f"Status: enabled and running\n\n"
                    f"The beacon will now start automatically on {'boot' if self.system_level else 'login'}.\n\n"
                    f"To check status: tsushin-beacon --persistence status\n"
                    f"To remove: tsushin-beacon --persistence uninstall",
            status=PersistenceStatus.RUNNING,
            details={
                "service_file": str(service_path),
                "method": "systemd"
            }
        )

    def _install_cron(self) -> PersistenceResult:
        """Install using cron @reboot fallback."""
        cron_line = f"@reboot {self.python_path} {self.beacon_path} --config {self.config_path} {self.CRON_MARKER}"

        try:
            # Get current crontab
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )
            current_cron = result.stdout if result.returncode == 0 else ""

            # Check if already installed
            if self.CRON_MARKER in current_cron:
                return PersistenceResult(
                    success=True,
                    message="Persistence already installed (cron @reboot).",
                    status=PersistenceStatus.INSTALLED,
                    details={"method": "cron"}
                )

            # Add new cron entry
            new_cron = current_cron.rstrip() + "\n" + cron_line + "\n"

            result = subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return PersistenceResult(
                    success=False,
                    message=f"Failed to install cron job: {result.stderr}",
                    status=PersistenceStatus.ERROR
                )

            return PersistenceResult(
                success=True,
                message=f"[SUCCESS] Persistence installed successfully (cron fallback)\n\n"
                        f"Platform: Linux (cron @reboot)\n"
                        f"Status: installed\n\n"
                        f"The beacon will start automatically on reboot.\n"
                        f"Note: systemd is not available, using cron as fallback.\n\n"
                        f"To check status: tsushin-beacon --persistence status\n"
                        f"To remove: tsushin-beacon --persistence uninstall",
                status=PersistenceStatus.INSTALLED,
                details={"method": "cron"}
            )

        except FileNotFoundError:
            return PersistenceResult(
                success=False,
                message="cron is not available on this system.",
                status=PersistenceStatus.ERROR
            )
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to install cron job: {e}",
                status=PersistenceStatus.ERROR
            )

    def uninstall(self) -> PersistenceResult:
        results = []

        # Try to uninstall systemd service
        if self._has_systemd():
            result = self._uninstall_systemd()
            if result.success or result.status != PersistenceStatus.NOT_INSTALLED:
                results.append(result)

        # Try to uninstall cron job
        cron_result = self._uninstall_cron()
        if cron_result.success or cron_result.status != PersistenceStatus.NOT_INSTALLED:
            results.append(cron_result)

        if not results:
            return PersistenceResult(
                success=True,
                message="No persistence mechanism was installed.",
                status=PersistenceStatus.NOT_INSTALLED
            )

        # Return combined result
        all_success = all(r.success for r in results)
        messages = [r.message for r in results if r.message]

        return PersistenceResult(
            success=all_success,
            message="\n".join(messages) if messages else "[SUCCESS] Persistence removed.",
            status=PersistenceStatus.NOT_INSTALLED if all_success else PersistenceStatus.ERROR
        )

    def _uninstall_systemd(self) -> PersistenceResult:
        """Uninstall systemd service."""
        service_path = Path(self.get_service_file_path())
        user_flag = not self.system_level

        if not service_path.exists():
            return PersistenceResult(
                success=True,
                message="",
                status=PersistenceStatus.NOT_INSTALLED
            )

        # Stop service
        self._run_systemctl("stop", self.SERVICE_NAME, user=user_flag)

        # Disable service
        self._run_systemctl("disable", self.SERVICE_NAME, user=user_flag)

        # Remove service file
        try:
            if self.system_level:
                subprocess.run(["sudo", "rm", str(service_path)], check=True)
            else:
                service_path.unlink()
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to remove service file: {e}",
                status=PersistenceStatus.ERROR
            )

        # Reload systemd
        self._run_systemctl("daemon-reload", user=user_flag)

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Systemd service removed.\nService file removed: {service_path}",
            status=PersistenceStatus.NOT_INSTALLED,
            details={"method": "systemd", "service_file": str(service_path)}
        )

    def _uninstall_cron(self) -> PersistenceResult:
        """Uninstall cron job."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0 or self.CRON_MARKER not in result.stdout:
                return PersistenceResult(
                    success=True,
                    message="",
                    status=PersistenceStatus.NOT_INSTALLED
                )

            # Remove our cron entry
            new_cron = "\n".join(
                line for line in result.stdout.splitlines()
                if self.CRON_MARKER not in line
            ) + "\n"

            result = subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return PersistenceResult(
                    success=False,
                    message=f"Failed to remove cron job: {result.stderr}",
                    status=PersistenceStatus.ERROR
                )

            return PersistenceResult(
                success=True,
                message="[SUCCESS] Cron job removed.",
                status=PersistenceStatus.NOT_INSTALLED,
                details={"method": "cron"}
            )

        except FileNotFoundError:
            return PersistenceResult(
                success=True,
                message="",
                status=PersistenceStatus.NOT_INSTALLED
            )
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to check/remove cron job: {e}",
                status=PersistenceStatus.ERROR
            )

    def status(self) -> PersistenceResult:
        details = {}

        # Check systemd
        if self._has_systemd():
            systemd_status = self._get_systemd_status()
            if systemd_status:
                details["systemd"] = systemd_status

        # Check cron
        cron_status = self._get_cron_status()
        if cron_status:
            details["cron"] = cron_status

        if not details:
            return PersistenceResult(
                success=True,
                message="[STATUS] Tsushin Beacon Persistence\n\n"
                        "Status: NOT INSTALLED\n\n"
                        "No persistence mechanism is configured.",
                status=PersistenceStatus.NOT_INSTALLED,
                details=details
            )

        # Build status message
        lines = ["[STATUS] Tsushin Beacon Persistence\n"]

        if "systemd" in details:
            s = details["systemd"]
            lines.append(f"Platform: {self.platform_name}")
            lines.append(f"Service file: {self.get_service_file_path()}")
            lines.append(f"Installation: {s.get('enabled', 'unknown')}")
            lines.append(f"Service state: {s.get('active', 'unknown')}")
            if s.get('pid'):
                lines[-1] += f" (PID: {s['pid']})"

        if "cron" in details:
            lines.append("\nCron @reboot: installed")

        lines.append(f"\nConfiguration:")
        lines.append(f"  Config file: {self.config_path}")
        lines.append(f"  Server URL: {self.server_url}")
        lines.append(f"  API key: {self._redact_api_key(self.api_key)}")

        # Determine overall status
        if "systemd" in details:
            if details["systemd"].get("active") == "active":
                status = PersistenceStatus.RUNNING
            elif details["systemd"].get("enabled") == "enabled":
                status = PersistenceStatus.INSTALLED
            else:
                status = PersistenceStatus.STOPPED
        elif "cron" in details:
            status = PersistenceStatus.INSTALLED
        else:
            status = PersistenceStatus.NOT_INSTALLED

        return PersistenceResult(
            success=True,
            message="\n".join(lines),
            status=status,
            details=details
        )

    def _get_systemd_status(self) -> Optional[dict]:
        """Get systemd service status."""
        user_flag = not self.system_level
        service_path = Path(self.get_service_file_path())

        if not service_path.exists():
            return None

        status = {}

        # Check if enabled
        rc, stdout, _ = self._run_systemctl("is-enabled", self.SERVICE_NAME, user=user_flag)
        status["enabled"] = stdout.strip() if rc == 0 else "disabled"

        # Check if active
        rc, stdout, _ = self._run_systemctl("is-active", self.SERVICE_NAME, user=user_flag)
        status["active"] = stdout.strip()

        # Get PID if running
        if status["active"] == "active":
            rc, stdout, _ = self._run_systemctl("show", "-p", "MainPID", self.SERVICE_NAME, user=user_flag)
            if rc == 0 and "MainPID=" in stdout:
                pid = stdout.strip().split("=")[1]
                if pid != "0":
                    status["pid"] = pid

        return status

    def _get_cron_status(self) -> Optional[dict]:
        """Check if cron job is installed."""
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )
            if result.returncode == 0 and self.CRON_MARKER in result.stdout:
                return {"installed": True}
        except Exception:
            pass
        return None
