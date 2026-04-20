'use client'

import { useEffect } from 'react'
import { useAgentWizard } from '@/contexts/AgentWizardContext'
import { areChannelsValid } from '@/lib/agent-wizard/reducer'
import { DEFAULT_CHANNELS } from '../defaults'

const CHANNELS: { id: string; label: string; desc: string }[] = [
  { id: 'playground', label: 'Playground', desc: 'Chat in the web playground (always recommended for testing).' },
  { id: 'whatsapp', label: 'WhatsApp', desc: 'Route incoming WhatsApp DMs/groups to this agent.' },
  { id: 'telegram', label: 'Telegram', desc: 'Route Telegram messages to this agent.' },
  { id: 'slack', label: 'Slack', desc: 'Respond to Slack messages and mentions.' },
  { id: 'discord', label: 'Discord', desc: 'Respond to Discord messages and mentions.' },
  { id: 'webhook', label: 'Webhook', desc: 'Expose a webhook endpoint for custom integrations.' },
]

export default function StepChannels() {
  const { state, setChannels, markStepComplete } = useAgentWizard()

  useEffect(() => {
    if (state.draft.channels.length === 0 && state.draft.type) {
      setChannels(DEFAULT_CHANNELS[state.draft.type])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
        {CHANNELS.map(c => {
          const selected = state.draft.channels.includes(c.id)
          return (
            <button
              key={c.id}
              type="button"
              onClick={() => toggle(c.id)}
              className={`text-left p-3 rounded-xl border transition-colors ${
                selected ? 'border-teal-400 bg-teal-500/10' : 'border-white/10 bg-white/[0.02] hover:border-white/20'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="text-white font-medium text-sm">{c.label}</div>
                {selected && <span className="w-4 h-4 rounded-full bg-teal-500 text-white flex items-center justify-center text-xs">✓</span>}
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
