"""
Docker Container Manager for WhatsApp MCP
Phase 8: Multi-Tenant MCP Containerization

Manages Docker containers for WhatsApp MCP instances.
Handles container lifecycle: create, start, stop, restart, delete.
"""

import os
import time
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict, Tuple
from sqlalchemy.orm import Session

from models import WhatsAppMCPInstance, Agent
from services.port_allocator import get_port_allocator
from services.mcp_auth_service import generate_mcp_secret
from services.docker_network_utils import resolve_tsushin_network_name
from services.container_runtime import (
    get_container_runtime,
    ContainerRuntime,
    ContainerNotFoundError,
    ContainerRuntimeError,
)

logger = logging.getLogger(__name__)


class MCPContainerManager:
    """Manages Docker containers for WhatsApp MCP instances"""

    IMAGE_NAME = "tsushin/whatsapp-mcp:latest"
    CONTAINER_PREFIX = "mcp-"
    HEALTH_CHECK_TIMEOUT = 60  # seconds
    HEALTH_CHECK_INTERVAL = 5  # seconds
    DNS_FALLBACK_ENV = "WHATSAPP_MCP_DNS_SERVERS"
    TESTER_CONTAINER_NAME = "tester-mcp"
    TESTER_API_URL = os.getenv("TESTER_MCP_API_URL", "http://tester-mcp:8080/api")

    def __init__(self):
        """Initialize container runtime"""
        self.runtime: ContainerRuntime = get_container_runtime()
        logger.info("MCPContainerManager initialized with container runtime")

    def _resolve_network_name(self) -> str:
        """Resolve the tsushin network name."""
        if hasattr(self.runtime, 'raw_client'):
            return resolve_tsushin_network_name(self.runtime.raw_client)
        return "tsushin-network"

    def create_instance(
        self,
        tenant_id: str,
        phone_number: str,
        db: Session,
        created_by: int,
        instance_type: str = "agent"
    ) -> WhatsAppMCPInstance:
        """
        Create and start new MCP container

        Args:
            tenant_id: Tenant ID
            phone_number: WhatsApp phone number
            db: Database session
            created_by: User ID who created the instance
            instance_type: Instance type ("agent" or "tester")

        Returns:
            WhatsAppMCPInstance: Created instance

        Raises:
            RuntimeError: If container creation fails
        """
        logger.info(f"Creating MCP instance ({instance_type}) for tenant {tenant_id}, phone {phone_number}")

        # 1. Allocate port
        port_allocator = get_port_allocator()
        port = port_allocator.allocate_port(db)
        logger.info(f"Allocated port {port}")

        # 1.5. Generate API secret (Phase Security-1: SSRF Prevention)
        api_secret = generate_mcp_secret()
        logger.info(f"Generated API secret for MCP authentication")

        # 2. Generate container name (unique with timestamp, includes type)
        container_name = f"{self.CONTAINER_PREFIX}{instance_type}-{tenant_id}_{int(time.time())}"

        # 3. Create volume directories (unique per instance)
        session_dir = self._create_session_directory(tenant_id, container_name)
        logger.info(f"Created session directory: {session_dir}")

        # 4. Start container
        try:
            container = self._start_container(container_name, port, session_dir, phone_number, api_secret)
            container_id = container.id if hasattr(container, 'id') else str(container)
            logger.info(f"Container {container_name} started with ID {container_id}")

        except Exception as e:
            logger.error(f"Failed to start container: {e}")
            raise RuntimeError(f"Failed to start Docker container: {e}")

        # 5. Use container name for Docker DNS resolution (more robust than IP)
        # Container name is resolvable within the Docker network
        logger.info(f"Container {container_name} created on tsushin network")

        # 6. Convert session_dir to container path for watcher
        # Host path: .../backend/data/... -> Container path: /app/data/...
        # Find 'data' directory in path and make everything after it relative to /app/data
        session_path = Path(session_dir)
        path_parts = session_path.parts

        # Find the index of 'data' in the path
        try:
            data_index = path_parts.index('data')
            # Take everything after 'data' (e.g., mcp/tenant/container/store)
            relative_parts = path_parts[data_index + 1:]
            container_session_dir = str(Path("/app/data").joinpath(*relative_parts))
        except ValueError:
            # Fallback: use old method with production path
            container_session_dir = session_dir.replace("/opt/tsushin/backend/data/", "/app/data/")
            if container_session_dir == session_dir:
                # Last resort: just use /app/data prefix with mcp subdirectory
                container_session_dir = f"/app/data/mcp/{tenant_id}/{container_name}/store"

        logger.info(f"Container session path: {container_session_dir}")

        # 7. Save to database with container-accessible paths
        # Use container name for Docker DNS (resilient to IP changes on restart)
        instance = WhatsAppMCPInstance(
            tenant_id=tenant_id,
            container_name=container_name,
            phone_number=phone_number,
            instance_type=instance_type,
            mcp_api_url=f"http://{container_name}:8080/api",
            mcp_port=port,
            messages_db_path=str(Path(container_session_dir) / "messages.db"),
            session_data_path=container_session_dir,
            status="starting",
            health_status="unknown",
            container_id=container_id,
            created_by=created_by,
            last_started_at=datetime.utcnow(),
            # Phase Security-1: API authentication
            api_secret=api_secret,
            api_secret_created_at=datetime.utcnow()
        )

        db.add(instance)
        db.commit()
        db.refresh(instance)

        logger.info(f"MCP instance {instance.id} created in database")

        # 6. Wait for health check (async, don't block)
        # Health check will be updated by periodic health monitoring
        logger.info(f"Container {container_name} starting, health check in progress")

        return instance

    def _create_session_directory(self, tenant_id: str, container_name: str) -> str:
        """
        Create unique session directory for instance

        Each instance gets its own isolated session directory to prevent
        session data conflicts between instances.

        Args:
            tenant_id: Tenant ID
            container_name: Unique container name

        Returns:
            Path to session directory
        """
        # Use absolute path from backend directory
        # Structure: data/mcp/{tenant_id}/{container_name}/store
        backend_dir = Path(__file__).parent.parent
        session_dir = backend_dir / "data" / "mcp" / tenant_id / container_name / "store"

        os.makedirs(session_dir, exist_ok=True)

        # Fix permissions for container user (UID 1000, GID 1000)
        # The WhatsApp MCP container runs as non-root user whatsapp:1000
        # Without this, the container can't create SQLite database files
        try:
            os.chmod(session_dir, 0o777)
            # Also fix parent directory (container_name level)
            os.chmod(session_dir.parent, 0o777)
            try:
                os.chown(session_dir, 1000, 1000)
                os.chown(session_dir.parent, 1000, 1000)
            except OSError:
                pass  # chown may fail on some systems, chmod 777 is sufficient
        except OSError as e:
            logger.warning(f"Could not set session directory permissions: {e}")

        logger.info(f"Created unique session directory for {container_name}: {session_dir}")
        return str(session_dir)

    def _start_container(
        self,
        container_name: str,
        port: int,
        session_dir: str,
        phone_number: str,
        api_secret: Optional[str] = None
    ):
        """
        Start Docker container

        Args:
            container_name: Container name
            port: Host port
            session_dir: Session directory path
            phone_number: WhatsApp phone number
            api_secret: API authentication secret (Phase Security-1)

        Returns:
            Container object

        Raises:
            ContainerRuntimeError: If container start fails
        """
        # Convert session_dir to absolute path
        session_dir_abs = os.path.abspath(session_dir)

        # CRITICAL FIX: When running inside Docker container, convert container path to host path
        # Backend container mounts ./backend/data:/app/data (from docker-compose.yml)
        # So /app/data/mcp/... needs to become {HOST_BACKEND_DATA_PATH}/mcp/...
        # Docker volume mounts require HOST filesystem paths, not container paths
        if session_dir_abs.startswith('/app/data/'):
            # We're in a container, need to map to host path
            # HOST_BACKEND_DATA_PATH must be set in .env (installer generates this automatically)
            host_backend_data = os.getenv('HOST_BACKEND_DATA_PATH')
            if not host_backend_data:
                raise RuntimeError(
                    "HOST_BACKEND_DATA_PATH environment variable is not set. "
                    "This is required for Docker-in-Docker volume mounts. "
                    "Run the installer (python3 install.py) to configure this automatically, "
                    "or set it manually in your .env file to the absolute path of backend/data on your host."
                )
            # Replace /app/data with host path
            session_dir_abs = session_dir_abs.replace('/app/data', host_backend_data)
            logger.info(f"Converted container path to host path for Docker volume mount: {session_dir_abs}")

        logger.info(f"Starting container {container_name} on port {port}")
        logger.info(f"Volume mount: {session_dir_abs} -> /app/store")

        # Check if tsushin network exists, create if not
        network_name = self._resolve_network_name()
        self.runtime.get_or_create_network(network_name)

        container = self.runtime.create_container(
            image=self.IMAGE_NAME,
            name=container_name,
            ports={'8080/tcp': ('127.0.0.1', port)},  # Also expose on localhost for debugging
            volumes={
                session_dir_abs: {'bind': '/app/store', 'mode': 'rw,z'},
                # Shared audio volume for TTS - allows backend to generate audio and MCP to read it
                'tsushin-audio': {'bind': '/tmp/tsushin_audio', 'mode': 'ro,z'},
                # Shared screenshots volume for browser automation
                'tsushin-screenshots': {'bind': '/tmp/tsushin_screenshots', 'mode': 'ro,z'},
                # Shared images volume for ImageSkill
                'tsushin-images': {'bind': '/tmp/tsushin_images', 'mode': 'ro,z'}
            },
            environment={
                'PHONE_NUMBER': phone_number,
                # Phase Security-1: API authentication secret
                'MCP_API_SECRET': api_secret or ''
            },
            restart_policy={"Name": "unless-stopped"},
            network=network_name,  # Connect to tsushin network for backend communication
            command=["--port", "8080"],
            dns=self._get_dns_servers(),
        )

        return container

    def _get_or_create_tsushin_network(self):
        """Get or create the tsushin Docker network"""
        network_name = self._resolve_network_name()
        return self.runtime.get_or_create_network(network_name)

    def _ensure_container_on_tsushin_network(self, container_name_or_id: str):
        """
        Ensure container is connected to tsushin network for backend communication.

        This is critical because:
        1. Backend needs to reach MCP container via container name (Docker DNS)
        2. If container was manually started or network was disconnected, this reconnects it

        Args:
            container_name_or_id: Container name or ID
        """
        network_name = self._resolve_network_name()
        try:
            self.runtime.ensure_container_on_network(container_name_or_id, network_name)
        except Exception as e:
            logger.error(f"Failed to ensure container on tsushin network: {e}")
            # Don't raise - container might still work via localhost fallback

    def _get_container_ip(self, container_name_or_id: str) -> str:
        """Get container IP address on tsushin network"""
        network_name = self._resolve_network_name()
        try:
            return self.runtime.get_container_network_ip(container_name_or_id, network_name)
        except Exception as e:
            logger.error(f"Failed to get container IP: {e}")
            return ''

    def _sanitize_container_ref(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        value = value.strip()
        return value or None

    def _get_dns_servers(self) -> Optional[list[str]]:
        raw_value = os.getenv(self.DNS_FALLBACK_ENV, "").strip()
        if not raw_value:
            return None
        servers = [item.strip() for item in raw_value.split(",") if item.strip()]
        return servers or None

    def _canonical_session_data_path(self, instance: WhatsAppMCPInstance) -> str:
        """Return the container-visible session directory path for an instance."""
        return str(Path("/app/data") / "mcp" / instance.tenant_id / instance.container_name / "store")

    def _canonical_messages_db_path(self, instance: WhatsAppMCPInstance) -> str:
        return str(Path(self._canonical_session_data_path(instance)) / "messages.db")

    def _extract_host_port(self, container_attrs: Dict[str, Any]) -> Optional[int]:
        try:
            port_info = (
                container_attrs.get("NetworkSettings", {})
                .get("Ports", {})
                .get("8080/tcp")
            )
            if not port_info:
                return None
            host_port = port_info[0].get("HostPort")
            return int(host_port) if host_port else None
        except (TypeError, ValueError, IndexError, AttributeError):
            return None

    def _resolve_container(self, instance: WhatsAppMCPInstance, db: Optional[Session] = None) -> Tuple[Optional[Any], Optional[str]]:
        """
        Resolve a container by ID first, then by name.

        Returns:
            (container_object, preferred_reference)
        """
        refs = []
        container_id = self._sanitize_container_ref(instance.container_id)
        if instance.container_id != container_id:
            instance.container_id = container_id
            if db is not None:
                db.flush()
        if container_id:
            refs.append(container_id)
        container_name = self._sanitize_container_ref(instance.container_name)
        if container_name and container_name not in refs:
            refs.append(container_name)

        for ref in refs:
            try:
                container = self.runtime.get_container(ref)
                container_id = container.id if hasattr(container, "id") else str(container)
                if instance.container_id != container_id:
                    instance.container_id = container_id
                    if db is not None:
                        db.flush()
                # Prefer container name for later lifecycle calls; it survives ID churn.
                return container, instance.container_name or container_id
            except ContainerNotFoundError:
                continue

        return None, None

    def reconcile_instance(self, instance: WhatsAppMCPInstance, db: Optional[Session] = None) -> Dict[str, Any]:
        """
        Repair stale instance metadata from deterministic conventions and container attrs.

        This keeps health checks, QR flows, and watcher startup aligned with runtime truth.
        """
        changes: Dict[str, Any] = {}

        expected_session_path = self._canonical_session_data_path(instance)
        expected_messages_db_path = self._canonical_messages_db_path(instance)
        expected_api_url = f"http://{instance.container_name}:8080/api"

        normalized_container_id = self._sanitize_container_ref(instance.container_id)
        if instance.container_id != normalized_container_id:
            instance.container_id = normalized_container_id
            changes["container_id"] = normalized_container_id

        if instance.session_data_path != expected_session_path:
            instance.session_data_path = expected_session_path
            changes["session_data_path"] = expected_session_path

        if instance.messages_db_path != expected_messages_db_path:
            instance.messages_db_path = expected_messages_db_path
            changes["messages_db_path"] = expected_messages_db_path

        if instance.mcp_api_url != expected_api_url:
            instance.mcp_api_url = expected_api_url
            changes["mcp_api_url"] = expected_api_url

        container, container_ref = self._resolve_container(instance, db)
        if container_ref:
            changes["container_ref"] = container_ref

        if container is not None:
            container_id = container.id if hasattr(container, "id") else str(container)
            if instance.container_id != container_id:
                instance.container_id = container_id
                changes["container_id"] = container_id

            try:
                attrs = self.runtime.get_container_attrs(container_ref)
                host_port = self._extract_host_port(attrs)
                if host_port and instance.mcp_port != host_port:
                    instance.mcp_port = host_port
                    changes["mcp_port"] = host_port
            except Exception as e:
                logger.debug(f"Could not inspect attrs for {instance.container_name}: {e}")

        if db is not None and changes:
            db.commit()
            db.refresh(instance)
            logger.info(f"Reconciled MCP instance {instance.id}: {sorted(changes.keys())}")

        return changes

    def start_instance(self, instance_id: int, db: Session):
        """
        Start existing container, recreating if necessary

        Args:
            instance_id: MCP instance ID
            db: Database session

        Raises:
            RuntimeError: If container start fails
        """
        instance = db.query(WhatsAppMCPInstance).get(instance_id)

        if not instance:
            raise ValueError(f"MCP instance {instance_id} not found")

        logger.info(f"Starting MCP instance {instance_id} (container {instance.container_name})")
        self.reconcile_instance(instance, db)

        container_found = False

        # Try to resolve the existing container first
        container, container_ref = self._resolve_container(instance, db)
        if container is not None:
            container_found = True
        else:
            logger.warning(f"Container {instance.container_name} not found, will recreate...")

        # If container exists, just start it
        if container_found:
            try:
                self.runtime.start_container(container_ref or instance.container_name)

                # Ensure container is connected to tsushin network for backend communication
                self._ensure_container_on_tsushin_network(container_ref or instance.container_name)

                instance.status = "starting"
                instance.last_started_at = datetime.utcnow()
                db.commit()
                logger.info(f"Container {instance.container_name} started")
                return
            except ContainerRuntimeError as e:
                logger.error(f"Failed to start existing container: {e}")
                # Container might be corrupted, try to recreate
                try:
                    self.runtime.remove_container(container_ref, force=True)
                except (ContainerNotFoundError, ContainerRuntimeError):
                    pass
                container_found = False

        # Recreate container if it doesn't exist
        if not container_found:
            logger.info(f"Recreating container for instance {instance_id}")
            try:
                # session_data_path already points at the store directory mounted as /app/store
                session_dir = instance.session_data_path

                # Create container (pass api_secret for Phase Security-1)
                new_container = self._start_container(
                    instance.container_name,
                    instance.mcp_port,
                    session_dir,
                    instance.phone_number,
                    instance.api_secret
                )

                # Update database with new container ID
                new_container_id = new_container.id if hasattr(new_container, 'id') else str(new_container)
                instance.container_id = new_container_id
                instance.status = "starting"
                instance.last_started_at = datetime.utcnow()
                db.commit()

                logger.info(f"Recreated container {instance.container_name} with ID {new_container_id}")
                return

            except Exception as e:
                logger.error(f"Failed to recreate container: {e}", exc_info=True)
                instance.status = "error"
                instance.health_status = "unavailable"
                db.commit()
                raise RuntimeError(f"Failed to recreate container: {e}")

    def stop_instance(self, instance_id: int, db: Session, timeout: int = 30):
        """
        Stop container gracefully

        Args:
            instance_id: MCP instance ID
            db: Database session
            timeout: Graceful shutdown timeout (seconds)

        Raises:
            RuntimeError: If container stop fails
        """
        instance = db.query(WhatsAppMCPInstance).get(instance_id)

        if not instance:
            raise ValueError(f"MCP instance {instance_id} not found")

        logger.info(f"Stopping MCP instance {instance_id} (container {instance.container_name})")
        self.reconcile_instance(instance, db)
        _, container_ref = self._resolve_container(instance, db)

        try:
            self.runtime.stop_container(container_ref or instance.container_name, timeout=timeout)

            instance.status = "stopped"
            instance.last_stopped_at = datetime.utcnow()
            db.commit()

            logger.info(f"Container {instance.container_name} stopped")

        except ContainerNotFoundError:
            logger.warning(f"Container {instance.container_id} not found (already removed?)")
            instance.status = "stopped"
            instance.health_status = "unavailable"
            db.commit()

        except ContainerRuntimeError as e:
            logger.error(f"Failed to stop container: {e}")
            raise RuntimeError(f"Failed to stop container: {e}")

    def restart_instance(self, instance_id: int, db: Session):
        """
        Restart container

        Args:
            instance_id: MCP instance ID
            db: Database session

        Raises:
            RuntimeError: If container restart fails
        """
        logger.info(f"Restarting MCP instance {instance_id}")

        try:
            # Stop then start
            self.stop_instance(instance_id, db)
            time.sleep(2)  # Brief pause
            self.start_instance(instance_id, db)

        except Exception as e:
            logger.error(f"Failed to restart instance: {e}")
            raise

    def delete_instance(self, instance_id: int, db: Session, remove_data: bool = False):
        """
        Delete container and optionally remove session data

        Args:
            instance_id: MCP instance ID
            db: Database session
            remove_data: If True, delete session data directory

        Raises:
            RuntimeError: If deletion fails
        """
        instance = db.query(WhatsAppMCPInstance).get(instance_id)

        if not instance:
            raise ValueError(f"MCP instance {instance_id} not found")

        logger.info(f"Deleting MCP instance {instance_id} (container {instance.container_name})")
        self.reconcile_instance(instance, db)
        _, container_ref = self._resolve_container(instance, db)

        # 1. Stop and remove container
        try:
            self.runtime.stop_container(container_ref or instance.container_name, timeout=10)
            self.runtime.remove_container(container_ref or instance.container_name)
            logger.info(f"Container {instance.container_name} removed")

        except ContainerNotFoundError:
            logger.warning(f"Container {instance.container_id} not found (already removed?)")

        except ContainerRuntimeError as e:
            logger.error(f"Failed to remove container: {e}")
            # Continue with database cleanup even if container removal fails

        # 2. Optionally remove session data
        if remove_data and instance.session_data_path:
            try:
                import shutil
                if os.path.exists(instance.session_data_path):
                    shutil.rmtree(instance.session_data_path)
                    logger.info(f"Session data removed: {instance.session_data_path}")
            except Exception as e:
                logger.error(f"Failed to remove session data: {e}")

        # 3. Clear foreign key references from agents linked to this instance
        linked_agents = db.query(Agent).filter(Agent.whatsapp_integration_id == instance_id).all()
        if linked_agents:
            for agent in linked_agents:
                logger.info(f"Clearing whatsapp_integration_id from agent id={agent.id}")
                agent.whatsapp_integration_id = None
            db.flush()

        # 4. Remove from database
        db.delete(instance)
        db.commit()
        logger.info(f"MCP instance {instance_id} deleted from database")

    def get_qr_code(self, instance: WhatsAppMCPInstance, db: Optional[Session] = None) -> Optional[str]:
        """
        Fetch QR code from MCP API with retry logic

        Args:
            instance: MCP instance

        Returns:
            Base64-encoded QR code image or None if unavailable
        """
        from services.mcp_auth_service import get_auth_headers

        max_retries = 2
        self.reconcile_instance(instance, db)
        # Phase Security-1: Include auth headers for MCP API requests
        headers = get_auth_headers(instance.api_secret)

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    f"{instance.mcp_api_url}/qr-code",
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    qr_code = data.get('qr_code')
                    message = data.get('message', '')

                    if qr_code:
                        logger.debug(f"QR code fetched for instance {instance.id}")
                        return qr_code
                    elif 'authenticated' in message.lower():
                        logger.info(f"Instance {instance.id} is already authenticated, no QR needed")
                        return None
                    else:
                        logger.debug(f"QR code not yet available for instance {instance.id}: {message}")
                        return None
                else:
                    logger.warning(f"QR code not available: HTTP {response.status_code}")
                    return None

            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    logger.debug(f"QR code fetch timeout (attempt {attempt + 1}), retrying...")
                    time.sleep(1)
                else:
                    logger.warning(f"Failed to fetch QR code for instance {instance.id}: timeout after {max_retries} attempts")
                    return None

            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    logger.debug(f"QR code fetch failed (attempt {attempt + 1}): {e}, retrying...")
                    time.sleep(1)
                else:
                    logger.error(f"Failed to fetch QR code for instance {instance.id}: {e}")
                    return None

        return None

    def logout_instance(self, instance_id: int, db: Session, backup: bool = True) -> Dict[str, any]:
        """
        Reset WhatsApp authentication by deleting session file

        This forces the container to regenerate a QR code for fresh authentication.
        Messages are preserved - only the authentication session is deleted.

        Operations:
        1. Fetch instance from DB and validate
        2. Call WhatsApp logout API to unpair device (if container is running)
        3. Stop container if running
        4. Get session file path
        5. Backup whatsapp.db to whatsapp.db.backup.{timestamp} (if backup=True)
        6. Delete whatsapp.db (preserve messages.db)
        7. Start container
        8. Poll /api/qr-code every 2s for max 30s until QR ready
        9. Update instance status in DB and return result with QR code readiness status

        Args:
            instance_id: MCP instance ID
            db: Database session
            backup: Create backup before deletion (recommended)

        Returns:
            Dict with:
                - success (bool): Operation succeeded
                - message (str): Human-readable result
                - qr_code_ready (bool): QR code available
                - backup_path (Optional[str]): Backup file path if created

        Raises:
            ValueError: Instance not found
            RuntimeError: Operation failed (session file locked, container error, etc.)
        """
        # 1. Fetch instance
        instance = db.query(WhatsAppMCPInstance).get(instance_id)
        if not instance:
            raise ValueError(f"MCP instance {instance_id} not found")

        logger.info(f"Logging out MCP instance {instance_id} (container {instance.container_name})")
        self.reconcile_instance(instance, db)

        backup_path = None

        try:
            # Helper to get container identifier (tries ID then name)
            def find_container_ref() -> Optional[str]:
                _, resolved_ref = self._resolve_container(instance, db)
                return resolved_ref

            # 2. Call WhatsApp logout API (if container is running)
            container_ref = find_container_ref()
            if container_ref:
                container_status = self.runtime.get_container_status(container_ref)
                if container_status == 'running':
                    logger.info("Calling WhatsApp logout API to unpair device")
                    try:
                        from services.mcp_auth_service import get_auth_headers
                        headers = get_auth_headers(instance.api_secret)
                        logout_response = requests.post(
                            f"{instance.mcp_api_url}/logout",
                            headers=headers,
                            timeout=10
                        )
                        if logout_response.status_code == 200:
                            logger.info("WhatsApp logout API call successful")
                        else:
                            logger.warning(f"WhatsApp logout API returned {logout_response.status_code}: {logout_response.text}")
                    except requests.exceptions.RequestException as e:
                        logger.warning(f"Failed to call WhatsApp logout API (continuing anyway): {e}")
            else:
                logger.info("Container not found, skipping logout API call")

            # 3. Stop container
            logger.info(f"Stopping container {instance.container_name}")
            container_ref = find_container_ref()  # Refresh reference
            if container_ref:
                container_status = self.runtime.get_container_status(container_ref)
                if container_status == 'running':
                    self.runtime.stop_container(container_ref, timeout=10)
                    logger.info("Container stopped")
            else:
                logger.warning(f"Container {instance.container_name} not found, continuing...")

            # 4. Get session file path
            session_path = Path(instance.session_data_path)
            session_file = session_path / "whatsapp.db"

            if not session_file.exists():
                logger.info("Session file does not exist, treating as already logged out")
                # Start container anyway to generate QR
            else:
                # 5. Backup session file
                if backup:
                    backup_path = self._backup_session_file(session_file)
                    logger.info(f"Session backed up to: {backup_path}")

                # 6. Delete session file (preserve messages.db)
                self._delete_session_file(session_file)
                logger.info("Session file deleted")

            # 7. Start container
            logger.info("Starting container to regenerate QR code")
            container_ref = find_container_ref()
            try:
                if container_ref:
                    self.runtime.start_container(container_ref)
                    logger.info("Container started")
                else:
                    logger.info("Container missing during logout reset, recreating it")
                    self.start_instance(instance_id, db)

                instance.status = "starting"
                instance.last_started_at = datetime.utcnow()
                db.commit()

            except ContainerRuntimeError as e:
                # Try to restore backup if start fails
                if backup_path and Path(backup_path).exists():
                    logger.error(f"Container failed to start, attempting to restore backup: {e}")
                    import shutil
                    shutil.copy2(backup_path, session_file)
                    logger.info("Backup restored")
                raise RuntimeError(f"Failed to start container: {e}")

            # 8. Wait for QR code availability
            qr_code_ready = self._wait_for_qr_ready(instance, timeout=30)

            # 9. Return success
            return {
                "success": True,
                "message": "Authentication reset successfully. QR code is ready for scanning." if qr_code_ready else "Authentication reset. QR code will be available shortly.",
                "qr_code_ready": qr_code_ready,
                "backup_path": backup_path
            }

        except Exception as e:
            logger.error(f"Logout failed: {e}")
            instance.status = "error"
            db.commit()
            raise RuntimeError(f"Logout failed: {str(e)}")

    def _backup_session_file(self, session_file: Path) -> str:
        """
        Create timestamped backup of session file

        Args:
            session_file: Path to whatsapp.db

        Returns:
            Path to backup file

        Raises:
            RuntimeError: If backup fails
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = session_file.parent / f"whatsapp.db.backup.{timestamp}"

        try:
            import shutil
            shutil.copy2(session_file, backup_path)
            logger.info(f"Session backed up: {backup_path}")
            return str(backup_path)

        except Exception as e:
            logger.error(f"Failed to backup session file: {e}")
            raise RuntimeError(f"Backup failed: {str(e)}")

    def _delete_session_file(self, session_file: Path) -> None:
        """
        Safely delete session file with retry logic

        Args:
            session_file: Path to whatsapp.db

        Raises:
            RuntimeError: If deletion fails after retries
        """
        max_retries = 3
        retry_delay = 2  # seconds

        for attempt in range(1, max_retries + 1):
            try:
                if session_file.exists():
                    session_file.unlink()
                    logger.info(f"Session file deleted: {session_file}")
                return

            except OSError as e:
                if attempt < max_retries:
                    logger.warning(f"Failed to delete session (attempt {attempt}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"Failed to delete session after {max_retries} attempts: {e}")
                    raise RuntimeError(f"Could not delete session file: {str(e)}")

    def _wait_for_qr_ready(self, instance: WhatsAppMCPInstance, timeout: int = 30) -> bool:
        """
        Poll QR code endpoint until available or timeout

        Args:
            instance: MCP instance
            timeout: Maximum wait time in seconds

        Returns:
            True if QR code became available, False if timeout
        """
        from services.mcp_auth_service import get_auth_headers

        poll_interval = 2  # seconds
        elapsed = 0
        # Phase Security-1: Include auth headers for MCP API requests
        headers = get_auth_headers(instance.api_secret)

        logger.info(f"Waiting for QR code (timeout: {timeout}s)")

        while elapsed < timeout:
            try:
                response = requests.get(
                    f"{instance.mcp_api_url}/qr-code",
                    headers=headers,
                    timeout=5
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('qr_code'):
                        logger.info(f"QR code available after {elapsed}s")
                        return True

            except requests.RequestException as e:
                logger.debug(f"QR code check failed (elapsed {elapsed}s): {e}")

            time.sleep(poll_interval)
            elapsed += poll_interval

        logger.warning(f"QR code not available after {timeout}s timeout")
        return False

    def _extract_container_env(self, container: Any) -> Dict[str, str]:
        attrs = getattr(container, "attrs", {}) or {}
        env_items = attrs.get("Config", {}).get("Env", []) or []
        env_map: Dict[str, str] = {}
        for item in env_items:
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            env_map[key] = value
        return env_map

    def _get_container_env(self, container_name_or_id: str) -> Dict[str, str]:
        try:
            container = self.runtime.get_container(container_name_or_id)
        except ContainerNotFoundError:
            return {}
        return self._extract_container_env(container)

    def _get_tester_container(self) -> Optional[Any]:
        """BUG-380: Try compose-managed tester first, then fall back to runtime tester instances."""
        # Try compose-managed tester
        try:
            return self.runtime.get_container(self.TESTER_CONTAINER_NAME)
        except ContainerNotFoundError:
            pass

        # Fall back to runtime-created tester instances (type=tester)
        try:
            from models import WhatsAppMCPInstance
            from db import get_db
            db = next(get_db())
            try:
                tester_instance = db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.instance_type == "tester",
                    WhatsAppMCPInstance.is_active == True
                ).order_by(WhatsAppMCPInstance.id.desc()).first()
                if tester_instance and tester_instance.container_name:
                    try:
                        container = self.runtime.get_container(tester_instance.container_name)
                        # Update class-level references to use the runtime tester
                        self._runtime_tester_name = tester_instance.container_name
                        self._runtime_tester_api_url = f"http://{tester_instance.container_name}:8080/api"
                        return container
                    except ContainerNotFoundError:
                        pass
            finally:
                db.close()
        except Exception as e:
            logger.debug(f"Runtime tester lookup failed: {e}")

        return None

    def _get_tester_headers(self) -> Dict[str, str]:
        tester_container = self._get_tester_container()
        if tester_container is None:
            return {}

        tester_secret = self._extract_container_env(tester_container).get("MCP_API_SECRET")
        if not tester_secret:
            return {}

        from services.mcp_auth_service import get_auth_headers
        return get_auth_headers(tester_secret)

    def get_tester_status(self) -> Dict[str, Any]:
        # BUG-380: Resolve tester name/URL from runtime instance if available
        self._runtime_tester_name = None
        self._runtime_tester_api_url = None
        tester_name = self.TESTER_CONTAINER_NAME
        tester_api_url = self.TESTER_API_URL
        tester_status = {
            "name": tester_name,
            "api_url": tester_api_url,
            "status": "unavailable",
            "container_state": "not_found",
            "api_reachable": False,
            "connected": False,
            "authenticated": False,
            "needs_reauth": False,
            "is_reconnecting": False,
            "reconnect_attempts": 0,
            "session_age_sec": 0,
            "last_activity_sec": 0,
            "container_id": None,
            "image": None,
            "error": None,
            "qr_available": False,
        }

        tester_container = self._get_tester_container()
        # BUG-380: Update status dict with resolved runtime tester info
        if self._runtime_tester_name:
            tester_name = self._runtime_tester_name
            tester_api_url = self._runtime_tester_api_url or tester_api_url
            tester_status["name"] = tester_name
            tester_status["api_url"] = tester_api_url
            tester_status["source"] = "runtime"
        else:
            tester_status["source"] = "compose"

        if tester_container is None:
            tester_status["error"] = "Tester container not found"
            return tester_status

        try:
            self._ensure_container_on_tsushin_network(tester_name)
        except Exception:
            pass

        try:
            attrs = self.runtime.get_container_attrs(tester_name)
            tester_status["container_state"] = attrs.get("status", "unknown")
            tester_status["container_id"] = attrs.get("id")
            image_tags = attrs.get("image_tags") or []
            tester_status["image"] = image_tags[0] if image_tags else None
        except Exception as e:
            tester_status["error"] = str(e)
            return tester_status

        if tester_status["container_state"] != "running":
            tester_status["status"] = "unhealthy"
            return tester_status

        headers = self._get_tester_headers()

        try:
            response = requests.get(f"{tester_api_url}/health", headers=headers, timeout=5)
            if response.status_code != 200:
                tester_status["status"] = "degraded"
                tester_status["error"] = f"Tester health returned HTTP {response.status_code}"
                return tester_status

            payload = response.json()
            tester_status.update({
                "status": payload.get("status", "healthy"),
                "api_reachable": True,
                "connected": payload.get("connected", False),
                "authenticated": payload.get("authenticated", False),
                "needs_reauth": payload.get("needs_reauth", False),
                "is_reconnecting": payload.get("is_reconnecting", False),
                "reconnect_attempts": payload.get("reconnect_attempts", 0),
                "session_age_sec": payload.get("session_age_sec", 0),
                "last_activity_sec": payload.get("last_activity_sec", 0),
            })
        except requests.RequestException as e:
            tester_status["status"] = "degraded"
            tester_status["error"] = str(e)
            return tester_status

        try:
            qr_response = requests.get(f"{self.TESTER_API_URL}/qr-code", headers=headers, timeout=5)
            if qr_response.status_code == 200:
                tester_status["qr_available"] = bool(qr_response.json().get("qr_code"))
        except requests.RequestException:
            pass

        return tester_status

    def get_tester_qr_code(self) -> Optional[str]:
        headers = self._get_tester_headers()
        try:
            response = requests.get(f"{self.TESTER_API_URL}/qr-code", headers=headers, timeout=10)
            if response.status_code != 200:
                return None
            return response.json().get("qr_code")
        except requests.RequestException:
            return None

    def restart_tester(self) -> Dict[str, Any]:
        self.runtime.restart_container(self.TESTER_CONTAINER_NAME, timeout=15)
        return {"success": True, "message": "Tester MCP restarting"}

    def logout_tester(self) -> Dict[str, Any]:
        return self.reset_tester_auth()

    def reset_tester_auth(self) -> Dict[str, Any]:
        headers = self._get_tester_headers()
        logout_error: Optional[str] = None

        try:
            response = requests.post(f"{self.TESTER_API_URL}/logout", headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json()
            logout_error = f"Tester logout failed with HTTP {response.status_code}"
        except requests.RequestException as exc:
            logout_error = str(exc)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        cleanup_cmd = [
            "sh",
            "-lc",
            (
                "if [ -f /app/store/whatsapp.db ]; then "
                f"cp /app/store/whatsapp.db /app/store/whatsapp.db.backup.{timestamp}; "
                "fi; "
                "rm -f /app/store/whatsapp.db /app/store/whatsapp.db-shm /app/store/whatsapp.db-wal"
            ),
        ]

        try:
            result = self.runtime.exec_run(self.TESTER_CONTAINER_NAME, cleanup_cmd, user="root")
            exit_code = getattr(result, "exit_code", 0)
            if exit_code not in (0, None):
                output = getattr(result, "output", b"")
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="ignore")
                raise RuntimeError(output or "unknown tester cleanup error")
            self.runtime.restart_container(self.TESTER_CONTAINER_NAME, timeout=15)
            return {
                "success": True,
                "message": "Tester authentication reset via filesystem cleanup",
                "fallback_error": logout_error,
            }
        except (ContainerNotFoundError, ContainerRuntimeError, RuntimeError) as exc:
            raise RuntimeError(logout_error or str(exc))

    def health_check(self, instance: WhatsAppMCPInstance, db: Optional[Session] = None) -> Dict[str, any]:
        """
        Check container and API health with enhanced session monitoring

        Args:
            instance: MCP instance

        Returns:
            Dict with comprehensive health status including session state
        """
        health_data = {
            'status': 'unknown',
            'container_state': 'unknown',
            'api_reachable': False,
            'error': None,
            'authenticated': False,
            'connected': False,
            'needs_reauth': False,
            'is_reconnecting': False,
            'reconnect_attempts': 0,
            'session_age_sec': 0,
            'last_activity_sec': 0
        }

        container_ref = None

        try:
            self.reconcile_instance(instance, db)

            # 1. Check container status - recover cleanly from missing/stale container_id
            _, container_ref = self._resolve_container(instance, db)
            if not container_ref:
                raise ContainerNotFoundError("Container not found by ID or name")

            # Get container state with detailed info
            container_state = self.runtime.get_container_status(container_ref)
            health_data['container_state'] = container_state

            logger.debug(f"Container {instance.container_name} state: {container_state}")

            # 2. Only check API if container is running
            if container_state != 'running':
                logger.info(f"Container {instance.container_name} is not running (state: {container_state})")
                health_data['status'] = 'unhealthy' if container_state in ['exited', 'dead'] else container_state
                return health_data

            # 2.5. Ensure container is on the correct network (self-healing)
            self._ensure_container_on_tsushin_network(container_ref)

            # 3. Check API health endpoint with retry logic
            api_healthy = False
            max_retries = 2

            for attempt in range(max_retries):
                try:
                    response = requests.get(
                        f"{instance.mcp_api_url}/health",
                        timeout=5
                    )
                    api_healthy = response.status_code == 200
                    health_data['api_reachable'] = api_healthy

                    # Extract enhanced session data from container health response
                    if api_healthy:
                        try:
                            container_health = response.json()
                            health_data['connected'] = container_health.get('connected', False)
                            health_data['authenticated'] = container_health.get('authenticated', False)
                            health_data['needs_reauth'] = container_health.get('needs_reauth', False)
                            health_data['is_reconnecting'] = container_health.get('is_reconnecting', False)
                            health_data['reconnect_attempts'] = container_health.get('reconnect_attempts', 0)
                            health_data['session_age_sec'] = container_health.get('session_age_sec', 0)
                            health_data['last_activity_sec'] = container_health.get('last_activity_sec', 0)

                            logger.debug(
                                f"Health check for instance {instance.id}: "
                                f"authenticated={health_data['authenticated']}, "
                                f"connected={health_data['connected']}"
                            )

                            # Alert if re-authentication is needed
                            if health_data['needs_reauth']:
                                logger.warning(
                                    f"MCP instance {instance.id} ({instance.phone_number}) requires re-authentication. "
                                    f"QR code scan needed."
                                )

                            # Alert if reconnection attempts are high
                            if health_data['reconnect_attempts'] >= 5:
                                logger.warning(
                                    f"MCP instance {instance.id} ({instance.phone_number}) has {health_data['reconnect_attempts']} "
                                    f"reconnection attempts. Session may be unstable."
                                )

                            # Alert if session has been inactive for too long (>5 minutes)
                            if health_data['last_activity_sec'] > 300:
                                logger.warning(
                                    f"MCP instance {instance.id} ({instance.phone_number}) has been inactive for "
                                    f"{health_data['last_activity_sec']//60} minutes."
                                )

                        except Exception as e:
                            logger.error(f"Failed to parse health response: {e}")
                            health_data['connected'] = False
                            health_data['authenticated'] = False
                    else:
                        logger.warning(f"Health API returned non-200 status: {response.status_code}")
                        health_data['connected'] = False
                        health_data['authenticated'] = False

                    # Success - break retry loop
                    break

                except requests.RequestException as e:
                    if attempt < max_retries - 1:
                        logger.debug(f"Health check attempt {attempt + 1} failed, retrying: {e}")
                        time.sleep(1)  # Brief delay before retry
                    else:
                        logger.warning(f"Health check API request failed for instance {instance.id} after {max_retries} attempts: {e}")
                        health_data['api_reachable'] = False
                        health_data['connected'] = False
                        health_data['authenticated'] = False

            # 4. Determine overall health status
            if container_state == 'running' and health_data['api_reachable']:
                if health_data['authenticated'] and health_data['connected']:
                    health_data['status'] = 'healthy'
                elif health_data['needs_reauth']:
                    health_data['status'] = 'needs_reauth'
                elif health_data['is_reconnecting']:
                    health_data['status'] = 'reconnecting'
                elif health_data['connected'] and not health_data['authenticated']:
                    health_data['status'] = 'authenticating'
                elif not health_data['authenticated'] and not health_data['connected']:
                    # Container API reachable but not connected/authenticated - waiting for QR scan
                    health_data['status'] = 'authenticating'
                else:
                    health_data['status'] = 'degraded'
            elif container_state == 'running':
                health_data['status'] = 'degraded'  # Container running but API not responding
            else:
                health_data['status'] = 'unhealthy'

        except ContainerNotFoundError:
            health_data['status'] = 'unavailable'
            health_data['container_state'] = 'not_found'
            health_data['error'] = 'Container not found. Verify the WhatsApp container is still present or restart the instance.'
            logger.error(f"Container not found for instance {instance.id} (id={instance.container_id}, name={instance.container_name})")

        except ContainerRuntimeError as e:
            health_data['status'] = 'error'
            health_data['error'] = str(e)
            logger.error(f"Runtime error for instance {instance.id}: {e}")

        return health_data

    def reconcile_all_instances(self, db: Session) -> Dict[int, Dict[str, Any]]:
        """Repair stale metadata for every WhatsApp MCP instance row."""
        reconciled: Dict[int, Dict[str, Any]] = {}
        instances = db.query(WhatsAppMCPInstance).all()
        for instance in instances:
            changes = self.reconcile_instance(instance, db=None)
            if changes:
                reconciled[instance.id] = changes
        if reconciled:
            db.commit()
            logger.info(f"Reconciled {len(reconciled)} WhatsApp MCP instance(s) at startup")
        return reconciled
