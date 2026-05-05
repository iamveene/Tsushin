"""
Track D: Whisper/Speaches Container Manager

Manages Docker lifecycle for per-tenant ASR instances. Mirrors the
Kokoro/SearXNG pattern, but uses an authenticated warm-up transcription call
before marking the container healthy so we verify both auth and model load.
"""

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
from sqlalchemy.orm import Session, sessionmaker

from services.container_runtime import (
    PORT_RANGES,
    ContainerNotFoundError,
    ContainerRuntime,
    ContainerRuntimeError,
    get_container_runtime,
    iter_port_range,
)
from services.docker_network_utils import resolve_tsushin_network_name
from services.whisper_instance_service import (
    WhisperInstanceService,
    DEFAULT_MODEL_ID,
    default_model_for_vendor,
)

logger = logging.getLogger(__name__)


def _speaches_image() -> str:
    return f"ghcr.io/speaches-ai/speaches:{os.getenv('SPEACHES_IMAGE_TAG', 'latest-cpu')}"


def _openai_whisper_image() -> str:
    return f"onerahmet/openai-whisper-asr-webservice:{os.getenv('OPENAI_WHISPER_IMAGE_TAG', 'latest')}"


VENDOR_CONFIGS: Dict[str, Dict[str, Any]] = {
    "speaches": {
        "internal_port": 8000,
        # The upstream Speaches image (`ghcr.io/speaches-ai/speaches:latest-cpu`)
        # runs as the non-root `ubuntu` user (uid 1000), so its HuggingFace
        # cache lives at /home/ubuntu/.cache/huggingface. Binding to
        # /root/.cache/huggingface (the previous default) left the named
        # volume empty and forced model re-downloads on every restart, which
        # in turn caused 404s on /v1/audio/transcriptions until a model was
        # cached.
        "volume_bind": "/home/ubuntu/.cache/huggingface",
        "default_mem_limit": "2g",
        "healthcheck_path": "/health",
        "transcribe_path": "/v1/audio/transcriptions",
        "transcribe_field": "file",
        "auth_scheme": "bearer",
        "image_factory": _speaches_image,
    },
    "openai_whisper": {
        "internal_port": 9000,
        "volume_bind": "/root/.cache",
        "default_mem_limit": "3g",
        # The webservice exposes the FastAPI swagger root at "/" — there is
        # no dedicated /health endpoint. We treat a 200 root response as
        # liveness; readiness is verified by the warm-up transcription call.
        "healthcheck_path": "/",
        "transcribe_path": "/asr",
        "transcribe_field": "audio_file",
        "auth_scheme": "none",
        "image_factory": _openai_whisper_image,
    },
}

PORT_RANGE_START, PORT_RANGE_END = PORT_RANGES["whisper"]
HEALTH_CHECK_TIMEOUT = 180
HEALTH_CHECK_INTERVAL = 5

_provision_lock = threading.Lock()


