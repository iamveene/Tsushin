'use client'

import React, {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react'
import dynamic from 'next/dynamic'
import {
  INITIAL_TEAM_WIZARD_STATE,
  TEAM_WIZARD_STEPS,
  canAccessTeamStep,
  hasMeaningfulTeamDraft,
  normalizeTeamDraft,
  teamWizardReducer,
  type TeamMemberDraft,
  type TeamTemplateId,
  type TeamTriggerDraft,
  type TeamWizardDraft,
  type TeamWizardState,
  type TeamWizardStep,
} from '@/lib/team-wizard/reducer'

export const TEAM_WIZARD_DRAFT_STORAGE_KEY = 'tsushin.team_wizard.draft'

interface TeamWizardProgressPatch {
  message?: string
  status?: TeamWizardState['progressStatus']
}

export interface TeamWizardContextType {
  state: TeamWizardState
  steps: TeamWizardStep[]
  currentStepNumber: number
  totalSteps: number
  persistedDraft: TeamWizardDraft | null
  openWizard: (preset?: Partial<TeamWizardDraft>) => void
  closeWizard: () => void
  resetWizard: () => void
  nextStep: () => void
  previousStep: () => void
  goToStep: (step: TeamWizardStep) => void
  patchDraft: (patch: Partial<TeamWizardDraft>) => void
  applyTemplate: (templateId: TeamTemplateId) => void
  addMember: (member: Omit<TeamMemberDraft, 'execution_order'> & { execution_order?: number | null }) => void
  removeMember: (agentId: number) => void
  patchMember: (agentId: number, patch: Partial<TeamMemberDraft>) => void
  reorderMember: (agentId: number, direction: 'up' | 'down') => void
  setTools: (toolIds: number[]) => void
  addTrigger: (trigger: TeamTriggerDraft) => void
  removeTrigger: (uid: string) => void
  patchTrigger: (uid: string, patch: Partial<TeamTriggerDraft>) => void
  setProgress: (patch: TeamWizardProgressPatch) => void
  setCreatedTeam: (teamId: number) => void
  clearPersistedDraft: () => void
  canAccess: (step: TeamWizardStep) => boolean
  registerOnComplete: (cb: (teamId: number) => void) => () => void
  fireComplete: (teamId: number) => void
}

const TeamWizardContext = createContext<TeamWizardContextType | undefined>(undefined)

function readPersistedDraft(): TeamWizardDraft | null {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(TEAM_WIZARD_DRAFT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return normalizeTeamDraft(parsed as Partial<TeamWizardDraft>)
  } catch {
    return null
  }
}

function writePersistedDraft(draft: TeamWizardDraft | null) {
  if (typeof window === 'undefined') return
  try {
    if (draft && hasMeaningfulTeamDraft(draft)) {
      window.localStorage.setItem(TEAM_WIZARD_DRAFT_STORAGE_KEY, JSON.stringify(draft))
    } else {
      window.localStorage.removeItem(TEAM_WIZARD_DRAFT_STORAGE_KEY)
    }
  } catch {
    // Storage can be unavailable in private modes; the wizard still works.
  }
}

export function TeamWizardProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(teamWizardReducer, INITIAL_TEAM_WIZARD_STATE)
  const [persistedDraft, setPersistedDraft] = useState<TeamWizardDraft | null>(null)
  const callbacksRef = useRef<Set<(teamId: number) => void>>(new Set())
  const stateRef = useRef(state)
  stateRef.current = state

  useEffect(() => {
    setPersistedDraft(readPersistedDraft())
  }, [])

  useEffect(() => {
    if (!state.isOpen) return
    writePersistedDraft(state.draft)
    setPersistedDraft(hasMeaningfulTeamDraft(state.draft) ? state.draft : null)
  }, [state.draft, state.isOpen])

  const openWizard = useCallback((preset?: Partial<TeamWizardDraft>) => {
    const draft = preset ? normalizeTeamDraft(preset) : (persistedDraft ?? readPersistedDraft())
    dispatch({ type: 'OPEN', draft })
  }, [persistedDraft])

  const closeWizard = useCallback(() => {
    const latest = stateRef.current
    writePersistedDraft(latest.draft)
    setPersistedDraft(hasMeaningfulTeamDraft(latest.draft) ? latest.draft : null)
    dispatch({ type: 'CLOSE' })
  }, [])

  const resetWizard = useCallback(() => {
    writePersistedDraft(null)
    setPersistedDraft(null)
    dispatch({ type: 'RESET' })
  }, [])

  const nextStep = useCallback(() => dispatch({ type: 'NEXT' }), [])
  const previousStep = useCallback(() => dispatch({ type: 'PREV' }), [])
  const goToStep = useCallback((step: TeamWizardStep) => dispatch({ type: 'SET_STEP', step }), [])
  const patchDraft = useCallback((patch: Partial<TeamWizardDraft>) => dispatch({ type: 'PATCH_DRAFT', patch }), [])
  const applyTemplate = useCallback((templateId: TeamTemplateId) => dispatch({ type: 'APPLY_TEMPLATE', templateId }), [])
  const addMember = useCallback(
    (member: Omit<TeamMemberDraft, 'execution_order'> & { execution_order?: number | null }) =>
      dispatch({ type: 'ADD_MEMBER', member }),
    [],
  )
  const removeMember = useCallback((agentId: number) => dispatch({ type: 'REMOVE_MEMBER', agentId }), [])
  const patchMember = useCallback(
    (agentId: number, patch: Partial<TeamMemberDraft>) => dispatch({ type: 'PATCH_MEMBER', agentId, patch }),
    [],
  )
  const reorderMember = useCallback(
    (agentId: number, direction: 'up' | 'down') => dispatch({ type: 'REORDER_MEMBER', agentId, direction }),
    [],
  )
  const setTools = useCallback((toolIds: number[]) => dispatch({ type: 'SET_TOOLS', toolIds }), [])
  const addTrigger = useCallback((trigger: TeamTriggerDraft) => dispatch({ type: 'ADD_TRIGGER', trigger }), [])
  const removeTrigger = useCallback((uid: string) => dispatch({ type: 'REMOVE_TRIGGER', uid }), [])
  const patchTrigger = useCallback(
    (uid: string, patch: Partial<TeamTriggerDraft>) => dispatch({ type: 'PATCH_TRIGGER', uid, patch }),
    [],
  )
  const setProgress = useCallback((patch: TeamWizardProgressPatch) => dispatch({ type: 'SET_PROGRESS', ...patch }), [])
  const setCreatedTeam = useCallback((teamId: number) => dispatch({ type: 'SET_CREATED_TEAM', teamId }), [])

  const clearPersistedDraft = useCallback(() => {
    writePersistedDraft(null)
    setPersistedDraft(null)
  }, [])

  const canAccess = useCallback((step: TeamWizardStep) => canAccessTeamStep(state, step), [state])

  const registerOnComplete = useCallback((cb: (teamId: number) => void) => {
    callbacksRef.current.add(cb)
    return () => {
      callbacksRef.current.delete(cb)
    }
  }, [])

  const fireComplete = useCallback((teamId: number) => {
    writePersistedDraft(null)
    setPersistedDraft(null)
    callbacksRef.current.forEach((cb) => {
      try {
        cb(teamId)
      } catch (error) {
        console.error('TeamWizard onComplete callback failed', error)
      }
    })
  }, [])

  const currentStepNumber = useMemo(() => TEAM_WIZARD_STEPS.indexOf(state.currentStep) + 1, [state.currentStep])

  const value: TeamWizardContextType = {
    state,
    steps: TEAM_WIZARD_STEPS,
    currentStepNumber,
    totalSteps: TEAM_WIZARD_STEPS.length,
    persistedDraft,
    openWizard,
    closeWizard,
    resetWizard,
    nextStep,
    previousStep,
    goToStep,
    patchDraft,
    applyTemplate,
    addMember,
    removeMember,
    patchMember,
    reorderMember,
    setTools,
    addTrigger,
    removeTrigger,
    patchTrigger,
    setProgress,
    setCreatedTeam,
    clearPersistedDraft,
    canAccess,
    registerOnComplete,
    fireComplete,
  }

  return (
    <TeamWizardContext.Provider value={value}>
      {children}
      <TeamWizardHost />
    </TeamWizardContext.Provider>
  )
}

export function useTeamWizard(): TeamWizardContextType {
  const ctx = useContext(TeamWizardContext)
  if (!ctx) throw new Error('useTeamWizard must be used within a TeamWizardProvider')
  return ctx
}

export function useTeamWizardComplete(cb: (teamId: number) => void) {
  const { registerOnComplete } = useTeamWizard()
  const cbRef = useRef(cb)
  useEffect(() => {
    cbRef.current = cb
  }, [cb])
  useEffect(() => {
    return registerOnComplete((teamId) => cbRef.current(teamId))
  }, [registerOnComplete])
}

const TeamWizard = dynamic(
  () => import('@/components/team-wizard/TeamWizard'),
  { ssr: false },
)

function TeamWizardHost() {
  const { state } = useTeamWizard()
  if (!state.isOpen) return null
  return <TeamWizard />
}
