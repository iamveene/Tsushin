'use client'

/**
 * Onboarding Context
 * Phase 3: Frontend Onboarding Wizard
 *
 * Manages onboarding tour state, persistence, and navigation.
 * The tour is a non-blocking helper — it never redirects users away from pages they navigate to.
 *
 * BUG-334: close/dismiss ALWAYS sets localStorage before any state updates.
 *           Escape key and close button both call dismissTour() for permanent dismissal.
 * BUG-325: auto-start is deferred if the User Guide panel is currently open.
 *           Uses a ref + event listener to avoid stale closure race conditions.
 * BUG-318: WhatsApp wizard auto-launch chain removed from here entirely.
 * BUG-319: TOTAL_STEPS reduced from 9 to 8 (step 9 duplicated GettingStartedChecklist).
 * v0.6.0:    TOTAL_STEPS raised from 8 to 12 — added four "What's New" showcase pages
 *            (expanded AI providers, new channels, custom skills/MCP, A2A + long-term memory).
 * v0.7.0:    TOTAL_STEPS raised to 16 through voice, Playground Mini,
 *            Sentinel, Triggers & Continuous Agents, and the existing finale.
 */

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react'
import { useAuth } from './AuthContext'

interface OnboardingState {
  isActive: boolean
  currentStep: number
  totalSteps: number
  isMinimized: boolean
  hasCompletedOnboarding: boolean
  isUserGuideOpen: boolean
}

interface OnboardingContextType {
  state: OnboardingState
  startTour: () => void
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: number) => void
  minimize: () => void
  maximize: () => void
  completeTour: () => void
  dismissTour: () => void
  skipTour: () => void
}

const OnboardingContext = createContext<OnboardingContextType | undefined>(undefined)

// BUG-319: Reduced from 9 to 8 (step 9 "Setup Checklist" removed — it duplicated GettingStartedChecklist)
// v0.6.0: Raised to 12 — added four "What's New in v0.6.0" showcase pages at the start
// v0.6.0 (Playground Mini): Raised to 13 — added a step highlighting the new floating Playground Mini bubble.
// v0.7.0-preview (Sentinel nudge): Raised to 14 — added a Sentinel/MemGuard block-mode toggle before the finale.
// v0.7.0 (Audio Agents wizard): Raised to 15 — added an optional "Voice Capabilities" step that launches the Audio Agents wizard.
// v0.7.0 (Triggers + Continuous Agents): Raised to 16 — added a read-only
// control-plane readiness step before the existing finale.
const TOTAL_STEPS = 16
const LEGACY_STORAGE_KEY = 'tsushin_onboarding_completed'
const STARTED_KEY_PREFIX = 'tsushin_onboarding_started'
const MINIMIZED_KEY_PREFIX = 'tsushin_onboarding_minimized'

function getStorageKey(userId: number | null): string | null {
  if (userId === null) {
    return null
  }
  return `${LEGACY_STORAGE_KEY}:${userId}`
}

function getStartedKey(storageKey: string): string {
  return storageKey.replace(LEGACY_STORAGE_KEY, STARTED_KEY_PREFIX)
}

function getMinimizedKey(storageKey: string): string {
  return storageKey.replace(LEGACY_STORAGE_KEY, MINIMIZED_KEY_PREFIX)
}

