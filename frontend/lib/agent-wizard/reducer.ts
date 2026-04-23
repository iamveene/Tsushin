/**
 * Pure state reducer for the Agent Creation Wizard.
 *
 * Everything here is deterministic and framework-agnostic so it can be unit
 * tested without a React renderer. The provider in `AgentWizardContext.tsx`
 * wraps this with `useReducer` and adds effectful concerns (dynamic imports,
 * callback fanout, localStorage).
 */

import type { AudioProvider } from '@/components/audio-wizard/defaults'

export type AgentType = 'text' | 'audio' | 'hybrid'
export type AudioCapability = 'voice' | 'transcript' | 'hybrid'
export type MemoryMode = 'builtin' | 'vector' | 'semantic'

export type StepKey =
  | 'type'
  | 'basics'
  | 'personality'
  | 'audio'
  | 'skills'
  | 'memory'
  | 'channels'
  | 'review'
  | 'progress'

export interface BasicsConfig {
  agent_name: string
  agent_phone: string
  model_provider: string
  model_name: string
  /**
   * Specific provider_instance to bind this agent to. Required when the tenant
   * has configured one or more instances for the chosen vendor — without it,
   * the backend would fall back to flat-field creds and break agents whose
   * vendor doesn't support flat fields (e.g. Vertex AI, which needs a
   * project_id/sa_email/private_key triple carried on the instance).
   */
  provider_instance_id: number | null
}

export interface PersonalityConfig {
  persona_id: number | null
  tone_preset_id: number | null
  custom_tone: string
  system_prompt: string
  /** true when the user explicitly skipped picking a persona */
  skip_persona: boolean
}

export interface AudioConfig {
  capability: AudioCapability
  provider: AudioProvider
  voice: string
  language: string
  speed: number
  format: string
  memLimit: string
  autoProvision: boolean
  setAsDefaultTTS: boolean
  /** Provider-specific TTS model id (Gemini today). */
  model?: string
}

export interface SkillsConfig {
  builtIns: Record<string, { is_enabled: boolean; config: Record<string, any> }>
  customIds: number[]
}

export interface MemoryConfig {
  mode: MemoryMode
  memory_size: number
  memory_isolation_mode: string
  enable_semantic_search: boolean
  memory_decay_enabled: boolean
  memory_decay_lambda: number
  vector_store_instance_id: number | null
  vector_store_mode: string
}

export interface WizardDraft {
  type: AgentType | null
  basics: BasicsConfig
  personality: PersonalityConfig
  audio: AudioConfig | null
  skills: SkillsConfig
  memory: MemoryConfig
  channels: string[]
}

export interface WizardState {
  isOpen: boolean
  currentStep: StepKey
  stepsCompleted: Record<StepKey, boolean>
  draft: WizardDraft
  createdAgentId: number | null
  progressMessage: string
  progressStatus: 'idle' | 'running' | 'done' | 'error'
  failedStep: string | null
}

export const DEFAULT_AUDIO_CONFIG: AudioConfig = {
  capability: 'voice',
  provider: 'kokoro',
  voice: 'pf_dora',
  language: 'pt',
  speed: 1.0,
  format: 'opus',
  memLimit: '1.5g',
  autoProvision: true,
  setAsDefaultTTS: false,
}

export const EMPTY_DRAFT: WizardDraft = {
  type: null,
  basics: {
    agent_name: '',
    agent_phone: '',
    model_provider: '',
    model_name: '',
    provider_instance_id: null,
  },
  personality: {
    persona_id: null,
    tone_preset_id: null,
    custom_tone: '',
    system_prompt: '',
    skip_persona: false,
  },
  audio: null,
  skills: {
    builtIns: {},
    customIds: [],
  },
  memory: {
    mode: 'builtin',
    memory_size: 10,
    memory_isolation_mode: 'isolated',
    enable_semantic_search: true,
    memory_decay_enabled: false,
    memory_decay_lambda: 0.01,
    vector_store_instance_id: null,
    vector_store_mode: 'override',
  },
  channels: ['playground'],
}

const ALL_STEP_KEYS: StepKey[] = [
  'type',
  'basics',
  'personality',
  'audio',
  'skills',
  'memory',
  'channels',
  'review',
  'progress',
]

