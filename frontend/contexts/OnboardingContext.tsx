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
const TOTAL_STEPS = 12
const LEGACY_STORAGE_KEY = 'tsushin_onboarding_completed'
const STARTED_KEY_PREFIX = 'tsushin_onboarding_started'

function getStorageKey(userId: number | null): string | null {
  if (userId === null) {
    return null
  }
  return `${LEGACY_STORAGE_KEY}:${userId}`
}

function getStartedKey(storageKey: string): string {
  return storageKey.replace(LEGACY_STORAGE_KEY, STARTED_KEY_PREFIX)
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
      if (!tourStartedRef.current && !tourDismissedRef.current) {
        const storageKey = activeStorageKeyRef.current
        const completed = storageKey ? getCompletedForUser(storageKey) : false
        if (!completed) {
          tourStartedRef.current = true
          clearAutoStartTimer()
          autoStartTimerRef.current = setTimeout(() => {
            setState(prev => {
              // Final check using prev state to be safe
              if (!prev.isActive && !prev.hasCompletedOnboarding) {
                return { ...prev, isActive: true, currentStep: 1, isMinimized: false }
              }
              return prev
            })
            autoStartTimerRef.current = null
          }, 500)
        }
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
    // BUG-536: Restore "started" state from localStorage so page reloads don't restart the tour
    const previouslyStarted = !completed && localStorage.getItem(getStartedKey(storageKey)) === 'true'

    tourDismissedRef.current = completed
    if (!completed) {
      tourStartedRef.current = previouslyStarted
    }
    queueMicrotask(() => {
      setState(prev => {
        if (prev.hasCompletedOnboarding === completed) {
          return prev
        }
        return { ...prev, hasCompletedOnboarding: completed }
      })
    })

    if (!completed && userId !== null) {
      autoStartTimerRef.current = setTimeout(() => {
        // BUG-325: Don't auto-start if the User Guide is currently open (use ref, not stale state)
        if (isUserGuideOpenRef.current || tourStartedRef.current || tourDismissedRef.current) {
          // Guide is open, or the user already launched/dismissed the tour.
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
    setState(prev => ({
      ...prev,
      isActive: true,
      currentStep: 1,
      isMinimized: false
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
    setState(prev => ({ ...prev, isMinimized: true }))
  }

  const maximize = () => {
    setState(prev => ({ ...prev, isMinimized: false }))
  }

  // BUG-334: completeTour sets localStorage FIRST, then updates state
  const completeTour = () => {
    const storageKey = activeStorageKeyRef.current
    if (storageKey) {
      localStorage.setItem(storageKey, 'true')
      localStorage.removeItem(getStartedKey(storageKey))  // BUG-536: clear started flag
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
