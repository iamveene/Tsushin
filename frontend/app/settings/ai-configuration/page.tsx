'use client'

/**
 * System AI Configuration Settings Page
 * Phase 17: Tenant-Configurable System AI Provider
 *
 * Allows users to configure which AI provider and model is used for
 * system-level operations like intent classification, skill routing,
 * and AI summaries.
 */

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'

interface ProviderOption {
  value: string
  label: string
  description: string
}

interface ModelOption {
  value: string
  label: string
  description: string
}

interface SystemAIConfig {
  provider: string
  model_name: string
}

interface TestResult {
  success: boolean
  message: string
  provider: string
  model: string
  token_usage?: Record<string, number>
  error?: string
}

// Provider icons for display
const PROVIDER_ICONS: Record<string, React.ReactNode> = {
  gemini: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/>
    </svg>
  ),
  anthropic: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
    </svg>
  ),
  openai: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0l-4.83-2.786A4.504 4.504 0 0 1 2.34 7.872zm16.597 3.855l-5.833-3.387L15.119 7.2a.076.076 0 0 1 .071 0l4.83 2.791a4.494 4.494 0 0 1-.676 8.105v-5.678a.79.79 0 0 0-.407-.667zm2.01-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.83-2.787a4.5 4.5 0 0 1 6.68 4.66zm-12.64 4.135l-2.02-1.164a.08.08 0 0 1-.038-.057V6.075a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.704 5.46a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/>
    </svg>
  ),
  openrouter: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="currentColor">
      <path d="M13 3v6h8V3h-8zM3 21h8v-6H3v6zm0-8h8V3H3v10zm10 8h8v-6h-8v6z"/>
    </svg>
  ),
}

