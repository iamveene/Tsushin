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
from typing import Optional, Set, Dict, Any, List

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
        "default_mem_limit": "4g",
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
_MANAGED_LIFECYCLE = "auto-provisioned"


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

    @staticmethod
    def _container_name(container: Any) -> str:
        name = getattr(container, "name", None)
        if name:
            return str(name).lstrip("/")
        attrs = getattr(container, "attrs", None) or {}
        return str(attrs.get("Name") or "").lstrip("/")

    @staticmethod
    def _container_id(container: Any) -> str:
        cid = getattr(container, "id", None)
        if cid:
            return str(cid)
        attrs = getattr(container, "attrs", None) or {}
        return str(attrs.get("Id") or "")

    @staticmethod
    def _container_status(container: Any) -> str:
        try:
            reload_fn = getattr(container, "reload", None)
            if callable(reload_fn):
                reload_fn()
        except Exception:
            pass
        status = getattr(container, "status", None)
        if status:
            return str(status)
        attrs = getattr(container, "attrs", None) or {}
        state = attrs.get("State") or {}
        return str(state.get("Status") or "unknown")

    @staticmethod
    def _container_labels(container: Any) -> Dict[str, str]:
        labels = getattr(container, "labels", None) or {}
        if labels:
            return dict(labels)
        attrs = getattr(container, "attrs", None) or {}
        config = attrs.get("Config") or {}
        return dict(config.get("Labels") or {})

    def _list_managed_containers(self) -> List[Any]:
        raw = getattr(self.runtime, "raw_client", None)
        containers = getattr(raw, "containers", None) if raw is not None else None
        list_fn = getattr(containers, "list", None)
        if not callable(list_fn):
            return []
        try:
            return list_fn(
                all=True,
                filters={
                    "label": [
                        "tsushin.service=asr",
                        f"tsushin.lifecycle={_MANAGED_LIFECYCLE}",
                    ]
                },
            )
        except TypeError:
            # Some test doubles only accept a filters kwarg. Falling back keeps
            # the reconcile path unit-testable without weakening Docker usage.
            return list_fn(
                filters={
                    "label": [
                        "tsushin.service=asr",
                        f"tsushin.lifecycle={_MANAGED_LIFECYCLE}",
                    ]
                },
            )

    def _assert_container_ownership(self, instance):
        if not instance.container_name:
            return None
        container = self.runtime.get_container(instance.container_name)
        labels = self._container_labels(container)
        expected = {
            "tsushin.service": "asr",
            "tsushin.tenant": instance.tenant_id,
            "tsushin.instance_id": str(instance.id),
        }
        mismatches = [
            f"{key}={labels.get(key)!r}"
            for key, value in expected.items()
            if labels.get(key) != value
        ]
        if mismatches:
            raise ValueError(
                "ASR container ownership mismatch for "
                f"{instance.container_name}: expected tenant={instance.tenant_id!r} "
                f"instance_id={instance.id}; got {', '.join(mismatches)}"
            )
        return container

    @staticmethod
    def _default_runtime_targets(tenant_id: str, instance_id: int) -> Dict[str, Any]:
        tenant_hash = hashlib.md5(tenant_id.encode()).hexdigest()[:8]
        container_name = f"{_get_container_prefix()}{tenant_hash}-{instance_id}"
        if len(container_name) > 63:
            container_name = container_name[:63].rstrip("-")
        return {
            "tenant_hash": tenant_hash,
            "container_name": container_name,
            "volume_name": f"{_get_container_prefix()}{tenant_hash}-{instance_id}",
        }

    def _resolve_provision_targets(
        self,
        instance,
        db: Session,
        *,
        preserve_existing: bool = False,
    ) -> Dict[str, Any]:
        targets = self._default_runtime_targets(instance.tenant_id, instance.id)
        if preserve_existing:
            targets["container_name"] = instance.container_name or targets["container_name"]
            targets["volume_name"] = instance.volume_name or targets["volume_name"]
            targets["port"] = instance.container_port or self._allocate_port(db)
        else:
            targets["port"] = self._allocate_port(db)
        return targets

    @staticmethod
    def _container_runtime_context(container: Any) -> Dict[str, Any]:
        attrs = getattr(container, "attrs", None) or {}
        state = attrs.get("State") or attrs.get("state") or {}
        restart_count = attrs.get("RestartCount")
        if restart_count is None:
            restart_count = attrs.get("restart_count")
        exit_code = state.get("ExitCode")
        oom_killed = state.get("OOMKilled")
        if isinstance(oom_killed, str):
            oom_killed = oom_killed.strip().lower() == "true"
        else:
            oom_killed = bool(oom_killed) if oom_killed is not None else False
        state_status = state.get("Status") or getattr(container, "status", None)
        state_error = state.get("Error") or None
        finished_at = state.get("FinishedAt") or None
        started_at = state.get("StartedAt") or None
        recent_exit = bool(
            oom_killed
            or state_status in {"exited", "dead"}
            or (exit_code not in (None, 0, "0"))
        )
        return {
            "restart_count": restart_count,
            "oom_killed": oom_killed,
            "exit_code": exit_code,
            "state": state_status,
            "state_error": state_error,
            "started_at": started_at,
            "finished_at": finished_at,
            "recent_exit": recent_exit,
        }

    @staticmethod
    def _format_runtime_context(context: Dict[str, Any]) -> str:
        parts = []
        if context.get("restart_count") is not None:
            parts.append(f"restart_count={context['restart_count']}")
        if context.get("oom_killed"):
            parts.append("oom_killed=true")
        exit_code = context.get("exit_code")
        if exit_code not in (None, 0, "0"):
            parts.append(f"exit_code={exit_code}")
        if context.get("state_error"):
            parts.append(f"state_error={context['state_error']}")
        if context.get("finished_at"):
            parts.append(f"finished_at={context['finished_at']}")
        return ", ".join(parts)

    def _remove_existing_container_for_retry(
        self,
        container_name: str,
        *,
        tenant_id: str,
        instance_id: int,
    ) -> None:
        try:
            container = self.runtime.get_container(container_name)
        except ContainerNotFoundError:
            return

        labels = self._container_labels(container)
        if (
            labels.get("tsushin.service") != "asr"
            or labels.get("tsushin.tenant") != tenant_id
            or labels.get("tsushin.instance_id") != str(instance_id)
        ):
            raise RuntimeError(
                "Refusing to replace ASR container with mismatched ownership "
                f"labels: {container_name}"
            )
        self.runtime.remove_container(container_name, force=True)

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

    def provision(self, instance, db: Session, *, preserve_existing: bool = False) -> None:
        vendor = instance.vendor or "speaches"
        if vendor not in VENDOR_CONFIGS:
            raise ValueError(f"Auto-provisioning not supported for vendor: {vendor}")

        config = VENDOR_CONFIGS[vendor]
        image = config["image_factory"]()
        tenant_id = instance.tenant_id

        with _provision_lock:
            targets = self._resolve_provision_targets(
                instance,
                db,
                preserve_existing=preserve_existing,
            )
            tenant_hash = targets["tenant_hash"]
            port = targets["port"]
            container_name = targets["container_name"]
            volume_name = targets["volume_name"]

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
            self._remove_existing_container_for_retry(
                container_name,
                tenant_id=tenant_id_capture,
                instance_id=instance_id,
            )

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
                    "tsushin.lifecycle": _MANAGED_LIFECYCLE,
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
                status_value = "running" if healthy else "error"
                health_value = "healthy" if healthy else "unavailable"
                reason_value = (
                    "Auto-provisioned and passed authenticated warm-up"
                    if healthy
                    else "Container started but authenticated warm-up failed"
                )
                checked_at = datetime.utcnow()
                if row is not None:
                    row.container_status = status_value
                    row.health_status = health_value
                    row.health_status_reason = reason_value
                    row.last_health_check = checked_at
                    db_final.commit()
                instance.container_status = status_value
                instance.health_status = health_value
                instance.health_status_reason = reason_value
                instance.last_health_check = checked_at
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

    def reprovision(
        self,
        instance_id: int,
        tenant_id: str,
        db: Session,
        *,
        mem_limit: Optional[str] = None,
        cpu_quota: Optional[int] = None,
    ):
        instance = self._get_instance(instance_id, tenant_id, db)
        if instance.container_name:
            try:
                self._assert_container_ownership(instance)
            except ContainerNotFoundError:
                pass
        if mem_limit is not None:
            instance.mem_limit = mem_limit
        if cpu_quota is not None:
            instance.cpu_quota = cpu_quota
        instance.container_status = "provisioning"
        instance.health_status = "unknown"
        instance.health_status_reason = "Reprovisioning ASR container with updated runtime limits"
        instance.last_health_check = datetime.utcnow()
        db.commit()

        self.provision(instance, db, preserve_existing=True)
        return instance

    def start_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self._assert_container_ownership(instance)
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
        self._assert_container_ownership(instance)
        self.runtime.stop_container(instance.container_name)
        instance.container_status = "stopped"
        db.commit()
        return "stopped"

    def restart_container(self, instance_id: int, tenant_id: str, db: Session) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            raise ValueError("No container associated with this instance")
        self._assert_container_ownership(instance)
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
                self._assert_container_ownership(instance)
            except ContainerNotFoundError:
                pass
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
        instance.health_status = "unknown"
        instance.health_status_reason = "Deprovisioned"
        instance.last_health_check = datetime.utcnow()
        db.commit()

    def get_status(self, instance_id: int, tenant_id: str, db: Session) -> Dict[str, Any]:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return {"status": "none", "container_name": None}
        try:
            container = self._assert_container_ownership(instance)
            status = self._container_status(container)
            runtime_context = self._container_runtime_context(container)
            should_commit = False
            if status != instance.container_status:
                instance.container_status = status
                should_commit = True
            context_reason = self._format_runtime_context(runtime_context)
            if runtime_context.get("recent_exit") and context_reason:
                instance.health_status = "unavailable"
                instance.health_status_reason = f"Container runtime context: {context_reason}"[:500]
                instance.last_health_check = datetime.utcnow()
                should_commit = True
                logger.warning(
                    "ASR container %s reported recent exit context: %s",
                    instance.container_name,
                    context_reason,
                )
            if should_commit:
                db.commit()
            return {
                "status": status,
                "container_name": instance.container_name,
                "container_port": instance.container_port,
                "image": instance.container_image,
                "volume": instance.volume_name,
                "base_url": instance.base_url,
                **runtime_context,
            }
        except ContainerNotFoundError:
            instance.container_status = "not_found"
            instance.health_status = "unavailable"
            instance.health_status_reason = "Container not found"
            instance.last_health_check = datetime.utcnow()
            db.commit()
            return {"status": "not_found", "container_name": instance.container_name}
        except ValueError as e:
            instance.container_status = "ownership_mismatch"
            instance.health_status = "unavailable"
            instance.health_status_reason = str(e)[:500]
            instance.last_health_check = datetime.utcnow()
            db.commit()
            return {
                "status": "ownership_mismatch",
                "container_name": instance.container_name,
            }

    def get_logs(self, instance_id: int, tenant_id: str, db: Session, tail: int = 100) -> str:
        instance = self._get_instance(instance_id, tenant_id, db)
        if not instance.container_name:
            return ""
        container = self._assert_container_ownership(instance)
        runtime_context = self._container_runtime_context(container)
        logs = self.runtime.get_container_logs(instance.container_name, tail=tail)
        context_reason = self._format_runtime_context(runtime_context)
        if runtime_context.get("recent_exit") and context_reason:
            logger.warning(
                "ASR container %s log request includes runtime context: %s",
                instance.container_name,
                context_reason,
            )
            return f"[container runtime] {context_reason}\n{logs}"
        return logs

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
            headers = {"Authorization": f"Bearer {token}"}
            # The PRELOAD_MODELS env var is not honored by
            # ghcr.io/speaches-ai/speaches:latest-cpu — model assets are
            # only fetched when the OpenAI-compatible /v1/models/{name}
            # endpoint is hit. Without this call, the silent-WAV warm-up
            # below 404s with "Model '<name>' is not installed locally"
            # and the container is marked unhealthy forever.
            self._ensure_speaches_model(base_url=base_url, headers=headers, model=model)

            wav_bytes = _build_silent_wav_bytes()
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

    @staticmethod
    def _ensure_speaches_model(*, base_url: str, headers: Dict[str, str], model: str) -> bool:
        try:
            resp = requests.post(
                f"{base_url.rstrip('/')}/v1/models/{model}",
                headers=headers,
                timeout=300,
            )
        except Exception as exc:
            logger.warning(
                "Speaches model download request failed for %s: %s",
                model,
                exc,
            )
            return False
        if resp.status_code not in (200, 201, 204, 409):
            logger.warning(
                "Speaches model download returned %s for %s: %s",
                resp.status_code,
                model,
                (resp.text or "")[:200],
            )
            return False
        return True

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

    def reconcile_managed_containers(
        self,
        db: Session,
        *,
        remove_orphans: bool = True,
    ) -> Dict[str, int]:
        """Reconcile Docker-managed ASR containers with active tenant DB rows.

        This intentionally uses both immutable identity labels and tenant-scoped
        rows. A container is considered valid only when labels, row tenant, row
        id, and row container name agree. Anything labeled as a managed ASR
        container without a matching active row is removed during startup so
        failed UI provisions cannot leave dead local Whisper containers behind.
        """
        from models import ASRInstance

        stats = {
            "rows_checked": 0,
            "rows_updated": 0,
            "orphan_containers_removed": 0,
            "orphan_containers_seen": 0,
        }
        rows = db.query(ASRInstance).filter(
            ASRInstance.is_auto_provisioned == True,
            ASRInstance.is_active == True,
        ).all()
        stats["rows_checked"] = len(rows)
        rows_by_key = {(row.tenant_id, str(row.id)): row for row in rows}
        seen_row_ids: Set[int] = set()

        for container in self._list_managed_containers():
            name = self._container_name(container)
            labels = self._container_labels(container)
            tenant_id = labels.get("tsushin.tenant")
            instance_id = labels.get("tsushin.instance_id")
            row = rows_by_key.get((tenant_id, instance_id))
            status = self._container_status(container)
            cid = self._container_id(container)

            if row is None or (row.container_name and row.container_name != name):
                stats["orphan_containers_seen"] += 1
                if remove_orphans and name:
                    try:
                        self.runtime.remove_container(name, force=True)
                        stats["orphan_containers_removed"] += 1
                    except Exception as e:
                        logger.warning(
                            "Whisper reconcile could not remove orphan container %s: %s",
                            name,
                            e,
                        )
                continue

            seen_row_ids.add(row.id)
            if row.container_status in {"creating", "provisioning"}:
                continue
            if not row.container_name and name:
                row.container_name = name
                stats["rows_updated"] += 1
            if row.container_id != cid and cid:
                row.container_id = cid
                stats["rows_updated"] += 1
            if row.container_status != status:
                row.container_status = status
                stats["rows_updated"] += 1
            if status != "running":
                row.health_status = "unavailable"
                row.health_status_reason = (
                    f"Reconciled at startup — container status={status}"
                )
                row.last_health_check = datetime.utcnow()

        for row in rows:
            if row.id in seen_row_ids:
                continue
            if row.container_status in {"creating", "provisioning"}:
                continue
            if not row.container_name:
                continue
            try:
                self._assert_container_ownership(row)
                status = self.runtime.get_container_status(row.container_name)
            except ContainerNotFoundError:
                status = "not_found"
            except Exception as e:
                row.container_status = "ownership_mismatch"
                row.health_status = "unavailable"
                row.health_status_reason = str(e)[:500]
                row.last_health_check = datetime.utcnow()
                stats["rows_updated"] += 1
                continue
            if row.container_status != status:
                row.container_status = status
                stats["rows_updated"] += 1
            if status in {"not_found", "exited", "dead", "removing"}:
                row.health_status = "unavailable"
                row.health_status_reason = (
                    f"Reconciled at startup — container status={status}"
                )
                row.last_health_check = datetime.utcnow()

        if stats["rows_updated"] or stats["orphan_containers_removed"]:
            db.commit()
        return stats


