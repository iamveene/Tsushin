'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { ProviderInstance } from '@/lib/client'
import { getPreferredProviderModel, getProviderModelOptions } from '@/lib/provider-models'
import ProviderModelInput from '@/components/providers/ProviderModelInput'
import { isBasicsValid } from '@/lib/agent-wizard/reducer'
import { DEFAULT_AGENT_NAME } from '../defaults'

export default function StepBasics() {
  const { state, patchBasics, markStepComplete } = useAgentWizard()
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [ollamaAvailable, setOllamaAvailable] = useState(false)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    let mounted = true
    api.getProviderInstances().then(pi => {
      if (!mounted) return
      setProviderInstances(pi)
      // Smart defaults if empty
      if (!state.draft.basics.model_provider) {
        const defaultInst = pi.find(p => p.is_default) || pi[0]
        if (defaultInst) {
          patchBasics({
            model_provider: defaultInst.vendor,
            model_name: getPreferredProviderModel(defaultInst.vendor, defaultInst.available_models),
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

  const vendors = useMemo(() => {
    const set = new Map<string, ProviderInstance>()
    for (const pi of providerInstances) {
      if (pi.api_key_configured && !set.has(pi.vendor)) set.set(pi.vendor, pi)
    }
    return Array.from(set.values())
  }, [providerInstances])

  const selectedInstance = providerInstances.find(v => v.id === state.draft.basics.provider_instance_id)
    || vendors.find(v => v.vendor === state.draft.basics.model_provider)
  const vendorInstances = providerInstances.filter(v => v.vendor === state.draft.basics.model_provider)
  const modelOptions = state.draft.basics.model_provider === 'ollama'
    ? ollamaModels
    : getProviderModelOptions(selectedInstance?.vendor, selectedInstance?.available_models || [], {
        currentModel: state.draft.basics.model_name,
      })

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
            onChange={e => {
              const v = e.target.value
              const inst = vendors.find(x => x.vendor === v)
              patchBasics({
                model_provider: v,
                provider_instance_id: inst?.id || null,
                model_name: v === 'ollama'
                  ? ollamaModels[0] || ''
                  : getPreferredProviderModel(v, inst?.available_models || []),
              })
            }}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            <option value="">Select provider</option>
            {vendors.map(v => <option key={v.vendor} value={v.vendor}>{v.vendor}</option>)}
            {ollamaAvailable && <option value="ollama">ollama (local)</option>}
          </select>
        </div>
        <div>
          <label className="block text-xs text-gray-400 mb-1">Model *</label>
          <ProviderModelInput
            vendor={state.draft.basics.model_provider}
            models={modelOptions}
            value={state.draft.basics.model_name}
            onChange={model_name => patchBasics({ model_name })}
            disabled={!state.draft.basics.model_provider}
            placeholder="Select or type a model ID"
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400 disabled:opacity-40"
          />
        </div>
      </div>

      {state.draft.basics.model_provider && vendorInstances.length > 0 && (
        <div>
          <label className="block text-xs text-gray-400 mb-1">Provider instance</label>
          <select
            value={state.draft.basics.provider_instance_id ?? ''}
            onChange={e => {
              const instanceId = e.target.value ? Number(e.target.value) : null
              const inst = providerInstances.find(x => x.id === instanceId)
              patchBasics({
                provider_instance_id: instanceId,
                model_name: inst
                  ? getPreferredProviderModel(inst.vendor, inst.available_models, state.draft.basics.model_name)
                  : state.draft.basics.model_name,
              })
            }}
            className="w-full px-3 py-2 bg-white/[0.02] border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-400"
          >
            <option value="">Use provider default</option>
            {vendorInstances.map(inst => (
              <option key={inst.id} value={inst.id}>
                {inst.instance_name}{inst.is_default ? ' (default)' : ''}{inst.health_status === 'healthy' ? '' : ` [${inst.health_status}]`}
              </option>
            ))}
          </select>
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
