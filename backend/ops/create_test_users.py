#!/usr/bin/env python3
"""
Create Test Users for Development

Creates three test users matching the frontend login page credentials:
- test@example.com (Tenant Owner)
- testadmin@example.com (Global Admin)
- member@example.com (Member)

Usage:
    docker exec tsushin-backend python3 /app/ops/create_test_users.py
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy.orm import Session
from db import get_engine, get_session
from models_rbac import User, Tenant, UserRole, Role
from auth_utils import hash_password
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_test_users(db: Session):
    """Create test users for development"""

    # Get the existing tenant (assuming there's at least one)
    tenant = db.query(Tenant).first()
    if not tenant:
        logger.error("No tenant found! Please run setup wizard first.")
        return False

    logger.info(f"Using tenant: {tenant.name} (ID: {tenant.id})")

    # Get roles
    owner_role = db.query(Role).filter(Role.name == "owner").first()
    member_role = db.query(Role).filter(Role.name == "member").first()

    if not owner_role or not member_role:
        logger.error("Roles not found! Database may not be initialized properly.")
        return False

    # Test users data
    test_users = [
        {
            "email": "test@example.com",
            "password": "test123",
            "full_name": "Test Owner",
            "tenant_id": tenant.id,
            "is_global_admin": False,
            "role": owner_role
        },
        {
            "email": "testadmin@example.com",
            "password": "admin123",
            "full_name": "Test Admin",
            "tenant_id": None,  # Global admin has no tenant
            "is_global_admin": True,
            "role": None  # Global admins don't need tenant roles
        },
        {
            "email": "member@example.com",
            "password": "member123",
            "full_name": "Test Member",
            "tenant_id": tenant.id,
            "is_global_admin": False,
            "role": member_role
        }
    ]

    created_count = 0
    for user_data in test_users:
        # Check if user already exists
        existing = db.query(User).filter(User.email == user_data["email"]).first()

        if existing:
            logger.info(f"User '{user_data['email']}' already exists, skipping...")
            continue

        # Hash password
        password_hash = hash_password(user_data["password"])

        # Create user
        user = User(
            email=user_data["email"],
            password_hash=password_hash,
            full_name=user_data["full_name"],
            tenant_id=user_data["tenant_id"],
            is_global_admin=user_data["is_global_admin"],
            is_active=True,
            email_verified=True
        )
        db.add(user)
        db.flush()  # Get user ID

        # Assign role if not global admin
        if user_data["role"] is not None:
            user_role = UserRole(
                user_id=user.id,
                role_id=user_data["role"].id
            )
            db.add(user_role)

        db.commit()
        created_count += 1

        logger.info(f"✓ Created user: {user_data['email']} ({user_data['full_name']})")
        if user_data["is_global_admin"]:
            logger.info(f"  → Global Admin (no tenant)")
        else:
            logger.info(f"  → Tenant: {tenant.name}, Role: {user_data['role'].name}")

    if created_count > 0:
        logger.info(f"\n✓ Successfully created {created_count} test user(s)")
        logger.info("\nTest Credentials:")
        logger.info("  test@example.com / test123 (Tenant Owner)")
        logger.info("  testadmin@example.com / admin123 (Global Admin)")
        logger.info("  member@example.com / member123 (Member)")
    else:
        logger.info("\nAll test users already exist")

    return True


def main():
    # Get database path from environment or use default
    db_path = os.getenv("DATABASE_PATH", "/app/data/agent.db")
    logger.info(f"Using database: {db_path}")

    # Initialize database
    engine = get_engine(db_path)

    # Create session and create users
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        success = create_test_users(db)
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Error creating test users: {e}", exc_info=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
