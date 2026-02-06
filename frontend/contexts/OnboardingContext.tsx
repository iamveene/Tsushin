'use client'

/**
 * Onboarding Context
 * Phase 3: Frontend Onboarding Wizard
 *
 * Manages onboarding tour state, persistence, and navigation.
 * Auto-starts tour for first-time users, provides manual trigger option.
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

  // Load completion status from localStorage on mount
  useEffect(() => {
    const completed = localStorage.getItem(STORAGE_KEY) === 'true'
    setState(prev => ({ ...prev, hasCompletedOnboarding: completed }))
  }, [])

  // Auto-start tour for new users
  useEffect(() => {
    if (user && !state.hasCompletedOnboarding && !state.isActive) {
      // Small delay to let the app render first
      const timer = setTimeout(() => {
        startTour()
      }, 1000)
      return () => clearTimeout(timer)
    }
  }, [user, state.hasCompletedOnboarding, state.isActive])

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
      case 4: // Hub
        router.push('/hub')
        break
      case 5: // Flows
        router.push('/flows')
        break
      case 6: // Playground
        router.push('/playground')
        break
      case 7: // Communication Channels (stay on playground)
        break
      case 8: // Contact Management
        // Stay on current page, will have button to go to contacts
        break
      case 9: // Completion
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

    // Optionally sync to backend (if user preferences API exists)
    // syncPreferencesToBackend({ onboarding_completed: true })
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
