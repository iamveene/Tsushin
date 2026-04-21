/**
 * Pure state reducer for the Provider Setup Wizard.
 *
 * Mirrors the Agent-wizard pattern so the two flows feel interchangeable.
 * This file is deliberately framework-agnostic — the context in
 * `contexts/ProviderWizardContext.tsx` wraps it with `useReducer` and adds
 * effectful concerns (dynamic imports, callback fanout, localStorage).
 */

export type Modality = 'llm' | 'tts' | 'image'
export type Hosting = 'cloud' | 'local'

export type StepKey =
  | 'modality'
  | 'hosting'
  | 'vendor'
  | 'credentials'
  | 'container'
  | 'pullModels'
  | 'testAndModels'
  | 'review'
  | 'progress'
  | 'assignAgents'

/**
 * The user's wizard draft. Secrets (api_key, private_key) are never persisted
 * to localStorage — the context strips them before writing.
 */
export interface WizardDraft {
  modality: Modality | null
  hosting: Hosting | null
  vendor: string | null
  instance_name: string
  api_key: string
  base_url: string
  extra_config: Record<string, any>
  available_models: string[]
  is_default: boolean
  /** Container options (Ollama / Kokoro). */
  mem_limit?: string
  cpu_quota?: number
  gpu_enabled?: boolean
  auto_provision?: boolean
  /** Model IDs selected for initial pull (Ollama only). */
  pull_models?: string[]
  /** Persisted id of the instance created so later steps can reference it. */
  created_instance_id?: number | null
  /** Connection test result surfaced in the UI. */
  test_result?: { success: boolean; message: string; latency_ms?: number } | null
}

export interface WizardState {
  isOpen: boolean
  currentStep: StepKey
  stepsCompleted: Record<StepKey, boolean>
  draft: WizardDraft
  progressMessage: string
  progressStatus: 'idle' | 'running' | 'done' | 'error'
  failedStep: string | null
}

export const EMPTY_DRAFT: WizardDraft = {
  modality: null,
  hosting: null,
  vendor: null,
  instance_name: '',
  api_key: '',
  base_url: '',
  extra_config: {},
  available_models: [],
  is_default: false,
  mem_limit: '4g',
  cpu_quota: 0,
  gpu_enabled: false,
  auto_provision: true,
  pull_models: [],
  created_instance_id: null,
  test_result: null,
}

const ALL_STEP_KEYS: StepKey[] = [
  'modality',
  'hosting',
  'vendor',
  'credentials',
  'container',
  'pullModels',
  'testAndModels',
  'review',
  'progress',
  'assignAgents',
]

export function makeEmptyStepsCompleted(): Record<StepKey, boolean> {
  return ALL_STEP_KEYS.reduce((acc, k) => {
    acc[k] = false
    return acc
  }, {} as Record<StepKey, boolean>)
}

export const INITIAL_STATE: WizardState = {
  isOpen: false,
  currentStep: 'modality',
  stepsCompleted: makeEmptyStepsCompleted(),
  draft: EMPTY_DRAFT,
  progressMessage: '',
  progressStatus: 'idle',
  failedStep: null,
}

/**
 * Compute the ordered list of visible steps given the current draft.
 * Branches:
 *   - hosting='local' → container step instead of credentials
 *   - vendor='ollama' AND hosting='local' → single pullModels step (picks
 *     BOTH what to pull into the container AND what to expose to agents;
 *     testAndModels is skipped because the duplicate "Test & choose models"
 *     step used to ask for the same model list twice — once to pull, once
 *     to expose. With one consolidated step the user picks their models
 *     once and the wizard pulls + exposes the same set.)
 *   - modality='image' → hosting auto-picked cloud so the hosting step is skipped
 */
export function getStepOrder(draft: WizardDraft): StepKey[] {
  const base: StepKey[] = ['modality']

  // Hosting step: skipped for image (cloud-only today).
  const wantsHosting = draft.modality !== 'image'
  const hostingSteps: StepKey[] = wantsHosting ? ['hosting'] : []

  const mid: StepKey[] = ['vendor']

  // Branch: credentials (cloud) vs container (local).
  const configStep: StepKey =
    draft.hosting === 'local' ? 'container' : 'credentials'
  const configSteps: StepKey[] = [configStep]

  const isOllamaLocal = draft.vendor === 'ollama' && draft.hosting === 'local'

  // Ollama local: one consolidated pullModels step.
  // Cloud/Image: the usual testAndModels step (connection test + expose list).
  const modelsSteps: StepKey[] = isOllamaLocal ? ['pullModels'] : ['testAndModels']

  // Post-create assign step — LLM only (TTS has its own assign-to-agent flow;
  // Image doesn't bind to a specific agent LLM the same way). Only visible
  // after the instance has been created, so it sits AFTER `progress` in the
  // flow but isn't surfaced in the step pills counter.
  const tail: StepKey[] = ['review', 'progress']
  const assign: StepKey[] = draft.modality === 'llm' ? ['assignAgents'] : []

  return [...base, ...hostingSteps, ...mid, ...configSteps, ...modelsSteps, ...tail, ...assign]
}

