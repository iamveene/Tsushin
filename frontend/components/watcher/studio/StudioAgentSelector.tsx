'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Modal from '@/components/ui/Modal'
import { api, VENDOR_LABELS } from '@/lib/client'
import type { Agent, ProviderInstance } from '@/lib/client'
import { AgentAvatarIcon } from './avatars/AgentAvatars'
import { useAudioWizard } from '@/contexts/AudioWizardContext'

type NewAgentKind = 'text' | 'voice' | 'hybrid'
// v0.7.0-fix Phase 6b: explicit wake-mode at agent creation so users
// don't have to learn that Continuous Agents are configured separately.
// 'conversational' = direct chat (default); 'continuous' = wakened by
// external triggers and configured via the Continuous Agent setup modal
// after the base agent is created.
type WakeMode = 'conversational' | 'continuous'

interface StudioAgentSelectorProps {
  agents: Agent[]
  selectedAgentId: number | null
  onAgentSelect: (agentId: number) => void
  onAgentCreated: (agentId: number) => void
}

export default function StudioAgentSelector({ agents, selectedAgentId, onAgentSelect, onAgentCreated }: StudioAgentSelectorProps) {
  const router = useRouter()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [newAgentKind, setNewAgentKind] = useState<NewAgentKind>('text')
  const [newWakeMode, setNewWakeMode] = useState<WakeMode>('conversational')
  const [newAgentName, setNewAgentName] = useState('')
  const [newAgentVendor, setNewAgentVendor] = useState('')
  const [newAgentModel, setNewAgentModel] = useState('')
  const [newAgentInstanceId, setNewAgentInstanceId] = useState<number | null>(null)
  const [createError, setCreateError] = useState('')
  const [allInstances, setAllInstances] = useState<ProviderInstance[]>([])
  const selectedAgent = agents.find(a => a.id === selectedAgentId)
  const { openWizard: openAudioWizard } = useAudioWizard()

  // Fetch all configured provider instances once on mount
  useEffect(() => {
    api.getProviderInstances().then(instances => {
      setAllInstances(instances)
      // Default to the first configured vendor
      if (instances.length > 0) {
        const first = instances.find(i => i.is_default) || instances[0]
        setNewAgentVendor(first.vendor)
        setNewAgentModel(first.available_models[0] || '')
        setNewAgentInstanceId(first.id)
      }
    }).catch(() => {})
  }, [])

  // Vendors that have at least one configured instance
  const configuredVendors = [...new Set(allInstances.map(i => i.vendor))]
    .map(v => ({ value: v, label: VENDOR_LABELS[v] || v }))

  // Instances for the currently selected vendor
  const vendorInstances = allInstances.filter(i => i.vendor === newAgentVendor)

  const handleVendorChange = (vendor: string) => {
    setNewAgentVendor(vendor)
    const instances = allInstances.filter(i => i.vendor === vendor)
    const defaultInst = instances.find(i => i.is_default) || instances[0]
    if (defaultInst) {
      setNewAgentModel(defaultInst.available_models[0] || '')
      setNewAgentInstanceId(defaultInst.id)
    } else {
      setNewAgentModel('')
      setNewAgentInstanceId(null)
    }
  }

  const handleCreate = async () => {
    if (!newAgentName.trim()) { setCreateError('Agent name is required'); return }

    // Voice/Hybrid kinds hand off to the Audio Agents wizard so TTS/transcription
    // skills get wired correctly in a single flow.
    if (newAgentKind === 'voice' || newAgentKind === 'hybrid') {
      setShowCreateModal(false)
      openAudioWizard({
        presetMode: 'new',
        presetAgentType: newAgentKind === 'voice' ? 'voice' : 'hybrid',
        presetNewAgentName: newAgentName.trim(),
      })
      setNewAgentName('')
      setNewAgentKind('text')
      return
    }

    if (!newAgentVendor) { setCreateError('Select a provider — configure one in Hub > AI Providers first'); return }
    if (!newAgentModel.trim()) { setCreateError('Model name is required'); return }
    setCreating(true); setCreateError('')
    try {
      const defaultContactId = agents[0]?.contact_id || 1
      // BUG-602 FIX: Unify the create-agent payload with the main Agents
      // page modal (frontend/app/agents/page.tsx::handleCreate). The two
      // flows used to produce visibly different agents — the studio
      // path omitted ``keywords`` / ``tone_preset_id`` / ``custom_tone``
      // / ``persona_id``, so agents created from Studio came out
      // persona-less and tone-less while agents created from /agents
      // inherited tenant smart-defaults. Now both flows send the same
      // explicit-null shape and the backend applies the SAME defaults.
      const agent = await api.createAgent({
        contact_id: defaultContactId,
        system_prompt: `You are ${newAgentName.trim()}, a helpful AI assistant.`,
        model_provider: newAgentVendor,
        model_name: newAgentModel,
        provider_instance_id: newAgentInstanceId ?? undefined,
        is_active: true,
        persona_id: null,
        tone_preset_id: null,
        custom_tone: null,
        keywords: [],
        is_default: false,
      } as any)
      setShowCreateModal(false); setNewAgentName('')
      // v0.7.0-fix Phase 6b: when the user picks Continuous wake mode,
      // hand off to /continuous-agents with the agent_id pre-filled so the
      // setup modal opens with the base agent already selected — closes
      // the loop the user complained about ("Why is this not a wizard
      // option for new agent created via Studio?").
      if (newWakeMode === 'continuous') {
        router.push(`/continuous-agents?new=1&agent_id=${agent.id}`)
        setNewWakeMode('conversational')
        return
      }
      onAgentCreated(agent.id)
    } catch (err) { setCreateError(err instanceof Error ? err.message : 'Failed to create agent') }
    finally { setCreating(false) }
  }

  // BUG-602 FIX: Offer a shortcut to the full /agents create modal for
  // users who need persona/tone/keywords — keeps the studio quick-create
  // for the 80% "I just need a bot" case while routing advanced needs
  // into the single canonical create-agent surface.
  const goToFullCreateFlow = () => {
    setShowCreateModal(false)
    router.push('/agents?create=1')
  }

  return (
    <div className="flex items-center gap-3">
      <AgentAvatarIcon slug={selectedAgent?.avatar} size="sm" />
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
        footer={<div className="flex justify-between items-center gap-3 w-full">
          <button
            type="button"
            onClick={goToFullCreateFlow}
            className="text-xs text-teal-400 hover:text-teal-300 transition-colors"
            title="Open the full Agent Studio create flow (persona, tone, keywords)"
          >
            Need persona / tone / keywords? Open full create flow →
          </button>
          <div className="flex items-center gap-3">
            <button onClick={() => setShowCreateModal(false)} className="px-4 py-2 text-sm text-tsushin-slate hover:text-white transition-colors">Cancel</button>
            <button onClick={handleCreate} disabled={creating} className="px-4 py-2 text-sm bg-tsushin-indigo text-white rounded-lg hover:bg-tsushin-indigo/90 disabled:opacity-50 transition-all">{creating ? 'Creating...' : (newAgentKind === 'text' ? 'Create Agent' : 'Continue in Audio Wizard →')}</button>
          </div>
        </div>}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-2">Agent Type</label>
            <div className="grid grid-cols-3 gap-2">
              {(['text', 'voice', 'hybrid'] as NewAgentKind[]).map(kind => (
                <button
                  key={kind}
                  type="button"
                  onClick={() => setNewAgentKind(kind)}
                  className={`px-3 py-2 rounded-lg border text-xs transition-colors ${
                    newAgentKind === kind
                      ? 'border-teal-400 bg-teal-500/10 text-white'
                      : 'border-tsushin-border bg-tsushin-deep text-tsushin-slate hover:border-white/20'
                  }`}
                >
                  <div className="font-medium capitalize">{kind}</div>
                  <div className="text-[10px] opacity-70 mt-0.5">
                    {kind === 'text' && 'Chat only'}
                    {kind === 'voice' && 'TTS replies'}
                    {kind === 'hybrid' && 'Transcribe + TTS'}
                  </div>
                </button>
              ))}
            </div>
            {(newAgentKind === 'voice' || newAgentKind === 'hybrid') && (
              <p className="text-[11px] text-tsushin-slate mt-2">
                Audio setup continues in the Audio Agents wizard after you click Continue.
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-1">Agent Name</label>
            <input type="text" value={newAgentName} onChange={(e) => setNewAgentName(e.target.value)} placeholder="e.g., Customer Support Bot"
              className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo" autoFocus />
          </div>
          {/* v0.7.0-fix Phase 6b: wake mode picker so users can declare
              Continuous at agent-creation time instead of discovering it
              later under Watcher → Continuous Agents. */}
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-2">Wake mode</label>
            <div className="grid grid-cols-2 gap-2">
              {(['conversational', 'continuous'] as WakeMode[]).map(mode => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setNewWakeMode(mode)}
                  className={`px-3 py-2 rounded-lg border text-left transition-colors ${
                    newWakeMode === mode
                      ? 'border-teal-400 bg-teal-500/10 text-white'
                      : 'border-tsushin-border bg-tsushin-deep text-tsushin-slate hover:border-white/20'
                  }`}
                >
                  <div className="text-sm font-medium capitalize">{mode}</div>
                  <div className="text-[10px] opacity-70 mt-0.5">
                    {mode === 'conversational' && 'Replies to direct chat (default).'}
                    {mode === 'continuous' && 'Always-on; wakes on triggers (email, Jira, GitHub, webhook).'}
                  </div>
                </button>
              ))}
            </div>
            {newWakeMode === 'continuous' && (
              <p className="text-[11px] text-tsushin-slate mt-2">
                After save, the Continuous Agent setup modal opens to define purpose + action kind.
              </p>
            )}
          </div>
          {newAgentKind === 'text' && (
          <div>
            <label className="block text-sm font-medium text-tsushin-slate mb-1">Provider</label>
            {configuredVendors.length === 0 ? (
              <div className="px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-xs text-tsushin-slate">
                No providers configured.{' '}
                <a href="/hub" className="text-teal-400 hover:underline">Set one up in Hub &gt; AI Providers</a>
              </div>
            ) : (
              <select value={newAgentVendor} onChange={(e) => handleVendorChange(e.target.value)}
                className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo">
                {configuredVendors.map(v => (
                  <option key={v.value} value={v.value}>{v.label}</option>
                ))}
              </select>
            )}
          </div>
          )}
          {newAgentKind === 'text' && vendorInstances.length > 1 && (
            <div>
              <label className="block text-sm font-medium text-tsushin-slate mb-1">Instance</label>
              <select value={newAgentInstanceId ?? ''} onChange={(e) => {
                const id = e.target.value ? parseInt(e.target.value) : null
                setNewAgentInstanceId(id)
                if (id) {
                  const inst = vendorInstances.find(i => i.id === id)
                  if (inst && inst.available_models.length > 0) setNewAgentModel(inst.available_models[0])
                }
              }} className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo">
                {vendorInstances.map(inst => (
                  <option key={inst.id} value={inst.id}>{inst.instance_name}{inst.is_default ? ' (default)' : ''}</option>
                ))}
              </select>
            </div>
          )}
          {newAgentKind === 'text' && newAgentVendor && (
            <div>
              <label className="block text-sm font-medium text-tsushin-slate mb-1">Model</label>
              {(() => {
                const inst = vendorInstances.find(i => i.id === newAgentInstanceId) || vendorInstances[0]
                const models = inst?.available_models || []
                return models.length > 0 ? (
                  <select value={newAgentModel} onChange={(e) => setNewAgentModel(e.target.value)}
                    className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo">
                    {models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input type="text" value={newAgentModel} onChange={(e) => setNewAgentModel(e.target.value)}
                    placeholder="e.g., gemini-2.5-flash" className="w-full px-3 py-2 bg-tsushin-deep border border-tsushin-border rounded-lg text-white text-sm focus:outline-none focus:border-tsushin-indigo" />
                )
              })()}
            </div>
          )}
          {createError && <p className="text-sm text-red-400">{createError}</p>}
        </div>
      </Modal>
    </div>
  )
}
