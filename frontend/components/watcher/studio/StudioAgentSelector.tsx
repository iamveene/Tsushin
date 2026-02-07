'use client'

import { useState } from 'react'
import Modal from '@/components/ui/Modal'
import { api } from '@/lib/client'
import type { Agent } from '@/lib/client'

interface StudioAgentSelectorProps {
  agents: Agent[]
  selectedAgentId: number | null
  onAgentSelect: (agentId: number) => void
  onAgentCreated: (agentId: number) => void
}

export default function StudioAgentSelector({ agents, selectedAgentId, onAgentSelect, onAgentCreated }: StudioAgentSelectorProps) {
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newAgentName, setNewAgentName] = useState('')
  const [newAgentModel, setNewAgentModel] = useState('openrouter')
  const [createError, setCreateError] = useState('')
  const selectedAgent = agents.find(a => a.id === selectedAgentId)

  const handleCreate = async () => {
    if (!newAgentName.trim()) { setCreateError('Agent name is required'); return }
    setCreating(true); setCreateError('')
    try {
      const defaultContactId = agents[0]?.contact_id || 1
      const agent = await api.createAgent({
        contact_id: defaultContactId,
        system_prompt: `You are ${newAgentName.trim()}, a helpful AI assistant.`,
        model_provider: newAgentModel,
        model_name: newAgentModel === 'openrouter' ? 'google/gemini-2.0-flash-001' : 'gpt-4o-mini',
        is_active: true,
      })
      setShowCreateModal(false); setNewAgentName(''); onAgentCreated(agent.id)
    } catch (err) { setCreateError(err instanceof Error ? err.message : 'Failed to create agent') }
    finally { setCreating(false) }
  }

  return (
    <div className="flex items-center gap-3">
      <svg className="w-5 h-5 text-tsushin-indigo" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
      </svg>
      <div className="relative">
        <select value={selectedAgentId ?? ''} onChange={(e) => e.target.value && onAgentSelect(Number(e.target.value))}
          className="appearance-none bg-tsushin-surface border border-tsushin-border rounded-lg px-4 py-2 pr-8 text-sm text-white focus:outline-none focus:border-tsushin-indigo transition-colors min-w-[200px]">
          <option value="">Select an agent...</option>
          {agents.map(agent => (
            <option key={agent.id} value={agent.id}>
              {agent.contact_name} {!agent.is_active ? '(inactive)' : ''} — {agent.model_provider}/{agent.model_name}
            </option>
          ))}
        </select>
        <svg className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-tsushin-muted pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
      {selectedAgent && (
        <div className="flex items-center gap-2 text-sm">
          <span className={`w-2 h-2 rounded-full ${selectedAgent.is_active ? 'bg-green-400' : 'bg-gray-500'}`} />
          <span className="text-tsushin-muted">{selectedAgent.skills_count || 0} skills</span>
        </div>
      )}
      <button onClick={() => setShowCreateModal(true)} className="p-2 rounded-lg bg-tsushin-surface border border-tsushin-border hover:border-tsushin-indigo transition-colors" title="Create new agent">
        <svg className="w-4 h-4 text-tsushin-slate" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4.5v15m7.5-7.5h-15" /></svg>
      </button>
      <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title="Create New Agent" size="md"
        footer={<div className="flex justify-end gap-3">
          <button onClick={() => setShowCreateModal(false)} className="px-4 py-2 text-sm text-tsushin-slate hover:text-white transition-colors">Cancel</button>
          <button onClick={handleCreate} disabled={creating} className="px-4 py-2 text-sm bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90 disabled:opacity-50 transition-all">{creating ? 'Creating...' : 'Create Agent'}</button>
        </div>}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-1">Agent Name</label>
            <input type="text" value={newAgentName} onChange={(e) => setNewAgentName(e.target.value)} placeholder="e.g., Customer Support Bot"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo" autoFocus />
          </div>
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-1">Model Provider</label>
            <select value={newAgentModel} onChange={(e) => setNewAgentModel(e.target.value)}
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo">
              <option value="openrouter">OpenRouter</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option>
            </select>
          </div>
          {createError && <p className="text-sm text-red-400">{createError}</p>}
        </div>
      </Modal>
    </div>
  )
}
