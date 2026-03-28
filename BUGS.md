# Tsushin Bug Tracker
**Open:** 0 | **In Progress:** 0 | **Resolved:** 62
**Source:** v0.6.1 Security Vulnerability Audit (2026-03-28)

## Open Issues

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
