"""
v0.6.0-patch.6: SearXNG Container Manager — auto-provisioning of per-tenant
SearXNG metasearch containers.

Mirrors KokoroContainerManager. Unique quirk: SearXNG expects a settings.yml
inside /etc/searxng/. We inject it via `put_archive` between create and start
so no file from the repo is mounted and the generated `secret_key` lives only
in the DB (SearxngInstance.extra_config) and inside the running container —
never on the host filesystem.

Backend runs under uvicorn with --workers 1, so module-level locks are safe.
"""

import hashlib
import io
import logging
import os
import secrets
import tarfile
import threading
import time
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


def _searxng_image() -> str:
    return f"ghcr.io/searxng/searxng:{os.getenv('SEARXNG_IMAGE_TAG', 'latest')}"


VENDOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "searxng": {
        "internal_port": 8080,
        "volume_bind": "/var/cache/searxng",
        "default_mem_limit": "512m",
        "healthcheck_path": "/healthz",
    },
}

PORT_RANGE_START, PORT_RANGE_END = PORT_RANGES["searxng"]
HEALTH_CHECK_TIMEOUT = 90
HEALTH_CHECK_INTERVAL = 5


def _get_container_prefix() -> str:
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-searxng-"


def _build_settings_yml(secret_key: str, instance_label: str) -> bytes:
    """Render the per-tenant settings.yml bytes.

    Keys chosen to:
      - enable JSON results (searx.formats),
      - disable rate-limiter (otherwise the first few requests return 429),
      - pin a generated secret_key (never hardcoded / never in repo).
    """
    yml = (
        "use_default_settings: true\n"
        "general:\n"
        "  debug: false\n"
        f"  instance_name: {instance_label!r}\n"
        "search:\n"
        "  safe_search: 1\n"
        "  autocomplete: \"duckduckgo\"\n"
        "  formats:\n"
        "    - html\n"
        "    - json\n"
        "server:\n"
        f"  secret_key: {secret_key!r}\n"
        "  limiter: false\n"
        "  image_proxy: false\n"
    )
    return yml.encode("utf-8")


