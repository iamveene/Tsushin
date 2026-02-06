'use client'

import { useEffect, useState } from 'react'
import { api, Agent, TonePreset, Persona } from '@/lib/client'
import {
  InfoIcon, TargetIcon, TheaterIcon, BotIcon, KeyIcon, LightbulbIcon,
  SettingsIcon, ClipboardIcon, SparklesIcon, ScaleIcon
} from '@/components/ui/icons'

interface Props {
  agentId: number
}

// Legacy tools (google_search, weather, web_scraping) removed
// Now handled by Skills system: web_search, weather, web_scraping skills

const MODEL_PROVIDERS = [
  { value: 'anthropic', label: 'Anthropic', models: ['claude-sonnet-4.5', 'claude-3-5-sonnet-20241022', 'claude-3-opus-20240229'] },
  { value: 'openai', label: 'OpenAI', models: ['gpt-4', 'gpt-4-turbo', 'gpt-3.5-turbo'] },
  { value: 'gemini', label: 'Google Gemini', models: ['gemini-3-pro-preview', 'gemini-3-flash-preview', 'gemini-2.5-pro', 'gemini-2.5-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash', 'gemini-2.0-flash-lite'] },
  { value: 'ollama', label: 'Ollama (Local)', models: ['Gemma3:4b', 'llama3.1:8b', 'deepseek-r1:8b', 'MFDoom/deepseek-r1-tool-calling:8b'] },
  {
    value: 'openrouter',
    label: 'OpenRouter (100+ models)',
    models: [
      // Top 20 most popular models on OpenRouter
      'google/gemini-2.5-flash',
      'google/gemini-2.5-pro',
      'anthropic/claude-3.5-sonnet',
      'anthropic/claude-3-opus',
      'openai/gpt-4o',
      'openai/gpt-4-turbo',
      'meta-llama/llama-3.3-70b-instruct',
      'meta-llama/llama-3.1-405b-instruct',
      'mistralai/mistral-large',
      'mistralai/mixtral-8x22b-instruct',
      'deepseek/deepseek-r1',
      'deepseek/deepseek-chat',
      'qwen/qwen-2.5-72b-instruct',
      'cohere/command-r-plus',
      'perplexity/llama-3.1-sonar-huge-128k-online',
      'x-ai/grok-2',
      'nvidia/llama-3.1-nemotron-70b-instruct',
      'microsoft/wizardlm-2-8x22b',
      'databricks/dbrx-instruct',
      'nousresearch/hermes-3-llama-3.1-405b'
    ]
  }
]

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
  // enabledTools removed - use Skills system for web_search, weather, etc.
  const [modelProvider, setModelProvider] = useState('gemini')
  const [modelName, setModelName] = useState('gemini-2.5-pro')
  const [isActive, setIsActive] = useState(true)
  const [isDefault, setIsDefault] = useState(false)

  // Trigger configuration (per-agent)
  const [triggerDmEnabled, setTriggerDmEnabled] = useState<boolean | null>(null)
  const [triggerGroupFilters, setTriggerGroupFilters] = useState<string[]>([])
  const [triggerNumberFilters, setTriggerNumberFilters] = useState<string[]>([])

  // Input helpers for triggers
  const [groupFilterInput, setGroupFilterInput] = useState('')
  const [numberFilterInput, setNumberFilterInput] = useState('')

  useEffect(() => {
    loadData()
  }, [agentId])

  const loadData = async () => {
    setLoading(true)
    try {
      const [agentData, personasData] = await Promise.all([
        api.getAgent(agentId),
        api.getPersonas(true), // Only active personas
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
      setIsActive(agentData.is_active)
      setIsDefault(agentData.is_default)

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
        // enabled_tools removed - use Skills system for web_search, weather, etc.
        model_provider: modelProvider,
        model_name: modelName,
        is_active: isActive,
        is_default: isDefault,

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

  const getAvailableModels = () => {
    const provider = MODEL_PROVIDERS.find(p => p.value === modelProvider)
    return provider?.models || []
  }

  if (loading) {
    return <div className="p-8 text-center">Loading configuration...</div>
  }

  if (!agent) {
    return <div className="p-8 text-center text-red-600">Failed to load agent</div>
  }

  return (
    <div className="space-y-6">
      <div className="bg-blue-50 dark:bg-blue-900/20 border dark:border-gray-700 border-blue-200 dark:border-blue-700 rounded-lg p-4">
        <h3 className="text-sm font-medium text-blue-800 dark:text-blue-200 mb-2 flex items-center gap-1.5"><InfoIcon size={16} /> About Configuration</h3>
        <p className="text-sm text-blue-700 dark:text-blue-300">
          Configure all agent settings in one place: system prompt, personality tone, AI model, keywords, and built-in tools.
          Changes are saved immediately when you click the Save button.
        </p>
      </div>

      {/* System Prompt */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TargetIcon size={20} /> System Prompt</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Define the agent's role, capabilities, and behavior guidelines. This is the core instruction set.
        </p>
        <textarea
          value={systemPrompt}
          onChange={(e) => setSystemPrompt(e.target.value)}
          className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800 font-mono text-sm"
          rows={8}
          placeholder="You are a helpful AI assistant..."
        />
      </div>

      {/* Persona Configuration */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TheaterIcon size={20} /> Agent Persona</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
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
            className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
          >
            <option value="">Select a persona...</option>
            {personas.map((persona) => (
              <option key={persona.id} value={persona.id}>
                {persona.name} — {persona.role || 'No role defined'}
              </option>
            ))}
          </select>

          {selectedPersona && (
            <div className="bg-gray-50 dark:bg-gray-900/50 border dark:border-gray-700 rounded-lg p-4 space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1"><ClipboardIcon size={14} /> Description</h4>
                <p className="text-sm text-gray-600 dark:text-gray-400">{selectedPersona.description}</p>
              </div>

              {selectedPersona.role && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1"><TargetIcon size={14} /> Role</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedPersona.role}</p>
                  {selectedPersona.role_description && (
                    <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">{selectedPersona.role_description}</p>
                  )}
                </div>
              )}

              {selectedPersona.personality_traits && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1"><SparklesIcon size={14} /> Personality Traits</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedPersona.personality_traits}</p>
                </div>
              )}

              {selectedPersona.guardrails && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1 flex items-center gap-1"><ScaleIcon size={14} /> Guardrails</h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">{selectedPersona.guardrails}</p>
                </div>
              )}

              <div className="pt-2 border-t dark:border-gray-700">
                <a
                  href="/agents?tab=personas"
                  className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                >
                  → Manage Personas
                </a>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* AI Model Selection */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><BotIcon size={20} /> AI Model</h3>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium mb-2">Provider</label>
            <select
              value={modelProvider}
              onChange={(e) => {
                setModelProvider(e.target.value)
                const provider = MODEL_PROVIDERS.find(p => p.value === e.target.value)
                if (provider && provider.models.length > 0) {
                  setModelName(provider.models[0])
                }
              }}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            >
              {MODEL_PROVIDERS.map((provider) => (
                <option key={provider.value} value={provider.value}>
                  {provider.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Model</label>
            <select
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              className="w-full px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
            >
              {getAvailableModels().map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Keywords */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><KeyIcon size={20} /> Trigger Keywords</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
          Keywords that will trigger this agent in group chats (e.g., @AgentName, mentions)
        </p>

        <div className="flex gap-2 mb-3">
          <input
            type="text"
            value={keywordInput}
            onChange={(e) => setKeywordInput(e.target.value)}
            onKeyPress={(e) => e.key === 'Enter' && addKeyword()}
            placeholder="Add keyword..."
            className="flex-1 px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
          />
          <button
            onClick={addKeyword}
            className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
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
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4 flex items-center gap-2"><TargetIcon size={20} /> Trigger Configuration</h3>
        <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
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
                <div className="text-xs text-gray-500 dark:text-gray-400">
                  Automatically respond to direct messages (if unchecked, uses system default)
                </div>
              </div>
            </label>
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">Group Filters</label>
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Group names to monitor. If empty, uses system default groups.
            </p>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={groupFilterInput}
                onChange={(e) => setGroupFilterInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addGroupFilter()}
                placeholder="Add group name..."
                className="flex-1 px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              />
              <button
                onClick={addGroupFilter}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
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
            <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
              Phone numbers to monitor. If empty, uses system default numbers.
            </p>
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={numberFilterInput}
                onChange={(e) => setNumberFilterInput(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && addNumberFilter()}
                placeholder="Add phone number..."
                className="flex-1 px-3 py-2 border dark:border-gray-700 rounded-md text-gray-900 dark:text-gray-100 bg-white dark:bg-gray-800"
              />
              <button
                onClick={addNumberFilter}
                className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
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
          Built-in tools (Web Search, Weather, Web Scraping, Flight Search) are now managed in the <strong>Skills</strong> tab.
          This provides better configuration options, per-agent customization, and unified management.
        </p>
        <a
          href={`/agents?tab=skills&agent=${agentId}`}
          className="inline-block mt-2 text-sm text-blue-600 dark:text-blue-400 hover:underline"
        >
          → Go to Skills Configuration
        </a>
      </div>

      {/* Status Settings */}
      <div className="bg-white dark:bg-gray-800 border dark:border-gray-700 rounded-lg p-6">
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
              <div className="text-xs text-gray-500 dark:text-gray-400">
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
              <div className="text-xs text-gray-500 dark:text-gray-400">
                This agent will respond to contacts without specific agent assignments
              </div>
            </div>
          </label>
        </div>
      </div>

      {/* Save Button */}
      <div className="flex justify-end gap-3 pt-4 border-t dark:border-gray-700">
        <button
          onClick={() => loadData()}
          disabled={saving}
          className="px-6 py-2 border dark:border-gray-700 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50"
        >
          Reset
        </button>
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50 font-medium"
        >
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  )
}
