"""
Usage Tracking Service
Phase 7.9: Tenant Usage Tracking

Tracks tenant usage of system integrations for billing/analytics.
"""

from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
import logging

from models_rbac import TenantSystemIntegrationUsage, SystemIntegration

logger = logging.getLogger(__name__)


class UsageTrackingService:
    """Service for tracking tenant usage of system resources."""

    def __init__(self, db: Session):
        self.db = db

    def track_integration_usage(
        self,
        tenant_id: str,
        integration_id: int,
        increment: int = 1,
    ) -> TenantSystemIntegrationUsage:
        """
        Track usage of a system integration by a tenant.

        Args:
            tenant_id: The tenant using the integration
            integration_id: The system integration being used
            increment: Number of uses to add (default 1)

        Returns:
            Updated usage record
        """
        # Find or create usage record
        usage = self.db.query(TenantSystemIntegrationUsage).filter(
            TenantSystemIntegrationUsage.tenant_id == tenant_id,
            TenantSystemIntegrationUsage.system_integration_id == integration_id,
        ).first()

        if not usage:
            usage = TenantSystemIntegrationUsage(
                tenant_id=tenant_id,
                system_integration_id=integration_id,
                usage_count=0,
            )
            self.db.add(usage)

        usage.usage_count += increment
        usage.last_used_at = datetime.utcnow()

        # Also update the system integration's total usage
        integration = self.db.query(SystemIntegration).filter(
            SystemIntegration.id == integration_id
        ).first()
        if integration:
            integration.usage_count += increment
            integration.last_used_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(usage)

        logger.debug(
            f"Tracked usage: tenant={tenant_id}, integration={integration_id}, "
            f"total={usage.usage_count}"
        )

        return usage

    def get_tenant_usage(
        self,
        tenant_id: str,
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a tenant.

        Args:
            tenant_id: The tenant to get usage for

        Returns:
            Dictionary with usage statistics
        """
        usages = self.db.query(TenantSystemIntegrationUsage).filter(
            TenantSystemIntegrationUsage.tenant_id == tenant_id
        ).all()

        total_usage = sum(u.usage_count for u in usages)

        usage_by_integration = {}
        for usage in usages:
            integration = self.db.query(SystemIntegration).filter(
                SystemIntegration.id == usage.system_integration_id
            ).first()

            if integration:
                usage_by_integration[integration.service_name] = {
                    "usage_count": usage.usage_count,
                    "last_used_at": usage.last_used_at.isoformat() if usage.last_used_at else None,
                    "display_name": integration.display_name,
                }

        return {
            "tenant_id": tenant_id,
            "total_usage": total_usage,
            "by_integration": usage_by_integration,
        }

    def get_integration_usage(
        self,
        integration_id: int,
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a system integration.

        Args:
            integration_id: The integration to get usage for

        Returns:
            Dictionary with usage statistics
        """
        integration = self.db.query(SystemIntegration).filter(
            SystemIntegration.id == integration_id
        ).first()

        if not integration:
            return None

        usages = self.db.query(TenantSystemIntegrationUsage).filter(
            TenantSystemIntegrationUsage.system_integration_id == integration_id
        ).all()

        tenant_count = len(usages)
        total_usage = sum(u.usage_count for u in usages)

        return {
            "integration_id": integration_id,
            "service_name": integration.service_name,
            "display_name": integration.display_name,
            "total_usage": total_usage,
            "tenant_count": tenant_count,
            "is_active": integration.is_active,
        }

    def reset_monthly_usage(self, tenant_id: Optional[str] = None) -> int:
        """
        Reset usage counts (typically called at start of billing period).

        Args:
            tenant_id: Optional tenant to reset, or None for all tenants

        Returns:
            Number of records reset
        """
        query = self.db.query(TenantSystemIntegrationUsage)

        if tenant_id:
            query = query.filter(TenantSystemIntegrationUsage.tenant_id == tenant_id)

        count = query.update({"usage_count": 0})
        self.db.commit()

        logger.info(f"Reset usage for {count} records")
        return count


def track_usage(
    db: Session,
    tenant_id: str,
    integration_id: int,
    increment: int = 1,
) -> Optional[TenantSystemIntegrationUsage]:
    """
    Convenience function for tracking usage.

    Can be used as a quick one-liner in route handlers:
        track_usage(db, user.tenant_id, ai_integration.id)
    """
    service = UsageTrackingService(db)
    return service.track_integration_usage(tenant_id, integration_id, increment)
