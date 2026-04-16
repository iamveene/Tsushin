"""
Subscription plan seeding — runs on every startup, idempotent.

Previously plans were only seeded via the SQLite-only migration
(migrations/add_plans_and_sso.py), leaving fresh PostgreSQL installs
with an empty subscription_plan table.  This module is the single
source of truth for default plan definitions and is called from
db.init_database() for both backends.
"""

import json
import logging

logger = logging.getLogger(__name__)

# Default plans for self-hosted installs.
# -1 = unlimited.  Prices in USD cents (irrelevant for self-hosted,
# kept so the schema stays consistent with SaaS deployments).
DEFAULT_PLANS = [
    {
        "name": "free",
        "display_name": "Free",
        "description": "Perfect for getting started with basic automation needs.",
        "price_monthly": 0,
        "price_yearly": 0,
        "max_users": 1,
        "max_agents": 1,
        "max_monthly_requests": 100,
        "max_knowledge_docs": 5,
        "max_flows": 2,
        "max_mcp_instances": 1,
        "features_json": json.dumps(["basic_support", "playground"]),
        "is_active": True,
        "is_public": True,
        "sort_order": 0,
    },
    {
        "name": "pro",
        "display_name": "Pro",
        "description": "For professionals who need more power and flexibility.",
        "price_monthly": 2900,
        "price_yearly": 29000,
        "max_users": 5,
        "max_agents": 10,
        "max_monthly_requests": 10000,
        "max_knowledge_docs": 50,
        "max_flows": 20,
        "max_mcp_instances": 3,
        "features_json": json.dumps(["priority_support", "playground", "custom_tools", "api_access"]),
        "is_active": True,
        "is_public": True,
        "sort_order": 1,
    },
    {
        "name": "team",
        "display_name": "Team",
        "description": "Collaboration features for growing teams.",
        "price_monthly": 9900,
        "price_yearly": 99000,
        "max_users": 20,
        "max_agents": 50,
        "max_monthly_requests": 100000,
        "max_knowledge_docs": 200,
        "max_flows": 100,
        "max_mcp_instances": 10,
        "features_json": json.dumps([
            "priority_support", "playground", "custom_tools",
            "api_access", "sso", "audit_logs", "advanced_analytics",
        ]),
        "is_active": True,
        "is_public": True,
        "sort_order": 2,
    },
    {
        "name": "enterprise",
        "display_name": "Enterprise",
        "description": "Custom solutions for large organizations with advanced needs.",
        "price_monthly": 0,
        "price_yearly": 0,
        "max_users": -1,
        "max_agents": -1,
        "max_monthly_requests": -1,
        "max_knowledge_docs": -1,
        "max_flows": -1,
        "max_mcp_instances": -1,
        "features_json": json.dumps([
            "dedicated_support", "playground", "custom_tools", "api_access",
            "sso", "audit_logs", "advanced_analytics", "sla",
            "on_premise", "custom_integrations",
        ]),
        "is_active": True,
        "is_public": True,
        "sort_order": 3,
    },
]


def seed_subscription_plans(session) -> None:
    """Insert default subscription plans that don't already exist.

    Safe to call on every startup — existing plans are never modified
    so manual overrides in production survive restarts.
    """
    from models_rbac import SubscriptionPlan

    created = 0
    for plan_data in DEFAULT_PLANS:
        existing = session.query(SubscriptionPlan).filter_by(name=plan_data["name"]).first()
        if existing:
            continue
        plan = SubscriptionPlan(**plan_data)
        session.add(plan)
        created += 1

    if created:
        session.commit()
        logger.info(f"[Plans] Seeded {created} subscription plan(s)")
    else:
        logger.debug("[Plans] Subscription plans already present — skipped")
