'use client'

/**
 * Guided wizard for configuring a `browser_automation` flow step.
 *
 * Replaces the legacy 360-line flat panel — the user used to face every
 * field (mode/provider/timeout/TTL/profile/integration_id/selectors/
 * tool_args) at once. The wizard splits the work into:
 *
 *  1. Trail picker     — Record vs Manual
 *  2. URL / Goal       — what to do and where
 *  3. Recording (Record trail) or Selectors (Manual trail)
 *  4. Review           — name, summary, Advanced collapsible
 *
 * For existing steps (selectors already configured) the wizard mounts
 * directly on Review so editing is fast.
 *
 * On-disk schema is unchanged: the wizard reads/writes the same
 * `FlowStepConfig` shape the legacy panel used.
 */

import { useCallback, useEffect, useMemo, useState } from 'react'
import TemplateInput from '@/components/flows/TemplateInput'
import TemplateTextarea from '@/components/flows/TemplateTextarea'
import type {
  BrowserSelectorConfig,
  FlowHeaderConfig,
  FlowStepConfig,
  StepType,
} from '@/lib/client'
import RecorderDialog from '@/app/flows/recorder/RecorderDialog'
import SessionProfilePicker from './SessionProfilePicker'
import {
  BROWSER_ACTION_OPTIONS,
  FRIENDLY_GOALS,
  SUPPRESS_SELECTOR_FOR_ACTIONS,
  browserActionSuggestedTimeout,
  deriveInitialStage,
  normalizeBrowserSelectorRows,
  normalizeHeaderRows,
  rowsToToolArguments,
  type FriendlyGoal,
  type WizardStage,
  type WizardTrail,
} from './defaults'

interface Props {
  config: FlowStepConfig | undefined
  onChange: (update: Partial<FlowStepConfig>) => void
  allSteps: Array<{ name: string; type: StepType; position: number; config?: FlowStepConfig }>
  currentStepPosition: number
}

const stageOrderRecord: WizardStage[] = ['trail', 'url', 'record', 'review']
const stageOrderManual: WizardStage[] = ['trail', 'goal', 'url-and-selectors', 'review']

