export type TeamWizardStep =
  | 'template'
  | 'basics'
  | 'topology'
  | 'members'
  | 'triggers'
  | 'review'
  | 'create'

export type TeamTemplateId = 'custom' | 'incident_triage' | 'release_review' | 'research_synthesis'
export type TeamTopologyDraft = 'line' | 'mesh'
export type TeamStatusDraft = 'draft' | 'active' | 'paused'
export type TeamTriggerDraftKind = 'webhook' | 'github' | 'jira'

export interface TeamMemberDraft {
  agent_id: number
  execution_order: number
  is_required: boolean
  position_x: number | null
  position_y: number | null
}

export interface TeamTriggerDraft {
  uid: string
  trigger_kind: TeamTriggerDraftKind
  trigger_instance_id: number
  event_types: string[]
  filters_text: string
  is_enabled: boolean
  label: string
}

export interface TeamWizardDraft {
  template_id: TeamTemplateId
  name: string
  description: string
  goal_text: string
  topology: TeamTopologyDraft
  status: TeamStatusDraft
  max_steps: number
  max_total_tokens: number | null
  max_concurrent_runs: number
  members: TeamMemberDraft[]
  triggers: TeamTriggerDraft[]
}

export interface TeamWizardState {
  isOpen: boolean
  currentStep: TeamWizardStep
  draft: TeamWizardDraft
  stepsCompleted: Record<TeamWizardStep, boolean>
  progressMessage: string
  progressStatus: 'idle' | 'running' | 'done' | 'error'
  createdTeamId: number | null
}

export interface TeamTemplatePreset {
  id: TeamTemplateId
  name: string
  description: string
  draft: Partial<TeamWizardDraft>
}

export const TEAM_WIZARD_STEPS: TeamWizardStep[] = [
  'template',
  'basics',
  'topology',
  'members',
  'triggers',
  'review',
  'create',
]

export const EMPTY_TEAM_DRAFT: TeamWizardDraft = {
  template_id: 'custom',
  name: '',
  description: '',
  goal_text: '',
  topology: 'line',
  status: 'active',
  max_steps: 10,
  max_total_tokens: null,
  max_concurrent_runs: 1,
  members: [],
  triggers: [],
}

export const TEAM_TEMPLATE_PRESETS: TeamTemplatePreset[] = [
  {
    id: 'custom',
    name: 'Custom team',
    description: 'Start from a blank draft and choose each detail manually.',
    draft: { template_id: 'custom' },
  },
  {
    id: 'incident_triage',
    name: 'Incident triage',
    description: 'Line topology for intake, diagnosis, and final operator-ready summary.',
    draft: {
      template_id: 'incident_triage',
      name: 'Incident Triage Team',
      description: 'Coordinates alert intake, investigation, and operator summary.',
      goal_text: 'Triage incoming incidents, identify likely impact, and produce a concise next-action summary.',
      topology: 'line',
      status: 'active',
      max_steps: 8,
      max_concurrent_runs: 1,
    },
  },
  {
    id: 'release_review',
    name: 'Release review',
    description: 'Mesh topology for cross-checking regressions, docs, and launch readiness.',
    draft: {
      template_id: 'release_review',
      name: 'Release Review Team',
      description: 'Reviews implementation, regression signals, and release readiness.',
      goal_text: 'Review a release candidate, identify blocking risks, and summarize readiness with evidence.',
      topology: 'mesh',
      status: 'active',
      max_steps: 12,
      max_concurrent_runs: 2,
    },
  },
  {
    id: 'research_synthesis',
    name: 'Research synthesis',
    description: 'Line topology for gathering context, comparing sources, and drafting conclusions.',
    draft: {
      template_id: 'research_synthesis',
      name: 'Research Synthesis Team',
      description: 'Collects context, compares findings, and writes a consolidated brief.',
      goal_text: 'Produce a sourced research brief with key findings, disagreements, and recommended next steps.',
      topology: 'line',
      status: 'draft',
      max_steps: 10,
      max_concurrent_runs: 1,
    },
  },
]