export function makeEmptyStepsCompleted(): Record<StepKey, boolean> {
  return ALL_STEP_KEYS.reduce((acc, k) => {
    acc[k] = false
    return acc
  }, {} as Record<StepKey, boolean>)
}

export const INITIAL_STATE: WizardState = {
  isOpen: false,
  currentStep: 'type',
  stepsCompleted: makeEmptyStepsCompleted(),
  draft: EMPTY_DRAFT,
  createdAgentId: null,
  progressMessage: '',
  progressStatus: 'idle',
  failedStep: null,
}

/**
 * Returns the ordered list of steps the user sees, given the chosen type.
 * Text agents skip the audio step entirely.
 */
export function getStepOrder(type: AgentType | null): StepKey[] {
  const base: StepKey[] = [
    'type',
    'basics',
    'personality',
  ]
  const withAudio: StepKey[] = type === 'audio' || type === 'hybrid' ? ['audio'] : []
  const tail: StepKey[] = ['skills', 'memory', 'channels', 'review', 'progress']
  return [...base, ...withAudio, ...tail]
}

export function getStepIndex(state: WizardState): number {
  const order = getStepOrder(state.draft.type)
  return order.indexOf(state.currentStep)
}

export function getTotalSteps(state: WizardState): number {
  // User-visible count excludes the terminal `progress` step.
  return getStepOrder(state.draft.type).length - 1
}

export function canAccessStep(state: WizardState, target: StepKey): boolean {
  const order = getStepOrder(state.draft.type)
  const targetIdx = order.indexOf(target)
  if (targetIdx < 0) return false
  if (targetIdx === 0) return true
  return order.slice(0, targetIdx).every(k => state.stepsCompleted[k])
}

// ---------- Actions ----------

export type WizardAction =
  | { type: 'OPEN'; preset?: Partial<WizardDraft> }
  | { type: 'CLOSE' }
  | { type: 'RESET' }
  | { type: 'SET_STEP'; step: StepKey }
  | { type: 'NEXT' }
  | { type: 'PREV' }
  | { type: 'MARK_STEP_COMPLETE'; step: StepKey; complete?: boolean }
  | { type: 'SET_TYPE'; agentType: AgentType }
  | { type: 'PATCH_BASICS'; patch: Partial<BasicsConfig> }
  | { type: 'PATCH_PERSONALITY'; patch: Partial<PersonalityConfig> }
  | { type: 'PATCH_AUDIO'; patch: Partial<AudioConfig> }
  | { type: 'PATCH_SKILLS'; patch: Partial<SkillsConfig> }
  | { type: 'PATCH_MEMORY'; patch: Partial<MemoryConfig> }
  | { type: 'SET_CHANNELS'; channels: string[] }
  | { type: 'LOAD_DRAFT'; draft: Partial<WizardDraft> }
  | { type: 'SET_PROGRESS'; message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }
  | { type: 'SET_CREATED_AGENT'; agentId: number }

