'use client'

/**
 * System AI Configuration Settings Page
 * Phase 27: Points to an existing Provider Instance instead of
 * duplicating provider/model configuration.
 */

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'
import { authenticatedFetch, ProviderInstance, api as apiClient, Config } from '@/lib/client'
import {
  GeminiIcon,
  OpenAIIcon,
  AnthropicIcon,
  GlobeIcon,
  LightningIcon,
  BrainIcon,
  BeakerIcon,
  CloudIcon,
  BotIcon as BotIconSvg,
  type IconProps,
} from '@/components/ui/icons'

// Grok (xAI) icon
const GrokIcon = ({ size, className }: IconProps) => (
  <svg className={className} width={size || 20} height={size || 20} viewBox="0 0 24 24" fill="currentColor">
    <path d="M4.5 2l7.5 10L4.5 22h2.1l6.45-8.55L19.5 22h2.1L12 12 21.6 2h-2.1l-6.45 8.55L6.6 2z" />
  </svg>
)

const VENDOR_ICONS: Record<string, React.FC<{ size?: number; className?: string }>> = {
  openai: OpenAIIcon,
  anthropic: AnthropicIcon,
  gemini: GeminiIcon,
  groq: LightningIcon,
  grok: GrokIcon,
  deepseek: BrainIcon,
  openrouter: GlobeIcon,
  vertex_ai: CloudIcon,
  ollama: BotIconSvg,
  custom: BeakerIcon,
}