def startup_reconcile(db: Session) -> None:
    from models import ASRInstance

    try:
        runtime = get_container_runtime()
    except Exception as e:
        logger.warning("Whisper startup_reconcile: runtime unavailable: %s", e)
        return
    manager = WhisperContainerManager()

    try:
        stats = manager.reconcile_managed_containers(db, remove_orphans=True)
        if stats.get("orphan_containers_removed"):
            logger.warning(
                "Whisper startup_reconcile removed %d orphan ASR container(s)",
                stats["orphan_containers_removed"],
            )
    except Exception as e:
        logger.warning("Whisper startup_reconcile managed-container pass failed: %s", e)
        try:
            db.rollback()
        except Exception:
            pass

    stale_deprovisioned_rows = db.query(ASRInstance).filter(
        ASRInstance.is_auto_provisioned == True,
        ASRInstance.is_active == False,
        ASRInstance.container_name.is_(None),
        ASRInstance.container_status == "none",
        ASRInstance.health_status == "healthy",
    ).all()
    stale_deprovisioned_rows = [
        instance
        for instance in stale_deprovisioned_rows
        if getattr(instance, "is_auto_provisioned", False) is True
        and getattr(instance, "is_active", True) is False
        and not getattr(instance, "container_name", None)
        and getattr(instance, "container_status", None) == "none"
        and getattr(instance, "health_status", None) == "healthy"
    ]
    for instance in stale_deprovisioned_rows:
        instance.health_status = "unknown"
        instance.health_status_reason = "Deprovisioned"
        instance.last_health_check = datetime.utcnow()
    if stale_deprovisioned_rows:
        db.commit()

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
