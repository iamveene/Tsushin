"""
Ollama Container Manager — per-tenant auto-provisioning of Ollama containers.

Mirrors VectorStoreContainerManager. Manages Docker container lifecycle for
tenant-owned Ollama instances so each tenant can have a private, isolated
LLM runtime reachable only via the internal tsushin-network DNS alias.

Provisioning is always tenant-scoped; every DB query filters by tenant_id.
Uses threading.Lock for port-allocation safety (uvicorn runs --workers 1).
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
from sqlalchemy.orm import Session, sessionmaker

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
    "ollama": {
        "image": os.getenv("OLLAMA_IMAGE_TAG", "ollama/ollama:latest"),
        "internal_port": 11434,
        "volume_bind": "/root/.ollama",
        "default_mem_limit": "4g",
    },
}

PORT_RANGE_START, PORT_RANGE_END = PORT_RANGES["ollama"]
HEALTH_CHECK_TIMEOUT = 120  # Ollama takes longer to start than Qdrant
HEALTH_CHECK_INTERVAL = 5


def _get_container_prefix() -> str:
    """Use TSN_STACK_NAME for runtime container isolation (mirrors BUG-448 pattern)."""
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-ollama-"


_provision_lock = threading.Lock()


# BUG-650: sanitize error text before persisting / returning to the UI.
# Strips raw SQL fragments and long hex container IDs that leak internals.
_HEX_ID_RE = re.compile(r"\b[a-f0-9]{12,64}\b", re.IGNORECASE)
_SQL_NOISE_RE = re.compile(
    r"(\[SQL:.*?\]|\(Background on this error at:.*?\)|\(psycopg2.*?\))",
    re.DOTALL,
)


def _sanitize_health_reason(text: str, max_len: int = 500) -> str:
    """Strip SQL + container-ID noise from provisioning error text."""
    if not text:
        return ""
    cleaned = _SQL_NOISE_RE.sub("", str(text))
    cleaned = _HEX_ID_RE.sub("<id>", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[: max_len - 1] + "\u2026"
    return cleaned


class OllamaContainerManager:
    """Manages auto-provisioned Docker containers for Ollama provider instances."""

    def __init__(self):
        self.runtime: ContainerRuntime = get_container_runtime()

    # ------------------------------------------------------------------
    # Port allocation
    # ------------------------------------------------------------------

    def _get_used_ports(self, db: Session) -> Set[int]:
        from models import ProviderInstance
        rows = db.query(ProviderInstance.container_port).filter(
            ProviderInstance.vendor == "ollama",
            ProviderInstance.container_port.isnot(None),
            ProviderInstance.is_active == True,
        ).all()
        return {r[0] for r in rows if r[0] is not None}

    def _allocate_port(self, db: Session) -> int:
        import socket
        used = self._get_used_ports(db)
        for port in iter_port_range("ollama"):
            if port in used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
        raise RuntimeError(
            f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}"
        )

    # ------------------------------------------------------------------
    # Container lifecycle
    # ------------------------------------------------------------------

    def provision(self, instance, db: Session) -> None:
        """
        Create and start a Docker container for the given Ollama ProviderInstance.
        Updates the instance in-place with container metadata and sets base_url
        to the internal DNS alias.
        """
        if instance.vendor != "ollama":
            raise ValueError(
                f"OllamaContainerManager can only provision Ollama instances "
                f"(got vendor={instance.vendor})"
            )

        config = VENDOR_CONFIGS["ollama"]
        tenant_id = instance.tenant_id

        # GPU pre-flight: refuse cleanly instead of letting Docker crash.
        if instance.gpu_enabled:
            try:
                supports_gpu = self.runtime.supports_gpu()
            except Exception:
                supports_gpu = False
            if not supports_gpu:
                instance.container_status = "error"
                instance.health_status = "unavailable"
                instance.health_status_reason = _sanitize_health_reason(
                    "GPU requested but NVIDIA Container Toolkit not detected"
                )
                db.commit()
                raise RuntimeError(
                    "GPU requested but NVIDIA Container Toolkit not detected. "
                    "Install nvidia-container-toolkit or uncheck GPU."
                )

        # Short DNS-safe hash of tenant ID.
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]

        # Lock to prevent port allocation race condition.
        with _provision_lock:
            port = self._allocate_port(db)

            prefix = _get_container_prefix()
            container_name = f"{prefix}{tenant_hash}-{instance.id}"
            if len(container_name) > 63:
                container_name = container_name[:63].rstrip("-")

            volume_name = f"{prefix}{tenant_hash}-{instance.id}"

        # Resolve network.
        network_name = resolve_tsushin_network_name(self.runtime.raw_client)

        mem_limit = instance.mem_limit or config["default_mem_limit"]
        cpu_quota = instance.cpu_quota or 100000  # 1 CPU default

        # DNS alias that matches the SSRF allowlist bypass pattern:
        # ^tsushin-ollama-[a-f0-9]{8}-\d+$
        dns_alias = f"tsushin-ollama-{tenant_hash}-{instance.id}"

        logger.info(
            f"Provisioning Ollama container: {container_name} "
            f"(tenant={tenant_id}, port={port}, gpu={instance.gpu_enabled})"
        )

        instance.container_status = "provisioning"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = config["image"]
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        db.commit()

        # Optional GPU device request.
        device_requests = None
        if instance.gpu_enabled:
            try:
                import docker
                device_requests = [
                    docker.types.DeviceRequest(count=1, capabilities=[["gpu"]])
                ]
            except Exception as e:
                logger.warning(
                    f"Failed to build GPU DeviceRequest (will fall back to CPU): {e}"
                )
                device_requests = None

        # BUG-663: capture ALL primitives needed downstream BEFORE the blocking
        # `create_container()` call. `docker pull` can block for up to 20
        # minutes on first use; holding a pooled DB session across that window
        # races PostgreSQL's idle_in_transaction_session_timeout and TCP
        # keepalive, which silently drops the socket and corrupts subsequent
        # writes. Extract primitives, close the session, do the blocking I/O
        # without any DB state, then re-open a fresh session for the write-back.
        instance_id = instance.id
        tenant_id_capture = instance.tenant_id
        internal_port = config["internal_port"]
        image = config["image"]
        volume_bind = config["volume_bind"]
        engine = db.get_bind()
        # Bind to err_* names too so the except-path can use them after close.
        err_instance_id = instance_id
        err_tenant_id_capture = tenant_id_capture
        db.close()

        container = None
        try:
            container = self.runtime.create_container(
                image=image,
                name=container_name,
                volumes={volume_name: {"bind": volume_bind, "mode": "rw"}},
                ports={f"{internal_port}/tcp": ("127.0.0.1", port)},
                network=network_name,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                labels={
                    "tsushin.service": "ollama",
                    "tsushin.vendor": "ollama",
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance_id),
                },
                detach=True,
                device_requests=device_requests,
            )

            container_id = (
                container.id if hasattr(container, "id") else str(container)
            )

            # Add the short DNS alias on the tsushin network so the backend can
            # reach the container at a stable, SSRF-allowlisted hostname.
            try:
                raw = self.runtime.raw_client
                if raw and hasattr(raw, "networks"):
                    net = raw.networks.get(network_name)
                    try:
                        net.disconnect(container_name)
                    except Exception:
                        pass
                    net.connect(container_name, aliases=[dns_alias])
            except Exception as alias_err:
                logger.warning(
                    f"Could not set DNS alias '{dns_alias}' for {container_name}: "
                    f"{alias_err}"
                )

            # base_url points at the DNS alias, not the host port.
            base_url_capture = f"http://{dns_alias}:{internal_port}"

            # BUG-663: open a FRESH session to persist container_id + base_url
            # now that `create_container()` (blocking docker pull) has returned.
            # The original session was closed before the pull.
            SessionLocal = sessionmaker(bind=engine)
            db_post_create = SessionLocal()
            try:
                from models import ProviderInstance
                inst_row = db_post_create.query(ProviderInstance).filter(
                    ProviderInstance.id == instance_id,
                    ProviderInstance.tenant_id == tenant_id_capture,
                ).first()
                if inst_row is not None:
                    inst_row.container_id = container_id
                    inst_row.base_url = base_url_capture
                    db_post_create.commit()
            finally:
                db_post_create.close()

            try:
                # Run health poll WITHOUT a live DB connection so the 60-120s
                # wait cannot hold a pooled session.
                healthy = self._wait_for_health_detached(base_url_capture)
            finally:
                # Re-attach: open a fresh session from the same engine and
                # re-fetch the row so subsequent writes go against a live conn.
                SessionLocal = sessionmaker(bind=engine)
                db_new = SessionLocal()
                try:
                    from models import ProviderInstance
                    instance = db_new.query(ProviderInstance).filter(
                        ProviderInstance.id == instance_id,
                        ProviderInstance.tenant_id == tenant_id_capture,
                    ).first()
                    if instance is not None:
                        instance.container_status = "running" if healthy else "error"
                        instance.health_status = "healthy" if healthy else "unavailable"
                        instance.health_status_reason = (
                            "Auto-provisioned and healthy"
                            if healthy
                            else "Container started but health check failed"
                        )
                        instance.last_health_check = datetime.utcnow()
                        db_new.commit()
                finally:
                    db_new.close()

            logger.info(
                f"Provisioned Ollama container: {container_name} (healthy={healthy})"
            )

        except Exception as e:
            logger.error(
                f"Failed to provision Ollama container {container_name}: {e}",
                exc_info=True,
            )
            # BUG-663: the original `db` session is already closed (we released
            # it before the blocking pull). Use the primitives captured above
            # and rebuild a fresh session for the error write-back.
            # PEER REVIEW B-B3: remove the half-created container BEFORE clearing DB
            # fields so we never orphan a container we can no longer find by name.
            try:
                self.runtime.remove_container(container_name, force=True)
            except Exception:
                pass

            if engine is not None:
                SessionLocal = sessionmaker(bind=engine)
                db_err = SessionLocal()
                try:
                    from models import ProviderInstance
                    err_instance = db_err.query(ProviderInstance).filter(
                        ProviderInstance.id == err_instance_id,
                        ProviderInstance.tenant_id == err_tenant_id_capture,
                    ).first() if (err_instance_id is not None and err_tenant_id_capture is not None) else None
                    if err_instance is not None:
                        err_instance.container_status = "error"
                        err_instance.container_name = None
                        err_instance.container_id = None
                        err_instance.container_port = None
                        err_instance.base_url = None
                        err_instance.health_status = "unavailable"
                        # BUG-650: strip raw SQL + container-ID noise.
                        err_instance.health_status_reason = _sanitize_health_reason(
                            str(e)
                        )
                        db_err.commit()
                finally:
                    db_err.close()
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
            logger.info(f"Removed Ollama container: {instance.container_name}")

        if remove_volume and instance.volume_name:
            try:
                self.runtime.remove_volume(instance.volume_name, force=True)
                logger.info(f"Removed Ollama volume: {instance.volume_name}")
            except Exception as e:
                logger.warning(
                    f"Failed to remove Ollama volume {instance.volume_name}: {e}"
                )

        instance.container_status = "none"
        instance.container_name = None
        instance.container_id = None
        instance.container_port = None
        instance.base_url = None
        db.commit()

    def get_status(
        self, instance_id: int, tenant_id: str, db: Session
    ) -> Dict[str, Any]:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return {
                "status": "none",
                "container_name": None,
                "container_port": None,
                "image": None,
                "volume": None,
                "pulled_models": instance.pulled_models or [],
            }
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
                "pulled_models": instance.pulled_models or [],
            }
        except ContainerNotFoundError:
            instance.container_status = "not_found"
            db.commit()
            return {
                "status": "not_found",
                "container_name": instance.container_name,
                "container_port": instance.container_port,
                "image": instance.container_image,
                "volume": instance.volume_name,
                "pulled_models": instance.pulled_models or [],
            }

    def get_logs(
        self, instance_id: int, tenant_id: str, db: Session, tail: int = 100
    ) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return ""
        return self.runtime.get_container_logs(instance.container_name, tail=tail)

    # ------------------------------------------------------------------
    # Health checking
    # ------------------------------------------------------------------

    def _wait_for_health(self, instance) -> bool:
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._check_health(instance):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _wait_for_health_detached(self, base_url: Optional[str]) -> bool:
        """Same as _wait_for_health but takes base_url directly so the caller
        can run the poll without holding a SQLAlchemy-bound instance (and thus
        without holding a DB connection for 60-120s). See BUG-649.
        """
        if not base_url:
            return False
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            try:
                resp = requests.get(f"{base_url}/api/tags", timeout=5)
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _check_health(self, instance) -> bool:
        try:
            base_url = instance.base_url
            if not base_url:
                return False
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_instance(self, instance_id: int, tenant_id: str, db: Session):
        """Tenant-filtered lookup — never returns another tenant's instance."""
        from models import ProviderInstance
        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == "ollama",
            ProviderInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Ollama provider instance {instance_id} not found")
        if not instance.is_auto_provisioned:
            raise ValueError(
                f"Instance {instance_id} is not auto-provisioned (host-Ollama)"
            )
        return instance


