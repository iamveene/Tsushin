"""
Track D: Whisper/Speaches Container Manager

Manages Docker lifecycle for per-tenant ASR instances. Mirrors the
Kokoro/SearXNG pattern, but uses an authenticated warm-up transcription call
before marking the container healthy so we verify both auth and model load.
"""

import base64
import hashlib
import io
import logging
import os
import struct
import threading
import time
import wave
from datetime import datetime
from typing import Optional, Set, Dict, Any

import requests
from sqlalchemy.orm import Session

from services.container_runtime import (
    PORT_RANGES,
    ContainerNotFoundError,
    ContainerRuntime,
    ContainerRuntimeError,
    get_container_runtime,
    iter_port_range,
)
from services.docker_network_utils import resolve_tsushin_network_name
from services.whisper_instance_service import WhisperInstanceService, DEFAULT_MODEL_ID

logger = logging.getLogger(__name__)


def _speaches_image() -> str:
    return f"ghcr.io/speaches-ai/speaches:{os.getenv('SPEACHES_IMAGE_TAG', 'latest-cpu')}"


VENDOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "speaches": {
        "internal_port": 8000,
        "volume_bind": "/home/ubuntu/.cache/huggingface/hub",
        "default_mem_limit": "2g",
        "healthcheck_path": "/health",
    },
}

PORT_RANGE_START, PORT_RANGE_END = PORT_RANGES["whisper"]
HEALTH_CHECK_TIMEOUT = 180
HEALTH_CHECK_INTERVAL = 5

_provision_lock = threading.Lock()


def _get_container_prefix() -> str:
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-whisper-"


def _make_basic_auth_header(username: str, token: str) -> str:
    raw = f"{username}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _build_silent_wav_bytes(duration_seconds: float = 1.0) -> bytes:
    sample_rate = 16000
    frames = max(1, int(sample_rate * duration_seconds))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        silence = struct.pack("<h", 0) * frames
        wav.writeframes(silence)
    return buf.getvalue()


class WhisperContainerManager:
    def __init__(self):
        self.runtime: ContainerRuntime = get_container_runtime()

    def _get_used_ports(self, db: Session) -> Set[int]:
        from models import ASRInstance

        rows = db.query(ASRInstance.container_port).filter(
            ASRInstance.container_port.isnot(None),
            ASRInstance.is_active == True,
        ).all()
        return {r[0] for r in rows}

    def _allocate_port(self, db: Session) -> int:
        import socket

        used = self._get_used_ports(db)
        for port in iter_port_range("whisper"):
            if port in used:
                continue
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
        raise RuntimeError(f"No available ports in range {PORT_RANGE_START}-{PORT_RANGE_END}")

    def provision(self, instance, db: Session) -> None:
        vendor = instance.vendor or "speaches"
        if vendor not in VENDOR_CONFIGS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {vendor}")

        config = VENDOR_CONFIGS[vendor]
        image = _speaches_image()
        tenant_id = instance.tenant_id
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]

        with _provision_lock:
            port = self._allocate_port(db)
            container_name = f"{_get_container_prefix()}{tenant_hash}-{instance.id}"
            if len(container_name) > 63:
                container_name = container_name[:63].rstrip("-")
            volume_name = f"{_get_container_prefix()}{tenant_hash}-{instance.id}"

        mem_limit = instance.mem_limit or config["default_mem_limit"]
        cpu_quota = instance.cpu_quota or 100000
        network_name = resolve_tsushin_network_name(self.runtime.raw_client)
        dns_alias = f"whisper-{tenant_hash}-{instance.id}"
        token = WhisperInstanceService.resolve_api_token(instance, db)
        if not token:
            raise RuntimeError("Missing decrypted ASR API token")
        username = (instance.auth_username or "tsushin").strip() or "tsushin"
        default_model = (instance.default_model or DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID

        instance.container_status = "creating"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = image
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        db.commit()

        container = None
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
                environment={
                    # The repo contract names SPEACHES_API_KEY explicitly;
                    # upstream Speaches currently reads API_KEY. Set both.
                    "SPEACHES_API_KEY": token,
                    "API_KEY": token,
                    "PRELOAD_MODELS": f'["{default_model}"]',
                },
                labels={
                    "tsushin.service": "asr",
                    "tsushin.vendor": vendor,
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance.id),
                    "tsushin.lifecycle": "auto-provisioned",
                },
                detach=True,
            )

            instance.container_id = container.id if hasattr(container, "id") else str(container)

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
                logger.warning("Could not set DNS alias '%s': %s", dns_alias, alias_err)

            instance.base_url = f"http://{dns_alias}:{config['internal_port']}"
            db.commit()

            healthy = self._wait_for_health(instance, token=token, username=username)
            try:
                db.rollback()
            except Exception:
                pass

            instance.container_status = "running" if healthy else "error"
            instance.health_status = "healthy" if healthy else "unavailable"
            instance.health_status_reason = (
                "Auto-provisioned and passed authenticated warm-up"
                if healthy
                else "Container started but authenticated warm-up failed"
            )
            instance.last_health_check = datetime.utcnow()
            db.commit()
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
            logger.error("Failed to provision whisper container: %s", e, exc_info=True)
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
        if remove_volume and instance.volume_name:
            try:
                self.runtime.remove_volume(instance.volume_name, force=True)
            except Exception as e:
                logger.warning("Failed to remove volume %s: %s", instance.volume_name, e)

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

    def _wait_for_health(self, instance, *, token: str, username: str) -> bool:
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._check_health(instance) and self._warm_up(instance, token=token, username=username):
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

    def _warm_up(self, instance, *, token: str, username: str) -> bool:
        try:
            if not instance.base_url:
                return False
            wav_bytes = _build_silent_wav_bytes()
            headers = {
                "Authorization": _make_basic_auth_header(username, token),
                "X-API-Key": token,
            }
            files = {"file": ("warmup.wav", wav_bytes, "audio/wav")}
            data = {
                "model": (instance.default_model or DEFAULT_MODEL_ID).strip() or DEFAULT_MODEL_ID,
                "language": "en",
            }
            resp = requests.post(
                f"{instance.base_url}/v1/audio/transcriptions",
                headers=headers,
                files=files,
                data=data,
                timeout=45,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _get_instance(self, instance_id: int, tenant_id: str, db: Session):
        from models import ASRInstance

        instance = db.query(ASRInstance).filter(
            ASRInstance.id == instance_id,
            ASRInstance.tenant_id == tenant_id,
            ASRInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"ASR instance {instance_id} not found")
        if not instance.is_auto_provisioned:
            raise ValueError(f"Instance {instance_id} is not auto-provisioned")
        return instance


def startup_reconcile(db: Session) -> None:
    from models import ASRInstance

    try:
        runtime = get_container_runtime()
    except Exception as e:
        logger.warning("Whisper startup_reconcile: runtime unavailable: %s", e)
        return

    rows = db.query(ASRInstance).filter(
        ASRInstance.container_status.in_(["creating", "provisioning"]),
        ASRInstance.is_active == True,
    ).all()
    if not rows:
        return

    logger.info("Whisper startup_reconcile: evaluating %d row(s)", len(rows))
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
        logger.warning("Whisper startup_reconcile commit failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