export default function BrowserStepWizard({ config, onChange, allSteps, currentStepPosition }: Props) {
  const cfg = config || {}
  const initial = useMemo(() => deriveInitialStage(config), [])
  const [stage, setStage] = useState<WizardStage>(initial.stage)
  const [trail, setTrail] = useState<WizardTrail>(initial.trail)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const selectorRows = normalizeBrowserSelectorRows(cfg.selectors)
  const toolArgRows = normalizeHeaderRows(cfg.tool_arguments)

  // Keep selectors as a derived value but expose a mutator for sub-stages.
  const setSelectors = useCallback(
    (next: BrowserSelectorConfig[]) => onChange({ selectors: next }),
    [onChange],
  )
  const setToolArgRows = useCallback(
    (next: FlowHeaderConfig[]) => onChange({ tool_arguments: rowsToToolArguments(next) }),
    [onChange],
  )

  // Apply a "friendly goal" — sets tool_action + a sensible timeout, and
  // moves to the URL+selectors stage. Idempotent: re-picking the same
  // goal doesn't wipe selectors the user already added under it.
  const applyGoal = useCallback(
    (goal: FriendlyGoal | { value: string }) => {
      const action = goal.value
      onChange({
        tool_action: action,
        use_tool_mode: true,
        tool_arguments: { ...((cfg.tool_arguments as Record<string, unknown>) || {}), action },
        timeout_seconds: cfg.timeout_seconds || browserActionSuggestedTimeout(action),
      })
      setStage('url-and-selectors')
    },
    [cfg.timeout_seconds, cfg.tool_arguments, onChange],
  )

  const pickTrail = useCallback((next: WizardTrail) => {
    setTrail(next)
    if (next === 'record') setStage('url')
    else setStage('goal')
  }, [])

  const resetWizard = useCallback(() => {
    if (selectorRows.length > 0 || toolArgRows.length > 0) {
      const ok = window.confirm('Start over? This clears the current selectors and tool arguments — config is otherwise preserved.')
      if (!ok) return
      onChange({ selectors: [], tool_arguments: {} })
    }
    setTrail('unset')
    setStage('trail')
  }, [onChange, selectorRows.length, toolArgRows.length])

  // --- recording integration -----------------------------------------------
  const handleRecorderClose = useCallback(() => {
    // Closing the recorder without saving: go back to URL collection
    // (preserves whatever was typed).
    if (stage === 'record') setStage('url')
  }, [stage])

  const handleRecorderApply = useCallback(
    (compiled: Partial<FlowStepConfig>) => {
      // Phase 5 will refine the merge — for now mirror the legacy panel:
      // recorded output overrides the wholesale config except for things
      // the recorder didn't produce.
      onChange({
        ...compiled,
        selectors: compiled.selectors ?? selectorRows,
        browser_secret_references: compiled.browser_secret_references ?? cfg.browser_secret_references ?? [],
      })
      setStage('review')
    },
    [cfg.browser_secret_references, onChange, selectorRows],
  )

  // --- stage views ---------------------------------------------------------

  const stageHeader = (
    <div className="flex items-center justify-between text-[11px] uppercase tracking-wide text-slate-500">
      <StageBreadcrumbs stage={stage} trail={trail} onJump={(target) => setStage(target)} />
      {stage !== 'trail' && (
        <button type="button" onClick={resetWizard} className="text-cyan-400 hover:text-cyan-300">
          ← Start over
        </button>
      )}
    </div>
  )

  if (stage === 'trail') {
    return (
      <div className="space-y-4">
        {stageHeader}
        <p className="text-sm text-slate-300">How do you want to build this step?</p>
        <div className="grid gap-3 md:grid-cols-2">
          <TrailCard
            title="🎬 Record a flow"
            recommended
            description="Open a live Chromium, click through what you want once, and Tsushin writes the selectors for you. Best for portals with login or multi-step navigation."
            onClick={() => pickTrail('record')}
          />
          <TrailCard
            title="⚙️ Configure manually"
            description="Pick an action, type CSS selectors, and wire values. Good for simple navigations or when you already know the page structure."
            onClick={() => pickTrail('manual')}
          />
        </div>
      </div>
    )
  }

  if (stage === 'goal') {
    return (
      <div className="space-y-4">
        {stageHeader}
        <p className="text-sm text-slate-300">What should this step do?</p>
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {FRIENDLY_GOALS.map((goal) => (
            <button
              key={goal.value}
              type="button"
              onClick={() => applyGoal(goal)}
              className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 text-left hover:border-cyan-500/60 hover:bg-slate-800/60 transition-colors"
            >
              <div className="text-2xl mb-1.5">{goal.icon}</div>
              <div className="text-sm font-medium text-slate-200">{goal.label}</div>
              <div className="text-xs text-slate-500 mt-1">{goal.hint}</div>
            </button>
          ))}
        </div>
        <details className="rounded-lg border border-slate-700 bg-slate-800/30 px-3 py-2">
          <summary className="text-xs text-slate-400 cursor-pointer hover:text-slate-200">More actions…</summary>
          <div className="mt-2 grid grid-cols-2 md:grid-cols-3 gap-2">
            {BROWSER_ACTION_OPTIONS
              .filter((opt) => !FRIENDLY_GOALS.some((g) => g.value === opt.value))
              .map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => applyGoal({ value: opt.value })}
                  className="rounded border border-slate-700 bg-slate-900/40 px-2 py-1.5 text-xs text-slate-300 hover:border-cyan-500/40"
                >
                  {opt.label}
                </button>
              ))}
          </div>
        </details>
      </div>
    )
  }

  if (stage === 'url') {
    // Record trail: collect URL, then advance into the recorder modal.
    const canStart = (cfg.url || '').trim().length > 0
    return (
      <div className="space-y-4">
        {stageHeader}
        <div>
          <label htmlFor="wizard-url" className="block text-sm font-medium text-slate-300 mb-1.5">
            Starting URL
          </label>
          <TemplateInput
            id="wizard-url"
            value={cfg.url || ''}
            onValueChange={(value: string) => onChange({ url: value })}
            placeholder="https://portal.example.com/"
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            allSteps={allSteps}
            currentStepPosition={currentStepPosition}
          />
          <p className="mt-1 text-xs text-slate-500">
            The recorder opens here when you click Start. Templates like <code className="font-mono text-slate-400">{'{{previous_step.field}}'}</code> are supported.
          </p>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-300 mb-1.5">
            What does this step do? <span className="text-slate-500 font-normal">(optional)</span>
          </label>
          <TemplateTextarea
            value={cfg.prompt || ''}
            onValueChange={(value: string) => onChange({ prompt: value })}
            rows={2}
            placeholder="e.g. Log in and extract this month's balance."
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
            allSteps={allSteps}
            currentStepPosition={currentStepPosition}
          />
        </div>
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => { setTrail('unset'); setStage('trail') }}
            className="text-xs text-slate-400 hover:text-slate-200"
          >
            ← Back
          </button>
          <button
            type="button"
            disabled={!canStart}
            onClick={() => setStage('record')}
            className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 disabled:bg-slate-700 disabled:text-slate-500 disabled:cursor-not-allowed text-slate-900 text-xs font-semibold transition-colors"
          >
            🎬 Open recorder →
          </button>
        </div>
      </div>
    )
  }

  if (stage === 'record') {
    // We still render the URL stage chrome under the modal so closing the
    // recorder reveals the URL form, not a blank wizard.
    return (
      <div className="space-y-4">
        {stageHeader}
        <p className="text-sm text-slate-300">Recording <span className="text-slate-200 font-mono">{cfg.url || '(no URL)'}</span>…</p>
        <p className="text-xs text-slate-500">The recorder modal is open. Close it (or hit Discard) to come back here and adjust the URL.</p>
        <RecorderDialog
          isOpen
          onClose={handleRecorderClose}
          url={cfg.url || ''}
          onUrlChange={(u) => onChange({ url: u })}
          hideUrlBar
          onApply={handleRecorderApply}
        />
      </div>
    )
  }

  if (stage === 'url-and-selectors') {
    return (
      <div className="space-y-4">
        {stageHeader}
        <ActionContextBanner action={cfg.tool_action} onPickAnother={() => setStage('goal')} />
        <div>
          <label htmlFor="wizard-url" className="block text-sm font-medium text-slate-300 mb-1.5">URL</label>
          <TemplateInput
            id="wizard-url"
            value={cfg.url || ''}
            onValueChange={(value: string) => onChange({ url: value })}
            placeholder="https://portal.example.com/"
            className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none"
            allSteps={allSteps}
            currentStepPosition={currentStepPosition}
          />
        </div>
        <SimpleSelectorEditor
          action={cfg.tool_action}
          selectors={selectorRows}
          onChange={setSelectors}
          allSteps={allSteps}
          currentStepPosition={currentStepPosition}
          toolArgRows={toolArgRows}
          onToolArgRows={setToolArgRows}
        />
        <div className="flex items-center justify-between">
          <button type="button" onClick={() => setStage('goal')} className="text-xs text-slate-400 hover:text-slate-200">
            ← Back
          </button>
          <button
            type="button"
            onClick={() => setStage('review')}
            className="px-3 py-2 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-900 text-xs font-semibold transition-colors"
          >
            Continue → Review
          </button>
        </div>
      </div>
    )
  }

  // stage === 'review'
  return (
    <div className="space-y-4">
      {stageHeader}
      <ReviewSummary cfg={cfg} selectorRows={selectorRows} toolArgRows={toolArgRows} />
      <div>
        <label className="block text-sm font-medium text-slate-300 mb-1.5">Prompt / description</label>
        <TemplateTextarea
          value={cfg.prompt || ''}
          onValueChange={(value: string) => onChange({ prompt: value })}
          rows={3}
          placeholder="Describe what this step does. Used as the step's friendly label."
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-sm focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-none"
          allSteps={allSteps}
          currentStepPosition={currentStepPosition}
        />
      </div>
      <SimpleSelectorEditor
        action={cfg.tool_action}
        selectors={selectorRows}
        onChange={setSelectors}
        allSteps={allSteps}
        currentStepPosition={currentStepPosition}
        toolArgRows={toolArgRows}
        onToolArgRows={setToolArgRows}
        showSelectorsHeading
      />
      <AdvancedPanel
        cfg={cfg}
        onChange={onChange}
        toolArgRows={toolArgRows}
        onToolArgRows={setToolArgRows}
        allSteps={allSteps}
        currentStepPosition={currentStepPosition}
        open={advancedOpen}
        onToggle={() => setAdvancedOpen((v) => !v)}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function TrailCard({
  title,
  description,
  recommended,
  onClick,
}: {
  title: string
  description: string
  recommended?: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-left rounded-lg border border-slate-700 bg-slate-800/40 p-4 hover:border-cyan-500/60 hover:bg-slate-800/60 transition-colors"
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="text-sm font-medium text-slate-200">{title}</span>
        {recommended && (
          <span className="text-[10px] uppercase tracking-wider rounded-full px-1.5 py-0.5 bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
            Recommended
          </span>
        )}
      </div>
      <p className="text-xs text-slate-400 leading-relaxed">{description}</p>
    </button>
  )
}

function StageBreadcrumbs({
  stage,
  trail,
  onJump,
}: {
  stage: WizardStage
  trail: WizardTrail
  onJump: (target: WizardStage) => void
}) {
  const sequence = trail === 'record'
    ? stageOrderRecord
    : trail === 'manual'
      ? stageOrderManual
      : (['trail'] as WizardStage[])
  const labels: Record<WizardStage, string> = {
    'trail': 'Choose',
    'goal': 'Action',
    'url': 'URL',
    'record': 'Record',
    'url-and-selectors': 'Selectors',
    'review': 'Review',
  }
  const currentIdx = sequence.indexOf(stage)
  return (
    <ol className="flex items-center gap-1.5">
      {sequence.map((s, i) => {
        const reached = i <= currentIdx
        const here = s === stage
        return (
          <li key={s} className="flex items-center gap-1.5">
            <button
              type="button"
              disabled={!reached || here}
              onClick={() => onJump(s)}
              className={
                'rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ' +
                (here
                  ? 'bg-cyan-500/15 text-cyan-300 border border-cyan-500/30'
                  : reached
                    ? 'text-slate-400 hover:text-cyan-300'
                    : 'text-slate-600 cursor-default')
              }
            >
              {labels[s]}
            </button>
            {i < sequence.length - 1 && <span className="text-slate-700">›</span>}
          </li>
        )
      })}
    </ol>
  )
}

function ActionContextBanner({
  action,
  onPickAnother,
}: {
  action: string | undefined
  onPickAnother: () => void
}) {
  const friendly = FRIENDLY_GOALS.find((g) => g.value === (action || ''))
  const label = friendly?.label || BROWSER_ACTION_OPTIONS.find((o) => o.value === action)?.label || 'Custom action'
  return (
    <div className="flex items-center justify-between rounded-lg border border-slate-700 bg-slate-800/30 px-3 py-2">
      <div className="text-xs text-slate-300">
        Action: <span className="text-slate-100 font-medium">{label}</span>{' '}
        <span className="text-slate-500">(timeout {browserActionSuggestedTimeout(action)}s suggested)</span>
      </div>
      <button type="button" onClick={onPickAnother} className="text-[11px] text-cyan-400 hover:text-cyan-300">
        Change action
      </button>
    </div>
  )
}

function SimpleSelectorEditor({
  action,
  selectors,
  onChange,
  allSteps,
  currentStepPosition,
  toolArgRows,
  onToolArgRows,
  showSelectorsHeading,
}: {
  action: string | undefined
  selectors: BrowserSelectorConfig[]
  onChange: (next: BrowserSelectorConfig[]) => void
  allSteps: Array<{ name: string; type: StepType; position: number; config?: FlowStepConfig }>
  currentStepPosition: number
  toolArgRows: FlowHeaderConfig[]
  onToolArgRows: (rows: FlowHeaderConfig[]) => void
  showSelectorsHeading?: boolean
}) {
  const compactInput = 'w-full min-w-0 px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none'
  const fieldLabel = 'block text-[11px] font-medium uppercase text-slate-500 mb-1'

  const friendly = FRIENDLY_GOALS.find((g) => g.value === (action || ''))
  const shape = friendly?.selectorShape

  // execute_script: hide selector rows and surface a single script
  // textarea wired to tool_arguments.script.
  if (shape === 'script') {
    const scriptRow = toolArgRows.find((r) => (r.key || '').trim() === 'script')
    const setScript = (value: string) => {
      const others = toolArgRows.filter((r) => (r.key || '').trim() !== 'script')
      onToolArgRows(value ? [...others, { key: 'script', value }] : others)
    }
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 space-y-2">
        <label className="text-sm font-medium text-slate-300">Script</label>
        <TemplateTextarea
          value={scriptRow?.value || ''}
          onValueChange={setScript}
          rows={6}
          placeholder="// async function (page) { ... }"
          className="w-full px-3 py-2 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs font-mono focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none resize-y"
          allSteps={allSteps}
          currentStepPosition={currentStepPosition}
        />
      </div>
    )
  }

  if (SUPPRESS_SELECTOR_FOR_ACTIONS.has(action || '')) {
    return (
      <div className="rounded-lg border border-slate-700 bg-slate-800/30 p-3 text-xs text-slate-400">
        This action doesn't target an element — no selector needed.
      </div>
    )
  }

  const addRow = () => {
    const seed: BrowserSelectorConfig =
      shape === 'fill' ? { name: '', selector: '', value: '' } as BrowserSelectorConfig :
      shape === 'extract' ? { name: '', action: 'extract', selector: '' } as BrowserSelectorConfig :
      { name: '', selector: '' } as BrowserSelectorConfig
    onChange([...selectors, seed])
  }

  const updateRow = (i: number, patch: Partial<BrowserSelectorConfig>) => {
    onChange(selectors.map((row, idx) => (idx === i ? { ...row, ...patch } : row)))
  }

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/40 p-4 space-y-3">
      <div className="flex items-center justify-between">
        {showSelectorsHeading ? (
          <label className="text-sm font-medium text-slate-300">Selectors</label>
        ) : (
          <label className="text-sm font-medium text-slate-300">Target {shape === 'fill' ? 'fields' : 'element'}</label>
        )}
        <button type="button" onClick={addRow} className="text-xs text-cyan-400 hover:text-cyan-300">
          + Add row
        </button>
      </div>
      {selectors.length === 0 ? (
        <p className="text-xs text-slate-500">
          {shape === 'fill' && 'Add one row per form field. Use {{previous_step.field}} or {{vault.password}} in Value to template.'}
          {shape === 'extract' && 'Add one row: the CSS selector to read text from, and the variable name to save it as.'}
          {(shape === 'one' || !shape) && 'Add a CSS selector that identifies the element to target.'}
        </p>
      ) : (
        <div className="space-y-2">
          {selectors.map((row, i) => (
            <div key={i} className="rounded-lg border border-slate-700 bg-slate-900/30 p-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="text-xs font-medium text-slate-400">Row {i + 1}</span>
                <button
                  type="button"
                  onClick={() => onChange(selectors.filter((_, idx) => idx !== i))}
                  className="shrink-0 rounded-md border border-red-500/30 px-2 py-1 text-xs font-medium text-red-300 hover:border-red-400/50 hover:bg-red-500/10 hover:text-red-200 transition-colors"
                >
                  Remove
                </button>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                <label className="min-w-0">
                  <span className={fieldLabel}>{shape === 'extract' ? 'Save as variable' : 'Label'}</span>
                  <input
                    type="text"
                    value={row.name || ''}
                    onChange={(e) => updateRow(i, { name: e.target.value })}
                    placeholder={shape === 'extract' ? 'balance' : 'login button'}
                    className={compactInput}
                  />
                </label>
                <label className="min-w-0">
                  <span className={fieldLabel}>CSS selector</span>
                  <input
                    type="text"
                    value={row.selector || ''}
                    onChange={(e) => updateRow(i, { selector: e.target.value })}
                    placeholder="#login-button, [data-testid='submit'], …"
                    className={`${compactInput} font-mono`}
                  />
                </label>
              </div>
              {shape === 'fill' && (
                <label className="block min-w-0">
                  <span className={fieldLabel}>Value to type</span>
                  <TemplateTextarea
                    value={row.value || ''}
                    onValueChange={(value: string) => updateRow(i, { value })}
                    rows={1}
                    placeholder="{{previous_step.username}} or literal text"
                    className={`${compactInput} resize-y`}
                    allSteps={allSteps}
                    currentStepPosition={currentStepPosition}
                  />
                </label>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ReviewSummary({
  cfg,
  selectorRows,
  toolArgRows,
}: {
  cfg: FlowStepConfig
  selectorRows: BrowserSelectorConfig[]
  toolArgRows: FlowHeaderConfig[]
}) {
  const action = cfg.tool_action || 'navigate'
  const friendly = FRIENDLY_GOALS.find((g) => g.value === action)
  const label = friendly?.label || BROWSER_ACTION_OPTIONS.find((o) => o.value === action)?.label || action
  return (
    <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 space-y-1">
      <div className="text-xs uppercase tracking-wide text-emerald-300/80">Summary</div>
      <div className="text-sm text-slate-200">{friendly?.icon || '⚙️'} {label}</div>
      <div className="text-xs text-slate-400 font-mono break-all">{cfg.url || '(no URL set)'}</div>
      <div className="text-xs text-slate-500">
        {selectorRows.length} selector row{selectorRows.length === 1 ? '' : 's'}
        {toolArgRows.length > 0 && <> · {toolArgRows.length} tool arg{toolArgRows.length === 1 ? '' : 's'}</>}
        {cfg.browser_session_profile_name && <> · profile: <span className="text-slate-300">{cfg.browser_session_profile_name}</span></>}
      </div>
    </div>
  )
}

function AdvancedPanel({
  cfg,
  onChange,
  toolArgRows,
  onToolArgRows,
  allSteps,
  currentStepPosition,
  open,
  onToggle,
}: {
  cfg: FlowStepConfig
  onChange: (update: Partial<FlowStepConfig>) => void
  toolArgRows: FlowHeaderConfig[]
  onToolArgRows: (rows: FlowHeaderConfig[]) => void
  allSteps: Array<{ name: string; type: StepType; position: number; config?: FlowStepConfig }>
  currentStepPosition: number
  open: boolean
  onToggle: () => void
}) {
  const compactInput = 'w-full min-w-0 px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none'
  const fieldLabel = 'block text-[11px] font-medium uppercase text-slate-500 mb-1'

  return (
    <div className="rounded-lg border border-slate-700 bg-slate-800/30">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-4 py-2 text-left"
      >
        <span className="text-sm font-medium text-slate-300">Advanced</span>
        <span className="text-xs text-slate-500">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="border-t border-slate-700 p-4 space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div>
              <label className={fieldLabel}>Mode</label>
              <select
                value={cfg.mode || 'container'}
                onChange={(e) => onChange({ mode: e.target.value })}
                className={compactInput}
              >
                <option value="container">Container</option>
                <option value="host">Host</option>
              </select>
            </div>
            <div>
              <label className={fieldLabel}>Provider</label>
              <input
                type="text"
                value={cfg.provider_type || 'playwright'}
                onChange={(e) => onChange({ provider_type: e.target.value })}
                className={compactInput}
              />
            </div>
            <div>
              <label className={fieldLabel}>
                Timeout seconds
                <span className="ml-1 normal-case text-slate-600">(suggested {browserActionSuggestedTimeout(cfg.tool_action)}s)</span>
              </label>
              <input
                type="number"
                min={5}
                value={cfg.timeout_seconds ?? browserActionSuggestedTimeout(cfg.tool_action)}
                onChange={(e) =>
                  onChange({
                    timeout_seconds: Number(e.target.value) || browserActionSuggestedTimeout(cfg.tool_action),
                  })
                }
                className={compactInput}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
              <span className="text-xs text-slate-300">Persist browser session</span>
              <input
                type="checkbox"
                checked={cfg.session_persistence !== false}
                onChange={(e) => onChange({ session_persistence: e.target.checked })}
                className="h-4 w-4 rounded border-slate-600 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
              />
            </label>
            <div>
              <label className={fieldLabel}>Session TTL seconds</label>
              <input
                type="number"
                min={0}
                value={cfg.session_ttl_seconds ?? 300}
                onChange={(e) => onChange({ session_ttl_seconds: Number(e.target.value) || 0 })}
                className={compactInput}
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className={fieldLabel}>Browser session profile</label>
              <SessionProfilePicker
                profileName={cfg.browser_session_profile_name}
                integrationId={(cfg as Record<string, unknown>).browser_session_integration_id as number | null | undefined}
                onChange={({ profileName, integrationId }) =>
                  onChange({
                    browser_session_profile_name: profileName,
                    browser_session_integration_id: integrationId,
                  } as Partial<FlowStepConfig>)
                }
              />
            </div>
            <div>
              <label className={fieldLabel}>Integration ID</label>
              <input
                type="number"
                min={0}
                value={
                  ((cfg as Record<string, unknown>).browser_session_integration_id as number | null | undefined) ?? ''
                }
                onChange={(e) =>
                  onChange({
                    browser_session_integration_id: e.target.value ? Number(e.target.value) : null,
                  } as Partial<FlowStepConfig>)
                }
                placeholder="auto-filled when you pick a profile"
                className={compactInput}
              />
            </div>
          </div>

          <label className="flex items-start justify-between gap-3 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2">
            <span>
              <span className="block text-xs font-medium text-slate-300">Optional browser action</span>
              <span className="block text-[11px] text-slate-500">Use with step behavior “Continue” to mark expected portal/login misses as skipped.</span>
            </span>
            <input
              type="checkbox"
              checked={cfg.optional === true || cfg.treat_failure_as_skipped === true}
              onChange={(e) => onChange({ optional: e.target.checked, treat_failure_as_skipped: e.target.checked })}
              className="mt-0.5 h-4 w-4 rounded border-slate-600 bg-slate-800 text-cyan-500 focus:ring-cyan-500"
            />
          </label>

          <ToolArgumentsEditor
            rows={toolArgRows}
            onChange={onToolArgRows}
            allSteps={allSteps}
            currentStepPosition={currentStepPosition}
          />
        </div>
      )}
    </div>
  )
}

function ToolArgumentsEditor({
  rows,
  onChange,
  allSteps,
  currentStepPosition,
}: {
  rows: FlowHeaderConfig[]
  onChange: (rows: FlowHeaderConfig[]) => void
  allSteps: Array<{ name: string; type: StepType; position: number; config?: FlowStepConfig }>
  currentStepPosition: number
}) {
  const compactInput = 'w-full min-w-0 px-2 py-1.5 bg-slate-700/50 border border-slate-600 rounded-lg text-white text-xs focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500 outline-none'
  const fieldLabel = 'block text-[11px] font-medium uppercase text-slate-500 mb-1'
  return (
    <div className="rounded-lg border border-slate-700 bg-slate-900/40 p-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-300">Tool arguments</span>
        <button
          type="button"
          onClick={() => onChange([...rows, { key: '', value: '' }])}
          className="text-xs text-cyan-400 hover:text-cyan-300"
        >
          + Add argument
        </button>
      </div>
      {rows.length === 0 ? (
        <p className="text-[11px] text-slate-500">
          Power-user knobs. Common keys: script, timeout_ms, url_contains, state, attribute, wait_until, tab_id, fallback_selector, fallback_script.
        </p>
      ) : (
        rows.map((row, i) => (
          <div key={i} className="space-y-1.5">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[11px] text-slate-500">Argument {i + 1}</span>
              <button
                type="button"
                onClick={() => onChange(rows.filter((_, idx) => idx !== i))}
                className="shrink-0 rounded-md border border-red-500/30 px-2 py-1 text-[11px] font-medium text-red-300 hover:border-red-400/50 hover:bg-red-500/10 hover:text-red-200 transition-colors"
              >
                Remove
              </button>
            </div>
            <div className="grid gap-2 md:grid-cols-[minmax(140px,0.8fr)_minmax(0,2fr)]">
              <label className="min-w-0">
                <span className={fieldLabel}>Key</span>
                <input
                  type="text"
                  value={row.key || ''}
                  onChange={(e) =>
                    onChange(rows.map((item, idx) => (idx === i ? { ...item, key: e.target.value } : item)))
                  }
                  placeholder="script"
                  className={compactInput}
                />
              </label>
              <label className="min-w-0">
                <span className={fieldLabel}>Value</span>
                <TemplateTextarea
                  value={row.value || ''}
                  onValueChange={(value: string) =>
                    onChange(rows.map((item, idx) => (idx === i ? { ...item, value } : item)))
                  }
                  rows={(row.key || '').trim() === 'script' ? 5 : 2}
                  placeholder="value or {{previous_step.field}}"
                  className={`${compactInput} resize-y font-mono`}
                  allSteps={allSteps}
                  currentStepPosition={currentStepPosition}
                />
              </label>
            </div>
          </div>
        ))
      )}
    </div>
  )
}