// Provider colors for styling
const PROVIDER_COLORS: Record<string, { bg: string; text: string; border: string }> = {
  gemini: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  anthropic: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' },
  openai: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  openrouter: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
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
  const [providers, setProviders] = useState<ProviderOption[]>([])
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelOption[]>>({})

  const [selectedProvider, setSelectedProvider] = useState<string>('')
  const [selectedModel, setSelectedModel] = useState<string>('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }, [])

  // Fetch current config, providers, and models
  const fetchData = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)

      // Fetch current config
      const configRes = await fetch(`${apiUrl}/api/config/system-ai`, {
        headers: getAuthHeaders()
      })

      if (configRes.ok) {
        const configData = await configRes.json()
        setConfig(configData)
        setSelectedProvider(configData.provider)
        setSelectedModel(configData.model_name)
      } else {
        throw new Error('Failed to load configuration')
      }

      // Fetch available providers
      const providersRes = await fetch(`${apiUrl}/api/config/system-ai/providers`, {
        headers: getAuthHeaders()
      })

      if (providersRes.ok) {
        const providersData = await providersRes.json()
        setProviders(providersData.providers)
      }

      // Fetch all models by provider
      const modelsRes = await fetch(`${apiUrl}/api/config/system-ai/models`, {
        headers: getAuthHeaders()
      })

      if (modelsRes.ok) {
        const modelsData = await modelsRes.json()
        setModelsByProvider(modelsData.models_by_provider)
      }

    } catch (err) {
      console.error('Error fetching AI config:', err)
      setError('Failed to load configuration')
    } finally {
      setLoading(false)
    }
  }, [apiUrl, getAuthHeaders])

  useEffect(() => {
    if (!authLoading && user) {
      fetchData()
    }
  }, [authLoading, user, fetchData])

  // Handle provider change
  const handleProviderChange = (provider: string) => {
    setSelectedProvider(provider)
    // Select first model from the new provider
    const models = modelsByProvider[provider] || []
    if (models.length > 0) {
      setSelectedModel(models[0].value)
    } else {
      setSelectedModel('')
    }
    setTestResult(null)
  }

  // Handle model change
  const handleModelChange = (model: string) => {
    setSelectedModel(model)
    setTestResult(null)
  }

  // Test connection
  const handleTestConnection = async () => {
    setTesting(true)
    setTestResult(null)
    setError(null)

    try {
      const response = await fetch(`${apiUrl}/api/config/system-ai/test`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          provider: selectedProvider,
          model_name: selectedModel
        })
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
        provider: selectedProvider,
        model: selectedModel
      })
    } finally {
      setTesting(false)
    }
  }

  // Save configuration
  const handleSave = async () => {
    setSaving(true)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(`${apiUrl}/api/config/system-ai`, {
        method: 'PUT',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          provider: selectedProvider,
          model_name: selectedModel
        })
      })

      const result = await response.json()

      if (result.success) {
        setSuccess(result.message)
        setConfig({ provider: selectedProvider, model_name: selectedModel })
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

  // Check if there are unsaved changes
  const hasChanges = config && (selectedProvider !== config.provider || selectedModel !== config.model_name)

  // Get current provider's models
  const currentModels = modelsByProvider[selectedProvider] || []

  // Get selected model details
  const selectedModelDetails = currentModels.find(m => m.value === selectedModel)

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
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
            Configure which AI provider and model is used for system-level operations
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

        {/* Current Configuration */}
        {config && (
          <div className="glass-card rounded-xl p-6 mb-8">
            <h3 className="text-lg font-semibold text-white mb-4">Current Configuration</h3>
            <div className="flex items-center gap-4">
              <div className={`w-12 h-12 rounded-lg ${PROVIDER_COLORS[config.provider]?.bg || 'bg-gray-500/10'} flex items-center justify-center ${PROVIDER_COLORS[config.provider]?.text || 'text-gray-400'}`}>
                {PROVIDER_ICONS[config.provider] || (
                  <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                )}
              </div>
              <div>
                <p className="text-white font-medium">
                  {providers.find(p => p.value === config.provider)?.label || config.provider}
                </p>
                <p className="text-sm text-tsushin-slate">{config.model_name}</p>
              </div>
            </div>
          </div>
        )}

        {/* Provider Selection */}
        <div className="glass-card rounded-xl p-6 mb-6">
          <h3 className="text-lg font-semibold text-white mb-4">Select AI Provider</h3>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {providers.map((provider) => {
              const colors = PROVIDER_COLORS[provider.value] || { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' }
              const isSelected = selectedProvider === provider.value

              return (
                <button
                  key={provider.value}
                  onClick={() => canEdit && handleProviderChange(provider.value)}
                  disabled={!canEdit}
                  className={`p-4 rounded-xl border transition-all text-left ${
                    isSelected
                      ? `${colors.bg} ${colors.border} ring-2 ring-offset-2 ring-offset-tsushin-darker ring-current`
                      : 'border-white/10 hover:border-white/20'
                  } ${!canEdit ? 'opacity-60 cursor-not-allowed' : ''}`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`w-10 h-10 rounded-lg ${colors.bg} flex items-center justify-center ${colors.text}`}>
                      {PROVIDER_ICONS[provider.value] || (
                        <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                        </svg>
                      )}
                    </div>
                    <div>
                      <p className="text-white font-medium">{provider.label}</p>
                      <p className="text-xs text-tsushin-slate">{provider.description}</p>
                    </div>
                  </div>
                </button>
              )
            })}
          </div>
        </div>

        {/* Model Selection */}
        {selectedProvider && currentModels.length > 0 && (
          <div className="glass-card rounded-xl p-6 mb-6">
            <h3 className="text-lg font-semibold text-white mb-4">Select Model</h3>
            <div className="space-y-3">
              {currentModels.map((model) => {
                const isSelected = selectedModel === model.value
                const colors = PROVIDER_COLORS[selectedProvider] || { bg: 'bg-gray-500/10', text: 'text-gray-400', border: 'border-gray-500/30' }

                return (
                  <button
                    key={model.value}
                    onClick={() => canEdit && handleModelChange(model.value)}
                    disabled={!canEdit}
                    className={`w-full p-4 rounded-xl border transition-all text-left flex items-center justify-between ${
                      isSelected
                        ? `${colors.bg} ${colors.border}`
                        : 'border-white/10 hover:border-white/20'
                    } ${!canEdit ? 'opacity-60 cursor-not-allowed' : ''}`}
                  >
                    <div>
                      <p className="text-white font-medium">{model.label}</p>
                      <p className="text-xs text-tsushin-slate mt-0.5">{model.description}</p>
                    </div>
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

        {/* Test Connection */}
        {canEdit && selectedProvider && selectedModel && (
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
              Send a test message to verify the API key is configured and the provider is accessible.
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
              disabled={saving || !hasChanges}
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

        {/* Read-only notice */}
        {!canEdit && (
          <div className="glass-card rounded-xl p-6 text-center">
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
