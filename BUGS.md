# Tsushin Bug Tracker
**Open:** 5 | **In Progress:** 0 | **Resolved:** 45
**Source:** v0.6.0 Comprehensive Platform Audit (2026-03-27)

## Open Issues (Lower Priority)

### BUG-042: enabled_channels always null in internal agent listing
- **Status:** Open
- **Severity:** Medium
- **Found:** 2026-03-27
- **Details:** `GET /api/agents` (internal) returns `enabled_channels: null` for all agents, while the public API correctly returns channel arrays.

### BUG-043: No validation on enabled_channels values
- **Status:** Open
- **Severity:** Medium
- **Found:** 2026-03-27
- **Details:** Arbitrary strings accepted in `enabled_channels` array. Only "playground", "whatsapp", "telegram" should be valid.

### BUG-044: Duplicate nuclei tool commands (data quality)
- **Status:** Open
- **Severity:** Medium
- **Found:** 2026-03-27
- **Details:** The `nuclei` tool has two `severity_scan` commands (IDs 22/24). Command ID 22 has duplicate parameters.

### BUG-045: Resource existence oracle via 403/404 differential
- **Status:** Open
- **Severity:** Low
- **Found:** 2026-03-27
- **Details:** GET-by-ID endpoints return 403 for existing cross-tenant resources and 404 for non-existing, allowing ID enumeration.

### BUG-046: CORS allows all origins (production concern)
- **Status:** Open
- **Severity:** Low
- **Found:** 2026-03-27
- **Details:** `Access-Control-Allow-Origin: *` acceptable for dev but needs restriction for production.

## Closed Issues

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