export function getStepIndex(state: WizardState): number {
  const order = getStepOrder(state.draft)
  return order.indexOf(state.currentStep)
}

export function getTotalSteps(state: WizardState): number {
  // Visible count excludes terminal / post-create steps: `progress` and
  // `assignAgents`. Those are reached via the post-create footer, not via
  // Next from the Review step, so they shouldn't bump the pill counter.
  const order = getStepOrder(state.draft)
  return order.filter(k => k !== 'progress' && k !== 'assignAgents').length
}

export function canAccessStep(state: WizardState, target: StepKey): boolean {
  const order = getStepOrder(state.draft)
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
  | { type: 'PATCH_DRAFT'; patch: Partial<WizardDraft> }
  | { type: 'SET_PROGRESS'; message?: string; status?: WizardState['progressStatus']; failedStep?: string | null }

export function reducer(state: WizardState, action: WizardAction): WizardState {
  switch (action.type) {
    case 'OPEN': {
      const next: WizardState = {
        ...INITIAL_STATE,
        isOpen: true,
      }
      if (action.preset) {
        next.draft = { ...EMPTY_DRAFT, ...action.preset }
        // Mark upstream steps complete if the preset provided their answer so
        // a caller passing `{vendor: 'openai', modality: 'llm', hosting: 'cloud'}`
        // can land on the credentials step directly.
        const stepsCompleted = makeEmptyStepsCompleted()
        if (next.draft.modality) stepsCompleted.modality = true
        if (next.draft.hosting || next.draft.modality === 'image') stepsCompleted.hosting = true
        if (next.draft.vendor) stepsCompleted.vendor = true
        next.stepsCompleted = stepsCompleted

        // Jump to the furthest step we can access.
        const order = getStepOrder(next.draft)
        let landing: StepKey = 'modality'
        for (const k of order) {
          if (!stepsCompleted[k]) {
            landing = k
            break
          }
        }
        next.currentStep = landing
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
      const order = getStepOrder(state.draft)
      const idx = order.indexOf(state.currentStep)
      if (idx < 0 || idx >= order.length - 1) return state
      if (!state.stepsCompleted[state.currentStep]) return state
      return { ...state, currentStep: order[idx + 1] }
    }
    case 'PREV': {
      const order = getStepOrder(state.draft)
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
    case 'PATCH_DRAFT': {
      const nextDraft = { ...state.draft, ...action.patch }
      // Changing modality or hosting may invalidate downstream choices;
      // mark downstream steps as incomplete so the user has to re-confirm.
      const structural = 'modality' in action.patch || 'hosting' in action.patch || 'vendor' in action.patch
      let stepsCompleted = state.stepsCompleted
      if (structural) {
        stepsCompleted = { ...state.stepsCompleted }
        const order = getStepOrder(nextDraft)
        const curIdx = order.indexOf(state.currentStep)
        // Reset everything strictly after the current step.
        order.forEach((k, i) => {
          if (i > curIdx) stepsCompleted[k] = false
        })
      }
      return {
        ...state,
        draft: nextDraft,
        stepsCompleted,
      }
    }
    case 'SET_PROGRESS':
      return {
        ...state,
        progressMessage: action.message ?? state.progressMessage,
        progressStatus: action.status ?? state.progressStatus,
        failedStep: action.failedStep === undefined ? state.failedStep : action.failedStep,
      }
    default:
      return state
  }
}

// ---------- Validators (pure) ----------

export function isModalityValid(d: WizardDraft): boolean {
  return d.modality !== null
}

export function isHostingValid(d: WizardDraft): boolean {
  return d.hosting !== null
}

export function isVendorValid(d: WizardDraft): boolean {
  return !!d.vendor
}

export function isCredentialsValid(d: WizardDraft): boolean {
  if (!d.instance_name.trim()) return false
  // Vertex AI: need project_id + sa_email + private_key in extra_config
  if (d.vendor === 'vertex_ai') {
    const ec = d.extra_config || {}
    if (!ec.project_id || !ec.sa_email || !ec.private_key) return false
    return true
  }
  // Custom: base_url becomes required (no default).
  if (d.vendor === 'custom') {
    if (!d.base_url.trim()) return false
  }
  // Ollama hosted can be keyless; everything else needs a key.
  if (d.vendor !== 'ollama' && !d.api_key.trim()) return false
  return true
}

export function isContainerValid(d: WizardDraft): boolean {
  // Instance name is the only hard requirement at container-config time.
  return d.instance_name.trim().length > 0
}

export function isTestValid(d: WizardDraft): boolean {
  // Accept any state — the step sets completion itself after a successful test
  // or the user may skip the test explicitly.
  return true
}