# ----------------------------------------------------------------------
# Startup reconciliation
# ----------------------------------------------------------------------


def startup_reconcile(db: Optional[Session] = None) -> None:
    """
    Reconcile auto-provisioned Ollama instances at app startup.

    For every ProviderInstance where vendor=='ollama' AND is_auto_provisioned==True
    AND container_status IN ('creating','provisioning'), try to locate the
    container. If present, sync container_status from the runtime; if absent
    (crashed mid-provision / host restart), mark the row as 'error' so the
    tenant sees actionable state.

    Always opens its own DB session if one is not provided — must be safe to
    call from a FastAPI startup hook.
    """
    from models import ProviderInstance

    own_session = False
    if db is None:
        try:
            from db import get_global_engine
            engine = get_global_engine()
        except Exception:
            engine = None
        if engine is None:
            logger.warning(
                "Ollama startup_reconcile: no engine available; skipping"
            )
            return
        from sqlalchemy.orm import sessionmaker
        SessionLocal = sessionmaker(bind=engine)
        db = SessionLocal()
        own_session = True

    try:
        try:
            runtime = get_container_runtime()
        except Exception as e:
            logger.warning(f"Ollama startup_reconcile: runtime init failed: {e}")
            return

        rows = db.query(ProviderInstance).filter(
            ProviderInstance.vendor == "ollama",
            ProviderInstance.is_auto_provisioned == True,
            ProviderInstance.container_status.in_(("creating", "provisioning")),
        ).all()

        if not rows:
            return

        logger.info(
            f"Ollama startup_reconcile: found {len(rows)} instance(s) "
            f"in creating/provisioning state"
        )

        for inst in rows:
            try:
                if not inst.container_name:
                    inst.container_status = "error"
                    inst.health_status = "unavailable"
                    inst.health_status_reason = "Reconciled at startup"
                    continue
                try:
                    status = runtime.get_container_status(inst.container_name)
                    inst.container_status = status or "error"
                    inst.health_status_reason = "Reconciled at startup"
                except ContainerNotFoundError:
                    inst.container_status = "error"
                    inst.health_status = "unavailable"
                    inst.health_status_reason = "Reconciled at startup"
            except Exception as e:
                logger.warning(
                    f"Ollama reconcile failed for instance {inst.id}: {e}"
                )

        db.commit()
    finally:
        if own_session:
            try:
                db.close()
            except Exception:
                pass
