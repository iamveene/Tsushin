### BUG-QA070-A1-001 — Onboarding tour minimized pill not visible after page reload

- **Severity:** medium
- **Category:** wizards
- **Surface:** `frontend/components/OnboardingWizard.tsx`, post-login dashboard
- **Repro steps:**
  1. Login as `test@example.com` with fresh tour state (clear `localStorage.onboarding:tour:*`)
  2. Walk to step 7 of the 16-step tour
  3. Click the minimize button
  4. Confirm pill is visible in the corner
  5. Reload the page (F5)
- **Expected:** Minimized "Continue tour" pill remains visible in the corner after reload (state persists across navigation).
- **Actual:** No pill visible after reload — tour appears fully closed despite minimized state being set.
- **Evidence:** `screenshots/W-002-minimized-step7.png` (minimized state pre-reload), `screenshots/W-002-after-reload.png` and `screenshots/W-002-FAIL-no-pill-after-reload.png` (post-reload — pill missing).
- **Reported by:** Wave A1
- **Suggested fix area:** Hydration of `onboarding:tour:minimized` localStorage key in OnboardingWizard mount effect. Likely the mount logic checks `dismissed` flag but not `minimized`, so a minimized-but-not-dismissed tour falls through to "hide entirely".
