"""
v0.6.0-patch.5: Kokoro TTS Container Manager — auto-provisioning of Kokoro TTS containers.

Manages Docker container lifecycle for auto-provisioned TTS instances. Mirrors the
pattern used by VectorStoreContainerManager (Qdrant/MongoDB). Vendor=`kokoro` is the
only supported vendor for v0.6.0-patch.5; additional vendors (e.g. speaches/Whisper)
will land in v0.7.0.

Backend runs under uvicorn with --workers 1, so module-level locks/dicts are safe.
"""

import hashlib
import logging
import os
import time
import threading
from datetime import datetime
from typing import Optional, Set, Dict, Any

import requests
from sqlalchemy.orm import Session

from services.container_runtime import (
    get_container_runtime,
    ContainerRuntime,
    ContainerNotFoundError,
    ContainerRuntimeError,
)
from services.docker_network_utils import resolve_tsushin_network_name

logger = logging.getLogger(__name__)


def _kokoro_image() -> str:
    """Resolve image tag at call time so env overrides (KOKORO_IMAGE_TAG) take effect."""
    return f"ghcr.io/remsky/kokoro-fastapi-cpu:{os.getenv('KOKORO_IMAGE_TAG', 'v0.2.4')}"


VENDOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "kokoro": {
        # image is resolved lazily via _kokoro_image() so env changes are respected
        "internal_port": 8880,
        "volume_bind": "/app/models",
        "default_mem_limit": "1.5g",
        "healthcheck_path": "/health",
    },
}

PORT_RANGE_START = 6600
PORT_RANGE_END = 6699
HEALTH_CHECK_TIMEOUT = 90
HEALTH_CHECK_INTERVAL = 5


def _get_container_prefix() -> str:
    """Use TSN_STACK_NAME for runtime container isolation."""
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-tts-"


_provision_lock = threading.Lock()


