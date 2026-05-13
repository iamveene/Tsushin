"""
v0.6.0: Vector Store Container Manager — auto-provisioning of Qdrant/MongoDB containers.

Manages Docker container lifecycle for auto-provisioned vector store instances.
Follows the same patterns as MCPContainerManager and ToolboxContainerService.
"""

import hashlib
import logging
import os
import re
import time
import threading
from datetime import datetime
from typing import Optional, Set, Dict, Any

import requests
from sqlalchemy.orm import Session

from services.container_runtime import (
    PORT_RANGES,
    get_container_runtime,
    iter_port_range,
    ContainerRuntime,
    ContainerNotFoundError,
    ContainerRuntimeError,
)
from services.docker_network_utils import resolve_tsushin_network_name

logger = logging.getLogger(__name__)


VENDOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "qdrant": {
        "image": "qdrant/qdrant:v1.13.2",
        "internal_port": 6333,
        "volume_bind": "/qdrant/storage",
        "default_mem_limit": "1g",
    },
    "mongodb": {
        "image": "mongo:7.0",
        "internal_port": 27017,
        "volume_bind": "/data/db",
        "default_mem_limit": "1g",
    },
}

PORT_RANGE_START, PORT_RANGE_END = PORT_RANGES["vector_store"]
HEALTH_CHECK_TIMEOUT = 90


def _get_container_prefix() -> str:
    """BUG-448: Use TSN_STACK_NAME for runtime container isolation."""
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-vs-"
HEALTH_CHECK_INTERVAL = 5


_provision_lock = threading.Lock()


