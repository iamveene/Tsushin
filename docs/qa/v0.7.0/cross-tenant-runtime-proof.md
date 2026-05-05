# Cross-Tenant Runtime Isolation Proof (v0.7.0 RC)

**Date:** 2026-04-24
**Method:** Login as both tenant owners via `/api/auth/login`, fetch `/api/agents` with each session cookie, compare results.

## Setup

- Tenant A: `acme2-dev` (seeded by `backend/scripts/seed_dev_tenants.py` in this RC) — owner `test-acme2@example.com`.
- Tenant B: original tenant (`tenant_20260406004333855618_c58c99`) — owner `test@example.com`.

## Result

```
acme2-dev: 3 agents [227, 228, 229]
acme orig: 11 agents [1, 2, 3, 5, 6, ...]
```

- **Zero overlap** in agent IDs.
- Each tenant sees only its own agents.
- Tenant scoping enforced at the API layer.

## Conclusion

The release-readiness review's D-3 defect ("dev DB only had one populated tenant; cross-tenant runtime proof was code-only") is closed. Cross-tenant isolation is now exercised at runtime against two real tenants with distinct seeded data.
