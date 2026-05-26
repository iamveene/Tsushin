/**
 * Browser-automation wizard: shared constants, defaults, and pure helpers.
 *
 * Ported from app/flows/page.tsx so the wizard can stand on its own and
 * the legacy panel can be deleted. Keep this module dependency-free
 * (no React) so it stays testable as a unit.
 */

import type {
  BrowserSelectorConfig,
  FlowHeaderConfig,
  FlowSecretReferenceConfig,
  FlowStepConfig,
} from '@/lib/client'

// Full catalog of underlying tool actions the backend dispatches.
// Mirrors BROWSER_ACTION_OPTIONS in app/flows/page.tsx so saved configs
// round-trip cleanly. New entries should land here AND there until the
// legacy panel is gone.
export const BROWSER_ACTION_OPTIONS: ReadonlyArray<{ value: string; label: string }> = [
  { value: 'navigate', label: 'Navigate' },
  { value: 'extract', label: 'Extract data' },
  { value: 'click', label: 'Click' },
  { value: 'fill', label: 'Fill form' },
  { value: 'type_text', label: 'Type text' },
  { value: 'wait_for', label: 'Wait for selector' },
  { value: 'wait_for_url', label: 'Wait for URL' },
  { value: 'dismiss_modal', label: 'Dismiss modal' },
  { value: 'solve_captcha', label: 'Solve CAPTCHA' },
  { value: 'execute_script', label: 'Execute script' },
  { value: 'screenshot', label: 'Screenshot' },
  { value: 'scroll', label: 'Scroll' },
  { value: 'select_option', label: 'Select option' },
  { value: 'hover', label: 'Hover' },
  { value: 'get_attribute', label: 'Get attribute' },
  { value: 'get_page_url', label: 'Get page URL' },
  { value: 'go_back', label: 'Go back' },
  { value: 'go_forward', label: 'Go forward' },
  { value: 'open_tab', label: 'Open tab' },
  { value: 'switch_tab', label: 'Switch tab' },
  { value: 'close_tab', label: 'Close tab' },
  { value: 'list_tabs', label: 'List tabs' },
]

// Friendly "goal" choices the wizard shows on the Manual trail. Each one
// maps to a tool action; the rest of the rare actions stay under "More…".
export interface FriendlyGoal {
  value: string
  label: string
  hint: string
  icon: string
  // How the selectors UI should behave when this goal is chosen:
  //  - "none"     : no selector rows expected (navigate, solve_captcha)
  //  - "one"      : single selector + optional name
  //  - "fill"     : selector + value pair
  //  - "extract"  : selector + variable name (selector.name)
  //  - "script"   : hides selector rows, exposes a single script textarea
  selectorShape: 'none' | 'one' | 'fill' | 'extract' | 'script'
}

export const FRIENDLY_GOALS: ReadonlyArray<FriendlyGoal> = [
  { value: 'navigate', label: 'Open a page', hint: 'Go to a URL and stop.', icon: '🌐', selectorShape: 'none' },
  { value: 'click', label: 'Click something', hint: 'Click a button or link by CSS selector.', icon: '🖱️', selectorShape: 'one' },
  { value: 'fill', label: 'Fill a form', hint: 'Type values into form fields.', icon: '✍️', selectorShape: 'fill' },
  { value: 'extract', label: 'Extract text', hint: 'Save text from an element as a variable.', icon: '🔍', selectorShape: 'extract' },
  { value: 'wait_for', label: 'Wait for element', hint: 'Pause until a selector appears or changes.', icon: '⏳', selectorShape: 'one' },
  { value: 'execute_script', label: 'Run JS', hint: 'Run a custom snippet against the page.', icon: '🧪', selectorShape: 'script' },
]

export const SUPPRESS_SELECTOR_FOR_ACTIONS = new Set([
  'navigate',
  'solve_captcha',
  'go_back',
  'go_forward',
  'screenshot',
  'get_page_url',
  'list_tabs',
])

// Per-action timeout suggestions — same defaults the legacy panel uses.
// 30s is too tight for solve_captcha/wait_for and too loose for navigate.
export function browserActionSuggestedTimeout(action: string | undefined): number {
  switch (action) {
    case 'solve_captcha': return 120
    case 'wait_for':
    case 'wait_for_url': return 60
    case 'extract': return 45
    case 'navigate': return 30
    case 'click':
    case 'fill':
    case 'type_text': return 15
    default: return 30
  }
}

