#!/usr/bin/env python3
"""
Tsushin Platform Installer
Phase 2: Installation Script

Interactive installer for Tsushin multi-agent platform.
Configures environment, deploys Docker containers, and sets up initial tenant/agents.

Usage:
    python3 install.py

Requirements:
    - Python 3.8+
    - Docker and Docker Compose
    - Internet connection
"""

import os
import sys
import re
import socket
import secrets
import subprocess
import time
import getpass
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime

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


class TsushinInstaller:
    def __init__(self):
        self.root_dir = Path(__file__).parent
        self.env_file = self.root_dir / ".env"
        self.backend_data_dir = self.root_dir / "backend" / "data"
        self.database_path = self.backend_data_dir / "agent.db"
        self.config = {}

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

        choice = input(f"\n{Colors.BOLD}Choice [1]:{Colors.ENDC} ").strip() or "1"

        if choice == "1":
            print_info("Installation cancelled to preserve existing instance.")
            sys.exit(0)
        elif choice == "2":
            return "update"
        elif choice == "3":
            print_warning("This will DELETE all existing data!")
            confirm = input(f"{Colors.RED}Type 'DELETE EVERYTHING' to confirm:{Colors.ENDC} ")
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

        # Check Docker Compose
        try:
            result = subprocess.run(["docker-compose", "--version"], capture_output=True, text=True, check=True)
            compose_version = result.stdout.strip()
            print_success(f"Docker Compose: {compose_version}")
        except (FileNotFoundError, subprocess.CalledProcessError):
            # Try 'docker compose' (newer syntax)
            try:
                result = subprocess.run(["docker", "compose", "version"], capture_output=True, text=True, check=True)
                compose_version = result.stdout.strip()
                print_success(f"Docker Compose: {compose_version}")
                # Use 'docker compose' for future commands
                self.docker_compose_cmd = ["docker", "compose"]
            except (FileNotFoundError, subprocess.CalledProcessError):
                print_error("Docker Compose is not installed")
                print_info("Install Docker Compose: https://docs.docker.com/compose/install/")
                sys.exit(1)
        else:
            self.docker_compose_cmd = ["docker-compose"]

        # Check Python version
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        print_success(f"Python: {python_version}")

        print()

    def prompt_for_configuration(self, mode: str):
        """
        Interactive prompts for configuration

        Args:
            mode: 'fresh', 'update', or 'destructive'
        """
        print_header("Configuration Setup")

        # AI Provider Configuration
        print(f"{Colors.BOLD}AI Provider Configuration{Colors.ENDC}")
        print("At least one AI provider API key is required.\n")

        # Gemini API Key
        gemini_key = self.prompt_with_validation(
            "Enter Google Gemini API Key (recommended): ",
            validator=lambda x: len(x) >= 20 if x else True,
            error_msg="API key must be at least 20 characters",
            optional=True,
            mask=True
        )
        self.config['GEMINI_API_KEY'] = gemini_key or ""

        # OpenAI API Key
        openai_key = self.prompt_with_validation(
            "Enter OpenAI API Key (optional, for audio agents): ",
            validator=lambda x: len(x) >= 20 if x else True,
            error_msg="API key must be at least 20 characters",
            optional=True,
            mask=True
        )
        self.config['OPENAI_API_KEY'] = openai_key or ""

        # Anthropic API Key
        anthropic_key = self.prompt_with_validation(
            "Enter Anthropic API Key (optional): ",
            validator=lambda x: len(x) >= 20 if x else True,
            error_msg="API key must be at least 20 characters",
            optional=True,
            mask=True
        )
        self.config['ANTHROPIC_API_KEY'] = anthropic_key or ""

        # Validate at least one API key provided
        if not (gemini_key or openai_key or anthropic_key):
            print_error("At least one AI provider API key is required!")
            sys.exit(1)

        print()

        # Network Configuration
        print(f"{Colors.BOLD}Network Configuration{Colors.ENDC}\n")

        backend_port = self.prompt_with_validation(
            "Enter Backend Port [8081]: ",
            default="8081",
            validator=lambda x: 1024 <= int(x) <= 65535,
            error_msg="Port must be between 1024 and 65535"
        )
        self.config['TSN_APP_PORT'] = backend_port

        frontend_port = self.prompt_with_validation(
            "Enter Frontend Port [3030]: ",
            default="3030",
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

        access_type = input(f"{Colors.BOLD}How will you access this installation? [localhost/remote]:{Colors.ENDC} ").strip().lower()

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

            # Configure frontend API URL for remote access
            self.config['NEXT_PUBLIC_API_URL'] = f"http://{public_host}:{backend_port}"
            print_success(f"Frontend will connect to backend at: {self.config['NEXT_PUBLIC_API_URL']}")
        else:
            # Local installation - use localhost
            self.config['NEXT_PUBLIC_API_URL'] = f"http://localhost:{backend_port}"
            print_info(f"Frontend will connect to backend at: {self.config['NEXT_PUBLIC_API_URL']}")

        print()

        # Only ask for tenant/admin info in fresh or destructive mode
        if mode in ["fresh", "destructive"]:
            # Tenant Setup
            print(f"{Colors.BOLD}Organization Setup{Colors.ENDC}\n")

            tenant_name = self.prompt_with_validation(
                "Enter initial Tenant name [DevTenant]: ",
                default="DevTenant",
                validator=lambda x: len(x) >= 2,
                error_msg="Tenant name must be at least 2 characters"
            )
            self.config['TENANT_NAME'] = tenant_name

            # Email validation with TLD check
            def validate_email(email: str) -> bool:
                # Basic format check
                if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                    return False
                # Check for reserved/special-use TLDs that fail email validation
                reserved_tlds = ['.test', '.example', '.invalid', '.localhost']
                domain = email.split('@')[1] if '@' in email else ''
                for tld in reserved_tlds:
                    if domain.endswith(tld):
                        print_warning(f"Email domain '{domain}' uses reserved TLD '{tld}' which may fail validation")
                        print_info("Recommended: Use .com, .local, .dev, or your actual domain")
                        return False
                return True

            # Global Admin Credentials
            print(f"\n{Colors.BOLD}Global Administrator Setup{Colors.ENDC}")
            print("This user will have platform-wide administrative access.\n")

            global_admin_email = self.prompt_with_validation(
                "Global admin email: ",
                validator=validate_email,
                error_msg="Invalid email format or reserved TLD"
            )
            self.config['GLOBAL_ADMIN_EMAIL'] = global_admin_email

            global_admin_full_name = self.prompt_with_validation(
                "Global admin full name: ",
                validator=lambda x: len(x) >= 2,
                error_msg="Name must be at least 2 characters"
            )
            self.config['GLOBAL_ADMIN_FULL_NAME'] = global_admin_full_name

            # Password with confirmation
            while True:
                global_admin_password = getpass.getpass(f"{Colors.BOLD}Global admin password (min 8 chars):{Colors.ENDC} ")
                if len(global_admin_password) < 8:
                    print_error("Password must be at least 8 characters")
                    continue
                password_confirm = getpass.getpass(f"{Colors.BOLD}Confirm password:{Colors.ENDC} ")
                if global_admin_password != password_confirm:
                    print_error("Passwords do not match")
                    continue
                break

            self.config['GLOBAL_ADMIN_PASSWORD'] = global_admin_password

            # Tenant Admin Credentials
            print(f"\n{Colors.BOLD}Tenant Administrator Setup{Colors.ENDC}")
            print(f"This user will manage the '{tenant_name}' organization.\n")

            while True:
                admin_email = self.prompt_with_validation(
                    "Tenant admin email: ",
                    validator=validate_email,
                    error_msg="Invalid email format or reserved TLD"
                )
                # Validate different from global admin
                if admin_email == self.config['GLOBAL_ADMIN_EMAIL']:
                    print_error("Tenant admin must use a different email from global admin")
                    continue
                break

            self.config['ADMIN_EMAIL'] = admin_email

            admin_full_name = self.prompt_with_validation(
                "Tenant admin full name: ",
                validator=lambda x: len(x) >= 2,
                error_msg="Name must be at least 2 characters"
            )
            self.config['ADMIN_FULL_NAME'] = admin_full_name

            # Password with confirmation
            while True:
                admin_password = getpass.getpass(f"{Colors.BOLD}Tenant admin password (min 8 chars):{Colors.ENDC} ")
                if len(admin_password) < 8:
                    print_error("Password must be at least 8 characters")
                    continue
                password_confirm = getpass.getpass(f"{Colors.BOLD}Confirm password:{Colors.ENDC} ")
                if admin_password != password_confirm:
                    print_error("Passwords do not match")
                    continue
                break

            self.config['ADMIN_PASSWORD'] = admin_password

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
                value = getpass.getpass(f"{Colors.BOLD}{prompt}{Colors.ENDC}").strip() or default
            else:
                value = input(f"{Colors.BOLD}{prompt}{Colors.ENDC}").strip() or default

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

    def prepare_data_directories(self):
        """Create required data directories with proper permissions"""
        print_header("Preparing Data Directories")

        directories = [
            self.backend_data_dir,
            self.backend_data_dir / "workspace",
            self.backend_data_dir / "chroma",
            self.backend_data_dir / "backups",
            self.root_dir / "logs" / "backend",
        ]

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

        # Auto-generate security keys
        jwt_secret = secrets.token_urlsafe(32)
        asana_encryption_key = Fernet.generate_key().decode()

        # Get absolute path for HOST_BACKEND_DATA_PATH
        host_backend_data_path = str(self.backend_data_dir.absolute())

        backend_url = f"http://localhost:{self.config['TSN_APP_PORT']}"
        frontend_url = f"http://localhost:{self.config['FRONTEND_PORT']}"

        env_content = f"""# Tsushin Configuration
# Generated by installer on {datetime.now().isoformat()}

# Application
TSN_APP_HOST=0.0.0.0
TSN_APP_PORT={self.config['TSN_APP_PORT']}
TSN_BACKEND_URL={backend_url}
TSN_FRONTEND_URL={frontend_url}
TSN_LOG_LEVEL=INFO
TSN_POLL_INTERVAL_MS=3000

# Database
INTERNAL_DB_PATH=/app/data/agent.db
TSN_CHROMA_DIR=/app/data/chroma
TSN_WORKSPACE_DIR=/app/data/workspace
TSN_BACKUPS_DIR=/app/data/backups
TSN_LOG_FILE=/app/logs/tsushin.log

# Host path for MCP container volume mounts (CRITICAL for Docker-in-Docker)
HOST_BACKEND_DATA_PATH={host_backend_data_path}

# AI Provider Keys
GEMINI_API_KEY={self.config['GEMINI_API_KEY']}
GOOGLE_API_KEY={self.config['GEMINI_API_KEY']}
OPENAI_API_KEY={self.config['OPENAI_API_KEY']}
ANTHROPIC_API_KEY={self.config['ANTHROPIC_API_KEY']}
OLLAMA_BASE_URL=http://host.docker.internal:11434

# Security (auto-generated)
JWT_SECRET_KEY={jwt_secret}
ASANA_ENCRYPTION_KEY={asana_encryption_key}

# Google OAuth (configure later via UI)
TSN_GOOGLE_OAUTH_REDIRECT_URI={backend_url}/api/hub/google/oauth/callback
ASANA_REDIRECT_URI={frontend_url}/hub/asana/callback

# Frontend Build Args
NEXT_PUBLIC_API_URL={self.config.get('NEXT_PUBLIC_API_URL', backend_url)}
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

    def run_docker_compose(self):
        """Run docker-compose up --build -d"""
        print_header("Deploying Docker Containers")

        print_info("Building and starting containers (this may take several minutes)...")
        print_info("Downloading base images, building custom images, and starting services...")
        print()

        try:
            process = subprocess.Popen(
                self.docker_compose_cmd + ["up", "--build", "-d"],
                cwd=self.root_dir,
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
                print_error("Failed to start containers")
                sys.exit(1)

        except Exception as e:
            print_error(f"Docker Compose failed: {e}")
            sys.exit(1)

    def build_additional_images(self):
        """Build additional Docker images required for integrations"""
        print_header("Building Integration Images")

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

    def health_check(self):
        """Wait for services to be healthy"""
        print_header("Health Checks")

        backend_url = f"http://localhost:{self.config['TSN_APP_PORT']}/api/health"
        frontend_url = f"http://localhost:{self.config['FRONTEND_PORT']}"

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

        # Frontend health check
        print_info(f"Waiting for frontend at {frontend_url}...")
        for i in range(30):
            try:
                response = requests.get(frontend_url, timeout=2)
                if response.status_code in [200, 404]:  # 404 is OK for Next.js root
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

        print()

    def setup_initial_tenant(self):
        """Call setup-wizard API to create tenant and agents"""
        print_header("Setting Up Initial Tenant")

        backend_url = f"http://localhost:{self.config['TSN_APP_PORT']}"
        setup_url = f"{backend_url}/api/auth/setup-wizard"

        payload = {
            "tenant_name": self.config['TENANT_NAME'],
            # Tenant admin
            "admin_email": self.config['ADMIN_EMAIL'],
            "admin_password": self.config['ADMIN_PASSWORD'],
            "admin_full_name": self.config['ADMIN_FULL_NAME'],
            # Global admin
            "global_admin_email": self.config['GLOBAL_ADMIN_EMAIL'],
            "global_admin_password": self.config['GLOBAL_ADMIN_PASSWORD'],
            "global_admin_full_name": self.config['GLOBAL_ADMIN_FULL_NAME'],
            # API keys
            "gemini_api_key": self.config['GEMINI_API_KEY'] or None,
            "openai_api_key": self.config['OPENAI_API_KEY'] or None,
            "anthropic_api_key": self.config['ANTHROPIC_API_KEY'] or None,
            "create_default_agents": True
        }

        try:
            print_info("Creating tenant, administrators, and default agents...")
            response = requests.post(setup_url, json=payload, timeout=30)

            if response.status_code == 201:
                data = response.json()
                print_success(f"Tenant created: {data['tenant_name']}")
                print_success(f"Global admin created: {self.config['GLOBAL_ADMIN_EMAIL']}")
                print_success(f"Tenant admin created: {self.config['ADMIN_EMAIL']}")

                if data.get('agents_created'):
                    print_success(f"Default agents created: {', '.join(data['agents_created'])}")

                print()
                return True
            else:
                print_error(f"Setup failed: {response.status_code}")
                print_error(response.text)
                return False

        except Exception as e:
            print_error(f"Setup API call failed: {e}")
            return False

    def display_success_message(self):
        """Display success message with access information"""
        print_header("Installation Complete!")

        frontend_url = f"http://localhost:{self.config['FRONTEND_PORT']}"
        backend_url = f"http://localhost:{self.config['TSN_APP_PORT']}"

        print(f"{Colors.GREEN}{Colors.BOLD}🎉 Tsushin has been successfully installed!{Colors.ENDC}\n")
        print(f"{Colors.BOLD}Access URLs:{Colors.ENDC}")
        print(f"  Frontend:  {Colors.CYAN}{frontend_url}{Colors.ENDC}")
        print(f"  Backend:   {Colors.CYAN}{backend_url}{Colors.ENDC}")
        print()

        if self.config.get('ADMIN_EMAIL'):
            print(f"{Colors.BOLD}Administrator Accounts:{Colors.ENDC}")
            print(f"\n  {Colors.YELLOW}Global Administrator:{Colors.ENDC}")
            print(f"    Email:     {Colors.CYAN}{self.config['GLOBAL_ADMIN_EMAIL']}{Colors.ENDC}")
            print(f"    Access:    Platform-wide management")
            print(f"\n  {Colors.YELLOW}Tenant Administrator:{Colors.ENDC}")
            print(f"    Email:     {Colors.CYAN}{self.config['ADMIN_EMAIL']}{Colors.ENDC}")
            print(f"    Access:    {self.config['TENANT_NAME']} organization")
            print()

        print(f"{Colors.BOLD}Next Steps:{Colors.ENDC}")
        print(f"  1. Open {Colors.CYAN}{frontend_url}{Colors.ENDC} in your browser")
        print(f"  2. Log in with your admin credentials")
        print(f"  3. Follow the onboarding wizard to configure Google OAuth (optional)")
        print(f"  4. Start creating agents and testing in the playground!")
        print()

        print(f"{Colors.BOLD}Useful Commands:{Colors.ENDC}")
        print(f"  View logs:      docker-compose logs -f")
        print(f"  Stop services:  docker-compose down")
        print(f"  Restart:        docker-compose restart")
        print(f"  Create backup:  python3 backup_installer.py create")
        print()

    def run(self):
        """Main installation flow"""
        print_header("Tsushin Platform Installer")
        print(f"{Colors.BOLD}Welcome to Tsushin!{Colors.ENDC}\n")
        print("This installer will guide you through the setup process.\n")

        # Enable ANSI color codes on Windows 10+
        enable_ansi_colors()

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
                    confirm = input(f"{Colors.BOLD}Continue anyway? (not recommended) [y/N]:{Colors.ENDC} ").strip().lower()
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

        # Step 7: Generate .env file
        self.generate_env_file()

        # Step 8: Deploy containers
        self.run_docker_compose()

        # Step 9: Build additional Docker images (WhatsApp MCP, Toolbox)
        self.build_additional_images()

        # Step 10: Health checks
        self.health_check()

        # Step 11: Setup tenant (only if fresh or destructive)
        if mode in ["fresh", "destructive"]:
            if not self.setup_initial_tenant():
                print_error("Installation completed but tenant setup failed")
                print_info("You can manually create a tenant by signing up at the frontend")
                print()

        # Step 12: Display success message
        self.display_success_message()


if __name__ == "__main__":
    try:
        installer = TsushinInstaller()
        installer.run()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Installation cancelled by user{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print(f"\n{Colors.RED}Installation failed: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
