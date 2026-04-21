'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { ProviderInstance } from '@/lib/client'
import { isBasicsValid } from '@/lib/agent-wizard/reducer'
import { DEFAULT_AGENT_NAME } from '../defaults'

// Health badge shown next to each instance in the dropdown. Kept short so it
// fits in a <select> entry; the full reason is tooltipped on hover.
function instanceLabel(inst: ProviderInstance): string {
  const bits: string[] = [inst.instance_name]
  if (inst.is_default) bits.push('(default)')
  if (inst.health_status && inst.health_status !== 'healthy') bits.push(`[${inst.health_status}]`)
  return bits.join(' ')
}

export default function StepBasics() {
  const { state, patchBasics, markStepComplete } = useAgentWizard()
  const [allInstances, setAllInstances] = useState<ProviderInstance[]>([])
  const [ollamaAvailable, setOllamaAvailable] = useState(false)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let mounted = true
    api.getProviderInstances().then(pi => {
      if (!mounted) return
      setAllInstances(pi)
      // Smart defaults if the user hasn't picked yet: prefer the tenant's
      // default provider instance, otherwise fall back to the first active one.
      if (!state.draft.basics.model_provider) {
        const configured = pi.filter(p => p.api_key_configured && p.is_active)
        const defaultInst = configured.find(p => p.is_default) || configured[0]
        if (defaultInst) {
          patchBasics({
            model_provider: defaultInst.vendor,
            model_name: defaultInst.available_models[0] || '',
            provider_instance_id: defaultInst.id,
          })
        }
      }
      if (!state.draft.basics.agent_name && state.draft.type) {
        patchBasics({ agent_name: DEFAULT_AGENT_NAME[state.draft.type] })
      }
      setLoaded(true)
    }).catch(() => setLoaded(true))
    // Ollama liveness (best-effort)
    fetch('http://localhost:11434/api/tags').then(r => r.json()).then(d => {
      if (!mounted) return
      setOllamaAvailable(true)
      setOllamaModels((d.models || []).map((m: any) => m.name))
    }).catch(() => { /* no ollama */ })
    return () => { mounted = false }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Unique list of vendors the tenant has configured (at least one active,
  // credentialed instance). Order preserved from the API.
  const vendors = useMemo(() => {
    const seen = new Set<string>()
    const out: string[] = []
    for (const pi of allInstances) {
      if (!pi.api_key_configured || !pi.is_active) continue
      if (!seen.has(pi.vendor)) {
        seen.add(pi.vendor)
        out.push(pi.vendor)
      }
    }
    return out
  }, [allInstances])

  const vendorInstances = useMemo(() => {
    const v = state.draft.basics.model_provider
    if (!v || v === 'ollama') return []
    return allInstances.filter(pi => pi.vendor === v && pi.is_active)
  }, [state.draft.basics.model_provider, allInstances])

  const selectedInstance = useMemo(
    () => vendorInstances.find(i => i.id === state.draft.basics.provider_instance_id) || null,
    [vendorInstances, state.draft.basics.provider_instance_id],
  )

  const modelOptions = state.draft.basics.model_provider === 'ollama'
    ? ollamaModels
    : (selectedInstance?.available_models || [])

  const phoneError = useMemo(() => {
    const p = state.draft.basics.agent_phone
    if (!p || !p.trim()) return ''
    return /^\+?\d{10,15}$/.test(p.replace(/\s/g, '')) ? '' : 'Use 10–15 digits, optional leading +.'
  }, [state.draft.basics.agent_phone])

  useEffect(() => {
    const ok = isBasicsValid(state.draft.basics)
      && (state.draft.basics.model_provider !== 'ollama' || ollamaAvailable)
    markStepComplete('basics', ok)
  }, [state.draft.basics, ollamaAvailable, markStepComplete])

  if (!loaded) {
    return <div className="py-6 text-center text-sm text-gray-400">Loading providers…</div>
  }

  if (vendors.length === 0 && !ollamaAvailable) {
    return (
      <div className="space-y-4">
        <h3 className="text-lg font-semibold text-white">Name & model</h3>
        <div className="p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-sm text-amber-200">
          <div className="font-medium mb-1">No AI providers configured yet</div>
          <div>Set up at least one provider in <a className="underline" href="/hub?tab=ai-providers">Hub → AI Providers</a>, then come back.</div>
        </div>
      </div>
    )
  }

  const onVendorChange = (vendor: string) => {
    if (vendor === 'ollama') {
      patchBasics({
        model_provider: vendor,
        provider_instance_id: null,
        model_name: ollamaModels[0] || '',
      })
      return
    }
    const insts = allInstances.filter(pi => pi.vendor === vendor && pi.is_active)
    const defaultInst = insts.find(i => i.is_default) || insts[0] || null
    patchBasics({
      model_provider: vendor,
      provider_instance_id: defaultInst?.id ?? null,
      model_name: defaultInst?.available_models[0] || '',
    })
  }

  const onInstanceChange = (idStr: string) => {
    const id = idStr ? parseInt(idStr, 10) : null
    const inst = id ? vendorInstances.find(i => i.id === id) : null
    patchBasics({
      provider_instance_id: id,
      model_name: inst?.available_models[0] || state.draft.basics.model_name,
    })
  }

  return (
    <div className="space-y-5">
      <h3 className="text-lg font-semibold text-white">Name & model</h3>

      <div>
        <label className="block text-xs text-gray-400 mb-1">Agent name *</label>
        <input
          type="text"
          value={state.draft.basics.agent_name}
          onChange={e => patchBasics({ agent_name: e.target.value })}
          placeholder="My Assistant"
          className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
        />
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">Phone number (optional)</label>
        <input
          type="text"
          value={state.draft.basics.agent_phone}
          onChange={e => patchBasics({ agent_phone: e.target.value })}
          placeholder="+15551234567"
          className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
        />
        {phoneError && <div className="text-xs text-red-300 mt-1">{phoneError}</div>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-xs text-gray-400 mb-1">Provider *</label>
          <select
            value={state.draft.basics.model_provider}
            onChange={e => onVendorChange(e.target.value)}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            <option value="">Select provider</option>
            {vendors.map(v => <option key={v} value={v}>{v}</option>)}
            {ollamaAvailable && <option value="ollama">ollama (local)</option>}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Model *</label>
          <select
            value={state.draft.basics.model_name}
            onChange={e => patchBasics({ model_name: e.target.value })}
            disabled={!state.draft.basics.model_provider || (state.draft.basics.model_provider !== 'ollama' && !state.draft.basics.provider_instance_id)}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400 disabled:opacity-40"
          >
            <option value="">Select model</option>
            {modelOptions.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>

      {/* Provider instance selector — hidden for Ollama (no credentials) */}
      {state.draft.basics.model_provider && state.draft.basics.model_provider !== 'ollama' && (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Provider instance *</label>
          {vendorInstances.length === 0 ? (
            <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200">
              No active instances for <span className="font-mono">{state.draft.basics.model_provider}</span>. Configure one at <a className="underline" href="/hub?tab=ai-providers">Hub → AI Providers</a>.
            </div>
          ) : (
            <select
              value={state.draft.basics.provider_instance_id ?? ''}
              onChange={e => onInstanceChange(e.target.value)}
              className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
            >
              <option value="">Select an instance</option>
              {vendorInstances.map(inst => (
                <option key={inst.id} value={inst.id} title={inst.health_status_reason || undefined}>
                  {instanceLabel(inst)}
                </option>
              ))}
            </select>
          )}
          <div className="text-[11px] text-gray-500 mt-1">
            Binds the agent to the credentials and base URL of this specific instance.
          </div>
        </div>
      )}

      {state.draft.basics.model_provider === 'ollama' && !ollamaAvailable && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200">
          Ollama isn't running locally. Start it with <code className="px-1 py-0.5 bg-white/5 rounded">ollama serve</code> or pick a different provider.
        </div>
      )}
    </div>
  )
}
