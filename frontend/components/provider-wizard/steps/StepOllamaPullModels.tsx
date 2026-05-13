'use client'

import { useEffect, useMemo, useState } from 'react'
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
 * Step 4b (Ollama local only) — single model picker.
 *
 * This is the consolidated "pull + expose" step for Ollama. Whatever the
 * user picks here becomes BOTH `pull_models` (fed to the provisioner so
 * the container downloads them) AND `available_models` (what agents can
 * select). Previously the wizard had a separate Step 5 "Pull starter
 * models" followed by Step 6 "Test & choose models" asking for the same
 * list twice — that duplication is gone.
 *
 * Users can pick from curated suggestions or type any custom tag; the
 * provisioner's `pullOllamaModel` call handles download on first use if
 * the tag isn't already cached locally.
 *
 * At least one model must be picked — `ProviderInstanceCreate` requires
 * `available_models.length >= 1`.
 */
export default function StepOllamaPullModels() {
  const { state, patchDraft, markStepComplete } = useProviderWizard()
  const selected = useMemo(() => state.draft.pull_models || [], [state.draft.pull_models])
  const selectedSet = useMemo(() => new Set(selected), [selected])
  const [customInput, setCustomInput] = useState('')

  // Gate Next on having at least one model (matches the ProviderInstanceCreate
  // schema's min-length-1 constraint on `available_models`).
  useEffect(() => {
    markStepComplete('pullModels', selected.length > 0)
  }, [markStepComplete, selected.length])

  // Mirror the chosen list into BOTH pull_models and available_models so
  // the create-provider-instance POST (StepProgress) doesn't have to know
  // about this step's specifics, and Review shows the right model list.
  const updateList = (next: string[]) => {
    patchDraft({ pull_models: next, available_models: next })
  }

  const toggle = (id: string) => {
    updateList(selectedSet.has(id) ? selected.filter(m => m !== id) : [...selected, id])
  }

  const addCustom = () => {
    const v = customInput.trim()
    if (!v || selectedSet.has(v)) { setCustomInput(''); return }
    updateList([...selected, v])
    setCustomInput('')
  }

  const remove = (id: string) => updateList(selected.filter(m => m !== id))

  const clear = () => updateList([])

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Pick models</h3>
        <p className="text-xs text-tsushin-slate">
          Pick one or more — we'll pull them into the container on first use and expose them to your agents.
          You can manage the list later from the Hub Ollama panel.
        </p>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        {SUGGESTED_MODELS.map(m => {
          const active = selectedSet.has(m.id)
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

      {/* Custom model input — any tag works; provisioner pulls on first use. */}
      <div>
        <label className="block text-xs font-medium text-tsushin-fog mb-1.5">Custom model tag</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={customInput}
            onChange={e => setCustomInput(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addCustom() } }}
            placeholder="e.g. llama3.2:8b-instruct-q4_K_M"
            className="flex-1 px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface placeholder:text-tsushin-slate/50 text-sm font-mono"
          />
          <button
            onClick={addCustom}
            disabled={!customInput.trim()}
            className="px-3 py-2 text-sm font-medium rounded-lg border border-tsushin-border text-tsushin-fog hover:text-white hover:border-white/20 transition-colors disabled:opacity-30"
          >
            Add
          </button>
        </div>
        <p className="text-[11px] text-tsushin-slate mt-1.5">
          Any valid Ollama tag works — if it isn't cached locally, the container will pull it on first use.
        </p>
      </div>

      {/* Custom-model chips (only those not already in SUGGESTED_MODELS). */}
      {selected.filter(m => !SUGGESTED_MODELS.some(s => s.id === m)).length > 0 && (
        <div>
          <label className="block text-[11px] text-tsushin-muted mb-1.5">Custom picks</label>
          <div className="flex flex-wrap gap-1.5">
            {selected.filter(m => !SUGGESTED_MODELS.some(s => s.id === m)).map(m => (
              <span key={m} className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-tsushin-indigo/10 text-tsushin-indigo border border-tsushin-indigo/20 rounded-md text-xs font-mono">
                {m}
                <button onClick={() => remove(m)} className="text-tsushin-indigo/60 hover:text-tsushin-indigo transition-colors">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex items-center justify-between text-xs">
        <span className={selected.length === 0 ? 'text-tsushin-vermilion' : 'text-tsushin-slate'}>
          {selected.length === 0
            ? 'Pick at least one model to continue.'
            : `${selected.length} model${selected.length !== 1 ? 's' : ''} selected.`}
        </span>
        {selected.length > 0 && (
          <button onClick={clear} className="text-tsushin-slate hover:text-white underline decoration-dotted">Clear</button>
        )}
      </div>
    </div>
  )
}
