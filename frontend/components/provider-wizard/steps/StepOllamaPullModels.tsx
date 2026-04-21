'use client'

import { useEffect, useMemo } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'

/**
 * Curated starter models surfaced on this step. Keep the list short —
 * users can pull anything via the main Ollama panel later.
 */
const SUGGESTED_MODELS: Array<{ id: string; label: string; hint: string }> = [
  { id: 'llama3.2:3b',            label: 'llama3.2:3b',            hint: 'Small, fast — good for chat' },
  { id: 'llama3.1:8b',            label: 'llama3.1:8b',            hint: 'Balanced — 8B params' },
  { id: 'qwen2.5:7b',             label: 'qwen2.5:7b',             hint: 'Strong multilingual, coding' },
  { id: 'mistral:7b',             label: 'mistral:7b',             hint: 'Classic Mistral 7B' },
  { id: 'phi3:3.8b',              label: 'phi3:3.8b',              hint: 'Tiny but capable (Microsoft)' },
  { id: 'gemma2:9b',              label: 'gemma2:9b',              hint: 'Google Gemma 2' },
]

/**
 * Step 4b (Ollama only) — starter model picker.
 *
 * The user can pick zero-or-more models to pull after provisioning. Skip is
 * first-class: this step is always "complete" because the backend will simply
 * not issue any pull jobs when `pull_models` is empty.
 */
export default function StepOllamaPullModels() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const selected = useMemo(() => new Set(state.draft.pull_models || []), [state.draft.pull_models])

  // Always complete — Skip is a valid outcome.
  useEffect(() => {
    markStepComplete('pullModels', true)
  }, [markStepComplete])

  const toggle = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    patchDraft({ pull_models: Array.from(next) })
  }

  const clear = () => patchDraft({ pull_models: [] })

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Pull starter models?</h3>
        <p className="text-xs text-tsushin-slate">Optional — pick zero or more to pull after the container comes up. You can pull more later from the Ollama panel.</p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {SUGGESTED_MODELS.map(m => {
          const active = selected.has(m.id)
          return (
            <button
              key={m.id}
              onClick={() => toggle(m.id)}
              className={`text-left rounded-lg border p-3 transition-all ${
                active
                  ? 'border-teal-500 bg-teal-500/10'
                  : 'border-tsushin-border bg-tsushin-ink/40 hover:border-tsushin-accent/50'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-xs text-white">{m.label}</span>
                {active && <span className="text-[10px] text-teal-400">Selected</span>}
              </div>
              <p className="text-[11px] text-tsushin-slate mt-1">{m.hint}</p>
            </button>
          )
        })}
      </div>

      <div className="flex items-center justify-between text-xs">
        <span className="text-tsushin-slate">
          {selected.size === 0 ? 'None selected — we\'ll skip the pull step.' : `${selected.size} model${selected.size !== 1 ? 's' : ''} queued for pull.`}
        </span>
        {selected.size > 0 && (
          <button onClick={clear} className="text-tsushin-slate hover:text-white underline decoration-dotted">Clear</button>
        )}
      </div>
    </div>
  )
}
