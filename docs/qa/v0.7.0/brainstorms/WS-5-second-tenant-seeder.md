# WS-5: Second-Tenant Dev Seeder — Architecture Blueprint

**Date:** 2026-04-24

## Patterns Found

**Existing seeders (idempotent skip-on-exist):**
- `backend/services/agent_seeding.py:184-195` — checks `Contact.friendly_name + tenant_id + role == "agent"` before inserting; commits per agent.
- `backend/services/persona_seeding.py:28-46` — global, system-scoped.
- `backend/services/tone_preset_seeding.py:44-48` — set-based skip.

**First-run tenant primitives:**
- `backend/auth_service.py:113-209` — `AuthService.signup()` creates `Tenant` + `User` + `UserRole(owner)`. Uses `hash_password()` (Argon2).
- `backend/api/routes_tenants.py:209-275` — admin route mirrors the same pattern without going through AuthService. **Preferred pattern to replicate.**
- `backend/db.py:1527-1688` — `init_database()` bootstraps system data only. Does NOT create a default `acme-corp`. The first tenant is created via signup; `acme-corp` exists in the dev DB because the operator ran signup post-install.

**No `TSN_ENV` variable exists.** Use a bespoke `TSN_SEED_ALLOW=true` env flag for production-safety.

**Trigger model FKs for stubs:**
- `EmailChannelInstance.gmail_integration_id` — nullable (`models.py:3145`).
- `ScheduleChannelInstance` — no external FK deps beyond `tenant_id`/`created_by`.

## Architecture Decision

A single self-contained script at `backend/scripts/seed_dev_tenants.py`, manual `docker exec` invocation. Imports existing seeders directly. Opt-in only — never auto-runs.

**Trade-off:** Skip `WebhookIntegration` stubs (need Fernet key). Use a `ScheduleChannelInstance` paused stub as the second trigger sample alongside the `EmailChannelInstance` stub.

## Component Design

### `backend/scripts/seed_dev_tenants.py` (new ~280 lines)

Imports:
```python
from db import get_engine
from models_rbac import Tenant, User, Role, UserRole
from models import Contact, Agent, EmailChannelInstance, ScheduleChannelInstance
from services.agent_seeding import seed_default_agents
from auth_utils import hash_password
from sqlalchemy.orm import sessionmaker
```

CLI:
```
python -m scripts.seed_dev_tenants [OPTIONS]

--tenant-id        default: acme2-dev
--tenant-name      default: "Acme #2 Dev"
--admin-email      default: test-acme2@example.com
--member-email     default: member-acme2@example.com
--password         default: test1234
--dry-run          flag — print without writing
--with-continuous  flag — placeholder, prints "WS-1 needed" until CRUD lands
```

Structure:
1. Module docstring (backup recommendation, usage, safety warnings).
2. `parse_args()`.
3. `guard_environment(db)`:
   - `TSN_SEED_ALLOW != "true"` → abort with clear message.
   - Tenant count `>= 5` → abort.
4. `seed_tenant(args, db, dry_run)`:
   - Tenant exists → "already seeded", exit 0.
   - Dry-run → print plan, return.
   - Create `Tenant`, owner `User` + `UserRole(owner)`, member `User` + `UserRole(member)`.
   - Call `seed_default_agents(tenant_id, owner.id, db)`.
   - Create paused `EmailChannelInstance` stub (`is_active=False`, `gmail_integration_id=None`).
   - Create paused `ScheduleChannelInstance` stub (`is_active=False`).
   - Commit + summary.
5. `main()` → argparse → guard → seed.

### `backend/scripts/__init__.py` — verify exists (for `-m` invocation)

### Documentation

`docs/changelog.md`: one line under v0.7.0:
```
- WS-5: Added `backend/scripts/seed_dev_tenants.py` — idempotent CLI script that seeds a second dev tenant (`acme2-dev`) for cross-tenant isolation testing.
```

`docs/documentation.md`: one paragraph under dev-setup section explaining usage, safety guards, and idempotency contract.

## Data Flow

```
CLI args
  └─ guard_environment(db)        ← TSN_SEED_ALLOW + tenant ceiling
       └─ Tenant(id=acme2-dev)
            └─ User(owner) + UserRole(owner)
                 └─ User(member) + UserRole(member)
                      └─ seed_default_agents() → 3x Contact+Agent+AgentSkill
                      └─ EmailChannelInstance(paused)
                      └─ ScheduleChannelInstance(paused)
                           → db.commit()
  └─ Print summary, exit 0
```

## Critical Details

- **Safety:** `TSN_SEED_ALLOW=true` env required; tenant count `>=5` ceiling; per-step rollback on error.
- **Password:** `auth_utils.hash_password()` (Argon2), identical to `AuthService.signup()`. Default `test1234` matches CLAUDE.md test creds.
- **Email uniqueness:** `user.email` is UNIQUE; idempotency per-entity (skip individual users if email already exists).
- **Trigger stubs:** Both stubs are `is_active=False`/`status="paused"` — trigger dispatch worker ignores them at runtime.
- **`seed_default_agents` signature:** `(tenant_id: str, user_id: int, db: Session, model_provider="gemini", model_name="gemini-2.5-flash")`. Already idempotent.
- **No auto-run.** `init_database()` and `lifespan()` in `app.py` do not invoke this script.

## Validation

After run:
```bash
docker exec tsushin-postgres psql -U tsushin -c "SELECT id, name FROM tenant;"
docker exec tsushin-postgres psql -U tsushin -c \
  "SELECT u.email, r.name FROM \"user\" u JOIN user_role ur ON ur.user_id=u.id JOIN role r ON r.id=ur.role_id WHERE u.tenant_id='acme2-dev';"
docker exec tsushin-postgres psql -U tsushin -c \
  "SELECT c.friendly_name, a.tenant_id FROM contact c JOIN agent a ON a.contact_id=c.id WHERE a.tenant_id='acme2-dev';"
```

Browser:
1. Log out, log in as `test-acme2@example.com` / `test1234` → see only acme2-dev agents.
2. Log in as `test@example.com` (acme-corp) → no acme2-dev rows visible.
3. Trigger stubs visible in Hub → Triggers, both paused.

## Build Sequence

1. Verify/create `backend/scripts/__init__.py`.
2. Write `seed_dev_tenants.py`.
3. Add `TSN_SEED_ALLOW` documentation (don't commit `.env`).
4. Update changelog + documentation.
5. Manual tests (dry-run, real run, re-run idempotency, cross-tenant browser).
6. Commit.

## Summary

A single opt-in CLI script that mirrors `routes_tenants.create_tenant()` patterns to seed a second dev tenant with users, agents, and two paused trigger stubs. Uses existing `seed_default_agents()` and `hash_password()`. Hard-gated by `TSN_SEED_ALLOW=true` and a 5-tenant ceiling. Fully idempotent. Does not touch container startup. Continuous-agent seeding is a future Phase 2 once WS-1 CRUD lands.
