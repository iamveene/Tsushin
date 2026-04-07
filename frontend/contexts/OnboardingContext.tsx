'use client'

/**
 * Onboarding Context
 * Phase 3: Frontend Onboarding Wizard
 *
 * Manages onboarding tour state, persistence, and navigation.
 * The tour is a non-blocking helper — it never redirects users away from pages they navigate to.
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useAuth } from './AuthContext'

interface OnboardingState {
  isActive: boolean
  currentStep: number
  totalSteps: number
  isMinimized: boolean
  hasCompletedOnboarding: boolean
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
  skipTour: () => void
}

const OnboardingContext = createContext<OnboardingContextType | undefined>(undefined)

const TOTAL_STEPS = 9
const STORAGE_KEY = 'tsushin_onboarding_completed'

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()

  const [state, setState] = useState<OnboardingState>({
    isActive: false,
    currentStep: 1,
    totalSteps: TOTAL_STEPS,
    isMinimized: false,
    hasCompletedOnboarding: false
  })

  // Load completion status and auto-start tour for first-time users
  useEffect(() => {
    const completed = localStorage.getItem(STORAGE_KEY) === 'true'
    setState(prev => ({ ...prev, hasCompletedOnboarding: completed }))

    // Auto-start tour on first login (when user is loaded and tour not completed)
    if (!completed && user) {
      // Small delay to let the dashboard render first
      const timer = setTimeout(() => {
        setState(prev => ({ ...prev, isActive: true, currentStep: 1, isMinimized: false }))
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [user])

  const startTour = () => {
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
      return {
        ...prev,
        currentStep: newStep
      }
    })
  }

  const previousStep = () => {
    setState(prev => {
      const newStep = Math.max(prev.currentStep - 1, 1)
      return {
        ...prev,
        currentStep: newStep
      }
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

  const completeTour = () => {
    localStorage.setItem(STORAGE_KEY, 'true')
    setState(prev => ({
      ...prev,
      isActive: false,
      hasCompletedOnboarding: true,
      currentStep: 1
    }))

    // Signal to WhatsApp wizard that onboarding is complete
    window.dispatchEvent(new CustomEvent('tsushin:onboarding-complete'))
  }

  const skipTour = () => {
    const skipConfirm = window.confirm('Are you sure you want to skip the tour? You can restart it anytime by clicking the ? button in the header.')
    if (skipConfirm) {
      completeTour()
    }
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
