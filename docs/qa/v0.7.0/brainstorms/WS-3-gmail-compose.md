# WS-3: Gmail compose scope + reauth — Implementation Blueprint

**Date:** 2026-04-24

## Patterns Found (Most Infrastructure Already Exists)

- **Scope constants exist:** `GMAIL_COMPOSE_SCOPE`, `GMAIL_DRAFT_COMPATIBLE_SCOPES`, `can_create_drafts()`, `_ensure_draft_capability()`, `has_compose_scope()` are all in `backend/hub/google/gmail_service.py:42–61, 305`.
- **Granted scope is already persisted:** `OAuthToken.scope` (`backend/models.py:2764`) stores the space-separated scope string from Google's token response. No new column needed.
- **`can_draft` is already computed and returned:** `routes_google.py:299–302` computes `can_draft=bool(token_scopes & GMAIL_DRAFT_COMPATIBLE_SCOPES)` and includes it in `IntegrationResponse` (line 85).
- **`_ensure_draft_capability()` already raises `PermissionError`** but the route layer doesn't translate it to a structured 409 — currently bubbles up as a 500.
- **`get_gmail_oauth_scopes()`** at `routes_google.py:125–131` conditionally appends `gmail.compose` only when `include_send_scope=True`. **`DEFAULT_SCOPES["gmail"]` does not yet include `gmail.compose` by default.**

## Architecture Decision: Option A (Hard-Block 409)

**Chosen:** Option A — hard-block draft actions with structured 409 `code: "needs_reauth"` when scope missing; UI shows pill + "Reconnect Gmail" button.

**Why not Option B (silent health_status nudge):** Option B delays the error signal to whenever a health check runs and obscures the failure cause. Option A surfaces the exact problem at moment of failure, propagates a machine-readable code, requires no background jobs.

**Trade-off accepted:** Hard stop on first draft attempt. Acceptable — it's an auth problem, not transient; retry without reauth always fails.

## Component Design

### 1. `backend/hub/google/oauth_handler.py:78–87`
Add `https://www.googleapis.com/auth/gmail.compose` to `DEFAULT_SCOPES["gmail"]`. Existing connections unaffected (their stored scope doesn't change).

### 2. `backend/hub/google/gmail_service.py`
Define exception class near imports:
```python
class InsufficientScopesError(Exception):
    def __init__(self, missing_scopes: list[str], message: str = ""):
        self.missing_scopes = missing_scopes
        super().__init__(message or f"Missing scopes: {missing_scopes}")
```

Replace bare `PermissionError` in `_ensure_draft_capability()` (line 305) with `InsufficientScopesError(missing_scopes=[GMAIL_COMPOSE_SCOPE], ...)`.

### 3. `backend/api/routes_google.py`
- Import `InsufficientScopesError`.
- Wherever `create_draft()` is called via HTTP (skill or future direct endpoint), catch `InsufficientScopesError`:

```python
except InsufficientScopesError as e:
    raise HTTPException(
        status_code=409,
        detail={
            "code": "needs_reauth",
            "missing_scopes": e.missing_scopes,
            "integration_id": integration_id,
            "message": str(e),
        }
    )
```

- Simplify `get_gmail_oauth_scopes()`: since compose is now in `DEFAULT_SCOPES`, remove conditional appending — leave only `include_send_scope` branch.

### 4. Frontend: `frontend/app/hub/page.tsx`
Gmail integration card additions:
- **Amber pill** when `integration.can_draft === false`: `"Drafts require reauth"`.
- **"Reconnect Gmail" button** triggers existing OAuth start endpoint (`POST /api/hub/google/gmail/oauth/authorize`). Same endpoint as new connections.
- **Toast** on draft 409: `"Gmail draft creation requires reauthorization. Reconnect your Gmail account in Hub."`.

### 5. `frontend/lib/client.ts`
Confirm/add `can_draft: boolean` on the Gmail integration TypeScript type.

## Files Modified

| File | Change |
|---|---|
| `backend/hub/google/oauth_handler.py:79` | Add `gmail.compose` to `DEFAULT_SCOPES["gmail"]` |
| `backend/hub/google/gmail_service.py` | Add `InsufficientScopesError`; replace `PermissionError` |
| `backend/api/routes_google.py` | Import + 409 handler; simplify `get_gmail_oauth_scopes()` |
| `frontend/app/hub/page.tsx` | Pill + reconnect button + 409 toast |
| `frontend/lib/client.ts` | Confirm `can_draft` type |

**No Alembic migration.**

## Data Flow

1. **New connection:** OAuth → consent screen shows compose → token saved with compose → `can_draft=True`.
2. **Existing connection (lazy reauth):** Agent triggers draft → `_ensure_draft_capability()` → `InsufficientScopesError` → 409 → frontend toast + Hub pill → user clicks "Reconnect Gmail" → OAuth with new scopes → token upgraded → `can_draft=True`.
3. **Reconnect path:** `_create_gmail_integration()` already handles upsert — finds existing row by email+tenant, resets `health_status="unknown"`, saves new token.
4. **Tenants not using drafts:** Zero disruption.

## Tests

1. `test_scope_present_draft_succeeds` — token with compose scope; mock _make_request; no exception.
2. `test_scope_missing_draft_raises_409` — readonly-only token; assert 409 + `code: "needs_reauth"` + `gmail.compose` in `missing_scopes`.
3. `test_oauth_start_includes_compose_scope` — generate URL; assert compose in scope param.
4. `test_oauth_callback_saves_granted_scopes` — mock token endpoint with compose; assert `OAuthToken.scope` contains compose.
5. `test_existing_token_without_compose_returns_can_draft_false` — list endpoint shows `can_draft=False`.
6. `test_reconnect_upgrades_scopes` — readonly token + simulated reconnect with compose → `can_draft=True`.

## QA Validation

1. New Gmail connection → consent screen lists "Create, read, update, delete drafts" → no pill.
2. Manually downgrade `OAuthToken.scope` to readonly → Hub shows amber pill.
3. Draft via Playground on stale connection → 409 → toast appears.
4. Click "Reconnect Gmail" → OAuth with compose → pill disappears → next draft succeeds.
5. Read-only operations unaffected on stale connections.
6. Multi-account: only stale integration shows pill.

## Summary

The bulk of infrastructure exists. Four targeted changes: add compose to `DEFAULT_SCOPES`, promote `PermissionError` to typed `InsufficientScopesError`, catch as 409, render pill + reconnect button. Lazy-upgrade for existing connections — first draft attempt prompts reconnect.
