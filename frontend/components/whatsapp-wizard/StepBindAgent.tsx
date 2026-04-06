'use client'

import { useState, useEffect } from 'react'
import { api, Agent } from '@/lib/client'
import { useWhatsAppWizard } from '@/contexts/WhatsAppWizardContext'

export default function StepBindAgent() {
  const { state, setBoundAgent, markStepComplete, nextStep } = useWhatsAppWizard()

  const [agents, setAgents] = useState<Agent[]>([])
  const [selectedAgentId, setSelectedAgentId] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.getAgents().then((list) => {
      setAgents(list)
      // Pre-select the default agent if any
      const defaultAgent = list.find((a) => a.is_default)
      if (defaultAgent) setSelectedAgentId(defaultAgent.id)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const handleBind = async () => {
    if (!selectedAgentId || !state.createdInstanceId) return
    setSaving(true)
    setError(null)
    try {
      const agent = agents.find((a) => a.id === selectedAgentId)
      if (!agent) throw new Error('Agent not found')

      // Enable WhatsApp channel and bind instance
      const currentChannels = agent.enabled_channels || ['playground']
      const newChannels = currentChannels.includes('whatsapp')
        ? currentChannels
        : [...currentChannels, 'whatsapp']

      await api.updateAgent(selectedAgentId, {
        enabled_channels: newChannels,
        whatsapp_integration_id: state.createdInstanceId,
      })

      // Link user contact to selected agent
      if (state.userContact) {
        try { await api.setContactAgentMapping(state.userContact.id, selectedAgentId) } catch {}
      }
      // Link bot contact to selected agent
      if (state.botContact) {
        try { await api.setContactAgentMapping(state.botContact.id, selectedAgentId) } catch {}
      }

      setBoundAgent(selectedAgentId, agent.contact_name)
      markStepComplete(7)
      nextStep()
    } catch (e: any) {
      setError(e.message || 'Failed to bind agent')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-8 h-8 border-2 border-teal-500 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <p className="text-tsushin-slate text-sm">
        Choose which AI agent handles messages from this WhatsApp number. The agent will receive all incoming messages and generate responses.
      </p>

      {agents.length === 0 ? (
        <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-4 text-center">
          <p className="text-sm text-amber-300">
            No agents found. You can create agents in the Studio page and come back to bind them later.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {agents.map((agent) => {
            const isSelected = selectedAgentId === agent.id
            const alreadyBound = agent.whatsapp_integration_id && agent.whatsapp_integration_id !== state.createdInstanceId
            return (
              <button
                key={agent.id}
                onClick={() => setSelectedAgentId(agent.id)}
                disabled={!!alreadyBound}
                className={`w-full text-left p-4 rounded-xl border transition-all ${
                  isSelected
                    ? 'border-teal-500 bg-teal-500/10'
                    : alreadyBound
                    ? 'border-tsushin-border/50 bg-tsushin-deep/30 opacity-50 cursor-not-allowed'
                    : 'border-tsushin-border bg-tsushin-deep/50 hover:border-tsushin-slate/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-white">{agent.contact_name}</span>
                      {agent.is_default && (
                        <span className="text-[10px] bg-teal-500/20 text-teal-300 px-1.5 py-0.5 rounded">Default</span>
                      )}
                      {alreadyBound && (
                        <span className="text-[10px] bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded">Already bound</span>
                      )}
                    </div>
                    <p className="text-xs text-tsushin-slate mt-1 line-clamp-1">
                      {agent.system_prompt?.substring(0, 80)}...
                    </p>
                  </div>
                  <div
                    className={`w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                      isSelected ? 'border-teal-500 bg-teal-500' : 'border-tsushin-slate/40'
                    }`}
                  >
                    {isSelected && (
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                  </div>
                </div>
              </button>
            )
          })}
        </div>
      )}

      <p className="text-xs text-tsushin-slate">
        The selected agent will handle messages from your WhatsApp contacts.
      </p>

      {error && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3">
          <p className="text-sm text-red-400">{error}</p>
        </div>
      )}

      <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-3">
        <p className="text-xs text-blue-300">
          <span className="font-semibold">What happens:</span> The selected agent's WhatsApp channel will be enabled and linked to {state.createdInstance?.phone_number || 'your number'}. Messages to this number will be routed to this agent.
        </p>
      </div>

      <button
        onClick={handleBind}
        disabled={saving || !selectedAgentId}
        className="w-full py-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-medium rounded-lg transition-colors"
      >
        {saving ? 'Binding...' : 'Bind Agent & Continue'}
      </button>
    </div>
  )
}
