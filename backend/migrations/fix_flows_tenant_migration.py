#!/usr/bin/env python3
"""
Migration: Fix Flows Tenant ID for Multi-Tenancy
Phase 7.9 Post-Migration Fix

Issue: All existing flows have tenant_id='default', making them invisible
to users with different tenant_ids after RBAC expansion.

Solution: Set tenant_id to NULL for existing flows so they remain accessible
to all tenants during migration. New flows will properly inherit creator's tenant_id.
"""

import sys
sys.path.insert(0, '.')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import settings
from models import FlowDefinition

def main():
    """Update existing flows to have NULL tenant_id for multi-tenant access"""

    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Count flows that need migration
        flows_to_update = session.query(FlowDefinition).filter(
            FlowDefinition.tenant_id.isnot(None)
        ).all()

        count = len(flows_to_update)

        if count == 0:
            print("✓ No flows need migration. All flows already have NULL tenant_id.")
            return

        print(f"Found {count} flows with non-NULL tenant_id that need migration:")
        for flow in flows_to_update[:5]:  # Show first 5
            print(f"  - Flow ID={flow.id}, name='{flow.name}', tenant_id={flow.tenant_id}")

        if count > 5:
            print(f"  ... and {count - 5} more")

        print(f"\nUpdating {count} flows to have NULL tenant_id...")

        # Update all flows to have NULL tenant_id
        for flow in flows_to_update:
            flow.tenant_id = None

        session.commit()

        print(f"✓ Successfully updated {count} flows to have NULL tenant_id")
        print("✓ Existing flows are now accessible to all tenants")
        print("✓ New flows will inherit creator's tenant_id as expected")

    except Exception as e:
        session.rollback()
        print(f"✗ Error during migration: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    print("=" * 60)
    print("Flows Tenant Migration Fix")
    print("=" * 60)
    main()
    print("=" * 60)
