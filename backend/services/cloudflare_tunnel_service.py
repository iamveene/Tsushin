"""Cloudflare Tunnel subprocess supervisor — v0.6.0 Remote Access.

Ports the proven state-machine/lifecycle pattern from the sibling `scheduler`
project (`scheduler/backend/services/cloudflare_tunnel.py`) into tsushin, with
five enterprise-grade enhancements:

1. Config is loaded from the DB on every start() call (NOT from settings/.env).
   Tunnel token is decrypted via TokenEncryption using a dedicated Fernet key
   managed through encryption_key_service.
2. A bounded supervisor task restarts cloudflared after a crash: 3 attempts
   with 5/15/30 second backoff, then surfaces the error to the admin UI.
3. Readiness is confirmed via cloudflared's Prometheus metrics endpoint
   (127.0.0.1:20241) — specifically the `cloudflared_tunnel_ha_connections`
   gauge. Named mode no longer trusts a sleep(1) to decide "running".
4. Cross-restart visibility: last_started_at / last_stopped_at / last_error
   are persisted to the remote_access_config row.
5. Optimistic concurrency + audit emission are handled at the REST layer
   (routes_remote_access.py), not in this service.

Concurrency model:
    - Single `asyncio.Lock` protects state transitions. Tsushin runs with
      --workers 1 (verified in backend/Dockerfile), so one lock suffices.
      Multi-worker deployments would additionally need a PG advisory lock
      around config writes AND a leader-election mechanism for subprocess
      ownership.

Target URL default: the stack-scoped Caddy proxy (`http://{stack}-proxy:80`).
Never use the frontend container directly or localhost from inside the backend
container.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shutil
from contextlib import suppress
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Callable, Literal, Optional, cast

import httpx
from sqlalchemy.orm import Session

from models import get_remote_access_proxy_target_url
from services.remote_access_config_service import normalize_remote_access_target_url

logger = logging.getLogger(__name__)


# ---------- Constants ----------

TRYCLOUDFLARE_RE = re.compile(
    r"https://[^\s'\"<>]*trycloudflare\.com[^\s'\"<>]*",
    re.IGNORECASE,
)

# Scrubs `--token <value>` and `token=<value>` patterns from log lines before
# we emit them. cloudflared does not currently echo the token on stdout, but
# this is defense-in-depth in case that changes in a future release.
TOKEN_SCRUB_RE = re.compile(
    r"(--token|token[=:])\s*\S+",
    re.IGNORECASE,
)


def _scrub_token(text: str) -> str:
    return TOKEN_SCRUB_RE.sub(r"\1 [REDACTED]", text)

METRICS_BIND = "127.0.0.1:20241"
METRICS_URL = f"http://{METRICS_BIND}/metrics"
SUPERVISOR_BACKOFFS = (5, 15, 30)  # seconds between restart attempts
SUPERVISOR_MAX_ATTEMPTS = len(SUPERVISOR_BACKOFFS)

TunnelModeName = Literal["quick", "named"]
TunnelStateName = Literal[
    "stopped", "starting", "verifying", "running", "stopping",
    "crashed", "error", "unavailable",
]


# ---------- Errors ----------

class TunnelConfigurationError(RuntimeError):
    """Raised when the stored tunnel configuration is incomplete or invalid."""


# ---------- Data types ----------

@dataclass(slots=True)
class _LoadedConfig:
    """In-memory snapshot of a RemoteAccessConfig row with decrypted token."""
    enabled: bool
    mode: TunnelModeName
    autostart: bool
    protocol: str
    tunnel_token: Optional[str]         # decrypted plaintext — NEVER persist or log
    tunnel_hostname: Optional[str]
    tunnel_dns_target: Optional[str]
    target_url: str


@dataclass(slots=True)
class TunnelSnapshot:
    state: TunnelStateName
    mode: Optional[TunnelModeName]
    public_url: Optional[str]
    hostname: Optional[str]
    target_url: Optional[str]
    pid: Optional[int]
    started_at: Optional[datetime]
    updated_at: datetime
    last_error: Optional[str]
    restart_attempts: int
    supervisor_active: bool
    binary_available: bool
    cloudflared_path: Optional[str]
    message: Optional[str] = None


# ---------- Service ----------

class CloudflareTunnelService:
    """Lifecycle manager for a single cloudflared subprocess.

    All state transitions run under `self._lock`. The supervisor task never
    holds the lock across the blocking `process.wait()` — it only takes the
    lock during the transition windows.
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._lock = asyncio.Lock()
        self._process: Optional[asyncio.subprocess.Process] = None
        self._reader_task: Optional[asyncio.Task] = None
        self._supervisor_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._restart_attempts = 0

        self._cloudflared_path = self._resolve_cloudflared_path()

        # In-memory state
        now = datetime.now(timezone.utc)
        self._state: TunnelSnapshot = TunnelSnapshot(
            state="stopped" if self._cloudflared_path else "unavailable",
            mode=None,
            public_url=None,
            hostname=None,
            target_url=None,
            pid=None,
            started_at=None,
            updated_at=now,
            last_error=None,
            restart_attempts=0,
            supervisor_active=False,
            binary_available=self._cloudflared_path is not None,
            cloudflared_path=self._cloudflared_path,
            message=(
                "Cloudflare tunnel has not been started"
                if self._cloudflared_path
                else "cloudflared is not installed or not on PATH"
            ),
        )

    # ----- Discovery -----

    @staticmethod
    def _resolve_cloudflared_path() -> Optional[str]:
        for candidate in ("/usr/local/bin/cloudflared", "cloudflared"):
            found = shutil.which(candidate)
            if found:
                return found
        return None

    # ----- DB config loading -----

    def _load_config(self) -> _LoadedConfig:
        """Read the current RemoteAccessConfig row and decrypt the token.

        Opens and closes its own DB session. Must be called without holding
        self._lock because it performs IO.
        """
        from models import RemoteAccessConfig
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_remote_access_encryption_key

        db = self._session_factory()
        try:
            row = db.query(RemoteAccessConfig).filter(
                RemoteAccessConfig.id == 1
            ).first()
            if row is None:
                row = RemoteAccessConfig(id=1)
                db.add(row)
                db.commit()
                db.refresh(row)

            token_plain: Optional[str] = None
            if row.tunnel_token_encrypted:
                key = get_remote_access_encryption_key(db)
                if not key:
                    raise TunnelConfigurationError(
                        "Remote access encryption key is unavailable"
                    )
                try:
                    encryption = TokenEncryption(key.encode())
                    token_plain = encryption.decrypt(
                        row.tunnel_token_encrypted,
                        "remote_access_system",
                    )
                except Exception as exc:
                    raise TunnelConfigurationError(
                        "Token decryption failed (key rotated or data corrupted)"
                    ) from exc

            return _LoadedConfig(
                enabled=bool(row.enabled),
                mode=cast(TunnelModeName, row.mode or "quick"),
                autostart=bool(row.autostart),
                protocol=(row.protocol or "auto").lower(),
                tunnel_token=token_plain,
                tunnel_hostname=(row.tunnel_hostname or None),
                tunnel_dns_target=(row.tunnel_dns_target or None),
                target_url=normalize_remote_access_target_url(row.target_url),
            )
        finally:
            db.close()

    async def _probe_proxy_target(self, target_url: str, timeout: float = 5.0) -> bool:
        """Check that the stack proxy/Caddy layer is reachable before launch."""
        probe_url = f"{target_url.rstrip('/')}/api/health"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(probe_url)
                return response.status_code == 200
        except Exception as exc:
            logger.info("Remote Access proxy probe failed for %s: %s", probe_url, exc)
            return False

    def _persist(
        self,
        *,
        last_started_at: Optional[datetime] = None,
        last_stopped_at: Optional[datetime] = None,
        last_error: Optional[str] = ...,  # type: ignore[assignment]
    ) -> None:
        """Write cross-restart metadata to the DB. Use ... to leave unchanged."""
        from models import RemoteAccessConfig

        db = self._session_factory()
        try:
            row = db.query(RemoteAccessConfig).filter(
                RemoteAccessConfig.id == 1
            ).first()
            if row is None:
                return
            if last_started_at is not None:
                row.last_started_at = last_started_at
            if last_stopped_at is not None:
                row.last_stopped_at = last_stopped_at
            if last_error is not ...:  # sentinel
                row.last_error = last_error  # type: ignore[assignment]
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("Failed to persist tunnel metadata: %s", exc)
        finally:
            db.close()

    # ----- Public API -----

    async def get_snapshot(self) -> dict:
        async with self._lock:
            return self._snapshot_dict()

    async def should_autostart(self) -> bool:
        """Return True if the config says autostart is on and the tunnel is enabled."""
        try:
            loaded = await asyncio.get_running_loop().run_in_executor(
                None, self._load_config
            )
        except Exception as exc:
            logger.info("Remote access autostart skipped: %s", exc)
            return False
        return bool(loaded.enabled and loaded.autostart and self._cloudflared_path)

    async def start_autostart(self) -> None:
        """Fire-and-forget autostart used from the FastAPI lifespan."""
        try:
            loaded = await asyncio.get_running_loop().run_in_executor(
                None, self._load_config
            )
            await self.start(mode=loaded.mode)
            logger.info("Cloudflare tunnel autostarted (%s)", loaded.mode)
        except Exception as exc:
            logger.warning("Cloudflare tunnel autostart failed: %s", exc)

    async def start(
        self,
        *,
        mode: Optional[TunnelModeName] = None,
        _supervised: bool = False,
    ) -> dict:
        """Start the tunnel. Reloads config from DB every call.

        Args:
            mode: override the stored mode for this run (doesn't persist).
                  None = use the DB value.
            _supervised: internal flag — set to True when called from the
                         supervisor so we don't recursively spawn supervisors.
        """
        if self._cloudflared_path is None:
            raise TunnelConfigurationError(
                "cloudflared binary not found in the backend container"
            )

        loaded = await asyncio.get_running_loop().run_in_executor(
            None, self._load_config
        )

        requested_mode: TunnelModeName = mode or loaded.mode
        if requested_mode not in {"quick", "named"}:
            raise TunnelConfigurationError(f"Unsupported tunnel mode: {mode}")
        if requested_mode == "named":
            if not loaded.tunnel_token or not loaded.tunnel_hostname:
                raise TunnelConfigurationError(
                    "Named tunnel requires tunnel_token and tunnel_hostname"
                )

        # If already running in the same mode, no-op
        async with self._lock:
            running = self._process is not None and self._process.returncode is None
            if running and self._state.mode == requested_mode:
                return self._snapshot_dict()

        expected_target_url = get_remote_access_proxy_target_url()
        loaded.target_url = normalize_remote_access_target_url(loaded.target_url)
        if loaded.target_url != expected_target_url:
            raise TunnelConfigurationError(
                "Remote Access requires the stack-scoped Caddy proxy target "
                f"{expected_target_url}; current target is {loaded.target_url}."
            )
        if not await self._probe_proxy_target(expected_target_url, timeout=5.0):
            raise TunnelConfigurationError(
                "Remote Access requires the Caddy proxy layer to be running "
                f"at {expected_target_url} before it can start."
            )

        # Stop any existing process outside the lock (stop() takes the lock itself)
        if self._process is not None and self._process.returncode is None:
            await self.stop()

        command = [
            self._cloudflared_path,
            "tunnel",
            "--no-autoupdate",
            "--metrics",
            METRICS_BIND,
        ]
        if loaded.protocol in {"http2", "quic", "auto"}:
            command.extend(["--protocol", loaded.protocol])
        if requested_mode == "quick":
            command.extend(["--url", loaded.target_url])
        else:
            command.extend(["run", "--token", loaded.tunnel_token or ""])

        async with self._lock:
            if not _supervised:
                self._restart_attempts = 0
            now = datetime.now(timezone.utc)
            self._state = TunnelSnapshot(
                state="starting",
                mode=requested_mode,
                public_url=None,
                hostname=loaded.tunnel_hostname if requested_mode == "named" else None,
                target_url=loaded.target_url,
                pid=None,
                started_at=now,
                updated_at=now,
                last_error=None,
                restart_attempts=self._restart_attempts,
                supervisor_active=self._supervisor_task is not None
                and not self._supervisor_task.done(),
                binary_available=True,
                cloudflared_path=self._cloudflared_path,
                message=(
                    "Starting Cloudflare quick tunnel"
                    if requested_mode == "quick"
                    else "Starting Cloudflare named tunnel"
                ),
            )

            self._process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            self._reader_task = asyncio.create_task(
                self._consume_output(mode=requested_mode)
            )
            self._state.pid = self._process.pid

        # Readiness probing is mode-specific
        if requested_mode == "quick":
            await self._await_quick_ready(timeout=30.0)
            # Soft metrics sanity check — don't block on it
            try:
                await self._probe_metrics(timeout=5.0)
            except Exception as exc:
                logger.debug("Metrics probe (quick, soft) failed: %s", exc)
        else:  # named
            ready = await self._probe_metrics(timeout=15.0)
            if not ready:
                self._persist(last_error="Named tunnel readiness probe timed out")
                await self.stop()
                raise RuntimeError(
                    "Named tunnel failed readiness probe "
                    "(no HA connections in 15s)"
                )
            # BUG-589: Even with HA connections up, the named hostname can
            # still return Cloudflare 502 if ingress/target is broken.
            # Verify end-to-end before declaring "running".
            hostname = loaded.tunnel_hostname
            public_url = f"https://{hostname}" if hostname else None
            if hostname:
                async with self._lock:
                    self._state.state = "verifying"
                    self._state.public_url = public_url
                    self._state.message = (
                        f"Verifying public hostname {hostname} is serving "
                        "the app"
                    )
                    self._state.updated_at = datetime.now(timezone.utc)
                public_ok, last_status = await self._probe_public_url(
                    hostname, timeout=30.0
                )
                if not public_ok:
                    status_hint = (
                        f" (last HTTP status: {last_status})"
                        if last_status is not None
                        else ""
                    )
                    err_msg = (
                        f"Named tunnel started but public hostname "
                        f"{hostname} is not serving the app{status_hint}"
                    )
                    self._persist(last_error=err_msg)
                    await self.stop()
                    raise RuntimeError(err_msg)
            async with self._lock:
                self._state.state = "running"
                self._state.public_url = public_url
                self._state.message = "Cloudflare named tunnel is running"
                self._state.updated_at = datetime.now(timezone.utc)

        self._persist(
            last_started_at=datetime.now(timezone.utc),
            last_error=None,
        )

        # Spawn supervisor if autostart is on and we weren't called from one
        if loaded.autostart and not _supervised:
            if self._supervisor_task is None or self._supervisor_task.done():
                self._supervisor_task = asyncio.create_task(self._supervise())
                async with self._lock:
                    self._state.supervisor_active = True

        async with self._lock:
            return self._snapshot_dict()

    async def stop(self) -> dict:
        """Stop the tunnel cleanly: cancel supervisor, SIGTERM→10s→SIGKILL→5s."""
        async with self._lock:
            self._stopping = True
            process = self._process
            reader_task = self._reader_task
            supervisor_task = self._supervisor_task

            if process is None or process.returncode is not None:
                # Already stopped
                self._process = None
                self._reader_task = None
                now = datetime.now(timezone.utc)
                self._state = TunnelSnapshot(
                    state="stopped" if self._cloudflared_path else "unavailable",
                    mode=None,
                    public_url=None,
                    hostname=None,
                    target_url=None,
                    pid=None,
                    started_at=None,
                    updated_at=now,
                    last_error=self._state.last_error,
                    restart_attempts=0,
                    supervisor_active=False,
                    binary_available=self._cloudflared_path is not None,
                    cloudflared_path=self._cloudflared_path,
                    message="Cloudflare tunnel is stopped",
                )
                self._stopping = False
                return self._snapshot_dict()

            self._state.state = "stopping"
            self._state.message = "Stopping Cloudflare tunnel"
            self._state.updated_at = datetime.now(timezone.utc)

            with suppress(ProcessLookupError):
                process.terminate()

        # Cancel supervisor outside the lock
        if supervisor_task is not None and not supervisor_task.done():
            supervisor_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await supervisor_task

        # Wait for graceful exit, then SIGKILL if needed
        proc = cast(asyncio.subprocess.Process, process)
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(proc.wait(), timeout=10)
        if proc.returncode is None:
            with suppress(ProcessLookupError):
                proc.kill()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(proc.wait(), timeout=5)

        if reader_task is not None and not reader_task.done():
            reader_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await reader_task

        async with self._lock:
            self._process = None
            self._reader_task = None
            self._supervisor_task = None
            self._stopping = False
            now = datetime.now(timezone.utc)
            self._state = TunnelSnapshot(
                state="stopped" if self._cloudflared_path else "unavailable",
                mode=None,
                public_url=None,
                hostname=None,
                target_url=None,
                pid=None,
                started_at=None,
                updated_at=now,
                last_error=self._state.last_error,
                restart_attempts=0,
                supervisor_active=False,
                binary_available=self._cloudflared_path is not None,
                cloudflared_path=self._cloudflared_path,
                message="Cloudflare tunnel is stopped",
            )

        self._persist(last_stopped_at=datetime.now(timezone.utc))
        async with self._lock:
            return self._snapshot_dict()

    async def reload_config(self) -> dict:
        """Called by the config PUT endpoint when the tunnel is running.

        Stops the current process and starts it again with the new settings.
        Returns the new snapshot.
        """
        was_running = False
        async with self._lock:
            was_running = (
                self._process is not None and self._process.returncode is None
            )
            current_mode = self._state.mode
        if not was_running:
            async with self._lock:
                return self._snapshot_dict()
        await self.stop()
        return await self.start(mode=current_mode)

    async def shutdown(self) -> None:
        """Called from the FastAPI lifespan shutdown hook. Never raises."""
        with suppress(Exception):
            await self.stop()

    # ----- Output consumer -----

    async def _consume_output(self, *, mode: TunnelModeName) -> None:
        """Read cloudflared's stdout until it closes.

        For quick tunnels we scan each line for the trycloudflare.com URL; once
        we find it, we update self._state.public_url and keep draining so the
        log never backs up.
        """
        if self._process is None or self._process.stdout is None:
            return

        stdout = self._process.stdout
        found_public_url = False

        try:
            while True:
                line = await stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    # Defense-in-depth: scrub any potential token exposure
                    # before forwarding cloudflared's stdout to our logger.
                    logger.info("cloudflared: %s", _scrub_token(text))

                if mode == "quick" and not found_public_url:
                    match = TRYCLOUDFLARE_RE.search(text)
                    if match:
                        public_url = match.group(0).rstrip(".,)")
                        async with self._lock:
                            self._state.public_url = public_url
                            self._state.state = "running"
                            self._state.message = "Cloudflare quick tunnel is running"
                            self._state.updated_at = datetime.now(timezone.utc)
                        found_public_url = True

            # Reader ended — process has exited
            return_code = await self._process.wait()
            async with self._lock:
                if self._stopping:
                    return
                # Process crashed unexpectedly
                self._state.state = "crashed"
                self._state.pid = None
                self._state.updated_at = datetime.now(timezone.utc)
                error_msg = (
                    f"cloudflared exited unexpectedly (code {return_code})"
                )
                self._state.last_error = error_msg
                self._state.message = error_msg
            self._persist(last_error=error_msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("cloudflared output reader error: %s", exc)

    async def _await_quick_ready(self, timeout: float) -> None:
        """Block until the quick-tunnel reader populates public_url or time runs out."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            async with self._lock:
                if self._state.public_url:
                    return
                if self._state.state in {"crashed", "error", "unavailable"}:
                    raise RuntimeError(
                        self._state.last_error or "Quick tunnel failed"
                    )
                proc = self._process
            if proc is None or proc.returncode is not None:
                raise RuntimeError("Quick tunnel process exited before URL was published")
            if asyncio.get_running_loop().time() >= deadline:
                self._persist(last_error="Quick tunnel timed out waiting for URL")
                await self.stop()
                raise RuntimeError("Quick tunnel timed out waiting for URL")
            await asyncio.sleep(0.2)

    async def _probe_metrics(self, timeout: float) -> bool:
        """Poll cloudflared's metrics endpoint until HA connections > 0 or timeout."""
        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    resp = await client.get(METRICS_URL)
                    if resp.status_code == 200:
                        for line in resp.text.splitlines():
                            if line.startswith("#"):
                                continue
                            if "cloudflared_tunnel_ha_connections" in line:
                                parts = line.rsplit(" ", 1)
                                if len(parts) == 2:
                                    try:
                                        value = float(parts[1])
                                        if value > 0:
                                            return True
                                    except ValueError:
                                        pass
            except Exception:
                pass
            await asyncio.sleep(0.25)
        return False

    async def _probe_public_url(
        self, hostname: str, timeout: float = 30.0
    ) -> tuple[bool, Optional[int]]:
        # BUG-589: `_probe_metrics()` only confirms the local cloudflared has a
        # connection to Cloudflare's edge. A misconfigured ingress or a dead
        # target still surfaces as a 5xx (typically 502) on the public URL.
        # We must verify the public hostname actually serves the app before
        # declaring the tunnel "running".
        probe_url = f"https://{hostname.strip('/')}/api/health"
        deadline = asyncio.get_running_loop().time() + timeout
        last_status: Optional[int] = None
        while asyncio.get_running_loop().time() < deadline:
            try:
                async with httpx.AsyncClient(
                    timeout=5.0, follow_redirects=True
                ) as client:
                    resp = await client.get(probe_url)
                    last_status = resp.status_code
                    if 200 <= resp.status_code < 500:
                        return True, resp.status_code
            except Exception as exc:
                logger.debug(
                    "Public URL probe error for %s: %s", probe_url, exc
                )
            await asyncio.sleep(2.0)
        return False, last_status

    # ----- Supervisor -----

    async def _supervise(self) -> None:
        """Bounded auto-restart loop. Runs as a background task.

        Triggered when the subprocess exits unexpectedly. Up to 3 attempts
        with 5/15/30 second backoff, then surrenders and sets state=error.
        Always reloads config fresh before each attempt.
        """
        try:
            while True:
                # Wait until the current process exits
                async with self._lock:
                    proc = self._process
                if proc is None:
                    return
                try:
                    await proc.wait()
                except asyncio.CancelledError:
                    return

                supervisor_gave_up_msg: Optional[str] = None
                async with self._lock:
                    if self._stopping:
                        return
                    self._restart_attempts += 1
                    if self._restart_attempts > SUPERVISOR_MAX_ATTEMPTS:
                        supervisor_gave_up_msg = (
                            f"Supervisor gave up after {SUPERVISOR_MAX_ATTEMPTS} restart attempts"
                        )
                        self._state.state = "error"
                        self._state.last_error = supervisor_gave_up_msg
                        self._state.supervisor_active = False
                        self._state.updated_at = datetime.now(timezone.utc)
                        attempt_num = 0
                    else:
                        attempt_num = self._restart_attempts

                # Persist OUTSIDE the lock — synchronous DB I/O must not
                # block the event loop while holding self._lock, otherwise
                # concurrent callers (e.g. the 5s status poller) stall.
                if supervisor_gave_up_msg is not None:
                    self._persist(last_error=supervisor_gave_up_msg)
                    return

                backoff = SUPERVISOR_BACKOFFS[attempt_num - 1]
                logger.warning(
                    "cloudflared crashed; supervisor restarting in %ss (attempt %s/%s)",
                    backoff, attempt_num, SUPERVISOR_MAX_ATTEMPTS,
                )
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return

                try:
                    await self.start(mode=None, _supervised=True)
                    async with self._lock:
                        self._restart_attempts = 0
                        self._state.supervisor_active = True
                except Exception as exc:
                    logger.warning("Supervisor restart attempt failed: %s", exc)
                    # Loop back and wait_for next process exit / retry
        finally:
            async with self._lock:
                self._state.supervisor_active = False

    # ----- Snapshot serialization -----

    def _snapshot_dict(self) -> dict:
        snapshot = asdict(self._state)
        # Ensure ISO timestamps in the API response
        for field_name in ("started_at", "updated_at"):
            value = snapshot.get(field_name)
            if isinstance(value, datetime):
                snapshot[field_name] = value.isoformat()
        return snapshot


# ---------- Singleton ----------

_service: Optional[CloudflareTunnelService] = None


def get_cloudflare_tunnel_service(
    session_factory: Optional[Callable[[], Session]] = None,
) -> CloudflareTunnelService:
    """Return the process-wide singleton.

    Pass ``session_factory`` on the very first call (from the FastAPI lifespan).
    Subsequent calls (e.g. from REST handlers) may omit it.
    """
    global _service
    if _service is None:
        if session_factory is None:
            raise RuntimeError(
                "CloudflareTunnelService must be initialized with a session_factory"
            )
        _service = CloudflareTunnelService(session_factory)
    return _service
