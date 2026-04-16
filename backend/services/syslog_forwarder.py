"""
Syslog Forwarder Worker
Consumes audit events from an in-memory queue and forwards to tenant syslog servers.
Daemon thread with per-tenant batching, config caching, and circuit breaker isolation.
"""

import json
import logging
import queue
import threading
import time
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# Module-level state
_worker_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_event_queue: Optional[queue.Queue] = None
_engine = None
_config_cache: Dict[str, dict] = {}
_cache_lock = threading.Lock()
_last_cache_refresh: float = 0


def enqueue_event(tenant_id: str, event_data: dict):
    """
    Non-blocking enqueue of an audit event for syslog forwarding.
    Called from log_tenant_event() after DB commit.
    Fire-and-forget: drops if queue is full.
    """
    if _event_queue is None:
        return
    try:
        _event_queue.put_nowait((tenant_id, event_data))
    except queue.Full:
        logger.warning(f"[SyslogForwarder] Queue full, dropping event for tenant {tenant_id}")


def invalidate_config_cache(tenant_id: str):
    """Invalidate cached config for a tenant (called when config is updated)."""
    global _last_cache_refresh
    with _cache_lock:
        _config_cache.pop(tenant_id, None)
        _last_cache_refresh = 0  # Force full refresh on next cycle


def _refresh_config_cache(SessionFactory):
    """Refresh the config cache from database."""
    global _last_cache_refresh, _config_cache
    from models_rbac import TenantSyslogConfig

    session = SessionFactory()
    try:
        configs = session.query(TenantSyslogConfig).filter(
            TenantSyslogConfig.enabled == True
        ).all()

        new_cache = {}
        for c in configs:
            categories = None
            if c.event_categories:
                try:
                    categories = json.loads(c.event_categories)
                except json.JSONDecodeError:
                    categories = None

            new_cache[c.tenant_id] = {
                "host": c.host,
                "port": c.port or 514,
                "protocol": c.protocol or "tcp",
                "facility": c.facility or 1,
                "app_name": c.app_name or "tsushin",
                "tls_verify": c.tls_verify if c.tls_verify is not None else True,
                "has_tls_certs": bool(c.tls_ca_cert_encrypted),
                "categories": categories,
                "config_id": c.id,
            }

        with _cache_lock:
            _config_cache = new_cache
            _last_cache_refresh = time.time()
    except Exception as e:
        logger.error(f"[SyslogForwarder] Config refresh failed: {e}")
    finally:
        session.close()


def _decrypt_tls_certs(SessionFactory, tenant_id: str) -> Optional[dict]:
    """Decrypt TLS certificates for a tenant."""
    from models_rbac import TenantSyslogConfig

    session = SessionFactory()
    try:
        config = session.query(TenantSyslogConfig).filter(
            TenantSyslogConfig.tenant_id == tenant_id
        ).first()
        if not config:
            return None

        from models import Config
        from hub.security import TokenEncryption

        sys_config = session.query(Config).first()
        if not sys_config or not sys_config.google_encryption_key:
            return None

        encryptor = TokenEncryption(sys_config.google_encryption_key.encode())
        result = {}

        if config.tls_ca_cert_encrypted:
            try:
                result["ca_cert"] = encryptor.decrypt(
                    config.tls_ca_cert_encrypted, f"syslog_ca_cert_{tenant_id}"
                )
            except Exception as e:
                logger.warning(f"[SyslogForwarder] Failed to decrypt CA cert for tenant {tenant_id}: {e}")
                return None  # Partial TLS config is unsafe — abort

        if config.tls_client_cert_encrypted:
            try:
                result["client_cert"] = encryptor.decrypt(
                    config.tls_client_cert_encrypted, f"syslog_client_cert_{tenant_id}"
                )
            except Exception as e:
                logger.warning(f"[SyslogForwarder] Failed to decrypt client cert for tenant {tenant_id}: {e}")

        if config.tls_client_key_encrypted:
            try:
                result["client_key"] = encryptor.decrypt(
                    config.tls_client_key_encrypted, f"syslog_client_key_{tenant_id}"
                )
            except Exception as e:
                logger.warning(f"[SyslogForwarder] Failed to decrypt client key for tenant {tenant_id}: {e}")

        result["verify"] = config.tls_verify if config.tls_verify is not None else True
        return result if result else None
    except Exception as e:
        logger.error(f"[SyslogForwarder] TLS decrypt failed for tenant {tenant_id}: {e}")
        return None
    finally:
        session.close()


