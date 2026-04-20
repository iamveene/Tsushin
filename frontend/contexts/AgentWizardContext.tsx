'use client'

/**
 * Agent Wizard Context
 *
 * Hosts the AgentWizard globally so the agents page (or any other surface)
 * can trigger it via `useAgentWizard().openWizard()`. The context owns the
 * full draft so that switching from Guided → Advanced mode preserves state —
 * the legacy single-form modal can read `draft` and pre-fill its fields.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  ReactNode,
} from 'react'
import dynamic from 'next/dynamic'
import {
  INITIAL_STATE,
  reducer,
  type WizardDraft,
  type WizardState,
  type StepKey,
  type AgentType,
  type BasicsConfig,
  type PersonalityConfig,
  type AudioConfig,
  type SkillsConfig,
  type MemoryConfig,
  getStepOrder,
  getStepIndex,
  getTotalSteps,
  canAccessStep,
} from '@/lib/agent-wizard/reducer'

const DRAFT_STORAGE_KEY = 'tsushin:agentWizardDraft'
const MODE_STORAGE_KEY = 'tsushin:agentWizardMode'

export type AgentWizardMode = 'guided' | 'advanced'

export interface AgentWizardContextType {
  state: WizardState
  stepOrder: StepKey[]
  totalSteps: number
  stepIndex: number
  openWizard: (preset?: Partial<WizardDraft>) => void
  closeWizard: () => void
  resetWizard: () => void
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: StepKey) => void
  markStepComplete: (step: StepKey, complete?: boolean) => void
  setType: (type: AgentType) => void
  patchBasics: (patch: Partial<BasicsConfig>) => void
  patchPersonality: (patch: Partial<PersonalityConfig>) => void
  patchAudio: (patch: Partial<AudioConfig>) => void
  patchSkills: (patch: Partial<SkillsConfig>) => void
  patchMemory: (patch: Partial<MemoryConfig>) => void
  setChannels: (channels: string[]) => void
  loadDraft: (draft: Partial<WizardDraft>) => void
  setProgress: (p: { message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }) => void
  setCreatedAgent: (agentId: number) => void
  canAccess: (step: StepKey) => boolean
  registerOnComplete: (cb: (agentId: number) => void) => () => void
  fireComplete: (agentId: number) => void
  /** Persisted draft from a prior Guided session (readable by the Advanced modal for pre-fill). */
  persistedDraft: WizardDraft | null
  clearPersistedDraft: () => void
  getMode: () => AgentWizardMode
  setMode: (mode: AgentWizardMode) => void
}

const AgentWizardContext = createContext<AgentWizardContextType | undefined>(undefined)

function readPersistedDraft(): WizardDraft | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(DRAFT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed as WizardDraft
  } catch {
    return null
  }
}

function writePersistedDraft(draft: WizardDraft | null) {
  if (typeof window === 'undefined') return
  try {
    if (draft === null) {
      window.localStorage.removeItem(DRAFT_STORAGE_KEY)
    } else {
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft))
    }
  } catch {
    /* ignore quota / disabled storage */
  }
}

