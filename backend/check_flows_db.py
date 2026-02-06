#!/usr/bin/env python3
"""Quick script to check flows in database and tenant_id column"""

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from models import FlowDefinition
import settings

engine = create_engine(settings.DATABASE_URL)
inspector = inspect(engine)

# Check if tenant_id column exists
try:
    columns = [col['name'] for col in inspector.get_columns('flow_definition')]
    print(f'✓ FlowDefinition table columns: {columns}')
    print(f'✓ Has tenant_id column: {"tenant_id" in columns}')
except Exception as e:
    print(f'✗ Error inspecting table: {e}')

# Check how many flows exist
Session = sessionmaker(bind=engine)
session = Session()

try:
    flow_count = session.query(FlowDefinition).count()
    print(f'\n✓ Total flows in database: {flow_count}')

    if flow_count > 0:
        print('\nFlows in database:')
        flows = session.query(FlowDefinition).limit(10).all()
        for flow in flows:
            tenant_val = getattr(flow, 'tenant_id', 'NO_COLUMN')
            print(f'  - Flow ID={flow.id}, name="{flow.name}", tenant_id={tenant_val}, is_active={flow.is_active}')
    else:
        print('\n⚠ No flows found in database')

except Exception as e:
    print(f'✗ Error querying flows: {e}')
finally:
    session.close()

# Check tenants
from models_rbac import Tenant
session = Session()
try:
    tenant_count = session.query(Tenant).count()
    print(f'\n✓ Total tenants in database: {tenant_count}')

    if tenant_count > 0:
        print('\nTenants in database:')
        tenants = session.query(Tenant).limit(10).all()
        for tenant in tenants:
            print(f'  - Tenant ID={tenant.id}, name="{tenant.name}", slug={tenant.slug}')
except Exception as e:
    print(f'✗ Error querying tenants: {e}')
finally:
    session.close()