class KokoroContainerManager:
    """Manages auto-provisioned Docker containers for Kokoro TTS instances."""

    def __init__(self):
        self.runtime: ContainerRuntime = get_container_runtime()

    # --- Port allocation ---

    def _get_used_ports(self, db: Session) -> Set[int]:
        from models import TTSInstance
        rows = db.query(TTSInstance.container_port).filter(
            TTSInstance.container_port.isnot(None),
            TTSInstance.is_active == True,
        ).all()
        return {r[0] for r in rows}

    def _allocate_port(self, db: Session) -> int:
        import socket
        used = self._get_used_ports(db)
        for port in range(PORT_RANGE_START, PORT_RANGE_END):
            if port in used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")

    # --- Container lifecycle ---

    def provision(self, instance, db: Session) -> None:
        """
        Create and start a Docker container for the given TTSInstance.
        Updates the instance in-place with container metadata.
        """
        vendor = instance.vendor
        if vendor not in VENDOR_CONFIGS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {vendor}")

        config = VENDOR_CONFIGS[vendor]
        image = _kokoro_image()
        tenant_id = instance.tenant_id

        # Short, DNS-safe hash of the tenant ID — full tenant IDs can be long
        # (e.g. "tenant_20251202232822_1766790203") and combining them with the
        # prefix and instance id can easily exceed the 63-character DNS label limit.
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]

        container_name: Optional[str] = None

        # Lock to prevent port-allocation race between concurrent provisions
        with _provision_lock:
            port = self._allocate_port(db)

            # Format: {stack}-tts-kokoro-{hash8}-{instance_id}
            container_name = f"{_get_container_prefix()}kokoro-{tenant_hash}-{instance.id}"
            # Defensive truncation to keep name DNS-safe (<=63 chars)
            if len(container_name) > 63:
                container_name = container_name[:63].rstrip("-")

            # Per peer review A-H4: volume name must include the stack prefix
            # so we don't collide across multi-stack installs on the same host.
            volume_name = f"{_get_container_prefix()}kokoro-{tenant_hash}-{instance.id}"

        # Resolve network
        network_name = resolve_tsushin_network_name(self.runtime.raw_client)

        mem_limit = instance.mem_limit or config["default_mem_limit"]
        cpu_quota = instance.cpu_quota or 100000  # 1 CPU default

        logger.info(f"Provisioning kokoro container: {container_name} on port {port}")

        instance.container_status = "creating"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = image
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        db.commit()

        # Short DNS alias for inter-container resolution
        dns_alias = f"tts-kokoro-{tenant_hash}-{instance.id}"

        try:
            container = self.runtime.create_container(
                image=image,
                name=container_name,
                volumes={volume_name: {"bind": config["volume_bind"], "mode": "rw"}},
                ports={f'{config["internal_port"]}/tcp': ("127.0.0.1", port)},
                network=network_name,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                labels={
                    "tsushin.service": "tts",
                    "tsushin.vendor": vendor,
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance.id),
                },
                detach=True,
            )

            instance.container_id = container.id if hasattr(container, 'id') else str(container)

            # Add a short DNS alias so other containers on tsushin-network can
            # resolve the service with a guaranteed-short hostname.
            try:
                raw = self.runtime.raw_client
                if raw and hasattr(raw, 'networks'):
                    net = raw.networks.get(network_name)
                    net.disconnect(container_name)
                    net.connect(container_name, aliases=[dns_alias])
            except Exception as alias_err:
                logger.warning(f"Could not set DNS alias '{dns_alias}': {alias_err}")

            # Build base_url using the short DNS alias (safe for DNS labels)
            instance.base_url = f"http://{dns_alias}:{config['internal_port']}"

            # Wait for service to become healthy
            healthy = self._wait_for_health(instance)
            instance.container_status = "running" if healthy else "error"
            instance.health_status = "healthy" if healthy else "unavailable"
            instance.health_status_reason = (
                "Auto-provisioned and healthy"
                if healthy
                else "Container started but health check failed"
            )
            instance.last_health_check = datetime.utcnow()

            db.commit()
            logger.info(f"Provisioned kokoro container: {container_name} (healthy={healthy})")

        except Exception as e:
            # Peer review A-B3: clean up orphan container before nulling DB fields
            if container_name:
                try:
                    self.runtime.remove_container(container_name, force=True)
                except Exception:
                    # Swallow cleanup errors — best-effort only
                    pass

            instance.container_status = "error"
            instance.container_name = None
            instance.container_id = None
            instance.container_port = None
            instance.health_status = "unavailable"
            instance.health_status_reason = str(e)[:500]
            db.commit()
            logger.error(f"Failed to provision kokoro container: {e}", exc_info=True)
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

    def deprovision(
        self,
        instance_id: int,
        tenant_id: str,
        db: Session,
        remove_volume: bool = False,
    ) -> None:
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

    def get_logs(
        self,
        instance_id: int,
        tenant_id: str,
        db: Session,
        tail: int = 100,
    ) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return ""
        return self.runtime.get_container_logs(instance.container_name, tail=tail)

    # --- Health checking ---

    def _wait_for_health(self, instance) -> bool:
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._check_health(instance):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _check_health(self, instance) -> bool:
        try:
            if not instance.base_url:
                return False
            resp = requests.get(f"{instance.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # --- Helpers ---

    def _get_instance(self, instance_id: int, tenant_id: str, db: Session):
        from models import TTSInstance
        instance = db.query(TTSInstance).filter(
            TTSInstance.id == instance_id,
            TTSInstance.tenant_id == tenant_id,
            TTSInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"TTS instance {instance_id} not found")
        if not instance.is_auto_provisioned:
            raise ValueError(f"Instance {instance_id} is not auto-provisioned")
        return instance


# ============================================================================
# Startup reconcile — best-effort re-sync of "creating" rows on app boot.
# ============================================================================

def startup_reconcile(db: Session) -> None:
    """Reconcile TTSInstance rows in 'creating' state with actual container state.

    If a row is stuck in 'creating' (e.g. the backend crashed mid-provision), this
    function checks whether the underlying container actually exists and is running:
    - If the container exists and is running, mark the row as 'running'.
    - Otherwise, mark the row as 'error' with a reconcile reason.
    """
    from models import TTSInstance

    try:
        runtime = get_container_runtime()
    except Exception as e:
        logger.warning(f"Kokoro startup_reconcile: runtime unavailable: {e}")
        return

    rows = db.query(TTSInstance).filter(
        TTSInstance.container_status == "creating",
        TTSInstance.is_active == True,
    ).all()

    if not rows:
        return

    logger.info(f"Kokoro startup_reconcile: evaluating {len(rows)} row(s) in 'creating' state")

    for instance in rows:
        container_name = instance.container_name
        if not container_name:
            instance.container_status = "error"
            instance.health_status = "unavailable"
            instance.health_status_reason = (
                "Reconciled at startup — container missing or failed"
            )
            continue

        try:
            runtime.get_container(container_name)
            status = runtime.get_container_status(container_name)
            if status == "running":
                instance.container_status = "running"
                instance.health_status = "healthy"
                instance.health_status_reason = "Reconciled at startup — container running"
            else:
                instance.container_status = "error"
                instance.health_status = "unavailable"
                instance.health_status_reason = (
                    f"Reconciled at startup — container status={status}"
                )
        except (ContainerNotFoundError, ContainerRuntimeError, Exception):
            instance.container_status = "error"
            instance.health_status = "unavailable"
            instance.health_status_reason = (
                "Reconciled at startup — container missing or failed"
            )

    try:
        db.commit()
    except Exception as e:
        logger.warning(f"Kokoro startup_reconcile commit failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
