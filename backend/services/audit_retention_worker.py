"""
Audit Retention Worker — v0.6.0
Periodically purges expired audit events based on per-tenant retention policy.
Follows the scheduler/worker.py daemon thread pattern.
"""

import logging
import threading
import time
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

_worker_thread: threading.Thread = None
_stop_event = threading.Event()
_engine = None


def _run_purge_cycle(SessionFactory):
    """Execute one purge cycle across all tenants."""
    from models_rbac import Tenant
    from services.audit_service import TenantAuditService

    session: Session = SessionFactory()
    try:
        tenants = session.query(Tenant).filter(Tenant.is_active == True).all()
        total_purged = 0

        for tenant in tenants:
            try:
                retention_days = tenant.audit_retention_days or 90
                if retention_days <= 0:
                    continue

                service = TenantAuditService(session)
                purged = service.purge_expired(tenant.id, retention_days)
                if purged > 0:
                    total_purged += purged
                    logger.info(f"[AuditRetention] Purged {purged} expired events for tenant {tenant.id} (retention={retention_days}d)")
            except Exception as e:
                logger.error(f"[AuditRetention] Failed to purge tenant {tenant.id}: {e}")

        if total_purged > 0:
            logger.info(f"[AuditRetention] Total purged: {total_purged} events across {len(tenants)} tenants")
    except Exception as e:
        logger.error(f"[AuditRetention] Purge cycle failed: {e}")
    finally:
        session.close()


def _worker_loop(SessionFactory, poll_interval_hours: int):
    """Main worker loop running in daemon thread."""
    logger.info(f"[AuditRetention] Worker started (poll interval: {poll_interval_hours}h)")

    while not _stop_event.is_set():
        try:
            _run_purge_cycle(SessionFactory)
        except Exception as e:
            logger.error(f"[AuditRetention] Worker error: {e}")

        # Sleep in small increments so we can respond to stop quickly
        for _ in range(poll_interval_hours * 3600):
            if _stop_event.is_set():
                break
            time.sleep(1)

    logger.info("[AuditRetention] Worker stopped")


def start_audit_retention_worker(engine, poll_interval_hours: int = 24):
    """Start the audit retention background worker."""
    global _worker_thread, _engine
    _engine = engine
    _stop_event.clear()

    SessionFactory = sessionmaker(bind=engine)
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(SessionFactory, poll_interval_hours),
        daemon=True,
        name="audit-retention-worker",
    )
    _worker_thread.start()
    logger.info("[AuditRetention] Background worker launched")


def stop_audit_retention_worker():
    """Stop the audit retention background worker."""
    global _worker_thread
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=5)
        logger.info("[AuditRetention] Worker thread joined")
    _worker_thread = None
