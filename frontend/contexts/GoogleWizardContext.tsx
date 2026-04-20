'use client'

/**
 * Google Wizard Context
 *
 * Hosts the Gmail and Google Calendar setup wizards globally so any page
 * can trigger them via `useGoogleWizard().openWizard('gmail' | 'calendar')`.
 *
 * The wizards themselves (GmailSetupWizard, GoogleCalendarSetupWizard) are
 * unmodified — they still own their own step state and OAuth polling. This
 * context only tracks which one is open and fans out onComplete callbacks
 * so consumer pages can refresh their local integration lists.
 */

import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  useRef,
  ReactNode,
} from 'react'
import dynamic from 'next/dynamic'

type WizardKind = 'gmail' | 'calendar'

interface GoogleWizardContextType {
  openWizard: (kind: WizardKind) => void
  closeWizard: () => void
  registerOnComplete: (kind: WizardKind, cb: () => void) => () => void
  activeKind: WizardKind | null
}

const GoogleWizardContext = createContext<GoogleWizardContextType | undefined>(undefined)

export function GoogleWizardProvider({ children }: { children: ReactNode }) {
  const [activeKind, setActiveKind] = useState<WizardKind | null>(null)
  const callbacksRef = useRef<Record<WizardKind, Set<() => void>>>({
    gmail: new Set(),
    calendar: new Set(),
  })

  const openWizard = useCallback((kind: WizardKind) => {
    setActiveKind(kind)
  }, [])

  const closeWizard = useCallback(() => {
    setActiveKind(null)
  }, [])

  const registerOnComplete = useCallback((kind: WizardKind, cb: () => void) => {
    callbacksRef.current[kind].add(cb)
    return () => {
      callbacksRef.current[kind].delete(cb)
    }
  }, [])

  const fireOnComplete = useCallback((kind: WizardKind) => {
    callbacksRef.current[kind].forEach(cb => {
      try { cb() } catch (e) { console.error('GoogleWizard onComplete callback failed', e) }
    })
  }, [])

  return (
    <GoogleWizardContext.Provider
      value={{ openWizard, closeWizard, registerOnComplete, activeKind }}
    >
      {children}
      <GoogleWizardHost
        activeKind={activeKind}
        onClose={closeWizard}
        onComplete={fireOnComplete}
      />
    </GoogleWizardContext.Provider>
  )
}

export function useGoogleWizard(): GoogleWizardContextType {
  const ctx = useContext(GoogleWizardContext)
  if (!ctx) {
    throw new Error('useGoogleWizard must be used within a GoogleWizardProvider')
  }
  return ctx
}

const GmailSetupWizard = dynamic(
  () => import('@/components/integrations/GmailSetupWizard'),
  { ssr: false },
)
const GoogleCalendarSetupWizard = dynamic(
  () => import('@/components/integrations/GoogleCalendarSetupWizard'),
  { ssr: false },
)

function GoogleWizardHost({
  activeKind,
  onClose,
  onComplete,
}: {
  activeKind: WizardKind | null
  onClose: () => void
  onComplete: (kind: WizardKind) => void
}) {
  // Keep each wizard mounted once opened so it can manage its own internal
  // reset via its own `isOpen` effect. We only render them when the kind
  // matches to keep the DOM light.
  return (
    <>
      <GmailSetupWizard
        isOpen={activeKind === 'gmail'}
        onClose={onClose}
        onComplete={() => onComplete('gmail')}
      />
      <GoogleCalendarSetupWizard
        isOpen={activeKind === 'calendar'}
        onClose={onClose}
        onComplete={() => onComplete('calendar')}
      />
    </>
  )
}

/**
 * Convenience hook that subscribes to wizard completion for the lifetime of
 * the calling component. Usage:
 *
 *   useGoogleWizardComplete('gmail', loadHubIntegrations)
 */
export function useGoogleWizardComplete(kind: WizardKind, cb: () => void) {
  const { registerOnComplete } = useGoogleWizard()
  const cbRef = useRef(cb)
  useEffect(() => { cbRef.current = cb }, [cb])
  useEffect(() => {
    return registerOnComplete(kind, () => cbRef.current())
  }, [kind, registerOnComplete])
}