// Default FlowStepConfig shape for a new browser_automation step. Same as
// page.tsx defaultConfigForStepType('browser_automation') — kept here so
// the wizard owns its own defaults and the legacy panel can be ripped out.
export function defaultBrowserStepConfig(previousUrl?: string): Partial<FlowStepConfig> {
  return {
    mode: 'container',
    provider_type: 'playwright',
    timeout_seconds: browserActionSuggestedTimeout('navigate'),
    use_tool_mode: true,
    tool_action: 'navigate',
    tool_arguments: {},
    selectors: [],
    browser_secret_references: [],
    session_persistence: true,
    session_ttl_seconds: 300,
    browser_session_profile_name: '',
    ...(previousUrl ? { url: previousUrl } : {}),
  }
}

// --- normalizers (lift the wire-format → array-of-rows shape used in UI) ---

export function normalizeHeaderRows(value: unknown): FlowHeaderConfig[] {
  if (Array.isArray(value)) return value as FlowHeaderConfig[]
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([key, raw]) => ({
      key,
      value: String(raw ?? ''),
    }))
  }
  return []
}

function coerceToolArgumentValue(key: string, value: string): string | number | boolean {
  const normalized = key.trim()
  if (['timeout_ms', 'x', 'y', 'delay_ms'].includes(normalized)) {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : value
  }
  if (normalized === 'full_page') {
    if (value.toLowerCase() === 'true') return true
    if (value.toLowerCase() === 'false') return false
  }
  return value
}

export function rowsToToolArguments(rows: FlowHeaderConfig[]): Record<string, unknown> {
  return rows.reduce<Record<string, unknown>>((acc, row) => {
    const key = (row.key || '').trim()
    if (!key) return acc
    acc[key] = coerceToolArgumentValue(key, row.value || '')
    return acc
  }, {})
}

export function normalizeBrowserSelectorRows(value: unknown): BrowserSelectorConfig[] {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === 'object') return item as BrowserSelectorConfig
        return { selector: String(item ?? '') } as BrowserSelectorConfig
      })
      .filter((item) => Object.keys(item).length > 0)
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([name, raw]) => {
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        return { name, ...(raw as BrowserSelectorConfig) } as BrowserSelectorConfig
      }
      return { name, selector: String(raw ?? '') } as BrowserSelectorConfig
    })
  }
  return []
}

export function normalizeSecretReferenceRows(value: unknown): FlowSecretReferenceConfig[] {
  if (Array.isArray(value)) {
    return value.filter(
      (item): item is FlowSecretReferenceConfig => !!item && typeof item === 'object',
    )
  }
  if (value && typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>).map(([target, raw]) => {
      if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
        return { target, ...(raw as FlowSecretReferenceConfig) } as FlowSecretReferenceConfig
      }
      return { target, reference: String(raw ?? '') } as FlowSecretReferenceConfig
    })
  }
  return []
}

// --- stage / state machine ---

export type WizardStage =
  | 'trail'             // pick Record vs Manual
  | 'goal'              // manual trail: pick an action
  | 'url'               // collect URL (both trails)
  | 'record'            // hosts RecorderDialog
  | 'url-and-selectors' // manual trail: URL + simplified selector editor
  | 'review'            // name + summary + Advanced toggle

export type WizardTrail = 'unset' | 'record' | 'manual'

// Heuristic for opening directly into Review when editing an existing
// step: if the user has already produced selectors or tool args, there's
// nothing to learn — drop them on the final stage with Advanced collapsed.
export function deriveInitialStage(config: FlowStepConfig | undefined): {
  stage: WizardStage
  trail: WizardTrail
} {
  const cfg = (config || {}) as FlowStepConfig
  const selectorCount = normalizeBrowserSelectorRows(cfg.selectors).length
  const toolArgCount = Object.keys((cfg.tool_arguments as Record<string, unknown>) || {}).length
  if (selectorCount > 0 || toolArgCount > 0) {
    return { stage: 'review', trail: 'manual' }
  }
  return { stage: 'trail', trail: 'unset' }
}
