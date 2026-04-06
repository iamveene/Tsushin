'use client'

/**
 * Onboarding Context
 * Phase 3: Frontend Onboarding Wizard
 *
 * Manages onboarding tour state, persistence, and navigation.
 * Tour only starts when the user explicitly triggers it (no auto-start).
 */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useRouter } from 'next/navigation'
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
  const router = useRouter()

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

      // Auto-navigate to pages based on step
      navigateToStep(newStep)

      return {
        ...prev,
        currentStep: newStep
      }
    })
  }

  const previousStep = () => {
    setState(prev => {
      const newStep = Math.max(prev.currentStep - 1, 1)

      // Auto-navigate to pages based on step
      navigateToStep(newStep)

      return {
        ...prev,
        currentStep: newStep
      }
    })
  }

  const goToStep = (step: number) => {
    if (step < 1 || step > TOTAL_STEPS) return

    setState(prev => ({ ...prev, currentStep: step }))
    navigateToStep(step)
  }

  const navigateToStep = (step: number) => {
    // Navigate to appropriate page based on step
    switch (step) {
      case 1: // Welcome
        // Stay on current page
        break
      case 2: // Watcher
        router.push('/')
        break
      case 3: // Studio
        router.push('/agents')
        break
      case 4: // Hub - AI Providers & System AI
        router.push('/hub')
        break
      case 5: // Communication Channels (Required)
        router.push('/hub')
        break
      case 6: // Flows
        router.push('/flows')
        break
      case 7: // Playground
        router.push('/playground')
        break
      case 8: // Security & API Access
        // Stay on current page
        break
      case 9: // Setup Checklist
        // Stay on current page
        break
    }
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