export function makeTeamStepsCompleted(): Record<TeamWizardStep, boolean> {
  return TEAM_WIZARD_STEPS.reduce((acc, step) => {
    acc[step] = false
    return acc
  }, {} as Record<TeamWizardStep, boolean>)
}

export const INITIAL_TEAM_WIZARD_STATE: TeamWizardState = {
  isOpen: false,
  currentStep: 'template',
  draft: EMPTY_TEAM_DRAFT,
  stepsCompleted: makeTeamStepsCompleted(),
  progressMessage: '',
  progressStatus: 'idle',
  createdTeamId: null,
}

export function normalizeTeamDraft(draft: Partial<TeamWizardDraft> | null | undefined): TeamWizardDraft {
  const merged: TeamWizardDraft = {
    ...EMPTY_TEAM_DRAFT,
    ...(draft || {}),
    members: Array.isArray(draft?.members)
      ? draft.members
          .filter((member) => Number.isFinite(Number(member.agent_id)) && Number(member.agent_id) > 0)
          .map((member, index) => ({
            agent_id: Number(member.agent_id),
            execution_order: Number.isFinite(Number(member.execution_order)) ? Number(member.execution_order) : index + 1,
            is_required: member.is_required !== false,
            position_x: member.position_x ?? null,
            position_y: member.position_y ?? null,
          }))
      : [],
    triggers: Array.isArray(draft?.triggers)
      ? draft.triggers
          .filter(
            (trigger) =>
              ['webhook', 'github', 'jira'].includes(trigger.trigger_kind) &&
              Number.isFinite(Number(trigger.trigger_instance_id)) &&
              Number(trigger.trigger_instance_id) > 0,
          )
          .map((trigger) => ({
            uid: trigger.uid || `${trigger.trigger_kind}:${trigger.trigger_instance_id}`,
            trigger_kind: trigger.trigger_kind,
            trigger_instance_id: Number(trigger.trigger_instance_id),
            event_types: Array.isArray(trigger.event_types)
              ? trigger.event_types.map((item) => String(item).trim()).filter(Boolean)
              : [],
            filters_text: trigger.filters_text || '{}',
            is_enabled: trigger.is_enabled !== false,
            label: trigger.label || `${trigger.trigger_kind} #${trigger.trigger_instance_id}`,
          }))
      : [],
  }

  merged.max_steps = clampInteger(merged.max_steps, 1, 100, 10)
  merged.max_concurrent_runs = clampInteger(merged.max_concurrent_runs, 1, 10, 1)
  merged.max_total_tokens = merged.max_total_tokens === null
    ? null
    : clampInteger(merged.max_total_tokens, 1, 10000000, 100000)
  merged.topology = merged.topology === 'mesh' ? 'mesh' : 'line'
  merged.status = ['draft', 'active', 'paused'].includes(merged.status) ? merged.status : 'active'
  merged.template_id = TEAM_TEMPLATE_PRESETS.some((preset) => preset.id === merged.template_id)
    ? merged.template_id
    : 'custom'
  return reorderMembers(merged)
}

export function isTeamStepComplete(draft: TeamWizardDraft, step: TeamWizardStep): boolean {
  switch (step) {
    case 'template':
      return Boolean(draft.template_id)
    case 'basics':
      return draft.name.trim().length > 0 && draft.goal_text.trim().length > 0
    case 'topology':
      return draft.max_steps >= 1 && draft.max_steps <= 100 && draft.max_concurrent_runs >= 1 && draft.max_concurrent_runs <= 10
    case 'members':
      return draft.members.length > 0
    case 'triggers':
      return true
    case 'review':
      return isTeamReadyToCreate(draft)
    case 'create':
      return false
    default:
      return false
  }
}

export function isTeamReadyToCreate(draft: TeamWizardDraft): boolean {
  return (
    isTeamStepComplete(draft, 'template') &&
    isTeamStepComplete(draft, 'basics') &&
    isTeamStepComplete(draft, 'topology') &&
    isTeamStepComplete(draft, 'members')
  )
}

