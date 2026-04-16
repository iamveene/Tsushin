'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, Agent, TonePreset, Persona, ProviderInstance, VectorStoreInstance, VENDOR_LABELS } from '@/lib/client'
import {
  InfoIcon, TargetIcon, TheaterIcon, BotIcon, KeyIcon, LightbulbIcon,
  SettingsIcon, ClipboardIcon, SparklesIcon, ScaleIcon, LinkIcon, DatabaseIcon
} from '@/components/ui/icons'

interface Props {
  agentId: number
}

export default function AgentConfigurationManager({ agentId }: Props) {
  const [agent, setAgent] = useState<Agent | null>(null)
  const [personas, setPersonas] = useState<Persona[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // Form state
  const [systemPrompt, setSystemPrompt] = useState('')
  const [personaId, setPersonaId] = useState<number | null>(null)
  const [selectedPersona, setSelectedPersona] = useState<Persona | null>(null)
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  // enabledTools removed - use Skills system for web_search, etc.
  const [modelProvider, setModelProvider] = useState('gemini')
  const [modelName, setModelName] = useState('gemini-2.5-pro')
  const [providerInstanceId, setProviderInstanceId] = useState<number | null>(null)
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])
  const [allInstances, setAllInstances] = useState<ProviderInstance[]>([])
  const [isActive, setIsActive] = useState(true)
  const [isDefault, setIsDefault] = useState(false)

  // Vector Store (per-agent override)
  const [vectorStoreInstanceId, setVectorStoreInstanceId] = useState<number | null>(null)
  const [vectorStoreMode, setVectorStoreMode] = useState('override')
  const [vectorStoreInstances, setVectorStoreInstances] = useState<VectorStoreInstance[]>([])
  const [defaultVectorStoreId, setDefaultVectorStoreId] = useState<number | null>(null)

  // Trigger configuration (per-agent)
  const [triggerDmEnabled, setTriggerDmEnabled] = useState<boolean | null>(null)
  const [triggerGroupFilters, setTriggerGroupFilters] = useState<string[]>([])
  const [triggerNumberFilters, setTriggerNumberFilters] = useState<string[]>([])

  // Input helpers for triggers
  const [groupFilterInput, setGroupFilterInput] = useState('')
  const [numberFilterInput, setNumberFilterInput] = useState('')
  const [ollamaModels, setOllamaModels] = useState<string[]>([])

  useEffect(() => {
    loadData()
    fetchOllamaModels()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [agentData, personasData, allInstancesData, vectorStoresData, defaultVsData] = await Promise.all([
        api.getAgent(agentId),
        api.getPersonas(true), // Only active personas
        api.getProviderInstances(),  // All configured provider instances (no vendor filter)
        api.getVectorStoreInstances().catch(() => []),
        api.getDefaultVectorStore().catch(() => ({ default_vector_store_instance_id: null, instance: null })),
      ])

      setAgent(agentData)
      setPersonas(personasData)

      // Populate form
      setSystemPrompt(agentData.system_prompt)
      setPersonaId(agentData.persona_id || null)

      // Find and set selected persona
      if (agentData.persona_id) {
        const persona = personasData.find(p => p.id === agentData.persona_id)
        setSelectedPersona(persona || null)
      }

      setKeywords(agentData.keywords || [])
      // enabledTools removed - use Skills system
      setModelProvider(agentData.model_provider)
      setModelName(agentData.model_name)
      setProviderInstanceId(agentData.provider_instance_id || null)
      setIsActive(agentData.is_active)
      setIsDefault(agentData.is_default)

      // Store all instances and filter for the agent's current vendor
      setAllInstances(allInstancesData)
      setProviderInstances(allInstancesData.filter(i => i.vendor === agentData.model_provider))

      // Vector store configuration
      setVectorStoreInstances(vectorStoresData)
      setDefaultVectorStoreId(defaultVsData.default_vector_store_instance_id)
      setVectorStoreInstanceId(agentData.vector_store_instance_id || null)
      setVectorStoreMode(agentData.vector_store_mode || 'override')

      // Trigger configuration
      setTriggerDmEnabled(agentData.trigger_dm_enabled ?? null)
      setTriggerGroupFilters(agentData.trigger_group_filters || [])
      setTriggerNumberFilters(agentData.trigger_number_filters || [])
    } catch (err) {
      console.error('Failed to load agent:', err)
      alert('Failed to load agent configuration')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!systemPrompt.trim()) {
      alert('System prompt is required')
      return
    }

    // Note: persona_id is optional, not required

    setSaving(true)
    try {
      const payload: any = {
        system_prompt: systemPrompt,
        persona_id: personaId,
        keywords,
        // enabled_tools removed - use Skills system for web_search, etc.
        model_provider: modelProvider,
        model_name: modelName,
        provider_instance_id: providerInstanceId,
        is_active: isActive,
        is_default: isDefault,

        // Vector store (per-agent override)
        vector_store_instance_id: vectorStoreInstanceId,
        vector_store_mode: vectorStoreInstanceId ? vectorStoreMode : null,

        // Trigger configuration (per-agent)
        trigger_dm_enabled: triggerDmEnabled,
        trigger_group_filters: triggerGroupFilters.length > 0 ? triggerGroupFilters : null,
        trigger_number_filters: triggerNumberFilters.length > 0 ? triggerNumberFilters : null,
      }

      await api.updateAgent(agentId, payload)

      alert('Configuration saved successfully!')
      await loadData()
    } catch (err: any) {
      console.error('Failed to save:', err)
      alert(err.message || 'Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const addKeyword = () => {
    const keyword = keywordInput.trim()
    if (keyword && !keywords.includes(keyword)) {
      setKeywords([...keywords, keyword])
      setKeywordInput('')
    }
  }

  const removeKeyword = (keyword: string) => {
    setKeywords(keywords.filter(k => k !== keyword))
  }

  // DEPRECATED: toggleTool - Tools are now managed via Skills tab
  // Kept for backward compatibility but no longer used in UI
  const toggleTool = (tool: string) => {
    if (enabledTools.includes(tool)) {
      setEnabledTools(enabledTools.filter(t => t !== tool))
    } else {
      setEnabledTools([...enabledTools, tool])
    }
  }

  // Per-agent filter management
  const addGroupFilter = () => {
    const filter = groupFilterInput.trim()
    if (filter && !triggerGroupFilters.includes(filter)) {
      setTriggerGroupFilters([...triggerGroupFilters, filter])
      setGroupFilterInput('')
    }
  }

  const removeGroupFilter = (filter: string) => {
    setTriggerGroupFilters(triggerGroupFilters.filter(f => f !== filter))
  }

  const addNumberFilter = () => {
    const filter = numberFilterInput.trim()
    if (filter && !triggerNumberFilters.includes(filter)) {
      setTriggerNumberFilters([...triggerNumberFilters, filter])
      setNumberFilterInput('')
    }
  }

  const removeNumberFilter = (filter: string) => {
    setTriggerNumberFilters(triggerNumberFilters.filter(f => f !== filter))
  }

  const fetchOllamaModels = async () => {
    try {
      const data = await api.getOllamaHealth()
      if (data.available && data.models) {
        setOllamaModels(data.models.map((m) => m.name))
      }
    } catch {
      // Ollama not available
    }
  }

  // Vendors that have at least one configured instance, plus always include the current agent's vendor
  const availableVendors = useMemo(() => {
    const configured = [...new Set(allInstances.map(i => i.vendor))]
    // Always include the agent's current vendor (even if it has no instances, to avoid breaking existing agents)
    if (modelProvider && !configured.includes(modelProvider)) {
      configured.push(modelProvider)
    }
    return configured.map(v => ({ value: v, label: VENDOR_LABELS[v] || v }))
  }, [allInstances, modelProvider])

  const getAvailableModels = () => {
    // If an instance is selected and it has models, use those
    if (providerInstanceId) {
      const instance = providerInstances.find(i => i.id === providerInstanceId)
      if (instance && instance.available_models.length > 0) {
        return instance.available_models
      }
    }
    // For Ollama, use dynamically fetched models
    if (modelProvider === 'ollama') {
      return ollamaModels
    }
    // Use all models from all configured instances for this vendor (deduplicated)
    const vendorModels = [...new Set(providerInstances.flatMap(i => i.available_models))]
    if (vendorModels.length > 0) return vendorModels
    // Last resort: keep current model so the dropdown is never empty
    return modelName ? [modelName] : []
  }

  if (loading) {
    return <div className="p-8 text-center">Loading configuration...</div>
  }

  if (!agent) {
    return <div className="p-8 text-center text-red-600">Failed to load agent</div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-tsushin-border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 flex items-center gap-1.5"><InfoIcon size={16} /> About Configuration</h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          Configure all agent settings in one place: system prompt, personality tone, AI model, keywords, and built-in tools.
          Changes are saved immediately when you click the Save button.
        </p>
      </div>

      {/* System Prompt */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TargetIcon size={20} /> System Prompt</h3>
        <p className="text-sm text-tsushin-slate mb-3">
          Define the agent's role, capabilities, and behavior guidelines. This is the core instruction set.
        </p>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface font-mono text-sm"
          rows={8}
          placeholder="You are a helpful AI assistant..."
        />
      </div>

      {/* Persona Configuration */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TheaterIcon size={20} /> Agent Persona</h3>
        <p className="text-sm text-tsushin-slate mb-4">
          Select a persona that defines the agent's personality, communication style, role, and behavior guidelines.
          Personas are reusable templates that can be shared across multiple agents.
        </p>

        <div className="space-y-4">
          <select
            value={personaId || ''}
            onChange={(e) => {
              const id = e.target.value ? parseInt(e.target.value) : null
              setPersonaId(id)
              const persona = personas.find(p => p.id === id)
              setSelectedPersona(persona || null)
            }}
            className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
          >
            <option value="">Select a persona...</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name} — {persona.role || 'No role defined'}
              </option>
            ))}
          </select>

          {selectedPersona && (
            <div className="bg-tsushin-ink border border-tsushin-border rounded-lg p-4 space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-tsushin-fog mb-1 flex items-center gap-1"><ClipboardIcon size={14} /> Description</h4>
                <p className="text-sm text-tsushin-slate">{selectedPersona.description}</p>
              </div>

              {selectedPersona.role && (
                <div>
                  <h4 className="text-sm font-semibold text-tsushin-fog mb-1 flex items-center gap-1"><TargetIcon size={14} /> Role</h4>
                  <p className="text-sm text-tsushin-slate">{selectedPersona.role}</p>
                  {selectedPersona.role_description && (
                    <p className="text-xs text-tsushin-muted mt-1">{selectedPersona.role_description}</p>
                  )}
                </div>
              )}

              {selectedPersona.personality_traits && (
                <div>
                  <h4 className="text-sm font-semibold text-tsushin-fog mb-1 flex items-center gap-1"><SparklesIcon size={14} /> Personality Traits</h4>
                  <p className="text-sm text-tsushin-slate">{selectedPersona.personality_traits}</p>
                </div>
              )}

              {selectedPersona.guardrails && (
                <div>
                  <h4 className="text-sm font-semibold text-tsushin-fog mb-1 flex items-center gap-1"><ScaleIcon size={14} /> Guardrails</h4>
                  <p className="text-sm text-tsushin-slate">{selectedPersona.guardrails}</p>
                </div>
              )}

              <div className="pt-2 border-t border-tsushin-border">
                <a
                  href="/agents?tab=personas"
                  className="text-sm text-teal-400 hover:underline"
                >
                  → Manage Personas
                </a>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Model Selection */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><BotIcon size={20} /> AI Model</h3>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">Provider</label>
              <select
                value={modelProvider}
                onChange={(e) => {
                  const newVendor = e.target.value
                  setModelProvider(newVendor)
                  setProviderInstanceId(null)
                  // Filter from already-loaded allInstances — no extra API call needed
                  const vendorInsts = allInstances.filter(i => i.vendor === newVendor)
                  setProviderInstances(vendorInsts)
                  if (newVendor === 'ollama') {
                    setModelName(ollamaModels[0] || '')
                  } else {
                    const defaultInst = vendorInsts.find(i => i.is_default) || vendorInsts[0]
                    if (defaultInst && defaultInst.available_models.length > 0) {
                      setModelName(defaultInst.available_models[0])
                      setProviderInstanceId(defaultInst.id)
                    }
                  }
                }}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                {availableVendors.map((vendor) => (
                  <option key={vendor.value} value={vendor.value}>
                    {vendor.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-2">Model</label>
              <select
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                {getAvailableModels().map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Provider Instance (Optional) */}
          <div>
            <label className="block text-sm font-medium mb-2 flex items-center gap-2">
              <LinkIcon size={14} />
              Provider Instance
              <span className="text-xs text-tsushin-slate font-normal">(Optional)</span>
            </label>
            {providerInstances.length > 0 ? (
              <select
                value={providerInstanceId || ''}
                onChange={(e) => {
                  const id = e.target.value ? parseInt(e.target.value) : null
                  setProviderInstanceId(id)
                  // If instance has models, auto-select the first one
                  if (id) {
                    const inst = providerInstances.find(i => i.id === id)
                    if (inst && inst.available_models.length > 0) {
                      setModelName(inst.available_models[0])
                    }
                  }
                }}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                <option value="">No instance (use default)</option>
                {providerInstances.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.instance_name}
                    {inst.is_default ? ' (default)' : ''}
                    {inst.health_status === 'healthy' ? '' : ` [${inst.health_status}]`}
                  </option>
                ))}
              </select>
            ) : (
              <div className="px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-xs text-tsushin-slate">
                No instances configured for {VENDOR_LABELS[modelProvider] || modelProvider}.
                <a href="/hub" className="text-teal-400 hover:underline ml-1">Configure in Hub &gt; AI Providers</a>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Vector Store */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><DatabaseIcon size={20} /> Vector Store</h3>
        <p className="text-sm text-tsushin-slate mb-4">
          Select a vector store for long-term memory and knowledge retrieval. Leave blank to use the tenant default.
        </p>

        <div className="space-y-4">
          <div className="text-xs text-tsushin-slate px-2 py-1.5 rounded bg-tsushin-ink/50">
            {vectorStoreInstanceId ? (
              <>Using: <span className="text-teal-400">{vectorStoreInstances.find(v => v.id === vectorStoreInstanceId)?.instance_name || 'Custom'}</span> (per-agent override)</>
            ) : defaultVectorStoreId ? (
              <>Using tenant default: <span className="text-teal-400">{vectorStoreInstances.find(v => v.id === defaultVectorStoreId)?.instance_name || 'Unknown'}</span></>
            ) : (
              <>Using default: <span className="text-gray-400">ChromaDB (built-in)</span></>
            )}
          </div>

          {vectorStoreInstances.length > 0 ? (
            <select
              value={vectorStoreInstanceId || ''}
              onChange={(e) => setVectorStoreInstanceId(e.target.value ? parseInt(e.target.value) : null)}
              className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
            >
              <option value="">Use Tenant Default</option>
              {vectorStoreInstances.map((inst) => (
                <option key={inst.id} value={inst.id}>
                  {inst.instance_name} ({inst.vendor}){inst.health_status === 'healthy' ? '' : ` [${inst.health_status}]`}
                </option>
              ))}
            </select>
          ) : (
            <div className="px-3 py-2 border border-tsushin-border rounded-md bg-tsushin-ink text-xs text-tsushin-slate">
              No vector stores configured.
              <a href="/hub" className="text-teal-400 hover:underline ml-1">Configure in Hub &gt; Vector Stores</a>
            </div>
          )}

          {vectorStoreInstanceId && (
            <div>
              <label className="block text-sm font-medium mb-2">Vector Store Mode</label>
              <select
                value={vectorStoreMode}
                onChange={(e) => setVectorStoreMode(e.target.value)}
                className="w-full px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              >
                <option value="override">Override (use only this store)</option>
                <option value="complement">Complement (use this + default)</option>
                <option value="shadow">Shadow (write to both, read from default)</option>
              </select>
              <p className="text-xs text-tsushin-slate mt-1">
                {vectorStoreMode === 'override' && 'All reads and writes go to this store only.'}
                {vectorStoreMode === 'complement' && 'Reads check both stores; writes go to both.'}
                {vectorStoreMode === 'shadow' && 'Writes go to both stores; reads only from the default.'}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Keywords */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><KeyIcon size={20} /> Trigger Keywords</h3>
        <p className="text-sm text-tsushin-slate mb-3">
          Keywords that will trigger this agent in group chats (e.g., @AgentName, mentions)
        </p>

        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && addKeyword()}
            placeholder="Add keyword..."
            className="flex-1 px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
          />
          <button
            onClick={addKeyword}
            className="btn-primary px-4 py-2 rounded-md"
          >
            Add
          </button>
        </div>

        <div className="flex flex-wrap gap-2">
          {keywords.map((keyword) => (
            <span
              key={keyword}
              className="inline-flex items-center gap-2 px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 rounded-full text-sm"
            >
              {keyword}
              <button
                onClick={() => removeKeyword(keyword)}
                className="hover:text-blue-600 dark:hover:text-blue-300"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      </div>

      {/* Trigger Configuration */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TargetIcon size={20} /> Trigger Configuration</h3>
        <p className="text-sm text-tsushin-slate mb-4">
          Configure when this agent should respond. Leave blank to use system defaults.
        </p>

        <div className="space-y-4">
          <div>
            <label className="flex items-center gap-3 cursor-pointer mb-4">
              <input
                type="checkbox"
                checked={triggerDmEnabled === true}
                onChange={(e) => setTriggerDmEnabled(e.target.checked ? true : null)}
                className="w-5 h-5"
              />
              <div>
                <div className="font-medium">Enable DM Auto-Response</div>
                <div className="text-xs text-tsushin-muted">
                  Automatically respond to direct messages (if unchecked, uses system default)
                </div>
              </div>
            </label>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Group Filters</label>
            <p className="text-xs text-tsushin-muted mb-2">
              Group names to monitor. If empty, uses system default groups.
            </p>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={groupFilterInput}
                onChange={(e) => setGroupFilterInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addGroupFilter()}
                placeholder="Add group name..."
                className="flex-1 px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              />
              <button
                onClick={addGroupFilter}
                className="btn-primary px-4 py-2 rounded-md"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {triggerGroupFilters.map((filter) => (
                <span
                  key={filter}
                  className="inline-flex items-center gap-2 px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 rounded-full text-sm"
                >
                  {filter}
                  <button
                    onClick={() => removeGroupFilter(filter)}
                    className="hover:text-green-600 dark:hover:text-green-300"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Number Filters</label>
            <p className="text-xs text-tsushin-muted mb-2">
              Phone numbers to monitor. If empty, uses system default numbers.
            </p>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={numberFilterInput}
                onChange={(e) => setNumberFilterInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addNumberFilter()}
                placeholder="Add phone number..."
                className="flex-1 px-3 py-2 border border-tsushin-border rounded-md text-white bg-tsushin-surface"
              />
              <button
                onClick={addNumberFilter}
                className="btn-primary px-4 py-2 rounded-md"
              >
                Add
              </button>
            </div>
            <div className="flex flex-wrap gap-2">
              {triggerNumberFilters.map((filter) => (
                <span
                  key={filter}
                  className="inline-flex items-center gap-2 px-3 py-1 bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 rounded-full text-sm"
                >
                  {filter}
                  <button
                    onClick={() => removeNumberFilter(filter)}
                    className="hover:text-purple-600 dark:hover:text-purple-300"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Skills Info Banner - API Tools have been migrated to Skills */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 flex items-center gap-1.5"><LightbulbIcon size={16} /> Skills-Based Configuration</h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          Built-in tools (Web Search, Web Scraping, Flight Search) are now managed in the <strong>Skills</strong> tab.
          This provides better configuration options, per-agent customization, and unified management.
        </p>
        <a
          href={`/agents?tab=skills&agent=${agentId}`}
          className="inline-block mt-2 text-sm text-teal-400 hover:underline"
        >
          → Go to Skills Configuration
        </a>
      </div>

      {/* Status Settings */}
      <div className="bg-tsushin-surface border border-tsushin-border rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><SettingsIcon size={20} /> Status Settings</h3>

        <div className="space-y-3">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="w-5 h-5"
            />
            <div>
              <div className="font-medium">Active</div>
              <div className="text-xs text-tsushin-muted">
                Agent can respond to messages when active
              </div>
            </div>
          </label>

          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={isDefault}
              onChange={(e) => setIsDefault(e.target.checked)}
              className="w-5 h-5"
            />
            <div>
              <div className="font-medium">Default Agent</div>
              <div className="text-xs text-tsushin-muted">
                This agent will respond to contacts without specific agent assignments
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end gap-3 pt-4 border-t border-tsushin-border">
        <button
          onClick={() => loadData()}
          disabled={saving}
          className="px-6 py-2 border border-tsushin-border rounded-md hover:bg-tsushin-surface disabled:opacity-50"
        >
          Reset
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="btn-primary px-6 py-2 rounded-md disabled:opacity-50 font-medium"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  )
}