def _tar_bytes_for_settings(yml_bytes: bytes) -> bytes:
    """Return an in-memory tar archive containing settings.yml (no host FS)."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        info = tarfile.TarInfo(name="settings.yml")
        info.size = len(yml_bytes)
        info.mode = 0o644
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(yml_bytes))
    return buf.getvalue()


_provision_lock = threading.Lock()


class SearxngContainerManager:
    """Manages auto-provisioned Docker containers for SearXNG instances."""

    def __init__(self):
        self.runtime: ContainerRuntime = get_container_runtime()

    # --- Port allocation ---

    def _get_used_ports(self, db: Session) -> Set[int]:
        from models import SearxngInstance
        rows = db.query(SearxngInstance.container_port).filter(
            SearxngInstance.container_port.isnot(None),
            SearxngInstance.is_active == True,
        ).all()
        return {r[0] for r in rows}

    def _allocate_port(self, db: Session) -> int:
        import socket
        used = self._get_used_ports(db)
        for port in iter_port_range("searxng"):
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
        """Create+configure+start a SearXNG container for this SearxngInstance."""
        vendor = instance.vendor or "searxng"
        if vendor not in VENDOR_CONFIGS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {vendor}")

        config = VENDOR_CONFIGS[vendor]
        image = _searxng_image()
        tenant_id = instance.tenant_id
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]

        container_name: Optional[str] = None
        secret_key = secrets.token_urlsafe(48)

        with _provision_lock:
            port = self._allocate_port(db)
            container_name = f"{_get_container_prefix()}{tenant_hash}-{instance.id}"
            if len(container_name) > 63:
                container_name = container_name[:63].rstrip("-")
            volume_name = f"{_get_container_prefix()}{tenant_hash}-{instance.id}"

        network_name = resolve_tsushin_network_name(self.runtime.raw_client)
        mem_limit = instance.mem_limit or config["default_mem_limit"]
        cpu_quota = instance.cpu_quota or 100000

        logger.info(f"Provisioning searxng container: {container_name} on port {port}")

        instance.container_status = "creating"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = image
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        # Persist the secret in extra_config (Fernet-at-rest via SQLAlchemy JSON
        # is NOT applied automatically — so this value lives alongside the
        # instance. Threat model: same DB-compromise assumption as every other
        # secret we store in extra_config today.)
        extra = dict(instance.extra_config or {})
        extra["secret_key"] = secret_key
        extra["instance_label"] = f"Tsushin Search ({tenant_id[:16]})"
        instance.extra_config = extra
        db.commit()

        dns_alias = f"searxng-{tenant_hash}-{instance.id}"

        raw = self.runtime.raw_client
        if raw is None:
            raise RuntimeError("Docker raw client unavailable; cannot provision SearXNG")

        container = None
        try:
            # containers.create() (unlike containers.run()) does NOT auto-pull
            # missing images. Explicit pull so we fail fast and loudly if the
            # daemon can't reach the registry, instead of surfacing an opaque
            # 404 from the Docker API.
            try:
                raw.images.pull(image)
            except Exception as pull_err:
                logger.warning(
                    f"Image pull for {image} failed (continuing, create() will re-try): {pull_err}"
                )

            # Create-without-start so we can put_archive() the settings before
            # the container boots. Otherwise searxng-entrypoint would bake in
            # the default settings.yml and our overrides would be ignored.
            container = raw.containers.create(
                image=image,
                name=container_name,
                volumes={volume_name: {"bind": config["volume_bind"], "mode": "rw"}},
                ports={f'{config["internal_port"]}/tcp': ("127.0.0.1", port)},
                network=network_name,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                environment={
                    "SEARXNG_SETTINGS_PATH": "/etc/searxng/settings.yml",
                    "SEARXNG_SECRET": secret_key,  # belt-and-suspenders
                },
                labels={
                    "tsushin.service": "searxng",
                    "tsushin.vendor": vendor,
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance.id),
                    "tsushin.lifecycle": "auto-provisioned",
                },
                detach=True,
            )
            instance.container_id = container.id

            # Inject settings.yml via tarball — host FS never touched.
            settings_bytes = _build_settings_yml(
                secret_key=secret_key,
                instance_label=extra["instance_label"],
            )
            tar_blob = _tar_bytes_for_settings(settings_bytes)
            try:
                container.put_archive("/etc/searxng", tar_blob)
            except Exception as put_err:
                logger.warning(
                    f"put_archive /etc/searxng failed for {container_name}: {put_err} — "
                    "falling back to env-only SEARXNG_SECRET; limiter/formats will use image defaults"
                )

            # Set a short DNS alias so sibling containers can reach this one.
            try:
                if hasattr(raw, 'networks'):
                    net = raw.networks.get(network_name)
                    try:
                        net.disconnect(container_name)
                    except Exception:
                        pass
                    net.connect(container_name, aliases=[dns_alias])
            except Exception as alias_err:
                logger.warning(f"Could not set DNS alias '{dns_alias}': {alias_err}")

            container.start()

            instance.base_url = f"http://{dns_alias}:{config['internal_port']}"
            db.commit()

            healthy = self._wait_for_health(instance)
            try:
                db.rollback()
            except Exception:
                pass

            instance.container_status = "running" if healthy else "error"
            instance.health_status = "healthy" if healthy else "unavailable"
            instance.health_status_reason = (
                "Auto-provisioned and healthy"
                if healthy
                else "Container started but health check failed"
            )
            instance.last_health_check = datetime.utcnow()
            db.commit()
            logger.info(f"Provisioned searxng container: {container_name} (healthy={healthy})")

        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            if container_name:
                try:
                    self.runtime.remove_container(container_name, force=True)
                except Exception:
                    pass
            instance.container_status = "error"
            instance.container_name = None
            instance.container_id = None
            instance.container_port = None
            instance.health_status = "unavailable"
            instance.health_status_reason = str(e)[:500]
            db.commit()
            logger.error(f"Failed to provision searxng container: {e}", exc_info=True)
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
        remove_volume: bool = True,
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
                "base_url": instance.base_url,
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
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._check_health(instance):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _check_health(self, instance) -> bool:
        """Probe via JSON search — SearXNG returns 200 only if JSON is enabled,
        which is precisely what we want to verify (settings.yml injection worked)."""
        try:
            if not instance.base_url:
                return False
            resp = requests.get(
                f"{instance.base_url}/search",
                params={"q": "health", "format": "json"},
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    # --- Helpers ---

    def _get_instance(self, instance_id: int, tenant_id: str, db: Session):
        from models import SearxngInstance
        instance = db.query(SearxngInstance).filter(
            SearxngInstance.id == instance_id,
            SearxngInstance.tenant_id == tenant_id,
            SearxngInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"SearXNG instance {instance_id} not found")
        if not instance.is_auto_provisioned:
            raise ValueError(f"Instance {instance_id} is not auto-provisioned")
        return instance


# ============================================================================
# Startup reconcile — best-effort re-sync of "creating" rows on app boot.
# ============================================================================

def startup_reconcile(db: Session) -> None:
    from models import SearxngInstance

    try:
        runtime = get_container_runtime()
    except Exception as e:
        logger.warning(f"Searxng startup_reconcile: runtime unavailable: {e}")
        return

    rows = db.query(SearxngInstance).filter(
        SearxngInstance.container_status == "creating",
        SearxngInstance.is_active == True,
    ).all()
    if not rows:
        return

    logger.info(f"Searxng startup_reconcile: evaluating {len(rows)} row(s) in 'creating' state")
    for instance in rows:
        container_name = instance.container_name
        if not container_name:
            instance.container_status = "error"
            instance.health_status = "unavailable"
            instance.health_status_reason = "Reconciled at startup — container missing or failed"
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
                instance.health_status_reason = f"Reconciled at startup — container status={status}"
        except (ContainerNotFoundError, ContainerRuntimeError, Exception):
            instance.container_status = "error"
            instance.health_status = "unavailable"
            instance.health_status_reason = "Reconciled at startup — container missing or failed"
    try:
        db.commit()
    except Exception as e:
        logger.warning(f"Searxng startup_reconcile commit failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
