"""
Toolbox Container Service
Phase: Custom Tools Hub Integration

Manages per-tenant Docker containers for custom tool execution.
Handles container lifecycle: create, start, stop, restart, delete.
Supports dynamic package installation and image commits.
"""

import os
import re
import time
import shlex
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session

from services.docker_network_utils import resolve_tsushin_network_name
from services.container_runtime import (
    get_container_runtime,
    ContainerRuntime,
    ContainerNotFoundError,
    ContainerRuntimeError,
)

logger = logging.getLogger(__name__)

# BUG-063 FIX: Package name validation patterns to prevent command injection
SAFE_PIP_PACKAGE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]*((\[[\w,]+\])?(==|>=|<=|!=|~=|>|<)[\d.*]+)?$')
SAFE_APT_PACKAGE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._+-]*(=[\d.:~+-]+)?$')

# BUG-132 FIX: Tenant ID validation to prevent path traversal and injection
_SAFE_TENANT_ID = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$')


class ToolboxContainerService:
    """Manages per-tenant toolbox Docker containers for custom tool execution"""

    BASE_IMAGE = os.getenv("TSN_TOOLBOX_BASE_IMAGE", "tsushin-toolbox:base")
    COMMAND_TIMEOUT = 300  # Default 5 minutes
    HEALTH_CHECK_TIMEOUT = 30

    def __init__(self):
        """Initialize container runtime"""
        self.runtime: ContainerRuntime = get_container_runtime()
        logger.info("ToolboxContainerService initialized with container runtime")

    def _validate_tenant_id(self, tenant_id: str) -> str:
        """BUG-132 FIX: Validate tenant_id to prevent path traversal and injection."""
        if not _SAFE_TENANT_ID.match(tenant_id):
            raise ValueError(f"Invalid tenant_id format: {tenant_id!r}")
        return tenant_id

    @property
    def _container_prefix(self) -> str:
        """BUG-448: Use TSN_STACK_NAME for runtime container isolation."""
        stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
        return f"{stack_name}-toolbox-"

    def _get_container_name(self, tenant_id: str) -> str:
        """Generate container name for tenant"""
        self._validate_tenant_id(tenant_id)
        return f"{self._container_prefix}{tenant_id}"

    def _get_image_tag(self, tenant_id: str) -> str:
        """Get tenant-specific image tag"""
        self._validate_tenant_id(tenant_id)
        return f"tsushin-toolbox:{tenant_id}"

    def _get_workspace_path(self, tenant_id: str) -> Path:
        """Get workspace directory path for tenant"""
        self._validate_tenant_id(tenant_id)

        backend_dir = Path(__file__).parent.parent
        workspace_base = backend_dir / "data" / "workspace"
        workspace_dir = workspace_base / tenant_id

        # BUG-132 FIX: Path traversal guard — ensure resolved path stays under base
        resolved = workspace_dir.resolve()
        base_resolved = workspace_base.resolve()
        if not str(resolved).startswith(str(base_resolved) + os.sep) and resolved != base_resolved:
            raise ValueError(f"Path traversal detected for tenant_id: {tenant_id!r}")

        # Ensure base workspace directory exists with proper permissions
        workspace_base.mkdir(parents=True, exist_ok=True)

        # BUG-064 FIX: Use restrictive permissions (750) instead of world-writable (777)
        try:
            os.chmod(workspace_base, 0o750)
        except OSError as e:
            logger.warning(f"Could not chmod base workspace dir: {e}")

        # Create tenant workspace directory
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # BUG-064 FIX: Use restrictive permissions (750) instead of world-writable (777)
        # Toolbox container runs as non-root 'toolbox' user for security
        try:
            os.chmod(workspace_dir, 0o750)
            # Also try to set ownership to UID 1000 (toolbox user) if running as root
            if os.geteuid() == 0:
                os.chown(workspace_dir, 1000, 1000)
        except OSError as e:
            logger.warning(f"Could not set workspace permissions: {e}")

        return workspace_dir

    def _get_host_workspace_path(self, tenant_id: str) -> str:
        """Get host filesystem path for Docker volume mount"""
        workspace_path = self._get_workspace_path(tenant_id)
        workspace_str = str(workspace_path)

        # If running inside Docker container, convert to host path
        if workspace_str.startswith('/app/data/'):
            # Use environment variable for host path (required for Docker-in-Docker)
            host_backend_data = os.getenv('HOST_BACKEND_DATA_PATH', '')
            if not host_backend_data:
                raise ValueError("HOST_BACKEND_DATA_PATH environment variable must be set for Docker-in-Docker operations")
            workspace_str = workspace_str.replace('/app/data', host_backend_data)
            logger.debug(f"Converted container path to host path: {workspace_str}")

        return workspace_str

    def _get_or_create_network(self):
        """Get or create the tsushin Docker network"""
        # Use raw_client for network name resolution (docker_network_utils needs docker client)
        if hasattr(self.runtime, 'raw_client'):
            network_name = resolve_tsushin_network_name(self.runtime.raw_client)
        else:
            # Non-Docker runtimes: use canonical name
            network_name = "tsushin-network"
        return self.runtime.get_or_create_network(network_name)

    def _resolve_network_name(self) -> str:
        """Resolve the tsushin network name."""
        if hasattr(self.runtime, 'raw_client'):
            return resolve_tsushin_network_name(self.runtime.raw_client)
        return "tsushin-network"

    def get_container_status(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get container status for a tenant

        Args:
            tenant_id: Tenant ID

        Returns:
            Dict with container status information
        """
        container_name = self._get_container_name(tenant_id)

        status = {
            'tenant_id': tenant_id,
            'container_name': container_name,
            'status': 'not_created',
            'container_id': None,
            'image': None,
            'created_at': None,
            'started_at': None,
            'health': 'unknown',
            'error': None
        }

        try:
            attrs = self.runtime.get_container_attrs(container_name)

            status['status'] = attrs['status']
            status['container_id'] = attrs['id']
            status['image'] = attrs['image_tags'][0] if attrs['image_tags'] else str(attrs['id'])[:12]
            status['created_at'] = attrs.get('created')

            # Get started timestamp
            state = attrs.get('state', {})
            status['started_at'] = state.get('StartedAt')

            # Determine health based on container status
            if attrs['status'] == 'running':
                status['health'] = 'healthy'
            elif attrs['status'] == 'exited':
                status['health'] = 'stopped'
            else:
                status['health'] = attrs['status']

        except ContainerNotFoundError:
            status['status'] = 'not_created'
            status['health'] = 'not_created'
            logger.debug(f"Container not found for tenant {tenant_id}")
        except ContainerRuntimeError as e:
            status['status'] = 'error'
            status['health'] = 'error'
            status['error'] = str(e)
            logger.error(f"Runtime error checking status for tenant {tenant_id}: {e}")

        return status

    def ensure_container_running(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Ensure tenant's toolbox container is running, creating if necessary

        Args:
            tenant_id: Tenant ID
            db: Database session (for updating ToolboxContainer record)

        Returns:
            Container status dict
        """
        container_name = self._get_container_name(tenant_id)

        try:
            container_status = self.runtime.get_container_status(container_name)

            if container_status == 'not_found':
                # Container doesn't exist, create it
                logger.info(f"Creating new toolbox container for tenant {tenant_id}")
                return self.create_container(tenant_id, db)

            if container_status != 'running':
                logger.info(f"Starting existing container {container_name}")
                self.runtime.start_container(container_name)
                time.sleep(1)  # Brief wait for startup
                # Fix workspace permissions after restart
                self._fix_workspace_permissions(container_name)

            return self.get_container_status(tenant_id)

        except ContainerNotFoundError:
            # Container doesn't exist, create it
            logger.info(f"Creating new toolbox container for tenant {tenant_id}")
            return self.create_container(tenant_id, db)

    def _fix_workspace_permissions(self, container_name: str) -> bool:
        """
        Fix workspace permissions inside the container by running chmod as root.
        This ensures the toolbox user (UID 1000) can write to the workspace.

        Args:
            container_name: Container name

        Returns:
            True if permissions were fixed successfully
        """
        try:
            # BUG-064 FIX: Use restrictive permissions (750) instead of world-writable (777)
            exec_result = self.runtime.exec_run(
                container_name,
                cmd=["chmod", "750", "/workspace"],
                user="root",
                workdir="/workspace",
            )
            if exec_result.exit_code == 0:
                logger.info("Fixed workspace permissions (chmod 750)")
                # Also set proper ownership for toolbox user
                chown_result = self.runtime.exec_run(
                    container_name,
                    cmd=["chown", "-R", "1000:1000", "/workspace"],
                    user="root",
                    workdir="/",
                )
                if chown_result.exit_code != 0:
                    logger.warning(f"Failed to chown workspace: {chown_result.output}")
                return True
            else:
                logger.warning(f"Failed to fix workspace permissions: {exec_result.output}")
                return False
        except Exception as e:
            logger.warning(f"Could not fix workspace permissions: {e}")
            return False

    def create_container(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Create and start toolbox container for a tenant

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Container status dict

        Raises:
            RuntimeError: If container creation fails
        """
        container_name = self._get_container_name(tenant_id)
        logger.info(f"Creating toolbox container {container_name} for tenant {tenant_id}")

        # Determine which image to use
        tenant_image = self._get_image_tag(tenant_id)
        if self.runtime.image_exists(tenant_image):
            image_to_use = tenant_image
            logger.info(f"Using tenant-specific image: {tenant_image}")
        elif self.runtime.image_exists(self.BASE_IMAGE):
            image_to_use = self.BASE_IMAGE
            logger.info(f"Using base image: {self.BASE_IMAGE}")
        else:
            raise RuntimeError(
                f"Toolbox base image not found. Please build it first: "
                f"docker build -f backend/containers/Dockerfile.toolbox -t {self.BASE_IMAGE} ."
            )

        # Get workspace path
        host_workspace = self._get_host_workspace_path(tenant_id)
        logger.info(f"Workspace mount: {host_workspace} -> /workspace")

        # Ensure network exists
        network = self._get_or_create_network()
        network_name = network.name if hasattr(network, 'name') else str(network)

        try:
            # Remove existing container if it exists but is stopped
            try:
                existing_status = self.runtime.get_container_status(container_name)
                if existing_status != 'not_found':
                    if existing_status == 'running':
                        # Already running
                        return self.get_container_status(tenant_id)
                    else:
                        self.runtime.remove_container(container_name)
                        logger.info(f"Removed stopped container {container_name}")
            except (ContainerNotFoundError, ContainerRuntimeError):
                pass

            # Create and start container
            container = self.runtime.create_container(
                image=image_to_use,
                name=container_name,
                volumes={
                    host_workspace: {'bind': '/workspace', 'mode': 'rw,z'}
                },
                environment={
                    'TENANT_ID': tenant_id,
                },
                restart_policy={"Name": "unless-stopped"},
                network=network_name,
                # Resource limits for security
                # Increased to 2GB for memory-intensive tools like nuclei
                mem_limit='2g',
                memswap_limit='4g',  # Allow swap for heavy scans
                cpu_quota=100000,  # Full CPU for heavy tools
                # Security hardening (Phase 23: C-2)
                security_opt=["no-new-privileges:true"],
                cap_drop=["ALL"],
                pids_limit=256,
                # Security H-1: External DNS to prevent internal service name resolution attacks
                dns=["8.8.8.8", "8.8.4.4"],
            )

            container_id = container.id if hasattr(container, 'id') else str(container)
            logger.info(f"Container {container_name} created with ID {container_id}")

            # Fix workspace permissions immediately after container creation
            # This runs chmod as root to ensure the toolbox user can write files
            time.sleep(0.5)  # Brief wait for container to fully start
            self._fix_workspace_permissions(container_name)

            # Update database record
            self._update_db_record(tenant_id, container_id, 'running', image_to_use, db)

            return self.get_container_status(tenant_id)

        except ContainerRuntimeError as e:
            logger.error(f"Failed to create container for tenant {tenant_id}: {e}")
            raise RuntimeError(f"Failed to create toolbox container: {e}")

    def start_container(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Start existing container

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Container status dict
        """
        container_name = self._get_container_name(tenant_id)

        try:
            status = self.runtime.get_container_status(container_name)

            if status == 'running':
                logger.info(f"Container {container_name} already running")
                return self.get_container_status(tenant_id)

            if status == 'not_found':
                # Container doesn't exist, create it
                return self.create_container(tenant_id, db)

            self.runtime.start_container(container_name)
            logger.info(f"Container {container_name} started")

            self._update_db_status(tenant_id, 'running', db)

            return self.get_container_status(tenant_id)

        except ContainerNotFoundError:
            # Container doesn't exist, create it
            return self.create_container(tenant_id, db)
        except ContainerRuntimeError as e:
            logger.error(f"Failed to start container: {e}")
            raise RuntimeError(f"Failed to start container: {e}")

    def stop_container(self, tenant_id: str, db: Session, timeout: int = 30) -> Dict[str, Any]:
        """
        Stop container gracefully

        Args:
            tenant_id: Tenant ID
            db: Database session
            timeout: Graceful shutdown timeout (seconds)

        Returns:
            Container status dict
        """
        container_name = self._get_container_name(tenant_id)

        try:
            status = self.runtime.get_container_status(container_name)

            if status != 'running':
                logger.info(f"Container {container_name} already stopped")
                return self.get_container_status(tenant_id)

            self.runtime.stop_container(container_name, timeout=timeout)
            logger.info(f"Container {container_name} stopped")

            self._update_db_status(tenant_id, 'stopped', db)

            return self.get_container_status(tenant_id)

        except ContainerNotFoundError:
            logger.warning(f"Container {container_name} not found")
            return self.get_container_status(tenant_id)
        except ContainerRuntimeError as e:
            logger.error(f"Failed to stop container: {e}")
            raise RuntimeError(f"Failed to stop container: {e}")

    def restart_container(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Restart container

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Container status dict
        """
        container_name = self._get_container_name(tenant_id)
        logger.info(f"Restarting container {container_name}")

        try:
            self.runtime.restart_container(container_name, timeout=30)
            logger.info(f"Container {container_name} restarted")

            self._update_db_status(tenant_id, 'running', db)

            return self.get_container_status(tenant_id)

        except ContainerNotFoundError:
            # Create if doesn't exist
            return self.create_container(tenant_id, db)
        except ContainerRuntimeError as e:
            logger.error(f"Failed to restart container: {e}")
            raise RuntimeError(f"Failed to restart container: {e}")

    def delete_container(self, tenant_id: str, db: Session, remove_workspace: bool = False) -> Dict[str, Any]:
        """
        Delete container and optionally remove workspace

        Args:
            tenant_id: Tenant ID
            db: Database session
            remove_workspace: If True, delete workspace directory

        Returns:
            Status dict
        """
        container_name = self._get_container_name(tenant_id)

        try:
            status = self.runtime.get_container_status(container_name)

            if status != 'not_found':
                # Stop if running
                if status == 'running':
                    self.runtime.stop_container(container_name, timeout=10)

                self.runtime.remove_container(container_name)
                logger.info(f"Container {container_name} removed")

        except ContainerNotFoundError:
            logger.info(f"Container {container_name} not found (already removed)")
        except ContainerRuntimeError as e:
            logger.error(f"Failed to remove container: {e}")

        # Optionally remove workspace
        if remove_workspace:
            workspace_path = self._get_workspace_path(tenant_id)
            if workspace_path.exists():
                import shutil
                shutil.rmtree(workspace_path)
                logger.info(f"Workspace removed: {workspace_path}")

        # Update database
        self._delete_db_record(tenant_id, db)

        return {'status': 'deleted', 'tenant_id': tenant_id}

    def _kill_running_execs(self, container_name: str):
        """Best-effort kill of any running exec processes in the container."""
        try:
            self.runtime.exec_run(
                container_name,
                cmd=["sh", "-c", "kill -9 $(ps -o pid= | grep -v '^ *1$') 2>/dev/null || true"],
                user="root",
                detach=True,
            )
            logger.info(f"Sent kill signal to processes in {container_name}")
        except Exception as e:
            logger.warning(f"Failed to kill processes in {container_name}: {e}")

    async def execute_command(
        self,
        tenant_id: str,
        command: str,
        timeout: int = None,
        workdir: str = "/workspace",
        db: Session = None,
        user: str = None
    ) -> Dict[str, Any]:
        """
        Execute command in tenant's container with timeout enforcement.

        Uses two-layer timeout:
          Layer A: Linux `timeout` command wraps the process inside the container
          Layer B: asyncio.wait_for wraps the Docker API call as a safety net

        Args:
            tenant_id: Tenant ID
            command: Command to execute
            timeout: Execution timeout in seconds
            workdir: Working directory inside container
            db: Database session
            user: User to run command as (default: container's default user, 'root' for privileged)

        Returns:
            Dict with execution results (exit_code, stdout, stderr, execution_time_ms)

        Raises:
            RuntimeError: If execution fails
        """
        container_name = self._get_container_name(tenant_id)
        timeout = timeout or self.COMMAND_TIMEOUT

        logger.info(f"Executing command in {container_name} (user={user}, timeout={timeout}s): {command[:100]}...")

        try:
            # Ensure container is running
            status = self.runtime.get_container_status(container_name)
            if status != 'running':
                self.runtime.start_container(container_name)
                time.sleep(1)

            start_time = time.time()

            # Layer A: Wrap command in Linux `timeout` for process-level enforcement
            # Sends SIGTERM first, then SIGKILL after 10s grace period
            wrapped_command = f"timeout --signal=TERM --kill-after=10 {timeout} sh -c {shlex.quote(command)}"

            # Build exec options
            exec_opts = {
                'cmd': ["sh", "-c", wrapped_command],
                'workdir': workdir,
                'demux': True,  # Separate stdout/stderr
                'environment': {'TERM': 'xterm'},
            }

            # Set user if specified
            if user:
                exec_opts['user'] = user

            # Layer B: Safety net — run exec_run in thread with asyncio timeout
            # Extra 30s buffer so Linux timeout handles it first
            safety_timeout = timeout + 30

            try:
                exec_result = await asyncio.wait_for(
                    asyncio.to_thread(
                        self.runtime.exec_run,
                        container_name,
                        **exec_opts
                    ),
                    timeout=safety_timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Safety timeout ({safety_timeout}s) reached for command in {container_name}")
                self._kill_running_execs(container_name)
                execution_time_ms = int((time.time() - start_time) * 1000)
                return {
                    'success': False,
                    'exit_code': -1,
                    'stdout': '',
                    'stderr': f'Command timed out after {timeout} seconds (safety timeout triggered)',
                    'execution_time_ms': execution_time_ms,
                    'command': command,
                    'tenant_id': tenant_id,
                    'timed_out': True,
                    'oom_killed': False
                }

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Parse output
            stdout_bytes, stderr_bytes = exec_result.output
            stdout = stdout_bytes.decode('utf-8', errors='replace') if stdout_bytes else ''
            stderr = stderr_bytes.decode('utf-8', errors='replace') if stderr_bytes else ''

            # Interpret special exit codes
            exit_code = exec_result.exit_code
            timed_out = False
            oom_killed = False

            if exit_code == 124:
                # Linux `timeout` command: process exceeded time limit
                timed_out = True
                stderr = f"Command timed out after {timeout} seconds.\n{stderr}".strip()
                logger.warning(f"Command timed out (exit 124) in {container_name}: {command[:100]}")
            elif exit_code in (137, -9):
                # SIGKILL — typically OOM killer
                oom_killed = True
                stderr = f"Process was killed (likely out of memory — container limit: 2GB).\n{stderr}".strip()
                logger.warning(f"Command OOM killed (exit {exit_code}) in {container_name}: {command[:100]}")

            result = {
                'success': exit_code == 0,
                'exit_code': exit_code,
                'stdout': stdout,
                'stderr': stderr,
                'execution_time_ms': execution_time_ms,
                'command': command,
                'tenant_id': tenant_id,
                'timed_out': timed_out,
                'oom_killed': oom_killed
            }

            logger.info(f"Command completed in {execution_time_ms}ms with exit code {exit_code}")

            return result

        except ContainerNotFoundError:
            raise RuntimeError(f"Container not found for tenant {tenant_id}. Please start it first.")
        except ContainerRuntimeError as e:
            logger.error(f"Runtime error executing command: {e}")
            raise RuntimeError(f"Command execution failed: {e}")

    async def execute_command_streaming(
        self,
        tenant_id: str,
        command: str,
        timeout: int = None,
        workdir: str = "/workspace"
    ):
        """
        Execute command with streaming output (generator)

        Yields:
            Dict with partial output {'type': 'stdout'|'stderr', 'data': str}
        """
        container_name = self._get_container_name(tenant_id)
        timeout = timeout or self.COMMAND_TIMEOUT

        try:
            # Ensure container is running
            status = self.runtime.get_container_status(container_name)
            if status != 'running':
                self.runtime.start_container(container_name)
                time.sleep(1)

            # Wrap command in Linux `timeout` for process-level enforcement
            wrapped_command = f"timeout --signal=TERM --kill-after=10 {timeout} sh -c {shlex.quote(command)}"

            # Create exec instance and start with streaming
            exec_id, output = self.runtime.exec_create_and_start(
                container_name,
                ["sh", "-c", wrapped_command],
                workdir=workdir,
                stream=True,
                demux=True,
            )

            for stdout_chunk, stderr_chunk in output:
                if stdout_chunk:
                    yield {'type': 'stdout', 'data': stdout_chunk.decode('utf-8', errors='replace')}
                if stderr_chunk:
                    yield {'type': 'stderr', 'data': stderr_chunk.decode('utf-8', errors='replace')}

            # Get exit code
            exec_info = self.runtime.exec_inspect(exec_id)
            yield {'type': 'exit', 'exit_code': exec_info.get('ExitCode', -1)}

        except ContainerNotFoundError:
            yield {'type': 'error', 'error': f"Container not found for tenant {tenant_id}"}
        except ContainerRuntimeError as e:
            yield {'type': 'error', 'error': str(e)}

    async def install_package(
        self,
        tenant_id: str,
        package_name: str,
        package_type: str,  # 'pip' or 'apt'
        db: Session
    ) -> Dict[str, Any]:
        """
        Install a package in the tenant's container

        Args:
            tenant_id: Tenant ID
            package_name: Package name to install
            package_type: 'pip' for Python packages, 'apt' for system packages
            db: Database session

        Returns:
            Installation result dict
        """
        # BUG-063 FIX: Validate package name to prevent command injection
        if package_type == 'pip' and not SAFE_PIP_PACKAGE.match(package_name):
            raise ValueError(
                f"Invalid pip package name '{package_name}'. "
                "Only letters, numbers, dots, hyphens, underscores allowed, "
                "optionally with version specifier (e.g., ==1.0.0)."
            )
        elif package_type == 'apt' and not SAFE_APT_PACKAGE.match(package_name):
            raise ValueError(
                f"Invalid apt package name '{package_name}'. "
                "Only letters, numbers, dots, hyphens, plus signs allowed."
            )

        if len(package_name) > 200:
            raise ValueError("Package name too long (max 200 characters)")

        # Determine command and user based on package type
        if package_type == 'pip':
            command = f"pip install --user {shlex.quote(package_name)}"
            user = None  # Use default user
        elif package_type == 'apt':
            # apt requires root privileges
            command = f"apt-get update && apt-get install -y {shlex.quote(package_name)}"
            user = "root"  # Run as root for system package installation
        else:
            raise ValueError(f"Unknown package type: {package_type}")

        logger.info(f"Installing {package_type} package '{package_name}' for tenant {tenant_id} (user={user})")

        result = await self.execute_command(tenant_id, command, timeout=300, db=db, user=user)

        if result['success']:
            # Record installation in database
            self._record_package_installation(tenant_id, package_name, package_type, db)
            logger.info(f"Package '{package_name}' installed successfully for tenant {tenant_id}")
        else:
            logger.error(f"Failed to install package '{package_name}': {result['stderr']}")

        return result

    def commit_container(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Commit current container state to a tenant-specific image

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Commit result dict with new image info
        """
        container_name = self._get_container_name(tenant_id)
        new_image_tag = self._get_image_tag(tenant_id)

        logger.info(f"Committing container {container_name} to image {new_image_tag}")

        try:
            image = self.runtime.commit_container(
                container_name,
                repository="tsushin-toolbox",
                tag=tenant_id,
                message=f"Committed by tenant {tenant_id} at {datetime.utcnow().isoformat() + 'Z'}",
            )
        except ContainerRuntimeError as e:
            if "not supported" in str(e).lower():
                # K8s mode: commit not supported — mark packages as committed in DB only
                logger.warning(f"Container commit not supported in current runtime, marking packages committed in DB only")
                self._mark_packages_committed(tenant_id, db)
                return {
                    'success': True,
                    'image_tag': new_image_tag,
                    'image_id': 'db-only',
                    'committed_at': datetime.utcnow().isoformat() + "Z",
                    'note': 'Packages recorded in DB. Use CI/CD to build custom images for K8s.'
                }
            raise

        try:

            image_id = image.id if hasattr(image, 'id') else str(image)
            logger.info(f"Container committed as {new_image_tag} (ID: {image_id[:12]})")

            # Update database to mark packages as committed
            self._mark_packages_committed(tenant_id, db)

            # Update container record with new image
            self._update_db_image(tenant_id, new_image_tag, db)

            return {
                'success': True,
                'image_tag': new_image_tag,
                'image_id': image_id,
                'committed_at': datetime.utcnow().isoformat() + "Z"
            }

        except ContainerNotFoundError:
            raise RuntimeError(f"Container not found for tenant {tenant_id}")
        except ContainerRuntimeError as e:
            logger.error(f"Failed to commit container: {e}")
            raise RuntimeError(f"Failed to commit container: {e}")

    def reset_to_base(self, tenant_id: str, db: Session) -> Dict[str, Any]:
        """
        Reset tenant to base image (delete tenant-specific image and recreate container)

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            Reset result dict
        """
        container_name = self._get_container_name(tenant_id)
        tenant_image = self._get_image_tag(tenant_id)

        logger.info(f"Resetting tenant {tenant_id} to base image")

        # Stop and remove container
        try:
            status = self.runtime.get_container_status(container_name)
            if status == 'running':
                self.runtime.stop_container(container_name, timeout=10)
            if status != 'not_found':
                self.runtime.remove_container(container_name)
            logger.info(f"Container {container_name} removed")
        except (ContainerNotFoundError, ContainerRuntimeError):
            pass

        # Remove tenant-specific image
        if self.runtime.image_exists(tenant_image):
            try:
                self.runtime.remove_image(tenant_image, force=True)
                logger.info(f"Tenant image {tenant_image} removed")
            except ContainerRuntimeError as e:
                logger.warning(f"Failed to remove tenant image: {e}")

        # Clear package records
        self._clear_package_records(tenant_id, db)

        # Recreate container from base image
        return self.create_container(tenant_id, db)

    def list_installed_packages(self, tenant_id: str, db: Session) -> List[Dict[str, Any]]:
        """
        List packages installed in tenant's container

        Args:
            tenant_id: Tenant ID
            db: Database session

        Returns:
            List of package dicts
        """
        from models import ToolboxPackage

        packages = db.query(ToolboxPackage).filter(
            ToolboxPackage.tenant_id == tenant_id
        ).order_by(ToolboxPackage.installed_at.desc()).all()

        return [
            {
                'id': pkg.id,
                'package_name': pkg.package_name,
                'package_type': pkg.package_type,
                'version': pkg.version,
                'installed_at': pkg.installed_at.isoformat() if pkg.installed_at else None,
                'is_committed': pkg.is_committed
            }
            for pkg in packages
        ]

    # ========================================================================
    # Database Helper Methods
    # ========================================================================

    def _update_db_record(self, tenant_id: str, container_id: str, status: str, image_tag: str, db: Session):
        """Update or create ToolboxContainer record"""
        from models import ToolboxContainer

        record = db.query(ToolboxContainer).filter(
            ToolboxContainer.tenant_id == tenant_id
        ).first()

        now = datetime.utcnow()

        if record:
            record.container_id = container_id
            record.status = status
            record.image_tag = image_tag
            record.last_started_at = now
            record.updated_at = now
        else:
            record = ToolboxContainer(
                tenant_id=tenant_id,
                container_id=container_id,
                status=status,
                image_tag=image_tag,
                last_started_at=now,
                created_at=now,
                updated_at=now
            )
            db.add(record)

        db.commit()

    def _update_db_status(self, tenant_id: str, status: str, db: Session):
        """Update container status in database"""
        from models import ToolboxContainer

        record = db.query(ToolboxContainer).filter(
            ToolboxContainer.tenant_id == tenant_id
        ).first()

        if record:
            record.status = status
            record.updated_at = datetime.utcnow()
            if status == 'running':
                record.last_started_at = datetime.utcnow()
            db.commit()

    def _update_db_image(self, tenant_id: str, image_tag: str, db: Session):
        """Update image tag in database after commit"""
        from models import ToolboxContainer

        record = db.query(ToolboxContainer).filter(
            ToolboxContainer.tenant_id == tenant_id
        ).first()

        if record:
            record.image_tag = image_tag
            record.last_commit_at = datetime.utcnow()
            record.updated_at = datetime.utcnow()
            db.commit()

    def _delete_db_record(self, tenant_id: str, db: Session):
        """Delete ToolboxContainer record"""
        from models import ToolboxContainer

        record = db.query(ToolboxContainer).filter(
            ToolboxContainer.tenant_id == tenant_id
        ).first()

        if record:
            db.delete(record)
            db.commit()

    def _record_package_installation(self, tenant_id: str, package_name: str, package_type: str, db: Session):
        """Record package installation in database"""
        from models import ToolboxPackage

        # Check if already exists
        existing = db.query(ToolboxPackage).filter(
            ToolboxPackage.tenant_id == tenant_id,
            ToolboxPackage.package_name == package_name,
            ToolboxPackage.package_type == package_type
        ).first()

        if existing:
            existing.installed_at = datetime.utcnow()
            existing.is_committed = False
        else:
            package = ToolboxPackage(
                tenant_id=tenant_id,
                package_name=package_name,
                package_type=package_type,
                installed_at=datetime.utcnow(),
                is_committed=False
            )
            db.add(package)

        db.commit()

    def _mark_packages_committed(self, tenant_id: str, db: Session):
        """Mark all packages as committed after image commit"""
        from models import ToolboxPackage

        db.query(ToolboxPackage).filter(
            ToolboxPackage.tenant_id == tenant_id
        ).update({'is_committed': True})

        db.commit()

    def _clear_package_records(self, tenant_id: str, db: Session):
        """Clear all package records for tenant (on reset)"""
        from models import ToolboxPackage

        db.query(ToolboxPackage).filter(
            ToolboxPackage.tenant_id == tenant_id
        ).delete()

        db.commit()


# Singleton instance
_toolbox_service = None


def get_toolbox_service() -> ToolboxContainerService:
    """Get singleton instance of ToolboxContainerService"""
    global _toolbox_service
    if _toolbox_service is None:
        _toolbox_service = ToolboxContainerService()
    return _toolbox_service
