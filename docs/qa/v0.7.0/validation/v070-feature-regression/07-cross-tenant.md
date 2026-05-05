# Cross-tenant isolation (live, 2026-04-25)

```sql
SELECT tenant_id, count(*) FROM agent GROUP BY tenant_id ORDER BY tenant_id;
```

```
 acme2-dev                          |     3
 tenant_20260406004333855618_c58c99 |    11
```

3 agents (227, 228, 229) for `acme2-dev` (seeded by `backend/scripts/seed_dev_tenants.py` in WS-5).
11 agents for the original tenant. **Zero overlap.**

PASS — runtime isolation confirmed.
