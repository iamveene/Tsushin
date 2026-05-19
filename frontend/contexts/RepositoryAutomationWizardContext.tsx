'use client'

import React, { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'
import RepositoryAutomationWizard from '@/components/repository-automation/RepositoryAutomationWizard'
import type { RepositoryAutomationOpenOptions } from '@/lib/repository-automation'

interface RepositoryAutomationWizardContextType {
  openWizard: (options?: RepositoryAutomationOpenOptions) => void
  closeWizard: () => void
}

const RepositoryAutomationWizardContext = createContext<RepositoryAutomationWizardContextType | undefined>(undefined)

export function RepositoryAutomationWizardProvider({ children }: { children: ReactNode }) {
  const [options, setOptions] = useState<RepositoryAutomationOpenOptions | null>(null)
  const [isOpen, setIsOpen] = useState(false)

  const openWizard = useCallback((nextOptions: RepositoryAutomationOpenOptions = {}) => {
    setOptions(nextOptions)
    setIsOpen(true)
  }, [])

  const closeWizard = useCallback(() => {
    setIsOpen(false)
  }, [])

  const value = useMemo<RepositoryAutomationWizardContextType>(
    () => ({ openWizard, closeWizard }),
    [closeWizard, openWizard],
  )

  return (
    <RepositoryAutomationWizardContext.Provider value={value}>
      {children}
      <RepositoryAutomationWizard
        isOpen={isOpen}
        options={options}
        onClose={closeWizard}
      />
    </RepositoryAutomationWizardContext.Provider>
  )
}

export function useRepositoryAutomationWizard(): RepositoryAutomationWizardContextType {
  const ctx = useContext(RepositoryAutomationWizardContext)
  if (!ctx) {
    throw new Error('useRepositoryAutomationWizard must be used within RepositoryAutomationWizardProvider')
  }
  return ctx
}