export function hasMeaningfulTeamDraft(draft: TeamWizardDraft): boolean {
  return Boolean(
    draft.name.trim() ||
      draft.description.trim() ||
      draft.goal_text.trim() ||
      draft.members.length ||
      draft.triggers.length ||
      draft.template_id !== 'custom',
  )
}

export function canAccessTeamStep(state: TeamWizardState, target: TeamWizardStep): boolean {
  const targetIndex = TEAM_WIZARD_STEPS.indexOf(target)
  if (targetIndex < 0) return false
  if (targetIndex === 0) return true
  return TEAM_WIZARD_STEPS.slice(0, targetIndex).every((step) => state.stepsCompleted[step])
}

export type TeamWizardAction =
  | { type: 'OPEN'; draft?: Partial<TeamWizardDraft> | null }
  | { type: 'CLOSE' }
  | { type: 'RESET' }
  | { type: 'HYDRATE_DRAFT'; draft: Partial<TeamWizardDraft> | null }
  | { type: 'SET_STEP'; step: TeamWizardStep }
  | { type: 'NEXT' }
  | { type: 'PREV' }
  | { type: 'PATCH_DRAFT'; patch: Partial<TeamWizardDraft> }
  | { type: 'APPLY_TEMPLATE'; templateId: TeamTemplateId }
  | { type: 'ADD_MEMBER'; member: Omit<TeamMemberDraft, 'execution_order'> & { execution_order?: number | null } }
  | { type: 'REMOVE_MEMBER'; agentId: number }
  | { type: 'PATCH_MEMBER'; agentId: number; patch: Partial<TeamMemberDraft> }
  | { type: 'REORDER_MEMBER'; agentId: number; direction: 'up' | 'down' }
  | { type: 'ADD_TRIGGER'; trigger: TeamTriggerDraft }
  | { type: 'REMOVE_TRIGGER'; uid: string }
  | { type: 'PATCH_TRIGGER'; uid: string; patch: Partial<TeamTriggerDraft> }
  | { type: 'SET_PROGRESS'; message?: string; status?: TeamWizardState['progressStatus'] }
  | { type: 'SET_CREATED_TEAM'; teamId: number }

