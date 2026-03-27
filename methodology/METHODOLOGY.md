# Tsushin Development Methodology

## Purpose

This methodology enforces disciplined, regression-aware development for Tsushin -- a multi-tenant WhatsApp automation platform. Every change must be validated before it is considered complete. No exceptions.

## Architecture Context

| Layer | Technology | Container | Port |
|-------|-----------|-----------|------|
| Frontend | Next.js (TypeScript) | tsushin-frontend | 3030 |
| Backend | Python / FastAPI | tsushin-backend | 8081 |
| Database | PostgreSQL 16 | tsushin-postgres | 5432 |
| WhatsApp Bridge | MCP containers | dynamic | varies |
| Toolbox | Per-tenant sandboxed containers | dynamic | varies |

**Docker rule:** Always start containers from `/Users/vinicios/code/tsushin`, never from worktrees. Worktrees have empty `backend/data/` directories and will cause data loss illusions.

```bash
# CORRECT
cd /Users/vinicios/code/tsushin && docker compose up -d

# WRONG (from a worktree)
cd /Users/vinicios/.claude-worktrees/tsushin/<name> && docker compose up -d
```

## The 6-Phase Lifecycle

Every feature, fix, or refactor follows these phases in order. Skipping a phase is not allowed.

### Phase 1: Brainstorm

**Goal:** Understand the problem space and identify the scope.

- What is the user-facing problem or requirement?
- Which layers are affected? (frontend, backend, database, WhatsApp bridge, toolbox)
- Is this tenant-scoped or global? (multi-tenancy implications)
- What existing code paths will be touched?
- Are there migration requirements (PostgreSQL schema changes)?

**Output:** A clear problem statement and affected-area list.

### Phase 2: Plan

**Goal:** Design the solution with concrete implementation steps.

- Define the exact files to create or modify
- If database changes: write the migration strategy (Alembic or manual SQL)
- If API changes: define the endpoint contract (method, path, request/response)
- If UI changes: identify the Next.js page/component and state management
- If agent behavior changes: identify the agent router, skills, or persona logic
- Identify test strategy: which endpoints to curl, which pages to verify via Playwright MCP
- Estimate blast radius: what adjacent features might break?

**Output:** A step-by-step implementation plan with test checkpoints.

### Phase 3: Review

**Goal:** Sanity-check the plan before writing code.

- Does the plan respect multi-tenancy? (tenant isolation, `tenantid` headers)
- Does it handle auth correctly? (JWT tokens, role-based access)
- Are there race conditions in async operations? (FastAPI async endpoints)
- Will this work with the existing Docker Compose setup?
- Does the plan account for seed/installer script updates?
- Is the migration reversible?

**Output:** Approved plan or revised plan with corrections.

### Phase 4: Adjust

**Goal:** Refine based on review findings.

- Update the plan to address review concerns
- Add missing test cases
- Adjust migration strategy if needed
- Confirm that all affected seed scripts are identified

**Output:** Final implementation plan ready for coding.

### Phase 5: Implement

**Goal:** Write the code, run the containers, verify it compiles/starts.

Steps:
1. Write the code changes across all affected layers
2. Update seed/installer scripts if schema or defaults changed
3. Rebuild containers:
   - Backend changes: `cd /Users/vinicios/code/tsushin && docker compose up -d --build backend`
   - Frontend changes: `cd /Users/vinicios/code/tsushin && docker compose build --no-cache frontend && docker compose up -d frontend`
   - Database changes: restart backend (migrations run on startup)
4. Check container health: `docker compose ps` and `docker compose logs --tail=50 backend`
5. Verify basic startup: `curl http://localhost:8081/health`

**Output:** Running containers with the new code.

### Phase 6: Validate

**Goal:** Prove the change works and nothing else broke. This is mandatory.

Validation checklist:
1. **Targeted test:** Verify the specific feature/fix works
   - API: curl the affected endpoints
   - UI: Navigate to the page via Playwright MCP, confirm rendering
   - Agent: Send test message via WhatsApp tester MCP or Playground
2. **Regression test:** Run `/fire_regression` against the changed area
3. **Adjacent features:** Manually verify 2-3 related features still work
4. **Service health:** Check `docker compose ps` -- all containers healthy
5. **Log review:** `docker compose logs --tail=100 backend` -- no errors

**Gate:** The implementation is NOT complete until validation passes. If `/fire_regression` finds issues, return to Phase 5.

## Test Credentials

| Role | Email | Password |
|------|-------|----------|
| Tenant Owner | test@example.com | test123 |
| Global Admin | testadmin@example.com | admin123 |
| Member | member@example.com | member123 |

## Test Infrastructure

- **Playwright MCP:** Browser automation for UI testing
- **WhatsApp Tester MCP:** Port 8088, for end-to-end message testing
- **Backend API:** http://localhost:8081 (all API endpoints)
- **Frontend:** http://localhost:3030 (all UI pages)

## Commit Discipline

- Commit after every successful validation (Phase 6 pass)
- Never commit untested code
- Follow the branch strategy: work on `develop` or `feature/*`, never `main`
- Git identity: commits as `iamveene`
- No co-authorship lines in commit messages

## Bug Tracking

All bugs found during regression are tracked in `/Users/vinicios/code/tsushin/BUGS.md` via the `/fire_remediation` command. This file is gitignored (working document, not committed).
