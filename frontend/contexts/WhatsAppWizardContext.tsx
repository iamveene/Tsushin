'use client'

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react'
import { api, WhatsAppMCPInstance, Contact } from '@/lib/client'

interface WizardState {
  isOpen: boolean
  currentStep: number
  totalSteps: number
  // Accumulated data from completed steps
  createdInstanceId: number | null
  createdInstance: WhatsAppMCPInstance | null
  configuredFilters: {
    group_filters?: string[]
    number_filters?: string[]
    group_keywords?: string[]
    dm_auto_mode?: boolean
  } | null
  createdContacts: Contact[]
  boundAgentId: number | null
  boundAgentName: string | null
  stepsCompleted: Record<number, boolean>
}

interface WhatsAppWizardContextType {
  state: WizardState
  openWizard: () => void
  closeWizard: () => void
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: number) => void
  setInstanceData: (instance: WhatsAppMCPInstance) => void
  setFiltersData: (filters: WizardState['configuredFilters']) => void
  addContact: (contact: Contact) => void
  setBoundAgent: (agentId: number, agentName: string) => void
  markStepComplete: (step: number) => void
}

const WhatsAppWizardContext = createContext<WhatsAppWizardContextType | undefined>(undefined)

const TOTAL_STEPS = 7
const DISMISSED_KEY = 'tsushin_whatsapp_wizard_dismissed'

const initialState: WizardState = {
  isOpen: false,
  currentStep: 1,
  totalSteps: TOTAL_STEPS,
  createdInstanceId: null,
  createdInstance: null,
  configuredFilters: null,
  createdContacts: [],
  boundAgentId: null,
  boundAgentName: null,
  stepsCompleted: {},
}

export function WhatsAppWizardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WizardState>(initialState)

  // Listen for onboarding completion to auto-launch wizard
  useEffect(() => {
    const handleOnboardingComplete = async () => {
      const dismissed = localStorage.getItem(DISMISSED_KEY) === 'true'
      if (dismissed) return

      try {
        const instances = await api.getMCPInstances()
        if (instances.length === 0) {
          // Auto-launch after 1s delay
          setTimeout(() => {
            setState(prev => ({ ...prev, isOpen: true, currentStep: 1 }))
          }, 1000)
        }
      } catch {
        // If API fails, don't auto-launch
      }
    }

    window.addEventListener('tsushin:onboarding-complete', handleOnboardingComplete)
    return () => window.removeEventListener('tsushin:onboarding-complete', handleOnboardingComplete)
  }, [])

  const openWizard = useCallback(() => {
    setState({ ...initialState, isOpen: true })
  }, [])

  const closeWizard = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: false }))
    localStorage.setItem(DISMISSED_KEY, 'true')
  }, [])

  const nextStep = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: Math.min(prev.currentStep + 1, TOTAL_STEPS),
    }))
  }, [])

  const previousStep = useCallback(() => {
    setState(prev => ({
      ...prev,
      currentStep: Math.max(prev.currentStep - 1, 1),
    }))
  }, [])

  const goToStep = useCallback((step: number) => {
    if (step < 1 || step > TOTAL_STEPS) return
    setState(prev => ({ ...prev, currentStep: step }))
  }, [])

  const setInstanceData = useCallback((instance: WhatsAppMCPInstance) => {
    setState(prev => ({
      ...prev,
      createdInstanceId: instance.id,
      createdInstance: instance,
      stepsCompleted: { ...prev.stepsCompleted, 2: true },
    }))
  }, [])

  const setFiltersData = useCallback((filters: WizardState['configuredFilters']) => {
    setState(prev => ({
      ...prev,
      configuredFilters: { ...prev.configuredFilters, ...filters },
    }))
  }, [])

  const addContact = useCallback((contact: Contact) => {
    setState(prev => ({
      ...prev,
      createdContacts: [...prev.createdContacts, contact],
    }))
  }, [])

  const setBoundAgent = useCallback((agentId: number, agentName: string) => {
    setState(prev => ({
      ...prev,
      boundAgentId: agentId,
      boundAgentName: agentName,
      stepsCompleted: { ...prev.stepsCompleted, 6: true },
    }))
  }, [])

  const markStepComplete = useCallback((step: number) => {
    setState(prev => ({
      ...prev,
      stepsCompleted: { ...prev.stepsCompleted, [step]: true },
    }))
  }, [])

  return (
    <WhatsAppWizardContext.Provider
      value={{
        state,
        openWizard,
        closeWizard,
        nextStep,
        previousStep,
        goToStep,
        setInstanceData,
        setFiltersData,
        addContact,
        setBoundAgent,
        markStepComplete,
      }}
    >
      {children}
    </WhatsAppWizardContext.Provider>
  )
}

export function useWhatsAppWizard(): WhatsAppWizardContextType {
  const context = useContext(WhatsAppWizardContext)
  if (context === undefined) {
    throw new Error('useWhatsAppWizard must be used within a WhatsAppWizardProvider')
  }
  return context
}