function getCompletedForUser(storageKey: string): boolean {
  if (localStorage.getItem(storageKey) === 'true') {
    return true
  }

  if (localStorage.getItem(LEGACY_STORAGE_KEY) === 'true') {
    localStorage.setItem(storageKey, 'true')
    localStorage.removeItem(LEGACY_STORAGE_KEY)
    return true
  }

  return false
}

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const userId = user?.id ?? null
  // Refs for values that need to be read in event handlers without stale closures
  const isUserGuideOpenRef = useRef(false)
  const tourStartedRef = useRef(false)
  const tourDismissedRef = useRef(false)
  const autoStartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeStorageKeyRef = useRef<string | null>(null)

  const [state, setState] = useState<OnboardingState>({
    isActive: false,
    currentStep: 1,
    totalSteps: TOTAL_STEPS,
    isMinimized: false,
    hasCompletedOnboarding: false,
    isUserGuideOpen: false,
  })

  const clearAutoStartTimer = () => {
    if (autoStartTimerRef.current) {
      clearTimeout(autoStartTimerRef.current)
      autoStartTimerRef.current = null
    }
  }

  // BUG-325: Track User Guide open state via refs + state
  // Using a ref avoids stale closure issues in event handlers and other effects
  useEffect(() => {
    const handleGuideOpen = () => {
      isUserGuideOpenRef.current = true
      setState(prev => ({ ...prev, isUserGuideOpen: true }))
    }
    const handleGuideClose = () => {
      isUserGuideOpenRef.current = false
      setState(prev => ({ ...prev, isUserGuideOpen: false }))

      // BUG-325: If tour should have started but was deferred because guide was open,
      // start it now that the guide is closed — but ONLY if tour hasn't been dismissed/completed.
      // Check refs (not stale closure state) to avoid race conditions.
      //
      // BUG-626 FIX: The previous guard only checked two refs. If the
      // provider remounts (tenant switch on a slow network, React Strict
      // Mode double-invoke in dev, or a route-level error boundary
      // recreating the tree), the refs are freshly ``false`` even though
      // localStorage has the completion marker from the last Skip. The
      // auto-start would then re-fire on the next guide-close and the
      // wizard would silently reappear. Treat ``localStorage`` as the
      // ultimate source of truth here — any completion / skip persisted
      // against the active user must block restart unconditionally.
      const storageKey = activeStorageKeyRef.current
      const persistedCompleted = storageKey ? getCompletedForUser(storageKey) : false
      if (persistedCompleted) {
        // Resync the ref so later checks agree with localStorage.
        tourDismissedRef.current = true
        return
      }
      if (!tourStartedRef.current && !tourDismissedRef.current) {
        tourStartedRef.current = true
        clearAutoStartTimer()
        autoStartTimerRef.current = setTimeout(() => {
          // Re-read localStorage one more time at fire-time — the user
          // may have hit Skip in the ~500 ms delay.
          const key = activeStorageKeyRef.current
          if (key && getCompletedForUser(key)) {
            tourDismissedRef.current = true
            return
          }
          setState(prev => {
            if (!prev.isActive && !prev.hasCompletedOnboarding) {
              return { ...prev, isActive: true, currentStep: 1, isMinimized: false }
            }
            return prev
          })
          autoStartTimerRef.current = null
        }, 500)
      }
    }
    window.addEventListener('tsushin:open-user-guide', handleGuideOpen)
    window.addEventListener('tsushin:close-user-guide', handleGuideClose)
    return () => {
      window.removeEventListener('tsushin:open-user-guide', handleGuideOpen)
      window.removeEventListener('tsushin:close-user-guide', handleGuideClose)
    }
  }, [])

  // Load completion status and auto-start tour for first-time users
  useEffect(() => {
    const storageKey = getStorageKey(userId)

    clearAutoStartTimer()

    if (!storageKey) {
      activeStorageKeyRef.current = null
      tourStartedRef.current = false
      tourDismissedRef.current = false
      queueMicrotask(() => {
        setState(prev => ({
          ...prev,
          isActive: false,
          isMinimized: false,
          hasCompletedOnboarding: false,
          currentStep: 1,
        }))
      })
      return
    }

    const previousStorageKey = activeStorageKeyRef.current
    activeStorageKeyRef.current = storageKey

    if (previousStorageKey !== storageKey) {
      tourStartedRef.current = false
      tourDismissedRef.current = false
      queueMicrotask(() => {
        setState(prev => ({
          ...prev,
          isActive: false,
          isMinimized: false,
          currentStep: 1,
        }))
      })
    }

    const completed = getCompletedForUser(storageKey)
    // BUG-QA070-A1-001: Restore minimized state so the pill survives page reloads.
    // The minimized key is set independently and is itself sufficient evidence the tour
    // was started — don't gate on previouslyStarted because manual launches via
    // startTour() do not persist the started key.
    const previouslyMinimized = !completed && localStorage.getItem(getMinimizedKey(storageKey)) === 'true'
    // BUG-536: Restore "started" state from localStorage so page reloads don't restart the tour
    const previouslyStarted = !completed && (previouslyMinimized || localStorage.getItem(getStartedKey(storageKey)) === 'true')

    tourDismissedRef.current = completed
    if (!completed) {
      tourStartedRef.current = previouslyStarted
    }
    queueMicrotask(() => {
      setState(prev => {
        const next = { ...prev }
        let changed = false
        if (prev.hasCompletedOnboarding !== completed) {
          next.hasCompletedOnboarding = completed
          changed = true
        }
        // BUG-QA070-A1-001: rehydrate active+minimized so the pill renders after reload
        if (previouslyMinimized && !prev.isMinimized) {
          next.isActive = true
          next.isMinimized = true
          changed = true
        }
        return changed ? next : prev
      })
    })

    if (!completed && userId !== null) {
      autoStartTimerRef.current = setTimeout(() => {
        // BUG-325: Don't auto-start if the User Guide is currently open (use ref, not stale state)
        if (isUserGuideOpenRef.current || tourStartedRef.current || tourDismissedRef.current) {
          // Guide is open, or the user already launched/dismissed the tour.
          return
        }
        // BUG-595: Final localStorage re-check at timer-fire time. The initial
        // `completed` capture above is a closure over the effect run; if the
        // user dismissed the tour on the home page and navigated to another
        // route before the 1s timer fired, the refs above may not be in sync
        // across context identity shifts — but localStorage always is. Treat
        // it as the source of truth so a dismissed tour NEVER re-opens just
        // because the user changed routes.
        const key = activeStorageKeyRef.current
        if (key && getCompletedForUser(key)) {
          tourDismissedRef.current = true
          return
        }
        tourStartedRef.current = true
        // BUG-536: Persist "started" state so page reloads don't restart the tour from scratch
        if (activeStorageKeyRef.current) {
          localStorage.setItem(getStartedKey(activeStorageKeyRef.current), 'true')
        }
        setState(prev => {
          if (!prev.hasCompletedOnboarding) {
            return { ...prev, isActive: true, currentStep: 1, isMinimized: false }
          }
          return prev
        })
      }, 1000)
      return () => clearAutoStartTimer()
    }
  }, [userId])

  const startTour = () => {
    clearAutoStartTimer()
    tourStartedRef.current = true
    tourDismissedRef.current = false
    // BUG-QA070-A1-001: Persist "started" so a reload-then-rehydrate path knows the
    // tour was launched (the auto-start timer also writes this — manual launches
    // need the same to survive reloads).
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(getStartedKey(storageKey), 'true')
      localStorage.removeItem(getMinimizedKey(storageKey))  // fresh launch is not minimized
    }
    setState(prev => ({
      ...prev,
      isActive: true,
      currentStep: 1,
      isMinimized: false,
      hasCompletedOnboarding: false,
    }))
  }

  const nextStep = () => {
    setState(prev => {
      const newStep = Math.min(prev.currentStep + 1, prev.totalSteps)
      return { ...prev, currentStep: newStep }
    })
  }

  const previousStep = () => {
    setState(prev => {
      const newStep = Math.max(prev.currentStep - 1, 1)
      return { ...prev, currentStep: newStep }
    })
  }

  const goToStep = (step: number) => {
    if (step < 1 || step > TOTAL_STEPS) return
    setState(prev => ({ ...prev, currentStep: step }))
  }

  const minimize = () => {
    // BUG-QA070-A1-001: Persist minimized state so the pill survives page reloads
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(getMinimizedKey(storageKey), 'true')
    }
    setState(prev => ({ ...prev, isMinimized: true }))
  }

  const maximize = () => {
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.removeItem(getMinimizedKey(storageKey))
    }
    setState(prev => ({ ...prev, isMinimized: false }))
  }

  // BUG-334: completeTour sets localStorage FIRST, then updates state
  const completeTour = () => {
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(storageKey, 'true')
      localStorage.removeItem(getStartedKey(storageKey))  // BUG-536: clear started flag
      localStorage.removeItem(getMinimizedKey(storageKey))  // BUG-QA070-A1-001: clear minimized flag too
    }
    tourDismissedRef.current = true
    clearAutoStartTimer()
    setState(prev => ({
      ...prev,
      isActive: false,
      hasCompletedOnboarding: true,
      currentStep: 1
    }))
    // NOTE: We intentionally do NOT dispatch 'tsushin:onboarding-complete' anymore.
    // BUG-318: WhatsApp wizard should not auto-launch after tour completes.
    // Users access the wizard via the Getting Started Checklist "Connect a Channel" item.
  }

  // BUG-334: dismissTour permanently dismisses — sets localStorage BEFORE state update
  const dismissTour = () => {
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(storageKey, 'true')
      localStorage.removeItem(getStartedKey(storageKey))  // BUG-536: clear started flag
      localStorage.removeItem(getMinimizedKey(storageKey))  // BUG-QA070-A1-001: clear minimized flag too
    }
    tourDismissedRef.current = true
    clearAutoStartTimer()
    setState(prev => ({
      ...prev,
      isActive: false,
      hasCompletedOnboarding: true,
      currentStep: 1
    }))
  }

  const skipTour = () => {
    // BUG-334: Set localStorage synchronously before state update — no confirm dialog (blocks browser events)
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(storageKey, 'true')
      localStorage.removeItem(getStartedKey(storageKey))  // BUG-536: clear started flag
      localStorage.removeItem(getMinimizedKey(storageKey))  // BUG-QA070-A1-001: clear minimized flag too
    }
    tourDismissedRef.current = true
    clearAutoStartTimer()
    setState(prev => ({
      ...prev,
      isActive: false,
      hasCompletedOnboarding: true,
      currentStep: 1
    }))
  }

  const value: OnboardingContextType = {
    state,
    startTour,
    nextStep,
    previousStep,
    goToStep,
    minimize,
    maximize,
    completeTour,
    dismissTour,
    skipTour
  }

  return (
    <OnboardingContext.Provider value={value}>
      {children}
    </OnboardingContext.Provider>
  )
}

export function useOnboarding(): OnboardingContextType {
  const context = useContext(OnboardingContext)
  if (context === undefined) {
    throw new Error('useOnboarding must be used within an OnboardingProvider')
  }
  return context
}
