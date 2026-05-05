'use client'

/**
 * Studio - Agents Page
 * Agent list with sub-navigation to Contacts and Personas
 */

import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'next/navigation'
import { useAuth } from '@/contexts/AuthContext'
import { useGlobalRefresh } from '@/hooks/useGlobalRefresh'
import Link from 'next/link'
import StudioTabs from '@/components/studio/StudioTabs'
import { api, Agent, TonePreset, Contact, Persona, ProviderInstance, VENDOR_LABELS } from '@/lib/client'
import { useToast } from '@/contexts/ToastContext'
import { useAgentWizard, useAgentWizardComplete } from '@/contexts/AgentWizardContext'
import InfoTooltip from '@/components/ui/InfoTooltip'
import EmptyState from '@/components/EmptyState'
import {
  SettingsIcon,
  StarIcon,
  CheckCircleIcon,
  LightningIcon,
  KeyIcon,
  LightbulbIcon,
} from '@/components/ui/icons'

interface AgentFormData {
  contact_id: number
  agent_name: string
  agent_phone: string
  system_prompt: string
  persona_id: number | null
  tone_preset_id: number | null
  custom_tone: string
  keywords: string[]
  // enabled_tools removed - use Skills system instead
  model_provider: string
  model_name: string
  is_active: boolean
}

// AVAILABLE_TOOLS removed - legacy tools migrated to Skills system
// Use AgentSkill table for web_search, web_scraping skills

