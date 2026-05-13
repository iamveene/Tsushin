'use client'

/**
 * Phase 17: Config Panel Component
 *
 * Model configuration and context preview for cockpit mode.
 * Features:
 * - Model settings (temperature, max tokens)
 * - System prompt preview
 * - Context window preview
 * - Agent configuration quick access
 * - Model pricing display for cost awareness
 *
 * BUG-007 Fix: Settings are now persisted to backend via PlaygroundSettings API
 */

import React, { useState, useEffect, useCallback, useRef } from 'react'
import { api, Agent, PlaygroundSettings, ProviderInstance } from '@/lib/client'
import {
  SettingsIcon,
  BotIcon,
  SlidersIcon,
  DocumentIcon,
  LinkIcon
} from '@/components/ui/icons'
import { PROVIDER_MODEL_CATALOG, getProviderModelLabels } from '@/lib/provider-models'

function redactPromptPreview(prompt?: string | null): string {
  if (!prompt?.trim()) return 'No system instructions configured'
  return 'Hidden by default. Use Show to inspect the agent instructions.'
}

// Model pricing per 1M tokens (USD) - synced with backend TokenTracker
// Format: { prompt: input cost, completion: output cost }
const MODEL_PRICING: Record<string, { prompt: number; completion: number }> = {
  // OpenAI
  'gpt-5.5': { prompt: 5.0, completion: 30.0 },
  'gpt-5.5-pro': { prompt: 30.0, completion: 180.0 },
  'gpt-5.4': { prompt: 2.5, completion: 15.0 },
  'gpt-5.4-pro': { prompt: 30.0, completion: 180.0 },
  'gpt-5.4-mini': { prompt: 0.75, completion: 4.5 },
  'gpt-5.4-nano': { prompt: 0.20, completion: 1.0 },
  'gpt-4o': { prompt: 2.5, completion: 10.0 },
  'gpt-4o-mini': { prompt: 0.15, completion: 0.60 },
  'gpt-4-turbo': { prompt: 10.0, completion: 30.0 },
  'gpt-3.5-turbo': { prompt: 0.5, completion: 1.5 },
  'o1': { prompt: 15.0, completion: 60.0 },
  'o1-mini': { prompt: 3.0, completion: 12.0 },
  // Anthropic
  'claude-opus-4-7': { prompt: 5.0, completion: 25.0 },
  'claude-opus-4-7-latest': { prompt: 5.0, completion: 25.0 },
  'claude-opus-4-6': { prompt: 15.0, completion: 75.0 },
  'claude-sonnet-4-6': { prompt: 3.0, completion: 15.0 },
  'claude-haiku-4-5': { prompt: 0.80, completion: 4.0 },
  'claude-sonnet-4-20250514': { prompt: 3.0, completion: 15.0 },
  'claude-3-5-sonnet-20241022': { prompt: 3.0, completion: 15.0 },
  'claude-3-opus-20240229': { prompt: 15.0, completion: 75.0 },
  // Google Gemini
  'gemini-3-flash-preview': { prompt: 0.30, completion: 2.50 },
  'gemini-3.1-flash-lite-preview': { prompt: 0.10, completion: 0.40 },
  'gemini-2.5-pro': { prompt: 1.25, completion: 5.0 },
  'gemini-2.5-flash': { prompt: 0.075, completion: 0.3 },
  'gemini-2.5-flash-lite': { prompt: 0.10, completion: 0.40 },
  'gemini-2.0-flash': { prompt: 0.10, completion: 0.40 },
  'gemini-1.5-pro': { prompt: 1.25, completion: 5.0 },
  'gemini-1.5-flash': { prompt: 0.075, completion: 0.3 },
  // Groq-hosted/open models
  'openai/gpt-oss-120b': { prompt: 0.15, completion: 0.60 },
  'openai/gpt-oss-20b': { prompt: 0.075, completion: 0.30 },
  'llama-3.3-70b-versatile': { prompt: 0.59, completion: 0.79 },
  'llama-3.1-8b-instant': { prompt: 0.05, completion: 0.08 },
  // xAI Grok
  'grok-4.3': { prompt: 1.25, completion: 2.50 },
  'grok-4.3-latest': { prompt: 1.25, completion: 2.50 },
  'grok-4.3-latest': { prompt: 1.25, completion: 2.50 },
  'grok-4.20-multi-agent-0309': { prompt: 1.25, completion: 2.50 },
  'grok-4.20-0309-reasoning': { prompt: 1.25, completion: 2.50 },
  'grok-4.20-0309-non-reasoning': { prompt: 1.25, completion: 2.50 },
  'grok-4-1-fast-reasoning': { prompt: 0.20, completion: 0.50 },
  'grok-4-1-fast-non-reasoning': { prompt: 0.20, completion: 0.50 },
  // DeepSeek
  'deepseek-v4-flash': { prompt: 0.14, completion: 0.28 },
  'deepseek-v4-pro': { prompt: 0.55, completion: 2.19 },
  // Ollama models are always free — handled dynamically via getModelCostInfo fallback
  // OpenRouter (unified API gateway - prices vary by model)
  'openai/gpt-5.5': { prompt: 5.0, completion: 30.0 },
  'openai/gpt-5.5-pro': { prompt: 30.0, completion: 180.0 },
  'anthropic/claude-opus-4.7': { prompt: 5.0, completion: 25.0 },
  'anthropic/claude-opus-4-7': { prompt: 5.0, completion: 25.0 },
  'x-ai/grok-4.3': { prompt: 1.25, completion: 2.50 },
  'x-ai/grok-4.3-latest': { prompt: 1.25, completion: 2.50 },
  'x-ai/grok-4.20-multi-agent-0309': { prompt: 1.25, completion: 2.50 },
  'x-ai/grok-4.20-0309-reasoning': { prompt: 1.25, completion: 2.50 },
  'x-ai/grok-4.20-0309-non-reasoning': { prompt: 1.25, completion: 2.50 },
  'x-ai/grok-4-1-fast-reasoning': { prompt: 0.20, completion: 0.50 },
  'x-ai/grok-4-1-fast-non-reasoning': { prompt: 0.20, completion: 0.50 },
  'google/gemini-2.5-flash': { prompt: 0.075, completion: 0.3 },
  'google/gemini-2.5-pro': { prompt: 1.25, completion: 5.0 },
  'google/gemini-2.0-flash-thinking-exp': { prompt: 0.10, completion: 0.40 },
  'anthropic/claude-sonnet-4-5': { prompt: 3.0, completion: 15.0 },
  'anthropic/claude-3.5-sonnet': { prompt: 3.0, completion: 15.0 },
  'anthropic/claude-3-opus': { prompt: 15.0, completion: 75.0 },
  'openai/gpt-4o': { prompt: 2.5, completion: 10.0 },
  'openai/gpt-4-turbo': { prompt: 10.0, completion: 30.0 },
  'meta-llama/llama-3.3-70b-instruct': { prompt: 0.35, completion: 0.4 },
  'meta-llama/llama-3.1-405b-instruct': { prompt: 2.7, completion: 2.7 },
  'mistralai/mistral-large': { prompt: 2.0, completion: 6.0 },
  'mistralai/mixtral-8x22b-instruct': { prompt: 0.65, completion: 0.65 },
  'deepseek/deepseek-r1': { prompt: 0.55, completion: 2.19 },
  'deepseek/deepseek-r1:free': { prompt: 0.0, completion: 0.0 },
  'deepseek/deepseek-chat': { prompt: 0.14, completion: 0.28 },
  'qwen/qwen-2.5-72b-instruct': { prompt: 0.35, completion: 0.4 },
  'cohere/command-r-plus': { prompt: 2.5, completion: 10.0 },
  'perplexity/llama-3.1-sonar-huge-128k-online': { prompt: 5.0, completion: 5.0 },
  'x-ai/grok-2': { prompt: 5.0, completion: 10.0 },
  'nvidia/llama-3.1-nemotron-70b-instruct': { prompt: 0.35, completion: 0.4 },
  'microsoft/wizardlm-2-8x22b': { prompt: 0.63, completion: 0.63 },
  'databricks/dbrx-instruct': { prompt: 0.60, completion: 0.60 },
  'nousresearch/hermes-3-llama-3.1-405b': { prompt: 2.7, completion: 2.7 },
}

