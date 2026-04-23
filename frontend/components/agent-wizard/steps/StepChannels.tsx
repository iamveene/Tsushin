'use client'

import { useEffect, useState } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { areChannelsValid } from '@/lib/agent-wizard/reducer'
import { DEFAULT_CHANNELS } from '../defaults'
import { api } from '@/lib/client'
import type { ChannelCatalogEntry } from '@/lib/client'

// Shape rendered by the wizard — derived from the backend catalog when
// available, otherwise from the static fallback below.
interface ChannelRow {
  id: string
  label: string
  desc: string
  requiresSetup: boolean
  tenantHasConfigured: boolean
}

// FALLBACK ONLY — used when GET /api/channels is unreachable (offline /
// degraded mode / first render before fetch resolves). The authoritative
// catalog lives in backend/channels/catalog.py and is cross-checked against
// this array by backend/tests/test_wizard_drift.py so the two can't drift.
const CHANNELS: { id: string; label: string; desc: string; requiresSetup: boolean }[] = [
  { id: 'playground', label: 'Playground', desc: 'Chat in the web playground (always recommended for testing).', requiresSetup: false },
  { id: 'whatsapp', label: 'WhatsApp', desc: 'Route incoming WhatsApp DMs/groups to this agent.', requiresSetup: true },
  { id: 'telegram', label: 'Telegram', desc: 'Route Telegram messages to this agent.', requiresSetup: true },
  { id: 'slack', label: 'Slack', desc: 'Respond to Slack messages and mentions.', requiresSetup: true },
  { id: 'discord', label: 'Discord', desc: 'Respond to Discord messages and mentions.', requiresSetup: true },
]

function rowsFromFallback(): ChannelRow[] {
  return CHANNELS.map(c => ({
    id: c.id,
    label: c.label,
    desc: c.desc,
    requiresSetup: c.requiresSetup,
    // Without backend data we can't know — optimistically assume configured
    // so the wizard doesn't nag with "Needs setup" badges during outages.
    tenantHasConfigured: true,
  }))
}

function rowsFromBackend(entries: ChannelCatalogEntry[]): ChannelRow[] {
  return entries.map(e => ({
    id: e.id,
    label: e.display_name,
    desc: e.description,
    requiresSetup: e.requires_setup,
    tenantHasConfigured: e.tenant_has_configured,
  }))
}

export default function StepChannels() {
  const { state, setChannels, markStepComplete } = useAgentWizard()
  const [catalog, setCatalog] = useState<ChannelRow[]>(() => rowsFromFallback())

  useEffect(() => {
    if (state.draft.channels.length === 0 && state.draft.type) {
      setChannels(DEFAULT_CHANNELS[state.draft.type])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    let cancelled = false
    api.getChannelCatalog()
      .then(entries => {
        if (cancelled) return
        if (entries.length > 0) setCatalog(rowsFromBackend(entries))
      })
      .catch(() => {
        // Network or auth failure — keep fallback already in state.
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    markStepComplete('channels', areChannelsValid(state.draft.channels))
  }, [state.draft.channels, markStepComplete])

  const toggle = (id: string) => {
    const set = new Set(state.draft.channels)
    if (set.has(id)) set.delete(id)
    else set.add(id)
    setChannels(Array.from(set))
  }

  return (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-semibold text-white mb-1">Where will it live?</h3>
        <p className="text-sm text-gray-300">Bind channels now or keep it in Playground to test first.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        {catalog.map(c => {
          const selected = state.draft.channels.includes(c.id)
          const needsSetup = c.requiresSetup && !c.tenantHasConfigured
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => toggle(c.id)}
              className={`text-left p-3 rounded-xl border transition-colors ${
                selected ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="text-white font-medium text-sm">{c.label}</div>
                <div className="flex items-center gap-2">
                  {needsSetup && (
                    <span className="px-2 py-0.5 text-[10px] uppercase tracking-wider rounded-full bg-amber-500/15 text-amber-300 border border-amber-400/30">
                      Needs setup
                    </span>
                  )}
                  {selected && <span className="w-4 h-4 rounded-full bg-teal-500 text-white flex items-center justify-center text-xs">✓</span>}
                </div>
              </div>
              <div className="text-xs text-gray-400 mt-0.5">{c.desc}</div>
            </button>
          )
        })}
      </div>

      <div className="text-xs text-gray-500">
        Channel bindings to specific integrations (e.g., a WhatsApp instance) can be adjusted from the agent's Channels tab after creation.
      </div>
    </div>
  )
}