def _get_container_prefix() -> str:
    stack_name = (os.getenv("TSN_STACK_NAME") or "tsushin").strip() or "tsushin"
    return f"{stack_name}-whisper-"


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
        image = config["image_factory"]()
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
        vendor_default_model = default_model_for_vendor(vendor)
        default_model = (instance.default_model or vendor_default_model).strip() or vendor_default_model

        instance.container_status = "creating"
        instance.container_name = container_name
        instance.container_port = port
        instance.container_image = image
        instance.volume_name = volume_name
        instance.is_auto_provisioned = True
        db.commit()

        # BUG-717: capture every primitive needed downstream BEFORE the blocking
        # `create_container()` call. Speaches image pull + model preload can
        # block for minutes on first run, during which holding a pooled DB
        # session races PostgreSQL's `idle_in_transaction_session_timeout`
        # (BUG-665, set to 15s) and strands the row in `container_status=error`
        # even when the container is actually healthy. Mirror the Kokoro/Ollama
        # pattern: extract primitives, close the session, do the blocking I/O
        # without any DB state, then re-open a fresh session for write-back.
        instance_id = instance.id
        tenant_id_capture = instance.tenant_id
        internal_port = config["internal_port"]
        volume_bind = config["volume_bind"]
        engine = db.get_bind()

        try:
            db.close()
        except Exception:
            pass

        from models import ASRInstance  # imported lazily to avoid circulars at module load

        container = None
        try:
            environment = self._build_environment(vendor, token, default_model)

            container = self.runtime.create_container(
                image=image,
                name=container_name,
                volumes={volume_name: {"bind": volume_bind, "mode": "rw"}},
                ports={f'{internal_port}/tcp': ("127.0.0.1", port)},
                network=network_name,
                restart_policy={"Name": "unless-stopped"},
                mem_limit=mem_limit,
                cpu_quota=cpu_quota,
                environment=environment,
                labels={
                    "tsushin.service": "asr",
                    "tsushin.vendor": vendor,
                    "tsushin.tenant": tenant_id,
                    "tsushin.instance_id": str(instance_id),
                    "tsushin.lifecycle": "auto-provisioned",
                },
                detach=True,
            )

            container_id = container.id if hasattr(container, "id") else str(container)

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

            base_url_capture = f"http://{dns_alias}:{internal_port}"
            vendor_capture = vendor

            # BUG-717: open a FRESH short-lived session to persist
            # container_id + base_url before the (potentially multi-minute)
            # health-poll. The original session was closed before the pull.
            SessionLocal = sessionmaker(bind=engine)
            db_post_create = SessionLocal()
            try:
                row = db_post_create.query(ASRInstance).filter(
                    ASRInstance.id == instance_id,
                    ASRInstance.tenant_id == tenant_id_capture,
                ).first()
                if row is not None:
                    row.container_id = container_id
                    row.base_url = base_url_capture
                    db_post_create.commit()
            finally:
                db_post_create.close()

            # Reflect on the detached ORM instance so callers see up-to-date state.
            instance.container_id = container_id
            instance.base_url = base_url_capture

            # BUG-717: run health poll WITHOUT a live DB connection so the
            # multi-minute warm-up cannot hold a pooled session.
            healthy = self._wait_for_health_detached(
                base_url=base_url_capture,
                token=token,
                model=default_model,
                vendor=vendor_capture,
            )

            # Final status write on another fresh short-lived session.
            db_final = SessionLocal()
            try:
                row = db_final.query(ASRInstance).filter(
                    ASRInstance.id == instance_id,
                    ASRInstance.tenant_id == tenant_id_capture,
                ).first()
                if row is not None:
                    row.container_status = "running" if healthy else "error"
                    row.health_status = "healthy" if healthy else "unavailable"
                    row.health_status_reason = (
                        "Auto-provisioned and passed authenticated warm-up"
                        if healthy
                        else "Container started but authenticated warm-up failed"
                    )
                    row.last_health_check = datetime.utcnow()
                    db_final.commit()
            finally:
                db_final.close()

            logger.info(
                "Provisioned whisper container: %s (healthy=%s)",
                container_name,
                healthy,
            )
        except Exception as e:
            # BUG-717: original `db` is closed; rebuild a fresh session for
            # the error write-back. Clean up the orphan container first.
            if container_name:
                try:
                    self.runtime.remove_container(container_name, force=True)
                except Exception:
                    pass

            try:
                SessionLocal = sessionmaker(bind=engine)
                db_err = SessionLocal()
                try:
                    row = db_err.query(ASRInstance).filter(
                        ASRInstance.id == instance_id,
                        ASRInstance.tenant_id == tenant_id_capture,
                    ).first()
                    if row is not None:
                        row.container_status = "error"
                        row.container_name = None
                        row.container_id = None
                        row.container_port = None
                        row.health_status = "unavailable"
                        row.health_status_reason = str(e)[:500]
                        db_err.commit()
                finally:
                    db_err.close()
            except Exception as write_err:
                logger.error(
                    "Could not write Whisper provision error state: %s", write_err
                )
            logger.error("Failed to provision whisper container: %s", e, exc_info=True)
            raise

    def start_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self.runtime.start_container(instance.container_name)
        healthy = self._ensure_authenticated_ready(instance, db)
        instance.container_status = "running" if healthy else "error"
        instance.health_status = "healthy" if healthy else "unavailable"
        instance.health_status_reason = (
            "Container started and passed authenticated warm-up"
            if healthy
            else "Container started but authenticated warm-up failed"
        )
        instance.last_health_check = datetime.utcnow()
        db.commit()
        return "running" if healthy else "error"

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
        healthy = self._ensure_authenticated_ready(instance, db)
        instance.container_status = "running" if healthy else "error"
        instance.health_status = "healthy" if healthy else "unavailable"
        instance.health_status_reason = (
            "Container restarted and passed authenticated warm-up"
            if healthy
            else "Container restarted but authenticated warm-up failed"
        )
        instance.last_health_check = datetime.utcnow()
        db.commit()
        return "running" if healthy else "error"

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

    def _build_environment(self, vendor: str, token: str, default_model: str) -> Dict[str, str]:
        if vendor == "openai_whisper":
            # The webservice loads ASR_MODEL once at startup and keeps it warm.
            # Pinning ASR_ENGINE to openai_whisper guarantees we use the
            # upstream openai/whisper package (not the faster-whisper variant).
            return {
                "ASR_ENGINE": "openai_whisper",
                "ASR_MODEL": default_model,
                # The image documents an idle unload after ~5 min by default.
                # Keep the model warm — we already paid the load cost.
                "MODEL_IDLE_TIMEOUT": os.getenv("OPENAI_WHISPER_MODEL_IDLE_TIMEOUT", "0"),
            }
        # Default: speaches/faster-whisper.
        return {
            "SPEACHES_API_KEY": token,
            "API_KEY": token,
            "PRELOAD_MODELS": f'["{default_model}"]',
        }

    def _wait_for_health(self, instance, *, token: str) -> bool:
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._warm_up(instance, token=token):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _wait_for_health_detached(
        self,
        *,
        base_url: str,
        token: str,
        model: str,
        vendor: str,
    ) -> bool:
        """BUG-717: detached health-poll variant.

        Mirrors the Ollama/Kokoro pattern — takes only the primitives needed to
        fire the warm-up call, never touches a SQLAlchemy session, so the long
        wait (image pull + model load can be minutes) does not race
        ``idle_in_transaction_session_timeout``.
        """
        start = time.time()
        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            if self._warm_up_detached(
                base_url=base_url,
                token=token,
                model=model,
                vendor=vendor,
            ):
                return True
            time.sleep(HEALTH_CHECK_INTERVAL)
        return False

    def _ensure_authenticated_ready(self, instance, db: Session) -> bool:
        token = WhisperInstanceService.resolve_api_token(instance, db)
        if not token:
            logger.warning("ASR instance %s missing API token during readiness check", instance.id)
            return False
        return self._wait_for_health(instance, token=token)

    def _check_health(self, instance) -> bool:
        try:
            if not instance.base_url:
                return False
            config = VENDOR_CONFIGS.get(instance.vendor or "speaches", VENDOR_CONFIGS["speaches"])
            resp = requests.get(
                f"{instance.base_url.rstrip('/')}{config['healthcheck_path']}",
                timeout=5,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _warm_up(self, instance, *, token: str) -> bool:
        if not instance.base_url:
            return False
        vendor = instance.vendor or "speaches"
        vendor_default_model = default_model_for_vendor(vendor)
        return self._warm_up_detached(
            base_url=instance.base_url,
            token=token,
            model=(instance.default_model or vendor_default_model).strip() or vendor_default_model,
            vendor=vendor,
        )

    def _warm_up_detached(
        self,
        *,
        base_url: str,
        token: str,
        model: str,
        vendor: str,
    ) -> bool:
        if not base_url:
            return False
        config = VENDOR_CONFIGS.get(vendor)
        if not config:
            return False

        try:
            if vendor == "openai_whisper":
                # No native auth on the webservice — rely on tsushin-network
                # isolation + 127.0.0.1 host bind. Pass language to bypass
                # auto-detection on the silent warmup clip.
                wav_bytes = _build_silent_wav_bytes()
                files = {"audio_file": ("warmup.wav", wav_bytes, "audio/wav")}
                params = {"task": "transcribe", "language": "en", "output": "json", "encode": "true"}
                resp = requests.post(
                    f"{base_url.rstrip('/')}{config['transcribe_path']}",
                    files=files,
                    params=params,
                    timeout=120,
                )
                return resp.status_code == 200

            # speaches / OpenAI-compatible /v1/audio/transcriptions
            wav_bytes = _build_silent_wav_bytes()
            headers = {"Authorization": f"Bearer {token}"}
            files = {"file": ("warmup.wav", wav_bytes, "audio/wav")}
            data = {"model": model, "language": "en"}
            resp = requests.post(
                f"{base_url.rstrip('/')}{config['transcribe_path']}",
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
    manager = WhisperContainerManager()

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
                ready = manager._ensure_authenticated_ready(instance, db)
                instance.container_status = "running" if ready else "error"
                instance.health_status = "healthy" if ready else "unavailable"
                instance.health_status_reason = (
                    "Reconciled at startup — authenticated warm-up passed"
                    if ready
                    else "Reconciled at startup — authenticated warm-up failed"
                )
            else:
                instance.container_status = "error"
                instance.health_status = "unavailable"
                instance.health_status_reason = f"Reconciled at startup — container status={status}"
            instance.last_health_check = datetime.utcnow()
        except (ContainerNotFoundError, ContainerRuntimeError, Exception):
            instance.container_status = "error"
            instance.health_status = "unavailable"
            instance.health_status_reason = "Reconciled at startup — container missing or failed"
            instance.last_health_check = datetime.utcnow()
    try:
        db.commit()
    except Exception as e:
        logger.warning("Whisper startup_reconcile commit failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass
