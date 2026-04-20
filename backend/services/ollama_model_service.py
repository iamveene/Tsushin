"""
Ollama Model Service — pull/list/delete helpers for auto-provisioned Ollama containers.

Pulls run in background threads (Ollama pulls are long-lived and streaming).
Job state is held in a module-level dict protected by a threading.Lock — safe
because the backend runs `uvicorn --workers 1`.

Each background thread opens its OWN DB session; we never share a request-bound
session across threads.
"""

import json
import logging
import threading
import time
import uuid
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


# Module-level job registry. Keys are uuid4().hex strings, values are dicts:
#   {
#     "status": "pulling" | "done" | "error",
#     "percent": 0..100,
#     "bytes_downloaded": int,
#     "bytes_total": int,
#     "error": Optional[str],
#     "model": str,
#     "instance_id": int,
#     "tenant_id": str,
#     "created_at": float (unix ts),
#     "updated_at": float (unix ts),
#   }
_pull_jobs: Dict[str, dict] = {}
_jobs_lock = threading.Lock()
JOB_TTL_SECONDS = 3600  # 1 hour


def _evict_expired_locked() -> None:
    """Called with _jobs_lock already held. Drop jobs older than JOB_TTL_SECONDS."""
    now = time.time()
    stale = [
        jid
        for jid, state in _pull_jobs.items()
        if (now - state.get("updated_at", state.get("created_at", now)))
        > JOB_TTL_SECONDS
    ]
    for jid in stale:
        _pull_jobs.pop(jid, None)


def _update_job(job_id: str, **updates) -> None:
    """Atomically merge updates into the job state dict."""
    with _jobs_lock:
        state = _pull_jobs.get(job_id)
        if state is None:
            return
        state.update(updates)
        state["updated_at"] = time.time()


def _get_session_factory():
    """Resolve the SessionLocal factory lazily so this module is importable early."""
    from db import get_global_engine
    from sqlalchemy.orm import sessionmaker

    engine = get_global_engine()
    if engine is None:
        raise RuntimeError(
            "DB engine not initialized; cannot open session for Ollama model pull"
        )
    return sessionmaker(bind=engine)