export default function AgentsPage() {
  const toast = useToast()
  // BUG-610 FIX: Read-only members (no agents.write) were seeing and
  // clicking create / delete / toggle buttons. The backend rejected those
  // with 403 but the buttons still rendered — confusing UX and a noisy
  // signal in audit logs. Gate every mutation control on ``canWriteAgents``.
  const { hasPermission } = useAuth()
  const canWriteAgents = hasPermission('agents.write')
  const canReadDefaultAgents = hasPermission('org.settings.read')
  const searchParams = useSearchParams()
  const [agents, setAgents] = useState<Agent[]>([])
  const [tones, setTones] = useState<TonePreset[]>([])
  const [personas, setPersonas] = useState<Persona[]>([])
  const [contacts, setContacts] = useState<Contact[]>([])
  const [agentSkillsCounts, setAgentSkillsCounts] = useState<Record<number, number>>({})
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [ollamaAvailable, setOllamaAvailable] = useState<boolean>(false)
  const [ollamaModels, setOllamaModels] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [expandedAgent, setExpandedAgent] = useState<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [createError, setCreateError] = useState<string>('')
  const [editingAgentId, setEditingAgentId] = useState<number | null>(null)
  const [editingAgentName, setEditingAgentName] = useState('')

  const [formData, setFormData] = useState<AgentFormData>({
    contact_id: 0,
    agent_name: "",
    agent_phone: "",
    system_prompt: '',
    persona_id: null,
    tone_preset_id: null,
    custom_tone: '',
    keywords: [],
    // enabled_tools removed - use Skills system
    // BUG-346: These are overridden by getSmartDefaults() in resetForm() and useEffect
    model_provider: '',
    model_name: '',
    is_active: true,
  })
  const [keywordInput, setKeywordInput] = useState('')
  const [useCustomTone, setUseCustomTone] = useState(false)
  const [useCustomModel, setUseCustomModel] = useState(false)
  const [customModelName, setCustomModelName] = useState('')
  const [showGuidedPrefillBanner, setShowGuidedPrefillBanner] = useState(false)

  // Agent Wizard (Guided mode) — the Create button dispatches here by default.
  const agentWizard = useAgentWizard()
  useAgentWizardComplete(() => loadData())

  const openCreateUI = () => {
    if (!canWriteAgents) return
    const mode = agentWizard.getMode()
    if (mode === 'advanced') {
      setShowCreateModal(true)
    } else {
      agentWizard.openWizard()
    }
  }

  // Legacy modal pre-fill from a persisted Guided draft (set when the user
  // switched from Guided → Advanced mid-wizard). Reads from localStorage
  // directly so the callback works even when captured as a stale closure.
  const applyPersistedDraft = () => {
    let draft: any = null
    try {
      const raw = typeof window !== 'undefined' ? window.localStorage.getItem('tsushin:agentWizardDraft') : null
      if (raw) draft = JSON.parse(raw)
    } catch { /* ignore */ }
    if (!draft) return false
    const patch: Partial<AgentFormData> = {}
    if (draft.basics?.agent_name) patch.agent_name = draft.basics.agent_name
    if (draft.basics?.agent_phone) patch.agent_phone = draft.basics.agent_phone
    if (draft.basics?.model_provider) patch.model_provider = draft.basics.model_provider
    if (draft.basics?.model_name) patch.model_name = draft.basics.model_name
    if (draft.personality?.system_prompt) patch.system_prompt = draft.personality.system_prompt
    if (draft.personality?.persona_id) patch.persona_id = draft.personality.persona_id
    if (draft.personality?.tone_preset_id) patch.tone_preset_id = draft.personality.tone_preset_id
    if (draft.personality?.custom_tone) {
      patch.custom_tone = draft.personality.custom_tone
      setUseCustomTone(true)
    }
    if (Object.keys(patch).length > 0) {
      setFormData(prev => ({ ...prev, ...patch }))
      setShowGuidedPrefillBanner(true)
      return true
    }
    return false
  }

  // Listen for the wizard's "switch to advanced" event. Uses a ref so the
  // closure always calls the latest applyPersistedDraft.
  const applyPersistedDraftRef = useRef(applyPersistedDraft)
  applyPersistedDraftRef.current = applyPersistedDraft
  useEffect(() => {
    const onOpenAdvanced = () => {
      setShowCreateModal(true)
      // Defer so showCreateModal commit completes before applying draft.
      setTimeout(() => applyPersistedDraftRef.current(), 0)
    }
    window.addEventListener('tsushin:open-agent-advanced-modal', onOpenAdvanced)
    return () => window.removeEventListener('tsushin:open-agent-advanced-modal', onOpenAdvanced)
  }, [])

  // Load configured provider instances for smart defaults
  useEffect(() => {
    api.getProviderInstances().then(instances => {
      setProviderInstances(instances)
    }).catch(() => {})
  }, [])

  // BUG-346: Apply smart defaults once provider instances are loaded (useRef avoids stale closure)
  const defaultsAppliedRef = useRef(false)
  useEffect(() => {
    if (providerInstances.length > 0 && !defaultsAppliedRef.current) {
      defaultsAppliedRef.current = true
      const defaultInstance = providerInstances.find(p => p.is_default) || providerInstances[0]
      const vendor = defaultInstance.vendor?.toLowerCase() || ''
      const model = defaultInstance.available_models?.[0] || ''
      if (vendor) {
        setFormData(prev => ({ ...prev, model_provider: vendor, model_name: model }))
      }
    }
  }, [providerInstances])

  useEffect(() => {
    loadData()
    checkOllamaHealth()
  }, [])

  // BUG-602 FIX: ``?create=1`` query param opens the create-agent
  // modal. The Studio quick-create dialog routes here when the user
  // asks for "the full flow" so both paths converge on this single
  // canonical modal — no more parallel create implementations.
  useEffect(() => {
    if (!canWriteAgents) return
    const shouldOpen = searchParams?.get('create') === '1'
    if (shouldOpen) {
      openCreateUI()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, canWriteAgents])

  useEffect(() => {
    if (formData.model_provider === 'ollama') {
      checkOllamaHealth()
    }
  }, [formData.model_provider])

  useGlobalRefresh(() => { loadData(); checkOllamaHealth() })

  // Vendors list derived live from configured hub instances — automatically includes any new provider
  const availableVendors = [...new Set(providerInstances.map(i => i.vendor))]
    .map(v => ({ value: v, label: VENDOR_LABELS[v] || v }))

  // BUG-346: Use the tenant's default provider instance (is_default=true) instead of [0]
  const getSmartDefaults = () => {
    if (providerInstances.length > 0) {
      const defaultInstance = providerInstances.find(p => p.is_default) || providerInstances[0]
      const vendor = defaultInstance.vendor?.toLowerCase() || ''
      if (vendor === 'ollama') {
        return { model_provider: 'ollama', model_name: ollamaModels[0] || '' }
      }
      const instanceModel = defaultInstance.available_models?.[0]
      if (instanceModel) {
        return { model_provider: vendor, model_name: instanceModel }
      }
    }
    return { model_provider: '', model_name: '' }
  }

  const resetForm = () => {
    const defaults = getSmartDefaults()
    setFormData({
      contact_id: 0,
      agent_name: '',
      agent_phone: '',
      system_prompt: '',
      persona_id: null,
      tone_preset_id: null,
      custom_tone: '',
      keywords: [],
      // enabled_tools removed - use Skills system
      model_provider: defaults.model_provider,
      model_name: defaults.model_name,
      is_active: true,
    })
    setKeywordInput('')
    setUseCustomTone(false)
    setUseCustomModel(false)
    setCustomModelName('')
    setCreateError('')
  }

  const getAvailableModels = () => {
    if (formData.model_provider === 'ollama') {
      return ollamaModels
    }
    // Get all models from all instances of the selected vendor (deduplicated)
    const vendorModels = [
      ...new Set(
        providerInstances
          .filter(i => i.vendor === formData.model_provider)
          .flatMap(i => i.available_models)
      )
    ]
    if (vendorModels.length > 0) return vendorModels
    return formData.model_name ? [formData.model_name] : []
  }

  const loadData = async () => {
    try {
      const [agentsData, tonesData, personasData, contactsRes] = await Promise.all([
        api.getAgents(),
        api.getTonePresets(),
        api.getPersonas(true),
        api.getContacts().then(contacts => contacts.filter(c => c.role === 'agent')),
      ])
      setAgents(agentsData)
      setTones(tonesData)
      setPersonas(personasData)
      setContacts(contactsRes)

      const skillsCounts: Record<number, number> = {}
      agentsData.forEach(agent => {
        skillsCounts[agent.id] = agent.skills_count || 0
      })
      setAgentSkillsCounts(skillsCounts)
    } catch (err) {
      console.error('Failed to load data:', err)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteAgent = async (id: number) => {
    if (!confirm('Are you sure you want to delete this agent?')) return
    try {
      await api.deleteAgent(id)
      await loadData()
    } catch (err: any) {
      toast.error('Delete Failed', err.message || 'Failed to delete agent')
    }
  }

  const handleToggleActive = async (agent: Agent) => {
    try {
      await api.updateAgent(agent.id, { is_active: !agent.is_active })
      await loadData()
    } catch (err: any) {
      toast.error('Update Failed', err.message || 'Failed to update agent')
    }
  }

  const handleStartRename = (agent: Agent) => {
    setEditingAgentId(agent.id)
    setEditingAgentName(agent.contact_name)
  }

  const handleCancelRename = () => {
    setEditingAgentId(null)
    setEditingAgentName('')
  }

  const handleSaveRename = async (agent: Agent) => {
    if (!editingAgentName.trim()) {
      toast.warning('Validation', 'Agent name cannot be empty')
      return
    }
    try {
      // Update the contact name
      await api.updateContact(agent.contact_id, {
        friendly_name: editingAgentName.trim()
      })
      setEditingAgentId(null)
      setEditingAgentName('')
      await loadData()
    } catch (err: any) {
      toast.error('Rename Failed', err.message || 'Failed to rename agent')
    }
  }

  const handleAddKeyword = () => {
    if (keywordInput.trim() && !formData.keywords.includes(keywordInput.trim())) {
      setFormData({ ...formData, keywords: [...formData.keywords, keywordInput.trim()] })
      setKeywordInput('')
    }
  }

  const handleRemoveKeyword = (keyword: string) => {
    setFormData({ ...formData, keywords: formData.keywords.filter(k => k !== keyword) })
  }

  // handleToggleTool removed - legacy tools migrated to Skills system

  const checkOllamaHealth = async () => {
    try {
      const data = await api.getOllamaHealth()
      setOllamaAvailable(data.available === true)
      if (data.available && data.models) {
        const modelNames = data.models.map((m) => m.name)
        setOllamaModels(modelNames)
      } else {
        setOllamaModels([])
      }
    } catch (error) {
      setOllamaAvailable(false)
      setOllamaModels([])
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!formData.agent_name) {
      toast.warning('Validation', 'Please provide agent name')
      return
    }

    if (formData.model_provider === 'ollama' && !ollamaAvailable) {
      toast.warning('Ollama Unavailable', 'Ollama service is not running. Please start Ollama or choose a different provider.')
      return
    }

    if (formData.agent_phone && formData.agent_phone.trim()) {
      const phoneRegex = /^\+?\d{10,15}$/
      if (!phoneRegex.test(formData.agent_phone.replace(/\s/g, ''))) {
        toast.warning('Validation', 'Invalid phone number format. Please use 10-15 digits.')
        return
      }
    }

    setSaving(true)
    setCreateError('')
    try {
      let contactId = formData.contact_id
      const existingContact = contacts.find(c => c.friendly_name.toLowerCase() === formData.agent_name.toLowerCase())

      if (existingContact) {
        contactId = existingContact.id
      } else {
        const newContact = await api.createContact({
          friendly_name: formData.agent_name,
          phone_number: formData.agent_phone?.trim() ? formData.agent_phone.replace(/\s/g, '') : undefined,
          role: 'agent',
          is_active: true,
          notes: 'Auto-created agent contact'
        })
        contactId = newContact.id
      }

      const payload: any = {
        contact_id: contactId,
        system_prompt: formData.system_prompt,
        persona_id: formData.persona_id,
        keywords: formData.keywords,
        // enabled_tools removed - use Skills system for web_search, etc.
        model_provider: formData.model_provider,
        model_name: formData.model_name,
        is_active: formData.is_active,
      }

      if (useCustomTone) {
        payload.custom_tone = formData.custom_tone
        payload.tone_preset_id = null
      } else {
        payload.tone_preset_id = formData.tone_preset_id
        payload.custom_tone = null
      }

      await api.createAgent(payload)
      setShowCreateModal(false)
      setShowGuidedPrefillBanner(false)
      agentWizard.clearPersistedDraft()
      setCreateError('')
      resetForm()
      await loadData()
    } catch (err: any) {
      const errMsg = err.message || 'Failed to create agent'
      setCreateError(errMsg)
      toast.error('Creation Failed', errMsg)
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="relative w-16 h-16 mx-auto mb-4">
            <div className="absolute inset-0 rounded-full border-4 border-tsushin-surface"></div>
            <div className="absolute inset-0 rounded-full border-4 border-transparent border-t-tsushin-indigo animate-spin"></div>
          </div>
          <p className="text-tsushin-slate font-medium">Loading agents...</p>
        </div>
      </div>
    )
  }

  const activeAgents = agents.filter(a => a.is_active)
  const defaultAgent = agents.find(a => a.is_default)

  return (
    <div className="min-h-screen animate-fade-in">
      {/* Header */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-8 flex justify-between items-center">
          <div>
            <h1 className="text-3xl font-display font-bold text-white mb-2">Agent Studio</h1>
            <p className="text-tsushin-slate">Configure AI agents with different personalities and capabilities</p>
          </div>
          {canWriteAgents && (
            <button
              onClick={openCreateUI}
              className="btn-primary flex items-center gap-2"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Create Agent
            </button>
          )}
        </div>
      </div>

      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-0 space-y-6">
        {/* Sub Navigation */}
        <StudioTabs />

        {/* Stats with enhanced cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 animate-stagger">
          <div className="stat-card stat-card-indigo group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Total Agents</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{agents.length}</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-teal-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
            </div>
          </div>
          <div className="stat-card stat-card-success group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Active Agents</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{activeAgents.length}</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-tsushin-success/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-tsushin-success" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              </div>
            </div>
          </div>
          <div className="stat-card stat-card-accent group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Personas</p>
                <p className="text-3xl font-display font-bold text-white mt-1">{personas.length}</p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-purple-500/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15.182 15.182a4.5 4.5 0 01-6.364 0M21 12a9 9 0 11-18 0 9 9 0 0118 0zM9.75 9.75c0 .414-.168.75-.375.75S9 10.164 9 9.75 9.168 9 9.375 9s.375.336.375.75zm-.375 0h.008v.015h-.008V9.75zm5.625 0c0 .414-.168.75-.375.75s-.375-.336-.375-.75.168-.75.375-.75.375.336.375.75zm-.375 0h.008v.015h-.008V9.75z" />
                </svg>
              </div>
            </div>
          </div>
          <div className="stat-card stat-card-warning group">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-tsushin-slate">Default Agent</p>
                <p className="text-lg font-semibold text-white mt-1 truncate">
                  {defaultAgent?.contact_name || 'None'}
                </p>
              </div>
              <div className="w-12 h-12 rounded-xl bg-tsushin-warning/10 flex items-center justify-center group-hover:scale-110 transition-transform">
                <svg className="w-6 h-6 text-tsushin-warning" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
                </svg>
              </div>
            </div>
          </div>
        </div>

        <div className="glass-card rounded-xl border border-tsushin-warning/20 bg-tsushin-warning/5 p-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-sm font-semibold text-white">Default routing now lives in Settings</h2>
              <p className="mt-1 text-sm text-tsushin-slate">
                Agent Studio still shows which agent is the tenant default, but changes now happen from the dedicated Default Agents settings page.
              </p>
            </div>
            {canReadDefaultAgents ? (
              <Link
                href="/settings/default-agents"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-tsushin-warning/30 bg-tsushin-warning/10 px-4 py-2 text-sm font-medium text-tsushin-warning hover:bg-tsushin-warning/20 transition-colors"
              >
                Manage Default Agents
                <span aria-hidden="true">→</span>
              </Link>
            ) : (
              <p className="text-sm text-tsushin-slate md:text-right">
                Ask an organization admin with settings access to update default routing.
              </p>
            )}
          </div>
        </div>

        {/* Agents List */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-tsushin-border/50 flex items-center justify-between">
            <h2 className="text-lg font-display font-semibold text-white">Configured Agents</h2>
            <span className="badge badge-indigo">{agents.length} agents</span>
          </div>

          {agents.length === 0 ? (
            <EmptyState
              variant="no-agents"
              actionLabel={canWriteAgents ? 'Create Your First Agent' : undefined}
              onAction={canWriteAgents ? openCreateUI : undefined}
            />
          ) : (
            <div className="divide-y divide-tsushin-border/30">
              {agents.map((agent, index) => (
                <div
                  key={agent.id}
                  className="px-6 py-5 hover:bg-tsushin-surface/30 transition-colors"
                  style={{ animationDelay: `${index * 50}ms` }}
                >
                  <div className="flex items-start justify-between">
                    <div className="flex-1">
                      <div className="flex items-center gap-3">
                        {/* Agent Avatar */}
                        <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500 to-cyan-400 text-white font-bold text-lg flex-shrink-0">
                          {agent.contact_name?.charAt(0).toUpperCase() || '?'}
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            {editingAgentId === agent.id ? (
                              <>
                                <input
                                  type="text"
                                  value={editingAgentName}
                                  onChange={(e) => setEditingAgentName(e.target.value)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleSaveRename(agent)
                                    if (e.key === 'Escape') handleCancelRename()
                                  }}
                                  className="input py-1 px-2 text-lg font-semibold"
                                  autoFocus
                                />
                                <button
                                  onClick={() => handleSaveRename(agent)}
                                  className="p-1.5 rounded-lg bg-tsushin-success/20 text-tsushin-success hover:bg-tsushin-success/30 transition-colors"
                                  title="Save"
                                >
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                                  </svg>
                                </button>
                                <button
                                  onClick={handleCancelRename}
                                  className="p-1.5 rounded-lg bg-tsushin-vermilion/20 text-tsushin-vermilion hover:bg-tsushin-vermilion/30 transition-colors"
                                  title="Cancel"
                                >
                                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                  </svg>
                                </button>
                              </>
                            ) : (
                              <>
                                <h3 className="text-lg font-semibold text-white">{agent.contact_name}</h3>
                                {canWriteAgents && (
                                  <button
                                    onClick={() => handleStartRename(agent)}
                                    className="p-1 rounded-lg bg-tsushin-indigo/20 text-tsushin-indigo hover:bg-tsushin-indigo/30 transition-colors"
                                    title="Rename agent"
                                  >
                                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                    </svg>
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                          <div className="flex gap-2 flex-wrap mt-1">
                            {agent.is_default && (
                              <span className="badge badge-warning flex items-center gap-1">
                                <StarIcon size={12} /> Default
                              </span>
                            )}
                            {agent.is_active ? (
                              <span className="badge badge-success flex items-center gap-1">
                                <CheckCircleIcon size={12} /> Active
                              </span>
                            ) : (
                              <span className="badge badge-neutral">
                                ○ Inactive
                              </span>
                            )}
                            {(agentSkillsCounts[agent.id] || 0) > 0 && (
                              <span className="badge badge-indigo flex items-center gap-1">
                                <LightningIcon size={12} /> {agentSkillsCounts[agent.id]} skills
                              </span>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm text-tsushin-slate">
                        <span className="flex items-center gap-1.5">
                          {agent.tone_preset_name || 'Custom'}
                        </span>
                        <span className="flex items-center gap-1.5">
                          {agent.model_name}
                        </span>
                        <span className="flex items-center gap-1.5">
                          <LightningIcon size={14} className="opacity-70" /> {agentSkillsCounts[agent.id] || 0} skills
                        </span>
                        <span className="flex items-center gap-1.5">
                          {agent.keywords.length || 0} keywords
                        </span>
                        <span className="flex items-center gap-1.5">Text</span>
                      </div>
                    </div>

                    <div className="flex gap-2 ml-4 flex-shrink-0">
                      <Link
                        href={`/agents/${agent.id}`}
                        className="btn-primary py-1.5 px-3 text-sm flex items-center gap-1.5"
                      >
                        <SettingsIcon size={14} /> Manage
                      </Link>
                      <button
                        onClick={() => setExpandedAgent(expandedAgent === agent.id ? null : agent.id)}
                        className="btn-ghost py-1.5 px-3 text-sm"
                      >
                        {expandedAgent === agent.id ? '▲ Hide' : '▼ Details'}
                      </button>
                      {canWriteAgents && (
                        <>
                          <button
                            onClick={() => handleToggleActive(agent)}
                            className={`py-1.5 px-3 text-sm rounded-lg font-medium transition-all ${
                              agent.is_active
                                ? 'bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20'
                                : 'bg-tsushin-success/10 text-tsushin-success border border-tsushin-success/30 hover:bg-tsushin-success/20'
                            }`}
                          >
                            {agent.is_active ? 'Deactivate' : 'Activate'}
                          </button>
                          <button
                            onClick={() => handleDeleteAgent(agent.id)}
                            className="py-1.5 px-3 text-sm rounded-lg font-medium bg-tsushin-vermilion/10 text-tsushin-vermilion border border-tsushin-vermilion/30 hover:bg-tsushin-vermilion/20 transition-all"
                          >
                            Delete
                          </button>
                        </>
                      )}
                    </div>
                  </div>

                  {expandedAgent === agent.id && (
                    <div className="mt-4 pt-4 border-t border-tsushin-border/30 space-y-4 animate-fade-in-up">
                      <div>
                        <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                          <span className="w-5 h-5 rounded bg-teal-500/20 flex items-center justify-center">
                            <svg className="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                            </svg>
                          </span>
                          System Prompt
                        </h4>
                        <div className="bg-tsushin-deep rounded-xl p-4 text-sm text-gray-300 whitespace-pre-wrap border border-tsushin-border font-mono">
                          {agent.system_prompt}
                        </div>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded bg-purple-500/20 flex items-center justify-center">
                              <svg className="w-3 h-3 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                              </svg>
                            </span>
                            Tone Configuration
                          </h4>
                          <div className="bg-purple-500/5 rounded-xl p-4 border border-purple-500/20">
                            {agent.tone_preset_name ? (
                              <>
                                <p className="text-sm font-medium text-purple-300">{agent.tone_preset_name}</p>
                                <p className="text-xs text-purple-400/80 mt-1">
                                  {tones.find(t => t.id === agent.tone_preset_id)?.description}
                                </p>
                              </>
                            ) : (
                              <>
                                <p className="text-sm font-medium text-purple-300">Custom Tone</p>
                                <p className="text-xs text-purple-400/80 mt-1">{agent.custom_tone || 'No custom tone specified'}</p>
                              </>
                            )}
                          </div>
                        </div>

                        <div>
                          <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                            <span className="w-5 h-5 rounded bg-teal-500/20 flex items-center justify-center">
                              <svg className="w-3 h-3 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                              </svg>
                            </span>
                            AI Model
                          </h4>
                          <div className="bg-tsushin-indigo/5 rounded-xl p-4 border border-tsushin-indigo/20">
                            <p className="text-sm font-medium text-tsushin-indigo-glow">{agent.model_provider}</p>
                            <p className="text-xs text-tsushin-indigo/80 mt-1 font-mono">{agent.model_name}</p>
                          </div>
                        </div>
                      </div>

                      <div>
                        <h4 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
                          <span className="w-5 h-5 rounded bg-tsushin-success/20 flex items-center justify-center">
                            <KeyIcon size={12} className="text-tsushin-success" />
                          </span>
                          Trigger Keywords
                        </h4>
                        <div className="bg-tsushin-success/5 rounded-xl p-4 border border-tsushin-success/20">
                          {agent.keywords.length > 0 ? (
                            <div className="flex flex-wrap gap-2">
                              {agent.keywords.map((kw, i) => (
                                <span key={i} className="badge badge-success">
                                  {kw}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <p className="text-xs text-tsushin-muted">No keywords configured</p>
                          )}
                        </div>
                      </div>
                      {/* Enabled Tools section removed - use Skills panel instead */}

                      <div className="text-xs text-tsushin-muted pt-3 border-t border-tsushin-border/30 flex items-center gap-4">
                        <span className="flex items-center gap-1.5">
                          ID: {agent.contact_id}
                        </span>
                        <span className="flex items-center gap-1.5">
                          {new Date(agent.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Create Modal */}
      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="glass-card-elevated rounded-2xl p-6 max-w-4xl w-full max-h-[90vh] overflow-y-auto animate-scale-in">
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-xl font-display font-bold text-white">Create New Agent</h2>
                <p className="text-sm text-tsushin-slate mt-1">Advanced mode — all fields in one form</p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    agentWizard.setMode('guided')
                    setShowCreateModal(false)
                    setShowGuidedPrefillBanner(false)
                    resetForm()
                    agentWizard.openWizard()
                  }}
                  className="px-3 py-1.5 text-xs text-gray-400 hover:text-teal-300 transition-colors underline decoration-dotted"
                >
                  Switch to Guided
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCreateModal(false); resetForm(); setShowGuidedPrefillBanner(false); agentWizard.clearPersistedDraft() }}
                  className="btn-icon"
                >
                  <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            </div>

            {showGuidedPrefillBanner && (
              <div className="mb-4 p-3 rounded-xl border border-teal-400/30 bg-teal-500/10 text-sm text-teal-100 flex items-center justify-between">
                <span>Continuing from the guided wizard — fields below are pre-filled.</span>
                <button
                  type="button"
                  onClick={() => setShowGuidedPrefillBanner(false)}
                  className="text-teal-200 hover:text-white text-xs underline"
                >
                  Dismiss
                </button>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label className="block text-sm font-medium text-white mb-2">Agent Name *</label>
                <input
                  type="text"
                  value={formData.agent_name}
                  onChange={(e) => setFormData({ ...formData, agent_name: e.target.value })}
                  className="input"
                  placeholder="e.g., Assistant, Support, Sales"
                  required
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Phone Number (Optional)</label>
                <input
                  type="text"
                  value={formData.agent_phone}
                  onChange={(e) => setFormData({ ...formData, agent_phone: e.target.value })}
                  className="input"
                  placeholder="e.g., 5527999888777"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">System Prompt *</label>
                <div className="flex flex-wrap gap-2 mb-2">
                  {[
                    { label: 'General Assistant', prompt: 'You are a helpful, friendly AI assistant. You provide clear, concise answers and help users with their questions.' },
                    { label: 'Customer Support', prompt: 'You are a customer support agent. You help users resolve issues, answer questions about products and services, and escalate complex problems when needed. Always be empathetic and solution-oriented.' },
                    { label: 'Sales Outreach', prompt: 'You are a sales assistant. You engage potential customers, answer product questions, highlight key features, and guide them toward making informed decisions. Be friendly and professional.' },
                    { label: 'Technical Support', prompt: 'You are a technical support specialist. You troubleshoot issues, provide step-by-step solutions, and explain technical concepts in simple terms. Ask clarifying questions when needed.' },
                  ].map((tpl) => (
                    <button
                      key={tpl.label}
                      type="button"
                      onClick={() => setFormData({ ...formData, system_prompt: tpl.prompt })}
                      className="bg-tsushin-deep border border-tsushin-border text-xs px-3 py-1 rounded-full text-tsushin-slate hover:text-white hover:border-teal-500/50 transition-colors"
                    >
                      {tpl.label}
                    </button>
                  ))}
                </div>
                <textarea
                  value={formData.system_prompt}
                  onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value })}
                  className="input h-32 font-mono text-sm resize-none"
                  required
                  placeholder="Define the agent's role, personality, and behavior..."
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Persona (Optional)</label>
                <select
                  value={formData.persona_id || ''}
                  onChange={(e) => setFormData({ ...formData, persona_id: Number(e.target.value) || null })}
                  className="select"
                >
                  <option value="">No persona</option>
                  {personas.map((persona) => (
                    <option key={persona.id} value={persona.id}>
                      {persona.name} — {persona.role || 'No role'}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Tone Configuration</label>
                <div className="space-y-3">
                  <div className="flex items-center gap-4">
                    <label className="flex items-center text-tsushin-slate hover:text-white cursor-pointer transition-colors">
                      <input
                        type="radio"
                        checked={!useCustomTone}
                        onChange={() => setUseCustomTone(false)}
                        className="mr-2 accent-tsushin-indigo"
                      />
                      Use Tone Preset
                    </label>
                    <label className="flex items-center text-tsushin-slate hover:text-white cursor-pointer transition-colors">
                      <input
                        type="radio"
                        checked={useCustomTone}
                        onChange={() => setUseCustomTone(true)}
                        className="mr-2 accent-tsushin-indigo"
                      />
                      Custom Tone
                    </label>
                  </div>

                  {!useCustomTone ? (
                    <select
                      value={formData.tone_preset_id || ''}
                      onChange={(e) => setFormData({ ...formData, tone_preset_id: Number(e.target.value) || null })}
                      className="select"
                    >
                      <option value="">Select a tone preset...</option>
                      {tones.map(t => (
                        <option key={t.id} value={t.id}>{t.name}</option>
                      ))}
                    </select>
                  ) : (
                    <textarea
                      value={formData.custom_tone}
                      onChange={(e) => setFormData({ ...formData, custom_tone: e.target.value })}
                      className="input h-20 resize-none"
                      placeholder="Describe custom tone..."
                    />
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-white mb-2">Trigger Keywords</label>
                <div className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={keywordInput}
                    onChange={(e) => setKeywordInput(e.target.value)}
                    onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddKeyword())}
                    className="input flex-1"
                    placeholder="Type keyword and press Enter"
                  />
                  <button
                    type="button"
                    onClick={handleAddKeyword}
                    className="px-4 py-2.5 bg-tsushin-success/20 text-tsushin-success border border-tsushin-success/30 rounded-lg hover:bg-tsushin-success/30 font-medium transition-colors"
                  >
                    Add
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {formData.keywords.map((kw, i) => (
                    <span key={i} className="badge badge-success flex items-center gap-2">
                      {kw}
                      <button type="button" onClick={() => handleRemoveKeyword(kw)} className="hover:text-white transition-colors">×</button>
                    </span>
                  ))}
                </div>
              </div>

              {/* Enabled Tools section removed - configure Skills in agent detail page */}
              <div className="bg-tsushin-surface/30 rounded-xl p-4 border border-tsushin-border/30">
                <p className="text-sm text-tsushin-slate flex items-start gap-2">
                  <LightbulbIcon size={16} className="text-teal-400 flex-shrink-0 mt-0.5" />
                  <span>
                    <span className="text-teal-400 font-medium">Skills Note:</span>{' '}
                    Configure Web Search and other capabilities as Skills after creating the agent.
                    Visit the agent&apos;s Manage page → Skills tab.
                  </span>
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-white mb-2 flex items-center gap-2">
                    Model Provider *
                    <InfoTooltip text="Choose a provider for which you have an API key configured in the Hub. If unsure, the default model works for most use cases." />
                  </label>
                  <select
                    value={formData.model_provider}
                    onChange={(e) => {
                      const newProvider = e.target.value
                      const vendorInsts = providerInstances.filter(i => i.vendor === newProvider)
                      const defaultInst = vendorInsts.find(i => i.is_default) || vendorInsts[0]
                      const defaultModel = newProvider === 'ollama'
                        ? (ollamaModels[0] || '')
                        : (defaultInst?.available_models[0] || '')
                      setFormData({
                        ...formData,
                        model_provider: newProvider,
                        model_name: defaultModel
                      })
                    }}
                    className="select"
                    required
                  >
                    {availableVendors.length === 0 ? (
                      <option value="" disabled>No providers configured — set one up in Hub &gt; AI Providers</option>
                    ) : (
                      availableVendors.map(p => (
                        <option key={p.value} value={p.value}>{p.label}</option>
                      ))
                    )}
                  </select>
                  {formData.model_provider === 'ollama' && !ollamaAvailable && (
                    <div className="mt-2 p-3 bg-tsushin-vermilion/10 border border-tsushin-vermilion/30 rounded-lg text-xs text-tsushin-vermilion">
                      Ollama offline. Start with: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono">ollama serve</code>
                    </div>
                  )}
                </div>
                <div>
                  <label className="block text-sm font-medium text-white mb-2">Model Name *</label>
                  {formData.model_provider === 'openrouter' ? (
                    <div className="space-y-2">
                      <div className="flex items-center gap-3">
                        <label className="flex items-center text-tsushin-slate hover:text-white cursor-pointer transition-colors">
                          <input
                            type="radio"
                            checked={!useCustomModel}
                            onChange={() => {
                              setUseCustomModel(false)
                              const firstModel = getAvailableModels()[0] || ''
                              setFormData({ ...formData, model_name: firstModel })
                            }}
                            className="mr-2 accent-tsushin-indigo"
                          />
                          <span className="text-xs">Select from list</span>
                        </label>
                        <label className="flex items-center text-tsushin-slate hover:text-white cursor-pointer transition-colors">
                          <input
                            type="radio"
                            checked={useCustomModel}
                            onChange={() => {
                              setUseCustomModel(true)
                              setFormData({ ...formData, model_name: customModelName })
                            }}
                            className="mr-2 accent-tsushin-indigo"
                          />
                          <span className="text-xs">Custom model</span>
                        </label>
                      </div>
                      {!useCustomModel ? (
                        <select
                          value={formData.model_name}
                          onChange={(e) => setFormData({ ...formData, model_name: e.target.value })}
                          className="select font-mono"
                          required
                        >
                          {getAvailableModels().map((model) => (
                            <option key={model} value={model}>
                              {model}
                            </option>
                          ))}
                        </select>
                      ) : (
                        <div className="space-y-2">
                          <input
                            type="text"
                            value={customModelName}
                            onChange={(e) => {
                              setCustomModelName(e.target.value)
                              setFormData({ ...formData, model_name: e.target.value })
                            }}
                            className="input font-mono"
                            placeholder="e.g., anthropic/claude-sonnet-4-6"
                            required
                          />
                          <p className="text-xs text-tsushin-slate">
                            Enter model ID in format: <code className="bg-tsushin-deep px-1.5 py-0.5 rounded font-mono">provider/model-name</code>
                          </p>
                        </div>
                      )}
                    </div>
                  ) : (
                    <select
                      value={formData.model_name}
                      onChange={(e) => setFormData({ ...formData, model_name: e.target.value })}
                      className="select font-mono"
                      required
                    >
                      {getAvailableModels().length === 0 && formData.model_provider === 'ollama' && (
                        <option value="" disabled>No models found — is Ollama running?</option>
                      )}
                      {getAvailableModels().map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              <div className="flex gap-6">
                <label className="flex items-center text-tsushin-slate hover:text-white cursor-pointer transition-colors">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    className="mr-2 accent-tsushin-success"
                  />
                  <span className="text-sm font-medium">Active</span>
                </label>
              </div>

              {createError && (
                <div className="flex items-start gap-3 p-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
                  <svg className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  </svg>
                  <span>{createError}</span>
                </div>
              )}

              <div className="flex justify-end gap-3 pt-6 border-t border-tsushin-border/30">
                <button
                  type="button"
                  onClick={() => { setShowCreateModal(false); setCreateError(''); resetForm() }}
                  className="btn-ghost"
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={saving}
                >
                  {saving ? (
                    <span className="flex items-center gap-2">
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Creating...
                    </span>
                  ) : 'Create Agent'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
