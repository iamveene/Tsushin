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
const TOTAL_STEPS = 8
const STORAGE_KEY = 'tsushin_onboarding_completed'

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  // Refs for values that need to be read in event handlers without stale closures
  const isUserGuideOpenRef = useRef(false)
  const tourStartedRef = useRef(false)
  const tourDismissedRef = useRef(false)

  const [state, setState] = useState<OnboardingState>({
    isActive: false,
    currentStep: 1,
    totalSteps: TOTAL_STEPS,
    isMinimized: false,
    hasCompletedOnboarding: false,
    isUserGuideOpen: false,
  })

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
        const completed = localStorage.getItem(STORAGE_KEY) === 'true'
        if (!completed) {
          tourStartedRef.current = true
          setTimeout(() => {
            setState(prev => {
              // Final check using prev state to be safe
              if (!prev.isActive && !prev.hasCompletedOnboarding) {
                return { ...prev, isActive: true, currentStep: 1, isMinimized: false }
              }
              return prev
            })
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
    const completed = localStorage.getItem(STORAGE_KEY) === 'true'
    if (completed) {
      tourDismissedRef.current = true
    }
    setState(prev => ({ ...prev, hasCompletedOnboarding: completed }))

    // Auto-start tour on first login (when user is loaded and tour not completed)
    if (!completed && user) {
      // Small delay to let the dashboard render first
      const timer = setTimeout(() => {
        // BUG-325: Don't auto-start if the User Guide is currently open (use ref, not stale state)
        if (isUserGuideOpenRef.current) {
          // Guide is open — deferred start will happen when guide closes (see handleGuideClose above)
          // Mark tourStartedRef as false so the deferred start knows to fire
          tourStartedRef.current = false
          return
        }
        tourStartedRef.current = true
        setState(prev => {
          if (!prev.hasCompletedOnboarding && !localStorage.getItem(STORAGE_KEY)) {
            return { ...prev, isActive: true, currentStep: 1, isMinimized: false }
          }
          return prev
        })
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [user])

  const startTour = () => {
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
    localStorage.setItem(STORAGE_KEY, 'true')
    tourDismissedRef.current = true
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
    localStorage.setItem(STORAGE_KEY, 'true')
    tourDismissedRef.current = true
    setState(prev => ({
      ...prev,
      isActive: false,
      hasCompletedOnboarding: true,
      currentStep: 1
    }))
  }

  const skipTour = () => {
    // BUG-334: Set localStorage synchronously before state update — no confirm dialog (blocks browser events)
    localStorage.setItem(STORAGE_KEY, 'true')
    tourDismissedRef.current = true
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