export function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'OPEN': {
      const next: WizardState = {
        ...INITIAL_STATE,
        isOpen: true,
      }
      if (action.preset) {
        next.draft = { ...EMPTY_DRAFT, ...action.preset }
      }
      return next
    }
    case 'CLOSE':
      return { ...state, isOpen: false }
    case 'RESET':
      return { ...INITIAL_STATE }
    case 'SET_STEP':
      if (!canAccessStep(state, action.step)) return state
      return { ...state, currentStep: action.step }
    case 'NEXT': {
      const order = getStepOrder(state.draft.type)
      const idx = order.indexOf(state.currentStep)
      if (idx < 0 || idx >= order.length - 1) return state
      if (!state.stepsCompleted[state.currentStep]) return state
      return { ...state, currentStep: order[idx + 1] }
    }
    case 'PREV': {
      const order = getStepOrder(state.draft.type)
      const idx = order.indexOf(state.currentStep)
      if (idx <= 0) return state
      return { ...state, currentStep: order[idx - 1] }
    }
    case 'MARK_STEP_COMPLETE':
      return {
        ...state,
        stepsCompleted: {
          ...state.stepsCompleted,
          [action.step]: action.complete ?? true,
        },
      }
    case 'SET_TYPE': {
      // Switching type may invalidate audio config and some auto-checked skills.
      const wantAudio = action.agentType === 'audio' || action.agentType === 'hybrid'
      const nextAudio: AudioConfig | null = wantAudio
        ? (state.draft.audio ?? {
            ...DEFAULT_AUDIO_CONFIG,
            capability: action.agentType === 'hybrid' ? 'hybrid' : 'voice',
          })
        : null

      // Drop audio_* skill selections when moving to text.
      const nextBuiltIns = { ...state.draft.skills.builtIns }
      if (!wantAudio) {
        delete nextBuiltIns.audio_tts
        delete nextBuiltIns.audio_transcript
        delete nextBuiltIns.audio_response
      }

      // Reset step completion downstream of `type` because the step list changed.
      const stepsCompleted = makeEmptyStepsCompleted()
      stepsCompleted.type = true

      return {
        ...state,
        draft: {
          ...state.draft,
          type: action.agentType,
          audio: nextAudio,
          skills: { ...state.draft.skills, builtIns: nextBuiltIns },
        },
        stepsCompleted,
      }
    }
    case 'PATCH_BASICS':
      return {
        ...state,
        draft: { ...state.draft, basics: { ...state.draft.basics, ...action.patch } },
      }
    case 'PATCH_PERSONALITY':
      return {
        ...state,
        draft: { ...state.draft, personality: { ...state.draft.personality, ...action.patch } },
      }
    case 'PATCH_AUDIO': {
      if (!state.draft.audio) return state
      return {
        ...state,
        draft: { ...state.draft, audio: { ...state.draft.audio, ...action.patch } },
      }
    }
    case 'PATCH_SKILLS':
      return {
        ...state,
        draft: {
          ...state.draft,
          skills: {
            builtIns: action.patch.builtIns ?? state.draft.skills.builtIns,
            customIds: action.patch.customIds ?? state.draft.skills.customIds,
          },
        },
      }
    case 'PATCH_MEMORY':
      return {
        ...state,
        draft: { ...state.draft, memory: { ...state.draft.memory, ...action.patch } },
      }
    case 'SET_CHANNELS':
      return { ...state, draft: { ...state.draft, channels: action.channels } }
    case 'LOAD_DRAFT':
      return { ...state, draft: { ...state.draft, ...action.draft } }
    case 'SET_PROGRESS':
      return {
        ...state,
        progressMessage: action.message ?? state.progressMessage,
        progressStatus: action.status ?? state.progressStatus,
        failedStep: action.failedStep === undefined ? state.failedStep : action.failedStep,
      }
    case 'SET_CREATED_AGENT':
      return { ...state, createdAgentId: action.agentId }
    default:
      return state
  }
}

// ---------- Per-step validators (pure) ----------

export function isBasicsValid(b: BasicsConfig): boolean {
  if (!b.agent_name.trim()) return false
  if (!b.model_provider || !b.model_name) return false
  // Non-local vendors must bind to a specific provider_instance so the backend
  // can resolve credentials. Ollama is the only vendor that can run without
  // one (local daemon, no auth).
  if (b.model_provider !== 'ollama' && !b.provider_instance_id) return false
  if (b.agent_phone && b.agent_phone.trim()) {
    const cleaned = b.agent_phone.replace(/\s/g, '')
    if (!/^\+?\d{10,15}$/.test(cleaned)) return false
  }
  return true
}

export function isPersonalityValid(p: PersonalityConfig): boolean {
  // Either a persona with a prompt is selected, or the user has written ≥20 chars.
  if (p.persona_id !== null && !p.skip_persona) return true
  return p.system_prompt.trim().length >= 20
}

export function isAudioValid(a: AudioConfig | null): boolean {
  if (!a) return false
  if (!a.voice || !a.language) return false
  return true
}

export function isMemoryValid(m: MemoryConfig): boolean {
  if (m.mode === 'vector' && m.vector_store_instance_id === null) return false
  return true
}

export function areChannelsValid(channels: string[]): boolean {
  return channels.length > 0
}
