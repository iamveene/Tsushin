'use client'

/**
 * Provider Wizard Context
 *
 * Hosts the ProviderWizard globally so the Hub (or any other surface) can
 * trigger it via `useProviderWizard().openWizard()`. The context owns the
 * full draft so that switching from Guided → Advanced mode preserves the
 * non-secret fields the user already entered — the legacy
 * `ProviderInstanceModal` can read `draft` and pre-fill its inputs.
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
  getStepOrder,
  getStepIndex,
  getTotalSteps,
  canAccessStep,
} from '@/lib/provider-wizard/reducer'

const DRAFT_STORAGE_KEY = 'tsushin:providerWizardDraft'
const MODE_STORAGE_KEY = 'tsushin:providerWizardMode'

export type ProviderWizardMode = 'guided' | 'advanced'

export interface ProviderWizardContextType {
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
  patchDraft: (patch: Partial<WizardDraft>) => void
  setProgress: (p: { message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }) => void
  canAccess: (step: StepKey) => boolean
  registerOnComplete: (cb: (instanceId: number | null) => void) => () => void
  fireComplete: (instanceId: number | null) => void
  /** Persisted draft (minus secrets) from a prior Guided session. */
  persistedDraft: WizardDraft | null
  clearPersistedDraft: () => void
  getMode: () => ProviderWizardMode
  setMode: (mode: ProviderWizardMode) => void
}

const ProviderWizardContext = createContext<ProviderWizardContextType | undefined>(undefined)

/**
 * Strip secrets from the draft before persisting. We never write api_key or
 * any Vertex AI private_key to localStorage — even if the browser is private,
 * the user's expectation is that a page refresh does not preserve credentials.
 */
function sanitizeDraftForStorage(draft: WizardDraft): WizardDraft {
  const nextExtra = { ...(draft.extra_config || {}) }
  if ('private_key' in nextExtra) delete nextExtra.private_key
  return {
    ...draft,
    api_key: '',
    extra_config: nextExtra,
  }
}

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
      window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(sanitizeDraftForStorage(draft)))
    }
  } catch {
    /* ignore quota / disabled storage */
  }
}

export function ProviderWizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, INITIAL_STATE)
  const callbacksRef = useRef<Set<(instanceId: number | null) => void>>(new Set())
  const persistedDraftRef = useRef<WizardDraft | null>(null)
  const stateRef = useRef(state)
  stateRef.current = state

  useEffect(() => {
    persistedDraftRef.current = readPersistedDraft()
  }, [])

  const openWizard = useCallback((preset?: Partial<WizardDraft>) => {
    dispatch({ type: 'OPEN', preset })
  }, [])

  const closeWizard = useCallback(() => {
    const latest = stateRef.current
    // Only persist if the user has made meaningful progress — a bare open/close
    // should not seed the "continue where you left off" state.
    if (latest.draft.vendor || latest.draft.modality) {
      writePersistedDraft(latest.draft)
      persistedDraftRef.current = sanitizeDraftForStorage(latest.draft)
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
  const patchDraft = useCallback((patch: Partial<WizardDraft>) => dispatch({ type: 'PATCH_DRAFT', patch }), [])
  const setProgress = useCallback(
    (p: { message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }) =>
      dispatch({ type: 'SET_PROGRESS', ...p }),
    [],
  )

  const canAccess = useCallback((step: StepKey) => canAccessStep(state, step), [state])

  const registerOnComplete = useCallback((cb: (instanceId: number | null) => void) => {
    callbacksRef.current.add(cb)
    return () => {
      callbacksRef.current.delete(cb)
    }
  }, [])

  const fireComplete = useCallback((instanceId: number | null) => {
    writePersistedDraft(null)
    persistedDraftRef.current = null
    callbacksRef.current.forEach(cb => {
      try { cb(instanceId) } catch (e) { console.error('ProviderWizard onComplete callback failed', e) }
    })
  }, [])

  const clearPersistedDraft = useCallback(() => {
    writePersistedDraft(null)
    persistedDraftRef.current = null
  }, [])

  const getMode = useCallback((): ProviderWizardMode => {
    if (typeof window === 'undefined') return 'guided'
    const raw = window.localStorage.getItem(MODE_STORAGE_KEY)
    return raw === 'advanced' ? 'advanced' : 'guided'
  }, [])

  const setMode = useCallback((mode: ProviderWizardMode) => {
    if (typeof window === 'undefined') return
    try { window.localStorage.setItem(MODE_STORAGE_KEY, mode) } catch { /* ignore */ }
  }, [])

  const stepOrder = useMemo(() => getStepOrder(state.draft), [state.draft])
  const totalSteps = useMemo(() => getTotalSteps(state), [state])
  const stepIndex = useMemo(() => getStepIndex(state), [state])

  const value: ProviderWizardContextType = {
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
    patchDraft,
    setProgress,
    canAccess,
    registerOnComplete,
    fireComplete,
    persistedDraft: persistedDraftRef.current,
    clearPersistedDraft,
    getMode,
    setMode,
  }

  return (
    <ProviderWizardContext.Provider value={value}>
      {children}
      <ProviderWizardHost />
    </ProviderWizardContext.Provider>
  )
}

export function useProviderWizard(): ProviderWizardContextType {
  const ctx = useContext(ProviderWizardContext)
  if (!ctx) throw new Error('useProviderWizard must be used within a ProviderWizardProvider')
  return ctx
}

/** Subscribe to wizard completion for the lifetime of the calling component. */
export function useProviderWizardComplete(cb: (instanceId: number | null) => void) {
  const { registerOnComplete } = useProviderWizard()
  const cbRef = useRef(cb)
  useEffect(() => { cbRef.current = cb }, [cb])
  useEffect(() => {
    return registerOnComplete((id) => cbRef.current(id))
  }, [registerOnComplete])
}

const ProviderWizard = dynamic(
  () => import('@/components/provider-wizard/ProviderWizard'),
  { ssr: false },
)

function ProviderWizardHost() {
  const { state } = useProviderWizard()
  if (!state.isOpen) return null
  return <ProviderWizard />
}