class VectorStoreContainerManager:
    """Manages auto-provisioned Docker containers for vector store instances."""

    def __init__(self):
        self.runtime: ContainerRuntime = get_container_runtime()

    # --- Port allocation ---

    def _get_used_ports(self, db: Session) -> Set[int]:
        from models import VectorStoreInstance
        rows = db.query(VectorStoreInstance.container_port).filter(
            VectorStoreInstance.container_port.isnot(None),
            VectorStoreInstance.is_active == True,
        ).all()
        return {r[0] for r in rows}

    def _docker_published_ports(self) -> Set[int]:
        """BUG-682: enumerate every host port already published by ANY running
        Docker container on this host, so side-by-side Tsushin stacks don't
        each grab port 6300 from their own DB and then race on docker run.

        Returns an empty set on any error — falls back to the socket-bind
        check in `_allocate_port` rather than failing provisioning.
        """
        published: Set[int] = set()
        try:
            client = self.runtime.raw_client
            for container in client.containers.list(all=False):
                try:
                    ports = (container.attrs or {}).get("NetworkSettings", {}).get("Ports") or {}
                    for _container_port, host_bindings in ports.items():
                        if not host_bindings:
                            continue
                        for binding in host_bindings:
                            hp = binding.get("HostPort")
                            if not hp:
                                continue
                            try:
                                published.add(int(hp))
                            except (TypeError, ValueError):
                                continue
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"docker-published-ports enumeration skipped: {e}")
        return published

    def _allocate_port(self, db: Session) -> int:
        import socket
        used = self._get_used_ports(db)
        docker_used = self._docker_published_ports()
        for port in iter_port_range("vector_store"):
            if port in used or port in docker_used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                    s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")

    # --- Container lifecycle ---

    def provision(self, instance, db: Session) -> None:
        """
        Create and start a Docker container for the given VectorStoreInstance.
        Updates the instance in-place with container metadata.
        """
        vendor = instance.vendor
        if vendor not in VENDOR_CONFIGS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {vendor}")

        config = VENDOR_CONFIGS[vendor]
        tenant_id = instance.tenant_id

        # Build a short, DNS-safe hash of the tenant ID to avoid exceeding
        # the 63-character DNS label limit.  Full tenant IDs can be very long
        # (e.g. "tenant_20251202232822_1766790203") and combining them with
        # the prefix, vendor, and timestamp easily overflows.
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]

        # Lock to prevent port allocation race condition
        with _provision_lock:
            port = self._allocate_port(db)

            # Generate names — keep container_name under 63 chars for DNS
            # Format: {stack}-vs-{vendor}-{hash8}-{instance_id}
            container_name = f"{_get_container_prefix()}{vendor}-{tenant_hash}-{instance.id}"
            # Defensive truncation: ensure <= 63 characters
            if len(container_name) > 63:
                container_name = container_name[:63].rstrip("-")

            volume_name = f"{_get_container_prefix()}{vendor}-{tenant_hash}-{instance.id}"

        # Resolve network
        network_name = resolve_tsushin_network_name(self.runtime.raw_client)

        mem_limit = instance.mem_limit or config["default_mem_limit"]
        cpu_quota = instance.cpu_quota or 100000  # 1 CPU default

        logger.info(f"Provisioning {vendor} container: {container_name} on port {port}")

        instance.container_status = "creating"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = config["image"]
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        db.commit()

        # Build a short network alias for DNS resolution (guaranteed <= 63 chars)
        dns_alias = f"vs-{vendor}-{tenant_hash}-{instance.id}"

        try:
            container = self.runtime.create_container(
                image=config["image"],
                name=container_name,
                volumes={volume_name: {"bind": config["volume_bind"], "mode": "rw"}},
                ports={f'{config["internal_port"]}/tcp': ("127.0.0.1", port)},
                network=network_name,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                labels={
                    "tsushin.service": "vector-store",
                    "tsushin.vendor": vendor,
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance.id),
                },
                detach=True,
            )

            instance.container_id = container.id if hasattr(container, 'id') else str(container)

            # Add a short DNS alias to the container on the network.
            # The container_name is already the DNS name, but since it is
            # kept short (<=63 chars) this alias serves as an explicit
            # guarantee for DNS-label compliance.
            try:
                raw = self.runtime.raw_client
                if raw and hasattr(raw, 'networks'):
                    net = raw.networks.get(network_name)
                    net.disconnect(container_name)
                    net.connect(container_name, aliases=[dns_alias])
            except Exception as alias_err:
                logger.warning(f"Could not set DNS alias '{dns_alias}': {alias_err}")

            # Build base_url using the short DNS alias (safe for DNS labels)
            if vendor == "qdrant":
                instance.base_url = f"http://{dns_alias}:{config['internal_port']}"
            elif vendor == "mongodb":
                instance.base_url = f"mongodb://{dns_alias}:{config['internal_port']}"
                # Set local mode for MongoDB (no Atlas Vector Search)
                extra = instance.extra_config or {}
                extra["use_native_search"] = False
                if not extra.get("database_name"):
                    extra["database_name"] = "tsushin"
                if not extra.get("collection_name"):
                    extra["collection_name"] = "vectors"
                instance.extra_config = extra

            # Wait for health
            healthy = self._wait_for_health(instance)
            instance.container_status = "running" if healthy else "error"
            instance.health_status = "healthy" if healthy else "unavailable"
            instance.health_status_reason = "Auto-provisioned and healthy" if healthy else "Container started but health check failed"
            instance.last_health_check = datetime.utcnow()

            db.commit()
            logger.info(f"Provisioned {vendor} container: {container_name} (healthy={healthy})")

        except Exception as e:
            instance.container_status = "error"
            instance.container_name = None
            instance.container_id = None
            instance.container_port = None
            instance.health_status = "unavailable"
            instance.health_status_reason = str(e)[:500]
            db.commit()
            logger.error(f"Failed to provision {vendor} container: {e}", exc_info=True)
            raise

    def start_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self.runtime.start_container(instance.container_name)
        instance.container_status = "running"
        db.commit()
        return "running"

    def stop_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self.runtime.stop_container(instance.container_name)
        instance.container_status = "stopped"
        db.commit()
        return "stopped"

    def restart_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self.runtime.restart_container(instance.container_name)
        instance.container_status = "running"
        db.commit()
        return "running"

    def deprovision(self, instance_id: int, tenant_id: str, db: Session, remove_volume: bool = False) -> None:
        instance = self._get_instance(instance_id, tenant_id, db)

        if instance.container_name:
            try:
                self.runtime.stop_container(instance.container_name, timeout=10)
            except (ContainerNotFoundError, ContainerRuntimeError):
                pass
            try:
                self.runtime.remove_container(instance.container_name, force=True)
            except (ContainerNotFoundError, ContainerRuntimeError):
                pass
            logger.info(f"Removed container: {instance.container_name}")

        if remove_volume and instance.volume_name:
            try:
                self.runtime.remove_volume(instance.volume_name, force=True)
                logger.info(f"Removed volume: {instance.volume_name}")
            except Exception as e:
                logger.warning(f"Failed to remove volume {instance.volume_name}: {e}")

        instance.container_status = "none"
        instance.container_name = None
        instance.container_id = None
        instance.container_port = None
        db.commit()

    def get_status(self, instance_id: int, tenant_id: str, db: Session) -> Dict[str, Any]:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return {"status": "none", "container_name": None}
        try:
            status = self.runtime.get_container_status(instance.container_name)
            if status != instance.container_status:
                instance.container_status = status
                db.commit()
            return {
                "status": status,
                "container_name": instance.container_name,
                "container_port": instance.container_port,
                "image": instance.container_image,
                "volume": instance.volume_name,
            }
        except ContainerNotFoundError:
            instance.container_status = "not_found"
            db.commit()
            return {"status": "not_found", "container_name": instance.container_name}

    def get_logs(self, instance_id: int, tenant_id: str, db: Session, tail: int = 100) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return ""
        return self.runtime.get_container_logs(instance.container_name, tail=tail)

    # --- Health checking ---

    def _wait_for_health(self, instance) -> bool:
        vendor = instance.vendor
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._check_health(instance):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _check_health(self, instance) -> bool:
        try:
            if instance.vendor == "qdrant":
                # Use container DNS name on tsushin-network (backend runs in Docker too)
                config = VENDOR_CONFIGS["qdrant"]
                resp = requests.get(
                    f"http://{instance.container_name}:{config['internal_port']}/healthz",
                    timeout=5,
                )
                return resp.status_code == 200
            elif instance.vendor == "mongodb":
                result = self.runtime.exec_run(
                    instance.container_name,
                    ["mongosh", "--quiet", "--eval", "db.adminCommand('ping').ok"],
                )
                output = result.output if hasattr(result, 'output') else str(result)
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="replace")
                return "1" in output
        except Exception:
            return False
        return False

    # --- Helpers ---

    def _get_instance(self, instance_id: int, tenant_id: str, db: Session):
        from models import VectorStoreInstance
        instance = db.query(VectorStoreInstance).filter(
            VectorStoreInstance.id == instance_id,
            VectorStoreInstance.tenant_id == tenant_id,
            VectorStoreInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Vector store instance {instance_id} not found")
        if not instance.is_auto_provisioned:
            raise ValueError(f"Instance {instance_id} is not auto-provisioned")
        return instance
