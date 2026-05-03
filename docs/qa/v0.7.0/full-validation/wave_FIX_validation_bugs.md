# Bug-Fix Validation — New Defects

## BUG-QA070-FIX-001 — Tour pill rehydrate does not display pill after reload (regression of A1-001)

**Severity:** Medium
**Component:** `frontend/contexts/OnboardingContext.tsx` + `frontend/components/OnboardingWizard.tsx`
**Discovered during:** V-001

### Summary

The `MINIMIZED_KEY_PREFIX` localStorage write in `minimize()` works as intended (`tsushin_onboarding_minimized:1=true` is stored and survives reload). However, the rehydrate path does not produce the expected visible state — after a reload, the user sees the FULL wizard modal at Step 1, not the "Continue Tour" pill.

### Reproduction

1. Login as `test@example.com`.
2. Click Help → Take Tour → wizard opens at Step 1 of 16.
3. Click `Minimize` button. Pill is shown at bottom-right ("Continue Tour 1/16"). LocalStorage now has `tsushin_onboarding_minimized:1=true` AND `tsushin_onboarding_started:1=true`.
4. Reload page (`browser_navigate https://localhost/`).
5. **Expected:** Pill is visible bottom-right; full modal NOT shown.
6. **Actual:** Full wizard modal renders covering the screen at Step 1 of 16. `pillCount=0`.

### Probable Root Cause

`OnboardingContext.tsx:233-237` rehydrates with `setState(prev => ({ ...prev, isActive: true, isMinimized: true }))` inside a `queueMicrotask`. Looking at the effect, this should produce `isActive=true, isMinimized=true`, which `OnboardingWizard.tsx:582` checks for to render the pill. The state update may be racing with the `1000ms` auto-start timer at line 242-272, which calls `setState` to set `isActive: true, isMinimized: false`. The guard at line 245 (`tourStartedRef.current`) is set to `previouslyStarted=true` at line 222, which SHOULD prevent the auto-start timer from firing — but the timer is still scheduled (line 243). If the rehydrate `queueMicrotask` somehow runs AFTER the timer's setState (unlikely but possible under React 18 strict mode double-effect), or the guard short-circuits before resetting, the wizard ends up at `isMinimized=false`.

Suggested investigation: add a `console.log` inside the rehydrate setState callback and inside the auto-start timer's setState to confirm execution order. Also consider moving the rehydrate state update OUT of `queueMicrotask` (synchronous setState) since localStorage reads are synchronous.

### Evidence

- See `wave_FIX_validation_evidence.md` row V-001
- Screenshot: `frontend/.playwright-mcp/v001-after-reload.png` (or root `v001-after-reload.png`)
- DOM scan: `pillCount=0`, `bodyText.includes('Continue Tour')=false`, `tsushin_onboarding_minimized:1=true` in localStorage.
