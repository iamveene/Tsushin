'use client'

/**
 * Audio Wizard Context
 *
 * Hosts the AudioAgentsWizard globally so any page (Studio, Hub, onboarding
 * tour, dashboard checklist) can trigger it via `useAudioWizard().openWizard()`.
 *
 * The wizard owns its own step state; this context only tracks whether it's
 * open and fans out `registerOnComplete` callbacks so consumer pages can
 * refresh their local agent/TTS lists after provisioning finishes.
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

export type AudioAgentType = 'voice' | 'transcript' | 'hybrid'
export type AudioWizardMode = 'new' | 'existing'

export interface AudioWizardOpenOptions {
  presetProvider?: 'kokoro' | 'openai' | 'elevenlabs'
  presetAgentId?: number
  presetMode?: AudioWizardMode
  presetAgentType?: AudioAgentType
  presetNewAgentName?: string
}

interface AudioWizardContextType {
  isOpen: boolean
  openWizard: (opts?: AudioWizardOpenOptions) => void
  closeWizard: () => void
  registerOnComplete: (cb: () => void) => () => void
  openOptions: AudioWizardOpenOptions
}

const AudioWizardContext = createContext<AudioWizardContextType | undefined>(undefined)

export function AudioWizardProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const [openOptions, setOpenOptions] = useState<AudioWizardOpenOptions>({})
  const callbacksRef = useRef<Set<() => void>>(new Set())

  const openWizard = useCallback((opts?: AudioWizardOpenOptions) => {
    setOpenOptions(opts || {})
    setIsOpen(true)
  }, [])

  const closeWizard = useCallback(() => {
    setIsOpen(false)
    window.dispatchEvent(new CustomEvent('tsushin:audio-wizard-closed'))
  }, [])

  const registerOnComplete = useCallback((cb: () => void) => {
    callbacksRef.current.add(cb)
    return () => {
      callbacksRef.current.delete(cb)
    }
  }, [])

  const fireOnComplete = useCallback(() => {
    callbacksRef.current.forEach(cb => {
      try { cb() } catch (e) { console.error('AudioWizard onComplete callback failed', e) }
    })
  }, [])

  return (
    <AudioWizardContext.Provider
      value={{ isOpen, openWizard, closeWizard, registerOnComplete, openOptions }}
    >
      {children}
      <AudioWizardHost
        isOpen={isOpen}
        onClose={closeWizard}
        onComplete={fireOnComplete}
        options={openOptions}
      />
    </AudioWizardContext.Provider>
  )
}

export function useAudioWizard(): AudioWizardContextType {
  const ctx = useContext(AudioWizardContext)
  if (!ctx) {
    throw new Error('useAudioWizard must be used within an AudioWizardProvider')
  }
  return ctx
}

const AudioAgentsWizard = dynamic(
  () => import('@/components/audio-wizard/AudioAgentsWizard'),
  { ssr: false },
)

function AudioWizardHost({
  isOpen,
  onClose,
  onComplete,
  options,
}: {
  isOpen: boolean
  onClose: () => void
  onComplete: () => void
  options: AudioWizardOpenOptions
}) {
  return (
    <AudioAgentsWizard
      isOpen={isOpen}
      onClose={onClose}
      onComplete={onComplete}
      options={options}
    />
  )
}

/**
 * Subscribe to wizard completion for the lifetime of the calling component.
 * Usage:
 *   useAudioWizardComplete(() => reloadAgents())
 */
export function useAudioWizardComplete(cb: () => void) {
  const { registerOnComplete } = useAudioWizard()
  const cbRef = useRef(cb)
  useEffect(() => { cbRef.current = cb }, [cb])
  useEffect(() => {
    return registerOnComplete(() => cbRef.current())
  }, [registerOnComplete])
}