def _update_operational_metadata(SessionFactory, tenant_id: str, success: bool, error_msg: str = None):
    """Update last_successful_send or last_error on the config record."""
    from models_rbac import TenantSyslogConfig

    session = SessionFactory()
    try:
        config = session.query(TenantSyslogConfig).filter(
            TenantSyslogConfig.tenant_id == tenant_id
        ).first()
        if config:
            if success:
                config.last_successful_send = datetime.utcnow()
            else:
                config.last_error = (error_msg or "Send failed")[:500]
                config.last_error_at = datetime.utcnow()
            session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def _worker_loop(SessionFactory, batch_size: int, poll_interval_ms: int):
    """Main worker loop."""
    from services.syslog_service import SyslogSender, RFC5424Formatter

    sender = SyslogSender()
    tls_cache: Dict[str, dict] = {}
    tls_cache_time: Dict[str, float] = {}

    logger.info("[SyslogForwarder] Worker started")

    while not _stop_event.is_set():
        try:
            # Batch drain
            events = []
            for _ in range(batch_size):
                try:
                    events.append(_event_queue.get_nowait())
                except queue.Empty:
                    break

            if not events:
                _stop_event.wait(poll_interval_ms / 1000.0)
                continue

            # Refresh config cache periodically (every 60s)
            if time.time() - _last_cache_refresh > 60:
                _refresh_config_cache(SessionFactory)

            # Group by tenant
            by_tenant: Dict[str, list] = {}
            for tenant_id, event_data in events:
                by_tenant.setdefault(tenant_id, []).append(event_data)

            # Process per tenant
            with _cache_lock:
                cache_snapshot = dict(_config_cache)

            for tenant_id, tenant_events in by_tenant.items():
                config = cache_snapshot.get(tenant_id)
                if not config or not config.get("host"):
                    continue

                categories = config.get("categories")
                tenant_success = False
                tenant_error = None

                for event_data in tenant_events:
                    try:
                        # Category filter
                        if categories:
                            action_cat = event_data.get("action", "").split(".")[0]
                            if action_cat not in categories:
                                continue

                        # Format
                        message = RFC5424Formatter.format_from_dict(
                            event_data,
                            facility=config["facility"],
                            app_name=config["app_name"],
                        )

                        # Get TLS config if needed
                        tls_config = None
                        if config["protocol"] == "tls":
                            now = time.time()
                            if tenant_id not in tls_cache or now - tls_cache_time.get(tenant_id, 0) > 300:
                                tls_cache[tenant_id] = _decrypt_tls_certs(SessionFactory, tenant_id) or {}
                                tls_cache_time[tenant_id] = now
                            tls_config = tls_cache.get(tenant_id)

                        # Send
                        success = sender.send(
                            tenant_id, message,
                            config["host"], config["port"], config["protocol"],
                            tls_config,
                        )

                        if success:
                            tenant_success = True

                    except Exception as e:
                        logger.error(f"[SyslogForwarder] Event send error for {tenant_id}: {e}")
                        tenant_error = str(e)

                # Update metadata once per tenant per batch (not per event)
                if tenant_success:
                    _update_operational_metadata(SessionFactory, tenant_id, True)
                elif tenant_error:
                    _update_operational_metadata(SessionFactory, tenant_id, False, tenant_error)

        except Exception as e:
            logger.error(f"[SyslogForwarder] Worker cycle error: {e}")
            time.sleep(1)

    sender.close_all()
    logger.info("[SyslogForwarder] Worker stopped")


def start_syslog_forwarder(engine, queue_size: int = 10000, batch_size: int = 50, poll_interval_ms: int = 200):
    """Start the syslog forwarder background worker."""
    global _worker_thread, _event_queue, _engine

    if _worker_thread and _worker_thread.is_alive():
        logger.warning("[SyslogForwarder] Worker already running, skipping duplicate start")
        return

    _engine = engine
    _event_queue = queue.Queue(maxsize=queue_size)
    _stop_event.clear()

    SessionFactory = sessionmaker(bind=engine)
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(SessionFactory, batch_size, poll_interval_ms),
        daemon=True,
        name="syslog-forwarder",
    )
    _worker_thread.start()
    logger.info("[SyslogForwarder] Background worker launched")


def stop_syslog_forwarder():
    """Stop the syslog forwarder background worker."""
    global _worker_thread
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)
    _worker_thread = None