const VENDOR_COLORS: Record<string, { text: string; bg: string; border: string }> = {
  openai: { text: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  anthropic: { text: 'text-orange-400', bg: 'bg-orange-500/10', border: 'border-orange-500/30' },
  gemini: { text: 'text-blue-400', bg: 'bg-blue-500/10', border: 'border-blue-500/30' },
  groq: { text: 'text-yellow-400', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30' },
  grok: { text: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
  deepseek: { text: 'text-cyan-400', bg: 'bg-cyan-500/10', border: 'border-cyan-500/30' },
  openrouter: { text: 'text-teal-400', bg: 'bg-teal-500/10', border: 'border-teal-500/30' },
  vertex_ai: { text: 'text-sky-400', bg: 'bg-sky-500/10', border: 'border-sky-500/30' },
  ollama: { text: 'text-purple-400', bg: 'bg-purple-500/10', border: 'border-purple-500/30' },
  custom: { text: 'text-rose-400', bg: 'bg-rose-500/10', border: 'border-rose-500/30' },
}

const VENDOR_LABELS: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  gemini: 'Google Gemini',
  groq: 'Groq',
  grok: 'Grok (xAI)',
  deepseek: 'DeepSeek',
  openrouter: 'OpenRouter',
  vertex_ai: 'Vertex AI',
  ollama: 'Ollama',
  custom: 'Custom',
}

interface SystemAIConfig {
  provider: string
  model_name: string
  provider_instance_id: number | null
  instance_name?: string
  vendor?: string
}

interface TestResult {
  success: boolean
  message: string
  provider: string
  model: string
  token_usage?: Record<string, number>
  error?: string
}

export default function AIConfigurationPage() {
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  const [config, setConfig] = useState<SystemAIConfig | null>(null)
  const [instances, setInstances] = useState<ProviderInstance[]>([])

  const [selectedInstanceId, setSelectedInstanceId] = useState<number | null>(null)
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  // BUG-716: platform-wide bounds for the agentic loop. Lives on the global
  // Config row and is exposed via PUT /api/config (already wired in schemas).
  const [platformConfig, setPlatformConfig] = useState<Config | null>(null)
  const [platformMinRounds, setPlatformMinRounds] = useState<number>(1)
  const [platformMaxRounds, setPlatformMaxRounds] = useState<number>(8)
  const [savingPlatform, setSavingPlatform] = useState(false)
  const [platformSuccess, setPlatformSuccess] = useState<string | null>(null)
  const [platformError, setPlatformError] = useState<string | null>(null)

  const apiUrl = ''

  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      const [configRes, instancesRes] = await Promise.all([
        authenticatedFetch(`${apiUrl}/api/config/system-ai`),
        authenticatedFetch(`${apiUrl}/api/provider-instances`),
      ])

      if (configRes.ok) {
        const configData: SystemAIConfig = await configRes.json()
        setConfig(configData)
        setSelectedInstanceId(configData.provider_instance_id)
        setSelectedModel(configData.model_name)
      } else {
        throw new Error('Failed to load configuration')
      }

      if (instancesRes.ok) {
        const instancesData: ProviderInstance[] = await instancesRes.json()
        // Only show active instances
        setInstances(instancesData.filter(i => i.is_active))
      }

      // Platform-wide agentic-loop bounds (BUG-716)
      try {
        const fullConfig = await apiClient.getConfig()
        setPlatformConfig(fullConfig)
        setPlatformMinRounds(fullConfig.platform_min_agentic_rounds ?? 1)
        setPlatformMaxRounds(fullConfig.platform_max_agentic_rounds ?? 8)
      } catch (cfgErr) {
        console.warn('Failed to load platform agentic bounds:', cfgErr)
      }
    } catch (err) {
      console.error('Error fetching AI config:', err)
      setError('Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }, [apiUrl])

  useEffect(() => {
    if (!authLoading && user) {
      fetchData()
    }
  }, [authLoading, user, fetchData])

  const selectedInstance = instances.find(i => i.id === selectedInstanceId) || null

  const handleInstanceSelect = (instance: ProviderInstance) => {
    setSelectedInstanceId(instance.id)
    // Auto-select first model from instance, or keep current if it belongs to this instance
    if (instance.available_models.length > 0) {
      if (instance.available_models.includes(selectedModel)) {
        // Keep current selection
      } else {
        setSelectedModel(instance.available_models[0])
      }
    } else {
      setSelectedModel('')
    }
    setTestResult(null)
    setSuccess(null)
  }

  const handleModelChange = (model: string) => {
    setSelectedModel(model)
    setTestResult(null)
    setSuccess(null)
  }

  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)

    try {
      const response = await authenticatedFetch(`${apiUrl}/api/config/system-ai/test`, {
        method: 'POST',
        body: JSON.stringify({
          provider_instance_id: selectedInstanceId,
          model_name: selectedModel,
        }),
      })

      const result = await response.json()
      setTestResult(result)

      if (!result.success) {
        setError(result.message)
      }
    } catch (err) {
      console.error('Error testing connection:', err)
      setError('Failed to test connection')
      setTestResult({
        success: false,
        message: 'Failed to test connection',
        provider: selectedInstance?.vendor || 'unknown',
        model: selectedModel,
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async () => {
    if (!selectedInstanceId || !selectedModel) return
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await authenticatedFetch(`${apiUrl}/api/config/system-ai`, {
        method: 'PUT',
        body: JSON.stringify({
          provider_instance_id: selectedInstanceId,
          model_name: selectedModel,
        }),
      })

      const result = await response.json()

      if (result.success) {
        setSuccess(result.message)
        setConfig({
          provider: result.vendor || selectedInstance?.vendor || '',
          model_name: selectedModel,
          provider_instance_id: selectedInstanceId,
          instance_name: result.instance_name || selectedInstance?.instance_name,
          vendor: result.vendor || selectedInstance?.vendor,
        })
      } else {
        setError(result.message || 'Failed to save configuration')
      }
    } catch (err) {
      console.error('Error saving config:', err)
      setError('Failed to save configuration')
    } finally {
      setSaving(false)
    }
  }

  const hasChanges =
    config &&
    (selectedInstanceId !== config.provider_instance_id || selectedModel !== config.model_name)

  const handleSavePlatformBounds = async () => {
    setSavingPlatform(true)
    setPlatformError(null)
    setPlatformSuccess(null)
    try {
      // Clamp + sanity-check before sending. Backend Field validators also
      // enforce 1..8 but we surface the message to the user up front.
      let minRounds = Math.round(platformMinRounds)
      let maxRounds = Math.round(platformMaxRounds)
      if (!Number.isFinite(minRounds) || minRounds < 1) minRounds = 1
      if (!Number.isFinite(maxRounds) || maxRounds > 8) maxRounds = 8
      if (maxRounds < minRounds) {
        setPlatformError('Max rounds must be greater than or equal to min rounds.')
        return
      }

      const updated = await apiClient.updateConfig({
        platform_min_agentic_rounds: minRounds,
        platform_max_agentic_rounds: maxRounds,
      } as Partial<Config>)
      setPlatformConfig(updated)
      setPlatformMinRounds(updated.platform_min_agentic_rounds ?? minRounds)
      setPlatformMaxRounds(updated.platform_max_agentic_rounds ?? maxRounds)
      setPlatformSuccess('Platform agentic-loop bounds saved.')
    } catch (err: any) {
      console.error('Failed to save platform bounds:', err)
      setPlatformError(err?.message || 'Failed to save platform bounds')
    } finally {
      setSavingPlatform(false)
    }
  }

  const platformBoundsChanged =
    platformConfig != null &&
    ((platformConfig.platform_min_agentic_rounds ?? 1) !== platformMinRounds ||
      (platformConfig.platform_max_agentic_rounds ?? 8) !== platformMaxRounds)

  const healthDot = (status: string) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-400'
      case 'degraded':
        return 'bg-yellow-400'
      case 'unavailable':
        return 'bg-red-400'
      default:
        return 'bg-gray-400'
    }
  }

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  if (!hasPermission('org.settings.read')) {
    return (
      <div className="container mx-auto px-4 py-8">
        <div className="bg-red-900/20 border border-red-800 rounded-lg p-6">
          <h3 className="text-lg font-semibold text-red-100 mb-2">Access Denied</h3>
          <p className="text-sm text-red-200">You do not have permission to view AI configuration.</p>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-4xl mx-auto">
        {/* Back link */}
        <Link
          href="/settings"
          className="inline-flex items-center gap-2 text-sm text-teal-400 hover:text-teal-300 mb-6 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
          </svg>
          Back to Settings
        </Link>

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-display font-bold text-white">System AI Configuration</h1>
          <p className="text-tsushin-slate mt-2">
            Select which AI provider instance and model to use for system-level operations
          </p>
        </div>

        {/* Status Messages */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 flex items-start gap-3">
            <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{error}</span>
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 flex items-start gap-3">
            <svg className="w-5 h-5 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{success}</span>
          </div>
        )}

        {/* Info Card */}
        <div className="glass-card rounded-xl p-6 mb-8">
          <div className="flex items-start gap-4">
            <div className="w-10 h-10 rounded-lg bg-teal-500/10 flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">What is System AI?</h3>
              <p className="text-sm text-tsushin-slate">
                System AI is used for internal operations like intent classification, skill routing,
                and AI-powered summaries. Choose a fast and affordable model for best cost efficiency.
                This is separate from the AI models used by individual agents.
              </p>
            </div>
          </div>
        </div>

        {/* No Instances Warning */}
        {instances.length === 0 && (
          <div className="glass-card rounded-xl p-8 mb-8 text-center">
            <div className="w-16 h-16 mx-auto mb-4 rounded-xl bg-yellow-500/10 flex items-center justify-center">
              <svg className="w-8 h-8 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-white mb-2">No Provider Instances Configured</h3>
            <p className="text-sm text-tsushin-slate mb-4">
              You need at least one AI provider instance to configure System AI.
              Create one in the Hub first.
            </p>
            <Link
              href="/hub"
              className="inline-flex items-center gap-2 px-4 py-2 bg-teal-500 hover:bg-teal-400 text-white rounded-lg transition-colors text-sm font-medium"
            >
              Go to Hub
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        )}

        {/* Provider Instance Selection */}
        {instances.length > 0 && (
          <>
            <div className="glass-card rounded-xl p-6 mb-6">
              <h3 className="text-lg font-semibold text-white mb-4">Select Provider Instance</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {instances.map((instance) => {
                  const colors = VENDOR_COLORS[instance.vendor] || VENDOR_COLORS.custom
                  const VendorIcon = VENDOR_ICONS[instance.vendor] || BeakerIcon
                  const isSelected = selectedInstanceId === instance.id

                  return (
                    <button
                      key={instance.id}
                      onClick={() => canEdit && handleInstanceSelect(instance)}
                      disabled={!canEdit}
                      className={`p-4 rounded-xl border transition-all text-left ${
                        isSelected
                          ? `${colors.bg} ${colors.border} ring-2 ring-offset-2 ring-offset-tsushin-darker ring-current`
                          : 'border-white/10 hover:border-white/20'
                      } ${!canEdit ? 'opacity-60 cursor-not-allowed' : ''}`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`w-10 h-10 rounded-lg ${colors.bg} flex items-center justify-center ${colors.text}`}>
                          <VendorIcon size={20} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="text-white font-medium truncate">{instance.instance_name}</p>
                            <span className={`w-2 h-2 rounded-full shrink-0 ${healthDot(instance.health_status)}`} />
                          </div>
                          <p className="text-xs text-tsushin-slate">
                            {VENDOR_LABELS[instance.vendor] || instance.vendor}
                            {instance.available_models.length > 0 && (
                              <> &middot; {instance.available_models.length} model{instance.available_models.length !== 1 ? 's' : ''}</>
                            )}
                          </p>
                        </div>
                        {instance.is_default && (
                          <span className="text-[10px] uppercase tracking-wider text-tsushin-slate bg-white/5 px-1.5 py-0.5 rounded">
                            default
                          </span>
                        )}
                      </div>
                    </button>
                  )
                })}
              </div>
              <p className="text-xs text-tsushin-slate mt-4">
                Manage instances in the{' '}
                <Link href="/hub" className="text-teal-400 hover:text-teal-300 underline">Hub</Link>.
              </p>
            </div>

            {/* Model Selection */}
            {selectedInstance && selectedInstance.available_models.length > 0 && (
              <div className="glass-card rounded-xl p-6 mb-6">
                <h3 className="text-lg font-semibold text-white mb-4">Select Model</h3>
                <div className="space-y-2">
                  {selectedInstance.available_models.map((model) => {
                    const isSelected = selectedModel === model
                    const colors = VENDOR_COLORS[selectedInstance.vendor] || VENDOR_COLORS.custom

                    return (
                      <button
                        key={model}
                        onClick={() => canEdit && handleModelChange(model)}
                        disabled={!canEdit}
                        className={`w-full p-3 rounded-lg border transition-all text-left flex items-center justify-between ${
                          isSelected
                            ? `${colors.bg} ${colors.border}`
                            : 'border-white/10 hover:border-white/20'
                        } ${!canEdit ? 'opacity-60 cursor-not-allowed' : ''}`}
                      >
                        <span className="text-sm text-white font-mono">{model}</span>
                        {isSelected && (
                          <svg className={`w-5 h-5 ${colors.text}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                      </button>
                    )
                  })}
                </div>
              </div>
            )}

            {/* No models warning */}
            {selectedInstance && selectedInstance.available_models.length === 0 && (
              <div className="glass-card rounded-xl p-6 mb-6">
                <div className="flex items-start gap-3">
                  <svg className="w-5 h-5 text-yellow-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                  <div>
                    <p className="text-yellow-400 font-medium">No models available</p>
                    <p className="text-sm text-tsushin-slate mt-1">
                      This instance has no models configured. Edit it in the{' '}
                      <Link href="/hub" className="text-teal-400 hover:text-teal-300 underline">Hub</Link>{' '}
                      to discover or add models.
                    </p>
                    {/* Allow manual model entry */}
                    <div className="mt-3">
                      <label className="text-xs text-tsushin-slate mb-1 block">Or enter a model name manually:</label>
                      <input
                        type="text"
                        value={selectedModel}
                        onChange={(e) => handleModelChange(e.target.value)}
                        placeholder="e.g. gemini-2.5-flash"
                        disabled={!canEdit}
                        className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white placeholder-tsushin-slate/50 focus:outline-none focus:border-teal-500/50 disabled:opacity-60"
                      />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Test Connection */}
            {canEdit && selectedInstanceId && selectedModel && (
              <div className="glass-card rounded-xl p-6 mb-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-white">Test Connection</h3>
                  <button
                    onClick={handleTestConnection}
                    disabled={testing}
                    className="px-4 py-2 text-sm bg-white/5 hover:bg-white/10 text-white border border-white/20 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
                  >
                    {testing ? (
                      <>
                        <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Testing...
                      </>
                    ) : (
                      <>
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                        Test Connection
                      </>
                    )}
                  </button>
                </div>

                <p className="text-sm text-tsushin-slate mb-4">
                  Send a test message to verify the provider instance is accessible with the selected model.
                </p>

                {testResult && (
                  <div className={`p-4 rounded-lg ${testResult.success ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
                    <div className="flex items-start gap-3">
                      {testResult.success ? (
                        <svg className="w-5 h-5 text-green-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      ) : (
                        <svg className="w-5 h-5 text-red-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      )}
                      <div>
                        <p className={testResult.success ? 'text-green-400' : 'text-red-400'}>
                          {testResult.message}
                        </p>
                        {testResult.token_usage && (
                          <p className="text-xs text-tsushin-slate mt-1">
                            Tokens used: {testResult.token_usage.total_tokens || 'N/A'}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Save Button */}
            {canEdit && (
              <div className="flex items-center justify-between glass-card rounded-xl p-6">
                <div>
                  {hasChanges && (
                    <p className="text-sm text-yellow-400 flex items-center gap-2">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      You have unsaved changes
                    </p>
                  )}
                </div>
                <button
                  onClick={handleSave}
                  disabled={saving || !hasChanges || !selectedInstanceId || !selectedModel}
                  className="px-6 py-2.5 bg-teal-500 hover:bg-teal-400 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {saving ? (
                    <>
                      <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Saving...
                    </>
                  ) : (
                    'Save Configuration'
                  )}
                </button>
              </div>
            )}
          </>
        )}

        {/* Platform AI — Agentic Loop Bounds (BUG-716) */}
        <div className="glass-card rounded-xl p-6 mt-8">
          <div className="flex items-start gap-4 mb-4">
            <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center shrink-0">
              <svg className="w-5 h-5 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <div>
              <h3 className="text-white font-medium mb-1">Platform AI — Agentic Loop Bounds</h3>
              <p className="text-sm text-tsushin-slate">
                Hard upper/lower bounds for the bounded agentic loop. Per-agent
                <code className="mx-1 px-1.5 py-0.5 text-xs rounded bg-white/5 border border-white/10">max_agentic_rounds</code>
                values are clamped into this range at runtime, regardless of what an agent owner saved.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
            <div>
              <label className="block text-sm font-medium text-tsushin-slate mb-2">
                Minimum rounds
              </label>
              <input
                type="number"
                min={1}
                max={8}
                disabled={!canEdit}
                value={platformMinRounds}
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10)
                  setPlatformMinRounds(Number.isFinite(n) ? n : 1)
                }}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-500/50 disabled:opacity-60"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-tsushin-slate mb-2">
                Maximum rounds
              </label>
              <input
                type="number"
                min={1}
                max={8}
                disabled={!canEdit}
                value={platformMaxRounds}
                onChange={(e) => {
                  const n = parseInt(e.target.value, 10)
                  setPlatformMaxRounds(Number.isFinite(n) ? n : 8)
                }}
                className="w-full px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-teal-500/50 disabled:opacity-60"
              />
            </div>
          </div>

          {platformError && (
            <div className="p-3 mb-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {platformError}
            </div>
          )}
          {platformSuccess && (
            <div className="p-3 mb-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
              {platformSuccess}
            </div>
          )}

          {canEdit && (
            <div className="flex items-center justify-between">
              <p className="text-xs text-tsushin-slate">
                {platformBoundsChanged ? 'Unsaved changes' : 'Range 1 – 8.'}
              </p>
              <button
                onClick={handleSavePlatformBounds}
                disabled={savingPlatform || !platformBoundsChanged}
                className="px-4 py-2 text-sm bg-purple-500 hover:bg-purple-400 text-white font-medium rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {savingPlatform ? 'Saving...' : 'Save Platform Bounds'}
              </button>
            </div>
          )}
        </div>

        {/* Read-only notice */}
        {!canEdit && (
          <div className="glass-card rounded-xl p-6 text-center mt-8">
            <p className="text-tsushin-slate">
              You don&apos;t have permission to modify system AI configuration.
              Contact your organization admin to make changes.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
