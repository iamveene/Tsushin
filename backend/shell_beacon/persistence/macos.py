"""
macOS persistence manager using LaunchAgent/LaunchDaemon.
"""

import os
import subprocess
import plistlib
from pathlib import Path
from typing import Optional, Dict, Any

from .base import BasePersistenceManager, PersistenceResult, PersistenceStatus


class MacOSPersistenceManager(BasePersistenceManager):
    """
    macOS persistence manager.

    User-level: ~/Library/LaunchAgents/com.tsushin.beacon.plist
    System-level: /Library/LaunchDaemons/com.tsushin.beacon.plist (requires root)
    """

    LABEL = "com.tsushin.beacon"

    @property
    def platform_name(self) -> str:
        if self.system_level:
            return "macOS (LaunchDaemon)"
        return "macOS (LaunchAgent)"

    def get_service_file_path(self) -> str:
        if self.system_level:
            return f"/Library/LaunchDaemons/{self.LABEL}.plist"
        return str(Path.home() / "Library" / "LaunchAgents" / f"{self.LABEL}.plist")

    def _get_log_dir(self) -> Path:
        """Get the log directory for stdout/stderr."""
        log_dir = Path.home() / ".tsushin" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def _generate_plist(self) -> Dict[str, Any]:
        """Generate LaunchAgent/LaunchDaemon plist content."""
        log_dir = self._get_log_dir()

        plist = {
            "Label": self.LABEL,
            "ProgramArguments": [
                self.python_path,
                self.beacon_path,
                "--config",
                self.config_path
            ],
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": str(log_dir / "beacon-stdout.log"),
            "StandardErrorPath": str(log_dir / "beacon-stderr.log"),
            "EnvironmentVariables": {
                "TSUSHIN_API_KEY": self.api_key,
                "TSUSHIN_SERVER_URL": self.server_url
            },
            "ThrottleInterval": 10,  # Don't restart more than once every 10 seconds
        }

        if self.system_level:
            # For LaunchDaemon, run as current user (optional: could be a dedicated user)
            plist["UserName"] = os.getenv("USER", "root")

        return plist

    def _run_launchctl(self, *args) -> tuple[int, str, str]:
        """Run launchctl command and return (returncode, stdout, stderr)."""
        cmd = ["launchctl"] + list(args)

        # System-level operations might need sudo
        if self.system_level and args and args[0] in ("load", "unload", "bootstrap", "bootout"):
            cmd = ["sudo"] + cmd

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
        plist_path = Path(self.get_service_file_path())

        # Create directory if needed
        plist_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate plist content
        plist_content = self._generate_plist()

        # Write plist file
        try:
            if self.system_level:
                # Write to temp file and sudo move
                import tempfile
                with tempfile.NamedTemporaryFile(mode='wb', suffix='.plist', delete=False) as f:
                    plistlib.dump(plist_content, f)
                    temp_path = f.name

                result = subprocess.run(
                    ["sudo", "cp", temp_path, str(plist_path)],
                    capture_output=True,
                    text=True
                )
                os.unlink(temp_path)

                if result.returncode != 0:
                    return PersistenceResult(
                        success=False,
                        message=f"Failed to write plist file (requires root): {result.stderr}",
                        status=PersistenceStatus.ERROR
                    )

                # Set correct permissions
                subprocess.run(["sudo", "chmod", "644", str(plist_path)], check=True)
                subprocess.run(["sudo", "chown", "root:wheel", str(plist_path)], check=True)
            else:
                with open(plist_path, 'wb') as f:
                    plistlib.dump(plist_content, f)

        except PermissionError:
            return PersistenceResult(
                success=False,
                message=f"Permission denied writing to {plist_path}.",
                status=PersistenceStatus.ERROR
            )
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to write plist file: {e}",
                status=PersistenceStatus.ERROR
            )

        # Unload first if already loaded (ignore errors)
        self._run_launchctl("unload", str(plist_path))

        # Load the service
        rc, stdout, stderr = self._run_launchctl("load", str(plist_path))
        if rc != 0:
            # On newer macOS, might need bootstrap instead
            if "load" in stderr or "bootstrap" in stderr.lower():
                domain = "system" if self.system_level else f"gui/{os.getuid()}"
                rc, stdout, stderr = self._run_launchctl("bootstrap", domain, str(plist_path))

            if rc != 0:
                return PersistenceResult(
                    success=False,
                    message=f"Failed to load service: {stderr}",
                    status=PersistenceStatus.ERROR,
                    details={"plist_path": str(plist_path)}
                )

        # Start the service
        rc, _, stderr = self._run_launchctl("start", self.LABEL)
        # start might fail if already running, that's OK

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Persistence installed successfully\n\n"
                    f"Platform: {self.platform_name}\n"
                    f"Service file: {plist_path}\n"
                    f"Status: enabled and running\n\n"
                    f"The beacon will now start automatically on {'boot' if self.system_level else 'login'}.\n\n"
                    f"To check status: tsushin-beacon --persistence status\n"
                    f"To remove: tsushin-beacon --persistence uninstall",
            status=PersistenceStatus.RUNNING,
            details={
                "plist_path": str(plist_path),
                "label": self.LABEL
            }
        )

    def uninstall(self) -> PersistenceResult:
        plist_path = Path(self.get_service_file_path())

        if not plist_path.exists():
            return PersistenceResult(
                success=True,
                message="No persistence mechanism was installed.",
                status=PersistenceStatus.NOT_INSTALLED
            )

        # Stop the service
        self._run_launchctl("stop", self.LABEL)

        # Unload the service
        rc, stdout, stderr = self._run_launchctl("unload", str(plist_path))
        if rc != 0:
            # Try bootout on newer macOS
            domain = "system" if self.system_level else f"gui/{os.getuid()}"
            self._run_launchctl("bootout", f"{domain}/{self.LABEL}")

        # Remove plist file
        try:
            if self.system_level:
                subprocess.run(["sudo", "rm", str(plist_path)], check=True)
            else:
                plist_path.unlink()
        except Exception as e:
            return PersistenceResult(
                success=False,
                message=f"Failed to remove plist file: {e}",
                status=PersistenceStatus.ERROR
            )

        return PersistenceResult(
            success=True,
            message=f"[SUCCESS] Persistence removed successfully\n\n"
                    f"The beacon will no longer start automatically.\n"
                    f"Service file removed: {plist_path}\n\n"
                    f"Note: The configuration file was preserved at {self.config_path}",
            status=PersistenceStatus.NOT_INSTALLED,
            details={"plist_path": str(plist_path)}
        )

    def status(self) -> PersistenceResult:
        plist_path = Path(self.get_service_file_path())
        details = {}

        if not plist_path.exists():
            return PersistenceResult(
                success=True,
                message="[STATUS] Tsushin Beacon Persistence\n\n"
                        "Status: NOT INSTALLED\n\n"
                        "No persistence mechanism is configured.",
                status=PersistenceStatus.NOT_INSTALLED
            )

        details["plist_path"] = str(plist_path)

        # Check if service is loaded and running
        rc, stdout, stderr = self._run_launchctl("list")
        service_info = self._parse_launchctl_list(stdout)

        if service_info:
            details["pid"] = service_info.get("pid")
            details["status_code"] = service_info.get("status")
            details["running"] = service_info.get("pid") not in (None, "-", "0", 0)
        else:
            details["running"] = False

        # Build status message
        lines = ["[STATUS] Tsushin Beacon Persistence\n"]
        lines.append(f"Platform: {self.platform_name}")
        lines.append(f"Service file: {plist_path}")
        lines.append(f"Installation: INSTALLED")

        if details.get("running"):
            lines.append(f"Service state: RUNNING (PID: {details.get('pid')})")
            status = PersistenceStatus.RUNNING
        else:
            lines.append("Service state: STOPPED")
            if details.get("status_code"):
                lines.append(f"Last exit code: {details.get('status_code')}")
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

    def _parse_launchctl_list(self, output: str) -> Optional[Dict[str, Any]]:
        """Parse launchctl list output to find our service."""
        for line in output.splitlines():
            if self.LABEL in line:
                parts = line.split()
                if len(parts) >= 3:
                    return {
                        "pid": parts[0] if parts[0] != "-" else None,
                        "status": parts[1] if parts[1] != "-" else None,
                        "label": parts[2]
                    }
        return None