class OllamaModelService:
    """Static helpers for Ollama model management on auto-provisioned containers."""

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    @staticmethod
    def start_pull(
        instance_id: int, tenant_id: str, model_name: str, db
    ) -> str:
        """
        Kick off a background pull. Returns a job_id the caller can poll.
        Raises ValueError if the instance is not runnable.
        """
        from models import ProviderInstance

        if not model_name or not model_name.strip():
            raise ValueError("Model name is required")
        model_name = model_name.strip()

        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == "ollama",
            ProviderInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Ollama instance {instance_id} not found")
        if instance.container_status != "running":
            raise ValueError(
                f"Container not running (status={instance.container_status}); "
                f"start the container before pulling a model"
            )
        if not instance.base_url:
            raise ValueError("Instance has no base_url; cannot pull model")

        job_id = uuid.uuid4().hex
        now = time.time()
        with _jobs_lock:
            _evict_expired_locked()
            _pull_jobs[job_id] = {
                "status": "pulling",
                "percent": 0,
                "bytes_downloaded": 0,
                "bytes_total": 0,
                "error": None,
                "model": model_name,
                "instance_id": instance_id,
                "tenant_id": tenant_id,
                "created_at": now,
                "updated_at": now,
            }

        # Pass ONLY primitives across the thread boundary. No ORM objects,
        # no DB sessions — the worker opens its own.
        thread = threading.Thread(
            target=_do_pull,
            args=(
                job_id,
                instance.container_port,
                instance.base_url,
                instance.tenant_id,
                instance.id,
                model_name,
            ),
            daemon=True,
            name=f"ollama-pull-{job_id[:8]}",
        )
        thread.start()
        logger.info(
            f"Started Ollama model pull: job={job_id} model={model_name} "
            f"instance={instance_id} tenant={tenant_id}"
        )
        return job_id

    @staticmethod
    def get_pull_status(job_id: str) -> Optional[dict]:
        """Return the current pull state, or None if unknown/expired."""
        with _jobs_lock:
            _evict_expired_locked()
            state = _pull_jobs.get(job_id)
            if state is None:
                return None
            # Return a shallow copy so the caller can't mutate our state dict.
            return dict(state)

    # ------------------------------------------------------------------
    # List / delete
    # ------------------------------------------------------------------

    @staticmethod
    def list_models(instance_id: int, tenant_id: str, db) -> List[str]:
        """
        Return the list of models that belong to this tenant's Ollama instance.
        Prefers the live `/api/tags` result (merged with the DB cache) so the
        UI always reflects reality.
        """
        from models import ProviderInstance

        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == "ollama",
            ProviderInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Ollama instance {instance_id} not found")

        cached: List[str] = list(instance.pulled_models or [])

        if not instance.base_url or instance.container_status != "running":
            return cached

        try:
            resp = requests.get(f"{instance.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                body = resp.json() or {}
                live = [
                    m.get("name")
                    for m in body.get("models", [])
                    if isinstance(m, dict) and m.get("name")
                ]
                merged = sorted({*cached, *live})
                # Persist live view back into DB cache.
                if merged != cached:
                    instance.pulled_models = merged
                    db.commit()
                return merged
        except Exception as e:
            logger.debug(
                f"Ollama list_models live query failed for instance "
                f"{instance_id}: {e}"
            )
        return cached

    @staticmethod
    def delete_model(
        instance_id: int, tenant_id: str, model_name: str, db
    ) -> dict:
        """
        Delete a model from the Ollama container via `DELETE /api/delete`
        and remove it from the cached `pulled_models` list.
        """
        from models import ProviderInstance

        if not model_name or not model_name.strip():
            raise ValueError("Model name is required")
        model_name = model_name.strip()

        instance = db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == "ollama",
            ProviderInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError(f"Ollama instance {instance_id} not found")
        if not instance.base_url:
            raise ValueError("Instance has no base_url; cannot delete model")

        # Ollama uses DELETE /api/delete with a JSON body.
        try:
            resp = requests.delete(
                f"{instance.base_url}/api/delete",
                json={"name": model_name},
                timeout=30,
            )
        except Exception as e:
            raise RuntimeError(f"Failed to reach Ollama: {e}")

        if resp.status_code not in (200, 204, 404):
            raise RuntimeError(
                f"Ollama returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        # Remove from DB cache regardless — if it's gone on Ollama, our cache
        # should reflect that.
        current = list(instance.pulled_models or [])
        if model_name in current:
            current.remove(model_name)
            instance.pulled_models = current
            db.commit()

        return {
            "deleted": model_name,
            "status_code": resp.status_code,
            "pulled_models": current,
        }


# ----------------------------------------------------------------------
# Background worker
# ----------------------------------------------------------------------


def _do_pull(
    job_id: str,
    container_port: Optional[int],
    base_url: str,
    tenant_id: str,
    instance_id: int,
    model_name: str,
) -> None:
    """
    Stream `/api/pull` and update the in-memory job state. Opens its own DB
    session; never shares the request-scoped session.
    """
    db = None
    try:
        try:
            SessionLocal = _get_session_factory()
            db = SessionLocal()
        except Exception as e:
            # Can't even open a DB session — record the error in memory only.
            logger.error(
                f"[pull {job_id}] Could not open DB session for pull finalize: {e}"
            )
            _update_job(job_id, status="error", error=f"DB init failed: {e}")
            return

        # PEER REVIEW B-M2: separate connect/read timeouts. Connect must be
        # fast; the read can take a while as tags/blobs download.
        try:
            resp = requests.post(
                f"{base_url}/api/pull",
                json={"name": model_name, "stream": True},
                stream=True,
                timeout=(30, 300),
            )
        except Exception as e:
            logger.error(f"[pull {job_id}] HTTP error: {e}")
            _update_job(job_id, status="error", error=str(e))
            return

        if resp.status_code != 200:
            msg = f"Ollama HTTP {resp.status_code}: {resp.text[:200]}"
            logger.error(f"[pull {job_id}] {msg}")
            _update_job(job_id, status="error", error=msg)
            return

        success_seen = False
        last_bytes_downloaded = 0
        last_bytes_total = 0

        try:
            for raw_line in resp.iter_lines():
                if not raw_line:
                    continue
                try:
                    line = (
                        raw_line.decode("utf-8", errors="replace")
                        if isinstance(raw_line, (bytes, bytearray))
                        else str(raw_line)
                    )
                    event = json.loads(line)
                except Exception as parse_err:
                    logger.debug(
                        f"[pull {job_id}] non-JSON line: {parse_err}"
                    )
                    continue

                status = event.get("status") or ""
                completed = int(event.get("completed") or 0)
                total = int(event.get("total") or 0)

                if total > 0:
                    last_bytes_total = total
                if completed > 0:
                    last_bytes_downloaded = completed

                percent = 0
                if last_bytes_total > 0:
                    try:
                        percent = int(
                            (last_bytes_downloaded / last_bytes_total) * 100
                        )
                        if percent > 100:
                            percent = 100
                    except Exception:
                        percent = 0

                if status == "success":
                    success_seen = True

                if event.get("error"):
                    err_msg = str(event.get("error"))
                    logger.error(f"[pull {job_id}] Ollama error event: {err_msg}")
                    _update_job(job_id, status="error", error=err_msg)
                    return

                _update_job(
                    job_id,
                    status="pulling",
                    percent=percent,
                    bytes_downloaded=last_bytes_downloaded,
                    bytes_total=last_bytes_total,
                )
        except Exception as stream_err:
            logger.error(f"[pull {job_id}] stream error: {stream_err}")
            _update_job(job_id, status="error", error=str(stream_err))
            return

        if not success_seen:
            _update_job(
                job_id,
                status="error",
                error="Ollama pull stream ended without success event",
            )
            return

        # Persist the model in pulled_models, tenant-scoped.
        try:
            from models import ProviderInstance
            inst = db.query(ProviderInstance).filter(
                ProviderInstance.id == instance_id,
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.vendor == "ollama",
            ).first()
            if inst is not None:
                current = list(inst.pulled_models or [])
                if model_name not in current:
                    current.append(model_name)
                    inst.pulled_models = current
                    db.commit()
        except Exception as db_err:
            logger.warning(
                f"[pull {job_id}] could not persist pulled model "
                f"(model is pulled on Ollama, DB cache is stale): {db_err}"
            )

        _update_job(
            job_id,
            status="done",
            percent=100,
            bytes_downloaded=last_bytes_downloaded or last_bytes_total,
            bytes_total=last_bytes_total,
            error=None,
        )
        logger.info(
            f"[pull {job_id}] completed: model={model_name} "
            f"instance={instance_id} tenant={tenant_id}"
        )

    except Exception as outer:
        logger.error(f"[pull {job_id}] unexpected error: {outer}", exc_info=True)
        _update_job(job_id, status="error", error=str(outer))
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass
