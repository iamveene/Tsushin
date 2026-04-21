'use client'

import { useEffect, useMemo, useState } from 'react'
import { useProviderWizard } from '@/contexts/ProviderWizardContext'
import { api } from '@/lib/client'
import type { Agent } from '@/lib/client'
import { CheckCircleIcon, AlertTriangleIcon } from '@/components/ui/icons'

type Status = 'pending' | 'applying' | 'done' | 'error'

interface AssignResult {
  agent_id: number
  agent_name: string
  status: Status
  error?: string
}

/**
 * Post-create step — wire the newly-created LLM provider instance to
 * existing agents without round-tripping through Agent Studio.
 *
 * Included for every `modality='llm'` flow (Cloud OpenAI/Anthropic/
 * Gemini/Vertex/Groq/Grok/DeepSeek/OpenRouter + self-hosted Ollama).
 * TTS/Image have their own assign flows and skip this step.
 *
 * Uses `POST /api/provider-instances/{id}/assign-to-agent` (routes_provider_instances.py)
 * which overwrites Agent.provider_instance_id + Agent.model_name +
 * Agent.model_provider in one shot — it REPLACES whatever LLM the agent
 * was previously bound to. Tenant isolation is enforced on both rows.
 *
 * Skip is first-class: users can always wire later from Agent Studio.
 */
export default function StepAssignAgents() {
  const { state } = useProviderWizard()
  const { created_instance_id, available_models, vendor } = state.draft

  const [agents, setAgents] = useState<Agent[] | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [modelName, setModelName] = useState<string>('')
  const [results, setResults] = useState<AssignResult[]>([])
  const [loading, setLoading] = useState(true)
  const [applying, setApplying] = useState(false)

  // Default model to the first available. If the user picked no models here,
  // fall back to empty — the backend requires a model_name so we'll block
  // Apply until they pick one.
  useEffect(() => {
    if (available_models.length > 0 && !modelName) {
      setModelName(available_models[0])
    }
  }, [available_models, modelName])

  // Load agents on mount.
  useEffect(() => {
    let cancelled = false
    api.getAgents()
      .then(list => { if (!cancelled) setAgents(list) })
      .catch(() => { if (!cancelled) setAgents([]) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const toggle = (id: number) => {
    const next = new Set(selectedIds)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelectedIds(next)
  }

  const allDone = results.length > 0 && results.every(r => r.status === 'done' || r.status === 'error')

  const apply = async () => {
    if (!created_instance_id || selectedIds.size === 0 || !modelName) return
    setApplying(true)
    const picked = (agents || []).filter(a => selectedIds.has(a.id))
    // `Agent.contact_name` is the tenant-facing display name (the model has
    // no `name` field — that caused the inline rows to render an empty
    // label on first-pass implementation).
    const initial: AssignResult[] = picked.map(a => ({ agent_id: a.id, agent_name: a.contact_name, status: 'applying' }))
    setResults(initial)
    for (const a of picked) {
      try {
        await api.assignOllamaInstanceToAgent(created_instance_id, {
          agent_id: a.id,
          model_name: modelName,
        })
        setResults(prev => prev.map(r => r.agent_id === a.id ? { ...r, status: 'done' } : r))
      } catch (err: any) {
        setResults(prev => prev.map(r => r.agent_id === a.id ? { ...r, status: 'error', error: err?.message || 'Assign failed' } : r))
      }
    }
    setApplying(false)
  }

  const canApply = !applying && !allDone && selectedIds.size > 0 && !!modelName && !!created_instance_id

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-base font-semibold text-white mb-1">Link to agents</h3>
        <p className="text-xs text-tsushin-slate">
          Optional — switch existing agents over to this new <span className="font-mono text-tsushin-accent">{vendor}</span> instance now.
          You can always do this later from Agent Studio.
        </p>
        <p className="text-[11px] text-amber-300/80 mt-1.5">
          Note: this <strong>replaces</strong> each selected agent's current LLM (provider + model). It doesn't stack.
        </p>
      </div>

      {/* Model picker */}
      <div>
        <label className="block text-xs font-medium text-tsushin-fog mb-1.5">Model to assign</label>
        <select
          value={modelName}
          onChange={e => setModelName(e.target.value)}
          disabled={applying || allDone}
          className="w-full px-3 py-2 border border-tsushin-border rounded-lg text-white bg-tsushin-surface text-sm font-mono disabled:opacity-50"
        >
          {available_models.length === 0 && <option value="">(no models configured)</option>}
          {available_models.map(m => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      {/* Agent list */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-tsushin-fog">Agents</label>
          {agents && agents.length > 0 && !allDone && (
            <button
              onClick={() => setSelectedIds(selectedIds.size === agents.length ? new Set() : new Set(agents.map(a => a.id)))}
              className="text-[11px] text-tsushin-slate hover:text-white underline decoration-dotted"
            >
              {selectedIds.size === agents.length ? 'Clear all' : 'Select all'}
            </button>
          )}
        </div>
        {loading ? (
          <p className="text-xs text-tsushin-slate italic">Loading agents…</p>
        ) : !agents || agents.length === 0 ? (
          <p className="text-xs text-tsushin-slate italic">No agents yet — create one in Agent Studio, then link this instance to it.</p>
        ) : (
          <div className="space-y-1.5 max-h-80 overflow-y-auto">
            {agents.map(a => {
              const result = results.find(r => r.agent_id === a.id)
              const checked = selectedIds.has(a.id)
              const currentModel = a.model_name ? `${a.model_provider || '—'}/${a.model_name}` : '(no LLM assigned)'
              return (
                <label
                  key={a.id}
                  className={`flex items-start gap-2 p-2.5 rounded-lg border transition-colors ${
                    checked || result
                      ? 'border-teal-500/40 bg-teal-500/5'
                      : 'border-tsushin-border bg-tsushin-ink/40 hover:border-tsushin-accent/50'
                  } ${applying || allDone ? 'cursor-default' : 'cursor-pointer'}`}
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => !applying && !allDone && toggle(a.id)}
                    disabled={applying || allDone}
                    className="mt-0.5 accent-teal-500"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm text-white font-medium truncate">{a.contact_name || `Agent #${a.id}`}</span>
                      {result?.status === 'done' && (
                        <span className="flex items-center gap-1 text-[11px] text-tsushin-success shrink-0">
                          <CheckCircleIcon size={12} /> Linked
                        </span>
                      )}
                      {result?.status === 'error' && (
                        <span className="flex items-center gap-1 text-[11px] text-tsushin-vermilion shrink-0" title={result.error}>
                          <AlertTriangleIcon size={12} /> Failed
                        </span>
                      )}
                      {result?.status === 'applying' && (
                        <span className="text-[11px] text-tsushin-slate shrink-0">Linking…</span>
                      )}
                    </div>
                    <p className="text-[11px] text-tsushin-slate mt-0.5 font-mono truncate">
                      Currently: {currentModel}
                    </p>
                  </div>
                </label>
              )
            })}
          </div>
        )}
      </div>

      {/* Apply / summary footer (inline — the modal footer handles Skip/Done) */}
      <div className="flex items-center justify-between pt-2 border-t border-white/5">
        <span className="text-[11px] text-tsushin-slate">
          {allDone
            ? `${results.filter(r => r.status === 'done').length} / ${results.length} agents linked.`
            : selectedIds.size > 0
              ? `${selectedIds.size} agent${selectedIds.size !== 1 ? 's' : ''} selected.`
              : 'Select one or more agents to link.'}
        </span>
        <button
          onClick={apply}
          disabled={!canApply}
          className="px-4 py-2 text-sm font-medium rounded-lg bg-teal-500 hover:bg-teal-400 text-white transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {applying ? 'Applying…' : allDone ? 'Done' : 'Apply'}
        </button>
      </div>
    </div>
  )
}