export function AgentWizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const callbacksRef = useRef<Set<(agentId: number) => void>>(new Set())
  const persistedDraftRef = useRef<WizardDraft | null>(null)
  const stateRef = useRef(state)
  stateRef.current = state

  // Read the persisted draft once on mount (client-side only).
  useEffect(() => {
    persistedDraftRef.current = readPersistedDraft()
  }, [])

  const openWizard = useCallback((preset?: Partial<WizardDraft>) => {
    dispatch({ type: 'OPEN', preset })
  }, [])

  const closeWizard = useCallback(() => {
    // Read the latest state via the ref so this callback stays correct even
    // when a consumer captured it from an earlier render.
    const latest = stateRef.current
    if (latest.draft.type) {
      writePersistedDraft(latest.draft)
      persistedDraftRef.current = latest.draft
    }
    dispatch({ type: 'CLOSE' })
  }, [])

  const resetWizard = useCallback(() => {
    writePersistedDraft(null)
    persistedDraftRef.current = null
    dispatch({ type: 'RESET' })
  }, [])

  const nextStep = useCallback(() => dispatch({ type: 'NEXT' }), [])
  const previousStep = useCallback(() => dispatch({ type: 'PREV' }), [])
  const goToStep = useCallback((step: StepKey) => dispatch({ type: 'SET_STEP', step }), [])
  const markStepComplete = useCallback(
    (step: StepKey, complete = true) => dispatch({ type: 'MARK_STEP_COMPLETE', step, complete }),
    [],
  )
  const setType = useCallback((agentType: AgentType) => dispatch({ type: 'SET_TYPE', agentType }), [])
  const patchBasics = useCallback((patch: Partial<BasicsConfig>) => dispatch({ type: 'PATCH_BASICS', patch }), [])
  const patchPersonality = useCallback((patch: Partial<PersonalityConfig>) => dispatch({ type: 'PATCH_PERSONALITY', patch }), [])
  const patchAudio = useCallback((patch: Partial<AudioConfig>) => dispatch({ type: 'PATCH_AUDIO', patch }), [])
  const patchSkills = useCallback((patch: Partial<SkillsConfig>) => dispatch({ type: 'PATCH_SKILLS', patch }), [])
  const patchMemory = useCallback((patch: Partial<MemoryConfig>) => dispatch({ type: 'PATCH_MEMORY', patch }), [])
  const setChannels = useCallback((channels: string[]) => dispatch({ type: 'SET_CHANNELS', channels }), [])
  const loadDraft = useCallback((draft: Partial<WizardDraft>) => dispatch({ type: 'LOAD_DRAFT', draft }), [])
  const setProgress = useCallback(
    (p: { message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }) =>
      dispatch({ type: 'SET_PROGRESS', ...p }),
    [],
  )
  const setCreatedAgent = useCallback((agentId: number) => dispatch({ type: 'SET_CREATED_AGENT', agentId }), [])

  const canAccess = useCallback((step: StepKey) => canAccessStep(state, step), [state])

  const registerOnComplete = useCallback((cb: (agentId: number) => void) => {
    callbacksRef.current.add(cb)
    return () => {
      callbacksRef.current.delete(cb)
    }
  }, [])

  const fireComplete = useCallback((agentId: number) => {
    // Clear persisted draft — the wizard finished successfully.
    writePersistedDraft(null)
    persistedDraftRef.current = null
    callbacksRef.current.forEach(cb => {
      try { cb(agentId) } catch (e) { console.error('AgentWizard onComplete callback failed', e) }
    })
  }, [])

  const clearPersistedDraft = useCallback(() => {
    writePersistedDraft(null)
    persistedDraftRef.current = null
  }, [])

  const getMode = useCallback((): AgentWizardMode => {
    if (typeof window === 'undefined') return 'guided'
    const raw = window.localStorage.getItem(MODE_STORAGE_KEY)
    return raw === 'advanced' ? 'advanced' : 'guided'
  }, [])

  const setMode = useCallback((mode: AgentWizardMode) => {
    if (typeof window === 'undefined') return
    try { window.localStorage.setItem(MODE_STORAGE_KEY, mode) } catch { /* ignore */ }
  }, [])

  const stepOrder = useMemo(() => getStepOrder(state.draft.type), [state.draft.type])
  const totalSteps = useMemo(() => getTotalSteps(state), [state])
  const stepIndex = useMemo(() => getStepIndex(state), [state])

  const value: AgentWizardContextType = {
    state,
    stepOrder,
    totalSteps,
    stepIndex,
    openWizard,
    closeWizard,
    resetWizard,
    nextStep,
    previousStep,
    goToStep,
    markStepComplete,
    setType,
    patchBasics,
    patchPersonality,
    patchAudio,
    patchSkills,
    patchMemory,
    setChannels,
    loadDraft,
    setProgress,
    setCreatedAgent,
    canAccess,
    registerOnComplete,
    fireComplete,
    persistedDraft: persistedDraftRef.current,
    clearPersistedDraft,
    getMode,
    setMode,
  }

  return (
    <AgentWizardContext.Provider value={value}>
      {children}
      <AgentWizardHost />
    </AgentWizardContext.Provider>
  )
}

export function useAgentWizard(): AgentWizardContextType {
  const ctx = useContext(AgentWizardContext)
  if (!ctx) throw new Error('useAgentWizard must be used within an AgentWizardProvider')
  return ctx
}

/** Subscribe to wizard completion for the lifetime of the calling component. */
export function useAgentWizardComplete(cb: (agentId: number) => void) {
  const { registerOnComplete } = useAgentWizard()
  const cbRef = useRef(cb)
  useEffect(() => { cbRef.current = cb }, [cb])
  useEffect(() => {
    return registerOnComplete((id) => cbRef.current(id))
  }, [registerOnComplete])
}

const AgentWizard = dynamic(
  () => import('@/components/agent-wizard/AgentWizard'),
  { ssr: false },
)

function AgentWizardHost() {
  const { state } = useAgentWizard()
  if (!state.isOpen) return null
  return <AgentWizard />
}