export function teamWizardReducer(state: TeamWizardState, action: TeamWizardAction): TeamWizardState {
  switch (action.type) {
    case 'OPEN': {
      const draft = normalizeTeamDraft(action.draft || EMPTY_TEAM_DRAFT)
      return recomputeCompleted({
        ...INITIAL_TEAM_WIZARD_STATE,
        isOpen: true,
        draft,
      })
    }
    case 'CLOSE':
      return { ...state, isOpen: false }
    case 'RESET':
      return { ...INITIAL_TEAM_WIZARD_STATE }
    case 'HYDRATE_DRAFT': {
      const draft = normalizeTeamDraft(action.draft || EMPTY_TEAM_DRAFT)
      return recomputeCompleted({ ...state, draft })
    }
    case 'SET_STEP':
      if (!canAccessTeamStep(state, action.step)) return state
      return { ...state, currentStep: action.step }
    case 'NEXT': {
      const currentIndex = TEAM_WIZARD_STEPS.indexOf(state.currentStep)
      if (currentIndex < 0 || currentIndex >= TEAM_WIZARD_STEPS.length - 1) return state
      if (!state.stepsCompleted[state.currentStep]) return state
      return { ...state, currentStep: TEAM_WIZARD_STEPS[currentIndex + 1] }
    }
    case 'PREV': {
      const currentIndex = TEAM_WIZARD_STEPS.indexOf(state.currentStep)
      if (currentIndex <= 0) return state
      return { ...state, currentStep: TEAM_WIZARD_STEPS[currentIndex - 1] }
    }
    case 'PATCH_DRAFT':
      return recomputeCompleted({
        ...state,
        draft: normalizeTeamDraft({ ...state.draft, ...action.patch }),
      })
    case 'APPLY_TEMPLATE': {
      const preset = TEAM_TEMPLATE_PRESETS.find((item) => item.id === action.templateId) || TEAM_TEMPLATE_PRESETS[0]
      return recomputeCompleted({
        ...state,
        draft: normalizeTeamDraft({ ...state.draft, ...preset.draft, template_id: preset.id }),
      })
    }
    case 'ADD_MEMBER': {
      if (state.draft.members.some((member) => member.agent_id === action.member.agent_id)) return state
      const nextMember: TeamMemberDraft = {
        agent_id: action.member.agent_id,
        execution_order: action.member.execution_order ?? state.draft.members.length + 1,
        is_required: action.member.is_required !== false,
        position_x: action.member.position_x ?? null,
        position_y: action.member.position_y ?? null,
      }
      return recomputeCompleted({
        ...state,
        draft: reorderMembers({
          ...state.draft,
          members: [...state.draft.members, nextMember],
        }),
      })
    }
    case 'REMOVE_MEMBER':
      return recomputeCompleted({
        ...state,
        draft: reorderMembers({
          ...state.draft,
          members: state.draft.members.filter((member) => member.agent_id !== action.agentId),
        }),
      })
    case 'PATCH_MEMBER':
      return recomputeCompleted({
        ...state,
        draft: reorderMembers({
          ...state.draft,
          members: state.draft.members.map((member) =>
            member.agent_id === action.agentId ? { ...member, ...action.patch } : member,
          ),
        }),
      })
    case 'REORDER_MEMBER':
      return recomputeCompleted({ ...state, draft: moveMember(state.draft, action.agentId, action.direction) })
    case 'ADD_TRIGGER':
      if (state.draft.triggers.some((trigger) => trigger.uid === action.trigger.uid)) return state
      return recomputeCompleted({
        ...state,
        draft: normalizeTeamDraft({ ...state.draft, triggers: [...state.draft.triggers, action.trigger] }),
      })
    case 'REMOVE_TRIGGER':
      return recomputeCompleted({
        ...state,
        draft: normalizeTeamDraft({
          ...state.draft,
          triggers: state.draft.triggers.filter((trigger) => trigger.uid !== action.uid),
        }),
      })
    case 'PATCH_TRIGGER':
      return recomputeCompleted({
        ...state,
        draft: normalizeTeamDraft({
          ...state.draft,
          triggers: state.draft.triggers.map((trigger) =>
            trigger.uid === action.uid ? { ...trigger, ...action.patch } : trigger,
          ),
        }),
      })
    case 'SET_PROGRESS':
      return {
        ...state,
        progressMessage: action.message ?? state.progressMessage,
        progressStatus: action.status ?? state.progressStatus,
      }
    case 'SET_CREATED_TEAM':
      return {
        ...state,
        createdTeamId: action.teamId,
        progressStatus: 'done',
        progressMessage: `Created team #${action.teamId}`,
      }
    default:
      return state
  }
}

function recomputeCompleted(state: TeamWizardState): TeamWizardState {
  const stepsCompleted = makeTeamStepsCompleted()
  for (const step of TEAM_WIZARD_STEPS) {
    stepsCompleted[step] = isTeamStepComplete(state.draft, step)
  }
  return { ...state, stepsCompleted }
}

function reorderMembers(draft: TeamWizardDraft): TeamWizardDraft {
  const seen = new Set<number>()
  const members = [...draft.members]
    .sort((a, b) => a.execution_order - b.execution_order)
    .filter((member) => {
      if (seen.has(member.agent_id)) return false
      seen.add(member.agent_id)
      return true
    })
    .map((member, index) => ({ ...member, execution_order: index + 1 }))
  return { ...draft, members }
}

function moveMember(draft: TeamWizardDraft, agentId: number, direction: 'up' | 'down'): TeamWizardDraft {
  const members = [...draft.members].sort((a, b) => a.execution_order - b.execution_order)
  const index = members.findIndex((member) => member.agent_id === agentId)
  if (index < 0) return draft
  const target = direction === 'up' ? index - 1 : index + 1
  if (target < 0 || target >= members.length) return draft
  const next = [...members]
  const current = next[index]
  next[index] = next[target]
  next[target] = current
  return reorderMembers({ ...draft, members: next })
}

function clampInteger(value: number | null | undefined, min: number, max: number, fallback: number): number {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return fallback
  return Math.max(min, Math.min(max, Math.trunc(numeric)))
}
