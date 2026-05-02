'use client'

import { useEffect, useMemo, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { api } from '@/lib/client'
import type { LlmCatalogVendor } from '@/lib/client'
import { isBasicsValid } from '@/lib/agent-wizard/reducer'
import ProviderInstancePicker from '@/components/providers/ProviderInstancePicker'
import { DEFAULT_AGENT_NAME } from '../defaults'

export default function StepBasics() {
  const { state, patchBasics, markStepComplete } = useAgentWizard()
  const [catalog, setCatalog] = useState<LlmCatalogVendor[]>([])
  const [loaded, setLoaded] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)

  // Initial smart default: pick the tenant's default-or-first active instance
  // across the whole catalog so the user lands on a working selection.
  useEffect(() => {
    let mounted = true
    api
      .getLlmProvidersCatalog()
      .then((data) => {
        if (!mounted) return
        setCatalog(data)
        if (!state.draft.basics.model_provider) {
          // First vendor with at least one instance, then its default-or-first.
          const firstWithInstance = data.find((v) => v.instances.length > 0)
          if (firstWithInstance) {
            const inst =
              firstWithInstance.instances.find((i) => i.is_default) ||
              firstWithInstance.instances[0]
            if (inst) {
              patchBasics({
                model_provider: firstWithInstance.vendor,
                model_name: inst.available_models[0] || '',
                provider_instance_id: inst.id,
              })
            }
          }
        }
        if (!state.draft.basics.agent_name && state.draft.type) {
          patchBasics({ agent_name: DEFAULT_AGENT_NAME[state.draft.type] })
        }
        setLoaded(true)
      })
      .catch(() => setLoaded(true))
    return () => {
      mounted = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  const phoneError = useMemo(() => {
    const p = state.draft.basics.agent_phone
    if (!p || !p.trim()) return ''
    return /^\+?\d{10,15}$/.test(p.replace(/\s/g, '')) ? '' : 'Use 10–15 digits, optional leading +.'
  }, [state.draft.basics.agent_phone])

  // Step is valid when basics are filled AND the chosen vendor either has
  // an active instance bound (instance_id) OR the user is in the middle of
  // selecting one. Ollama is the only vendor that historically tolerated a
  // null instance — v0.7.0 boot migration creates one automatically, so we
  // now require an instance for every vendor (consistent with Studio edit).
  useEffect(() => {
    const ok =
      isBasicsValid(state.draft.basics) &&
      state.draft.basics.provider_instance_id !== null &&
      state.draft.basics.provider_instance_id !== undefined
    markStepComplete('basics', ok)
  }, [state.draft.basics, markStepComplete])

  if (!loaded) {
    return <div className="py-6 text-center text-sm text-gray-400">Loading providers…</div>
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

      <div>
        <label className="block text-xs text-gray-400 mb-2">LLM Provider *</label>
        <ProviderInstancePicker
          value={{
            vendor: state.draft.basics.model_provider || '',
            instance_id: state.draft.basics.provider_instance_id ?? null,
            model_name: state.draft.basics.model_name || '',
          }}
          onChange={(next) => {
            patchBasics({
              model_provider: next.vendor,
              provider_instance_id: next.instance_id,
              model_name: next.model_name,
            })
          }}
          onInstanceCreated={() => setRefreshKey((k) => k + 1)}
          refreshKey={refreshKey}
        />
        <div className="text-[11px] text-gray-500 mt-1">
          Binds the agent to a specific provider instance (credentials + base URL). Use the
          <span className="text-teal-400"> + New </span> button to wire up a new provider without
          leaving the wizard.
        </div>
      </div>

      {/* Catalog drift sanity check: warn if no vendor has any instances yet */}
      {catalog.every((v) => v.instances.length === 0) && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 text-xs text-amber-200">
          No LLM provider instances configured for this tenant yet. Pick a provider above and click
          <span className="font-medium"> + Create</span> to wire one up — the new instance will
          auto-link to this agent.
        </div>
      )}
    </div>
  )
}
