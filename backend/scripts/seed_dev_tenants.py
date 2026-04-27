#!/usr/bin/env python3
"""
Dev-only second-tenant seeder for cross-tenant runtime testing.

Creates a second tenant ("acme2-dev" by default) with two users (owner + member),
the standard set of system agents, and two paused trigger stubs (Email + Schedule).
The script is opt-in and idempotent: re-running it exits 0 with "already seeded"
when the tenant row exists.

Usage (inside the backend container):
    docker exec -e TSN_SEED_ALLOW=true tsushin-backend \\
        python scripts/seed_dev_tenants.py [--dry-run]

Safety:
- Refuses to run unless TSN_SEED_ALLOW=true is set.
- Refuses to run if the tenant table already has 5 or more rows.
- Backup recommendation:
      docker exec tsushin-postgres pg_dump -U tsushin tsushin > backup_seed.sql
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import settings as settings_module
from auth_utils import hash_password
from models import EmailChannelInstance, ScheduleChannelInstance
from models_rbac import Role, Tenant, User, UserRole
from services.agent_seeding import seed_default_agents


logger = logging.getLogger("seed_dev_tenants")


DEFAULTS = {
    "tenant_id": "acme2-dev",
    "tenant_name": "Acme #2 Dev",
    "admin_email": "test-acme2@example.com",
    "admin_name": "Acme2 Owner",
    "member_email": "member-acme2@example.com",
    "member_name": "Acme2 Member",
    "password": "test1234",
}

TENANT_CEILING = 5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed a second dev tenant for cross-tenant testing.")
    parser.add_argument("--tenant-id", default=DEFAULTS["tenant_id"])
    parser.add_argument("--tenant-name", default=DEFAULTS["tenant_name"])
    parser.add_argument("--admin-email", default=DEFAULTS["admin_email"])
    parser.add_argument("--admin-name", default=DEFAULTS["admin_name"])
    parser.add_argument("--member-email", default=DEFAULTS["member_email"])
    parser.add_argument("--member-name", default=DEFAULTS["member_name"])
    parser.add_argument("--password", default=DEFAULTS["password"])
    parser.add_argument("--dry-run", action="store_true", help="Print plan without writing.")
    parser.add_argument(
        "--with-continuous",
        action="store_true",
        help="Reserved for future continuous-agent seeding once WS-1 CRUD is GA.",
    )
    return parser.parse_args()


def guard_environment(db) -> None:
    flag = (os.environ.get("TSN_SEED_ALLOW") or "").strip().lower()
    if flag not in {"true", "1", "yes"}:
        sys.stderr.write(
            "Refusing to run: set TSN_SEED_ALLOW=true to authorize this dev seeder. "
            "Never run against production.\n"
        )
        sys.exit(2)
    count = db.query(Tenant).count()
    if count >= TENANT_CEILING:
        sys.stderr.write(
            f"Refusing to run: tenant table has {count} rows (ceiling {TENANT_CEILING}). "
            "Drop the ceiling guard if you really meant to seed.\n"
        )
        sys.exit(2)


def _resolve_role(db, role_name: str) -> Role:
    role = db.query(Role).filter(Role.name == role_name).first()
    if role is None:
        raise RuntimeError(f"Role '{role_name}' missing — run db.seed_rbac_defaults() first.")
    return role


def _get_or_create_user(
    db,
    *,
    tenant_id: str,
    email: str,
    full_name: str,
    password_hash: str,
    role: Role,
) -> User:
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        return existing
    user = User(
        tenant_id=tenant_id,
        email=email,
        full_name=full_name,
        password_hash=password_hash,
        is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id, tenant_id=tenant_id))
    db.flush()
    return user


def _get_or_create_email_stub(db, *, tenant_id: str, owner_id: int) -> Optional[EmailChannelInstance]:
    existing = (
        db.query(EmailChannelInstance)
        .filter(
            EmailChannelInstance.tenant_id == tenant_id,
            EmailChannelInstance.integration_name == "Acme2 Email Watch",
        )
        .first()
    )
    if existing is not None:
        return existing
    instance = EmailChannelInstance(
        tenant_id=tenant_id,
        integration_name="Acme2 Email Watch",
        provider="gmail",
        gmail_integration_id=None,
        search_query="is:unread label:inbox",
        poll_interval_seconds=300,
        is_active=False,
        status="paused",
        health_status="unknown",
        created_by=owner_id,
    )
    db.add(instance)
    db.flush()
    return instance


def _get_or_create_schedule_stub(db, *, tenant_id: str, owner_id: int) -> Optional[ScheduleChannelInstance]:
    existing = (
        db.query(ScheduleChannelInstance)
        .filter(
            ScheduleChannelInstance.tenant_id == tenant_id,
            ScheduleChannelInstance.integration_name == "Acme2 Weekly Digest",
        )
        .first()
    )
    if existing is not None:
        return existing
    instance = ScheduleChannelInstance(
        tenant_id=tenant_id,
        integration_name="Acme2 Weekly Digest",
        cron_expression="0 9 * * MON",
        timezone="UTC",
        is_active=False,
        status="paused",
        created_by=owner_id,
    )
    db.add(instance)
    db.flush()
    return instance


def seed_tenant(args: argparse.Namespace, db) -> None:
    existing_tenant = db.query(Tenant).filter(Tenant.id == args.tenant_id).first()
    if existing_tenant is not None:
        print(f"Tenant '{args.tenant_id}' already exists — nothing to do.")
        return

    if args.dry_run:
        print(f"[dry-run] Would create tenant '{args.tenant_id}' ({args.tenant_name})")
        print(f"[dry-run] Would create owner: {args.admin_email}")
        print(f"[dry-run] Would create member: {args.member_email}")
        print(f"[dry-run] Would seed 3 default agents")
        print(f"[dry-run] Would create paused EmailChannelInstance 'Acme2 Email Watch'")
        print(f"[dry-run] Would create paused ScheduleChannelInstance 'Acme2 Weekly Digest'")
        return

    owner_role = _resolve_role(db, "owner")
    member_role = _resolve_role(db, "member")

    tenant = Tenant(id=args.tenant_id, name=args.tenant_name, slug=args.tenant_id)
    db.add(tenant)
    db.flush()

    password_hash = hash_password(args.password)

    owner = _get_or_create_user(
        db,
        tenant_id=args.tenant_id,
        email=args.admin_email,
        full_name=args.admin_name,
        password_hash=password_hash,
        role=owner_role,
    )
    _get_or_create_user(
        db,
        tenant_id=args.tenant_id,
        email=args.member_email,
        full_name=args.member_name,
        password_hash=password_hash,
        role=member_role,
    )

    seeded_agents = seed_default_agents(args.tenant_id, owner.id, db)
    _get_or_create_email_stub(db, tenant_id=args.tenant_id, owner_id=owner.id)
    _get_or_create_schedule_stub(db, tenant_id=args.tenant_id, owner_id=owner.id)

    db.commit()

    print("=== Seed summary ===")
    print(f"Tenant:       {args.tenant_id} ({args.tenant_name})")
    print(f"Owner:        {args.admin_email} (password: {args.password})")
    print(f"Member:       {args.member_email} (password: {args.password})")
    print(f"Agents:       {len(seeded_agents)}")
    print(f"Email stub:   Acme2 Email Watch (paused)")
    print(f"Schedule stub:Acme2 Weekly Digest (paused)")

    if args.with_continuous:
        print(
            "[note] --with-continuous is reserved until WS-1 ContinuousAgent CRUD ships. "
            "Re-run after the CRUD endpoints are GA."
        )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = parse_args()

    engine = create_engine(settings_module.DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        guard_environment(db)
        seed_tenant(args, db)
    except Exception as exc:
        db.rollback()
        sys.stderr.write(f"Seed failed: {type(exc).__name__}: {exc}\n")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
