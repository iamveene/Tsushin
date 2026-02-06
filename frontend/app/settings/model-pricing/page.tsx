'use client'

/**
 * Model Pricing Settings Page
 *
 * Allows users to view and customize LLM pricing rates for cost estimation.
 * Custom pricing overrides system defaults per model.
 */

import React, { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useRequireAuth } from '@/contexts/AuthContext'

interface ModelPricing {
  id?: number
  model_provider: string
  model_name: string
  display_name?: string
  input_cost_per_million: number
  output_cost_per_million: number
  cached_input_cost_per_million?: number
  is_active: boolean
  is_default: boolean
}

interface PricingResponse {
  pricing: ModelPricing[]
  count: number
}

// Provider display configuration
const PROVIDER_CONFIG: Record<string, { name: string; color: string; bgColor: string }> = {
  openai: { name: 'OpenAI', color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' },
  anthropic: { name: 'Anthropic', color: 'text-orange-400', bgColor: 'bg-orange-500/10' },
  gemini: { name: 'Google', color: 'text-blue-400', bgColor: 'bg-blue-500/10' },
  kokoro: { name: 'Kokoro', color: 'text-pink-400', bgColor: 'bg-pink-500/10' },
  elevenlabs: { name: 'ElevenLabs', color: 'text-cyan-400', bgColor: 'bg-cyan-500/10' },
  ollama: { name: 'Ollama (Local)', color: 'text-purple-400', bgColor: 'bg-purple-500/10' },
  unknown: { name: 'Other', color: 'text-gray-400', bgColor: 'bg-gray-500/10' },
}

export default function ModelPricingPage() {
  const { user, loading: authLoading, hasPermission } = useRequireAuth()
  const canEdit = hasPermission('org.settings.write')

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [pricing, setPricing] = useState<ModelPricing[]>([])
  const [editingModel, setEditingModel] = useState<string | null>(null)
  const [editValues, setEditValues] = useState<{ input: string; output: string }>({ input: '', output: '' })
  const [filterProvider, setFilterProvider] = useState<string>('all')

  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8081'

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('tsushin_auth_token') : null
    return {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {})
    }
  }, [])

  const fetchPricing = useCallback(async () => {
    try {
      setLoading(true)
      const response = await fetch(`${apiUrl}/api/settings/model-pricing`, {
        headers: getAuthHeaders()
      })

      if (response.ok) {
        const data: PricingResponse = await response.json()
        setPricing(data.pricing)
      } else {
        setError('Failed to load pricing data')
      }
    } catch (err) {
      console.error('Error fetching pricing:', err)
      setError('Failed to load pricing data')
    } finally {
      setLoading(false)
    }
  }, [apiUrl, getAuthHeaders])

  useEffect(() => {
    if (!authLoading && user) {
      fetchPricing()
    }
  }, [authLoading, user, fetchPricing])

  const handleEdit = (model: ModelPricing) => {
    const key = `${model.model_provider}:${model.model_name}`
    setEditingModel(key)
    setEditValues({
      input: model.input_cost_per_million.toString(),
      output: model.output_cost_per_million.toString()
    })
  }

  const handleSave = async (model: ModelPricing) => {
    const key = `${model.model_provider}:${model.model_name}`
    setSaving(key)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        `${apiUrl}/api/settings/model-pricing/${model.model_provider}/${model.model_name}`,
        {
          method: 'PUT',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            model_provider: model.model_provider,
            model_name: model.model_name,
            display_name: model.display_name,
            input_cost_per_million: parseFloat(editValues.input) || 0,
            output_cost_per_million: parseFloat(editValues.output) || 0,
            is_active: true
          })
        }
      )

      if (response.ok) {
        setSuccess(`Pricing for ${model.display_name || model.model_name} updated`)
        setEditingModel(null)
        await fetchPricing()
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Failed to update pricing')
      }
    } catch (err) {
      setError('Failed to update pricing')
    } finally {
      setSaving(null)
    }
  }

  const handleReset = async (model: ModelPricing) => {
    if (model.is_default) return

    const key = `${model.model_provider}:${model.model_name}`
    setSaving(key)
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(
        `${apiUrl}/api/settings/model-pricing/${model.model_provider}/${model.model_name}`,
        {
          method: 'DELETE',
          headers: getAuthHeaders()
        }
      )

      if (response.ok) {
        setSuccess(`${model.display_name || model.model_name} reset to default pricing`)
        await fetchPricing()
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Failed to reset pricing')
      }
    } catch (err) {
      setError('Failed to reset pricing')
    } finally {
      setSaving(null)
    }
  }

  const handleResetAll = async () => {
    if (!confirm('Reset all pricing to system defaults? This will delete all custom pricing configurations.')) {
      return
    }

    setSaving('all')
    setError(null)
    setSuccess(null)

    try {
      const response = await fetch(`${apiUrl}/api/settings/model-pricing/reset`, {
        method: 'POST',
        headers: getAuthHeaders()
      })

      if (response.ok) {
        setSuccess('All pricing reset to system defaults')
        await fetchPricing()
      } else {
        const errorData = await response.json()
        setError(errorData.detail || 'Failed to reset pricing')
      }
    } catch (err) {
      setError('Failed to reset pricing')
    } finally {
      setSaving(null)
    }
  }

  const cancelEdit = () => {
    setEditingModel(null)
    setEditValues({ input: '', output: '' })
  }

  // Group pricing by provider
  const providers = [...new Set(pricing.map(p => p.model_provider))]
  const filteredPricing = filterProvider === 'all'
    ? pricing
    : pricing.filter(p => p.model_provider === filterProvider)

  const formatCost = (cost: number) => {
    if (cost === 0) return '$0.00'
    if (cost < 0.01) return `$${cost.toFixed(4)}`
    return `$${cost.toFixed(2)}`
  }

  const hasCustomPricing = pricing.some(p => !p.is_default)

  if (authLoading || loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-gray-600 dark:text-gray-400">Loading...</div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="max-w-6xl mx-auto">
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
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="text-3xl font-display font-bold text-white">Model Pricing</h1>
            <p className="text-tsushin-slate mt-2">
              Configure LLM pricing rates for cost estimation in the debug panel
            </p>
          </div>

          {canEdit && hasCustomPricing && (
            <button
              onClick={handleResetAll}
              disabled={saving === 'all'}
              className="px-4 py-2 text-sm text-red-400 hover:text-red-300 border border-red-500/30 hover:border-red-500/50 rounded-lg transition-colors disabled:opacity-50"
            >
              {saving === 'all' ? 'Resetting...' : 'Reset All to Defaults'}
            </button>
          )}
        </div>

        {/* Status Messages */}
        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400">
            {error}
          </div>
        )}
        {success && (
          <div className="mb-6 p-4 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400">
            {success}
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
              <h3 className="text-white font-medium mb-1">How Pricing Works</h3>
              <p className="text-sm text-tsushin-slate">
                Pricing rates are used to estimate API costs in the playground debug panel.
                Rates are per 1 million tokens. Default rates are based on official provider pricing.
                Custom rates you set will override defaults for your organization.
              </p>
            </div>
          </div>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-4 mb-6">
          <span className="text-sm text-white/60">Filter by provider:</span>
          <div className="flex gap-2">
            <button
              onClick={() => setFilterProvider('all')}
              className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                filterProvider === 'all'
                  ? 'bg-teal-500/20 text-teal-400 border border-teal-500/30'
                  : 'text-white/60 hover:text-white hover:bg-white/5'
              }`}
            >
              All
            </button>
            {providers.map(provider => {
              const config = PROVIDER_CONFIG[provider] || PROVIDER_CONFIG.unknown
              return (
                <button
                  key={provider}
                  onClick={() => setFilterProvider(provider)}
                  className={`px-3 py-1.5 text-sm rounded-lg transition-colors ${
                    filterProvider === provider
                      ? `${config.bgColor} ${config.color} border border-current/30`
                      : 'text-white/60 hover:text-white hover:bg-white/5'
                  }`}
                >
                  {config.name}
                </button>
              )
            })}
          </div>
        </div>

        {/* Pricing Table */}
        <div className="glass-card rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-white/10">
                <th className="text-left px-6 py-4 text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Model
                </th>
                <th className="text-right px-6 py-4 text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Input (per 1M)
                </th>
                <th className="text-right px-6 py-4 text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Output (per 1M)
                </th>
                <th className="text-center px-6 py-4 text-xs font-semibold text-white/50 uppercase tracking-wider">
                  Status
                </th>
                {canEdit && (
                  <th className="text-right px-6 py-4 text-xs font-semibold text-white/50 uppercase tracking-wider">
                    Actions
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {filteredPricing.map((model) => {
                const key = `${model.model_provider}:${model.model_name}`
                const isEditing = editingModel === key
                const isSaving = saving === key
                const config = PROVIDER_CONFIG[model.model_provider] || PROVIDER_CONFIG.unknown

                return (
                  <tr key={key} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="px-6 py-4">
                      <div className="flex items-center gap-3">
                        <span className={`px-2 py-1 text-xs rounded ${config.bgColor} ${config.color}`}>
                          {config.name}
                        </span>
                        <div>
                          <p className="text-white font-medium">{model.display_name || model.model_name}</p>
                          <p className="text-xs text-white/40">{model.model_name}</p>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.001"
                          min="0"
                          value={editValues.input}
                          onChange={(e) => setEditValues({ ...editValues, input: e.target.value })}
                          className="w-24 px-2 py-1 text-right bg-white/5 border border-white/20 rounded text-white text-sm focus:border-teal-500 focus:outline-none"
                        />
                      ) : (
                        <span className="text-white font-mono">{formatCost(model.input_cost_per_million)}</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          step="0.001"
                          min="0"
                          value={editValues.output}
                          onChange={(e) => setEditValues({ ...editValues, output: e.target.value })}
                          className="w-24 px-2 py-1 text-right bg-white/5 border border-white/20 rounded text-white text-sm focus:border-teal-500 focus:outline-none"
                        />
                      ) : (
                        <span className="text-white font-mono">{formatCost(model.output_cost_per_million)}</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-center">
                      {model.is_default ? (
                        <span className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded bg-white/5 text-white/50">
                          Default
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded bg-teal-500/10 text-teal-400">
                          Custom
                        </span>
                      )}
                    </td>
                    {canEdit && (
                      <td className="px-6 py-4 text-right">
                        {isEditing ? (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={cancelEdit}
                              className="px-3 py-1 text-sm text-white/60 hover:text-white transition-colors"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleSave(model)}
                              disabled={isSaving}
                              className="px-3 py-1 text-sm bg-teal-500/20 text-teal-400 hover:bg-teal-500/30 rounded transition-colors disabled:opacity-50"
                            >
                              {isSaving ? 'Saving...' : 'Save'}
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center justify-end gap-2">
                            <button
                              onClick={() => handleEdit(model)}
                              className="px-3 py-1 text-sm text-white/60 hover:text-white transition-colors"
                            >
                              Edit
                            </button>
                            {!model.is_default && (
                              <button
                                onClick={() => handleReset(model)}
                                disabled={isSaving}
                                className="px-3 py-1 text-sm text-red-400/60 hover:text-red-400 transition-colors disabled:opacity-50"
                              >
                                Reset
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>

          {filteredPricing.length === 0 && (
            <div className="px-6 py-12 text-center text-white/40">
              No models found for the selected filter
            </div>
          )}
        </div>

        {/* Footer Note */}
        <p className="mt-6 text-sm text-white/40 text-center">
          Pricing estimates are based on official provider rates and may not reflect actual charges.
          Check provider documentation for current pricing.
        </p>
      </div>
    </div>
  )
}
