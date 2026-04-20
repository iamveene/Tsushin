'use client'

/**
 * WhatsApp Wizard Context
 *
 * BUG-318: Removed auto-launch on 'tsushin:onboarding-complete' event.
 *           The WhatsApp wizard should only open when explicitly triggered by the user
 *           (via Getting Started Checklist or tour step 5 action button).
 * BUG-322: Added forceOpen() method that ignores the dismissed state — used by
 *           Getting Started Checklist "Connect a Channel" item so users can
 *           relaunch the wizard even after previously dismissing it.
 * BUG-321: Dispatches 'tsushin:whatsapp-wizard-closed' when wizard closes so the
 *           onboarding tour can advance to the next step.
 */

import React, { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { api, WhatsAppMCPInstance, Contact } from '@/lib/client'

interface WizardState {
  isOpen: boolean
  currentStep: number
  totalSteps: number
  // Accumulated data from completed steps
  createdInstanceId: number | null
  createdInstance: WhatsAppMCPInstance | null
  instanceDisplayName: string | null
  botContact: Contact | null
  userContact: Contact | null
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
  forceOpenWizard: () => void
  closeWizard: () => void
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: number) => void
  setInstanceData: (instance: WhatsAppMCPInstance) => void
  setInstanceDisplayName: (name: string) => void
  setBotContact: (contact: Contact) => void
  setUserContact: (contact: Contact) => void
  setFiltersData: (filters: WizardState['configuredFilters']) => void
  addContact: (contact: Contact) => void
  setBoundAgent: (agentId: number, agentName: string) => void
  markStepComplete: (step: number) => void
}

const WhatsAppWizardContext = createContext<WhatsAppWizardContextType | undefined>(undefined)

const TOTAL_STEPS = 8
const DISMISSED_KEY = 'tsushin_whatsapp_wizard_dismissed'

const initialState: WizardState = {
  isOpen: false,
  currentStep: 1,
  totalSteps: TOTAL_STEPS,
  createdInstanceId: null,
  createdInstance: null,
  instanceDisplayName: null,
  botContact: null,
  userContact: null,
  configuredFilters: null,
  createdContacts: [],
  boundAgentId: null,
  boundAgentName: null,
  stepsCompleted: {},
}

export function WhatsAppWizardProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<WizardState>(initialState)

  // BUG-318: Removed the 'tsushin:onboarding-complete' auto-launch listener.
  // The wizard no longer auto-starts after the onboarding tour completes.
  // Users access the wizard explicitly via:
  //   (a) Getting Started Checklist "Connect a Channel" item (uses forceOpenWizard)
  //   (b) Tour Step 5 "Set Up Channels" action button (uses openWizard)

  // openWizard: respects dismissed state (won't reopen if user previously dismissed)
  const openWizard = useCallback(() => {
    const dismissed = localStorage.getItem(DISMISSED_KEY) === 'true'
    if (dismissed) return
    setState({ ...initialState, isOpen: true })
  }, [])

  // BUG-322: forceOpenWizard: ignores dismissed state — used from Getting Started Checklist
  const forceOpenWizard = useCallback(() => {
    // Clear dismissed flag so the wizard can function normally after force-open
    localStorage.removeItem(DISMISSED_KEY)
    setState({ ...initialState, isOpen: true })
  }, [])

  // BUG-321: closeWizard dispatches event so onboarding tour can advance step
  const closeWizard = useCallback(() => {
    setState(prev => ({ ...prev, isOpen: false }))
    localStorage.setItem(DISMISSED_KEY, 'true')
    // Signal to onboarding tour that wizard was closed (BUG-321)
    window.dispatchEvent(new CustomEvent('tsushin:whatsapp-wizard-closed'))
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
    // BUG-591: Do NOT mark step 2 complete here. Instance creation alone
    // does not mean WhatsApp is authenticated — the QR still needs to be
    // scanned. Step 2 is marked complete by StepCreateInstance only after
    // health polling confirms `authenticated=true`.
    setState(prev => ({
      ...prev,
      createdInstanceId: instance.id,
      createdInstance: instance,
    }))
  }, [])

  const setInstanceDisplayName = useCallback((name: string) => {
    setState(prev => ({ ...prev, instanceDisplayName: name }))
  }, [])

  const setBotContact = useCallback((contact: Contact) => {
    setState(prev => ({ ...prev, botContact: contact }))
  }, [])

  const setUserContact = useCallback((contact: Contact) => {
    setState(prev => ({ ...prev, userContact: contact }))
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
      stepsCompleted: { ...prev.stepsCompleted, 7: true },
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
        forceOpenWizard,
        closeWizard,
        nextStep,
        previousStep,
        goToStep,
        setInstanceData,
        setInstanceDisplayName,
        setBotContact,
        setUserContact,
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