// Get cost tier label and color for a model
const getModelCostInfo = (modelName: string, provider?: string): { tier: string; color: string; bgColor: string } => {
  const pricing = MODEL_PRICING[modelName]
  // Ollama models are always free (local inference)
  if (!pricing && provider?.toLowerCase() === 'ollama') {
    return { tier: 'Free', color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' }
  }
  if (!pricing) return { tier: '?', color: 'text-white/40', bgColor: 'bg-white/5' }

  const avgCost = (pricing.prompt + pricing.completion) / 2

  if (avgCost === 0) return { tier: 'Free', color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' }
  if (avgCost < 1) return { tier: '$', color: 'text-green-400', bgColor: 'bg-green-500/10' }
  if (avgCost < 5) return { tier: '$$', color: 'text-yellow-400', bgColor: 'bg-yellow-500/10' }
  if (avgCost < 20) return { tier: '$$$', color: 'text-orange-400', bgColor: 'bg-orange-500/10' }
  return { tier: '$$$$', color: 'text-red-400', bgColor: 'bg-red-500/10' }
}

// Format cost for display
const formatCost = (cost: number): string => {
  if (cost === 0) return 'Free'
  if (cost < 0.1) return `$${cost.toFixed(3)}`
  return `$${cost.toFixed(2)}`
}

// Common models by provider, shared with setup, provider instances, Studio, and Sentinel.
const MODEL_OPTIONS = PROVIDER_MODEL_CATALOG

interface ConfigPanelProps {
  agentId: number | null
  settings?: PlaygroundSettings | null
  onSettingsChange?: (settings: PlaygroundSettings) => void
}

export default function ConfigPanel({ agentId, settings, onSettingsChange }: ConfigPanelProps) {
  const [agent, setAgent] = useState<Agent | null>(null)
  const [loading, setLoading] = useState(false)
  const [localSettings, setLocalSettings] = useState({
    temperature: 0.7,
    maxTokens: 2048,
    streamResponse: true,
    modelOverride: '' // Empty means use agent's default model
  })
  const [showPrompt, setShowPrompt] = useState(false)
  const [saving, setSaving] = useState(false)
  const [showModelSelector, setShowModelSelector] = useState(false)
  const [showCustomModelInput, setShowCustomModelInput] = useState(false)
  const [customModelInput, setCustomModelInput] = useState('')
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const [providerInstances, setProviderInstances] = useState<ProviderInstance[]>([])

  // Load settings from parent props or fetch from API
  useEffect(() => {
    if (agentId && settings?.modelSettings?.[String(agentId)]) {
      const agentSettings = settings.modelSettings[String(agentId)]
      setLocalSettings({
        temperature: agentSettings.temperature ?? 0.7,
        maxTokens: agentSettings.maxTokens ?? 2048,
        streamResponse: agentSettings.streamResponse ?? true,
        modelOverride: agentSettings.modelOverride ?? ''
      })
    }
  }, [agentId, settings])

  useEffect(() => {
    if (agentId) {
      loadAgentConfig()
    }
  }, [agentId])

  const loadAgentConfig = async () => {
    if (!agentId) return
    setLoading(true)
    try {
      const agents = await api.getAgents()
      const foundAgent = agents.find(a => a.id === agentId)
      if (foundAgent) {
        setAgent(foundAgent)
        // Load provider instances for this agent's vendor to populate the model override selector
        try {
          const instances = await api.getProviderInstances(foundAgent.model_provider)
          setProviderInstances(instances)
        } catch {
          setProviderInstances([])
        }
      }
    } catch (error) {
      console.error('Failed to load agent config:', error)
    } finally {
      setLoading(false)
    }
  }

  // BUG-007 Fix: Debounced save to backend
  const saveSettingsToBackend = useCallback(async (newSettings: typeof localSettings) => {
    if (!agentId) return

    setSaving(true)
    try {
      const updatedSettings: PlaygroundSettings = {
        modelSettings: {
          ...(settings?.modelSettings || {}),
          [String(agentId)]: newSettings
        }
      }
      await api.updatePlaygroundSettings(updatedSettings)
      onSettingsChange?.(updatedSettings)
    } catch (error) {
      console.error('Failed to save settings:', error)
    } finally {
      setSaving(false)
    }
  }, [agentId, settings, onSettingsChange])

  const handleSettingChange = (key: string, value: any) => {
    const newSettings = { ...localSettings, [key]: value }
    setLocalSettings(newSettings)

    // Debounce save to avoid too many API calls
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveSettingsToBackend(newSettings)
    }, 500)
  }

  return (
    <div className="h-full flex flex-col bg-tsushin-deep">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/[0.06]">
        <div className="flex items-center gap-2">
          <span className="text-white/70"><SettingsIcon size={18} /></span>
          <h3 className="text-sm font-semibold text-white">Configuration</h3>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <div className="flex items-center justify-center h-full">
            <div className="w-6 h-6 border-2 border-white/20 border-t-teal-500 rounded-full animate-spin" />
          </div>
        ) : !agent ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <span className="text-white/30 mb-2"><SettingsIcon size={48} /></span>
            <p className="text-sm text-white/40">Select an agent to view config</p>
          </div>
        ) : (
          <>
            {/* Agent Info */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                <BotIcon size={14} /> Agent Info
              </h4>
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/40">Name</span>
                  <span className="text-white font-medium">{agent.contact_name}</span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/40">Provider</span>
                  <span className="text-white font-medium">{agent.model_provider}</span>
                </div>

                {/* Current Model Cost Indicator */}
                {(() => {
                  const currentModel = localSettings.modelOverride || agent.model_name
                  const pricing = agent.model_provider?.toLowerCase() === 'ollama'
                    ? { prompt: 0.0, completion: 0.0 }
                    : MODEL_PRICING[currentModel]
                  const costInfo = getModelCostInfo(currentModel, agent.model_provider)

                  return (
                    <div className="flex items-center justify-between text-xs">
                      <span className="text-white/40">Est. Cost</span>
                      <div className="flex items-center gap-2">
                        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${costInfo.bgColor} ${costInfo.color}`}>
                          {costInfo.tier}
                        </span>
                        {pricing && pricing.prompt > 0 && (
                          <span className="text-white/50 text-[10px]">
                            ~{formatCost((pricing.prompt + pricing.completion) / 2)}/1M
                          </span>
                        )}
                      </div>
                    </div>
                  )
                })()}

                {/* Model Selector */}
                <div className="text-xs">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-white/40">Model</span>
                    <button
                      onClick={() => setShowModelSelector(!showModelSelector)}
                      className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-teal-500/10 border border-teal-500/20 text-teal-400 hover:bg-teal-500/20 transition-colors"
                    >
                      <span className="font-mono text-[11px]">
                        {localSettings.modelOverride || agent.model_name}
                      </span>
                      <svg className={`w-3 h-3 transition-transform ${showModelSelector ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                  </div>

                  {showModelSelector && (
                    <div className="bg-black/40 rounded-lg border border-white/[0.06] p-2 space-y-1 max-h-[280px] overflow-y-auto">
                      {/* Use default */}
                      {(() => {
                        const defaultCostInfo = getModelCostInfo(agent.model_name, agent.model_provider)
                        return (
                          <button
                            onClick={() => {
                              handleSettingChange('modelOverride', '')
                              setShowModelSelector(false)
                            }}
                            className={`w-full px-2 py-1.5 text-left rounded text-xs transition-colors ${
                              !localSettings.modelOverride
                                ? 'bg-teal-500/20 text-teal-400'
                                : 'text-white/60 hover:bg-white/[0.04] hover:text-white'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div>
                                <span className="font-medium">Use Default</span>
                                <span className="text-white/40 ml-1">({agent.model_name})</span>
                              </div>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${defaultCostInfo.bgColor} ${defaultCostInfo.color}`}>
                                {defaultCostInfo.tier}
                              </span>
                            </div>
                          </button>
                        )
                      })()}

                      {/* Provider models with pricing — sourced from configured instances */}
                      {(() => {
                        // TTS-only models must not appear in the chat-model picker — they
                        // emit audio only and would fail at call time on a text agent.
                        const TTS_ONLY_SUFFIXES = ['-tts-preview', '-tts']
                        const isTTSOnlyModel = (m: string) =>
                          TTS_ONLY_SUFFIXES.some(s => m.endsWith(s))
                        // Build model list from configured instances; fall back to static MODEL_OPTIONS if none.
                        // Enrich raw model IDs with friendly labels from MODEL_OPTIONS when available.
                        const vendorKey = agent.model_provider?.toLowerCase() || ''
                        const staticOptions = MODEL_OPTIONS[vendorKey] || []
                        const instanceModels = [
                          ...new Set(providerInstances.flatMap(i => i.available_models))
                        ].filter(m => !isTTSOnlyModel(m))
                        // v0.7.0: Ollama models now flow through providerInstances like every
                        // other vendor — single source of truth via the provider_instance catalog.
                        const dynamicModels = instanceModels.length > 0
                          ? getProviderModelLabels(vendorKey, instanceModels, {
                              currentModel: localSettings.modelOverride || agent.model_name,
                            })
                          : staticOptions
                        return dynamicModels
                          .filter(o => !isTTSOnlyModel(o.value))
                      })().map(model => {
                        const costInfo = getModelCostInfo(model.value, agent.model_provider)
                        const pricing = agent.model_provider?.toLowerCase() === 'ollama'
                          ? { prompt: 0.0, completion: 0.0 }
                          : MODEL_PRICING[model.value]

                        return (
                          <button
                            key={model.value}
                            onClick={() => {
                              handleSettingChange('modelOverride', model.value)
                              setShowModelSelector(false)
                              setShowCustomModelInput(false)
                            }}
                            className={`w-full px-2 py-2 text-left rounded text-xs transition-colors group ${
                              localSettings.modelOverride === model.value
                                ? 'bg-teal-500/20 text-teal-400'
                                : 'text-white/60 hover:bg-white/[0.04] hover:text-white'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-medium">{model.label}</span>
                              <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${costInfo.bgColor} ${costInfo.color}`}>
                                {costInfo.tier}
                              </span>
                            </div>
                            {pricing && (
                              <div className="text-[10px] text-white/30 mt-0.5 group-hover:text-white/40 transition-colors">
                                {pricing.prompt === 0 && pricing.completion === 0 ? (
                                  <span className="text-emerald-400/60">Local model - no API cost</span>
                                ) : (
                                  <span>
                                    In: {formatCost(pricing.prompt)}/1M · Out: {formatCost(pricing.completion)}/1M
                                  </span>
                                )}
                              </div>
                            )}
                          </button>
                        )
                      })}

                      {/* Custom Model Input */}
                      {!showCustomModelInput ? (
                        <button
                          onClick={() => setShowCustomModelInput(true)}
                          className="w-full px-2 py-2 text-left rounded text-xs transition-colors text-white/60 hover:bg-white/[0.04] hover:text-white border border-white/[0.06] border-dashed"
                        >
                          <div className="flex items-center gap-2">
                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                            </svg>
                            <span className="font-medium">Use Custom Model</span>
                          </div>
                          <div className="text-[10px] text-white/40 mt-0.5">
                            Type any model ID for this provider
                          </div>
                        </button>
                      ) : (
                        <div className="bg-white/[0.02] rounded-lg border border-white/[0.06] p-2 space-y-2">
                          <div className="text-xs text-white/60 font-medium">Custom Model Name</div>
                          <input
                            type="text"
                            value={customModelInput}
                            onChange={(e) => setCustomModelInput(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' && customModelInput.trim()) {
                                handleSettingChange('modelOverride', customModelInput.trim())
                                setShowModelSelector(false)
                                setShowCustomModelInput(false)
                                setCustomModelInput('')
                              }
                            }}
                            placeholder="e.g., gpt-5.5 or provider/model-name"
                            className="w-full px-2 py-1.5 text-xs bg-black/40 border border-white/[0.06] rounded text-white placeholder-white/30 focus:outline-none focus:border-teal-500/50"
                            autoFocus
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => {
                                if (customModelInput.trim()) {
                                  handleSettingChange('modelOverride', customModelInput.trim())
                                  setShowModelSelector(false)
                                  setShowCustomModelInput(false)
                                  setCustomModelInput('')
                                }
                              }}
                              className="flex-1 px-2 py-1 text-xs bg-teal-500/20 text-teal-400 border border-teal-500/30 rounded hover:bg-teal-500/30 transition-colors"
                              disabled={!customModelInput.trim()}
                            >
                              Apply
                            </button>
                            <button
                              onClick={() => {
                                setShowCustomModelInput(false)
                                setCustomModelInput('')
                              }}
                              className="px-2 py-1 text-xs bg-white/[0.02] text-white/60 border border-white/[0.06] rounded hover:bg-white/[0.04] transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                          <div className="text-[10px] text-white/40">
                            Manual IDs are saved as typed and may use direct or gateway naming.
                          </div>
                        </div>
                      )}

                      {/* Pricing legend */}
                      <div className="mt-2 pt-2 border-t border-white/[0.06] px-1">
                        <div className="flex items-center justify-between text-[9px] text-white/30">
                          <span>Cost per 1M tokens</span>
                          <div className="flex gap-1.5">
                            <span className="text-emerald-400">Free</span>
                            <span className="text-green-400">$</span>
                            <span className="text-yellow-400">$$</span>
                            <span className="text-orange-400">$$$</span>
                            <span className="text-red-400">$$$$</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {localSettings.modelOverride && localSettings.modelOverride !== agent.model_name && (
                    <div className="mt-2 flex items-center gap-1.5 text-amber-400/70 text-[10px]">
                      <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                      </svg>
                      <span>Temporary override for this session</span>
                    </div>
                  )}
                </div>

                {agent.persona_name && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-white/40">Persona</span>
                    <span className="text-purple-400">{agent.persona_name}</span>
                  </div>
                )}
                <div className="flex items-center justify-between text-xs">
                  <span className="text-white/40">Memory Size</span>
                  <span className="text-white font-medium">{agent.memory_size || 10} messages</span>
                </div>
              </div>
            </div>

            {/* Model Settings */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-4 flex items-center gap-2">
                <SlidersIcon size={14} /> Model Settings
                {saving && (
                  <span className="ml-auto text-[10px] text-teal-400 animate-pulse">Saving...</span>
                )}
              </h4>

              {/* Temperature */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-white/60">Temperature</label>
                  <span className="text-xs text-teal-400 font-mono">{localSettings.temperature.toFixed(2)}</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="2"
                  step="0.1"
                  value={localSettings.temperature}
                  onChange={e => handleSettingChange('temperature', parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-white/[0.08] rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-teal-500 [&::-webkit-slider-thumb]:shadow-lg"
                />
                <div className="flex justify-between text-[10px] text-white/30 mt-1">
                  <span>Precise</span>
                  <span>Creative</span>
                </div>
              </div>

              {/* Max Tokens */}
              <div className="mb-4">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-xs text-white/60">Max Tokens</label>
                  <span className="text-xs text-teal-400 font-mono">{localSettings.maxTokens}</span>
                </div>
                <input
                  type="range"
                  min="256"
                  max="8192"
                  step="256"
                  value={localSettings.maxTokens}
                  onChange={e => handleSettingChange('maxTokens', parseInt(e.target.value))}
                  className="w-full h-1.5 bg-white/[0.08] rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-teal-500 [&::-webkit-slider-thumb]:shadow-lg"
                />
                <div className="flex justify-between text-[10px] text-white/30 mt-1">
                  <span>256</span>
                  <span>8192</span>
                </div>
              </div>

              {/* Stream Response Toggle */}
              <div className="flex items-center justify-between">
                <label className="text-xs text-white/60">Stream Response</label>
                <button
                  onClick={() => handleSettingChange('streamResponse', !localSettings.streamResponse)}
                  className={`
                    w-10 h-5 rounded-full transition-colors relative
                    ${localSettings.streamResponse ? 'bg-teal-500' : 'bg-white/[0.1]'}
                  `}
                >
                  <span
                    className={`
                      absolute top-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform
                      ${localSettings.streamResponse ? 'left-[22px]' : 'left-0.5'}
                    `}
                  />
                </button>
              </div>
            </div>

            {/* Agent Instructions */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <div className="flex items-center justify-between mb-3">
                <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider flex items-center gap-2">
                  <DocumentIcon size={14} /> Agent Instructions
                </h4>
                <button
                  onClick={() => setShowPrompt(!showPrompt)}
                  className="text-xs text-teal-400 hover:text-teal-300"
                >
                  {showPrompt ? 'Hide' : 'Show'}
                </button>
              </div>

              {showPrompt && (
                <div className="bg-white/[0.02] rounded-lg border border-white/[0.06] p-3 max-h-[200px] overflow-auto">
                  <pre className="text-xs text-white/70 whitespace-pre-wrap font-mono">
                    {agent.system_prompt || 'No system instructions configured'}
                  </pre>
                </div>
              )}

              {!showPrompt && (
                <div className="text-xs text-white/40">
                  {redactPromptPreview(agent.system_prompt)}
                </div>
              )}
            </div>

            {/* Features panel removed - all capabilities are now managed via Skills system */}
            {/* Use the Skills tab in the inspector to view/manage agent skills */}

            {/* Quick Links */}
            <div className="bg-white/[0.02] rounded-xl border border-white/[0.06] p-4">
              <h4 className="text-xs font-semibold text-white/50 uppercase tracking-wider mb-3 flex items-center gap-2">
                <LinkIcon size={14} /> Quick Actions
              </h4>
              <div className="space-y-2">
                <a
                  href={`/agents?edit=${agentId}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] text-xs text-white/70 hover:text-white transition-colors border border-white/[0.06]"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                  </svg>
                  Edit Agent Settings
                </a>
                <a
                  href={`/agents/personas`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] text-xs text-white/70 hover:text-white transition-colors border border-white/[0.06]"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                  Manage Personas
                </a>
                <a
                  href={`/hub/custom-tools`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/[0.02] hover:bg-white/[0.04] text-xs text-white/70 hover:text-white transition-colors border border-white/[0.06]"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0" />
                  </svg>
                  Manage Tools
                </a>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
