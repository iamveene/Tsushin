#!/usr/bin/env python3
"""
Tsushin Platform Installer

Installer for the Tsushin multi-agent AI platform.
Configures environment and deploys Docker containers.
User/org creation and AI provider setup are handled via the /setup UI wizard.

Requirements:
    - Python 3.8+
    - Docker and Docker Compose
    - Internet connection
"""

import argparse
import os
import sys
import re
import shutil
import socket
import secrets
import subprocess
import time
import getpass
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="install.py",
        description="Tsushin Platform Installer — deploy and configure the Tsushin multi-agent AI platform.",
        epilog="""
examples:
  python3 install.py                              Interactive mode (recommended for first install)
  python3 install.py --defaults                   Fully unattended with self-signed HTTPS
  python3 install.py --defaults --http            Unattended with HTTP only (no SSL)
  python3 install.py --defaults --domain app.io --email you@email.com
                                                  Unattended with Let's Encrypt SSL
  python3 install.py --port 9090                  Custom backend port (works in both modes)

modes:
  interactive (default)   Prompts for network config (ports, access type) and SSL mode.
                          Requires a TTY (terminal). If stdin is not a terminal, the installer
                          looks for a pre-existing .env file and skips prompts.

  --defaults              Fully unattended. Auto-generates .env with random secrets, detects the
                          machine's IP for remote access, and enables self-signed HTTPS.

  Both modes set up infrastructure only — no user accounts or API keys are created.
  SSL is handled by Caddy (auto Let's Encrypt or self-signed, no certbot needed).

after install:
  Open the URL shown at the end of install. The /setup wizard will guide you through
  creating your admin account, organization, and configuring AI provider API keys.
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--defaults",
        action="store_true",
        help="Fully unattended install with auto-generated secrets and self-signed HTTPS",
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Disable SSL (HTTP only). Only valid with --defaults. Insecure — use for isolated dev/test only",
    )
    parser.add_argument(
        "--domain",
        type=str,
        metavar="DOMAIN",
        help="Domain name for Let's Encrypt SSL (e.g., app.example.com). Only valid with --defaults",
    )
    parser.add_argument(
        "--email",
        type=str,
        metavar="EMAIL",
        help="Email for Let's Encrypt certificate notifications. Required with --domain",
    )
    parser.add_argument(
        "--le-staging",
        action="store_true",
        help="Use Let's Encrypt staging environment (for testing, avoids production rate limits). Only valid with --domain",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8081,
        metavar="PORT",
        help="Backend API port (default: 8081)",
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=3030,
        metavar="PORT",
        help="Frontend port (default: 3030)",
    )

    args = parser.parse_args()

    # Validation
    if args.http and args.domain:
        parser.error("--http and --domain are mutually exclusive")
    if (args.http or args.domain) and not args.defaults:
        parser.error("--http and --domain require --defaults mode")
    if args.domain and not args.email:
        parser.error("--domain requires --email for Let's Encrypt certificate notifications")
    if args.email and not args.domain:
        parser.error("--email requires --domain")
    if args.le_staging and not args.domain:
        parser.error("--le-staging requires --domain")

    return args

from platform_utils import (
    is_windows, is_linux, is_macos, is_root,
    set_directory_permissions, set_directory_ownership,
    get_real_user_info, enable_ansi_colors,
)

# Check Python version
if sys.version_info < (3, 8):
    print("Error: Python 3.8 or higher is required")
    sys.exit(1)

# Try to import required libraries
try:
    import requests
    from cryptography.fernet import Fernet
except ImportError:
    print("Installing required Python packages...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "requests", "cryptography"])
    import requests
    from cryptography.fernet import Fernet


# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text: str):
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.CYAN}{Colors.BOLD}{text:^60}{Colors.ENDC}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text: str):
    print(f"{Colors.GREEN}✓{Colors.ENDC} {text}")


def print_error(text: str):
    print(f"{Colors.RED}✗{Colors.ENDC} {text}")


def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠{Colors.ENDC}  {text}")


def print_info(text: str):
    print(f"{Colors.BLUE}ℹ{Colors.ENDC}  {text}")


def is_interactive() -> bool:
    """Check if stdin is connected to a terminal (interactive mode)."""
    try:
        return os.isatty(sys.stdin.fileno())
    except (AttributeError, ValueError, OSError):
        return False


def safe_input(prompt: str, default: str = "") -> str:
    """Read input safely, returning default in non-interactive mode or on EOF."""
    if not is_interactive():
        return default
    try:
        return input(prompt)
    except EOFError:
        return default


def safe_getpass(prompt: str, default: str = "") -> str:
    """Read password safely, returning default in non-interactive mode or on EOF."""
    if not is_interactive():
        return default
    try:
        return getpass.getpass(prompt)
    except EOFError:
        return default


class TsushinInstaller:
    def __init__(self, args=None):
        self.root_dir = Path(__file__).parent
        self.env_file = self.root_dir / ".env"
        self.backend_data_dir = self.root_dir / "backend" / "data"
        self.database_path = self.backend_data_dir / "agent.db"
        stack_name = (os.environ.get("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
        self.config = {"TSN_STACK_NAME": stack_name}
        self.interactive = is_interactive()
        self.args = args or argparse.Namespace(defaults=False, http=False, domain=None, port=8081, frontend_port=3030)
        # Set to True when the frontend Docker image must be rebuilt with
        # --no-cache (because NEXT_PUBLIC_API_URL changed and Next.js bakes
        # that value into the static build at image-build time).
        self._force_frontend_rebuild = False
        # Tracks whether generate_env_file() preserved a POSTGRES_PASSWORD
        # from an existing .env. If False and the postgres volume already
        # exists, the installer would crash with FATAL auth — BUG-582.
        self._preserved_existing_postgres_password = False

    @staticmethod
    def _normalize_ssl_mode(value: str) -> str:
        """Normalize legacy SSL mode aliases to the installer-supported set."""
        normalized = (value or "").strip().lower()
        if normalized in ("", "off", "none", "disabled"):
            return "disabled"
        return normalized

    def _resolve_auth_rate_limit(self) -> str:
        """
        Local/dev-friendly installs should not trip the production auth throttle.
        Public HTTPS installs keep the secure default.
        """
        ssl_mode = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))
        return "30/minute" if ssl_mode in ("disabled", "selfsigned") else "5/minute"

    @staticmethod
    def _resolve_disable_auth_rate_limit() -> str:
        """Auth throttling stays enabled by default unless the operator opts out."""
        return "false"

    def _read_env_file_vars(self) -> Dict[str, str]:
        """Parse the current .env file into a key/value dict."""
        env_vars = {}
        try:
            with open(self.env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, _, value = line.partition('=')
                        env_vars[key.strip()] = value.strip()
        except Exception as e:
            print_warning(f"Could not parse .env file: {e}")
        return env_vars

    def _load_config_from_env(self):
        """Load configuration values from an existing .env file for non-interactive mode."""
        env_vars = self._read_env_file_vars()

        # Map .env keys to config keys used by the installer
        self.config['TSN_APP_PORT'] = env_vars.get('TSN_APP_PORT', '8081')
        self.config['FRONTEND_PORT'] = env_vars.get('FRONTEND_PORT', '3030')
        self.config['TSN_STACK_NAME'] = env_vars.get('TSN_STACK_NAME', self.config.get('TSN_STACK_NAME', 'tsushin'))
        self.config['SSL_MODE'] = self._normalize_ssl_mode(env_vars.get('SSL_MODE', 'disabled'))
        self.config['SSL_DOMAIN'] = env_vars.get('SSL_DOMAIN', '')
        self.config['SSL_EMAIL'] = env_vars.get('SSL_EMAIL', '')
        # Persist the LE staging flag so non-interactive re-runs don't silently
        # flip production ACME when a previous run opted into staging (or vice
        # versa) — the Caddyfile generator reads SSL_LE_STAGING from config.
        self.config['SSL_LE_STAGING'] = env_vars.get('SSL_LE_STAGING', '')
        # Manual-cert paths — non-interactive re-run with SSL_MODE=manual
        # calls copy_manual_certs(), which indexes self.config['SSL_CERT_PATH']
        # / SSL_KEY_PATH. Without these here, the installer would KeyError on
        # re-run for any user who previously configured manual SSL.
        self.config['SSL_CERT_PATH'] = env_vars.get('SSL_CERT_PATH', '')
        self.config['SSL_KEY_PATH'] = env_vars.get('SSL_KEY_PATH', '')
        self.config['SSL_CERT_CHAIN_PATH'] = env_vars.get('SSL_CERT_CHAIN_PATH', '')
        self.config['TSN_AUTH_RATE_LIMIT'] = env_vars.get('TSN_AUTH_RATE_LIMIT', '')
        self.config['TSN_DISABLE_AUTH_RATE_LIMIT'] = env_vars.get('TSN_DISABLE_AUTH_RATE_LIMIT', '')
        self.config['NEXT_PUBLIC_API_URL'] = env_vars.get(
            'NEXT_PUBLIC_API_URL',
            f"http://localhost:{self.config['TSN_APP_PORT']}"
        )

    def _backfill_existing_env_defaults(self):
        """
        Older installs may predate newer derived settings. Append only missing
        runtime defaults so non-interactive updates inherit the current safe/dev
        behavior without rotating secrets or rewriting the whole file.
        """
        env_vars = self._read_env_file_vars()
        updates: Dict[str, str] = {}
        replacements: Dict[str, str] = {}

        if not env_vars.get('TSN_AUTH_RATE_LIMIT'):
            updates['TSN_AUTH_RATE_LIMIT'] = self._resolve_auth_rate_limit()
            self.config['TSN_AUTH_RATE_LIMIT'] = updates['TSN_AUTH_RATE_LIMIT']

        if not env_vars.get('TSN_DISABLE_AUTH_RATE_LIMIT'):
            updates['TSN_DISABLE_AUTH_RATE_LIMIT'] = self._resolve_disable_auth_rate_limit()
            self.config['TSN_DISABLE_AUTH_RATE_LIMIT'] = updates['TSN_DISABLE_AUTH_RATE_LIMIT']

        if not env_vars.get('TSN_SSL_MODE'):
            updates['TSN_SSL_MODE'] = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))

        if not updates and not replacements:
            return

        existing_content = self.env_file.read_text() if self.env_file.exists() else ""
        for key, value in replacements.items():
            existing_content = re.sub(
                rf"(?m)^{re.escape(key)}=.*$",
                f"{key}={value}",
                existing_content,
            )

        prefix = "" if not existing_content or existing_content.endswith("\n") else "\n"
        updated_content = existing_content
        if updates:
            updated_content += prefix + "\n".join(f"{key}={value}" for key, value in updates.items()) + "\n"

        with open(self.env_file, 'w') as f:
            f.write(updated_content)

        changed_keys = sorted({*updates.keys(), *replacements.keys()})
        print_info(
            "Updated existing .env with runtime defaults: "
            + ", ".join(changed_keys)
        )

    def check_existing_installation(self) -> str:
        """
        Check if Tsushin is already installed
        Returns: 'fresh', 'update', or 'destructive'
        """
        checks = {
            'docker_containers': self.check_docker_containers_running(),
            'env_file': self.env_file.exists(),
            'database': self.database_path.exists(),
            'port_8081': self.check_port_in_use(8081),
            'port_3030': self.check_port_in_use(3030)
        }

        if not any(checks.values()):
            return "fresh"

        print_warning("Existing Tsushin installation detected!")
        print(f"  - Running containers: {Colors.GREEN if checks['docker_containers'] else Colors.RED}{checks['docker_containers']}{Colors.ENDC}")
        print(f"  - .env file exists: {Colors.GREEN if checks['env_file'] else Colors.RED}{checks['env_file']}{Colors.ENDC}")
        print(f"  - Database exists: {Colors.GREEN if checks['database'] else Colors.RED}{checks['database']}{Colors.ENDC}")
        print(f"  - Port 8081 in use: {Colors.GREEN if checks['port_8081'] else Colors.RED}{checks['port_8081']}{Colors.ENDC}")
        print(f"  - Port 3030 in use: {Colors.GREEN if checks['port_3030'] else Colors.RED}{checks['port_3030']}{Colors.ENDC}")

        print("\nOptions:")
        print("1. EXIT (recommended to preserve data)")
        print("2. Update configuration only (keep data)")
        print("3. DESTRUCTIVE: Wipe and reinstall")

        choice = safe_input(f"\n{Colors.BOLD}Choice [1]:{Colors.ENDC} ").strip() or "1"

        if choice == "1":
            print_info("Installation cancelled to preserve existing instance.")
            sys.exit(0)
        elif choice == "2":
            return "update"
        elif choice == "3":
            print_warning("This will DELETE all existing data!")
            confirm = safe_input(f"{Colors.RED}Type 'DELETE EVERYTHING' to confirm:{Colors.ENDC} ")
            if confirm != "DELETE EVERYTHING":
                print_error("Confirmation failed. Exiting.")
                sys.exit(0)
            return "destructive"
        else:
            print_error("Invalid choice. Exiting.")
            sys.exit(0)

    def check_docker_containers_running(self) -> bool:
        """Check if Tsushin Docker containers are running"""
        try:
            result = subprocess.run(
                ["docker", "ps", "--filter", "name=tsushin", "--format", "{{.Names}}"],
                capture_output=True,
                text=True,
                check=False
            )
            return bool(result.stdout.strip())
        except FileNotFoundError:
            return False

    def check_port_in_use(self, port: int) -> bool:
        """Check if a port is in use"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(('localhost', port)) == 0

    def check_prerequisites(self):
        """Check if Docker and Docker Compose are installed"""
        print_header("Checking Prerequisites")

        # Check Docker
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True, check=True)
            docker_version = result.stdout.strip()
            print_success(f"Docker: {docker_version}")
        except (FileNotFoundError, subprocess.CalledProcessError):
            print_error("Docker is not installed or not in PATH")
            print_info("Install Docker: https://docs.docker.com/get-docker/")
            sys.exit(1)

        # Check Docker permissions (platform-specific)
        if is_linux():
            try:
                subprocess.run(["docker", "ps"], capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError as e:
                if "permission denied" in e.stderr.lower():
                    print_error("Docker permission denied")
                    print_warning("On Linux, Docker requires sudo or docker group membership")
                    print_info("Solutions:")
                    print_info("  1. Run with sudo: sudo python3 install.py")
                    print_info("  2. Add user to docker group: sudo usermod -aG docker $USER && newgrp docker")
                    sys.exit(1)
        elif is_windows():
            try:
                subprocess.run(["docker", "ps"], capture_output=True, text=True, check=True)
            except subprocess.CalledProcessError:
                print_error("Docker is not accessible")
                print_info("Ensure Docker Desktop is running (check the system tray icon)")
                sys.exit(1)

        # Check Docker Compose v2 (required — v1 is no longer supported).
        # BuildKit cache mounts in backend/Dockerfile require Compose v2,
        # which is bundled with Docker Desktop >=20.10 as the `docker compose` plugin.
        try:
            result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, check=True)
            compose_version = result.stdout.strip()
            print_success(f"Docker Compose: {compose_version}")
            self.docker_compose_cmd = ["docker", "compose"]
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Fall back to checking for legacy docker-compose v1 and error out with guidance.
            try:
                result = subprocess.run(["docker-compose", "--version"], capture_output=True, text=True, check=True)
                print_error("docker-compose v1 is no longer supported.")
                print_info("Please install Docker Compose v2 (bundled with Docker Desktop >=20.10) and re-run the installer.")
                print_info(f"Detected: {result.stdout.strip()}")
                sys.exit(1)
            except (FileNotFoundError, subprocess.CalledProcessError):
                print_error("Docker Compose v2 is not installed")
                print_info("Install Docker Compose v2: https://docs.docker.com/compose/install/")
                sys.exit(1)

        # Check Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print_success(f"Python: {python_version}")

        print()

    def prompt_for_configuration(self, mode: str):
        """
        Interactive prompts for infrastructure configuration only.
        User/org creation is handled by the /setup UI wizard after install.

        Args:
            mode: 'fresh', 'update', or 'destructive'
        """
        print_header("Configuration Setup")

        # Network Configuration
        print(f"{Colors.BOLD}Network Configuration{Colors.ENDC}\n")

        default_port = str(self.args.port)
        default_frontend_port = str(self.args.frontend_port)

        backend_port = self.prompt_with_validation(
            f"Enter Backend Port [{default_port}]: ",
            default=default_port,
            validator=lambda x: 1024 <= int(x) <= 65535,
            error_msg="Port must be between 1024 and 65535"
        )
        self.config['TSN_APP_PORT'] = backend_port

        frontend_port = self.prompt_with_validation(
            f"Enter Frontend Port [{default_frontend_port}]: ",
            default=default_frontend_port,
            validator=lambda x: 1024 <= int(x) <= 65535 and int(x) != int(backend_port),
            error_msg="Port must be between 1024 and 65535 and different from backend port"
        )
        self.config['FRONTEND_PORT'] = frontend_port

        print()

        # Public Access Configuration
        print(f"{Colors.BOLD}Public Access Configuration{Colors.ENDC}\n")
        print_info("If you're accessing this installation from a different machine (remote VM, cloud server),")
        print_info("you need to configure the public hostname or IP address.")
        print()

        access_type = safe_input(f"{Colors.BOLD}How will you access this installation? [localhost/remote]:{Colors.ENDC} ").strip().lower()

        if access_type == "remote":
            print()
            print_info("Enter the hostname or IP address you'll use to access this installation.")
            print_info("Examples: 10.211.55.5, myserver.local, app.example.com")
            print()

            public_host = self.prompt_with_validation(
                "Enter public hostname or IP address: ",
                validator=lambda x: len(x) > 0 and ('.' in x or ':' in x),
                error_msg="Please enter a valid hostname or IP address"
            )
        else:
            public_host = "localhost"

        self.config['ACCESS_TYPE'] = access_type
        self.config['PUBLIC_HOST'] = public_host

        print()

        # SSL/HTTPS Configuration
        self.prompt_ssl_configuration(access_type, public_host, backend_port)

        # Set final URLs based on SSL mode
        self._resolve_urls(access_type, public_host, backend_port)

    def _resolve_urls(self, access_type: str, public_host: str, backend_port: str):
        """Resolve NEXT_PUBLIC_API_URL and frontend_url based on SSL mode and access type."""
        ssl_mode = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))
        if ssl_mode != 'disabled':
            domain = self.config['SSL_DOMAIN']
            self.config['NEXT_PUBLIC_API_URL'] = f"https://{domain}"
            print_success(f"Frontend will connect via HTTPS: {self.config['NEXT_PUBLIC_API_URL']}")
        else:
            if access_type == "remote":
                self.config['NEXT_PUBLIC_API_URL'] = f"http://{public_host}:{backend_port}"
            else:
                self.config['NEXT_PUBLIC_API_URL'] = f"http://localhost:{backend_port}"
            print_info(f"Frontend will connect to backend at: {self.config['NEXT_PUBLIC_API_URL']}")
        print()

    def prompt_with_validation(self, prompt: str, default: str = "", validator=None, error_msg: str = "", optional: bool = False, mask: bool = False) -> str:
        """
        Prompt user for input with validation

        Args:
            prompt: Prompt text
            default: Default value
            validator: Validation function
            error_msg: Error message for invalid input
            optional: Whether the input is optional
            mask: Whether to mask the input (for sensitive data)

        Returns:
            User input (validated)
        """
        while True:
            if mask:
                value = safe_getpass(f"{Colors.BOLD}{prompt}{Colors.ENDC}", default).strip() or default
            else:
                value = safe_input(f"{Colors.BOLD}{prompt}{Colors.ENDC}", default).strip() or default

            if not value and optional:
                return ""

            if not value:
                print_error(error_msg or "This field is required")
                continue

            if validator:
                try:
                    if validator(value):
                        return value
                    else:
                        print_error(error_msg)
                except:
                    print_error(error_msg)
            else:
                return value

    def prompt_ssl_configuration(self, access_type: str, public_host: str, backend_port: str):
        """Prompt for SSL/HTTPS configuration"""
        print(f"{Colors.BOLD}SSL/HTTPS Configuration{Colors.ENDC}\n")

        # Determine available SSL modes based on access type
        # HTTPS is the default — Tsushin is a security-first platform
        if access_type == "localhost":
            print_info("SSL modes available for localhost installations:")
            print("  1. Self-signed certificate (HTTPS) — recommended [default]")
            print("  2. No SSL (HTTP only) — development/testing only")
            print()
            choice = safe_input(f"{Colors.BOLD}SSL Mode [1]:{Colors.ENDC} ").strip() or "1"
            mode_map = {"1": "selfsigned", "2": "disabled"}
        else:
            print_info("SSL modes available for remote installations:")
            print("  1. Auto HTTPS (Let's Encrypt) — recommended [default]")
            print("  2. Self-signed certificate — development/testing")
            print("  3. Manual certificates — provide your own .crt and .key files")
            print("  4. No SSL (HTTP only) — development only (insecure)")
            print()
            choice = safe_input(f"{Colors.BOLD}SSL Mode [1]:{Colors.ENDC} ").strip() or "1"
            mode_map = {"1": "letsencrypt", "2": "selfsigned", "3": "manual", "4": "disabled"}

        ssl_mode = mode_map.get(choice, "selfsigned")
        self.config['SSL_MODE'] = ssl_mode

        if ssl_mode == "disabled":
            print_warning("HTTP mode is insecure — credentials and API keys will be transmitted in plaintext.")
            print_warning("Only use HTTP for isolated development/testing environments.")
            return

        # Domain/hostname prompt
        if ssl_mode == "letsencrypt":
            self._prompt_letsencrypt(public_host)
        elif ssl_mode == "manual":
            self._prompt_manual_certs(public_host)
        elif ssl_mode == "selfsigned":
            self._prompt_selfsigned(public_host)

        print_success(f"SSL mode: {ssl_mode} (domain: {self.config.get('SSL_DOMAIN', 'N/A')})")

    def _prompt_letsencrypt(self, public_host: str):
        """Prompt for Let's Encrypt configuration"""
        print()
        print_info("Let's Encrypt auto-provisions free SSL certificates.")
        print_info("Requirements: domain name pointing to this server, ports 80 and 443 open.")
        print()

        # Domain
        default_domain = public_host if '.' in public_host and not self._is_ip(public_host) else ""
        domain_prompt = f"Enter domain name for SSL certificate"
        if default_domain:
            domain_prompt += f" [{default_domain}]"
        domain_prompt += ": "

        domain = self.prompt_with_validation(
            domain_prompt,
            default=default_domain,
            validator=lambda x: '.' in x and not self._is_ip(x),
            error_msg="Must be a valid domain name (e.g., app.example.com), not an IP address"
        )
        self.config['SSL_DOMAIN'] = domain

        # Email for Let's Encrypt
        email = self.prompt_with_validation(
            "Enter email for Let's Encrypt notifications: ",
            validator=lambda x: re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', x) is not None,
            error_msg="Please enter a valid email address"
        )
        self.config['SSL_EMAIL'] = email

        # Staging option — use LE staging to avoid production rate limits when testing
        staging_choice = safe_input(
            f"{Colors.BOLD}Use Let's Encrypt staging (for testing, avoids rate limits)? [y/N]:{Colors.ENDC} "
        ).strip().lower()
        if staging_choice == 'y':
            self.config['SSL_LE_STAGING'] = 'true'
            print_warning("Staging certs are not trusted by browsers — switch to production mode for real deploys.")

        # Port availability check
        for port in [80, 443]:
            if self.check_port_in_use(port):
                print_warning(f"Port {port} is currently in use!")
                print_info("Let's Encrypt requires ports 80 and 443 to be available.")
                confirm = safe_input(f"{Colors.BOLD}Continue anyway? [y/N]:{Colors.ENDC} ").strip().lower()
                if confirm != 'y':
                    print_info("Switching to disabled SSL mode.")
                    self.config['SSL_MODE'] = 'disabled'
                    return

        # DNS + reachability validation
        self._validate_domain_dns(domain)

    def _prompt_manual_certs(self, public_host: str):
        """Prompt for manual certificate configuration"""
        print()
        print_info("Provide paths to your existing SSL certificate and private key.")
        print_info("An optional intermediate/chain bundle may be supplied if your CA requires it.")
        print()

        domain = self.prompt_with_validation(
            f"Enter domain name [{public_host}]: ",
            default=public_host,
            validator=lambda x: len(x) > 0,
            error_msg="Domain name is required"
        )
        self.config['SSL_DOMAIN'] = domain

        cert_path = self.prompt_with_validation(
            "Path to SSL certificate (.crt or .pem): ",
            validator=lambda x: Path(x).expanduser().exists() and Path(x).expanduser().is_file(),
            error_msg="File not found. Please provide a valid path to the certificate file."
        )
        self.config['SSL_CERT_PATH'] = str(Path(cert_path).expanduser().resolve())

        key_path = self.prompt_with_validation(
            "Path to SSL private key (.key or .pem): ",
            validator=lambda x: Path(x).expanduser().exists() and Path(x).expanduser().is_file(),
            error_msg="File not found. Please provide a valid path to the key file."
        )
        self.config['SSL_KEY_PATH'] = str(Path(key_path).expanduser().resolve())

        # Optional chain/intermediate bundle (pressing Enter skips)
        chain_raw = safe_input(
            f"{Colors.BOLD}Path to certificate chain/intermediate bundle (optional, Enter to skip):{Colors.ENDC} "
        ).strip()
        if chain_raw:
            chain_expanded = Path(chain_raw).expanduser()
            if not chain_expanded.exists() or not chain_expanded.is_file():
                print_warning(f"Chain file not found: {chain_raw} — continuing without chain.")
            else:
                self.config['SSL_CERT_CHAIN_PATH'] = str(chain_expanded.resolve())

        # Validate the cert/key pair BEFORE deploy. Hard errors for mismatch
        # or expired cert; warn-and-confirm for domain coverage.
        ok, errors, warnings = self._validate_cert_pair(
            cert_path=Path(self.config['SSL_CERT_PATH']),
            key_path=Path(self.config['SSL_KEY_PATH']),
            chain_path=Path(self.config['SSL_CERT_CHAIN_PATH']) if self.config.get('SSL_CERT_CHAIN_PATH') else None,
            domain=domain,
        )
        for w in warnings:
            print_warning(w)
        if not ok:
            for e in errors:
                print_error(e)
            print_info("Re-run the installer with valid certificates, or choose a different SSL mode.")
            sys.exit(1)

    def _validate_cert_pair(self, cert_path: Path, key_path: Path,
                             chain_path: Optional[Path], domain: str):
        """Validate a user-provided cert/key pair before deployment.

        Checks (hard errors vs warnings):
          - Cert and key parse as PEM                  → hard error
          - Cert public key matches private key         → hard error
          - Cert is not expired                         → hard error
          - Cert expires within 30 days                 → warning
          - Cert SAN/CN covers the configured domain    → warning (confirm)
          - Chain (if provided) parses and issuer chain  → hard error on malformed

        Returns (ok, errors, warnings).
        """
        errors: List[str] = []
        warnings: List[str] = []

        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import serialization
            from cryptography.x509.oid import NameOID, ExtensionOID
            import ipaddress
        except Exception as exc:  # pragma: no cover - installer bootstraps cryptography
            errors.append(f"cryptography library unavailable: {exc}")
            return False, errors, warnings

        # Load cert
        try:
            cert_bytes = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_bytes)
        except Exception as exc:
            errors.append(f"Certificate failed to parse as PEM: {exc}")
            return False, errors, warnings

        # Load key (no password support — match existing behavior)
        try:
            key_bytes = key_path.read_bytes()
            private_key = serialization.load_pem_private_key(key_bytes, password=None)
        except TypeError:
            errors.append("Private key appears to be passphrase-protected. Tsushin requires an unencrypted key.")
            return False, errors, warnings
        except Exception as exc:
            errors.append(f"Private key failed to parse as PEM: {exc}")
            return False, errors, warnings

        # Key/cert match — compare public key serialized form (works for RSA/EC/Ed25519)
        try:
            cert_pub = cert.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            key_pub = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.DER,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            if cert_pub != key_pub:
                errors.append("Certificate and private key do not match (public keys differ).")
        except Exception as exc:
            errors.append(f"Could not compare certificate and key public keys: {exc}")

        # Expiry check — prefer timezone-aware attributes (cryptography >=42), fall back otherwise.
        try:
            not_after = getattr(cert, 'not_valid_after_utc', None) or cert.not_valid_after
            if not_after.tzinfo is None:
                from datetime import timezone
                not_after = not_after.replace(tzinfo=timezone.utc)
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            if not_after <= now:
                errors.append(f"Certificate has expired (notAfter={not_after.isoformat()}).")
            elif not_after - now < timedelta(days=30):
                warnings.append(
                    f"Certificate expires in less than 30 days (notAfter={not_after.isoformat()})."
                )
        except Exception as exc:
            warnings.append(f"Could not determine certificate expiry: {exc}")

        # Domain coverage — walk SAN (DNSName for hostnames, IPAddress for IPs), fall back to CN
        try:
            is_ip_domain = self._is_ip(domain)
            covered = False
            try:
                san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                san = san_ext.value
                if is_ip_domain:
                    try:
                        target_ip = ipaddress.ip_address(domain)
                        covered = target_ip in san.get_values_for_type(x509.IPAddress)
                    except ValueError:
                        covered = False
                else:
                    dns_names = [n.lower() for n in san.get_values_for_type(x509.DNSName)]
                    target = domain.lower()
                    covered = target in dns_names or any(
                        n.startswith('*.') and target.endswith(n[1:]) for n in dns_names
                    )
            except x509.ExtensionNotFound:
                covered = False

            if not covered:
                # Fall back to CN
                try:
                    cn_attrs = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
                    cn = cn_attrs[0].value.lower() if cn_attrs else ""
                    if cn and cn == domain.lower():
                        covered = True
                except Exception:
                    pass

            if not covered:
                warnings.append(
                    f"Certificate does not cover the configured domain '{domain}' (checked SAN and CN). "
                    "Browsers will reject it. Continue only if you are certain this is correct."
                )
                confirm = safe_input(
                    f"{Colors.BOLD}Proceed with mismatched certificate? [y/N]:{Colors.ENDC} "
                ).strip().lower()
                if confirm != 'y':
                    errors.append("User declined to proceed with a domain-mismatched certificate.")
        except Exception as exc:
            warnings.append(f"Could not verify certificate domain coverage: {exc}")

        # Optional chain validation
        if chain_path is not None:
            try:
                chain_bytes = chain_path.read_bytes()
                chain_certs = x509.load_pem_x509_certificates(chain_bytes)
                if not chain_certs:
                    errors.append(f"Chain file is empty or contains no PEM certificates: {chain_path}")
                else:
                    if cert.issuer != chain_certs[0].subject:
                        warnings.append(
                            "Leaf certificate issuer does not match the first certificate in the chain. "
                            "Caddy may still accept it, but the chain order is unusual."
                        )
            except Exception as exc:
                errors.append(f"Chain file failed to parse: {exc}")

        return (len(errors) == 0), errors, warnings

    def _prompt_selfsigned(self, public_host: str):
        """Prompt for self-signed certificate configuration"""
        print()
        print_info("A self-signed certificate will be generated for development/testing.")
        print_warning("Browsers will show a security warning with self-signed certificates.")
        print()

        domain = self.prompt_with_validation(
            f"Enter hostname for certificate [{public_host}]: ",
            default=public_host,
            validator=lambda x: len(x) > 0,
            error_msg="Hostname is required"
        )
        self.config['SSL_DOMAIN'] = domain

    def _is_ip(self, value: str) -> bool:
        """Check if a string looks like an IP address"""
        try:
            socket.inet_pton(socket.AF_INET, value)
            return True
        except socket.error:
            pass
        try:
            socket.inet_pton(socket.AF_INET6, value)
            return True
        except socket.error:
            return False

    def _has_stale_ip_dns_san(self, cert_path: Path, ip_domain: str) -> bool:
        """Return True if cert at cert_path encodes ip_domain as a DNSName SAN.

        This detects the pre-fix behaviour where the installer emitted
        ``DNS:10.x.x.x`` instead of ``IP:10.x.x.x`` — an RFC 5280 violation
        that browsers reject. Used to trigger one-time auto-regeneration on
        re-runs of affected installs. Returns False on any parse error or if
        the cert correctly encodes the IP as an iPAddress SAN.
        """
        try:
            from cryptography import x509
            from cryptography.x509.oid import ExtensionOID
            import ipaddress

            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            try:
                san_ext = cert.extensions.get_extension_for_oid(
                    ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                )
            except x509.ExtensionNotFound:
                return False
            san = san_ext.value
            # If the IP correctly appears as iPAddress, no regen needed.
            try:
                target_ip = ipaddress.ip_address(ip_domain)
                if target_ip in san.get_values_for_type(x509.IPAddress):
                    return False
            except ValueError:
                return False
            # If it appears (incorrectly) as DNSName, it's the stale cert.
            dns_values = [str(v).lower() for v in san.get_values_for_type(x509.DNSName)]
            return ip_domain.lower() in dns_values
        except Exception:
            # Best-effort only — errors mean we leave the existing cert alone.
            return False

    def _get_stack_name(self) -> str:
        return (self.config.get('TSN_STACK_NAME') or 'tsushin').strip() or 'tsushin'

    def _get_caddy_stack_dir(self) -> Path:
        return self.root_dir / "caddy" / self._get_stack_name()

    def _get_caddy_legacy_dir(self) -> Path:
        return self.root_dir / "caddy"

    def _write_caddy_artifact(self, relative_path: str, content: str) -> Path:
        stack_path = self._get_caddy_stack_dir() / relative_path
        stack_path.parent.mkdir(parents=True, exist_ok=True)
        stack_path.write_text(content)

        if self._get_stack_name() == "tsushin":
            legacy_path = self._get_caddy_legacy_dir() / relative_path
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            legacy_path.write_text(content)

        return stack_path

    def _sync_cert_files(self, filenames: List[str]):
        """Mirror cert files from caddy/{stack}/certs/ to legacy caddy/certs/.

        The legacy path is kept in sync only when the stack name is the
        default ``tsushin`` — custom stack names do not touch legacy paths.
        Reduces inline duplication in self-signed / manual cert flows.
        """
        if self._get_stack_name() != "tsushin":
            return
        stack_certs = self._get_caddy_stack_dir() / "certs"
        legacy_certs = self._get_caddy_legacy_dir() / "certs"
        legacy_certs.mkdir(parents=True, exist_ok=True)
        for name in filenames:
            src = stack_certs / name
            if src.exists():
                shutil.copy(src, legacy_certs / name)

    def _validate_domain_dns(self, domain: str):
        """Validate that a domain resolves via DNS and is reachable.

        Performs three checks (all advisory — any failure prompts the user):
          1. DNS resolution (A/AAAA)
          2. Resolved IPs match this server's public IP (detected via ipify)
          3. HTTP reachability on port 80 (ACME HTTP-01 challenge path)

        Common valid configurations (CNAME via CDN, Cloudflare proxy, NAT)
        may fail check #2 or #3 but still work for ACME — so these are
        warnings, not blockers.
        """
        # 1. DNS resolution
        try:
            resolved = socket.getaddrinfo(domain, None)
            resolved_ips = set(addr[4][0] for addr in resolved)
            print_success(f"Domain {domain} resolves to: {', '.join(sorted(resolved_ips))}")
        except socket.gaierror:
            print_warning(f"Domain {domain} does not resolve (DNS lookup failed).")
            print_warning("Let's Encrypt will fail if the domain doesn't point to this server.")
            confirm = safe_input(f"{Colors.BOLD}Continue anyway? [y/N]:{Colors.ENDC} ").strip().lower()
            if confirm != 'y':
                print_info("Switching to disabled SSL mode.")
                self.config['SSL_MODE'] = 'disabled'
            return

        # 2. Public IP comparison
        server_public_ip = None
        try:
            server_public_ip = requests.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            # Network/endpoint unavailable — skip silently, don't block install
            pass

        if server_public_ip:
            if server_public_ip not in resolved_ips:
                print_warning(
                    f"Domain resolves to {', '.join(sorted(resolved_ips))} "
                    f"but this server's public IP is {server_public_ip}."
                )
                print_info(
                    "This can be valid (CDN/CNAME/Cloudflare proxy) but often indicates DNS is "
                    "pointing at the wrong host. ACME HTTP-01 will fail unless the domain routes to this server."
                )
                confirm = safe_input(f"{Colors.BOLD}Continue anyway? [y/N]:{Colors.ENDC} ").strip().lower()
                if confirm != 'y':
                    print_info("Switching to disabled SSL mode.")
                    self.config['SSL_MODE'] = 'disabled'
                    return
            else:
                print_success(f"Public IP ({server_public_ip}) matches one of the resolved addresses.")

        # 3. HTTP reachability on port 80 (what ACME HTTP-01 uses)
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            requests.head(
                f"http://{domain}/",
                timeout=5,
                allow_redirects=False,
                # nosemgrep: python.requests.security.disabled-cert-validation.disabled-cert-validation
                verify=False,
            )
            print_success(f"HTTP reachability to {domain} confirmed (port 80 responds).")
        except requests.exceptions.ConnectionError:
            print_warning(
                f"Could not reach http://{domain}/ — ACME HTTP-01 requires port 80 open to the internet."
            )
            print_info("If your server is behind a firewall/NAT, ensure port 80 is forwarded.")
            confirm = safe_input(f"{Colors.BOLD}Continue anyway? [y/N]:{Colors.ENDC} ").strip().lower()
            if confirm != 'y':
                print_info("Switching to disabled SSL mode.")
                self.config['SSL_MODE'] = 'disabled'
        except Exception:
            # Timeouts, redirect handling quirks, etc. — don't block
            pass

    def generate_caddyfile(self):
        """Generate Caddy reverse proxy configuration based on SSL mode.

        v0.6.0 Remote Access: emits an additional :80 site block using the same
        routing snippet so cloudflared (running inside the backend container)
        can forward Cloudflare Tunnel requests to `{stack}-proxy:80`. Without
        this, tunnel traffic would bypass Caddy's /api routing and the
        frontend's API calls would 502.
        """
        ssl_mode = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))
        if ssl_mode == 'disabled':
            return

        caddyfile_path = self._get_caddy_stack_dir() / "Caddyfile"
        domain = self.config.get('SSL_DOMAIN', 'localhost')
        stack_name = self._get_stack_name()
        backend_host = f"{stack_name}-backend:8081"
        frontend_host = f"{stack_name}-frontend:3030"

        # Reusable snippet — imported by both the main HTTPS site and the
        # HTTP :80 site used by the Cloudflare Tunnel (v0.6.0 Remote Access).
        snippet_block = f"""(tsushin_routes) {{
    header Strict-Transport-Security "max-age=31536000; includeSubDomains"
    handle /api/* {{
        reverse_proxy {backend_host}
    }}
    handle /ws/* {{
        reverse_proxy {backend_host}
    }}
    handle {{
        reverse_proxy {frontend_host}
    }}
}}"""

        remote_access_block = """# v0.6.0 Remote Access (Cloudflare Tunnel): cloudflared forwards requests
# from the public tunnel hostname to this proxy on plain HTTP inside the
# container network. Cloudflare terminates TLS at the edge.
:80 {
    import tsushin_routes
}"""

        if ssl_mode == 'letsencrypt':
            email = self.config.get('SSL_EMAIL', '')
            # Opt in to LE staging when requested — avoids production rate limits
            # (5 failed validations per account, per hostname, per hour).
            staging_enabled = str(self.config.get('SSL_LE_STAGING', '')).lower() in ('true', '1', 'yes')
            global_lines = [f"    email {email}"]
            if staging_enabled:
                global_lines.append("    acme_ca https://acme-staging-v02.api.letsencrypt.org/directory")
            global_block = "{\n" + "\n".join(global_lines) + "\n}\n\n"
            caddyfile_content = (
                f"{global_block}"
                f"{snippet_block}\n\n"
                f"{domain} {{\n    import tsushin_routes\n}}\n\n"
                f"{remote_access_block}\n"
            )

        elif ssl_mode == 'manual':
            caddyfile_content = (
                f"{snippet_block}\n\n"
                f"{domain} {{\n"
                f"    tls /etc/caddy/certs/cert.pem /etc/caddy/certs/key.pem\n"
                f"    import tsushin_routes\n}}\n\n"
                f"{remote_access_block}\n"
            )

        elif ssl_mode == 'selfsigned':
            # default_sni ensures Caddy serves the cert even when clients don't
            # send SNI (e.g., curl/browsers connecting via bare IP address).
            # Caddy rejects IP literals in `default_sni` — fall back to
            # `localhost` when the domain is an IP. The site-block label is
            # still the IP (Caddy accepts IPs as site addresses).
            sni_target = 'localhost' if self._is_ip(domain) else domain
            global_block = f"{{\n    default_sni {sni_target}\n}}\n\n"
            caddyfile_content = (
                f"{global_block}"
                f"{snippet_block}\n\n"
                f"{domain} {{\n    tls internal\n    import tsushin_routes\n}}\n\n"
                f"{remote_access_block}\n"
            )

        else:
            return

        generated_path = self._write_caddy_artifact("Caddyfile", caddyfile_content)
        print_success(f"Caddy configuration generated: {generated_path.relative_to(self.root_dir)}")

    def generate_self_signed_cert(self):
        """Generate self-signed SSL certificate for development"""
        ssl_mode = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))
        if ssl_mode != 'selfsigned':
            return

        certs_dir = self._get_caddy_stack_dir() / "certs"
        cert_path = certs_dir / "selfsigned.crt"
        key_path = certs_dir / "selfsigned.key"
        domain = self.config.get('SSL_DOMAIN', 'localhost')

        if cert_path.exists() and key_path.exists():
            # One-time migration for installs affected by the DNS-for-IP SAN
            # bug: when the configured domain is an IP literal and the existing
            # cert encodes that IP as a DNSName SAN entry (invalid per RFC
            # 5280), delete the stale pair and fall through to regeneration.
            # This makes the IP SAN fix reach existing installs automatically
            # instead of requiring users to manually remove the broken cert.
            if self._is_ip(domain) and self._has_stale_ip_dns_san(cert_path, domain):
                print_warning(
                    f"Existing self-signed cert encodes IP '{domain}' as a DNSName SAN "
                    "(invalid per RFC 5280). Regenerating with IP SAN."
                )
                try:
                    cert_path.unlink()
                    key_path.unlink()
                except Exception as exc:
                    print_warning(f"Could not remove stale cert files: {exc}")
                    return
            else:
                print_info("Self-signed certificates already exist, skipping generation.")
                return

        certs_dir.mkdir(parents=True, exist_ok=True)

        # Check for openssl
        try:
            subprocess.run(["openssl", "version"], capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            print_warning("OpenSSL not found. Caddy will generate its own self-signed certificate.")
            print_info("Using Caddy's 'tls internal' directive instead.")
            return

        # Build subjectAltName: use IP: entry when domain is an IP literal,
        # DNS: when it's a hostname. RFC 5280 requires IP addresses in
        # iPAddress SAN entries — DNS:10.0.0.1 is invalid and browsers will
        # reject it (NET::ERR_CERT_COMMON_NAME_INVALID) or fall back to CN.
        if self._is_ip(domain):
            primary_san = f"IP:{domain}"
        else:
            primary_san = f"DNS:{domain}"
        san_entries = [primary_san, "DNS:localhost", "IP:127.0.0.1", "IP:::1"]
        san_value = ",".join(san_entries)

        cmd = [
            "openssl", "req", "-x509", "-nodes",
            "-days", "365",
            "-newkey", "rsa:2048",
            "-keyout", str(key_path),
            "-out", str(cert_path),
            "-subj", f"/CN={domain}/O=Tsushin Dev/C=US",
            "-addext", f"subjectAltName={san_value}"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            self._sync_cert_files(["selfsigned.crt", "selfsigned.key"])
            print_success("Self-signed certificate generated")
        else:
            print_warning(f"Could not generate certificate: {result.stderr}")
            print_info("Caddy will generate its own self-signed certificate using 'tls internal'.")

    def copy_manual_certs(self):
        """Copy user-provided certificates into caddy/{stack}/certs/.

        When an optional intermediate/chain bundle is supplied via
        SSL_CERT_CHAIN_PATH, the leaf cert and chain are concatenated into
        the destination ``cert.pem`` (Caddy reads a single bundled PEM).
        """
        ssl_mode = self.config.get('SSL_MODE', 'disabled')
        if ssl_mode != 'manual':
            return

        certs_dir = self._get_caddy_stack_dir() / "certs"
        certs_dir.mkdir(parents=True, exist_ok=True)

        cert_src = Path(self.config['SSL_CERT_PATH'])
        key_src = Path(self.config['SSL_KEY_PATH'])
        chain_src_str = self.config.get('SSL_CERT_CHAIN_PATH')

        dest_cert = certs_dir / "cert.pem"
        dest_key = certs_dir / "key.pem"

        # Write leaf cert, optionally with chain appended
        cert_bytes = cert_src.read_bytes()
        if chain_src_str:
            chain_src = Path(chain_src_str)
            # Ensure newline separation between PEM blocks
            if not cert_bytes.endswith(b"\n"):
                cert_bytes += b"\n"
            cert_bytes += chain_src.read_bytes()
        dest_cert.write_bytes(cert_bytes)

        shutil.copy(key_src, dest_key)
        self._sync_cert_files(["cert.pem", "key.pem"])

        if chain_src_str:
            print_success("SSL certificates (with chain) copied to caddy/certs/")
        else:
            print_success("SSL certificates copied to caddy/certs/")

    def prepare_data_directories(self):
        """Create required data directories with proper permissions"""
        print_header("Preparing Data Directories")

        directories = [
            self.backend_data_dir,
            self.backend_data_dir / "workspace",
            self.backend_data_dir / "chroma",
            self.backend_data_dir / "backups",
            self.root_dir / "logs" / "backend",
            self._get_caddy_stack_dir() / "certs",
        ]

        if self._get_stack_name() == "tsushin":
            directories.append(self.root_dir / "caddy" / "certs")

        for dir_path in directories:
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                # Set world-writable permissions for Docker containers
                # This is needed because toolbox containers run as UID 1000
                # No-op on Windows (Docker Desktop handles permissions)
                set_directory_permissions(dir_path, 0o777)
                print_success(f"Created: {dir_path.relative_to(self.root_dir)}")
            except PermissionError as e:
                print_warning(f"Could not set permissions on {dir_path}: {e}")
                if is_linux():
                    print_info("You may need to run with sudo on Linux")
            except Exception as e:
                print_warning(f"Could not create {dir_path}: {e}")

        # If running as root (sudo) on Linux, set ownership to allow non-root access
        if is_linux() and is_root():
            user_info = get_real_user_info()
            if user_info:
                uid, gid, username = user_info
                try:
                    for dir_path in directories:
                        if dir_path.exists():
                            set_directory_ownership(dir_path, uid, gid)
                    print_success(f"Set ownership to {username} for data directories")
                except Exception as e:
                    print_warning(f"Could not set ownership: {e}")

        print()

    def generate_env_file(self):
        """Generate .env file with user configuration"""
        print_header("Generating Configuration")

        # Get absolute path for HOST_BACKEND_DATA_PATH
        host_backend_data_path = str(self.backend_data_dir.absolute())

        # Capture the previous NEXT_PUBLIC_API_URL (if any) so we can detect
        # changes that require a cache-busting frontend rebuild. Next.js bakes
        # NEXT_PUBLIC_* values into the static build at image-build time — a
        # cached image carries the old URL forever and silently routes API
        # calls to the wrong host.
        #
        # Also reuse the parsed values below to PRESERVE existing secrets
        # (POSTGRES_PASSWORD, JWT_SECRET_KEY, ASANA_ENCRYPTION_KEY) across
        # installer re-runs. Regenerating these on every run orphans the
        # postgres volume (wrong password) and invalidates every issued JWT
        # plus every Fernet-encrypted secret stored in the DB.
        previous_api_url = ""
        previous_env_vars: Dict[str, str] = {}
        if self.env_file.exists():
            try:
                previous_env_vars = self._read_env_file_vars()
                previous_api_url = previous_env_vars.get('NEXT_PUBLIC_API_URL', '')
            except Exception:
                previous_api_url = ""
                previous_env_vars = {}

        # Preserve existing secrets when re-running the installer; only
        # generate fresh values on a true first install (or when a key
        # was missing from the previous .env for any reason).
        postgres_password = previous_env_vars.get('POSTGRES_PASSWORD') or secrets.token_urlsafe(24)
        jwt_secret = previous_env_vars.get('JWT_SECRET_KEY') or secrets.token_urlsafe(32)
        asana_encryption_key = previous_env_vars.get('ASANA_ENCRYPTION_KEY') or Fernet.generate_key().decode()

        self._preserved_existing_postgres_password = bool(previous_env_vars.get('POSTGRES_PASSWORD'))

        if previous_env_vars.get('POSTGRES_PASSWORD'):
            print_info("Preserved existing POSTGRES_PASSWORD from .env")
        if previous_env_vars.get('JWT_SECRET_KEY'):
            print_info("Preserved existing JWT_SECRET_KEY from .env")
        if previous_env_vars.get('ASANA_ENCRYPTION_KEY'):
            print_info("Preserved existing ASANA_ENCRYPTION_KEY from .env")

        # Determine URLs based on SSL mode
        ssl_mode = self._normalize_ssl_mode(self.config.get('SSL_MODE', 'disabled'))
        access_type = self.config.get('ACCESS_TYPE', 'localhost')
        public_host = self.config.get('PUBLIC_HOST', 'localhost')
        auth_rate_limit = self._resolve_auth_rate_limit()

        if ssl_mode != 'disabled':
            ssl_domain = self.config.get('SSL_DOMAIN', 'localhost')
            backend_url = f"https://{ssl_domain}"
            frontend_url = f"https://{ssl_domain}"
        elif access_type == 'remote':
            backend_url = f"http://{public_host}:{self.config['TSN_APP_PORT']}"
            frontend_url = f"http://{public_host}:{self.config['FRONTEND_PORT']}"
        else:
            backend_url = f"http://localhost:{self.config['TSN_APP_PORT']}"
            frontend_url = f"http://localhost:{self.config['FRONTEND_PORT']}"

        # Compare new backend_url against previous NEXT_PUBLIC_API_URL; if
        # different (including the fresh-install case where previous is empty),
        # schedule a --no-cache frontend rebuild in run_docker_compose.
        if previous_api_url and previous_api_url != backend_url:
            self._force_frontend_rebuild = True
            print_info(
                f"NEXT_PUBLIC_API_URL changed ({previous_api_url} -> {backend_url}); "
                f"frontend will be rebuilt with --no-cache."
            )

        cors_origins = [frontend_url]
        if ssl_mode != 'disabled':
            extra_origins = ["https://localhost"]
        else:
            # BUG-445: Always include loopback origins for both frontend and
            # backend ports so localhost/127.0.0.1 browser access passes CORS.
            frontend_port = self.config['FRONTEND_PORT']
            backend_port = self.config['TSN_APP_PORT']
            extra_origins = [
                f"http://localhost:{frontend_port}",
                f"http://127.0.0.1:{frontend_port}",
            ]
            if str(backend_port) != str(frontend_port):
                extra_origins.append(f"http://localhost:{backend_port}")
                extra_origins.append(f"http://127.0.0.1:{backend_port}")
        for origin in extra_origins:
            if origin not in cors_origins:
                cors_origins.append(origin)

        disable_auth_rate_limit = self.config.get('TSN_DISABLE_AUTH_RATE_LIMIT', self._resolve_disable_auth_rate_limit())

        env_content = f"""# Tsushin Configuration
# Generated by installer on {datetime.now().isoformat()}

# Application
TSN_APP_HOST=0.0.0.0
TSN_APP_PORT={self.config['TSN_APP_PORT']}
FRONTEND_PORT={self.config['FRONTEND_PORT']}
TSN_STACK_NAME={self.config.get('TSN_STACK_NAME', 'tsushin')}
COMPOSE_PROJECT_NAME={self.config.get('TSN_STACK_NAME', 'tsushin')}  # Must equal TSN_STACK_NAME for consistent naming
TSN_BACKEND_URL={backend_url}
TSN_FRONTEND_URL={frontend_url}
TSN_LOG_LEVEL=INFO
TSN_AUTH_RATE_LIMIT={auth_rate_limit}
TSN_DISABLE_AUTH_RATE_LIMIT={disable_auth_rate_limit}
TSN_POLL_INTERVAL_MS=3000

# Database
POSTGRES_PASSWORD={postgres_password}
INTERNAL_DB_PATH=/app/data/agent.db
TSN_CHROMA_DIR=/app/data/chroma
TSN_WORKSPACE_DIR=/app/data/workspace
TSN_BACKUPS_DIR=/app/data/backups
TSN_LOG_FILE=/app/logs/tsushin.log

# Host path for MCP container volume mounts (CRITICAL for Docker-in-Docker)
HOST_BACKEND_DATA_PATH={host_backend_data_path}

# AI Provider Keys — stored in database via setup wizard, not in .env
# Configure additional providers via Settings > Integrations after install

# Security (auto-generated)
JWT_SECRET_KEY={jwt_secret}
ASANA_ENCRYPTION_KEY={asana_encryption_key}

# Google OAuth (configure later via UI)
TSN_GOOGLE_OAUTH_REDIRECT_URI={backend_url}/api/hub/google/oauth/callback
ASANA_REDIRECT_URI={frontend_url}/hub/asana/callback

# SSL/HTTPS Configuration
SSL_MODE={ssl_mode}
SSL_DOMAIN={self.config.get('SSL_DOMAIN', '')}
SSL_EMAIL={self.config.get('SSL_EMAIL', '')}
SSL_LE_STAGING={self.config.get('SSL_LE_STAGING', '')}
SSL_CERT_PATH={self.config.get('SSL_CERT_PATH', '')}
SSL_KEY_PATH={self.config.get('SSL_KEY_PATH', '')}
SSL_CERT_CHAIN_PATH={self.config.get('SSL_CERT_CHAIN_PATH', '')}
TSN_SSL_MODE={ssl_mode}
TSN_CORS_ORIGINS={','.join(cors_origins)}
HTTP_PORT=80
HTTPS_PORT=443

# Frontend Build Args
NEXT_PUBLIC_API_URL={backend_url}

# Optional local services
# Kokoro TTS: auto-provisioned per-tenant via Hub → Kokoro TTS → Setup with Wizard.
# The legacy KOKORO_SERVICE_URL / docker compose --profile tts path has been removed.
"""

        # Write .env file
        with open(self.env_file, 'w') as f:
            f.write(env_content)

        print_success(f"Configuration file created: {self.env_file}")
        print()

    def create_backup(self) -> Optional[str]:
        """Create backup before destructive operations"""
        try:
            result = subprocess.run(
                [sys.executable, "backup_installer.py", "create"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=True
            )
            # Parse backup path from output
            for line in result.stdout.split('\n'):
                if "Location:" in line:
                    return line.split("Location:")[1].strip()
            return None
        except Exception as e:
            print_warning(f"Could not create backup: {e}")
            return None

    def _check_postgres_volume_collision(self) -> None:
        """
        Abort if a Postgres named volume already exists whose password we
        cannot match (BUG-582).

        BUG-566 preserves POSTGRES_PASSWORD from an existing .env so that
        re-running the installer against the same data volume works. That
        preservation is scoped to the working directory's .env — it does
        NOT cross worktrees, clean clones, or machines. If a developer
        clones this repo into a new directory while the original tsushin
        stack's named volume (`<stack>-postgres-data`) still exists on
        the host, the fresh installer generates a brand-new password and
        `docker compose up` then crashes the backend with FATAL auth.

        This guard detects that case and surfaces clear remediation paths
        before any Docker action is taken. Non-destructive — we never
        remove the volume on the user's behalf.
        """
        stack_name = (self.config.get('TSN_STACK_NAME') or 'tsushin').strip() or 'tsushin'
        volume_name = f"{stack_name}-postgres-data"

        try:
            result = subprocess.run(
                ["docker", "volume", "inspect", volume_name],
                capture_output=True,
                text=True,
            )
        except Exception as e:
            print_warning(f"Could not inspect postgres volume '{volume_name}': {e}")
            return

        volume_exists = result.returncode == 0
        if not volume_exists:
            return

        if self._preserved_existing_postgres_password:
            # BUG-566 path — password was preserved from an existing .env,
            # so the volume and the .env agree. Proceed silently.
            return

        print_error(
            f"Postgres volume '{volume_name}' already exists from a previous "
            f"install, but this run generated a fresh POSTGRES_PASSWORD that "
            f"will not match the data on that volume."
        )
        print_info("Without this check, the backend would crash-loop with "
                   "'FATAL: password authentication failed for user \"tsushin\"' "
                   "immediately after compose up.")
        print_info("")
        print_info("Choose one of the following:")
        print_info(f"  (a) Copy the original .env into this directory so "
                   f"POSTGRES_PASSWORD is preserved (recommended when you want "
                   f"to keep your data).")
        print_info(f"  (b) Isolate this install by setting a different stack "
                   f"name BEFORE running the installer, e.g.:")
        print_info(f"        export TSN_STACK_NAME=tsushin-dev")
        print_info(f"        export COMPOSE_PROJECT_NAME=tsushin-dev")
        print_info(f"        python3 install.py --defaults --http --port 8091 "
                   f"--frontend-port 3091")
        print_info(f"  (c) Destroy the existing volume to start fresh "
                   f"(WARNING: permanent data loss — back up first with "
                   f"'bash backend/scripts/backup_db.sh'):")
        print_info(f"        docker volume rm {volume_name}")
        print_info("")
        sys.exit(1)

    def run_docker_compose(self):
        """Run docker-compose up --build -d"""
        print_header("Deploying Docker Containers")

        # BUG-582: refuse to proceed if an existing postgres volume would
        # collide with the freshly-generated password.
        self._check_postgres_volume_collision()

        # Ensure the external network exists (required before docker-compose up)
        try:
            result = subprocess.run(
                ["docker", "network", "inspect", "tsushin-network"],
                capture_output=True, text=True
            )
            if result.returncode != 0:
                print_info("Creating tsushin-network (external network for MCP containers)...")
                subprocess.run(
                    ["docker", "network", "create", "tsushin-network"],
                    check=True, capture_output=True
                )
        except Exception as e:
            print_warning(f"Could not create tsushin-network: {e}")

        print_info("Building and starting containers (this may take several minutes)...")
        print_info("Downloading base images, building custom images, and starting services...")
        print()

        # BuildKit is required for cache mounts in backend/Dockerfile (v0.6.0+).
        # Docker Compose v2 (bundled with Docker Desktop >=20.10) enables BuildKit
        # by default. docker-compose v1 is no longer supported.
        compose_env = os.environ.copy()

        # Build compose command with SSL override if enabled
        ssl_mode = self.config.get('SSL_MODE', 'disabled')
        compose_file_args: List[str] = []
        if ssl_mode != 'disabled':
            compose_file_args = ["-f", "docker-compose.yml", "-f", "docker-compose.ssl.yml"]
            print_info("SSL enabled: deploying with Caddy reverse proxy...")

        # If NEXT_PUBLIC_API_URL changed, rebuild frontend without cache first.
        # This is the only layer that bakes in build-time env vars; a cached
        # image would keep the old API URL despite the new .env.
        if self._force_frontend_rebuild:
            print_info("Frontend rebuild required (API URL changed) — running build --no-cache frontend...")
            rebuild_cmd = self.docker_compose_cmd + compose_file_args + [
                "build", "--no-cache", "frontend"
            ]
            try:
                subprocess.run(rebuild_cmd, cwd=self.root_dir, env=compose_env, check=True)
                print_success("Frontend image rebuilt without cache")
            except subprocess.CalledProcessError as exc:
                print_warning(f"Frontend --no-cache rebuild failed (continuing with cached build): {exc}")

        compose_cmd = self.docker_compose_cmd + compose_file_args + ["up", "--build", "-d"]

        try:
            process = subprocess.Popen(
                compose_cmd,
                cwd=self.root_dir,
                env=compose_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

            # Stream output
            for line in process.stdout:
                print(f"  {line.rstrip()}")

            process.wait()

            if process.returncode == 0:
                print()
                print_success("Containers started successfully")
            else:
                # docker-compose v1 may report errors for dependency timing issues
                # (e.g., frontend waiting on backend health). This is recoverable —
                # the health_check() step will retry and _ensure_frontend_started()
                # will bring up any missing services.
                print_warning("Docker Compose reported errors (may be recoverable)")
                print_info("Will attempt recovery during health checks...")

        except Exception as e:
            print_error(f"Docker Compose failed: {e}")
            sys.exit(1)

    def build_additional_images(self):
        """Build additional Docker images required for integrations"""
        print_header("Building Integration Images")

        # BuildKit required for backend/Dockerfile cache mounts (v0.6.0+).
        build_env = os.environ.copy()

        images_to_build = [
            {
                "name": "WhatsApp MCP",
                "image": "tsushin/whatsapp-mcp:latest",
                "context": self.root_dir / "backend" / "whatsapp-mcp",
                "dockerfile": None  # Uses default Dockerfile
            },
            {
                "name": "Toolbox (Sandboxed Tools)",
                "image": "tsushin-toolbox:base",
                "context": self.root_dir,
                "dockerfile": self.root_dir / "backend" / "containers" / "Dockerfile.toolbox"
            }
        ]

        for img in images_to_build:
            print_info(f"Building {img['name']} image...")

            # Check if context directory exists
            if not img['context'].exists():
                print_warning(f"Skipping {img['name']}: directory not found at {img['context']}")
                continue

            try:
                cmd = ["docker", "build", "-t", img['image']]

                # Add dockerfile path if specified
                if img['dockerfile']:
                    cmd.extend(["-f", str(img['dockerfile'])])

                cmd.append(str(img['context']))

                process = subprocess.Popen(
                    cmd,
                    env=build_env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1
                )

                # Stream output (limited to avoid flooding)
                line_count = 0
                for line in process.stdout:
                    line_count += 1
                    # Show first few lines and progress indicators
                    if line_count <= 5 or "Step" in line or "Successfully" in line:
                        print(f"  {line.rstrip()}")
                    elif line_count == 6:
                        print("  ...")

                process.wait()

                if process.returncode == 0:
                    print_success(f"{img['name']} image built successfully")
                else:
                    print_warning(f"{img['name']} image build failed (non-critical)")

            except Exception as e:
                print_warning(f"Could not build {img['name']} image: {e}")
                print_info("You can build it manually later if needed")

        print()

    def _ensure_frontend_started(self):
        """Ensure frontend container is running — workaround for docker-compose v1 race condition."""
        try:
            result = subprocess.run(
                ["docker", "inspect", "--format", "{{.State.Running}}", f"{self.config.get('TSN_STACK_NAME', 'tsushin')}-frontend"],
                capture_output=True, text=True
            )
            if result.returncode != 0 or result.stdout.strip() != 'true':
                print_info("Frontend not running (docker-compose v1 race) — starting it now...")
                ssl_mode = self.config.get('SSL_MODE', 'disabled')
                if ssl_mode != 'disabled':
                    start_cmd = self.docker_compose_cmd + [
                        "-f", "docker-compose.yml",
                        "-f", "docker-compose.ssl.yml",
                        "up", "-d", "frontend"
                    ]
                else:
                    start_cmd = self.docker_compose_cmd + ["up", "-d", "frontend"]
                subprocess.run(start_cmd, cwd=self.root_dir, check=True, capture_output=True)
                print_success("Frontend container started")
        except Exception as e:
            print_warning(f"Could not ensure frontend started: {e}")

    def _get_local_backend_health_url(self) -> str:
        """Use loopback IP to avoid localhost-only frontend redirect logic during health checks."""
        return f"http://127.0.0.1:{self.config['TSN_APP_PORT']}/api/health"

    def _get_local_frontend_health_url(self) -> str:
        """Use loopback IP to avoid localhost-only frontend redirect logic during health checks."""
        return f"http://127.0.0.1:{self.config['FRONTEND_PORT']}"

    def _get_access_urls(self) -> Dict[str, str]:
        """Build user-facing access URLs based on SSL mode and access type."""
        ssl_mode = self.config.get('SSL_MODE', 'disabled')
        access_type = self.config.get('ACCESS_TYPE', 'localhost')
        public_host = (self.config.get('PUBLIC_HOST') or '').strip() or "localhost"
        frontend_port = self.config['FRONTEND_PORT']
        backend_port = self.config['TSN_APP_PORT']

        if ssl_mode != 'disabled':
            domain = self.config['SSL_DOMAIN']
            return {
                "primary": f"https://{domain}",
                "frontend": f"http://localhost:{frontend_port}",
                "backend": f"http://localhost:{backend_port}",
            }

        display_host = public_host if access_type == "remote" else "localhost"
        return {
            "primary": f"http://{display_host}:{frontend_port}",
            "frontend": f"http://{display_host}:{frontend_port}",
            "backend": f"http://{display_host}:{backend_port}",
        }

    def health_check(self):
        """Wait for services to be healthy"""
        print_header("Health Checks")

        backend_url = self._get_local_backend_health_url()
        frontend_url = self._get_local_frontend_health_url()

        # Backend health check
        print_info(f"Waiting for backend at {backend_url}...")
        for i in range(30):
            try:
                response = requests.get(backend_url, timeout=2)
                if response.status_code == 200:
                    print_success("Backend is healthy")
                    break
            except:
                pass
            time.sleep(2)
            print(f"  Attempt {i+1}/30...", end='\r')
        else:
            print_error("Backend health check failed")
            print_info("Check logs: docker-compose logs backend")
            sys.exit(1)

        self._ensure_frontend_started()

        # Frontend health check
        print_info(f"Waiting for frontend at {frontend_url}...")
        for i in range(30):
            try:
                response = requests.get(frontend_url, timeout=2, allow_redirects=False)
                if response.status_code in [200, 301, 302, 307, 308, 404]:
                    print_success("Frontend is healthy")
                    break
            except:
                pass
            time.sleep(2)
            print(f"  Attempt {i+1}/30...", end='\r')
        else:
            print_error("Frontend health check failed")
            print_info("Check logs: docker-compose logs frontend")
            sys.exit(1)

        # Proxy health check (when SSL is enabled)
        ssl_mode = self.config.get('SSL_MODE', 'disabled')
        if ssl_mode != 'disabled':
            domain = self.config.get('SSL_DOMAIN', 'localhost')
            proxy_url = f"https://{domain}"
            print_info(f"Waiting for SSL proxy at {proxy_url}...")
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            for i in range(20):
                try:
                    # Local loopback health-check against Caddy `tls internal` self-signed cert.
                    # No credentials transmitted; only status code is consumed.
                    # nosemgrep: python.requests.security.disabled-cert-validation.disabled-cert-validation
                    response = requests.get(proxy_url, timeout=3, verify=False)
                    if response.status_code in [200, 308, 404]:
                        print_success("SSL proxy is healthy")
                        break
                except:
                    pass
                time.sleep(2)
                print(f"  Attempt {i+1}/20...", end='\r')
            else:
                print_warning("SSL proxy health check failed — services may still be accessible on direct ports")

        print()

    def display_success_message(self):
        """Display success message with access information"""
        print_header("Installation Complete!")

        ssl_mode = self.config.get('SSL_MODE', 'disabled')
        access_urls = self._get_access_urls()
        frontend_url = access_urls["frontend"]
        backend_url = access_urls["backend"]

        print(f"{Colors.GREEN}{Colors.BOLD}Tsushin has been successfully installed!{Colors.ENDC}\n")

        if ssl_mode != 'disabled':
            primary_url = access_urls["primary"]
            print(f"{Colors.BOLD}Access URLs:{Colors.ENDC}")
            print(f"  HTTPS:     {Colors.CYAN}{primary_url}{Colors.ENDC}")
            print(f"  Direct:    {Colors.CYAN}{frontend_url}{Colors.ENDC} (HTTP, localhost only)")
            print(f"  API:       {Colors.CYAN}{backend_url}{Colors.ENDC} (HTTP, localhost only)")
            print()

            if ssl_mode == 'selfsigned':
                print_warning("Self-signed certificate: browsers will show a security warning.")
                print_info("Accept the warning to proceed, or add the certificate to your trusted store.")
                print()
            elif ssl_mode == 'letsencrypt':
                print_success("Let's Encrypt certificate will auto-renew (managed by Caddy).")
                print()
        else:
            print(f"{Colors.BOLD}Access URLs:{Colors.ENDC}")
            print(f"  Frontend:  {Colors.CYAN}{frontend_url}{Colors.ENDC}")
            print(f"  Backend:   {Colors.CYAN}{backend_url}{Colors.ENDC}")
            print()

        access_url = access_urls["primary"]
        setup_wizard_url = f"{access_url}/setup"

        print(f"{Colors.BOLD}Next Steps:{Colors.ENDC}")
        print(f"  1. Open {Colors.CYAN}{access_url}{Colors.ENDC} in your browser")
        print(f"  2. Complete the setup wizard to create your admin account and configure AI providers:")
        print(f"     {Colors.CYAN}{setup_wizard_url}{Colors.ENDC}")
        print(f"  3. Start creating agents and testing in the playground!")
        print()

        print(f"{Colors.BOLD}Local Ollama (optional):{Colors.ENDC}")
        print(f"  Ollama binds to 127.0.0.1 by default — unreachable from Docker containers.")
        print(f"  To use Ollama with Tsushin:")
        print(f"  a) Make Ollama listen on all interfaces (add systemd override):")
        print(f"       sudo mkdir -p /etc/systemd/system/ollama.service.d/")
        print(f"       printf '[Service]\\nEnvironment=\"OLLAMA_HOST=0.0.0.0:11434\"\\n' | sudo tee /etc/systemd/system/ollama.service.d/override.conf")
        print(f"       sudo systemctl daemon-reload && sudo systemctl restart ollama")
        print(f"  b) In Hub > Local Services > Ollama, set URL to:")
        print(f"       {Colors.CYAN}http://172.18.0.1:11434{Colors.ENDC}  (Docker gateway IP)")
        print()

        print(f"{Colors.BOLD}Useful Commands:{Colors.ENDC}")
        print(f"  View logs:      docker compose logs -f")
        print(f"  Stop services:  docker compose down")
        print(f"  Restart:        docker compose restart")
        print(f"  Create backup:  python3 backup_installer.py create")
        print()

    def _get_primary_ip(self) -> str:
        """Detect the machine's primary non-loopback IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "localhost"

    def _populate_defaults(self):
        """Populate self.config with sensible defaults for unattended install.
        Only infrastructure config — no user/org/API key creation.
        User creation is handled by the /setup UI wizard after install."""
        self.config['TSN_APP_PORT'] = str(self.args.port)
        self.config['FRONTEND_PORT'] = str(self.args.frontend_port)
        self.config['SSL_MODE'] = 'selfsigned'
        # Use machine's IP so HTTPS works from the network, not just localhost
        host = self._get_primary_ip()
        self.config['SSL_DOMAIN'] = host
        self.config['SSL_EMAIL'] = ''
        self.config['ACCESS_TYPE'] = 'remote' if host != 'localhost' else 'localhost'
        self.config['PUBLIC_HOST'] = host

    def run(self):
        """Main installation flow"""
        print_header("Tsushin Platform Installer")
        print(f"{Colors.BOLD}Welcome to Tsushin!{Colors.ENDC}\n")
        print("This installer will guide you through the setup process.\n")

        # Enable ANSI color codes on Windows 10+
        enable_ansi_colors()

        # --defaults mode: fully unattended infrastructure install
        if self.args.defaults:
            print_info("Defaults mode: generating .env with sensible defaults.")
            self._populate_defaults()
            # Apply CLI overrides
            if self.args.http:
                self.config['SSL_MODE'] = 'disabled'
            elif self.args.domain:
                self.config['SSL_MODE'] = 'letsencrypt'
                self.config['SSL_DOMAIN'] = self.args.domain
                self.config['SSL_EMAIL'] = self.args.email
                if self.args.le_staging:
                    self.config['SSL_LE_STAGING'] = 'true'
                    print_info("Let's Encrypt staging environment enabled (for testing only).")
            # Resolve URLs after SSL mode is finalized
            host = self.config['PUBLIC_HOST']
            self._resolve_urls(self.config['ACCESS_TYPE'], host, self.config['TSN_APP_PORT'])
            self.check_prerequisites()
            self.prepare_data_directories()
            self.generate_caddyfile()
            self.generate_self_signed_cert()
            self.generate_env_file()
            self.run_docker_compose()
            self.build_additional_images()
            self.health_check()
            self.display_success_message()
            return

        # Non-interactive mode: require pre-existing .env file
        if not self.interactive:
            print_info("Non-interactive mode detected (stdin is not a terminal).")
            if self.env_file.exists():
                print_success(f"Using existing .env file: {self.env_file}")
                print_info("Skipping interactive prompts. Proceeding with existing configuration.")
                # Load minimal config from .env for downstream steps
                self._load_config_from_env()
                self._backfill_existing_env_defaults()
                # Skip to deployment steps
                self.check_prerequisites()
                self.prepare_data_directories()
                self.generate_caddyfile()
                self.generate_self_signed_cert()
                self.copy_manual_certs()
                self.run_docker_compose()
                self.build_additional_images()
                self.health_check()
                self.display_success_message()
                return
            else:
                print_error("Non-interactive mode requires a pre-existing .env file.")
                print_info("Either:")
                print_info("  1. Run the installer interactively in a terminal to generate .env")
                print_info("  2. Use --defaults for fully unattended install")
                sys.exit(1)

        # Early check: Warn about sudo requirement on Linux
        if is_linux() and not is_root():
            # Check if user is in docker group
            try:
                result = subprocess.run(["groups"], capture_output=True, text=True)
                if "docker" not in result.stdout:
                    print_warning("On Linux, this installer requires elevated permissions")
                    print_info("Recommendation: Run with sudo")
                    print_info("  sudo python3 install.py")
                    print()
                    confirm = safe_input(f"{Colors.BOLD}Continue anyway? (not recommended) [y/N]:{Colors.ENDC} ").strip().lower()
                    if confirm != 'y':
                        print_info("Exiting. Please run with: sudo python3 install.py")
                        sys.exit(0)
            except:
                pass  # If we can't check groups, continue

        # Step 1: Check for existing installation
        mode = self.check_existing_installation()
        print_info(f"Installation mode: {Colors.BOLD}{mode}{Colors.ENDC}\n")

        # Step 2: Check prerequisites
        self.check_prerequisites()

        # Step 3: Create backup if needed
        if mode in ["update", "destructive"]:
            print_info("Creating backup before proceeding...")
            backup_path = self.create_backup()
            if backup_path:
                print_success(f"Backup created: {backup_path}")
            print()

        # Step 4: Stop containers if destructive
        if mode == "destructive":
            print_info("Stopping existing containers...")
            try:
                subprocess.run(self.docker_compose_cmd + ["down"], cwd=self.root_dir, check=True)
            except subprocess.CalledProcessError as e:
                print_error("Failed to stop containers. You may need sudo permissions.")
                if is_linux():
                    print_info("Try: sudo python3 install.py")
                sys.exit(1)

            if self.database_path.exists():
                print_info("Removing existing database...")
                try:
                    self.database_path.unlink()
                except PermissionError:
                    print_error(f"Permission denied deleting: {self.database_path}")
                    if is_linux():
                        print_info("The database was created by Docker (root). Run with sudo:")
                        print_info("  sudo python3 install.py")
                    sys.exit(1)
            print()

        # Step 5: Prompt for configuration
        self.prompt_for_configuration(mode)

        # Step 6: Prepare data directories with proper permissions
        self.prepare_data_directories()

        # Step 6b: Generate SSL configuration (Caddyfile)
        self.generate_caddyfile()

        # Step 6c: Generate self-signed certificate if needed
        self.generate_self_signed_cert()

        # Step 6d: Copy manual certificates if needed
        self.copy_manual_certs()

        # Step 7: Generate .env file
        self.generate_env_file()

        # Step 8: Deploy containers
        self.run_docker_compose()

        # Step 9: Build additional Docker images (WhatsApp MCP, Toolbox)
        self.build_additional_images()

        # Step 10: Health checks
        self.health_check()

        # Step 11: Display success message (user creates org/admin via /setup UI)
        self.display_success_message()


if __name__ == "__main__":
    try:
        args = parse_args()
        installer = TsushinInstaller(args=args)
        installer.run()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Installation cancelled by user{Colors.ENDC}")
        sys.exit(0)
    except EOFError:
        print(f"\n\n{Colors.YELLOW}Installation cancelled: stdin closed (non-interactive mode){Colors.ENDC}")
        print(f"{Colors.BLUE}ℹ{Colors.ENDC}  To run non-interactively, create a .env file first, then re-run.")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}Installation failed: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
